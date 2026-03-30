-- ============================================================
-- Migration 009: pp Schema — Production Planning (SAP PP) — 임가공
-- ============================================================
-- SAP S/4HANA PP module equivalent tables for production
-- planning, BOM management, work centers, routings,
-- production orders, and confirmations.
-- ============================================================

-- Schema
CREATE SCHEMA IF NOT EXISTS pp;

-- ============================================================
-- 1. pp.bom_headers (SAP BOM MAST)
-- ============================================================
CREATE TABLE pp.bom_headers (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    bom_code        VARCHAR(50) UNIQUE NOT NULL,
    goods_id        UUID        REFERENCES shared.goods_master(id),
    item_id         UUID        REFERENCES shared.item_master(id),
    bom_type        VARCHAR(20),                -- kit, assembly, packaging
    valid_from      DATE,
    valid_to        DATE,
    notes           TEXT,
    created_by      UUID        REFERENCES shared.users(id),
    created_at      TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT bom_exactly_one_level
        CHECK (
            (goods_id IS NOT NULL)::int + (item_id IS NOT NULL)::int = 1
        )
);

COMMENT ON TABLE  pp.bom_headers IS 'Bill of Materials header — SAP MAST equivalent';
COMMENT ON COLUMN pp.bom_headers.bom_type IS 'kit | assembly | packaging';

-- ============================================================
-- 2. pp.bom_items (SAP BOM STPO)
-- ============================================================
CREATE TABLE pp.bom_items (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    bom_id          UUID            NOT NULL REFERENCES pp.bom_headers(id),
    parts_id        UUID            NOT NULL REFERENCES shared.parts_master(id),
    component_qty   NUMERIC(10,3)   NOT NULL,
    unit_of_measure VARCHAR(10)     DEFAULT 'EA'
                                    REFERENCES shared.units_of_measure(uom_code),
    item_category   VARCHAR(20),                -- stock, non_stock
    scrap_pct       NUMERIC(5,2)    DEFAULT 0,
    sort_order      INTEGER,
    notes           TEXT
);

COMMENT ON TABLE  pp.bom_items IS 'Bill of Materials line items — SAP STPO equivalent';
COMMENT ON COLUMN pp.bom_items.item_category IS 'stock | non_stock';

