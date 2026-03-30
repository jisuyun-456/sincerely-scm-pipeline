-- ============================================================================
-- Migration 004: shared Schema — Material Master (3-Level, FK chain removed)
--
-- SAP S/4HANA mapping:
--   shared.goods_master  → Material Master FERT (Finished Goods)
--   shared.item_master   → Material Master HALB (Semi-Finished Goods)
--   shared.parts_master  → Material Master ROH/VERP (Raw Materials / Packaging)
--
-- CRITICAL DESIGN DECISION:
--   There is NO foreign key chain between goods → item → parts.
--   Each material level is an independent master record.
--   Composition relationships are expressed ONLY through BOM (Bill of Materials)
--   in the pp (Production Planning) schema, created in a later migration.
--
-- Dependencies:
--   002_shared_reference_data.sql  (shared.material_types, shared.material_groups,
--                                   shared.units_of_measure)
--   003_shared_master_data.sql     (shared.users, shared.vendors)
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. shared.goods_master (SAP Material Master — FERT level)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shared.goods_master (
    id                      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    goods_code              VARCHAR(50)     UNIQUE NOT NULL,
    goods_name              VARCHAR(200)    NOT NULL,
    material_type_id        UUID            REFERENCES shared.material_types(id),
    material_group_id       UUID            REFERENCES shared.material_groups(id),
    base_uom                VARCHAR(10)     DEFAULT 'EA' REFERENCES shared.units_of_measure(uom_code),
    goods_category          VARCHAR(50),                    -- goods, kit, sample
    product_type_l1         VARCHAR(50),
    product_status          VARCHAR(20)     DEFAULT 'active',
    moq                     INTEGER,
    packaging_qty_per_box   INTEGER,
    packing_standard_qty    INTEGER,
    release_date            DATE,
    planned_release_date    DATE,
    packaging_tip           TEXT,
    memo_cx                 TEXT,
    memo_scm                TEXT,
    lead_time_bulk_days     INTEGER,
    default_bom_id          UUID,                           -- FK to pp.bom_headers added via ALTER TABLE later
    created_at              TIMESTAMPTZ     DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE shared.goods_master IS 'Finished goods master — FERT level (SAP Material Master)';
COMMENT ON COLUMN shared.goods_master.goods_category IS 'goods | kit | sample';
COMMENT ON COLUMN shared.goods_master.default_bom_id IS 'Deferred FK → pp.bom_headers (added via ALTER TABLE in pp migration)';
COMMENT ON COLUMN shared.goods_master.lead_time_bulk_days IS 'Standard lead time in days for bulk production';

-- ---------------------------------------------------------------------------
-- 2. shared.item_master (SAP Material Master — HALB level)
--    CRITICAL: NO goods_id FK! BOM handles composition.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shared.item_master (
    id                          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    item_code                   VARCHAR(50)     UNIQUE NOT NULL,
    item_name                   VARCHAR(200)    NOT NULL,
    material_type_id            UUID            REFERENCES shared.material_types(id),
    material_group_id           UUID            REFERENCES shared.material_groups(id),
    base_uom                    VARCHAR(10)     DEFAULT 'EA' REFERENCES shared.units_of_measure(uom_code),
    item_detail                 TEXT,
    category                    VARCHAR(50),
    production_type             VARCHAR(20),                -- purchase, production, assembly
    requires_assembly           BOOLEAN         DEFAULT FALSE,
    dimensions                  VARCHAR(100),
    template_size               VARCHAR(100),
    stock_managed               BOOLEAN         DEFAULT TRUE,
    pre_packaging_instruction   TEXT,
    purchaser_id                UUID            REFERENCES shared.users(id),
    created_at                  TIMESTAMPTZ     DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE shared.item_master IS 'Semi-finished goods master — HALB level (SAP Material Master). NO FK to goods_master; BOM handles composition.';
COMMENT ON COLUMN shared.item_master.production_type IS 'purchase | production | assembly';
COMMENT ON COLUMN shared.item_master.purchaser_id IS 'Default purchaser responsible for procurement of this item';

-- ---------------------------------------------------------------------------
-- 3. shared.parts_master (SAP Material Master — ROH/VERP level)
--    CRITICAL: NO item_id FK! BOM handles composition.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shared.parts_master (
    id                      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    parts_code              VARCHAR(50)     UNIQUE NOT NULL,
    parts_name              VARCHAR(200)    NOT NULL,
    material_type_id        UUID            REFERENCES shared.material_types(id),
    material_group_id       UUID            REFERENCES shared.material_groups(id),
    base_uom                VARCHAR(10)     DEFAULT 'EA' REFERENCES shared.units_of_measure(uom_code),
    vendor_id               UUID            REFERENCES shared.vendors(id),
    parts_type              VARCHAR(50),                    -- raw, semi_finished, packaging, merchandise (legacy, plan to deprecate)
    stock_classification    VARCHAR(20),
    is_stock_managed        BOOLEAN         DEFAULT TRUE,
    is_batch_managed        BOOLEAN         DEFAULT FALSE,
    procurement_type        VARCHAR(1),                     -- E(in-house), F(external), X(both)
    reorder_point           INTEGER,
    min_order_qty           INTEGER,
    gross_weight_kg         NUMERIC(10,3),
    net_weight_kg           NUMERIC(10,3),
    volume_cbm              NUMERIC(10,6),
    dimensions              VARCHAR(100),
    material_spec           TEXT,
    base_processing         TEXT,
    printing_options        TEXT,
    print_area              VARCHAR(200),
    print_color             VARCHAR(100),
    vendor_product_name     VARCHAR(200),
    order_options           TEXT,
    template_size           VARCHAR(100),
    template_link           TEXT,
    packaging_tip           TEXT,
    is_customer_goods       BOOLEAN         DEFAULT FALSE,
    status                  VARCHAR(20)     DEFAULT 'active',
    created_at              TIMESTAMPTZ     DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE shared.parts_master IS 'Raw materials & packaging master — ROH/VERP level (SAP Material Master). NO FK to item_master; BOM handles composition.';
COMMENT ON COLUMN shared.parts_master.parts_type IS 'raw | semi_finished | packaging | merchandise (legacy, plan to deprecate)';
COMMENT ON COLUMN shared.parts_master.procurement_type IS 'E = in-house production, F = external procurement, X = both';
COMMENT ON COLUMN shared.parts_master.vendor_id IS 'Default vendor for this part';

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

-- goods_master indexes
CREATE INDEX IF NOT EXISTS idx_goods_material_type      ON shared.goods_master(material_type_id);
CREATE INDEX IF NOT EXISTS idx_goods_material_group     ON shared.goods_master(material_group_id);
CREATE INDEX IF NOT EXISTS idx_goods_category           ON shared.goods_master(goods_category);
CREATE INDEX IF NOT EXISTS idx_goods_product_status     ON shared.goods_master(product_status);
CREATE INDEX IF NOT EXISTS idx_goods_product_type_l1    ON shared.goods_master(product_type_l1);

-- item_master indexes
CREATE INDEX IF NOT EXISTS idx_item_material_type       ON shared.item_master(material_type_id);
CREATE INDEX IF NOT EXISTS idx_item_material_group      ON shared.item_master(material_group_id);
CREATE INDEX IF NOT EXISTS idx_item_production_type     ON shared.item_master(production_type);
CREATE INDEX IF NOT EXISTS idx_item_purchaser           ON shared.item_master(purchaser_id);
CREATE INDEX IF NOT EXISTS idx_item_category            ON shared.item_master(category);

-- parts_master indexes
CREATE INDEX IF NOT EXISTS idx_parts_material_type      ON shared.parts_master(material_type_id);
CREATE INDEX IF NOT EXISTS idx_parts_material_group     ON shared.parts_master(material_group_id);
CREATE INDEX IF NOT EXISTS idx_parts_vendor             ON shared.parts_master(vendor_id);
CREATE INDEX IF NOT EXISTS idx_parts_parts_type         ON shared.parts_master(parts_type);
CREATE INDEX IF NOT EXISTS idx_parts_procurement_type   ON shared.parts_master(procurement_type);
CREATE INDEX IF NOT EXISTS idx_parts_status             ON shared.parts_master(status);
CREATE INDEX IF NOT EXISTS idx_parts_is_stock_managed   ON shared.parts_master(is_stock_managed);
