-- ============================================================
-- Sincerely SCM — Supabase 재고 스냅샷 스키마
-- 재고 로직 분석 결과 기반
-- ============================================================

-- 스냅샷 메타데이터
CREATE TABLE IF NOT EXISTS snapshot_log (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_date   DATE NOT NULL,
    snapshot_ts     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source_base     TEXT NOT NULL DEFAULT 'appLui4ZR5HWcQRri',
    tables_synced   TEXT[] NOT NULL,
    record_counts   JSONB NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'running', -- running | completed | failed
    error_message   TEXT,
    duration_sec    NUMERIC(10,2)
);

CREATE INDEX idx_snapshot_log_date ON snapshot_log(snapshot_date DESC);

-- ─── 1. material_stock (재고 원장) ───
CREATE TABLE IF NOT EXISTS material_stock (
    id                  BIGSERIAL,
    snapshot_id         BIGINT NOT NULL REFERENCES snapshot_log(id),
    snapshot_date       DATE NOT NULL,
    airtable_record_id  TEXT NOT NULL,

    -- 식별자
    name                TEXT,           -- 파츠명 || 위치
    location            TEXT,           -- 재고위치
    coordinates         TEXT[],         -- 좌표
    created_at          TIMESTAMPTZ,

    -- 핵심 재고 수량
    physical_qty        INT DEFAULT 0,  -- 실물재고수량
    system_qty          INT DEFAULT 0,  -- 전산재고수량
    available_qty       INT DEFAULT 0,  -- 가용재고수량
    sellable_qty        INT DEFAULT 0,  -- 판매가능수량

    -- 전산재고 구성 요소
    initial_stock           INT DEFAULT 0,  -- 기초재고
    procurement_qty         INT DEFAULT 0,  -- 구매조달완료수량
    production_output_qty   INT DEFAULT 0,  -- 생산산출완료수량
    assembly_output_qty     INT DEFAULT 0,  -- 조립산출완료수량
    assembly_input_qty      INT DEFAULT 0,  -- 조립투입완료수량
    transfer_in_qty         INT DEFAULT 0,  -- 이동입고완료수량
    transfer_out_qty        INT DEFAULT 0,  -- 이동출고완료수량
    production_input_qty    INT DEFAULT 0,  -- 생산투입완료수량
    customer_delivery_qty   INT DEFAULT 0,  -- 고객주문납품수량
    adj_in_qty              INT DEFAULT 0,  -- 재고조정수량(입고)
    adj_out_qty             INT DEFAULT 0,  -- 재고조정수량(출고)

    -- 예정 수량 (가용재고 차감)
    wip_qty                     INT DEFAULT 0,
    assembly_planned_qty        INT DEFAULT 0,
    outbound_request_qty        INT DEFAULT 0,
    production_planned_qty      INT DEFAULT 0,
    reserved_qty                INT DEFAULT 0,
    procurement_planned_qty     INT DEFAULT 0,
    secured_pipeline_qty        INT DEFAULT 0,
    customer_order_planned_qty  INT DEFAULT 0,

    -- 실사
    physical_check_qty      INT,
    last_check_at           TIMESTAMPTZ,
    physical_system_diff    INT DEFAULT 0,
    audit_qty_2412          TEXT,
    closing_qty_2412        INT,
    closing_qty_2025        INT,

    -- 자재 이동 참조
    inbound_movement_ids    TEXT[],
    outbound_movement_ids   TEXT,

    -- 검증용 계산 필드
    calc_system_qty         INT GENERATED ALWAYS AS (
        COALESCE(procurement_qty, 0)
        + COALESCE(production_output_qty, 0)
        + COALESCE(assembly_output_qty, 0)
        + COALESCE(transfer_in_qty, 0)
        + COALESCE(adj_in_qty, 0)
        - COALESCE(production_input_qty, 0)
        - COALESCE(assembly_input_qty, 0)
        - COALESCE(transfer_out_qty, 0)
        - COALESCE(customer_delivery_qty, 0)
        - COALESCE(adj_out_qty, 0)
    ) STORED,

    system_qty_mismatch     INT GENERATED ALWAYS AS (
        system_qty - (
            COALESCE(procurement_qty, 0)
            + COALESCE(production_output_qty, 0)
            + COALESCE(assembly_output_qty, 0)
            + COALESCE(transfer_in_qty, 0)
            + COALESCE(adj_in_qty, 0)
            - COALESCE(production_input_qty, 0)
            - COALESCE(assembly_input_qty, 0)
            - COALESCE(transfer_out_qty, 0)
            - COALESCE(customer_delivery_qty, 0)
            - COALESCE(adj_out_qty, 0)
        )
    ) STORED,

    PRIMARY KEY (id)
);

