-- ============================================================
-- Migration 012: Views — Business Intelligence & Reporting
-- ============================================================
-- SCM System views for inventory analysis, cost valuation,
-- stock ledger, and accounting summaries.
-- ============================================================

-- ------------------------------------------------------------
-- 1. wms.v_quant_summary
--    Aggregates stock_movements by quant for inventory summary.
--    Shows total receipt, issue, assembly, transfer quantities.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW wms.v_quant_summary AS
SELECT
  q.id AS quant_id,
  q.parts_id,
  q.storage_bin_id,
  q.stock_type,
  q.physical_qty,
  q.system_qty,
  q.reserved_qty,
  q.blocked_qty,
  q.available_qty,
  COALESCE(SUM(CASE WHEN sm.movement_type IN ('101','501','561','161','262') AND sm.to_bin_id = q.storage_bin_id THEN sm.actual_qty ELSE 0 END), 0) AS total_receipt_qty,
  COALESCE(SUM(CASE WHEN sm.movement_type IN ('201','261','551','601','122') AND sm.from_bin_id = q.storage_bin_id THEN sm.actual_qty ELSE 0 END), 0) AS total_issue_qty,
  COALESCE(SUM(CASE WHEN sm.movement_type = '301' AND sm.to_bin_id = q.storage_bin_id THEN sm.actual_qty ELSE 0 END), 0) AS transfer_in_qty,
  COALESCE(SUM(CASE WHEN sm.movement_type = '301' AND sm.from_bin_id = q.storage_bin_id THEN sm.actual_qty ELSE 0 END), 0) AS transfer_out_qty
FROM wms.quants q
LEFT JOIN mm.stock_movements sm
  ON sm.parts_id = q.parts_id
  AND (sm.to_bin_id = q.storage_bin_id OR sm.from_bin_id = q.storage_bin_id)
  AND sm.status = 'completed'
GROUP BY q.id, q.parts_id, q.storage_bin_id, q.stock_type,
         q.physical_qty, q.system_qty, q.reserved_qty, q.blocked_qty, q.available_qty;


-- ------------------------------------------------------------
-- 2. shared.v_available_qty (improved)
--    Shows available quantities per parts with reserved qty
--    deducted. Only considers unrestricted stock.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW shared.v_available_qty AS
SELECT
  p.id AS parts_id,
  p.parts_code,
  p.parts_name,
  p.vendor_id,
  p.parts_type,
  p.material_type_id,
  COALESCE(SUM(q.available_qty), 0) AS available_qty,
  COALESCE(SUM(q.system_qty), 0)    AS system_qty,
  COALESCE(SUM(q.physical_qty), 0)  AS physical_qty,
  COALESCE(SUM(q.reserved_qty), 0)  AS reserved_qty,
  COALESCE(SUM(q.blocked_qty), 0)   AS blocked_qty
FROM shared.parts_master p
LEFT JOIN wms.quants q ON q.parts_id = p.id AND q.stock_type = 'unrestricted'
GROUP BY p.id, p.parts_code, p.parts_name, p.vendor_id, p.parts_type, p.material_type_id;


-- ------------------------------------------------------------
-- 3. finance.v_cost_weighted_avg (FIXED — includes opening balance)
--    Weighted average cost calculation per parts per period,
--    incorporating prior period closing balance.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW finance.v_cost_weighted_avg AS
WITH period_data AS (
  SELECT
    sm.parts_id,
    DATE_TRUNC('month', sm.actual_date) AS period,
    SUM(CASE WHEN sm.movement_type IN ('101','501','561') THEN sm.actual_qty ELSE 0 END) AS receipt_qty,
    SUM(CASE WHEN sm.movement_type IN ('101','501','561') THEN sm.total_cost ELSE 0 END) AS receipt_cost
  FROM mm.stock_movements sm
  WHERE sm.status = 'completed' AND sm.total_cost IS NOT NULL
  GROUP BY sm.parts_id, DATE_TRUNC('month', sm.actual_date)
)
SELECT
  pd.parts_id,
  pd.period,
  COALESCE(pc.closing_qty, 0) AS opening_qty,
  COALESCE(pc.closing_value, 0) AS opening_value,
  pd.receipt_qty,
  pd.receipt_cost,
  CASE
    WHEN (COALESCE(pc.closing_qty, 0) + pd.receipt_qty) > 0
    THEN (COALESCE(pc.closing_value, 0) + pd.receipt_cost)
       / (COALESCE(pc.closing_qty, 0) + pd.receipt_qty)
    ELSE 0
  END AS weighted_avg_unit_cost
