SELECT
  sb.parts_code,
  sb.location,
  sb.period,
  sb.qty_on_hand,
  sb.updated_at,
  mm.parts_name,
  mm.is_customer_goods
FROM sap.stock_balance sb
LEFT JOIN sap.mat_master mm ON mm.parts_code = sb.parts_code
