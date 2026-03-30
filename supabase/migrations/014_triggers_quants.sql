-- ============================================================================
-- Migration 014: Triggers — Stock Movement -> Quants Auto-Update (FIX-3)
--
-- CRITICAL BUSINESS LOGIC:
--   When a stock_movement is inserted (or updated) with status='completed',
--   automatically update wms.quants system_qty via UPSERT.
--
-- Movement type -> action mapping (SAP MSEG):
--   Decrease from_bin: 102, 122, 201, 261, 301, 309, 551, 601, 702
--   Increase to_bin:   101, 161, 262, 301, 309, 501, 561, 701
--
-- The partial unique indexes on wms.quants are:
--   quants_no_batch_unique   ON (parts_id, storage_bin_id, stock_type)           WHERE batch_id IS NULL
--   quants_with_batch_unique ON (parts_id, storage_bin_id, batch_id, stock_type) WHERE batch_id IS NOT NULL
--
-- Dependencies:
--   007_wms_schema.sql   (wms.quants, wms.storage_bins, wms.batches)
--   008_mm_schema.sql    (mm.stock_movements)
-- ============================================================================


-- ---------------------------------------------------------------------------
-- 1. Helper: wms.fn_upsert_quant
--    Handles the NULL vs NOT NULL batch_id UPSERT pattern cleanly.
--    p_qty_delta can be positive (increase) or negative (decrease).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION wms.fn_upsert_quant(
  p_parts_id    UUID,
  p_bin_id      UUID,
  p_batch_id    UUID,
  p_stock_type  VARCHAR,
  p_qty_delta   INTEGER,
  p_date        DATE
) RETURNS VOID AS $$
BEGIN
  -- Guard: skip if no bin specified
  IF p_bin_id IS NULL THEN
    RETURN;
  END IF;

  IF p_batch_id IS NULL THEN
    -- ---- Case A: batch_id IS NULL ----
    -- Uses partial unique index: quants_no_batch_unique
    INSERT INTO wms.quants (
      parts_id, storage_bin_id, batch_id, stock_type,
      system_qty, physical_qty, last_movement_date
    )
    VALUES (
      p_parts_id, p_bin_id, NULL, p_stock_type,
      GREATEST(p_qty_delta, 0), 0, p_date
    )
    ON CONFLICT (parts_id, storage_bin_id, stock_type) WHERE batch_id IS NULL
    DO UPDATE SET
      system_qty          = wms.quants.system_qty + p_qty_delta,
      last_movement_date  = COALESCE(p_date, wms.quants.last_movement_date),
      updated_at          = NOW();
  ELSE
    -- ---- Case B: batch_id IS NOT NULL ----
    -- Uses partial unique index: quants_with_batch_unique
    INSERT INTO wms.quants (
      parts_id, storage_bin_id, batch_id, stock_type,
      system_qty, physical_qty, last_movement_date
    )
    VALUES (
      p_parts_id, p_bin_id, p_batch_id, p_stock_type,
      GREATEST(p_qty_delta, 0), 0, p_date
    )
    ON CONFLICT (parts_id, storage_bin_id, batch_id, stock_type) WHERE batch_id IS NOT NULL
    DO UPDATE SET
      system_qty          = wms.quants.system_qty + p_qty_delta,
      last_movement_date  = COALESCE(p_date, wms.quants.last_movement_date),
      updated_at          = NOW();
  END IF;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION wms.fn_upsert_quant IS 'Atomic quant UPSERT handling NULL/NOT-NULL batch_id partial unique indexes. p_qty_delta is signed (+/-).';


-- ---------------------------------------------------------------------------
-- 2. Main trigger function: wms.fn_update_quants_on_movement
--    Fires AFTER INSERT OR UPDATE OF status on mm.stock_movements
--    when NEW.status = 'completed'.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION wms.fn_update_quants_on_movement()
RETURNS TRIGGER AS $$
DECLARE
  v_parts_id  UUID;
  v_from_bin  UUID;
  v_to_bin    UUID;
  v_qty       INTEGER;
  v_batch_id  UUID;
  v_date      DATE;
BEGIN
  -- Only process completed movements
  IF NEW.status <> 'completed' THEN
    RETURN NEW;
  END IF;

  v_parts_id := NEW.parts_id;
  v_from_bin := NEW.from_bin_id;
  v_to_bin   := NEW.to_bin_id;
  v_qty      := COALESCE(NEW.actual_qty, 0);
  v_batch_id := NEW.batch_id;
  v_date     := COALESCE(NEW.actual_date, CURRENT_DATE);

  -- Skip zero-quantity movements
  IF v_qty <= 0 THEN
    RETURN NEW;
  END IF;

  -- -----------------------------------------------------------------------
  -- DECREASE from_bin
  -- Movement types that consume / remove stock from the source bin:
  --   102  GR Reversal
  --   122  Return to Vendor
  --   201  Cost Center Issue (Consumption)
  --   261  Production Issue (Assembly Issue)
  --   301  Transfer Posting (bin-to-bin)
  --   309  Transfer w/o Reservation
  --   551  Scrap
  --   601  Outbound Delivery (Customer Goods Issue)
  --   702  Inventory Shortage
  -- -----------------------------------------------------------------------
  IF NEW.movement_type IN ('102','122','201','261','301','309','551','601','702')
     AND v_from_bin IS NOT NULL
  THEN
    PERFORM wms.fn_upsert_quant(
      v_parts_id, v_from_bin, v_batch_id,
      'unrestricted', -v_qty, v_date
    );
  END IF;

  -- -----------------------------------------------------------------------
  -- INCREASE to_bin
  -- Movement types that add stock to the destination bin:
  --   101  Goods Receipt
  --   161  Customer Return
  --   262  Return from Production (Assembly Receipt)
  --   301  Transfer Posting (bin-to-bin)
  --   309  Transfer w/o Reservation
  --   501  Receipt without PO
  --   561  Initial Stock Entry
  --   701  Inventory Surplus
  -- -----------------------------------------------------------------------
  IF NEW.movement_type IN ('101','161','262','301','309','501','561','701')
     AND v_to_bin IS NOT NULL
  THEN
    PERFORM wms.fn_upsert_quant(
      v_parts_id, v_to_bin, v_batch_id,
      'unrestricted', v_qty, v_date
    );
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION wms.fn_update_quants_on_movement IS 'Trigger fn: auto-update wms.quants system_qty when a stock_movement is completed (FIX-3)';


-- ---------------------------------------------------------------------------
-- 3. Create the trigger on mm.stock_movements
-- ---------------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_stock_movement_update_quants ON mm.stock_movements;

CREATE TRIGGER trg_stock_movement_update_quants
  AFTER INSERT OR UPDATE OF status ON mm.stock_movements
  FOR EACH ROW
  WHEN (NEW.status = 'completed')
  EXECUTE FUNCTION wms.fn_update_quants_on_movement();

COMMENT ON TRIGGER trg_stock_movement_update_quants ON mm.stock_movements
  IS 'Auto-update wms.quants when a stock movement reaches completed status';
