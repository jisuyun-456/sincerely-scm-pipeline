SELECT
  mm.parts_code,
  mm.parts_name,
  mm.location,
  mm.is_customer_goods,
  COALESCE(sb.qty_on_hand, 0) AS current_qty,
  sb.period                   AS balance_period
FROM sap.mat_master mm
LEFT JOIN sap.stock_balance sb
  ON  sb.parts_code = mm.parts_code
 AND sb.period = (SELECT MAX(period) FROM sap.stock_balance)