-- ============================================================
-- 3. pp.work_centers (SAP CRHD) ★NEW
-- ============================================================
CREATE TABLE pp.work_centers (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    wc_code         VARCHAR(20)     UNIQUE NOT NULL,
    wc_name         VARCHAR(200)    NOT NULL,
    wc_type         VARCHAR(20),                -- internal | external_vendor
    vendor_id       UUID            REFERENCES shared.vendors(id),
    capacity_daily  INTEGER,
    cost_rate_hourly NUMERIC(10,2),
    location        TEXT,
    contact_name    VARCHAR(100),
    contact_phone   VARCHAR(20),
    status          VARCHAR(10)     DEFAULT 'active',
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE  pp.work_centers IS 'Work centers — SAP CRHD equivalent. Links 임가공 vendors.';
COMMENT ON COLUMN pp.work_centers.wc_type IS 'internal | external_vendor';

-- ============================================================
-- 4. pp.routings (SAP PLKO/PLPO) ★NEW
-- ============================================================
CREATE TABLE pp.routings (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    routing_code        VARCHAR(50)     UNIQUE NOT NULL,
    bom_id              UUID            REFERENCES pp.bom_headers(id),
    goods_id            UUID            REFERENCES shared.goods_master(id),
    operation_number    INTEGER         NOT NULL,
    operation_name      VARCHAR(100),
    work_center_id      UUID            REFERENCES pp.work_centers(id),
    operation_type      VARCHAR(50),    -- assembly | packing | qc_check | printing | cutting
    standard_time_min   NUMERIC(8,2),
    setup_time_min      NUMERIC(8,2),
    sort_order          INTEGER,
    notes               TEXT,

    UNIQUE (routing_code, operation_number)
);

COMMENT ON TABLE  pp.routings IS 'Routing operations — SAP PLKO/PLPO equivalent';
COMMENT ON COLUMN pp.routings.operation_type IS 'assembly | packing | qc_check | printing | cutting';

-- ============================================================
-- 5. pp.production_orders (SAP Production Order)
-- ============================================================
CREATE TABLE pp.production_orders (
    id                      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    order_number            VARCHAR(50)     UNIQUE NOT NULL,
    project_id              UUID            REFERENCES shared.projects(id),
    goods_id                UUID            REFERENCES shared.goods_master(id),
    bom_id                  UUID            REFERENCES pp.bom_headers(id),
    work_center_id          UUID            REFERENCES pp.work_centers(id),
    vendor_id               UUID            REFERENCES shared.vendors(id),
    status                  VARCHAR(20)     DEFAULT 'planned',
    planned_start_date      DATE,
    planned_end_date        DATE,
    actual_start_date       DATE,
    actual_end_date         DATE,
    planned_qty             INTEGER,
    actual_qty              INTEGER         DEFAULT 0,
    output_qty              INTEGER         DEFAULT 0,
    scrap_qty               INTEGER         DEFAULT 0,
    zone                    VARCHAR(20),                -- 출고Zone
    man_hours_planned       NUMERIC(8,2),
    man_hours_calc          NUMERIC(8,2),
    man_hours_actual        NUMERIC(8,2),
    unit_cost_actual        NUMERIC(15,4),
    picking_status          VARCHAR(20)     DEFAULT 'pending',
    material_input_status   VARCHAR(20)     DEFAULT 'pending',
    assembly_instructions   TEXT,
    design_file_url         TEXT,
    special_notes           TEXT,
    is_bespoke              BOOLEAN         DEFAULT FALSE,
    cx_responsible_id       UUID            REFERENCES shared.users(id),
    created_at              TIMESTAMPTZ     DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE  pp.production_orders IS 'Production orders — SAP Production Order equivalent';
COMMENT ON COLUMN pp.production_orders.status IS 'planned | released | in_progress | completed | cancelled';
COMMENT ON COLUMN pp.production_orders.vendor_id IS '임가공 vendor';
COMMENT ON COLUMN pp.production_orders.zone IS '출고Zone';

-- ============================================================
-- 6. pp.production_order_components (SAP RESB)
-- ============================================================
CREATE TABLE pp.production_order_components (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    production_order_id     UUID        NOT NULL REFERENCES pp.production_orders(id),
    parts_id                UUID        NOT NULL REFERENCES shared.parts_master(id),
    required_qty            INTEGER     NOT NULL,
    issued_qty              INTEGER     DEFAULT 0,
    returned_qty            INTEGER     DEFAULT 0,
    storage_bin_id          UUID        REFERENCES wms.storage_bins(id),
    status                  VARCHAR(20) DEFAULT 'pending',
    sort_order              INTEGER,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE pp.production_order_components IS 'Production order material components — SAP RESB equivalent';

-- ============================================================
-- 7. pp.production_confirmations (SAP AFRU)
-- ============================================================
CREATE TABLE pp.production_confirmations (
    id                      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    production_order_id     UUID            NOT NULL REFERENCES pp.production_orders(id),
    confirmation_date       TIMESTAMPTZ     NOT NULL,
    operation_type          VARCHAR(50),    -- assembly, packing, qc_check
    completed_qty           INTEGER,
    man_hours_actual        NUMERIC(8,2),
    worker_id               UUID            REFERENCES shared.users(id),
    notes                   TEXT,
    photos_url              TEXT,
    created_at              TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE  pp.production_confirmations IS 'Production confirmations — SAP AFRU equivalent';
COMMENT ON COLUMN pp.production_confirmations.operation_type IS 'assembly | packing | qc_check';

-- ============================================================
-- INDEXES — FK columns & status columns
-- ============================================================

-- bom_headers
CREATE INDEX idx_bom_headers_goods_id    ON pp.bom_headers(goods_id);
CREATE INDEX idx_bom_headers_item_id     ON pp.bom_headers(item_id);
CREATE INDEX idx_bom_headers_created_by  ON pp.bom_headers(created_by);

-- bom_items
CREATE INDEX idx_bom_items_bom_id        ON pp.bom_items(bom_id);
CREATE INDEX idx_bom_items_parts_id      ON pp.bom_items(parts_id);

-- work_centers
CREATE INDEX idx_work_centers_vendor_id  ON pp.work_centers(vendor_id);
CREATE INDEX idx_work_centers_status     ON pp.work_centers(status);

-- routings
CREATE INDEX idx_routings_bom_id         ON pp.routings(bom_id);
CREATE INDEX idx_routings_goods_id       ON pp.routings(goods_id);
CREATE INDEX idx_routings_work_center_id ON pp.routings(work_center_id);

-- production_orders
CREATE INDEX idx_po_project_id           ON pp.production_orders(project_id);
CREATE INDEX idx_po_goods_id             ON pp.production_orders(goods_id);
CREATE INDEX idx_po_bom_id              ON pp.production_orders(bom_id);
CREATE INDEX idx_po_work_center_id       ON pp.production_orders(work_center_id);
CREATE INDEX idx_po_vendor_id            ON pp.production_orders(vendor_id);
CREATE INDEX idx_po_status               ON pp.production_orders(status);
CREATE INDEX idx_po_picking_status       ON pp.production_orders(picking_status);
CREATE INDEX idx_po_material_input_status ON pp.production_orders(material_input_status);
CREATE INDEX idx_po_cx_responsible_id    ON pp.production_orders(cx_responsible_id);

-- production_order_components
CREATE INDEX idx_poc_production_order_id ON pp.production_order_components(production_order_id);
CREATE INDEX idx_poc_parts_id            ON pp.production_order_components(parts_id);
CREATE INDEX idx_poc_storage_bin_id      ON pp.production_order_components(storage_bin_id);
CREATE INDEX idx_poc_status              ON pp.production_order_components(status);

-- production_confirmations
CREATE INDEX idx_pc_production_order_id  ON pp.production_confirmations(production_order_id);
CREATE INDEX idx_pc_worker_id            ON pp.production_confirmations(worker_id);
CREATE INDEX idx_pc_confirmation_date    ON pp.production_confirmations(confirmation_date);