CREATE INDEX idx_material_snapshot ON material_stock(snapshot_date, name);
CREATE INDEX idx_material_mismatch ON material_stock(snapshot_date) WHERE system_qty_mismatch != 0;
CREATE INDEX idx_material_record ON material_stock(airtable_record_id, snapshot_date);

-- ─── 2. movement (재고 이동 트랜잭션) ───
CREATE TABLE IF NOT EXISTS movement (
    id                  BIGSERIAL,
    snapshot_id         BIGINT NOT NULL REFERENCES snapshot_log(id),
    snapshot_date       DATE NOT NULL,
    airtable_record_id  TEXT NOT NULL,

    -- 식별자
    movement_id         TEXT,
    item_description    TEXT,
    movement_purpose    TEXT,
    movement_type       TEXT,

    -- 수량
    movement_qty        INT DEFAULT 0,
    receiving_qty       INT DEFAULT 0,
    shipping_qty        INT DEFAULT 0,
    inbound_qty         INT DEFAULT 0,
    return_out_qty      INT DEFAULT 0,
    return_in_qty       INT DEFAULT 0,
    return_qty          INT DEFAULT 0,
    planned_qty         INT DEFAULT 0,
    inspection_qty      INT DEFAULT 0,
    defect_sampling_qty INT DEFAULT 0,
    defect_full_qty     INT DEFAULT 0,
    disposal_qty        INT DEFAULT 0,

    -- 자재 참조
    inbound_material    TEXT,
    outbound_material   TEXT,
    inbound_item        TEXT,

    -- 위치
    inbound_location    TEXT,
    outbound_location   TEXT,
    coordinate          TEXT,

    -- 일자
    actual_receiving_date   DATE,
    planned_move_date       DATE,
    stock_adj_date          DATE,

    -- 상태
    shipping_status         TEXT,
    qty_inspection_result   TEXT,
    move_request_completed  TEXT,

    -- 프리징
    frozen_qty          INT DEFAULT 0,
    frozen_item         TEXT,

    -- 실사
    audit_basket_qty    INT DEFAULT 0,
    physical_pre_adj_qty INT DEFAULT 0,
    adj_qty_check       INT DEFAULT 0,

    -- 참조
    pkg_task            TEXT,
    material_input_order TEXT,

    PRIMARY KEY (id)
);

CREATE INDEX idx_movement_snapshot ON movement(snapshot_date, movement_id);
CREATE INDEX idx_movement_purpose ON movement(snapshot_date, movement_purpose);
CREATE INDEX idx_movement_item ON movement(item_description, snapshot_date);