FROM period_data pd
LEFT JOIN finance.period_closes pc
  ON pc.parts_id = pd.parts_id
  AND pc.period = TO_CHAR(pd.period - INTERVAL '1 month', 'YYYY-MM')
  AND pc.is_closed = TRUE;


-- ------------------------------------------------------------
-- 4. finance.v_cost_fifo (FIXED — uses gr_id direct link)
--    FIFO cost layers from active batches, linked to
--    goods_receipts via gr_id for receipt date ordering.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW finance.v_cost_fifo AS
SELECT
  b.parts_id,
  b.id AS batch_id,
  b.batch_number,
  b.unit_cost AS fifo_unit_cost,
  b.remaining_qty,
  gr.actual_receipt_date AS receipt_date,
  gr.received_qty AS original_qty
FROM wms.batches b
LEFT JOIN mm.goods_receipts gr ON gr.id = b.gr_id
WHERE b.unit_cost IS NOT NULL AND b.status = 'active'
ORDER BY b.parts_id, gr.actual_receipt_date NULLS LAST;


-- ------------------------------------------------------------
-- 5. finance.v_inventory_valuation
--    K-IFRS IAS 2 inventory valuation view.
--    Uses latest weighted average cost per parts.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW finance.v_inventory_valuation AS
SELECT
  p.parts_id,
  p.parts_code,
  p.parts_name,
  p.available_qty,
  p.physical_qty,
  COALESCE(wa.weighted_avg_unit_cost, 0) AS unit_cost_weighted_avg,
  COALESCE(wa.weighted_avg_unit_cost, 0) * p.available_qty AS inventory_value_weighted_avg
FROM shared.v_available_qty p
LEFT JOIN (
  SELECT DISTINCT ON (parts_id) parts_id, weighted_avg_unit_cost
  FROM finance.v_cost_weighted_avg
  ORDER BY parts_id, period DESC
) wa ON wa.parts_id = p.parts_id;


-- ------------------------------------------------------------
-- 6. finance.v_stock_ledger (재고수불부) ★NEW
--    Period-based stock ledger showing opening balance,
--    receipts, issues, and closing balance per parts.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW finance.v_stock_ledger AS
WITH movements AS (
  SELECT
    TO_CHAR(sm.actual_date, 'YYYY-MM') AS period,
    sm.parts_id,
    SUM(CASE WHEN sm.movement_type IN ('101','501','561','161','262','701') AND sm.to_bin_id IS NOT NULL
        THEN sm.actual_qty ELSE 0 END) AS receipt_qty,
    SUM(CASE WHEN sm.movement_type IN ('101','501','561','161','262','701') AND sm.total_cost IS NOT NULL
        THEN sm.total_cost ELSE 0 END) AS receipt_value,
    SUM(CASE WHEN sm.movement_type IN ('201','261','551','601','122','702') AND sm.from_bin_id IS NOT NULL
        THEN sm.actual_qty ELSE 0 END) AS issue_qty,
    SUM(CASE WHEN sm.movement_type IN ('201','261','551','601','122','702') AND sm.total_cost IS NOT NULL
        THEN sm.total_cost ELSE 0 END) AS issue_value
  FROM mm.stock_movements sm
  WHERE sm.status = 'completed'
  GROUP BY TO_CHAR(sm.actual_date, 'YYYY-MM'), sm.parts_id
)
SELECT
  m.period,
  m.parts_id,
  pm.parts_code,
  pm.parts_name,
  COALESCE(pc.closing_qty, 0) AS opening_qty,
  COALESCE(pc.closing_value, 0) AS opening_value,
  m.receipt_qty,
  m.receipt_value,
  m.issue_qty,
  m.issue_value,
  COALESCE(pc.closing_qty, 0) + m.receipt_qty - m.issue_qty AS closing_qty,
  COALESCE(pc.closing_value, 0) + m.receipt_value - m.issue_value AS closing_value
FROM movements m
JOIN shared.parts_master pm ON pm.id = m.parts_id
LEFT JOIN finance.period_closes pc
  ON pc.parts_id = m.parts_id
  AND pc.period = TO_CHAR((m.period || '-01')::DATE - INTERVAL '1 month', 'YYYY-MM')
  AND pc.is_closed = TRUE;


-- ------------------------------------------------------------
-- 7. finance.v_accounting_summary
--    Aggregated accounting entries by type and status.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW finance.v_accounting_summary AS
SELECT
  ae.entry_type,
  ae.status,
  COUNT(*) AS entry_count,
  SUM(ae.amount) AS total_amount,
  MIN(ae.entry_date) AS earliest_date,
  MAX(ae.entry_date) AS latest_date
FROM finance.accounting_entries ae
GROUP BY ae.entry_type, ae.status
ORDER BY ae.entry_type, ae.status;
