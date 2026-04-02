-- ============================================================================
-- Migration 018: Quick Wins — QM Defect Catalog, OTIF Records, Reorder Alerts,
--                              Purchasing Info Records
--
-- SAP S/4HANA mapping:
--   mm.defect_catalogs           → QS41 (Defect Catalog / Quality Code Groups)
--   mm.purchasing_info_records   → ME11 (Purchasing Info Record)
--   tms.otif_records             → TM Delivery Performance KPI
--   shared.v_reorder_alerts      → MM-MRP Reorder Point Planning (MRP Type VB)
--   mm.v_qc_defect_trend         → QM Quality Scorecard (vendor/material/period)
--   tms.v_otif_trend             → TM Delivery Performance Dashboard
--
-- Dependencies:
--   004_shared_material_master.sql  (shared.parts_master, shared.goods_master)
--   006_tms_schema.sql              (tms.freight_orders, tms.carriers)
--   008_mm_schema.sql               (mm.quality_inspections, mm.goods_receipts)
--   012_views.sql                   (shared.v_available_qty)
--
-- Business context:
--   QW-1: QC defect rate 20.6% (target ≤1%) — need structured defect tracking
--   QW-2: OTIF not automated — need persistent KPI storage
--   QW-3: 331 negative inventory items — need reorder point alerts
--   QW-4: 8 parts missing unit prices — need vendor-material price history
-- ============================================================================


-- ═══════════════════════════════════════════════════════════════════════════
-- QW-1: DEFECT CATALOG (SAP QS41 — Quality Code Groups)
-- ═══════════════════════════════════════════════════════════════════════════

