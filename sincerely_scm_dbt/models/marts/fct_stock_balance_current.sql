SELECT
  sb.parts_code,
  mm.parts_name,
  sb.location,
  sb.period,
  sb.qty_on_hand,
  sb.updated_at,
  mm.is_customer_goods,
  CASE WHEN sb.qty_on_hand < 0 THEN true ELSE false END AS is_negative
FROM sap.stock_balance sb
LEFT JOIN sap.mat_master mm ON mm.parts_code = sb.parts_code
WHERE sb.period = (SELECT MAX(period) FROM sap.stock_balance)
