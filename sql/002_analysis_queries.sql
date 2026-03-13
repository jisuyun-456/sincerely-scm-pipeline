-- ============================================================
-- 재고 불일치 분석 쿼리 모음
-- 스냅샷 적재 후 이 쿼리들로 분석 실행
-- ============================================================

-- ① 전산재고 공식 불일치 항목 (calc_system_qty vs system_qty)
-- system_qty_mismatch != 0 이면 Airtable Automation 계산 오류
SELECT
    name,
    location,
    system_qty           AS "전산재고(Airtable)",
    calc_system_qty      AS "전산재고(공식계산)",
    system_qty_mismatch  AS "오차",
    procurement_qty      AS "구매조달",
    production_output_qty AS "생산산출",
    assembly_input_qty   AS "조립투입",
    transfer_in_qty      AS "이동입고",
    transfer_out_qty     AS "이동출고",
    adj_in_qty           AS "조정입고",
    adj_out_qty          AS "조정출고"
FROM material_stock
WHERE snapshot_date = CURRENT_DATE
  AND system_qty_mismatch != 0
ORDER BY ABS(system_qty_mismatch) DESC
LIMIT 50;


-- ② 실물재고 vs 전산재고 차이 (실사 필요 항목)
SELECT
    name,
    location,
    physical_qty    AS "실물수량",
    system_qty      AS "전산수량",
    physical_qty - system_qty AS "차이",
    last_check_at   AS "최종체크일",
    CURRENT_DATE - last_check_at::date AS "체크경과일"
FROM material_stock
WHERE snapshot_date = CURRENT_DATE
  AND physical_qty != system_qty
  AND (physical_qty != 0 OR system_qty != 0)
ORDER BY ABS(physical_qty - system_qty) DESC;


-- ③ 가용재고 부족 위험 항목 (예정수량 > 가용수량)
SELECT
    name,
    location,
    available_qty       AS "가용재고",
    sellable_qty        AS "판매가능",
    assembly_planned_qty AS "조립예정",
    reserved_qty        AS "예약",
    customer_order_planned_qty AS "주문예정",
    (assembly_planned_qty + reserved_qty + customer_order_planned_qty) AS "총필요량",
    available_qty - (assembly_planned_qty + reserved_qty + customer_order_planned_qty) AS "잔여"
FROM material_stock
WHERE snapshot_date = CURRENT_DATE
  AND available_qty < (assembly_planned_qty + reserved_qty + customer_order_planned_qty)
  AND available_qty > 0
ORDER BY (available_qty - assembly_planned_qty - reserved_qty - customer_order_planned_qty) ASC;


-- ④ 특정 파츠 전체 이력 추적 (예: PT0493)
SELECT
    m.snapshot_date,
    m.name,
    m.system_qty,
    m.physical_qty,
    m.available_qty,
    m.calc_system_qty,
    m.system_qty_mismatch,
    m.procurement_qty,
    m.assembly_input_qty,
    m.transfer_in_qty,
    m.transfer_out_qty
FROM material_stock m
WHERE m.name LIKE 'PT0493%'
ORDER BY m.snapshot_date, m.name;


-- ⑤ 일별 스냅샷 간 변동량 분석
SELECT
    name,
    snapshot_date,
    system_qty,
    system_qty - LAG(system_qty) OVER (PARTITION BY name ORDER BY snapshot_date) AS "일간변동",
    available_qty,
    available_qty - LAG(available_qty) OVER (PARTITION BY name ORDER BY snapshot_date) AS "가용변동"
FROM material_stock
WHERE name LIKE 'PT0493%'
ORDER BY name, snapshot_date;


-- ⑥ 주문별 재고 사용 현황 (특정 파츠)
SELECT
    o.order_id,
    o.project_name,
    o.parts_name,
    o.order_qty,
    o.stock_deduct_qty,
    o.return_out_qty,
    o.outbound_date,
    o.po_stage,
    o.stock_usage_purpose
FROM orders o
WHERE o.snapshot_date = CURRENT_DATE
  AND o.parts_name LIKE 'PT0493%'
ORDER BY o.order_created_date;


-- ⑦ 위치별 재고 총괄 요약
SELECT
    location,
    COUNT(*) AS "품목수",
    SUM(physical_qty) AS "총실물수량",
    SUM(system_qty) AS "총전산수량",
    SUM(available_qty) AS "총가용수량",
    SUM(CASE WHEN system_qty_mismatch != 0 THEN 1 ELSE 0 END) AS "불일치건수",
    ROUND(SUM(CASE WHEN system_qty_mismatch != 0 THEN 1 ELSE 0 END)::numeric
          / NULLIF(COUNT(*), 0) * 100, 1) AS "불일치율(%)"
FROM material_stock
WHERE snapshot_date = CURRENT_DATE
GROUP BY location
ORDER BY "총실물수량" DESC;
