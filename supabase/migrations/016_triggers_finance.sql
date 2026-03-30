-- ============================================================================
-- Migration 016: Triggers — Finance (운영이벤트 -> 전표 자동생성, GL 동적 결정)
--
-- Automatic accounting entry generation from SCM operational events:
--   1. Goods Receipt   -> DR: 재고자산 / CR: 매입채무   (from material_type GL)
--   2. Stock Movement   -> Assembly Issue (261), Assembly Receipt (262),
--                          Goods Issue (601)
--   3. Freight Order    -> DR: 운반비(831000) / CR: 미지급금(253000)
--   4. Inventory Adj.   -> Surplus: DR 재고자산 / CR 잡이익(909000)
--                          Shortage: DR 잡손실(909100) / CR 재고자산
--
-- FIX-4: GL accounts are dynamically resolved from shared.material_types
--        (default_debit_gl_id, default_credit_gl_id, issue_debit_gl_id,
--         issue_credit_gl_id) instead of being hardcoded.
--
-- Dependencies:
--   002_shared_reference_data.sql (shared.gl_accounts, shared.material_types)
--   004_shared_material_master.sql (shared.parts_master)
--   006_tms_schema.sql            (tms.freight_orders)
--   007_wms_schema.sql            (wms.inventory_count_items)
--   008_mm_schema.sql             (mm.goods_receipts, mm.stock_movements)
--   011_finance_schema.sql        (finance.accounting_entries, finance.cost_settings)
-- ============================================================================


-- =========================================================================
-- HELPER FUNCTIONS
-- =========================================================================

-- ---------------------------------------------------------------------------
-- Helper 1: Entry number generator
-- Format: AE-YYYYMMDD-NNNN (sequential per day)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION finance.generate_entry_number()
RETURNS TEXT AS $$
DECLARE
  v_date TEXT := TO_CHAR(CURRENT_DATE, 'YYYYMMDD');
  v_seq  INT;
BEGIN
  -- I4 FIX: Advisory lock prevents race condition on concurrent entry_number generation
  PERFORM pg_advisory_xact_lock(hashtext('ae_entry_number_' || v_date));

  SELECT COALESCE(MAX(CAST(SPLIT_PART(entry_number, '-', 3) AS INT)), 0) + 1
  INTO v_seq
  FROM finance.accounting_entries
  WHERE entry_number LIKE 'AE-' || v_date || '-%';

  RETURN 'AE-' || v_date || '-' || LPAD(v_seq::TEXT, 4, '0');
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION finance.generate_entry_number IS 'Generate sequential accounting entry number: AE-YYYYMMDD-NNNN';


-- ---------------------------------------------------------------------------
-- Helper 2: GL account lookup by account_code
-- Raises exception if account not found.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION finance.get_gl_account_id(p_code TEXT)
RETURNS UUID AS $$
DECLARE
  v_id UUID;
BEGIN
  SELECT id INTO v_id
  FROM shared.gl_accounts
  WHERE account_code = p_code
  LIMIT 1;

  IF v_id IS NULL THEN
    RAISE EXCEPTION 'GL account % not found', p_code;
  END IF;

  RETURN v_id;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION finance.get_gl_account_id IS 'Lookup shared.gl_accounts.id by account_code; raises exception if not found';


-- ---------------------------------------------------------------------------
-- Helper 3: Get GL accounts from material_type (FIX-4: dynamic GL lookup)
-- p_direction: 'receipt' -> default_debit/credit_gl_id
--              'issue'   -> issue_debit/credit_gl_id
-- Falls back to 146000 (원재료) / 251000 (매입채무) if no material_type found.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION finance.get_material_gl_accounts(
  p_parts_id  UUID,
  p_direction VARCHAR  -- 'receipt' or 'issue'
)
RETURNS TABLE(debit_gl_id UUID, credit_gl_id UUID) AS $$
BEGIN
  IF p_direction = 'receipt' THEN
    RETURN QUERY
    SELECT mt.default_debit_gl_id, mt.default_credit_gl_id
    FROM shared.parts_master pm
    JOIN shared.material_types mt ON mt.id = pm.material_type_id
    WHERE pm.id = p_parts_id;
  ELSIF p_direction = 'issue' THEN
    RETURN QUERY
    SELECT mt.issue_debit_gl_id, mt.issue_credit_gl_id
    FROM shared.parts_master pm
    JOIN shared.material_types mt ON mt.id = pm.material_type_id
    WHERE pm.id = p_parts_id;
  END IF;

  -- Fallback if no material_type mapping found
  IF NOT FOUND THEN
    RETURN QUERY
    SELECT finance.get_gl_account_id('146000'),
           finance.get_gl_account_id('251000');
  END IF;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION finance.get_material_gl_accounts IS 'Dynamic GL account resolution from material_type (FIX-4). Fallback: 146000/251000';


