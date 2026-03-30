SELECT
  md.period,
  md.parts_code,
  md.parts_name,
  md.managed_location                                          AS location,
  SUM(CASE WHEN md.direction =  1 THEN md.quantity ELSE 0 END) AS total_in,
  SUM(CASE WHEN md.direction = -1 THEN md.quantity ELSE 0 END) AS total_out,
  SUM(md.signed_qty)                                           AS net_change
FROM {{ ref('fct_inventory_movement') }} md
WHERE md.movement_type != '561'
GROUP BY md.period, md.parts_code, md.parts_name, md.managed_location