-- ─── 3. orders (주문/발주) ───
CREATE TABLE IF NOT EXISTS orders (
    id                  BIGSERIAL,
    snapshot_id         BIGINT NOT NULL REFERENCES snapshot_log(id),
    snapshot_date       DATE NOT NULL,
    airtable_record_id  TEXT NOT NULL,

    -- 식별자
    order_id            TEXT,
    parts_name          TEXT,
    project_name        TEXT,
    order_created_date  DATE,
    created_time        DATE,

    -- 수량
    order_qty           INT DEFAULT 0,
    po_qty              INT DEFAULT 0,
    stock_out_qty       INT DEFAULT 0,
    stock_in_qty        INT DEFAULT 0,
    return_out_qty      INT DEFAULT 0,
    return_in_qty       INT DEFAULT 0,
    stock_deduct_qty    INT DEFAULT 0,
    purchase_qty        INT DEFAULT 0,
    return_in_func_qty  INT DEFAULT 0,

    -- 상태
    po_stage                TEXT,
    stock_usage_purpose     TEXT,
    stock_production_status TEXT,
    is_stock_item           TEXT,
    managed_stock_flag      TEXT[],

    -- 일자
    inbound_date            DATE,
    outbound_date           TEXT,
    separate_outbound_date  DATE,
    last_outbound_date      DATE,

    -- 위치
    stock_coordinates       TEXT[],
    stock_location          TEXT,
    inbound_location        TEXT,
    outbound_location       TEXT,

    -- 실사
    audit_basket1_qty   INT DEFAULT 0,
    audit_basket2_qty   INT DEFAULT 0,
    audit_basket3_qty   INT DEFAULT 0,
    audit_basket4_qty   INT DEFAULT 0,
    adj_qty             INT DEFAULT 0,
    physical_qty        INT DEFAULT 0,
    physical_pre_adj_qty INT DEFAULT 0,

    PRIMARY KEY (id)
);

CREATE INDEX idx_orders_snapshot ON orders(snapshot_date, order_id);
CREATE INDEX idx_orders_parts ON orders(parts_name, snapshot_date);
CREATE INDEX idx_orders_project ON orders(project_name, snapshot_date);

-- ─── 4. project (프로젝트 마스터) ───
CREATE TABLE IF NOT EXISTS project (
    id                  BIGSERIAL,
    snapshot_id         BIGINT NOT NULL REFERENCES snapshot_log(id),
    snapshot_date       DATE NOT NULL,
    airtable_record_id  TEXT NOT NULL,

    name                TEXT,
    status              TEXT,
    project_status      TEXT,
    customer_company    TEXT,
    first_outbound_date DATE,
    last_outbound_date  DATE,
    outbound_days       INT,
    po_items            TEXT,
    logistics_new       TEXT,
    po_request_date     DATE,
    fulfillment_leadtime INT,

    PRIMARY KEY (id)
);

CREATE INDEX idx_project_snapshot ON project(snapshot_date);

-- ─── 분석용 뷰 ───

-- 최신 스냅샷의 재고 불일치 항목
CREATE OR REPLACE VIEW v_latest_stock_mismatch AS
SELECT
    name,
    location,
    system_qty,
    calc_system_qty,
    system_qty_mismatch,
    physical_qty,
    available_qty,
    sellable_qty,
    snapshot_date
FROM material_stock
WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM snapshot_log WHERE status = 'completed')
  AND system_qty_mismatch != 0
ORDER BY ABS(system_qty_mismatch) DESC;

-- 최신 스냅샷의 재고 요약 (위치별)
CREATE OR REPLACE VIEW v_latest_stock_summary AS
SELECT
    location,
    COUNT(*) AS item_count,
    SUM(physical_qty) AS total_physical,
    SUM(system_qty) AS total_system,
    SUM(available_qty) AS total_available,
    SUM(sellable_qty) AS total_sellable,
    SUM(CASE WHEN system_qty_mismatch != 0 THEN 1 ELSE 0 END) AS mismatch_count,
    snapshot_date
FROM material_stock
WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM snapshot_log WHERE status = 'completed')
GROUP BY location, snapshot_date
ORDER BY total_physical DESC;

-- 파츠별 재고 추이 (스냅샷 간 비교)
CREATE OR REPLACE VIEW v_stock_trend AS
SELECT
    name,
    snapshot_date,
    system_qty,
    physical_qty,
    available_qty,
    system_qty - LAG(system_qty) OVER (PARTITION BY name ORDER BY snapshot_date) AS qty_change,
    system_qty_mismatch
FROM material_stock
ORDER BY name, snapshot_date;
