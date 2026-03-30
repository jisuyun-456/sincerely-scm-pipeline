SELECT
  id,
  doc_number,
  posting_date,
  period,
  parts_code,
  NULLIF(location_from, '') AS location_from,
  NULLIF(location_to,   '') AS location_to,
  movement_type,
  quantity,
  direction,
  quantity * direction       AS signed_qty,
  status,
  at_purpose,
  source,
  CASE movement_type
    WHEN '101' THEN '입고GR'
    WHEN '201' THEN '생산투입'
    WHEN '261' THEN '조립/외주투입'
    WHEN '311' THEN '창고이동'
    WHEN '312' THEN '반품'
    WHEN '561' THEN '기초재고'
    WHEN '601' THEN '고객납품'
    WHEN '701' THEN '재고조정'
    ELSE movement_type
  END AS movement_type_label
FROM sap.mat_document
WHERE status = 'posted'
