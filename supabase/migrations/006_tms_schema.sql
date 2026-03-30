-- ============================================================================
-- Migration 006: tms Schema — Transportation Management (SAP TM)
--
-- SAP S/4HANA TM mapping:
--   tms.locations                    → SAP TM Location Master
--   tms.carriers                     → SAP BP-Carrier (Forwarding Agent)
--   tms.dispatch_schedules           → SAP Vehicle Scheduling
--   tms.transportation_requirements  → SAP TR (Transportation Requirement)
--   tms.freight_orders               → SAP FO (Freight Order / Shipment)
--   tms.logistics_releases           → SAP Outbound Delivery (VL01N)
--   tms.logistics_release_items      → SAP LIPS (Delivery Item)
--   tms.packaging_materials          → SAP Packaging Material Master
--   tms.routes                       → SAP TM Route
--
-- Dependencies:
--   001_create_schemas.sql   (tms schema)
--   002_shared_reference_data.sql (shared.gl_accounts, shared.units_of_measure)
--   003_shared_master_data.sql    (shared.users, shared.projects)
--   004 or 005               (shared.parts_master — assumed to exist)
--
-- NOTE: tms.logistics_release_items.batch_id and from_bin_id FK constraints
--       to wms.batches / wms.storage_bins will be added in 010_cross_fks.sql
--       because the wms schema tables are created in 007.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. tms.locations (SAP TM Location Master)
-- ---------------------------------------------------------------------------
CREATE TABLE tms.locations (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    location_code   VARCHAR(20)     UNIQUE NOT NULL,
    location_type   VARCHAR(20)     NOT NULL,               -- warehouse, customer, vendor, hub, fulfillment
    location_name   VARCHAR(200)    NOT NULL,
    address         TEXT,
    postal_code     VARCHAR(10),
    city            VARCHAR(100),
    country_code    CHAR(2)         DEFAULT 'KR',
    contact_name    VARCHAR(100),
    contact_phone   VARCHAR(20),
    contact_email   VARCHAR(255),
    inbound_address TEXT,
    max_cbm         NUMERIC(10,3),
    is_origin       BOOLEAN         DEFAULT FALSE,
    is_destination  BOOLEAN         DEFAULT FALSE,
    status          VARCHAR(10)     DEFAULT 'active',
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE tms.locations IS 'Physical locations — warehouses, customer sites, hubs (SAP TM Location Master)';
COMMENT ON COLUMN tms.locations.location_type IS 'warehouse | customer | vendor | hub | fulfillment';
COMMENT ON COLUMN tms.locations.is_origin IS 'TRUE if this location can be a shipment origin';
COMMENT ON COLUMN tms.locations.is_destination IS 'TRUE if this location can be a shipment destination';

-- ---------------------------------------------------------------------------
-- 2. tms.carriers (SAP BP-Carrier)
-- ---------------------------------------------------------------------------
CREATE TABLE tms.carriers (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    carrier_code        VARCHAR(20)     UNIQUE NOT NULL,
    carrier_name        VARCHAR(200)    NOT NULL,
    carrier_type        VARCHAR(20),                        -- truck, courier, air, sea, mixed
    max_cbm_per_trip    NUMERIC(10,3),
    assigned_dispatcher UUID            REFERENCES shared.users(id),
    contact_name        VARCHAR(100),
    contact_phone       VARCHAR(20),
    notes               TEXT,
    status              VARCHAR(10)     DEFAULT 'active',
    created_at          TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE tms.carriers IS 'Transportation carriers / forwarding agents (SAP BP-Carrier role)';
COMMENT ON COLUMN tms.carriers.carrier_type IS 'truck | courier | air | sea | mixed';
COMMENT ON COLUMN tms.carriers.assigned_dispatcher IS 'Internal dispatcher user responsible for this carrier';

-- ---------------------------------------------------------------------------
-- 3. tms.dispatch_schedules (SAP Vehicle Scheduling)
-- ---------------------------------------------------------------------------
CREATE TABLE tms.dispatch_schedules (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    schedule_date       DATE            NOT NULL,
    carrier_id          UUID            REFERENCES tms.carriers(id),
    total_cbm_assigned  NUMERIC(10,3)   DEFAULT 0,
    max_cbm             NUMERIC(10,3),
    is_overbooked       BOOLEAN         DEFAULT FALSE,
    notes               TEXT,
    created_at          TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE tms.dispatch_schedules IS 'Daily vehicle/carrier dispatch capacity schedule (SAP Vehicle Scheduling)';
COMMENT ON COLUMN tms.dispatch_schedules.is_overbooked IS 'TRUE when total_cbm_assigned exceeds max_cbm';

-- ---------------------------------------------------------------------------
-- 4. tms.transportation_requirements (SAP TR)
-- ---------------------------------------------------------------------------
CREATE TABLE tms.transportation_requirements (
    id                          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    tr_number                   VARCHAR(50)     UNIQUE NOT NULL,
    project_id                  UUID            REFERENCES shared.projects(id),
    origin_location_id          UUID            REFERENCES tms.locations(id),
    destination_location_id     UUID            REFERENCES tms.locations(id),
    requested_shipment_date     DATE            NOT NULL,
    delivery_type               VARCHAR(20),                    -- direct, courier, relay, pickup, transfer
    packaging_type              VARCHAR(50),
    payment_method              VARCHAR(20),
    delivery_method             VARCHAR(20),
    delivery_type_detail        VARCHAR(50),
    outbound_method             VARCHAR(50),
    unloading_service           VARCHAR(20),
    recipient_name              VARCHAR(200),
    recipient_phone             VARCHAR(20),
    recipient_alt_phone         VARCHAR(20),
    recipient_address           TEXT,
    recipient_preferred_time    VARCHAR(50),
    delivery_time_slot          VARCHAR(20),
    reception_time_slot         VARCHAR(20),
    sender_name                 VARCHAR(200),
    sender_phone                VARCHAR(20),
    sender_address              TEXT,
    outer_box_count             INTEGER,
    cbm_manual                  NUMERIC(10,3),
    outbound_zone               TEXT[],
    items_description           TEXT,
    special_instructions        TEXT,
    partner_instructions        TEXT,
    status                      VARCHAR(20)     DEFAULT 'draft',
    dispatch_status             VARCHAR(20),
    sync_source                 VARCHAR(20),                    -- serpa, fulfillment, movement
    external_record_id          VARCHAR(100),
    is_pre_shipment             BOOLEAN         DEFAULT FALSE,
    outbound_confirmation_url   TEXT,
    created_by                  UUID            REFERENCES shared.users(id),
    created_at                  TIMESTAMPTZ     DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE tms.transportation_requirements IS 'Transportation requirements — demand-side shipping requests (SAP TR)';
COMMENT ON COLUMN tms.transportation_requirements.delivery_type IS 'direct | courier | relay | pickup | transfer';
COMMENT ON COLUMN tms.transportation_requirements.sync_source IS 'serpa | fulfillment | movement — external system origin';
COMMENT ON COLUMN tms.transportation_requirements.outbound_zone IS 'Array of zone codes for outbound routing';

-- ---------------------------------------------------------------------------
-- 5. tms.freight_orders (SAP FO — Shipment)
-- ---------------------------------------------------------------------------
CREATE TABLE tms.freight_orders (
    id                          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    fo_number                   VARCHAR(50)     UNIQUE NOT NULL,
    tr_id                       UUID            REFERENCES tms.transportation_requirements(id),
    carrier_id                  UUID            REFERENCES tms.carriers(id),
    dispatch_schedule_id        UUID            REFERENCES tms.dispatch_schedules(id),
    origin_location_id          UUID            REFERENCES tms.locations(id),
    destination_location_id     UUID            REFERENCES tms.locations(id),
    planned_shipment_date       DATE,
    confirmed_shipment_date     DATE,
    actual_departure_datetime   TIMESTAMPTZ,
    actual_arrival_datetime     TIMESTAMPTZ,
    shipping_status             VARCHAR(20)     DEFAULT 'planned',
    delivery_slot               VARCHAR(20),
    vehicle_type                VARCHAR(50),
    total_cbm                   NUMERIC(10,3),
    freight_revenue             NUMERIC(15,2),
    freight_cost                NUMERIC(15,2),
    loading_cost                NUMERIC(15,2),
    revenue_account_id          UUID            REFERENCES shared.gl_accounts(id),
    cost_account_id             UUID            REFERENCES shared.gl_accounts(id),
    tax_invoice_no              VARCHAR(30),
    tracking_number             VARCHAR(100),
    packing_list_url            TEXT,
    delivery_confirmation_url   TEXT,
    customer_signature_url      TEXT,
    qr_code_url                 TEXT,
    slack_ts                    VARCHAR(100),
    alimtalk_sent               BOOLEAN         DEFAULT FALSE,
    pre_shipment_date           DATE,
    customer_accepted           BOOLEAN         DEFAULT FALSE,
    customer_accepted_name      VARCHAR(100),
    customer_accepted_at        TIMESTAMPTZ,
    billing_status              VARCHAR(20)     DEFAULT 'pending',
    expense_status              VARCHAR(20)     DEFAULT 'pending',
    portfolio_sent              BOOLEAN         DEFAULT FALSE,
    portfolio_tracking_number   VARCHAR(100),
    created_by                  UUID            REFERENCES shared.users(id),
    created_at                  TIMESTAMPTZ     DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE tms.freight_orders IS 'Freight orders — supply-side shipment execution (SAP Freight Order)';
COMMENT ON COLUMN tms.freight_orders.shipping_status IS 'planned | confirmed | in_transit | delivered | cancelled';
COMMENT ON COLUMN tms.freight_orders.billing_status IS 'pending | invoiced | paid';
COMMENT ON COLUMN tms.freight_orders.expense_status IS 'pending | invoiced | paid';

-- ---------------------------------------------------------------------------
-- 6. tms.logistics_releases (SAP Outbound Delivery — moved from pp to tms)
-- ---------------------------------------------------------------------------
CREATE TABLE tms.logistics_releases (
    id                          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    release_number              VARCHAR(50)     UNIQUE NOT NULL,
    production_order_id         UUID,            -- FK to pp.production_orders added later via ALTER
    project_id                  UUID            REFERENCES shared.projects(id),
    tr_id                       UUID            REFERENCES tms.transportation_requirements(id),
    status                      VARCHAR(20)     DEFAULT 'pending',  -- pending | picking | packed | released | cancelled
    shipment_status             VARCHAR(20),
    requested_release_date      DATE,
    actual_release_date         DATE,
    items_summary               TEXT,
    outer_box_count             INTEGER,
    outer_box_detail            TEXT,
    remaining_packing           TEXT,
    release_confirmation_url    TEXT,
    delivery_confirmation_url   TEXT,
    customer_signature_url      TEXT,
    courier_waybill_url         TEXT,
    tracking_number             TEXT,
    created_by                  UUID            REFERENCES shared.users(id),
    created_at                  TIMESTAMPTZ     DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE tms.logistics_releases IS 'Outbound delivery / logistics release documents (SAP VL01N Outbound Delivery)';
COMMENT ON COLUMN tms.logistics_releases.status IS 'pending | picking | packed | released | cancelled';
COMMENT ON COLUMN tms.logistics_releases.production_order_id IS 'FK to pp.production_orders — added via ALTER in cross-FK migration';

-- ---------------------------------------------------------------------------
-- 7. tms.logistics_release_items (SAP LIPS — Delivery Item)
-- ---------------------------------------------------------------------------
CREATE TABLE tms.logistics_release_items (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    release_id          UUID            NOT NULL REFERENCES tms.logistics_releases(id),
    line_number         INTEGER         NOT NULL,
    parts_id            UUID            NOT NULL REFERENCES shared.parts_master(id),
    released_qty        INTEGER         NOT NULL,
    batch_id            UUID,            -- FK to wms.batches added in 010_cross_fks.sql
    from_bin_id         UUID,            -- FK to wms.storage_bins added in 010_cross_fks.sql
    unit_of_measure     VARCHAR(10)     DEFAULT 'EA' REFERENCES shared.units_of_measure(uom_code),
    UNIQUE (release_id, line_number)
);

COMMENT ON TABLE tms.logistics_release_items IS 'Line items for logistics releases (SAP LIPS — Delivery Item)';
COMMENT ON COLUMN tms.logistics_release_items.batch_id IS 'FK to wms.batches — added via ALTER in 010_cross_fks.sql';
COMMENT ON COLUMN tms.logistics_release_items.from_bin_id IS 'FK to wms.storage_bins — added via ALTER in 010_cross_fks.sql';

-- ---------------------------------------------------------------------------
-- 8. tms.packaging_materials (SAP Packaging Material)
-- ---------------------------------------------------------------------------
CREATE TABLE tms.packaging_materials (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    box_code        VARCHAR(20)     UNIQUE NOT NULL,
    box_name        VARCHAR(100),
    width_cm        NUMERIC(8,2),
    depth_cm        NUMERIC(8,2),
    height_cm       NUMERIC(8,2),
    cbm             NUMERIC(10,6),
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE tms.packaging_materials IS 'Standard packaging box dimensions and CBM (SAP Packaging Material Master)';

-- ---------------------------------------------------------------------------
-- 9. tms.routes (SAP TM Route)
-- ---------------------------------------------------------------------------
CREATE TABLE tms.routes (
    id                      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    route_code              VARCHAR(20)     UNIQUE NOT NULL,
    origin_location_id      UUID            REFERENCES tms.locations(id),
    destination_location_id UUID            REFERENCES tms.locations(id),
    carrier_id              UUID            REFERENCES tms.carriers(id),
    standard_transit_days   INTEGER,
    cost_rate               NUMERIC(10,2),
    status                  VARCHAR(10)     DEFAULT 'active'
);

COMMENT ON TABLE tms.routes IS 'Predefined shipping routes with carrier assignments (SAP TM Route)';

-- ===========================================================================
-- Indexes
-- ===========================================================================

-- locations
CREATE INDEX idx_tms_locations_type          ON tms.locations(location_type);
CREATE INDEX idx_tms_locations_status        ON tms.locations(status);
CREATE INDEX idx_tms_locations_country       ON tms.locations(country_code);

-- carriers
CREATE INDEX idx_tms_carriers_type           ON tms.carriers(carrier_type);
CREATE INDEX idx_tms_carriers_status         ON tms.carriers(status);
CREATE INDEX idx_tms_carriers_dispatcher     ON tms.carriers(assigned_dispatcher);

-- dispatch_schedules
CREATE INDEX idx_tms_dispatch_date           ON tms.dispatch_schedules(schedule_date);
CREATE INDEX idx_tms_dispatch_carrier        ON tms.dispatch_schedules(carrier_id);

-- transportation_requirements
CREATE INDEX idx_tms_tr_project              ON tms.transportation_requirements(project_id);
CREATE INDEX idx_tms_tr_origin               ON tms.transportation_requirements(origin_location_id);
CREATE INDEX idx_tms_tr_destination          ON tms.transportation_requirements(destination_location_id);
CREATE INDEX idx_tms_tr_shipment_date        ON tms.transportation_requirements(requested_shipment_date);
CREATE INDEX idx_tms_tr_status               ON tms.transportation_requirements(status);
CREATE INDEX idx_tms_tr_dispatch_status      ON tms.transportation_requirements(dispatch_status);
CREATE INDEX idx_tms_tr_sync_source          ON tms.transportation_requirements(sync_source);
CREATE INDEX idx_tms_tr_created_by           ON tms.transportation_requirements(created_by);

-- freight_orders
CREATE INDEX idx_tms_fo_tr                   ON tms.freight_orders(tr_id);
CREATE INDEX idx_tms_fo_carrier              ON tms.freight_orders(carrier_id);
CREATE INDEX idx_tms_fo_dispatch_schedule    ON tms.freight_orders(dispatch_schedule_id);
CREATE INDEX idx_tms_fo_origin               ON tms.freight_orders(origin_location_id);
CREATE INDEX idx_tms_fo_destination          ON tms.freight_orders(destination_location_id);
CREATE INDEX idx_tms_fo_planned_date         ON tms.freight_orders(planned_shipment_date);
CREATE INDEX idx_tms_fo_shipping_status      ON tms.freight_orders(shipping_status);
CREATE INDEX idx_tms_fo_billing_status       ON tms.freight_orders(billing_status);
CREATE INDEX idx_tms_fo_expense_status       ON tms.freight_orders(expense_status);
CREATE INDEX idx_tms_fo_created_by           ON tms.freight_orders(created_by);

-- logistics_releases
CREATE INDEX idx_tms_lr_production_order     ON tms.logistics_releases(production_order_id);
CREATE INDEX idx_tms_lr_project              ON tms.logistics_releases(project_id);
CREATE INDEX idx_tms_lr_tr                   ON tms.logistics_releases(tr_id);
CREATE INDEX idx_tms_lr_status               ON tms.logistics_releases(status);
CREATE INDEX idx_tms_lr_shipment_status      ON tms.logistics_releases(shipment_status);
CREATE INDEX idx_tms_lr_release_date         ON tms.logistics_releases(requested_release_date);
CREATE INDEX idx_tms_lr_created_by           ON tms.logistics_releases(created_by);

-- logistics_release_items
CREATE INDEX idx_tms_lri_release             ON tms.logistics_release_items(release_id);
CREATE INDEX idx_tms_lri_parts               ON tms.logistics_release_items(parts_id);
CREATE INDEX idx_tms_lri_batch               ON tms.logistics_release_items(batch_id);

-- routes
CREATE INDEX idx_tms_routes_origin           ON tms.routes(origin_location_id);
CREATE INDEX idx_tms_routes_destination      ON tms.routes(destination_location_id);
CREATE INDEX idx_tms_routes_carrier          ON tms.routes(carrier_id);
CREATE INDEX idx_tms_routes_status           ON tms.routes(status);
