-- ============================================================================
-- Migration 008: mm Schema — Materials Management + Quality Management (SAP MM/QM)
--
-- SAP S/4HANA mapping:
--   mm.purchase_requisitions   → EBAN  (Purchase Requisition)
--   mm.purchase_orders         → EKKO  (PO Header)
--   mm.purchase_order_items    → EKPO  (PO Line Item)
--   mm.goods_receipts          → MKPF  (Material Document Header / GR)
--   mm.stock_movements         → MSEG  (Material Document Item)
--   mm.invoice_verifications   → MIRO  (Invoice Verification)
--   mm.reservations            → RESB  (Reservation)
--   mm.return_orders           → Return Order (custom)
--   mm.quality_inspections     → QALS  (Inspection Lot)
--   mm.scrap_records           → Scrap / Disposal (custom)
--
-- Dependencies:
--   001_create_schemas.sql          (mm schema)
--   002_shared_reference_data.sql   (shared.gl_accounts, shared.units_of_measure)
--   003_shared_master_data.sql      (shared.organizations, shared.users, shared.vendors, shared.projects)
--   004_shared_material_master.sql  (shared.parts_master)
--   006_tms_schema.sql              (tms.logistics_releases, tms.transportation_requirements)
--   007_wms_schema.sql              (wms.storage_bins, wms.batches)
--
-- CRITICAL structural fixes applied:
--   1. PO Header/Line split (SAP EKKO/EKPO) — purchase_orders + purchase_order_items
--   2. Circular FK removed — goods_receipts has NO stock_movement_id column
--   3. Typed FKs for stock_movements — gr_id, po_item_id, logistics_release_id, tr_id
--      instead of polymorphic source_doc_id
--   4. Deferred FKs — production_order_id columns have no FK constraint here;
--      constraints added in 010_cross_fks.sql after pp schema is created
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. mm.purchase_requisitions (SAP EBAN — Purchase Requisition)
-- ---------------------------------------------------------------------------
CREATE TABLE mm.purchase_requisitions (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    pr_number           VARCHAR(50)     UNIQUE NOT NULL,
    parts_id            UUID            NOT NULL REFERENCES shared.parts_master(id),
    required_qty        INTEGER         NOT NULL,
    required_date       DATE            NOT NULL,
    project_id          UUID            REFERENCES shared.projects(id),
    source              VARCHAR(10),                        -- manual | mrp | reorder
    status              VARCHAR(20)     DEFAULT 'open',     -- open | approved | converted | closed
    converted_po_item_id UUID,          -- FK added after purchase_order_items is created
    requested_by        UUID            REFERENCES shared.users(id),
    approved_by         UUID            REFERENCES shared.users(id),
    approved_at         TIMESTAMPTZ,
    unit_of_measure     VARCHAR(10)     DEFAULT 'EA' REFERENCES shared.units_of_measure(uom_code),
    created_at          TIMESTAMPTZ     DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE mm.purchase_requisitions IS 'Purchase requisitions — internal demand before PO creation (SAP EBAN)';
COMMENT ON COLUMN mm.purchase_requisitions.source IS 'manual | mrp | reorder — how the requisition was generated';
COMMENT ON COLUMN mm.purchase_requisitions.status IS 'open | approved | converted | closed';
COMMENT ON COLUMN mm.purchase_requisitions.converted_po_item_id IS 'FK to mm.purchase_order_items — set when PR is converted to a PO line';

-- ---------------------------------------------------------------------------
-- 2. mm.purchase_orders (SAP EKKO — PO Header only)
-- ---------------------------------------------------------------------------
CREATE TABLE mm.purchase_orders (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    po_number           VARCHAR(50)     UNIQUE NOT NULL,
    project_id          UUID            REFERENCES shared.projects(id),
    vendor_id           UUID            REFERENCES shared.vendors(id),
    purchasing_org_id   UUID            REFERENCES shared.organizations(id),
    po_status           VARCHAR(30)     DEFAULT 'draft',    -- draft | sent | confirmed | partial_received | received | closed | cancelled
    order_stage         VARCHAR(30),
    requested_date      DATE,
    ordered_by          UUID            REFERENCES shared.users(id),
    cx_manager_id       UUID            REFERENCES shared.users(id),
    is_archived         BOOLEAN         DEFAULT FALSE,
    created_at          TIMESTAMPTZ     DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE mm.purchase_orders IS 'Purchase order headers — one per vendor order (SAP EKKO)';
COMMENT ON COLUMN mm.purchase_orders.po_status IS 'draft | sent | confirmed | partial_received | received | closed | cancelled';
COMMENT ON COLUMN mm.purchase_orders.order_stage IS 'Custom workflow stage for internal tracking';
COMMENT ON COLUMN mm.purchase_orders.cx_manager_id IS 'CX manager responsible for this order';

-- ---------------------------------------------------------------------------
-- 3. mm.purchase_order_items (SAP EKPO — PO Line Items)
-- ---------------------------------------------------------------------------
CREATE TABLE mm.purchase_order_items (
    id                          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    po_id                       UUID            NOT NULL REFERENCES mm.purchase_orders(id),
    line_number                 INTEGER         NOT NULL,
    parts_id                    UUID            NOT NULL REFERENCES shared.parts_master(id),
    order_qty                   INTEGER         NOT NULL,
    received_qty                INTEGER         DEFAULT 0,
    unit_price                  NUMERIC(15,2),
    total_amount                NUMERIC(15,2)   GENERATED ALWAYS AS (order_qty * COALESCE(unit_price, 0)) STORED,
    unit_of_measure             VARCHAR(10)     DEFAULT 'EA' REFERENCES shared.units_of_measure(uom_code),
    planned_delivery_date       DATE,
    confirmed_delivery_date     DATE,
    actual_delivery_date        DATE,
    quality_check_result        VARCHAR(20),                -- pass | fail | pending | sample_pass
    sample_check_result         VARCHAR(20),
    visual_check_result         VARCHAR(20),
    is_urgent                   BOOLEAN         DEFAULT FALSE,
    is_rework                   BOOLEAN         DEFAULT FALSE,
    is_bespoke                  BOOLEAN         DEFAULT FALSE,
    production_type             VARCHAR(20),                -- purchase | production | assembly
    over_delivery_tolerance_pct  NUMERIC(5,2)   DEFAULT 0,
    under_delivery_tolerance_pct NUMERIC(5,2)   DEFAULT 0,
    design_file_url             TEXT,
    spec_notes                  TEXT,
    box_count                   INTEGER,
    tax_code                    VARCHAR(10),
    UNIQUE(po_id, line_number)
);

COMMENT ON TABLE mm.purchase_order_items IS 'Purchase order line items — one per material per PO (SAP EKPO)';
COMMENT ON COLUMN mm.purchase_order_items.total_amount IS 'GENERATED: order_qty * unit_price';
COMMENT ON COLUMN mm.purchase_order_items.quality_check_result IS 'pass | fail | pending | sample_pass';
COMMENT ON COLUMN mm.purchase_order_items.production_type IS 'purchase | production | assembly';
COMMENT ON COLUMN mm.purchase_order_items.over_delivery_tolerance_pct IS 'Allowed over-delivery percentage (SAP tolerance)';
COMMENT ON COLUMN mm.purchase_order_items.under_delivery_tolerance_pct IS 'Allowed under-delivery percentage (SAP tolerance)';

-- Now that purchase_order_items exists, add the deferred FK from purchase_requisitions
ALTER TABLE mm.purchase_requisitions
    ADD CONSTRAINT fk_pr_poi
    FOREIGN KEY (converted_po_item_id) REFERENCES mm.purchase_order_items(id);

-- ---------------------------------------------------------------------------
-- 4. mm.goods_receipts (SAP MKPF — Material Document Header / Goods Receipt)
--    CRITICAL: NO stock_movement_id column — circular FK removed!
--    stock_movements references goods_receipts (one-way), not vice-versa.
-- ---------------------------------------------------------------------------
CREATE TABLE mm.goods_receipts (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    gr_number           VARCHAR(50)     UNIQUE NOT NULL,
    po_id               UUID            REFERENCES mm.purchase_orders(id),
    po_item_id          UUID            REFERENCES mm.purchase_order_items(id),
    parts_id            UUID            REFERENCES shared.parts_master(id),
    storage_bin_id      UUID            REFERENCES wms.storage_bins(id),
    batch_id            UUID            REFERENCES wms.batches(id),
    movement_type       VARCHAR(10)     DEFAULT '101',      -- SAP: 101=GR, 102=GR reversal
    received_qty        INTEGER         NOT NULL,
    accepted_qty        INTEGER,
    rejected_qty        INTEGER         DEFAULT 0,
    unit_of_measure     VARCHAR(10)     DEFAULT 'EA' REFERENCES shared.units_of_measure(uom_code),
    unit_cost           NUMERIC(15,4),
    total_cost          NUMERIC(15,2),
    tax_invoice_no      VARCHAR(30),
    vat_amount          NUMERIC(15,2),
    planned_receipt_date DATE,
    actual_receipt_date DATE            NOT NULL,
    posting_date        DATE,
    inspection_result   VARCHAR(20),                        -- pass | fail | conditional
    inspection_notes    TEXT,
    inspection_photos_url TEXT,
    received_by         UUID            REFERENCES shared.users(id),
    inspected_by        UUID            REFERENCES shared.users(id),
    created_at          TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE mm.goods_receipts IS 'Goods receipt documents — records material arrival and inspection (SAP MKPF)';
COMMENT ON COLUMN mm.goods_receipts.movement_type IS 'SAP movement type: 101=GR, 102=GR reversal';
COMMENT ON COLUMN mm.goods_receipts.inspection_result IS 'pass | fail | conditional';
COMMENT ON COLUMN mm.goods_receipts.accepted_qty IS 'Quantity accepted after inspection (may differ from received_qty)';
COMMENT ON COLUMN mm.goods_receipts.rejected_qty IS 'Quantity rejected during inspection';

-- ---------------------------------------------------------------------------
-- 5. mm.stock_movements (SAP Material Document — MSEG)
--    CRITICAL changes:
--      - Typed FKs: gr_id, po_item_id, logistics_release_id, tr_id
--        (CRITICAL-4: polymorphic source_doc_id removed)
--      - Removed: assembly_location, status columns (inbound/outbound/return),
--        return_qty
--      - Added: material_document_number, posting_date, batch_id,
--        reversal support, fiscal fields
-- ---------------------------------------------------------------------------
CREATE TABLE mm.stock_movements (
    id                          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    movement_number             VARCHAR(50)     UNIQUE NOT NULL,
    material_document_number    VARCHAR(50),                -- groups related movements
    movement_type               VARCHAR(30)     NOT NULL,   -- SAP codes: 101,102,122,161,201,261,262,301,309,501,551,561,601,701,702
    sap_movement_code           VARCHAR(10),                -- same value as movement_type for SAP alignment
    parts_id                    UUID            NOT NULL REFERENCES shared.parts_master(id),
    from_bin_id                 UUID            REFERENCES wms.storage_bins(id),
    to_bin_id                   UUID            REFERENCES wms.storage_bins(id),
    batch_id                    UUID            REFERENCES wms.batches(id),
    planned_qty                 INTEGER,
    actual_qty                  INTEGER,
    unit_of_measure             VARCHAR(10)     DEFAULT 'EA' REFERENCES shared.units_of_measure(uom_code),
    movement_purpose            VARCHAR(50),
    planned_date                DATE,
    actual_date                 DATE,
    posting_date                DATE,
    fiscal_year                 VARCHAR(4),
    fiscal_period               VARCHAR(2),
    status                      VARCHAR(20)     DEFAULT 'planned',  -- planned | in_progress | completed | cancelled
    unit_cost_at_movement       NUMERIC(15,4),
    total_cost                  NUMERIC(15,2),
    gl_account_id               UUID            REFERENCES shared.gl_accounts(id),
    is_reversal                 BOOLEAN         DEFAULT FALSE,
    reversal_movement_id        UUID            REFERENCES mm.stock_movements(id),
    -- Typed FKs (CRITICAL-4: polymorphic source_doc_id removed)
    gr_id                       UUID            REFERENCES mm.goods_receipts(id),
    po_item_id                  UUID            REFERENCES mm.purchase_order_items(id),
    production_order_id         UUID,           -- FK to pp.production_orders added in 010_cross_fks.sql
    logistics_release_id        UUID            REFERENCES tms.logistics_releases(id),
    tr_id                       UUID            REFERENCES tms.transportation_requirements(id),
    reference_doc_type          VARCHAR(30),                -- human-readable context: gr | po | production_order | logistics_release | tr | adjustment
    created_by                  UUID            REFERENCES shared.users(id),
    last_modified_by            UUID            REFERENCES shared.users(id),
    created_at                  TIMESTAMPTZ     DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE mm.stock_movements IS 'Material document items — every physical stock movement (SAP MSEG)';
COMMENT ON COLUMN mm.stock_movements.movement_type IS 'SAP movement type codes: 101(GR), 102(GR reversal), 122(return to vendor), 161(return from customer), 201(consumption), 261(production issue), 262(return from production), 301(transfer), 309(transfer w/o reservation), 501(receipt w/o PO), 551(scrap), 561(initial stock), 601(outbound delivery), 701(surplus), 702(shortage)';
COMMENT ON COLUMN mm.stock_movements.material_document_number IS 'Groups related movements into a single material document';
COMMENT ON COLUMN mm.stock_movements.sap_movement_code IS 'Mirror of movement_type for SAP alignment queries';
COMMENT ON COLUMN mm.stock_movements.is_reversal IS 'TRUE if this movement reverses another movement';
COMMENT ON COLUMN mm.stock_movements.reversal_movement_id IS 'Points to the original movement being reversed';
COMMENT ON COLUMN mm.stock_movements.reference_doc_type IS 'Human-readable source context: gr | po | production_order | logistics_release | tr | adjustment';
COMMENT ON COLUMN mm.stock_movements.production_order_id IS 'FK to pp.production_orders — constraint added in 010_cross_fks.sql';

-- ---------------------------------------------------------------------------
-- 6. mm.invoice_verifications (SAP MIRO — Invoice Verification / 3-way match)
-- ---------------------------------------------------------------------------
CREATE TABLE mm.invoice_verifications (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    iv_number           VARCHAR(50)     UNIQUE NOT NULL,
    po_id               UUID            REFERENCES mm.purchase_orders(id),
    vendor_id           UUID            NOT NULL REFERENCES shared.vendors(id),
    invoice_date        DATE            NOT NULL,
    posting_date        DATE,
    invoice_amount      NUMERIC(15,2)   NOT NULL,
    gr_amount           NUMERIC(15,2),
    po_amount           NUMERIC(15,2),
    price_variance      NUMERIC(15,2),
    qty_variance        INTEGER,
    tax_invoice_no      VARCHAR(30),
    vat_amount          NUMERIC(15,2),
    status              VARCHAR(20)     DEFAULT 'pending',  -- pending | matched | variance | posted
    match_result        VARCHAR(20),                        -- exact | within_tolerance | over_tolerance
    verified_by         UUID            REFERENCES shared.users(id),
    verified_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE mm.invoice_verifications IS 'Invoice verification — 3-way match PO vs GR vs Invoice (SAP MIRO)';
COMMENT ON COLUMN mm.invoice_verifications.status IS 'pending | matched | variance | posted';
COMMENT ON COLUMN mm.invoice_verifications.match_result IS 'exact | within_tolerance | over_tolerance';
COMMENT ON COLUMN mm.invoice_verifications.price_variance IS 'invoice_amount - po_amount (positive = overcharge)';
COMMENT ON COLUMN mm.invoice_verifications.qty_variance IS 'Invoice qty - GR accepted qty';

-- ---------------------------------------------------------------------------
-- 7. mm.reservations (SAP RESB — Reservation generalized)
-- ---------------------------------------------------------------------------
CREATE TABLE mm.reservations (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    reservation_number  VARCHAR(50)     UNIQUE NOT NULL,
    parts_id            UUID            NOT NULL REFERENCES shared.parts_master(id),
    storage_bin_id      UUID            REFERENCES wms.storage_bins(id),
    requirement_qty     INTEGER         NOT NULL,
    withdrawn_qty       INTEGER         DEFAULT 0,
    movement_type       VARCHAR(10),                        -- 261, 201, 601
    unit_of_measure     VARCHAR(10)     DEFAULT 'EA' REFERENCES shared.units_of_measure(uom_code),
    -- Typed FKs (no polymorphic source_doc_id)
    project_id          UUID            REFERENCES shared.projects(id),
    production_order_id UUID,           -- FK to pp.production_orders added in 010_cross_fks.sql
    tr_id               UUID            REFERENCES tms.transportation_requirements(id),
    source_doc_type     VARCHAR(30),                        -- human-readable: project | production_order | tr
    status              VARCHAR(20)     DEFAULT 'open',     -- open | partially_withdrawn | closed | cancelled
    requirement_date    DATE,
    created_by          UUID            REFERENCES shared.users(id),
    created_at          TIMESTAMPTZ     DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE mm.reservations IS 'Material reservations — planned goods issues for production, projects, or shipments (SAP RESB)';
COMMENT ON COLUMN mm.reservations.movement_type IS 'SAP movement type for withdrawal: 261 (production issue), 201 (cost center issue), 601 (outbound delivery)';
COMMENT ON COLUMN mm.reservations.source_doc_type IS 'Human-readable source: project | production_order | tr';
COMMENT ON COLUMN mm.reservations.status IS 'open | partially_withdrawn | closed | cancelled';
COMMENT ON COLUMN mm.reservations.production_order_id IS 'FK to pp.production_orders — constraint added in 010_cross_fks.sql';

-- ---------------------------------------------------------------------------
-- 8. mm.return_orders (Return Management)
-- ---------------------------------------------------------------------------
CREATE TABLE mm.return_orders (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    return_number       VARCHAR(50)     UNIQUE NOT NULL,
    direction           VARCHAR(10)     NOT NULL,           -- vendor | customer
    original_doc_type   VARCHAR(30),                        -- po | gr | freight_order
    original_doc_id     UUID,
    parts_id            UUID            NOT NULL REFERENCES shared.parts_master(id),
    return_qty          INTEGER         NOT NULL,
    unit_of_measure     VARCHAR(10)     DEFAULT 'EA' REFERENCES shared.units_of_measure(uom_code),
    reason_code         VARCHAR(20),                        -- quality_fail | wrong_item | damaged | excess | customer_return
    disposition         VARCHAR(20),                        -- restock | scrap | rework | replace
    status              VARCHAR(20)     DEFAULT 'open',     -- open | shipped | received | closed
    requested_date      DATE,
    completed_date      DATE,
    created_by          UUID            REFERENCES shared.users(id),
    approved_by         UUID            REFERENCES shared.users(id),
    created_at          TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE mm.return_orders IS 'Return orders — vendor returns (122) and customer returns (161)';
COMMENT ON COLUMN mm.return_orders.direction IS 'vendor | customer';
COMMENT ON COLUMN mm.return_orders.original_doc_type IS 'po | gr | freight_order — source document type';
COMMENT ON COLUMN mm.return_orders.reason_code IS 'quality_fail | wrong_item | damaged | excess | customer_return';
COMMENT ON COLUMN mm.return_orders.disposition IS 'restock | scrap | rework | replace';
COMMENT ON COLUMN mm.return_orders.status IS 'open | shipped | received | closed';

-- ---------------------------------------------------------------------------
-- 9. mm.quality_inspections (SAP QALS — Inspection Lot)
-- ---------------------------------------------------------------------------
CREATE TABLE mm.quality_inspections (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    inspection_number   VARCHAR(50)     UNIQUE NOT NULL,
    gr_id               UUID            REFERENCES mm.goods_receipts(id),
    parts_id            UUID            NOT NULL REFERENCES shared.parts_master(id),
    inspection_type     VARCHAR(20),                        -- incoming | in_process | final
    sample_size         INTEGER,
    accepted_qty        INTEGER,
    rejected_qty        INTEGER,
    defect_codes        TEXT[],
    result              VARCHAR(20),                        -- pass | fail | conditional
    decision            VARCHAR(20),                        -- accept | reject | rework | scrap
    decision_date       DATE,
    inspector_id        UUID            REFERENCES shared.users(id),
    photos_url          TEXT,
    notes               TEXT,
    created_at          TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE mm.quality_inspections IS 'Quality inspection lots — incoming, in-process, and final inspections (SAP QALS)';
COMMENT ON COLUMN mm.quality_inspections.inspection_type IS 'incoming | in_process | final';
COMMENT ON COLUMN mm.quality_inspections.result IS 'pass | fail | conditional';
COMMENT ON COLUMN mm.quality_inspections.decision IS 'Usage decision: accept | reject | rework | scrap';
COMMENT ON COLUMN mm.quality_inspections.defect_codes IS 'Array of defect code identifiers found during inspection';

-- ---------------------------------------------------------------------------
-- 10. mm.scrap_records (Scrap / Disposal)
-- ---------------------------------------------------------------------------
CREATE TABLE mm.scrap_records (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    scrap_number        VARCHAR(50)     UNIQUE NOT NULL,
    parts_id            UUID            NOT NULL REFERENCES shared.parts_master(id),
    scrap_qty           INTEGER         NOT NULL,
    unit_of_measure     VARCHAR(10)     DEFAULT 'EA' REFERENCES shared.units_of_measure(uom_code),
    reason_code         VARCHAR(20),                        -- production_defect | handling_damage | expiry | obsolete
    cost_value          NUMERIC(15,2),
    production_order_id UUID,           -- FK to pp.production_orders added in 010_cross_fks.sql
    storage_bin_id      UUID            REFERENCES wms.storage_bins(id),
    movement_id         UUID            REFERENCES mm.stock_movements(id),
    approved_by         UUID            REFERENCES shared.users(id),
    scrap_date          DATE            NOT NULL,
    notes               TEXT,
    created_at          TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE mm.scrap_records IS 'Scrap/disposal records — tracks scrapped material with cost and reason (movement type 551)';
COMMENT ON COLUMN mm.scrap_records.reason_code IS 'production_defect | handling_damage | expiry | obsolete';
COMMENT ON COLUMN mm.scrap_records.production_order_id IS 'FK to pp.production_orders — constraint added in 010_cross_fks.sql';
COMMENT ON COLUMN mm.scrap_records.movement_id IS 'FK to mm.stock_movements — the scrap movement (551) that posted this';

-- ===========================================================================
-- Indexes
-- ===========================================================================

-- ---- purchase_requisitions ----
CREATE INDEX idx_mm_pr_parts_id          ON mm.purchase_requisitions(parts_id);
CREATE INDEX idx_mm_pr_project_id        ON mm.purchase_requisitions(project_id);
CREATE INDEX idx_mm_pr_status            ON mm.purchase_requisitions(status);
CREATE INDEX idx_mm_pr_required_date     ON mm.purchase_requisitions(required_date);
CREATE INDEX idx_mm_pr_requested_by      ON mm.purchase_requisitions(requested_by);
CREATE INDEX idx_mm_pr_approved_by       ON mm.purchase_requisitions(approved_by);
CREATE INDEX idx_mm_pr_converted_poi     ON mm.purchase_requisitions(converted_po_item_id);

-- ---- purchase_orders ----
CREATE INDEX idx_mm_po_project_id        ON mm.purchase_orders(project_id);
CREATE INDEX idx_mm_po_vendor_id         ON mm.purchase_orders(vendor_id);
CREATE INDEX idx_mm_po_purchasing_org_id ON mm.purchase_orders(purchasing_org_id);
CREATE INDEX idx_mm_po_status            ON mm.purchase_orders(po_status);
CREATE INDEX idx_mm_po_ordered_by        ON mm.purchase_orders(ordered_by);
CREATE INDEX idx_mm_po_cx_manager_id     ON mm.purchase_orders(cx_manager_id);
CREATE INDEX idx_mm_po_requested_date    ON mm.purchase_orders(requested_date);
CREATE INDEX idx_mm_po_is_archived       ON mm.purchase_orders(is_archived) WHERE is_archived = FALSE;

-- ---- purchase_order_items ----
CREATE INDEX idx_mm_poi_po_id            ON mm.purchase_order_items(po_id);
CREATE INDEX idx_mm_poi_parts_id         ON mm.purchase_order_items(parts_id);
CREATE INDEX idx_mm_poi_planned_del      ON mm.purchase_order_items(planned_delivery_date);
CREATE INDEX idx_mm_poi_confirmed_del    ON mm.purchase_order_items(confirmed_delivery_date);
CREATE INDEX idx_mm_poi_actual_del       ON mm.purchase_order_items(actual_delivery_date);
CREATE INDEX idx_mm_poi_quality_check    ON mm.purchase_order_items(quality_check_result);
CREATE INDEX idx_mm_poi_is_urgent        ON mm.purchase_order_items(is_urgent) WHERE is_urgent = TRUE;
CREATE INDEX idx_mm_poi_production_type  ON mm.purchase_order_items(production_type);

-- ---- goods_receipts ----
CREATE INDEX idx_mm_gr_po_id             ON mm.goods_receipts(po_id);
CREATE INDEX idx_mm_gr_po_item_id        ON mm.goods_receipts(po_item_id);
CREATE INDEX idx_mm_gr_parts_id          ON mm.goods_receipts(parts_id);
CREATE INDEX idx_mm_gr_storage_bin_id    ON mm.goods_receipts(storage_bin_id);
CREATE INDEX idx_mm_gr_batch_id          ON mm.goods_receipts(batch_id);
CREATE INDEX idx_mm_gr_movement_type     ON mm.goods_receipts(movement_type);
CREATE INDEX idx_mm_gr_actual_receipt    ON mm.goods_receipts(actual_receipt_date);
CREATE INDEX idx_mm_gr_posting_date      ON mm.goods_receipts(posting_date);
CREATE INDEX idx_mm_gr_received_by       ON mm.goods_receipts(received_by);
CREATE INDEX idx_mm_gr_inspected_by      ON mm.goods_receipts(inspected_by);
CREATE INDEX idx_mm_gr_inspection_result ON mm.goods_receipts(inspection_result);

-- ---- stock_movements ----
CREATE INDEX idx_mm_sm_material_doc      ON mm.stock_movements(material_document_number);
CREATE INDEX idx_mm_sm_movement_type     ON mm.stock_movements(movement_type);
CREATE INDEX idx_mm_sm_sap_code          ON mm.stock_movements(sap_movement_code);
CREATE INDEX idx_mm_sm_parts_id          ON mm.stock_movements(parts_id);
CREATE INDEX idx_mm_sm_from_bin_id       ON mm.stock_movements(from_bin_id);
CREATE INDEX idx_mm_sm_to_bin_id         ON mm.stock_movements(to_bin_id);
CREATE INDEX idx_mm_sm_batch_id          ON mm.stock_movements(batch_id);
CREATE INDEX idx_mm_sm_status            ON mm.stock_movements(status);
CREATE INDEX idx_mm_sm_posting_date      ON mm.stock_movements(posting_date);
CREATE INDEX idx_mm_sm_actual_date       ON mm.stock_movements(actual_date);
CREATE INDEX idx_mm_sm_fiscal            ON mm.stock_movements(fiscal_year, fiscal_period);
CREATE INDEX idx_mm_sm_gl_account_id     ON mm.stock_movements(gl_account_id);
CREATE INDEX idx_mm_sm_reversal_id       ON mm.stock_movements(reversal_movement_id);
CREATE INDEX idx_mm_sm_gr_id             ON mm.stock_movements(gr_id);
CREATE INDEX idx_mm_sm_po_item_id        ON mm.stock_movements(po_item_id);
CREATE INDEX idx_mm_sm_prod_order_id     ON mm.stock_movements(production_order_id);
CREATE INDEX idx_mm_sm_logistics_rel_id  ON mm.stock_movements(logistics_release_id);
CREATE INDEX idx_mm_sm_tr_id             ON mm.stock_movements(tr_id);
CREATE INDEX idx_mm_sm_created_by        ON mm.stock_movements(created_by);

-- ---- invoice_verifications ----
CREATE INDEX idx_mm_iv_po_id             ON mm.invoice_verifications(po_id);
CREATE INDEX idx_mm_iv_vendor_id         ON mm.invoice_verifications(vendor_id);
CREATE INDEX idx_mm_iv_invoice_date      ON mm.invoice_verifications(invoice_date);
CREATE INDEX idx_mm_iv_posting_date      ON mm.invoice_verifications(posting_date);
CREATE INDEX idx_mm_iv_status            ON mm.invoice_verifications(status);
CREATE INDEX idx_mm_iv_match_result      ON mm.invoice_verifications(match_result);
CREATE INDEX idx_mm_iv_verified_by       ON mm.invoice_verifications(verified_by);

-- ---- reservations ----
CREATE INDEX idx_mm_rsv_parts_id         ON mm.reservations(parts_id);
CREATE INDEX idx_mm_rsv_storage_bin_id   ON mm.reservations(storage_bin_id);
CREATE INDEX idx_mm_rsv_project_id       ON mm.reservations(project_id);
CREATE INDEX idx_mm_rsv_prod_order_id    ON mm.reservations(production_order_id);
CREATE INDEX idx_mm_rsv_tr_id            ON mm.reservations(tr_id);
CREATE INDEX idx_mm_rsv_status           ON mm.reservations(status);
CREATE INDEX idx_mm_rsv_movement_type    ON mm.reservations(movement_type);
CREATE INDEX idx_mm_rsv_requirement_date ON mm.reservations(requirement_date);
CREATE INDEX idx_mm_rsv_created_by       ON mm.reservations(created_by);

-- ---- return_orders ----
CREATE INDEX idx_mm_ret_direction        ON mm.return_orders(direction);
CREATE INDEX idx_mm_ret_parts_id         ON mm.return_orders(parts_id);
CREATE INDEX idx_mm_ret_status           ON mm.return_orders(status);
CREATE INDEX idx_mm_ret_reason_code      ON mm.return_orders(reason_code);
CREATE INDEX idx_mm_ret_disposition      ON mm.return_orders(disposition);
CREATE INDEX idx_mm_ret_requested_date   ON mm.return_orders(requested_date);
CREATE INDEX idx_mm_ret_created_by       ON mm.return_orders(created_by);
CREATE INDEX idx_mm_ret_approved_by      ON mm.return_orders(approved_by);

-- ---- quality_inspections ----
CREATE INDEX idx_mm_qi_gr_id             ON mm.quality_inspections(gr_id);
CREATE INDEX idx_mm_qi_parts_id          ON mm.quality_inspections(parts_id);
CREATE INDEX idx_mm_qi_inspection_type   ON mm.quality_inspections(inspection_type);
CREATE INDEX idx_mm_qi_result            ON mm.quality_inspections(result);
CREATE INDEX idx_mm_qi_decision          ON mm.quality_inspections(decision);
CREATE INDEX idx_mm_qi_decision_date     ON mm.quality_inspections(decision_date);
CREATE INDEX idx_mm_qi_inspector_id      ON mm.quality_inspections(inspector_id);

-- ---- scrap_records ----
CREATE INDEX idx_mm_scrap_parts_id       ON mm.scrap_records(parts_id);
CREATE INDEX idx_mm_scrap_prod_order_id  ON mm.scrap_records(production_order_id);
CREATE INDEX idx_mm_scrap_storage_bin_id ON mm.scrap_records(storage_bin_id);
CREATE INDEX idx_mm_scrap_movement_id    ON mm.scrap_records(movement_id);
CREATE INDEX idx_mm_scrap_reason_code    ON mm.scrap_records(reason_code);
CREATE INDEX idx_mm_scrap_scrap_date     ON mm.scrap_records(scrap_date);
CREATE INDEX idx_mm_scrap_approved_by    ON mm.scrap_records(approved_by);
