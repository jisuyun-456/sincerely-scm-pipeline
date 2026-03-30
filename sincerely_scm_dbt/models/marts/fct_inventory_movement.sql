SELECT
  md.id,
  md.doc_number,
  md.posting_date,
  md.period,
  md.parts_code,
  mm.parts_name,
  md.location_from,
  md.location_to,
  md.movement_type,
  md.movement_type_label,
  md.quantity,
  md.direction,
  md.signed_qty,
  md.at_purpose,
  md.source,
  mm.is_customer_goods,
  CASE md.direction WHEN 1 THEN '입고' ELSE '출고' END AS direction_label,
  CASE md.direction
    WHEN  1 THEN md.location_to
    WHEN -1 THEN md.location_from
  END AS managed_location
FROM {{ ref('stg_mat_document') }} md
LEFT JOIN {{ ref('stg_mat_master') }} mm
  ON mm.parts_code = md.parts_code