-- =========================================================================
-- TRIGGER 1: Goods Receipt -> Accounting Entry
-- =========================================================================

-- ---------------------------------------------------------------------------
-- finance.trg_goods_receipt_entry()
-- AFTER INSERT on mm.goods_receipts
-- DR: 재고자산 (from material_type.default_debit_gl_id)
-- CR: 매입채무 (from material_type.default_credit_gl_id)
--
-- I5 NOTE: This trigger fires on EVERY INSERT unconditionally.
-- This is INTENTIONAL — all goods receipts immediately generate a 'draft'
-- accounting entry. The entry must be reviewed/posted via the workflow
-- (draft → reviewed → posted). Invalid GRs can be corrected by creating
-- a reversal entry (is_reversal = TRUE) rather than deleting.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION finance.trg_goods_receipt_entry()
RETURNS TRIGGER AS $$
DECLARE
  v_dr      UUID;
  v_cr      UUID;
  v_costing TEXT;
  v_amount  NUMERIC(15,2);
BEGIN
  -- Get GL accounts from material_type (FIX-4: dynamic lookup)
  SELECT debit_gl_id, credit_gl_id INTO v_dr, v_cr
  FROM finance.get_material_gl_accounts(NEW.parts_id, 'receipt');

  -- Get costing method from cost_settings (per parts_type)
  SELECT cs.costing_method INTO v_costing
  FROM finance.cost_settings cs
  JOIN shared.parts_master pm ON pm.parts_type = cs.parts_type
  WHERE pm.id = NEW.parts_id
    AND cs.effective_to IS NULL
  LIMIT 1;

  -- Calculate amount (must be > 0 per CHECK constraint)
  v_amount := COALESCE(NEW.total_cost, 0);
  IF v_amount <= 0 THEN
    -- Cannot create entry with zero/negative amount; skip silently
    RETURN NEW;
  END IF;

  INSERT INTO finance.accounting_entries (
    entry_number, entry_date, entry_type,
    source_table, source_id,
    debit_account_id, credit_account_id, amount,
    quantity, unit_cost, costing_method,
    tax_invoice_no, vat_amount,
    fiscal_year, fiscal_period,
    status
  ) VALUES (
    finance.generate_entry_number(),
    COALESCE(NEW.posting_date, NEW.actual_receipt_date, CURRENT_DATE),
    'goods_receipt',
    'mm.goods_receipts', NEW.id,
    v_dr, v_cr, v_amount,
    NEW.received_qty,
    NEW.unit_cost,
    COALESCE(v_costing, 'weighted_avg'),
    NEW.tax_invoice_no, NEW.vat_amount,
    TO_CHAR(COALESCE(NEW.posting_date, CURRENT_DATE), 'YYYY'),
    TO_CHAR(COALESCE(NEW.posting_date, CURRENT_DATE), 'MM'),
    'draft'
  );

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION finance.trg_goods_receipt_entry IS 'Auto-generate accounting entry on goods receipt (dynamic GL from material_type)';

DROP TRIGGER IF EXISTS trg_goods_receipt_accounting ON mm.goods_receipts;

CREATE TRIGGER trg_goods_receipt_accounting
  AFTER INSERT ON mm.goods_receipts
  FOR EACH ROW
  EXECUTE FUNCTION finance.trg_goods_receipt_entry();

COMMENT ON TRIGGER trg_goods_receipt_accounting ON mm.goods_receipts
  IS 'Auto-create draft accounting entry when a goods receipt is recorded';


-- =========================================================================
-- TRIGGER 2: Stock Movement -> Accounting Entry (selective movement types)
-- =========================================================================

