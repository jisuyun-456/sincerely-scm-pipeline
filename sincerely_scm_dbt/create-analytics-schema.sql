-- ============================================================
-- Sincerely SCM — analytics 스키마 생성
-- Supabase Dashboard > SQL Editor 에서 전체 실행
-- ============================================================

CREATE SCHEMA IF NOT EXISTS analytics;

-- ────────────────────────────────────────────────────────────
-- STAGING 뷰 (sap 원본 정제)
-- ────────────────────────────────────────────────────────────

CREATE OR REPLACE VIEW analytics.stg_mat_document AS
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
WHERE status = 'posted';

CREATE OR REPLACE VIEW analytics.stg_mat_master AS
SELECT
  parts_code,
  parts_name,
  is_customer_goods
FROM sap.mat_master;

CREATE OR REPLACE VIEW analytics.stg_stock_balance AS
SELECT
  sb.parts_code,
  sb.location,
  sb.period,
  sb.qty_on_hand,
  sb.updated_at,
  mm.parts_name,
  mm.is_customer_goods
FROM sap.stock_balance sb
LEFT JOIN sap.mat_master mm ON mm.parts_code = sb.parts_code;

-- ────────────────────────────────────────────────────────────
-- MARTS 테이블 (분석용 집계, 필요 시 MATERIALIZED VIEW로 전환)
-- ────────────────────────────────────────────────────────────

-- 1. 이동 팩트 (파츠명 조인 + 방향 라벨)
CREATE OR REPLACE VIEW analytics.fct_inventory_movement AS
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
FROM analytics.stg_mat_document md
LEFT JOIN analytics.stg_mat_master mm ON mm.parts_code = md.parts_code;

-- 2. 현재 잔액 (최신 기간, 음수 플래그)
CREATE OR REPLACE VIEW analytics.fct_stock_balance_current AS
SELECT
  sb.parts_code,
  mm.parts_name,
  sb.location,
  sb.period,
  sb.qty_on_hand,
  sb.updated_at,
  mm.is_customer_goods,
  (sb.qty_on_hand < 0) AS is_negative
FROM sap.stock_balance sb
LEFT JOIN sap.mat_master mm ON mm.parts_code = sb.parts_code
WHERE sb.period = (SELECT MAX(period) FROM sap.stock_balance);

-- 3. 기간별 입출고 요약
CREATE OR REPLACE VIEW analytics.fct_period_summary AS
SELECT
  md.period,
  md.parts_code,
  md.parts_name,
  md.managed_location                                          AS location,
  SUM(CASE WHEN md.direction =  1 THEN md.quantity ELSE 0 END) AS total_in,
  SUM(CASE WHEN md.direction = -1 THEN md.quantity ELSE 0 END) AS total_out,
  SUM(md.signed_qty)                                           AS net_change
FROM analytics.fct_inventory_movement md
WHERE md.movement_type != '561'
GROUP BY md.period, md.parts_code, md.parts_name, md.managed_location;

-- 4. 파츠 마스터 + 현재 잔액 디멘션 (location은 stock_balance 기준)
CREATE OR REPLACE VIEW analytics.dim_parts AS
SELECT
  mm.parts_code,
  mm.parts_name,
  mm.is_customer_goods,
  sb.location,
  COALESCE(sb.qty_on_hand, 0) AS current_qty,
  sb.period                   AS balance_period
FROM sap.mat_master mm
LEFT JOIN sap.stock_balance sb
  ON  sb.parts_code = mm.parts_code
 AND sb.period = (SELECT MAX(period) FROM sap.stock_balance);

-- ────────────────────────────────────────────────────────────
-- 확인 쿼리
-- ────────────────────────────────────────────────────────────
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'analytics'
ORDER BY table_name;
