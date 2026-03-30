-- ============================================================================
-- Migration 007: wms Schema — Extended Warehouse Management (SAP EWM)
--
-- SAP S/4HANA EWM mapping:
--   wms.warehouses            → /SCWM/T_WH   (Warehouse Number)
--   wms.storage_types         → /SCWM/T_ST    (Storage Type)
--   wms.storage_bins          → /SCWM/LAGP    (Storage Bin)
--   wms.batches               → MCHA           (Batch Master)
--   wms.quants                → /SCWM/AQUA    (Quant — Inventory Unit)
--   wms.inventory_count_docs  → IKPF           (Physical Inventory Document Header)
--   wms.inventory_count_items → ISEG           (Physical Inventory Document Item)
--
-- Dependencies:
--   001_create_schemas.sql          (wms schema)
--   002_shared_reference_data.sql   (shared.units_of_measure)
--   003_shared_master_data.sql      (shared.organizations, shared.users)
--   004_shared_material_master.sql  (shared.parts_master)
--
-- Cross-schema deferred FKs:
--   wms.batches.gr_id → mm.goods_receipts(id) — added in 010_cross_fks.sql
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. wms.warehouses (SAP Warehouse Number — /SCWM/T_WH)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wms.warehouses (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    warehouse_code  VARCHAR(10)     UNIQUE NOT NULL,
    warehouse_name  VARCHAR(200)    NOT NULL,
    plant_id        UUID            REFERENCES shared.organizations(id),
    address         TEXT,
    max_cbm         NUMERIC(10,3),
    manager_id      UUID            REFERENCES shared.users(id),
    status          VARCHAR(10)     DEFAULT 'active',
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE wms.warehouses IS 'Warehouse master — one per physical warehouse (SAP Warehouse Number)';
COMMENT ON COLUMN wms.warehouses.plant_id IS 'FK to shared.organizations — the plant this warehouse belongs to';
COMMENT ON COLUMN wms.warehouses.max_cbm IS 'Maximum storage capacity in cubic meters';

-- ---------------------------------------------------------------------------
-- 2. wms.storage_types (SAP Storage Type — /SCWM/T_ST)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wms.storage_types (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    warehouse_id    UUID            REFERENCES wms.warehouses(id),
    type_code       VARCHAR(10)     NOT NULL,
    type_name       VARCHAR(100),
    UNIQUE(warehouse_id, type_code)
);

COMMENT ON TABLE wms.storage_types IS 'Storage type within a warehouse — e.g., high-rack, floor, cold (SAP Storage Type)';
COMMENT ON COLUMN wms.storage_types.type_code IS 'Type code unique per warehouse — e.g., HR (high-rack), FL (floor)';

-- ---------------------------------------------------------------------------
-- 3. wms.storage_bins (SAP Storage Bin — /SCWM/LAGP)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wms.storage_bins (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    bin_code        VARCHAR(20)     UNIQUE NOT NULL,   -- 좌표 예: A-01-01
    warehouse_id    UUID            REFERENCES wms.warehouses(id),
    storage_type_id UUID            REFERENCES wms.storage_types(id),
    zone            VARCHAR(20),                       -- 출고Zone
    aisle           VARCHAR(10),
    rack            VARCHAR(10),
    level           VARCHAR(10),
    bin_type        VARCHAR(20)     DEFAULT 'standard',
    max_weight_kg   NUMERIC(8,2),
    max_cbm         NUMERIC(8,3),
    status          VARCHAR(20)     DEFAULT 'active',
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE wms.storage_bins IS 'Physical storage locations within a warehouse (SAP Storage Bin)';
COMMENT ON COLUMN wms.storage_bins.bin_code IS 'Coordinate-based bin code — e.g., A-01-01 (aisle-rack-level)';
COMMENT ON COLUMN wms.storage_bins.zone IS 'Logical zone for outbound picking — 출고Zone';
COMMENT ON COLUMN wms.storage_bins.bin_type IS 'standard | bulk | picking | receiving | shipping';

-- ---------------------------------------------------------------------------
-- 4. wms.batches (SAP Batch Master — MCHA)
--    NOTE: gr_id references mm.goods_receipts which is created in a later
--    migration. The FK constraint is added in 010_cross_fks.sql.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wms.batches (
    id                UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    parts_id          UUID            NOT NULL REFERENCES shared.parts_master(id),
    batch_number      VARCHAR(50)     NOT NULL,
    gr_id             UUID,           -- FK to mm.goods_receipts added in 010_cross_fks.sql
    remaining_qty     INTEGER,
    unit_cost         NUMERIC(15,4),  -- FIFO cost at batch level
    production_date   DATE,
    expiry_date       DATE,
    vendor_batch_ref  VARCHAR(100),
    status            VARCHAR(20)     DEFAULT 'active',
    created_at        TIMESTAMPTZ     DEFAULT NOW(),
    UNIQUE(parts_id, batch_number)
);

COMMENT ON TABLE wms.batches IS 'Batch/lot tracking per material — FIFO cost and traceability (SAP MCHA)';
COMMENT ON COLUMN wms.batches.gr_id IS 'Goods receipt that created this batch — FK deferred to 010_cross_fks.sql';
COMMENT ON COLUMN wms.batches.unit_cost IS 'FIFO unit cost captured at goods receipt time';
COMMENT ON COLUMN wms.batches.vendor_batch_ref IS 'Vendor/manufacturer original batch reference number';

-- ---------------------------------------------------------------------------
-- 5. wms.quants (SAP Quant — /SCWM/AQUA)
--    CRITICAL changes from previous version:
--      ADD: reserved_qty, blocked_qty, available_qty (GENERATED)
--      ADD: unit_of_measure, last_movement_date
--      REMOVE: opening_qty (moved to finance.period_closes)
--      REMOVE: check_status (merged with verification_status)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wms.quants (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    parts_id            UUID            NOT NULL REFERENCES shared.parts_master(id),
    storage_bin_id      UUID            NOT NULL REFERENCES wms.storage_bins(id),
    batch_id            UUID            REFERENCES wms.batches(id),
    stock_type          VARCHAR(20)     DEFAULT 'unrestricted',   -- unrestricted, quality_inspection, blocked, returns
    physical_qty        INTEGER         DEFAULT 0,
    system_qty          INTEGER         DEFAULT 0,
    reserved_qty        INTEGER         DEFAULT 0,
    blocked_qty         INTEGER         DEFAULT 0,
    available_qty       INTEGER         GENERATED ALWAYS AS (
                            system_qty - COALESCE(reserved_qty, 0) - COALESCE(blocked_qty, 0)
                        ) STORED,
    unit_of_measure     VARCHAR(10)     DEFAULT 'EA' REFERENCES shared.units_of_measure(uom_code),
    last_movement_date  DATE,
    last_verified_at    TIMESTAMPTZ,
    verification_status VARCHAR(20)     DEFAULT 'pending',
    created_at          TIMESTAMPTZ     DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE wms.quants IS 'Inventory units — each record = one material + bin + batch + stock type combination (SAP Quant)';
COMMENT ON COLUMN wms.quants.stock_type IS 'unrestricted | quality_inspection | blocked | returns';
COMMENT ON COLUMN wms.quants.physical_qty IS 'Last physically counted quantity';
COMMENT ON COLUMN wms.quants.system_qty IS 'Current system-tracked quantity (adjusted by movements)';
COMMENT ON COLUMN wms.quants.reserved_qty IS 'Quantity reserved by outbound delivery orders';
COMMENT ON COLUMN wms.quants.blocked_qty IS 'Quantity blocked for quality holds or other reasons';
COMMENT ON COLUMN wms.quants.available_qty IS 'GENERATED: system_qty - reserved_qty - blocked_qty';
COMMENT ON COLUMN wms.quants.verification_status IS 'pending | verified | discrepancy';

-- Partial unique indexes to enforce one quant per (part, bin, stock_type) combo,
-- handling the NULL batch_id case correctly.
CREATE UNIQUE INDEX quants_no_batch_unique
    ON wms.quants(parts_id, storage_bin_id, stock_type)
    WHERE batch_id IS NULL;

CREATE UNIQUE INDEX quants_with_batch_unique
    ON wms.quants(parts_id, storage_bin_id, batch_id, stock_type)
    WHERE batch_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 6. wms.inventory_count_docs (SAP Physical Inventory Document — IKPF)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wms.inventory_count_docs (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_number      VARCHAR(50)     UNIQUE NOT NULL,
    count_name      VARCHAR(200),
    count_type      VARCHAR(20),                       -- annual, cycle, spot
    warehouse_id    UUID            REFERENCES wms.warehouses(id),
    planned_date    DATE,
    completed_date  DATE,
    status          VARCHAR(20)     DEFAULT 'created',
    scope           TEXT,
    created_by      UUID            REFERENCES shared.users(id),
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE wms.inventory_count_docs IS 'Physical inventory count document header (SAP IKPF)';
COMMENT ON COLUMN wms.inventory_count_docs.count_type IS 'annual | cycle | spot';
COMMENT ON COLUMN wms.inventory_count_docs.status IS 'created | in_progress | completed | cancelled';
COMMENT ON COLUMN wms.inventory_count_docs.scope IS 'Free-text description of count scope — zones, bins, material groups, etc.';

-- ---------------------------------------------------------------------------
-- 7. wms.inventory_count_items (SAP Physical Inventory Item — ISEG)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS wms.inventory_count_items (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id              UUID            NOT NULL REFERENCES wms.inventory_count_docs(id),
    parts_id            UUID            NOT NULL REFERENCES shared.parts_master(id),
    storage_bin_id      UUID            REFERENCES wms.storage_bins(id),
    book_qty            INTEGER,
    count_qty_1st       INTEGER,
    count_qty_2nd       INTEGER,
    final_count_qty     INTEGER,
    difference          INTEGER,
    difference_type     VARCHAR(50),
    sap_movement_type   VARCHAR(10),                   -- 701/702
    adjustment_approved BOOLEAN         DEFAULT FALSE,
    approved_by         UUID            REFERENCES shared.users(id),
    counted_by          UUID            REFERENCES shared.users(id),
    counted_at          TIMESTAMPTZ,
    processed_at        TIMESTAMPTZ
);

COMMENT ON TABLE wms.inventory_count_items IS 'Physical inventory count line items (SAP ISEG)';
COMMENT ON COLUMN wms.inventory_count_items.book_qty IS 'System book quantity at time of count';
COMMENT ON COLUMN wms.inventory_count_items.count_qty_1st IS 'First physical count result';
COMMENT ON COLUMN wms.inventory_count_items.count_qty_2nd IS 'Recount result (if first count has discrepancy)';
COMMENT ON COLUMN wms.inventory_count_items.final_count_qty IS 'Accepted final count quantity';
COMMENT ON COLUMN wms.inventory_count_items.difference IS 'final_count_qty - book_qty';
COMMENT ON COLUMN wms.inventory_count_items.sap_movement_type IS '701 (surplus) / 702 (shortage) for inventory adjustments';

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

-- warehouses
CREATE INDEX IF NOT EXISTS idx_warehouses_plant_id
    ON wms.warehouses(plant_id);
CREATE INDEX IF NOT EXISTS idx_warehouses_status
    ON wms.warehouses(status);

-- storage_bins
CREATE INDEX IF NOT EXISTS idx_storage_bins_warehouse_id
    ON wms.storage_bins(warehouse_id);
CREATE INDEX IF NOT EXISTS idx_storage_bins_storage_type_id
    ON wms.storage_bins(storage_type_id);
CREATE INDEX IF NOT EXISTS idx_storage_bins_zone
    ON wms.storage_bins(zone);
CREATE INDEX IF NOT EXISTS idx_storage_bins_status
    ON wms.storage_bins(status);

-- batches
CREATE INDEX IF NOT EXISTS idx_batches_parts_id
    ON wms.batches(parts_id);
CREATE INDEX IF NOT EXISTS idx_batches_gr_id
    ON wms.batches(gr_id);
CREATE INDEX IF NOT EXISTS idx_batches_status
    ON wms.batches(status);
CREATE INDEX IF NOT EXISTS idx_batches_expiry_date
    ON wms.batches(expiry_date);

-- quants
CREATE INDEX IF NOT EXISTS idx_quants_parts_id
    ON wms.quants(parts_id);
CREATE INDEX IF NOT EXISTS idx_quants_storage_bin_id
    ON wms.quants(storage_bin_id);
CREATE INDEX IF NOT EXISTS idx_quants_batch_id
    ON wms.quants(batch_id);
CREATE INDEX IF NOT EXISTS idx_quants_stock_type
    ON wms.quants(stock_type);
CREATE INDEX IF NOT EXISTS idx_quants_verification_status
    ON wms.quants(verification_status);

-- inventory_count_docs
CREATE INDEX IF NOT EXISTS idx_inventory_count_docs_warehouse_id
    ON wms.inventory_count_docs(warehouse_id);
CREATE INDEX IF NOT EXISTS idx_inventory_count_docs_status
    ON wms.inventory_count_docs(status);
CREATE INDEX IF NOT EXISTS idx_inventory_count_docs_planned_date
    ON wms.inventory_count_docs(planned_date);

-- inventory_count_items
CREATE INDEX IF NOT EXISTS idx_inventory_count_items_doc_id
    ON wms.inventory_count_items(doc_id);
CREATE INDEX IF NOT EXISTS idx_inventory_count_items_parts_id
    ON wms.inventory_count_items(parts_id);
CREATE INDEX IF NOT EXISTS idx_inventory_count_items_storage_bin_id
    ON wms.inventory_count_items(storage_bin_id);