-- ---------------------------------------------------------------------------
-- finance.trg_stock_movement_entry()
-- AFTER INSERT OR UPDATE OF status on mm.stock_movements
-- Only fires for specific movement types when status = 'completed':
--   261: Assembly Issue   -> DR: 재공품(WIP 147000)   / CR: 원재료 (from issue GL)
--   262: Assembly Receipt -> DR: 제품(150000)          / CR: 재공품(147000)
--   601: Goods Issue      -> DR: 매출원가 (from issue GL) / CR: 재고자산 (from issue GL)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION finance.trg_stock_movement_entry()
RETURNS TRIGGER AS $$
DECLARE
  v_dr         UUID;
  v_cr         UUID;
  v_entry_type VARCHAR(30);
  v_amount     NUMERIC(15,2);
BEGIN
  -- Only process completed movements
  IF NEW.status <> 'completed' THEN
    RETURN NEW;
  END IF;

  -- -----------------------------------------------------------------------
  -- Determine GL accounts and entry type by movement type
  -- -----------------------------------------------------------------------
  IF NEW.movement_type = '261' THEN
    -- Assembly Issue: DR 재공품(WIP) / CR 원재료 (from material_type issue GL)
    SELECT mt.issue_debit_gl_id, mt.issue_credit_gl_id INTO v_dr, v_cr
    FROM shared.parts_master pm
    JOIN shared.material_types mt ON mt.id = pm.material_type_id
    WHERE pm.id = NEW.parts_id;

    -- Override debit: assembly issue goes to WIP (147000), not COGS
    v_dr := COALESCE(
      (SELECT id FROM shared.gl_accounts WHERE account_code = '147000'),
      v_dr
    );
    v_entry_type := 'assembly_issue';

  ELSIF NEW.movement_type = '262' THEN
    -- Assembly Receipt: DR 제품(150000) / CR 재공품(WIP 147000)
    v_dr := (SELECT id FROM shared.gl_accounts WHERE account_code = '150000');
    v_cr := (SELECT id FROM shared.gl_accounts WHERE account_code = '147000');
    v_entry_type := 'assembly_receipt';

  ELSIF NEW.movement_type = '601' THEN
    -- Goods Issue (Customer Delivery): DR 매출원가 / CR 재고자산 (from material_type)
    SELECT debit_gl_id, credit_gl_id INTO v_dr, v_cr
    FROM finance.get_material_gl_accounts(NEW.parts_id, 'issue');
    v_entry_type := 'goods_issue';

  ELSE
    -- No accounting entry for other movement types
    RETURN NEW;
  END IF;

  -- Guard: both accounts must be resolved
  IF v_dr IS NULL OR v_cr IS NULL THEN
    -- Cannot determine GL accounts; skip entry (avoid blocking the movement)
    RAISE WARNING 'finance.trg_stock_movement_entry: GL accounts not resolved for movement % (type=%, parts_id=%). Skipping entry.',
      NEW.movement_number, NEW.movement_type, NEW.parts_id;
    RETURN NEW;
  END IF;

  -- Calculate amount
  v_amount := COALESCE(NEW.total_cost, 0);
  IF v_amount <= 0 THEN
    RETURN NEW;
  END IF;

  INSERT INTO finance.accounting_entries (
    entry_number, entry_date, entry_type,
    source_table, source_id,
    debit_account_id, credit_account_id, amount,
    quantity, unit_cost, costing_method,
    fiscal_year, fiscal_period,
    status
  ) VALUES (
    finance.generate_entry_number(),
    COALESCE(NEW.posting_date, NEW.actual_date, CURRENT_DATE),
    v_entry_type,
    'mm.stock_movements', NEW.id,
    v_dr, v_cr, v_amount,
    NEW.actual_qty,
    NEW.unit_cost_at_movement,
    'weighted_avg',
    TO_CHAR(COALESCE(NEW.posting_date, CURRENT_DATE), 'YYYY'),
    TO_CHAR(COALESCE(NEW.posting_date, CURRENT_DATE), 'MM'),
    'draft'
  );

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION finance.trg_stock_movement_entry IS 'Auto-generate accounting entry for assembly issue(261), assembly receipt(262), goods issue(601)';