-- ---------------------------------------------------------------------------
-- 1. mm.defect_catalogs — Master table for structured defect codes
-- ---------------------------------------------------------------------------
CREATE TABLE mm.defect_catalogs (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    defect_code         VARCHAR(20)     UNIQUE NOT NULL,
    defect_name         VARCHAR(200)    NOT NULL,
    defect_category     VARCHAR(50)     NOT NULL,               -- printing, manufacturing, material, dimensional, packaging, labeling, color, contamination
    severity            VARCHAR(10)     DEFAULT 'major',        -- critical, major, minor
    applies_to_group_id UUID            REFERENCES shared.material_groups(id),
    description         TEXT,
    is_active           BOOLEAN         DEFAULT TRUE,
    created_at          TIMESTAMPTZ     DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE mm.defect_catalogs IS 'Defect code master catalog — structured defect classification for QC inspections (SAP QS41)';
COMMENT ON COLUMN mm.defect_catalogs.defect_category IS 'printing | manufacturing | material | dimensional | packaging | labeling | color | contamination';
COMMENT ON COLUMN mm.defect_catalogs.severity IS 'critical (safety/legal) | major (functional) | minor (cosmetic)';
COMMENT ON COLUMN mm.defect_catalogs.applies_to_group_id IS 'Optional: restrict this defect code to a specific material group';

-- Indexes
CREATE INDEX idx_mm_dc_category     ON mm.defect_catalogs(defect_category);
CREATE INDEX idx_mm_dc_severity     ON mm.defect_catalogs(severity);
CREATE INDEX idx_mm_dc_group_id     ON mm.defect_catalogs(applies_to_group_id);
CREATE INDEX idx_mm_dc_is_active    ON mm.defect_catalogs(is_active) WHERE is_active = TRUE;

-- ---------------------------------------------------------------------------
-- 2. mm.inspection_defects — Junction table: inspection ↔ defect catalog
--    Replaces the TEXT[] defect_codes array on quality_inspections with
--    structured, queryable defect records per inspection.
-- ---------------------------------------------------------------------------
CREATE TABLE mm.inspection_defects (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    inspection_id       UUID            NOT NULL REFERENCES mm.quality_inspections(id),
    defect_catalog_id   UUID            NOT NULL REFERENCES mm.defect_catalogs(id),
    defect_qty          INTEGER         NOT NULL DEFAULT 1,
    sample_position     VARCHAR(50),                            -- which sample/batch position
    notes               TEXT,
    photo_url           TEXT,
    created_at          TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE mm.inspection_defects IS 'Defect findings per inspection — structured defect ↔ catalog linkage (replaces TEXT[] defect_codes)';
COMMENT ON COLUMN mm.inspection_defects.sample_position IS 'Position within sample batch where defect was found';

-- Indexes
CREATE INDEX idx_mm_id_inspection   ON mm.inspection_defects(inspection_id);
CREATE INDEX idx_mm_id_catalog      ON mm.inspection_defects(defect_catalog_id);

-- Unique constraint: one defect code per inspection (aggregate by qty)
CREATE UNIQUE INDEX idx_mm_id_unique_defect ON mm.inspection_defects(inspection_id, defect_catalog_id);

-- ---------------------------------------------------------------------------
-- 3. VIEW: mm.v_qc_defect_trend — QC defect rate by vendor/material/month
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW mm.v_qc_defect_trend AS
SELECT
    DATE_TRUNC('month', qi.created_at)::DATE        AS period,
    pm.vendor_id,
    v.vendor_name,
    qi.parts_id,
    pm.parts_code,
    pm.parts_name,
    COUNT(*)                                         AS inspection_count,
    SUM(qi.sample_size)                              AS total_inspected,
    SUM(qi.accepted_qty)                             AS total_accepted,
    SUM(qi.rejected_qty)                             AS total_rejected,
    CASE
        WHEN SUM(qi.sample_size) > 0
        THEN ROUND(SUM(qi.rejected_qty)::NUMERIC / SUM(qi.sample_size) * 100, 2)
        ELSE 0
    END                                              AS defect_rate_pct,
    COUNT(*) FILTER (WHERE qi.result = 'fail')       AS fail_count,
    COUNT(*) FILTER (WHERE qi.result = 'pass')       AS pass_count,
    COUNT(*) FILTER (WHERE qi.result = 'conditional') AS conditional_count
FROM mm.quality_inspections qi
JOIN shared.parts_master pm ON pm.id = qi.parts_id
LEFT JOIN shared.vendors v ON v.id = pm.vendor_id
GROUP BY
    DATE_TRUNC('month', qi.created_at)::DATE,
    pm.vendor_id, v.vendor_name,
    qi.parts_id, pm.parts_code, pm.parts_name;

COMMENT ON VIEW mm.v_qc_defect_trend IS 'QC defect rate trend — aggregated by vendor/material/month for quality dashboard';

-- ---------------------------------------------------------------------------
-- 4. VIEW: mm.v_defect_pareto — Pareto analysis of defect codes
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW mm.v_defect_pareto AS
SELECT
    dc.defect_code,
    dc.defect_name,
    dc.defect_category,
    dc.severity,
    COUNT(id2.id)                                    AS occurrence_count,
    SUM(id2.defect_qty)                              AS total_defect_qty,
    SUM(SUM(id2.defect_qty)) OVER (ORDER BY SUM(id2.defect_qty) DESC) AS cumulative_qty,
    ROUND(
        SUM(id2.defect_qty)::NUMERIC /
        NULLIF(SUM(SUM(id2.defect_qty)) OVER (), 0) * 100,
        2
    )                                                AS pct_of_total
FROM mm.defect_catalogs dc
LEFT JOIN mm.inspection_defects id2 ON id2.defect_catalog_id = dc.id
GROUP BY dc.id, dc.defect_code, dc.defect_name, dc.defect_category, dc.severity
ORDER BY total_defect_qty DESC NULLS LAST;

COMMENT ON VIEW mm.v_defect_pareto IS 'Pareto analysis of defect codes — identifies top defect types for 80/20 improvement focus';


-- ═══════════════════════════════════════════════════════════════════════════
-- QW-2: OTIF RECORDS (SAP TM Delivery Performance KPI)
-- ═══════════════════════════════════════════════════════════════════════════

-- ---------------------------------------------------------------------------
-- 5. tms.otif_records — Persistent OTIF measurement per freight order
-- ---------------------------------------------------------------------------
CREATE TABLE tms.otif_records (
    id                      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    freight_order_id        UUID            NOT NULL REFERENCES tms.freight_orders(id),
    project_id              UUID            REFERENCES shared.projects(id),
    carrier_id              UUID            REFERENCES tms.carriers(id),
    route_id                UUID            REFERENCES tms.routes(id),

    -- On Time measurement
    planned_delivery_date   DATE            NOT NULL,
    actual_delivery_date    DATE,
    on_time                 BOOLEAN,                            -- NULL = not yet measured
    time_variance_days      INTEGER,                            -- actual - planned (negative = early)

    -- In Full measurement
    planned_qty             INTEGER         NOT NULL,
    actual_qty              INTEGER,
    in_full                 BOOLEAN,                            -- NULL = not yet measured
    qty_variance            INTEGER,                            -- actual - planned (negative = short)

    -- Combined score
    otif_score              BOOLEAN GENERATED ALWAYS AS (
                                COALESCE(on_time, FALSE) AND COALESCE(in_full, FALSE)
                            ) STORED,

    -- Metadata
    measurement_date        TIMESTAMPTZ     DEFAULT NOW(),
    measured_by             UUID            REFERENCES shared.users(id),
    failure_reason          TEXT,                                -- Free text when OTIF fails
    notes                   TEXT,
    created_at              TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE tms.otif_records IS 'OTIF (On Time In Full) delivery performance records — one per freight order delivery (SAP TM Delivery KPI)';
COMMENT ON COLUMN tms.otif_records.on_time IS 'TRUE if actual_delivery_date <= planned_delivery_date';
COMMENT ON COLUMN tms.otif_records.in_full IS 'TRUE if actual_qty >= planned_qty';
COMMENT ON COLUMN tms.otif_records.otif_score IS 'GENERATED: on_time AND in_full';
COMMENT ON COLUMN tms.otif_records.time_variance_days IS 'actual - planned delivery date in days (negative = early delivery)';

-- Indexes
CREATE UNIQUE INDEX idx_tms_otif_fo          ON tms.otif_records(freight_order_id);   -- 1:1 with freight_order
CREATE INDEX idx_tms_otif_project            ON tms.otif_records(project_id);
CREATE INDEX idx_tms_otif_carrier            ON tms.otif_records(carrier_id);
CREATE INDEX idx_tms_otif_route              ON tms.otif_records(route_id);
CREATE INDEX idx_tms_otif_planned_date       ON tms.otif_records(planned_delivery_date);
CREATE INDEX idx_tms_otif_actual_date        ON tms.otif_records(actual_delivery_date);
CREATE INDEX idx_tms_otif_score              ON tms.otif_records(otif_score);
CREATE INDEX idx_tms_otif_measurement_date   ON tms.otif_records(measurement_date);

-- ---------------------------------------------------------------------------
-- 6. VIEW: tms.v_otif_trend — OTIF trend by carrier/route/period
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW tms.v_otif_trend AS
SELECT
    DATE_TRUNC('week', o.planned_delivery_date)::DATE   AS period_week,
    DATE_TRUNC('month', o.planned_delivery_date)::DATE  AS period_month,
    o.carrier_id,
    c.carrier_name,
    o.route_id,
    r.route_code,
    COUNT(*)                                             AS total_deliveries,
    COUNT(*) FILTER (WHERE o.on_time = TRUE)             AS on_time_count,
    COUNT(*) FILTER (WHERE o.in_full = TRUE)             AS in_full_count,
    COUNT(*) FILTER (WHERE o.otif_score = TRUE)          AS otif_count,
    ROUND(COUNT(*) FILTER (WHERE o.on_time = TRUE)::NUMERIC / NULLIF(COUNT(*), 0) * 100, 1)  AS on_time_pct,
    ROUND(COUNT(*) FILTER (WHERE o.in_full = TRUE)::NUMERIC / NULLIF(COUNT(*), 0) * 100, 1)  AS in_full_pct,
    ROUND(COUNT(*) FILTER (WHERE o.otif_score = TRUE)::NUMERIC / NULLIF(COUNT(*), 0) * 100, 1) AS otif_pct,
    AVG(o.time_variance_days)                            AS avg_time_variance_days
FROM tms.otif_records o
LEFT JOIN tms.carriers c ON c.id = o.carrier_id
LEFT JOIN tms.routes r ON r.id = o.route_id
GROUP BY
    DATE_TRUNC('week', o.planned_delivery_date)::DATE,
    DATE_TRUNC('month', o.planned_delivery_date)::DATE,
    o.carrier_id, c.carrier_name,
    o.route_id, r.route_code;

COMMENT ON VIEW tms.v_otif_trend IS 'OTIF delivery performance trend — weekly/monthly by carrier and route for TMS dashboard';


-- ═══════════════════════════════════════════════════════════════════════════
-- QW-3: REORDER ALERT VIEW (SAP MM-MRP Reorder Point Planning)
-- ═══════════════════════════════════════════════════════════════════════════

-- ---------------------------------------------------------------------------
-- 7. VIEW: shared.v_reorder_alerts — Parts below reorder point
--    Uses parts_master.reorder_point and parts_master.min_order_qty
--    joined with available inventory from quants.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW shared.v_reorder_alerts AS
SELECT
    p.id                    AS parts_id,
    p.parts_code,
    p.parts_name,
    p.parts_type,
    p.vendor_id,
    v.vendor_name,
    p.reorder_point,
    p.min_order_qty,
    p.procurement_type,
    aq.available_qty,
    aq.system_qty,
    aq.reserved_qty,
    -- Alert classification
    CASE
        WHEN aq.available_qty < 0 THEN 'negative_stock'
        WHEN p.reorder_point IS NOT NULL AND aq.available_qty <= 0 THEN 'stockout'
        WHEN p.reorder_point IS NOT NULL AND aq.available_qty <= p.reorder_point THEN 'below_rop'
        WHEN p.reorder_point IS NULL THEN 'no_rop_defined'
        ELSE 'ok'
    END                     AS alert_level,
    -- Suggested order quantity
    CASE
        WHEN p.reorder_point IS NOT NULL AND aq.available_qty < p.reorder_point
        THEN GREATEST(COALESCE(p.min_order_qty, 0), p.reorder_point - aq.available_qty)
        ELSE 0
    END                     AS suggested_order_qty,
    -- Open PR/PO pipeline qty (how much is already on order)
    COALESCE(open_pr.pr_qty, 0)  AS open_pr_qty,
    COALESCE(open_po.po_qty, 0)  AS open_po_qty
FROM shared.parts_master p
JOIN shared.v_available_qty aq ON aq.parts_id = p.id
LEFT JOIN shared.vendors v ON v.id = p.vendor_id
-- Open purchase requisitions
LEFT JOIN (
    SELECT parts_id, SUM(required_qty) AS pr_qty
    FROM mm.purchase_requisitions
    WHERE status IN ('open', 'approved')
    GROUP BY parts_id
) open_pr ON open_pr.parts_id = p.id
-- Open purchase orders (not yet fully received)
LEFT JOIN (
    SELECT poi.parts_id, SUM(poi.ordered_qty - COALESCE(poi.received_qty, 0)) AS po_qty
    FROM mm.purchase_order_items poi
    JOIN mm.purchase_orders po ON po.id = poi.po_id
    WHERE po.po_status IN ('draft', 'sent', 'confirmed', 'partial_received')
    GROUP BY poi.parts_id
) open_po ON open_po.parts_id = p.id
WHERE p.is_stock_managed = TRUE AND p.status = 'active'
ORDER BY
    CASE
        WHEN aq.available_qty < 0 THEN 1
        WHEN p.reorder_point IS NOT NULL AND aq.available_qty <= 0 THEN 2
        WHEN p.reorder_point IS NOT NULL AND aq.available_qty <= p.reorder_point THEN 3
        ELSE 4
    END,
    aq.available_qty ASC;

COMMENT ON VIEW shared.v_reorder_alerts IS 'Reorder point alert view — shows parts below ROP with suggested order quantities (SAP MRP Type VB)';


-- ═══════════════════════════════════════════════════════════════════════════
-- QW-4: PURCHASING INFO RECORDS (SAP ME11 — Info Record)
-- ═══════════════════════════════════════════════════════════════════════════

-- ---------------------------------------------------------------------------
-- 8. mm.purchasing_info_records — Vendor-material price history
-- ---------------------------------------------------------------------------
CREATE TABLE mm.purchasing_info_records (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    parts_id            UUID            NOT NULL REFERENCES shared.parts_master(id),
    vendor_id           UUID            NOT NULL REFERENCES shared.vendors(id),

    -- Pricing
    net_price           NUMERIC(15,2)   NOT NULL,
    currency_code       VARCHAR(3)      DEFAULT 'KRW',
    price_unit          INTEGER         DEFAULT 1,              -- price per X units (e.g., price per 100 EA)
    unit_of_measure     VARCHAR(10)     DEFAULT 'EA' REFERENCES shared.units_of_measure(uom_code),

    -- Terms
    min_order_qty       INTEGER,
    standard_lead_time_days INTEGER,
    payment_terms       VARCHAR(50),                            -- net30, net60, prepaid, etc.

    -- Validity
    valid_from          DATE            NOT NULL,
    valid_to            DATE,                                   -- NULL = indefinite

    -- Auto-populated from PO history
    last_po_date        DATE,
    last_po_price       NUMERIC(15,2),
    last_po_id          UUID            REFERENCES mm.purchase_orders(id),

    -- Status
    is_preferred        BOOLEAN         DEFAULT FALSE,          -- preferred vendor for this part
    status              VARCHAR(10)     DEFAULT 'active',       -- active | expired | blocked
    notes               TEXT,
    created_at          TIMESTAMPTZ     DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE mm.purchasing_info_records IS 'Purchasing info records — vendor-material price agreements and procurement terms (SAP ME11)';
COMMENT ON COLUMN mm.purchasing_info_records.price_unit IS 'Price per X units (e.g., 1 = per EA, 100 = per 100 EA)';
COMMENT ON COLUMN mm.purchasing_info_records.is_preferred IS 'TRUE = preferred source for this part (used for automatic source determination)';
COMMENT ON COLUMN mm.purchasing_info_records.valid_to IS 'NULL = indefinite validity';
COMMENT ON COLUMN mm.purchasing_info_records.status IS 'active | expired | blocked';

-- Indexes
CREATE INDEX idx_mm_pir_parts_id        ON mm.purchasing_info_records(parts_id);
CREATE INDEX idx_mm_pir_vendor_id       ON mm.purchasing_info_records(vendor_id);
CREATE INDEX idx_mm_pir_valid_from      ON mm.purchasing_info_records(valid_from);
CREATE INDEX idx_mm_pir_valid_to        ON mm.purchasing_info_records(valid_to);
CREATE INDEX idx_mm_pir_is_preferred    ON mm.purchasing_info_records(is_preferred) WHERE is_preferred = TRUE;
CREATE INDEX idx_mm_pir_status          ON mm.purchasing_info_records(status);
CREATE INDEX idx_mm_pir_last_po_date    ON mm.purchasing_info_records(last_po_date);

-- Unique: one active record per vendor+part+validity period
CREATE UNIQUE INDEX idx_mm_pir_unique_active
    ON mm.purchasing_info_records(parts_id, vendor_id, valid_from)
    WHERE status = 'active';

-- ---------------------------------------------------------------------------
-- 9. VIEW: mm.v_current_prices — Latest valid price per vendor-material
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW mm.v_current_prices AS
SELECT DISTINCT ON (pir.parts_id, pir.vendor_id)
    pir.parts_id,
    pm.parts_code,
    pm.parts_name,
    pir.vendor_id,
    v.vendor_name,
    pir.net_price,
    pir.currency_code,
    pir.price_unit,
    pir.min_order_qty,
    pir.standard_lead_time_days,
    pir.payment_terms,
    pir.is_preferred,
    pir.valid_from,
    pir.valid_to,
    pir.last_po_date,
    pir.last_po_price
FROM mm.purchasing_info_records pir
JOIN shared.parts_master pm ON pm.id = pir.parts_id
JOIN shared.vendors v ON v.id = pir.vendor_id
WHERE pir.status = 'active'
  AND pir.valid_from <= CURRENT_DATE
  AND (pir.valid_to IS NULL OR pir.valid_to >= CURRENT_DATE)
ORDER BY pir.parts_id, pir.vendor_id, pir.valid_from DESC;

COMMENT ON VIEW mm.v_current_prices IS 'Current valid prices per vendor-material pair — latest active info record (SAP ME13 display)';

-- ---------------------------------------------------------------------------
-- 10. VIEW: mm.v_parts_without_prices — Parts missing price information
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW mm.v_parts_without_prices AS
SELECT
    pm.id AS parts_id,
    pm.parts_code,
    pm.parts_name,
    pm.vendor_id,
    v.vendor_name,
    pm.parts_type,
    pm.status
FROM shared.parts_master pm
LEFT JOIN shared.vendors v ON v.id = pm.vendor_id
LEFT JOIN mm.purchasing_info_records pir
    ON pir.parts_id = pm.id
    AND pir.status = 'active'
    AND pir.valid_from <= CURRENT_DATE
    AND (pir.valid_to IS NULL OR pir.valid_to >= CURRENT_DATE)
WHERE pm.status = 'active'
  AND pm.is_stock_managed = TRUE
  AND pir.id IS NULL
ORDER BY pm.parts_code;

COMMENT ON VIEW mm.v_parts_without_prices IS 'Active stock-managed parts with no valid purchasing info record — data quality monitoring';


-- ═══════════════════════════════════════════════════════════════════════════
-- SEED DATA: Common defect codes for packaging/printing industry
-- ═══════════════════════════════════════════════════════════════════════════

INSERT INTO mm.defect_catalogs (defect_code, defect_name, defect_category, severity, description) VALUES
    -- Printing defects (Q1 top issue: 사각스티커 커스텀인쇄)
    ('PRT-001', '인쇄 색상 불일치', 'printing', 'major', '인쇄 색상이 승인 샘플과 불일치'),
    ('PRT-002', '인쇄 위치 틀어짐', 'printing', 'major', '인쇄 위치가 기준선 대비 ±2mm 이상 벗어남'),
    ('PRT-003', '인쇄 번짐/얼룩', 'printing', 'major', '잉크 번짐, 얼룩, 묻어남 발생'),
    ('PRT-004', '인쇄 누락', 'printing', 'critical', '필수 인쇄 요소(로고, 텍스트, 바코드 등) 누락'),
    ('PRT-005', '인쇄 해상도 불량', 'printing', 'minor', '인쇄 해상도가 기준 DPI 미달'),
    ('PRT-006', '코팅/라미네이팅 불량', 'printing', 'major', '코팅 벗겨짐, 기포 발생, 라미네이팅 분리'),

    -- Manufacturing defects
    ('MFG-001', '치수 불량', 'manufacturing', 'major', '제품 치수가 허용 공차 범위 초과'),
    ('MFG-002', '접합 불량', 'manufacturing', 'major', '접착, 재봉, 열봉합 등 접합부 분리 또는 불균일'),
    ('MFG-003', '성형 불량', 'manufacturing', 'major', '프레스/금형 성형 결함 (뒤틀림, 미성형)'),
    ('MFG-004', '마감 불량', 'manufacturing', 'minor', '가장자리 거칠기, 버(burr) 발생'),

    -- Material defects
    ('MAT-001', '원자재 이물질', 'material', 'critical', '원자재 내 이물질/오염 혼입'),
    ('MAT-002', '원자재 변색', 'material', 'major', '원자재 색상이 기준 색상 대비 변색'),
    ('MAT-003', '원자재 두께 불량', 'material', 'major', '원자재 두께가 허용 범위 초과 (±10%)'),

    -- Packaging defects
    ('PKG-001', '포장 파손', 'packaging', 'major', '외박스/내박스 파손, 찢어짐, 변형'),
    ('PKG-002', '포장 수량 상이', 'packaging', 'major', '박스 내 수량이 표기 수량과 불일치'),
    ('PKG-003', '라벨 오부착', 'labeling', 'major', '바코드/품목 라벨이 잘못 부착됨'),
    ('PKG-004', '라벨 인쇄 불량', 'labeling', 'minor', '바코드 스캔 불가, 라벨 글자 흐림'),

    -- Contamination
    ('CTM-001', '이물 오염', 'contamination', 'critical', '먼지, 머리카락, 벌레 등 이물질 오염'),
    ('CTM-002', '습기/수분 피해', 'contamination', 'major', '제품에 습기, 곰팡이, 수분 피해 발견'),

    -- Dimensional
    ('DIM-001', '중량 불량', 'dimensional', 'major', '제품 중량이 허용 범위 초과 (±5%)'),
    ('DIM-002', '외형 치수 불량', 'dimensional', 'major', '길이/폭/높이가 허용 공차 범위 초과');

COMMENT ON TABLE mm.defect_catalogs IS 'Defect code master catalog — structured defect classification for QC inspections (SAP QS41). Seeded with 21 standard codes for packaging/printing industry.';