DROP TRIGGER IF EXISTS trg_stock_movement_accounting ON mm.stock_movements;

CREATE TRIGGER trg_stock_movement_accounting
  AFTER INSERT OR UPDATE OF status ON mm.stock_movements
  FOR EACH ROW
  WHEN (NEW.status = 'completed')
  EXECUTE FUNCTION finance.trg_stock_movement_entry();

COMMENT ON TRIGGER trg_stock_movement_accounting ON mm.stock_movements
  IS 'Auto-create draft accounting entry when specific movement types are completed (261, 262, 601)';


-- =========================================================================
-- TRIGGER 3: Freight Order Billing -> Accounting Entry
-- =========================================================================

-- ---------------------------------------------------------------------------
-- finance.trg_freight_order_billing_entry()
-- AFTER UPDATE OF billing_status on tms.freight_orders
-- When billing_status changes to 'billed':
--   DR: 운반비 (831000) / CR: 미지급금 (253000)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION finance.trg_freight_order_billing_entry()
RETURNS TRIGGER AS $$
DECLARE
  v_dr     UUID;
  v_cr     UUID;
  v_amount NUMERIC(15,2);
BEGIN
  -- Only fire when billing_status transitions TO 'billed'
  IF NEW.billing_status <> 'billed' THEN
    RETURN NEW;
  END IF;
  IF OLD.billing_status = 'billed' THEN
    -- Already billed; no duplicate entry
    RETURN NEW;
  END IF;

  -- DR: 운반비 (Freight Expense)
  v_dr := finance.get_gl_account_id('831000');
  -- CR: 미지급금 (Accounts Payable - Freight)
  v_cr := finance.get_gl_account_id('253000');

  -- Amount = freight_cost (carrier cost to us)
  v_amount := COALESCE(NEW.freight_cost, 0);
  IF v_amount <= 0 THEN
    RETURN NEW;
  END IF;

  INSERT INTO finance.accounting_entries (
    entry_number, entry_date, entry_type,
    source_table, source_id,
    debit_account_id, credit_account_id, amount,
    tax_invoice_no,
    fiscal_year, fiscal_period,
    status
  ) VALUES (
    finance.generate_entry_number(),
    COALESCE(NEW.confirmed_shipment_date, NEW.planned_shipment_date, CURRENT_DATE),
    'freight',
    'tms.freight_orders', NEW.id,
    v_dr, v_cr, v_amount,
    NEW.tax_invoice_no,
    TO_CHAR(COALESCE(NEW.confirmed_shipment_date, CURRENT_DATE), 'YYYY'),
    TO_CHAR(COALESCE(NEW.confirmed_shipment_date, CURRENT_DATE), 'MM'),
    'draft'
  );

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION finance.trg_freight_order_billing_entry IS 'Auto-generate freight expense entry when freight order is billed: DR 운반비(831000) / CR 미지급금(253000)';

DROP TRIGGER IF EXISTS trg_freight_order_billing_accounting ON tms.freight_orders;

CREATE TRIGGER trg_freight_order_billing_accounting
  AFTER UPDATE OF billing_status ON tms.freight_orders
  FOR EACH ROW
  WHEN (NEW.billing_status = 'billed')
  EXECUTE FUNCTION finance.trg_freight_order_billing_entry();

COMMENT ON TRIGGER trg_freight_order_billing_accounting ON tms.freight_orders
  IS 'Auto-create draft freight expense entry when billing_status changes to billed';


-- =========================================================================
-- TRIGGER 4: Inventory Count Adjustment -> Accounting Entry
-- =========================================================================

-- ---------------------------------------------------------------------------
-- finance.trg_inventory_adjustment_entry()
-- AFTER UPDATE OF adjustment_approved on wms.inventory_count_items
-- When adjustment_approved changes to TRUE and difference <> 0:
--   Surplus (difference > 0): DR 재고자산 (from material_type) / CR 잡이익 (909000)
--   Shortage (difference < 0): DR 잡손실 (909100) / CR 재고자산 (from material_type)
--
-- Cost is estimated using weighted average from recent goods receipts.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION finance.trg_inventory_adjustment_entry()
RETURNS TRIGGER AS $$
DECLARE
  v_dr         UUID;
  v_cr         UUID;
  v_inv_gl     UUID;  -- inventory asset GL from material_type
  v_unit_cost  NUMERIC(15,4);
  v_amount     NUMERIC(15,2);
  v_abs_diff   INTEGER;
  v_entry_type VARCHAR(30) := 'inventory_adjustment';
BEGIN
  -- Only fire when adjustment_approved transitions to TRUE
  IF NEW.adjustment_approved IS NOT TRUE THEN
    RETURN NEW;
  END IF;
  IF OLD.adjustment_approved IS TRUE THEN
    -- Already processed; no duplicate entry
    RETURN NEW;
  END IF;

  -- Skip zero difference
  IF COALESCE(NEW.difference, 0) = 0 THEN
    RETURN NEW;
  END IF;

  v_abs_diff := ABS(NEW.difference);

  -- Get inventory asset GL account from material_type (receipt debit = inventory asset)
  SELECT debit_gl_id INTO v_inv_gl
  FROM finance.get_material_gl_accounts(NEW.parts_id, 'receipt');

  -- Estimate unit cost using weighted average from recent goods receipts
  SELECT COALESCE(
    (SELECT SUM(gr.total_cost) / NULLIF(SUM(gr.received_qty), 0)
     FROM mm.goods_receipts gr
     WHERE gr.parts_id = NEW.parts_id
       AND gr.total_cost IS NOT NULL
       AND gr.total_cost > 0
       AND gr.actual_receipt_date >= (CURRENT_DATE - INTERVAL '12 months')
    ),
    0
  ) INTO v_unit_cost;

  v_amount := ROUND(v_abs_diff * v_unit_cost, 2);

  -- Skip if cost cannot be determined
  IF v_amount <= 0 THEN
    RAISE WARNING 'finance.trg_inventory_adjustment_entry: Cannot determine cost for parts_id=% (difference=%). Skipping entry.',
      NEW.parts_id, NEW.difference;
    RETURN NEW;
  END IF;

  IF NEW.difference > 0 THEN
    -- Surplus (+): DR 재고자산 / CR 잡이익(909000)
    v_dr := v_inv_gl;
    v_cr := finance.get_gl_account_id('909000');
  ELSE
    -- Shortage (-): DR 잡손실(909100) / CR 재고자산
    v_dr := finance.get_gl_account_id('909100');
    v_cr := v_inv_gl;
  END IF;

  -- Guard
  IF v_dr IS NULL OR v_cr IS NULL THEN
    RAISE WARNING 'finance.trg_inventory_adjustment_entry: GL accounts not resolved for parts_id=%. Skipping.', NEW.parts_id;
    RETURN NEW;
  END IF;

  INSERT INTO finance.accounting_entries (
    entry_number, entry_date, entry_type,
    source_table, source_id,
    debit_account_id, credit_account_id, amount,
    quantity, unit_cost, costing_method,
    fiscal_year, fiscal_period,
    status
  ) VALUES (
    finance.generate_entry_number(),
    CURRENT_DATE,
    v_entry_type,
    'wms.inventory_count_items', NEW.id,
    v_dr, v_cr, v_amount,
    v_abs_diff,
    v_unit_cost,
    'weighted_avg',
    TO_CHAR(CURRENT_DATE, 'YYYY'),
    TO_CHAR(CURRENT_DATE, 'MM'),
    'draft'
  );

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION finance.trg_inventory_adjustment_entry IS 'Auto-generate inventory adjustment entry on count approval. Surplus: DR inventory/CR 잡이익. Shortage: DR 잡손실/CR inventory.';

DROP TRIGGER IF EXISTS trg_inventory_adjustment_accounting ON wms.inventory_count_items;

CREATE TRIGGER trg_inventory_adjustment_accounting
  AFTER UPDATE OF adjustment_approved ON wms.inventory_count_items
  FOR EACH ROW
  WHEN (NEW.adjustment_approved = TRUE AND COALESCE(NEW.difference, 0) <> 0)
  EXECUTE FUNCTION finance.trg_inventory_adjustment_entry();

COMMENT ON TRIGGER trg_inventory_adjustment_accounting ON wms.inventory_count_items
  IS 'Auto-create draft inventory adjustment entry when count adjustment is approved with nonzero difference';
