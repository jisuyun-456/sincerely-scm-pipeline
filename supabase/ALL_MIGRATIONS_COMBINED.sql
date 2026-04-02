-- ================================================================
-- SCM Data Architecture — SAP S/4HANA Full Enterprise
-- Supabase PostgreSQL Complete Migration (18 files)
-- Generated: 2026-04-02 (018 Quick Wins 추가)
-- Tables: ~55 across 6 schemas (shared/tms/wms/mm/pp/finance)
-- ================================================================


-- ################################################################
-- ## 001_create_schemas.sql
-- ################################################################

-- ============================================================
-- Migration 001: Schema Namespace 생성
-- SAP S/4HANA Full Enterprise 기반 6개 Schema
-- Version: v4 (2026-03-29 완전 재작성)
-- ============================================================

CREATE SCHEMA IF NOT EXISTS shared;   -- SAP: Master Data (MM/BP/PS)
CREATE SCHEMA IF NOT EXISTS tms;      -- SAP: TM (Transportation Management)
CREATE SCHEMA IF NOT EXISTS wms;      -- SAP: EWM (Extended Warehouse Management)
CREATE SCHEMA IF NOT EXISTS mm;       -- SAP: MM (Materials Management) + QM
CREATE SCHEMA IF NOT EXISTS pp;       -- SAP: PP (Production Planning)
CREATE SCHEMA IF NOT EXISTS finance;  -- SAP: FI 경량화 + 더존 아마란스10 연계

-- cross-schema FK를 위한 search_path 설정
ALTER DATABASE postgres SET search_path TO shared, tms, wms, mm, pp, finance, public;


-- ################################################################
-- ## 002_shared_reference_data.sql
-- ################################################################

-- ============================================================
-- Migration 002: shared Schema — Reference/Config Tables
-- SAP: T134 (Material Types), T023 (Material Groups),
--       T006 (Units of Measure), SKA1 (Chart of Accounts)
-- 이 테이블들은 다른 모든 테이블에서 참조되므로 가장 먼저 생성
-- ============================================================

-- -------------------------------------------------------
-- shared.units_of_measure (SAP T006)
-- 모든 수량 필드에서 참조하는 단위 마스터
-- -------------------------------------------------------
CREATE TABLE shared.units_of_measure (
  uom_code   VARCHAR(10) PRIMARY KEY,  -- EA, M, KG, SET, BOX, SHEET, ROLL, PCS
  uom_name   VARCHAR(50) NOT NULL,
  dimension  VARCHAR(20),  -- quantity, length, weight, volume, area
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- -------------------------------------------------------
-- shared.gl_accounts (SAP: Chart of Accounts — 더존 코드 매핑)
-- -------------------------------------------------------
CREATE TABLE shared.gl_accounts (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_code   VARCHAR(10) UNIQUE NOT NULL,   -- 더존 계정코드 (예: 146000)
  account_name   VARCHAR(100) NOT NULL,          -- 원재료, 제품, 매출원가 등
  account_type   VARCHAR(20) NOT NULL,           -- asset, liability, equity, revenue, expense
  ifrs_category  VARCHAR(30),                    -- inventory, cogs, trade_payable, trade_receivable
  normal_balance VARCHAR(6) NOT NULL,            -- debit, credit
  parent_id      UUID REFERENCES shared.gl_accounts(id),
  douzone_code   VARCHAR(20),                    -- 더존 아마란스10 내부 코드
  is_active      BOOLEAN DEFAULT TRUE,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- -------------------------------------------------------
-- shared.material_types (SAP T134)
-- 자재유형 — GL 계정 자동결정의 핵심 참조 테이블
-- -------------------------------------------------------
CREATE TABLE shared.material_types (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  type_code               VARCHAR(10) UNIQUE NOT NULL,  -- ROH, HALB, FERT, VERP, HIBE, HAWA
  type_name               VARCHAR(100) NOT NULL,
  is_stockable            BOOLEAN DEFAULT TRUE,
  is_batch_managed        BOOLEAN DEFAULT FALSE,
  default_procurement     VARCHAR(1),  -- E(in-house), F(external), X(both)
  default_valuation_class VARCHAR(10),
  -- GL 계정 자동결정 (FIX-4: 하드코딩 제거)
  default_debit_gl_id     UUID REFERENCES shared.gl_accounts(id),  -- GR 시 차변 계정
  default_credit_gl_id    UUID REFERENCES shared.gl_accounts(id),  -- GR 시 대변 계정
  issue_debit_gl_id       UUID REFERENCES shared.gl_accounts(id),  -- GI 시 차변 (매출원가 등)
  issue_credit_gl_id      UUID REFERENCES shared.gl_accounts(id),  -- GI 시 대변 (재고자산)
  created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- -------------------------------------------------------
-- shared.material_groups (SAP T023)
-- 자재그룹 — 구매분석, 지출분석용 분류
-- -------------------------------------------------------
CREATE TABLE shared.material_groups (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  group_code VARCHAR(20) UNIQUE NOT NULL,
  group_name VARCHAR(100) NOT NULL,
  parent_id  UUID REFERENCES shared.material_groups(id),
  created_at TIMESTAMPTZ DEFAULT NOW()
);


-- ################################################################
-- ## 003_shared_master_data.sql
-- ################################################################

-- ============================================================================
-- Migration 003: shared Schema — Organizations, Users, Business Partners, Projects
--
-- SAP S/4HANA mapping:
--   shared.organizations  → T001 (Company Codes) / T001W (Plants/Warehouses)
--   shared.users          → SU01 (User Master) + Supabase Auth integration
--   shared.clients        → BP (Business Partner - Customer role)
--   shared.vendors        → BP (Business Partner - Vendor role) + 더존 ERP linkage
--   shared.projects       → PS (Project System)
--
-- Dependencies: 002_shared_reference_data.sql (shared.units_of_measure, shared.gl_accounts)
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. shared.organizations (SAP T001 / T001W)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shared.organizations (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    org_code        VARCHAR(10)     UNIQUE NOT NULL,
    org_name        VARCHAR(100)    NOT NULL,
    org_type        VARCHAR(20),                        -- company, plant, warehouse
    parent_id       UUID            REFERENCES shared.organizations(id),
    country_code    CHAR(2)         DEFAULT 'KR',
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE shared.organizations IS 'Organizational units — companies, plants, warehouses (SAP T001/T001W)';
COMMENT ON COLUMN shared.organizations.org_type IS 'company | plant | warehouse';
COMMENT ON COLUMN shared.organizations.parent_id IS 'Self-referencing hierarchy (plant → company, warehouse → plant)';

-- ---------------------------------------------------------------------------
-- 2. shared.users (SAP SU01 + Supabase Auth)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shared.users (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_user_id    UUID            UNIQUE REFERENCES auth.users(id),
    employee_number VARCHAR(20)     UNIQUE,
    name            VARCHAR(100)    NOT NULL,
    email           VARCHAR(255)    UNIQUE NOT NULL,
    phone           VARCHAR(20),
    team            VARCHAR(20),                        -- cx, logistics, scm, production, procurement
    slack_id        VARCHAR(50),
    slack_id_tag    TEXT,
    status          VARCHAR(10)     DEFAULT 'active',
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE shared.users IS 'Internal users linked to Supabase Auth (SAP SU01)';
COMMENT ON COLUMN shared.users.team IS 'cx | logistics | scm | production | procurement';
COMMENT ON COLUMN shared.users.auth_user_id IS 'FK to auth.users — Supabase authentication identity';

-- ---------------------------------------------------------------------------
-- 3. shared.clients (SAP BP-Customer)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shared.clients (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    client_code         VARCHAR(20)     UNIQUE,
    company_name        VARCHAR(200)    NOT NULL,
    business_reg_number VARCHAR(20),
    contact_name        VARCHAR(100),
    contact_email       VARCHAR(255),
    contact_phone       VARCHAR(20),
    address             TEXT,
    status              VARCHAR(10)     DEFAULT 'active',
    created_at          TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE shared.clients IS 'Customer business partners (SAP BP-Customer role)';

-- ---------------------------------------------------------------------------
-- 4. shared.vendors (SAP BP-Vendor + 더존 ERP linkage)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shared.vendors (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    vendor_code         VARCHAR(20)     UNIQUE NOT NULL,
    vendor_name         VARCHAR(200)    NOT NULL,
    vendor_type         VARCHAR(50),                    -- manufacturer, packaging, logistics, assembly
    business_reg_number VARCHAR(20),
    contact_name        VARCHAR(100),
    contact_phone       VARCHAR(20),
    email               VARCHAR(255),
    address             TEXT,
    bank_account        VARCHAR(50),
    bank_holder         VARCHAR(100),
    bank_name           VARCHAR(100),
    is_stock_vendor     BOOLEAN         DEFAULT FALSE,
    douzone_vendor_code VARCHAR(20),
    status              VARCHAR(10)     DEFAULT 'active',
    created_at          TIMESTAMPTZ     DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE shared.vendors IS 'Vendor business partners with 더존 ERP integration (SAP BP-Vendor role)';
COMMENT ON COLUMN shared.vendors.vendor_type IS 'manufacturer | packaging | logistics | assembly';
COMMENT ON COLUMN shared.vendors.douzone_vendor_code IS 'Mapped vendor code in 더존 ERP system';
COMMENT ON COLUMN shared.vendors.is_stock_vendor IS 'TRUE if vendor supplies stock-managed materials';

-- ---------------------------------------------------------------------------
-- 5. shared.projects (SAP PS — Project System)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shared.projects (
    id                      UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    project_code            VARCHAR(50)     UNIQUE NOT NULL,
    project_name            VARCHAR(200)    NOT NULL,
    client_id               UUID            REFERENCES shared.clients(id),
    main_usage              VARCHAR(50),
    project_status          VARCHAR(20)     DEFAULT 'active',
    first_shipment_date     DATE,
    last_shipment_date      DATE,
    fulfillment_lead_time   INTEGER,
    cx_specialist_id        UUID            REFERENCES shared.users(id),
    ordered_items_summary   TEXT,
    dropbox_link            TEXT,
    created_at              TIMESTAMPTZ     DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE shared.projects IS 'Customer projects linking orders to fulfillment (SAP PS)';
COMMENT ON COLUMN shared.projects.cx_specialist_id IS 'CX team member responsible for this project';
COMMENT ON COLUMN shared.projects.fulfillment_lead_time IS 'Standard lead time in days from order to shipment';

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_organizations_parent     ON shared.organizations(parent_id);
CREATE INDEX IF NOT EXISTS idx_organizations_org_type   ON shared.organizations(org_type);

CREATE INDEX IF NOT EXISTS idx_users_team               ON shared.users(team);
CREATE INDEX IF NOT EXISTS idx_users_status             ON shared.users(status);
CREATE INDEX IF NOT EXISTS idx_users_auth_user_id       ON shared.users(auth_user_id);

CREATE INDEX IF NOT EXISTS idx_clients_status           ON shared.clients(status);

CREATE INDEX IF NOT EXISTS idx_vendors_vendor_type      ON shared.vendors(vendor_type);
CREATE INDEX IF NOT EXISTS idx_vendors_status           ON shared.vendors(status);
CREATE INDEX IF NOT EXISTS idx_vendors_is_stock_vendor  ON shared.vendors(is_stock_vendor);

CREATE INDEX IF NOT EXISTS idx_projects_client_id       ON shared.projects(client_id);
CREATE INDEX IF NOT EXISTS idx_projects_cx_specialist   ON shared.projects(cx_specialist_id);
CREATE INDEX IF NOT EXISTS idx_projects_status          ON shared.projects(project_status);


-- ################################################################
-- ## 004_shared_material_master.sql
-- ################################################################

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


-- ################################################################
-- ## 005_shared_valuation.sql
-- ################################################################

-- ============================================================================
-- Migration 005: shared Schema — Material Valuation & Vendor Evaluations
--
-- SAP S/4HANA mapping:
--   shared.material_valuation   → MBEW (Material Valuation)
--   shared.vendor_evaluations   → ME61 (Vendor Evaluation)
--
-- Dependencies:
--   003_shared_master_data.sql     (shared.organizations, shared.users, shared.vendors)
--   004_shared_material_master.sql (shared.parts_master)
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. shared.material_valuation (SAP MBEW)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shared.material_valuation (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    parts_id            UUID            NOT NULL REFERENCES shared.parts_master(id),
    valuation_area_id   UUID            REFERENCES shared.organizations(id),
    valuation_class     VARCHAR(10),
    costing_method      VARCHAR(15),                        -- weighted_avg | fifo
    standard_price      NUMERIC(15,4),
    moving_avg_price    NUMERIC(15,4),
    total_stock_value   NUMERIC(15,2),
    last_updated_at     TIMESTAMPTZ     DEFAULT NOW(),

    UNIQUE(parts_id, valuation_area_id)
);

COMMENT ON TABLE shared.material_valuation IS 'Material valuation per valuation area — costing and stock value (SAP MBEW)';
COMMENT ON COLUMN shared.material_valuation.costing_method IS 'weighted_avg | fifo';
COMMENT ON COLUMN shared.material_valuation.valuation_area_id IS 'Valuation area — typically a plant (shared.organizations)';
COMMENT ON COLUMN shared.material_valuation.standard_price IS 'Standard price per base UOM for standard costing';
COMMENT ON COLUMN shared.material_valuation.moving_avg_price IS 'Moving average price per base UOM';

-- ---------------------------------------------------------------------------
-- 2. shared.vendor_evaluations
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS shared.vendor_evaluations (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    vendor_id       UUID            NOT NULL REFERENCES shared.vendors(id),
    period          VARCHAR(7)      NOT NULL,               -- YYYY-MM
    quality_score   NUMERIC(5,2),
    delivery_score  NUMERIC(5,2),
    price_score     NUMERIC(5,2),
    overall_score   NUMERIC(5,2),
    evaluated_by    UUID            REFERENCES shared.users(id),
    created_at      TIMESTAMPTZ     DEFAULT NOW(),

    UNIQUE(vendor_id, period)
);

COMMENT ON TABLE shared.vendor_evaluations IS 'Periodic vendor performance evaluations (SAP ME61)';
COMMENT ON COLUMN shared.vendor_evaluations.period IS 'Evaluation period in YYYY-MM format';
COMMENT ON COLUMN shared.vendor_evaluations.overall_score IS 'Composite score derived from quality, delivery, and price';

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_valuation_parts          ON shared.material_valuation(parts_id);
CREATE INDEX IF NOT EXISTS idx_valuation_area           ON shared.material_valuation(valuation_area_id);
CREATE INDEX IF NOT EXISTS idx_valuation_costing_method ON shared.material_valuation(costing_method);

CREATE INDEX IF NOT EXISTS idx_vendor_eval_vendor       ON shared.vendor_evaluations(vendor_id);
CREATE INDEX IF NOT EXISTS idx_vendor_eval_period       ON shared.vendor_evaluations(period);
CREATE INDEX IF NOT EXISTS idx_vendor_eval_evaluated_by ON shared.vendor_evaluations(evaluated_by);


-- ################################################################
-- ## 006_tms_schema.sql
-- ################################################################

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


-- ################################################################
-- ## 007_wms_schema.sql
-- ################################################################

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


-- ################################################################
-- ## 008_mm_schema.sql
-- ################################################################

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


-- ################################################################
-- ## 009_pp_schema.sql
-- ################################################################

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


-- ################################################################
-- ## 010_cross_schema_fks.sql
-- ################################################################

-- ============================================================
-- Migration 010: Cross-Schema Foreign Keys
-- Resolving circular dependencies between schemas
-- ============================================================
-- These FK constraints could not be created during initial
-- table creation because the referenced tables did not yet
-- exist (cross-schema dependency ordering).
-- ============================================================

-- pp → tms: logistics_releases.production_order_id
ALTER TABLE tms.logistics_releases
  ADD CONSTRAINT fk_lr_production_order
  FOREIGN KEY (production_order_id) REFERENCES pp.production_orders(id);

-- mm → pp: stock_movements.production_order_id
ALTER TABLE mm.stock_movements
  ADD CONSTRAINT fk_sm_production_order
  FOREIGN KEY (production_order_id) REFERENCES pp.production_orders(id);

-- mm → pp: reservations.production_order_id
ALTER TABLE mm.reservations
  ADD CONSTRAINT fk_res_production_order
  FOREIGN KEY (production_order_id) REFERENCES pp.production_orders(id);

-- mm → pp: scrap_records.production_order_id
-- (defined as plain UUID in migration 008; FK added here now
--  that pp.production_orders exists)
ALTER TABLE mm.scrap_records
  ADD CONSTRAINT fk_scrap_production_order
  FOREIGN KEY (production_order_id) REFERENCES pp.production_orders(id);

-- wms → mm: batches.gr_id
ALTER TABLE wms.batches
  ADD CONSTRAINT fk_batch_goods_receipt
  FOREIGN KEY (gr_id) REFERENCES mm.goods_receipts(id);

-- tms → wms: logistics_release_items.batch_id
ALTER TABLE tms.logistics_release_items
  ADD CONSTRAINT fk_lri_batch
  FOREIGN KEY (batch_id) REFERENCES wms.batches(id);

-- tms → wms: logistics_release_items.from_bin_id
ALTER TABLE tms.logistics_release_items
  ADD CONSTRAINT fk_lri_from_bin
  FOREIGN KEY (from_bin_id) REFERENCES wms.storage_bins(id);

-- shared → pp: goods_master.default_bom_id
ALTER TABLE shared.goods_master
  ADD CONSTRAINT fk_goods_default_bom
  FOREIGN KEY (default_bom_id) REFERENCES pp.bom_headers(id);


-- ################################################################
-- ## 011_finance_schema.sql
-- ################################################################

-- ============================================================================
-- Migration 011: finance Schema — K-IFRS 회계 + 더존 아마란스10 연계 (SAP FI 경량화)
--
-- SAP S/4HANA FI mapping (lightweight):
--   finance.accounting_entries  → BKPF/BSEG (Accounting Document Header/Item)
--   finance.cost_settings       → OBYA/T030 (Costing Method Config per Material Type)
--   finance.douzone_sync_log    → Custom (더존 아마란스10 전표 연동 이력)
--   finance.period_closes       → MARDH/MBEWH (Month-End Inventory Valuation Snapshot)
--
-- Design philosophy:
--   더존 아마란스10이 실질 원장(Real Ledger)이며,
--   본 시스템은 SCM 트랜잭션의 회계 전표 초안을 생성하고
--   더존과의 동기화 상태를 추적한다.
--   Single-row 차변/대변 패턴으로 전표를 관리하고,
--   월말 마감 시 재고 평가 스냅샷을 기록한다.
--
-- Dependencies:
--   001_create_schemas.sql          (finance schema)
--   002_shared_reference_data.sql   (shared.gl_accounts)
--   003_shared_master_data.sql      (shared.users)
--   004_shared_material_master.sql  (shared.parts_master)
--   007_wms_schema.sql              (wms.warehouses)
-- ============================================================================


-- ---------------------------------------------------------------------------
-- 1. finance.accounting_entries (SAP BKPF/BSEG — Single-row debit/credit)
--    분개 전표: Draft → Reviewed → Posted 워크플로우
--    더존이 실질 원장이므로 본 테이블은 SCM 측 전표 초안 + 연동 추적용
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS finance.accounting_entries (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    entry_number        VARCHAR(50)     UNIQUE NOT NULL,         -- auto-generated: AE-YYYYMMDD-NNNN
    entry_date          DATE            NOT NULL,
    entry_type          VARCHAR(30)     NOT NULL,                -- purchase_invoice | goods_receipt | goods_issue | production
                                                                 -- assembly_issue | assembly_receipt | freight | inventory_adjustment

    -- Source traceability (SCM 트랜잭션 원본 추적)
    source_table        VARCHAR(50),                             -- 'mm.goods_receipts', 'mm.stock_movements', etc.
    source_id           UUID,

    -- Debit / Credit (단일 행 차변/대변 패턴)
    debit_account_id    UUID            NOT NULL REFERENCES shared.gl_accounts(id),
    credit_account_id   UUID            NOT NULL REFERENCES shared.gl_accounts(id),
    amount              NUMERIC(15,2)   NOT NULL,

    -- Quantity & Cost detail
    quantity            INTEGER,
    unit_cost           NUMERIC(15,4),
    costing_method      VARCHAR(15),                             -- weighted_avg | fifo

    -- Tax (부가세)
    tax_invoice_no      VARCHAR(30),
    vat_amount          NUMERIC(15,2),

    -- Fiscal period (K-IFRS 회계기간)
    fiscal_year         VARCHAR(4),
    fiscal_period       VARCHAR(2),

    -- Currency
    currency_code       CHAR(3)         DEFAULT 'KRW',

    -- Workflow: draft → reviewed → posted
    status              VARCHAR(15)     DEFAULT 'draft',
    reviewed_by         UUID            REFERENCES shared.users(id),
    reviewed_at         TIMESTAMPTZ,
    posted_by           UUID            REFERENCES shared.users(id),
    posted_at           TIMESTAMPTZ,

    -- Reversal (역분개)
    is_reversal         BOOLEAN         DEFAULT FALSE,
    reversal_entry_id   UUID            REFERENCES finance.accounting_entries(id),

    -- 더존 아마란스10 연계
    douzone_slip_no     VARCHAR(30),                             -- 더존 전표번호 (회계팀 기재)

    description         TEXT,

    -- Audit
    created_by          UUID            REFERENCES shared.users(id),
    created_at          TIMESTAMPTZ     DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE  finance.accounting_entries IS 'SCM 분개 전표 — single-row 차변/대변 패턴, 더존 아마란스10이 실질 원장 (SAP BKPF/BSEG)';
COMMENT ON COLUMN finance.accounting_entries.entry_number IS 'Auto-generated: AE-YYYYMMDD-NNNN';
COMMENT ON COLUMN finance.accounting_entries.entry_type IS 'purchase_invoice | goods_receipt | goods_issue | production | assembly_issue | assembly_receipt | freight | inventory_adjustment';
COMMENT ON COLUMN finance.accounting_entries.source_table IS 'Origin table: mm.goods_receipts, mm.stock_movements, etc.';
COMMENT ON COLUMN finance.accounting_entries.status IS 'Workflow: draft → reviewed → posted';
COMMENT ON COLUMN finance.accounting_entries.costing_method IS 'weighted_avg | fifo';
COMMENT ON COLUMN finance.accounting_entries.douzone_slip_no IS '더존 아마란스10 전표번호 — 회계팀이 더존에서 확정 후 기재';
COMMENT ON COLUMN finance.accounting_entries.is_reversal IS 'TRUE if this entry reverses another entry';
COMMENT ON COLUMN finance.accounting_entries.reversal_entry_id IS 'Points to the original entry being reversed';
COMMENT ON COLUMN finance.accounting_entries.fiscal_year IS 'K-IFRS 회계연도 (YYYY)';
COMMENT ON COLUMN finance.accounting_entries.fiscal_period IS 'K-IFRS 회계기간 (01-12)';


-- ---------------------------------------------------------------------------
-- 2. finance.cost_settings (SAP OBYA/T030 — Per parts_type costing config)
--    자재유형별 원가산정 방법 설정 (가중평균 / FIFO)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS finance.cost_settings (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    parts_type      VARCHAR(50)     NOT NULL,                    -- raw, packaging, merchandise, semi_finished
    costing_method  VARCHAR(15)     NOT NULL,                    -- weighted_avg | fifo
    effective_from  DATE            NOT NULL,
    effective_to    DATE,                                        -- NULL = currently active
    set_by          UUID            REFERENCES shared.users(id),
    created_at      TIMESTAMPTZ     DEFAULT NOW(),

    UNIQUE(parts_type, effective_from)
);

COMMENT ON TABLE  finance.cost_settings IS '자재유형(parts_type)별 원가산정 방법 설정 — effective_to IS NULL이면 현행 (SAP OBYA/T030)';
COMMENT ON COLUMN finance.cost_settings.parts_type IS 'raw | packaging | merchandise | semi_finished';
COMMENT ON COLUMN finance.cost_settings.costing_method IS 'weighted_avg | fifo';
COMMENT ON COLUMN finance.cost_settings.effective_to IS 'NULL = currently active policy';


-- ---------------------------------------------------------------------------
-- 3. finance.douzone_sync_log (Custom — 더존 아마란스10 전표 연동 이력)
--    SCM 전표 → 더존 동기화 상태 추적
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS finance.douzone_sync_log (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    entry_id        UUID            NOT NULL REFERENCES finance.accounting_entries(id),
    douzone_slip_no VARCHAR(30),
    sync_status     VARCHAR(20)     DEFAULT 'pending',           -- pending | synced | error
    sync_notes      TEXT,
    synced_by       UUID            REFERENCES shared.users(id),
    synced_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE  finance.douzone_sync_log IS 'SCM 전표 → 더존 아마란스10 동기화 이력 추적';
COMMENT ON COLUMN finance.douzone_sync_log.sync_status IS 'pending | synced | error';
COMMENT ON COLUMN finance.douzone_sync_log.douzone_slip_no IS '더존에서 생성된 전표번호';


-- ---------------------------------------------------------------------------
-- 4. finance.period_closes (SAP MARDH/MBEWH — Month-End Closing Snapshot)
--    월말 마감 시 재고 평가 스냅샷 — 재고원장(Stock Ledger) 역할
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS finance.period_closes (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    period          VARCHAR(7)      NOT NULL,                    -- YYYY-MM
    parts_id        UUID            NOT NULL REFERENCES shared.parts_master(id),
    warehouse_id    UUID            REFERENCES wms.warehouses(id),
    closing_qty     INTEGER         NOT NULL,
    closing_value   NUMERIC(15,2),
    unit_cost       NUMERIC(15,4),
    costing_method  VARCHAR(15),                                 -- weighted_avg | fifo
    is_closed       BOOLEAN         DEFAULT FALSE,
    closed_by       UUID            REFERENCES shared.users(id),
    closed_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ     DEFAULT NOW(),

    UNIQUE(period, parts_id, warehouse_id)
);

COMMENT ON TABLE  finance.period_closes IS '월말 마감 재고 평가 스냅샷 — 재고원장 역할 (SAP MARDH/MBEWH)';
COMMENT ON COLUMN finance.period_closes.period IS 'Closing period: YYYY-MM';
COMMENT ON COLUMN finance.period_closes.closing_qty IS '마감 시점 재고 수량';
COMMENT ON COLUMN finance.period_closes.closing_value IS '마감 시점 재고 금액 (closing_qty × unit_cost)';
COMMENT ON COLUMN finance.period_closes.unit_cost IS '해당 기간 단위원가';
COMMENT ON COLUMN finance.period_closes.is_closed IS 'TRUE after period close is finalized — no further changes allowed';


-- ============================================================================
-- INDEXES
-- ============================================================================

-- ---------------------------------------------------------------------------
-- finance.accounting_entries indexes
-- ---------------------------------------------------------------------------

-- Workflow filtering: find all drafts, reviewed, or posted entries
CREATE INDEX idx_ae_status
    ON finance.accounting_entries (status);

-- Date range queries for reporting and period closes
CREATE INDEX idx_ae_entry_date
    ON finance.accounting_entries (entry_date);

-- Source traceability: find accounting entries from a specific SCM transaction
CREATE INDEX idx_ae_source
    ON finance.accounting_entries (source_table, source_id);

-- Filter by transaction type (goods_receipt, purchase_invoice, etc.)
CREATE INDEX idx_ae_entry_type
    ON finance.accounting_entries (entry_type);

-- GL account analysis: debit side
CREATE INDEX idx_ae_debit_account
    ON finance.accounting_entries (debit_account_id);

-- GL account analysis: credit side
CREATE INDEX idx_ae_credit_account
    ON finance.accounting_entries (credit_account_id);

-- Fiscal period reporting (K-IFRS): find all entries for a given fiscal year + period
CREATE INDEX idx_ae_fiscal
    ON finance.accounting_entries (fiscal_year, fiscal_period);

-- ---------------------------------------------------------------------------
-- finance.douzone_sync_log indexes
-- ---------------------------------------------------------------------------

-- Find all sync records for a specific accounting entry
CREATE INDEX idx_dsl_entry_id
    ON finance.douzone_sync_log (entry_id);

-- Filter by sync status (pending entries awaiting sync, errors to retry)
CREATE INDEX idx_dsl_sync_status
    ON finance.douzone_sync_log (sync_status);

-- ---------------------------------------------------------------------------
-- finance.period_closes indexes
-- ---------------------------------------------------------------------------

-- Period-based queries: monthly closing reports
CREATE INDEX idx_pc_period
    ON finance.period_closes (period);

-- Material-based queries: valuation history for a specific part
CREATE INDEX idx_pc_parts_id
    ON finance.period_closes (parts_id);

-- Warehouse-based queries: inventory value per warehouse
CREATE INDEX idx_pc_warehouse_id
    ON finance.period_closes (warehouse_id);

-- Find open/closed periods
CREATE INDEX idx_pc_is_closed
    ON finance.period_closes (is_closed);


-- ============================================================================
-- CHECK CONSTRAINTS
-- ============================================================================

-- Ensure valid entry types
ALTER TABLE finance.accounting_entries
    ADD CONSTRAINT chk_ae_entry_type CHECK (
        entry_type IN (
            'purchase_invoice', 'goods_receipt', 'goods_issue', 'production',
            'assembly_issue', 'assembly_receipt', 'freight', 'inventory_adjustment'
        )
    );

-- Ensure valid workflow status
ALTER TABLE finance.accounting_entries
    ADD CONSTRAINT chk_ae_status CHECK (
        status IN ('draft', 'reviewed', 'posted')
    );

-- Ensure positive amount
ALTER TABLE finance.accounting_entries
    ADD CONSTRAINT chk_ae_amount_positive CHECK (amount > 0);

-- Ensure valid costing methods
ALTER TABLE finance.accounting_entries
    ADD CONSTRAINT chk_ae_costing_method CHECK (
        costing_method IS NULL OR costing_method IN ('weighted_avg', 'fifo')
    );

-- Ensure valid costing methods for cost_settings
ALTER TABLE finance.cost_settings
    ADD CONSTRAINT chk_cs_costing_method CHECK (
        costing_method IN ('weighted_avg', 'fifo')
    );

-- Ensure valid parts types
ALTER TABLE finance.cost_settings
    ADD CONSTRAINT chk_cs_parts_type CHECK (
        parts_type IN ('raw', 'packaging', 'merchandise', 'semi_finished')
    );

-- Ensure effective_to >= effective_from when set
ALTER TABLE finance.cost_settings
    ADD CONSTRAINT chk_cs_effective_range CHECK (
        effective_to IS NULL OR effective_to >= effective_from
    );

-- Ensure valid sync status
ALTER TABLE finance.douzone_sync_log
    ADD CONSTRAINT chk_dsl_sync_status CHECK (
        sync_status IN ('pending', 'synced', 'error')
    );

-- Ensure valid costing method in period_closes
ALTER TABLE finance.period_closes
    ADD CONSTRAINT chk_pc_costing_method CHECK (
        costing_method IS NULL OR costing_method IN ('weighted_avg', 'fifo')
    );

-- Ensure period format YYYY-MM
ALTER TABLE finance.period_closes
    ADD CONSTRAINT chk_pc_period_format CHECK (
        period ~ '^\d{4}-(0[1-9]|1[0-2])$'
    );

-- Ensure fiscal_year format YYYY
ALTER TABLE finance.accounting_entries
    ADD CONSTRAINT chk_ae_fiscal_year_format CHECK (
        fiscal_year IS NULL OR fiscal_year ~ '^\d{4}$'
    );

-- Ensure fiscal_period format 01-12
ALTER TABLE finance.accounting_entries
    ADD CONSTRAINT chk_ae_fiscal_period_format CHECK (
        fiscal_period IS NULL OR fiscal_period ~ '^(0[1-9]|1[0-2])$'
    );


-- ============================================================================
-- updated_at TRIGGER (accounting_entries only — others are append-only)
-- ============================================================================
CREATE OR REPLACE FUNCTION finance.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_ae_updated_at
    BEFORE UPDATE ON finance.accounting_entries
    FOR EACH ROW
    EXECUTE FUNCTION finance.set_updated_at();


-- ################################################################
-- ## 012_views.sql
-- ################################################################

-- ============================================================
-- Migration 012: Views — Business Intelligence & Reporting
-- ============================================================
-- SCM System views for inventory analysis, cost valuation,
-- stock ledger, and accounting summaries.
-- ============================================================

-- ------------------------------------------------------------
-- 1. wms.v_quant_summary
--    Aggregates stock_movements by quant for inventory summary.
--    Shows total receipt, issue, assembly, transfer quantities.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW wms.v_quant_summary AS
SELECT
  q.id AS quant_id,
  q.parts_id,
  q.storage_bin_id,
  q.stock_type,
  q.physical_qty,
  q.system_qty,
  q.reserved_qty,
  q.blocked_qty,
  q.available_qty,
  COALESCE(SUM(CASE WHEN sm.movement_type IN ('101','501','561','161','262') AND sm.to_bin_id = q.storage_bin_id THEN sm.actual_qty ELSE 0 END), 0) AS total_receipt_qty,
  COALESCE(SUM(CASE WHEN sm.movement_type IN ('201','261','551','601','122') AND sm.from_bin_id = q.storage_bin_id THEN sm.actual_qty ELSE 0 END), 0) AS total_issue_qty,
  COALESCE(SUM(CASE WHEN sm.movement_type = '301' AND sm.to_bin_id = q.storage_bin_id THEN sm.actual_qty ELSE 0 END), 0) AS transfer_in_qty,
  COALESCE(SUM(CASE WHEN sm.movement_type = '301' AND sm.from_bin_id = q.storage_bin_id THEN sm.actual_qty ELSE 0 END), 0) AS transfer_out_qty
FROM wms.quants q
LEFT JOIN mm.stock_movements sm
  ON sm.parts_id = q.parts_id
  AND (sm.to_bin_id = q.storage_bin_id OR sm.from_bin_id = q.storage_bin_id)
  AND sm.status = 'completed'
GROUP BY q.id, q.parts_id, q.storage_bin_id, q.stock_type,
         q.physical_qty, q.system_qty, q.reserved_qty, q.blocked_qty, q.available_qty;


-- ------------------------------------------------------------
-- 2. shared.v_available_qty (improved)
--    Shows available quantities per parts with reserved qty
--    deducted. Only considers unrestricted stock.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW shared.v_available_qty AS
SELECT
  p.id AS parts_id,
  p.parts_code,
  p.parts_name,
  p.vendor_id,
  p.parts_type,
  p.material_type_id,
  COALESCE(SUM(q.available_qty), 0) AS available_qty,
  COALESCE(SUM(q.system_qty), 0)    AS system_qty,
  COALESCE(SUM(q.physical_qty), 0)  AS physical_qty,
  COALESCE(SUM(q.reserved_qty), 0)  AS reserved_qty,
  COALESCE(SUM(q.blocked_qty), 0)   AS blocked_qty
FROM shared.parts_master p
LEFT JOIN wms.quants q ON q.parts_id = p.id AND q.stock_type = 'unrestricted'
GROUP BY p.id, p.parts_code, p.parts_name, p.vendor_id, p.parts_type, p.material_type_id;


-- ------------------------------------------------------------
-- 3. finance.v_cost_weighted_avg (FIXED — includes opening balance)
--    Weighted average cost calculation per parts per period,
--    incorporating prior period closing balance.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW finance.v_cost_weighted_avg AS
WITH period_data AS (
  SELECT
    sm.parts_id,
    DATE_TRUNC('month', sm.actual_date) AS period,
    SUM(CASE WHEN sm.movement_type IN ('101','501','561') THEN sm.actual_qty ELSE 0 END) AS receipt_qty,
    SUM(CASE WHEN sm.movement_type IN ('101','501','561') THEN sm.total_cost ELSE 0 END) AS receipt_cost
  FROM mm.stock_movements sm
  WHERE sm.status = 'completed' AND sm.total_cost IS NOT NULL
  GROUP BY sm.parts_id, DATE_TRUNC('month', sm.actual_date)
)
SELECT
  pd.parts_id,
  pd.period,
  COALESCE(pc.closing_qty, 0) AS opening_qty,
  COALESCE(pc.closing_value, 0) AS opening_value,
  pd.receipt_qty,
  pd.receipt_cost,
  CASE
    WHEN (COALESCE(pc.closing_qty, 0) + pd.receipt_qty) > 0
    THEN (COALESCE(pc.closing_value, 0) + pd.receipt_cost)
       / (COALESCE(pc.closing_qty, 0) + pd.receipt_qty)
    ELSE 0
  END AS weighted_avg_unit_cost
FROM period_data pd
LEFT JOIN finance.period_closes pc
  ON pc.parts_id = pd.parts_id
  AND pc.period = TO_CHAR(pd.period - INTERVAL '1 month', 'YYYY-MM')
  AND pc.is_closed = TRUE;


-- ------------------------------------------------------------
-- 4. finance.v_cost_fifo (FIXED — uses gr_id direct link)
--    FIFO cost layers from active batches, linked to
--    goods_receipts via gr_id for receipt date ordering.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW finance.v_cost_fifo AS
SELECT
  b.parts_id,
  b.id AS batch_id,
  b.batch_number,
  b.unit_cost AS fifo_unit_cost,
  b.remaining_qty,
  gr.actual_receipt_date AS receipt_date,
  gr.received_qty AS original_qty
FROM wms.batches b
LEFT JOIN mm.goods_receipts gr ON gr.id = b.gr_id
WHERE b.unit_cost IS NOT NULL AND b.status = 'active'
ORDER BY b.parts_id, gr.actual_receipt_date NULLS LAST;


-- ------------------------------------------------------------
-- 5. finance.v_inventory_valuation
--    K-IFRS IAS 2 inventory valuation view.
--    Uses latest weighted average cost per parts.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW finance.v_inventory_valuation AS
SELECT
  p.parts_id,
  p.parts_code,
  p.parts_name,
  p.available_qty,
  p.physical_qty,
  COALESCE(wa.weighted_avg_unit_cost, 0) AS unit_cost_weighted_avg,
  COALESCE(wa.weighted_avg_unit_cost, 0) * p.available_qty AS inventory_value_weighted_avg
FROM shared.v_available_qty p
LEFT JOIN (
  SELECT DISTINCT ON (parts_id) parts_id, weighted_avg_unit_cost
  FROM finance.v_cost_weighted_avg
  ORDER BY parts_id, period DESC
) wa ON wa.parts_id = p.parts_id;


-- ------------------------------------------------------------
-- 6. finance.v_stock_ledger (재고수불부) ★NEW
--    Period-based stock ledger showing opening balance,
--    receipts, issues, and closing balance per parts.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW finance.v_stock_ledger AS
WITH movements AS (
  SELECT
    TO_CHAR(sm.actual_date, 'YYYY-MM') AS period,
    sm.parts_id,
    SUM(CASE WHEN sm.movement_type IN ('101','501','561','161','262','701') AND sm.to_bin_id IS NOT NULL
        THEN sm.actual_qty ELSE 0 END) AS receipt_qty,
    SUM(CASE WHEN sm.movement_type IN ('101','501','561','161','262','701') AND sm.total_cost IS NOT NULL
        THEN sm.total_cost ELSE 0 END) AS receipt_value,
    SUM(CASE WHEN sm.movement_type IN ('201','261','551','601','122','702') AND sm.from_bin_id IS NOT NULL
        THEN sm.actual_qty ELSE 0 END) AS issue_qty,
    SUM(CASE WHEN sm.movement_type IN ('201','261','551','601','122','702') AND sm.total_cost IS NOT NULL
        THEN sm.total_cost ELSE 0 END) AS issue_value
  FROM mm.stock_movements sm
  WHERE sm.status = 'completed'
  GROUP BY TO_CHAR(sm.actual_date, 'YYYY-MM'), sm.parts_id
)
SELECT
  m.period,
  m.parts_id,
  pm.parts_code,
  pm.parts_name,
  COALESCE(pc.closing_qty, 0) AS opening_qty,
  COALESCE(pc.closing_value, 0) AS opening_value,
  m.receipt_qty,
  m.receipt_value,
  m.issue_qty,
  m.issue_value,
  COALESCE(pc.closing_qty, 0) + m.receipt_qty - m.issue_qty AS closing_qty,
  COALESCE(pc.closing_value, 0) + m.receipt_value - m.issue_value AS closing_value
FROM movements m
JOIN shared.parts_master pm ON pm.id = m.parts_id
LEFT JOIN finance.period_closes pc
  ON pc.parts_id = m.parts_id
  AND pc.period = TO_CHAR((m.period || '-01')::DATE - INTERVAL '1 month', 'YYYY-MM')
  AND pc.is_closed = TRUE;


-- ------------------------------------------------------------
-- 7. finance.v_accounting_summary
--    Aggregated accounting entries by type and status.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW finance.v_accounting_summary AS
SELECT
  ae.entry_type,
  ae.status,
  COUNT(*) AS entry_count,
  SUM(ae.amount) AS total_amount,
  MIN(ae.entry_date) AS earliest_date,
  MAX(ae.entry_date) AS latest_date
FROM finance.accounting_entries ae
GROUP BY ae.entry_type, ae.status
ORDER BY ae.entry_type, ae.status;


-- ################################################################
-- ## 013_indexes.sql
-- ################################################################

-- ============================================================
-- Migration 013: Performance Indexes — Composite & Additional
-- NOTE: Most FK/single-column indexes are already created inline
-- in each migration file. This file adds composite indexes and
-- any missing ones using IF NOT EXISTS for safety.
-- ============================================================

-- ============================================================
-- SCHEMA: shared
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_parts_master_vendor_id ON shared.parts_master (vendor_id);
CREATE INDEX IF NOT EXISTS idx_parts_master_parts_type ON shared.parts_master (parts_type);
CREATE INDEX IF NOT EXISTS idx_parts_master_material_type_id ON shared.parts_master (material_type_id);
CREATE INDEX IF NOT EXISTS idx_parts_master_material_group_id ON shared.parts_master (material_group_id);
CREATE INDEX IF NOT EXISTS idx_parts_master_status ON shared.parts_master (status);
CREATE INDEX IF NOT EXISTS idx_projects_client_id ON shared.projects (client_id);
CREATE INDEX IF NOT EXISTS idx_projects_project_status ON shared.projects (project_status);
CREATE INDEX IF NOT EXISTS idx_item_master_material_type_id ON shared.item_master (material_type_id);
CREATE INDEX IF NOT EXISTS idx_goods_master_material_type_id ON shared.goods_master (material_type_id);

-- ============================================================
-- SCHEMA: tms
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_freight_orders_carrier_id ON tms.freight_orders (carrier_id);
CREATE INDEX IF NOT EXISTS idx_freight_orders_tr_id ON tms.freight_orders (tr_id);
CREATE INDEX IF NOT EXISTS idx_freight_orders_dispatch_schedule_id ON tms.freight_orders (dispatch_schedule_id);
CREATE INDEX IF NOT EXISTS idx_freight_orders_shipping_status ON tms.freight_orders (shipping_status);
CREATE INDEX IF NOT EXISTS idx_freight_orders_planned_date ON tms.freight_orders (planned_shipment_date);
CREATE INDEX IF NOT EXISTS idx_tr_project_id ON tms.transportation_requirements (project_id);
CREATE INDEX IF NOT EXISTS idx_tr_status ON tms.transportation_requirements (status);
CREATE INDEX IF NOT EXISTS idx_lr_tr_id ON tms.logistics_releases (tr_id);
CREATE INDEX IF NOT EXISTS idx_lr_production_order_id ON tms.logistics_releases (production_order_id);

-- ============================================================
-- SCHEMA: wms
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_quants_parts_id ON wms.quants (parts_id);
CREATE INDEX IF NOT EXISTS idx_quants_storage_bin_id ON wms.quants (storage_bin_id);
CREATE INDEX IF NOT EXISTS idx_quants_parts_bin ON wms.quants (parts_id, storage_bin_id);
CREATE INDEX IF NOT EXISTS idx_quants_stock_type ON wms.quants (stock_type);
CREATE INDEX IF NOT EXISTS idx_storage_bins_warehouse_id ON wms.storage_bins (warehouse_id);
CREATE INDEX IF NOT EXISTS idx_storage_bins_zone ON wms.storage_bins (zone);
CREATE INDEX IF NOT EXISTS idx_batches_parts_id ON wms.batches (parts_id);
CREATE INDEX IF NOT EXISTS idx_batches_gr_id ON wms.batches (gr_id);
CREATE INDEX IF NOT EXISTS idx_batches_status ON wms.batches (status);

-- ============================================================
-- SCHEMA: mm
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_po_project_id ON mm.purchase_orders (project_id);
CREATE INDEX IF NOT EXISTS idx_po_vendor_id ON mm.purchase_orders (vendor_id);
CREATE INDEX IF NOT EXISTS idx_po_po_status ON mm.purchase_orders (po_status);
CREATE INDEX IF NOT EXISTS idx_poi_po_id ON mm.purchase_order_items (po_id);
CREATE INDEX IF NOT EXISTS idx_poi_parts_id ON mm.purchase_order_items (parts_id);
CREATE INDEX IF NOT EXISTS idx_gr_po_item_id ON mm.goods_receipts (po_item_id);
CREATE INDEX IF NOT EXISTS idx_gr_parts_id ON mm.goods_receipts (parts_id);
CREATE INDEX IF NOT EXISTS idx_gr_actual_receipt_date ON mm.goods_receipts (actual_receipt_date);
CREATE INDEX IF NOT EXISTS idx_sm_parts_id ON mm.stock_movements (parts_id);
CREATE INDEX IF NOT EXISTS idx_sm_movement_type ON mm.stock_movements (movement_type);
CREATE INDEX IF NOT EXISTS idx_sm_actual_date ON mm.stock_movements (actual_date);
CREATE INDEX IF NOT EXISTS idx_sm_status ON mm.stock_movements (status);
CREATE INDEX IF NOT EXISTS idx_sm_from_bin_id ON mm.stock_movements (from_bin_id);
CREATE INDEX IF NOT EXISTS idx_sm_to_bin_id ON mm.stock_movements (to_bin_id);
CREATE INDEX IF NOT EXISTS idx_sm_gr_id ON mm.stock_movements (gr_id);
CREATE INDEX IF NOT EXISTS idx_sm_production_order_id ON mm.stock_movements (production_order_id);

-- Composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_sm_parts_status ON mm.stock_movements (parts_id, status);
CREATE INDEX IF NOT EXISTS idx_sm_parts_type_date ON mm.stock_movements (parts_id, movement_type, actual_date);
CREATE INDEX IF NOT EXISTS idx_sm_status_date ON mm.stock_movements (status, actual_date);

CREATE INDEX IF NOT EXISTS idx_res_parts_id ON mm.reservations (parts_id);
CREATE INDEX IF NOT EXISTS idx_res_status ON mm.reservations (status);
CREATE INDEX IF NOT EXISTS idx_res_project_id ON mm.reservations (project_id);
CREATE INDEX IF NOT EXISTS idx_pr_parts_id ON mm.purchase_requisitions (parts_id);
CREATE INDEX IF NOT EXISTS idx_pr_status ON mm.purchase_requisitions (status);

-- ============================================================
-- SCHEMA: pp
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_prod_project_id ON pp.production_orders (project_id);
CREATE INDEX IF NOT EXISTS idx_prod_status ON pp.production_orders (status);
CREATE INDEX IF NOT EXISTS idx_prod_goods_id ON pp.production_orders (goods_id);
CREATE INDEX IF NOT EXISTS idx_prod_work_center_id ON pp.production_orders (work_center_id);
CREATE INDEX IF NOT EXISTS idx_bom_goods_id ON pp.bom_headers (goods_id);
CREATE INDEX IF NOT EXISTS idx_bom_item_id ON pp.bom_headers (item_id);
CREATE INDEX IF NOT EXISTS idx_poc_production_order_id ON pp.production_order_components (production_order_id);
CREATE INDEX IF NOT EXISTS idx_poc_parts_id ON pp.production_order_components (parts_id);

-- ============================================================
-- SCHEMA: finance
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_ae_status ON finance.accounting_entries (status);
CREATE INDEX IF NOT EXISTS idx_ae_entry_date ON finance.accounting_entries (entry_date);
CREATE INDEX IF NOT EXISTS idx_ae_source ON finance.accounting_entries (source_table, source_id);
CREATE INDEX IF NOT EXISTS idx_ae_entry_type ON finance.accounting_entries (entry_type);
CREATE INDEX IF NOT EXISTS idx_ae_debit_account_id ON finance.accounting_entries (debit_account_id);
CREATE INDEX IF NOT EXISTS idx_ae_credit_account_id ON finance.accounting_entries (credit_account_id);
CREATE INDEX IF NOT EXISTS idx_ae_fiscal ON finance.accounting_entries (fiscal_year, fiscal_period);
CREATE INDEX IF NOT EXISTS idx_ae_status_date ON finance.accounting_entries (status, entry_date);
CREATE INDEX IF NOT EXISTS idx_dz_entry_id ON finance.douzone_sync_log (entry_id);
CREATE INDEX IF NOT EXISTS idx_dz_sync_status ON finance.douzone_sync_log (sync_status);
CREATE INDEX IF NOT EXISTS idx_pc_period ON finance.period_closes (period);
CREATE INDEX IF NOT EXISTS idx_pc_parts_id ON finance.period_closes (parts_id);
CREATE INDEX IF NOT EXISTS idx_pc_warehouse_id ON finance.period_closes (warehouse_id);
CREATE INDEX IF NOT EXISTS idx_pc_parts_period ON finance.period_closes (parts_id, period);
CREATE INDEX IF NOT EXISTS idx_pc_parts_period_closed ON finance.period_closes (parts_id, period, is_closed);


-- ################################################################
-- ## 014_triggers_quants.sql
-- ################################################################

-- ============================================================================
-- Migration 014: Triggers — Stock Movement -> Quants Auto-Update (FIX-3)
--
-- CRITICAL BUSINESS LOGIC:
--   When a stock_movement is inserted (or updated) with status='completed',
--   automatically update wms.quants system_qty via UPSERT.
--
-- Movement type -> action mapping (SAP MSEG):
--   Decrease from_bin: 102, 122, 201, 261, 301, 309, 551, 601, 702
--   Increase to_bin:   101, 161, 262, 301, 309, 501, 561, 701
--
-- The partial unique indexes on wms.quants are:
--   quants_no_batch_unique   ON (parts_id, storage_bin_id, stock_type)           WHERE batch_id IS NULL
--   quants_with_batch_unique ON (parts_id, storage_bin_id, batch_id, stock_type) WHERE batch_id IS NOT NULL
--
-- Dependencies:
--   007_wms_schema.sql   (wms.quants, wms.storage_bins, wms.batches)
--   008_mm_schema.sql    (mm.stock_movements)
-- ============================================================================


-- ---------------------------------------------------------------------------
-- 1. Helper: wms.fn_upsert_quant
--    Handles the NULL vs NOT NULL batch_id UPSERT pattern cleanly.
--    p_qty_delta can be positive (increase) or negative (decrease).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION wms.fn_upsert_quant(
  p_parts_id    UUID,
  p_bin_id      UUID,
  p_batch_id    UUID,
  p_stock_type  VARCHAR,
  p_qty_delta   INTEGER,
  p_date        DATE
) RETURNS VOID AS $$
BEGIN
  -- Guard: skip if no bin specified
  IF p_bin_id IS NULL THEN
    RETURN;
  END IF;

  IF p_batch_id IS NULL THEN
    -- ---- Case A: batch_id IS NULL ----
    -- Uses partial unique index: quants_no_batch_unique
    INSERT INTO wms.quants (
      parts_id, storage_bin_id, batch_id, stock_type,
      system_qty, physical_qty, last_movement_date
    )
    VALUES (
      p_parts_id, p_bin_id, NULL, p_stock_type,
      GREATEST(p_qty_delta, 0), 0, p_date
    )
    ON CONFLICT (parts_id, storage_bin_id, stock_type) WHERE batch_id IS NULL
    DO UPDATE SET
      system_qty          = wms.quants.system_qty + p_qty_delta,
      last_movement_date  = COALESCE(p_date, wms.quants.last_movement_date),
      updated_at          = NOW();
  ELSE
    -- ---- Case B: batch_id IS NOT NULL ----
    -- Uses partial unique index: quants_with_batch_unique
    INSERT INTO wms.quants (
      parts_id, storage_bin_id, batch_id, stock_type,
      system_qty, physical_qty, last_movement_date
    )
    VALUES (
      p_parts_id, p_bin_id, p_batch_id, p_stock_type,
      GREATEST(p_qty_delta, 0), 0, p_date
    )
    ON CONFLICT (parts_id, storage_bin_id, batch_id, stock_type) WHERE batch_id IS NOT NULL
    DO UPDATE SET
      system_qty          = wms.quants.system_qty + p_qty_delta,
      last_movement_date  = COALESCE(p_date, wms.quants.last_movement_date),
      updated_at          = NOW();
  END IF;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION wms.fn_upsert_quant IS 'Atomic quant UPSERT handling NULL/NOT-NULL batch_id partial unique indexes. p_qty_delta is signed (+/-).';


-- ---------------------------------------------------------------------------
-- 2. Main trigger function: wms.fn_update_quants_on_movement
--    Fires AFTER INSERT OR UPDATE OF status on mm.stock_movements
--    when NEW.status = 'completed'.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION wms.fn_update_quants_on_movement()
RETURNS TRIGGER AS $$
DECLARE
  v_parts_id  UUID;
  v_from_bin  UUID;
  v_to_bin    UUID;
  v_qty       INTEGER;
  v_batch_id  UUID;
  v_date      DATE;
BEGIN
  -- Only process completed movements
  IF NEW.status <> 'completed' THEN
    RETURN NEW;
  END IF;

  v_parts_id := NEW.parts_id;
  v_from_bin := NEW.from_bin_id;
  v_to_bin   := NEW.to_bin_id;
  v_qty      := COALESCE(NEW.actual_qty, 0);
  v_batch_id := NEW.batch_id;
  v_date     := COALESCE(NEW.actual_date, CURRENT_DATE);

  -- Skip zero-quantity movements
  IF v_qty <= 0 THEN
    RETURN NEW;
  END IF;

  -- -----------------------------------------------------------------------
  -- DECREASE from_bin
  -- Movement types that consume / remove stock from the source bin:
  --   102  GR Reversal
  --   122  Return to Vendor
  --   201  Cost Center Issue (Consumption)
  --   261  Production Issue (Assembly Issue)
  --   301  Transfer Posting (bin-to-bin)
  --   309  Transfer w/o Reservation
  --   551  Scrap
  --   601  Outbound Delivery (Customer Goods Issue)
  --   702  Inventory Shortage
  -- -----------------------------------------------------------------------
  IF NEW.movement_type IN ('102','122','201','261','301','309','551','601','702')
     AND v_from_bin IS NOT NULL
  THEN
    PERFORM wms.fn_upsert_quant(
      v_parts_id, v_from_bin, v_batch_id,
      'unrestricted', -v_qty, v_date
    );
  END IF;

  -- -----------------------------------------------------------------------
  -- INCREASE to_bin
  -- Movement types that add stock to the destination bin:
  --   101  Goods Receipt
  --   161  Customer Return
  --   262  Return from Production (Assembly Receipt)
  --   301  Transfer Posting (bin-to-bin)
  --   309  Transfer w/o Reservation
  --   501  Receipt without PO
  --   561  Initial Stock Entry
  --   701  Inventory Surplus
  -- -----------------------------------------------------------------------
  IF NEW.movement_type IN ('101','161','262','301','309','501','561','701')
     AND v_to_bin IS NOT NULL
  THEN
    PERFORM wms.fn_upsert_quant(
      v_parts_id, v_to_bin, v_batch_id,
      'unrestricted', v_qty, v_date
    );
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION wms.fn_update_quants_on_movement IS 'Trigger fn: auto-update wms.quants system_qty when a stock_movement is completed (FIX-3)';


-- ---------------------------------------------------------------------------
-- 3. Create the trigger on mm.stock_movements
-- ---------------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_stock_movement_update_quants ON mm.stock_movements;

CREATE TRIGGER trg_stock_movement_update_quants
  AFTER INSERT OR UPDATE OF status ON mm.stock_movements
  FOR EACH ROW
  WHEN (NEW.status = 'completed')
  EXECUTE FUNCTION wms.fn_update_quants_on_movement();

COMMENT ON TRIGGER trg_stock_movement_update_quants ON mm.stock_movements
  IS 'Auto-update wms.quants when a stock movement reaches completed status';


-- ################################################################
-- ## 015_triggers_reservations.sql
-- ################################################################

-- ============================================================================
-- Migration 015: Triggers — Reservations -> Quants Reserved Qty
--
-- BUSINESS LOGIC:
--   When a reservation (mm.reservations) is created, updated, or deleted,
--   automatically adjust wms.quants.reserved_qty for the relevant quant.
--
--   reserved_qty tracks how much stock is "spoken for" by open reservations.
--   available_qty = system_qty - reserved_qty - blocked_qty (GENERATED column).
--
--   Only reservations with status IN ('open', 'partially_withdrawn') contribute
--   to reserved_qty. The open quantity for a reservation is:
--     open_qty = requirement_qty - COALESCE(withdrawn_qty, 0)
--
-- Dependencies:
--   007_wms_schema.sql   (wms.quants)
--   008_mm_schema.sql    (mm.reservations)
-- ============================================================================


-- ---------------------------------------------------------------------------
-- 1. Trigger function: wms.fn_update_reserved_qty
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION wms.fn_update_reserved_qty()
RETURNS TRIGGER AS $$
DECLARE
  v_old_open_qty  INTEGER := 0;
  v_new_open_qty  INTEGER := 0;
  v_delta         INTEGER;
  v_parts_id      UUID;
  v_bin_id        UUID;
BEGIN
  -- -----------------------------------------------------------------------
  -- Calculate the OLD open (unreleased) quantity
  -- Only count reservations that are actively reserving stock
  -- -----------------------------------------------------------------------
  IF TG_OP = 'UPDATE' OR TG_OP = 'DELETE' THEN
    IF OLD.status IN ('open', 'partially_withdrawn') THEN
      v_old_open_qty := GREATEST(OLD.requirement_qty - COALESCE(OLD.withdrawn_qty, 0), 0);
    END IF;
  END IF;

  -- -----------------------------------------------------------------------
  -- Calculate the NEW open (unreleased) quantity
  -- -----------------------------------------------------------------------
  IF TG_OP = 'INSERT' OR TG_OP = 'UPDATE' THEN
    IF NEW.status IN ('open', 'partially_withdrawn') THEN
      v_new_open_qty := GREATEST(NEW.requirement_qty - COALESCE(NEW.withdrawn_qty, 0), 0);
    END IF;
  END IF;

  -- -----------------------------------------------------------------------
  -- Compute delta and apply
  -- -----------------------------------------------------------------------
  v_delta := v_new_open_qty - v_old_open_qty;

  IF v_delta = 0 THEN
    -- No change to reserved qty
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
  END IF;

  -- -----------------------------------------------------------------------
  -- Determine which quant to update
  -- On UPDATE, the bin may have changed; handle both old and new bin
  -- -----------------------------------------------------------------------
  IF TG_OP = 'UPDATE'
     AND OLD.storage_bin_id IS DISTINCT FROM NEW.storage_bin_id
  THEN
    -- Bin changed: release old reservation, apply new reservation
    -- Release from old bin
    IF OLD.storage_bin_id IS NOT NULL AND v_old_open_qty > 0 THEN
      UPDATE wms.quants
      SET reserved_qty = GREATEST(reserved_qty - v_old_open_qty, 0),
          updated_at   = NOW()
      WHERE parts_id       = OLD.parts_id
        AND storage_bin_id = OLD.storage_bin_id
        AND stock_type     = 'unrestricted';
    END IF;
    -- Reserve at new bin
    IF NEW.storage_bin_id IS NOT NULL AND v_new_open_qty > 0 THEN
      UPDATE wms.quants
      SET reserved_qty = GREATEST(reserved_qty + v_new_open_qty, 0),
          updated_at   = NOW()
      WHERE parts_id       = NEW.parts_id
        AND storage_bin_id = NEW.storage_bin_id
        AND stock_type     = 'unrestricted';
    END IF;
  ELSE
    -- Same bin (or only one operation side has a bin)
    IF TG_OP IN ('INSERT', 'UPDATE') AND NEW.storage_bin_id IS NOT NULL THEN
      v_parts_id := NEW.parts_id;
      v_bin_id   := NEW.storage_bin_id;
    ELSIF TG_OP = 'DELETE' AND OLD.storage_bin_id IS NOT NULL THEN
      v_parts_id := OLD.parts_id;
      v_bin_id   := OLD.storage_bin_id;
    ELSE
      -- No bin specified; cannot update quants
      IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END IF;

    UPDATE wms.quants
    SET reserved_qty = GREATEST(reserved_qty + v_delta, 0),
        updated_at   = NOW()
    WHERE parts_id       = v_parts_id
      AND storage_bin_id = v_bin_id
      AND stock_type     = 'unrestricted';
  END IF;

  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION wms.fn_update_reserved_qty IS 'Trigger fn: sync wms.quants.reserved_qty with mm.reservations open quantity changes';


-- ---------------------------------------------------------------------------
-- 2. Create the trigger on mm.reservations
-- ---------------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_reservation_update_reserved ON mm.reservations;

CREATE TRIGGER trg_reservation_update_reserved
  AFTER INSERT OR UPDATE OR DELETE ON mm.reservations
  FOR EACH ROW
  EXECUTE FUNCTION wms.fn_update_reserved_qty();

COMMENT ON TRIGGER trg_reservation_update_reserved ON mm.reservations
  IS 'Auto-sync wms.quants.reserved_qty when reservations are created, modified, or deleted';


-- ################################################################
-- ## 016_triggers_finance.sql
-- ################################################################

-- ============================================================================
-- Migration 016: Triggers — Finance (운영이벤트 -> 전표 자동생성, GL 동적 결정)
--
-- Automatic accounting entry generation from SCM operational events:
--   1. Goods Receipt   -> DR: 재고자산 / CR: 매입채무   (from material_type GL)
--   2. Stock Movement   -> Assembly Issue (261), Assembly Receipt (262),
--                          Goods Issue (601)
--   3. Freight Order    -> DR: 운반비(831000) / CR: 미지급금(253000)
--   4. Inventory Adj.   -> Surplus: DR 재고자산 / CR 잡이익(909000)
--                          Shortage: DR 잡손실(909100) / CR 재고자산
--
-- FIX-4: GL accounts are dynamically resolved from shared.material_types
--        (default_debit_gl_id, default_credit_gl_id, issue_debit_gl_id,
--         issue_credit_gl_id) instead of being hardcoded.
--
-- Dependencies:
--   002_shared_reference_data.sql (shared.gl_accounts, shared.material_types)
--   004_shared_material_master.sql (shared.parts_master)
--   006_tms_schema.sql            (tms.freight_orders)
--   007_wms_schema.sql            (wms.inventory_count_items)
--   008_mm_schema.sql             (mm.goods_receipts, mm.stock_movements)
--   011_finance_schema.sql        (finance.accounting_entries, finance.cost_settings)
-- ============================================================================


-- =========================================================================
-- HELPER FUNCTIONS
-- =========================================================================

-- ---------------------------------------------------------------------------
-- Helper 1: Entry number generator
-- Format: AE-YYYYMMDD-NNNN (sequential per day)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION finance.generate_entry_number()
RETURNS TEXT AS $$
DECLARE
  v_date TEXT := TO_CHAR(CURRENT_DATE, 'YYYYMMDD');
  v_seq  INT;
BEGIN
  -- I4 FIX: Advisory lock prevents race condition on concurrent entry_number generation
  PERFORM pg_advisory_xact_lock(hashtext('ae_entry_number_' || v_date));

  SELECT COALESCE(MAX(CAST(SPLIT_PART(entry_number, '-', 3) AS INT)), 0) + 1
  INTO v_seq
  FROM finance.accounting_entries
  WHERE entry_number LIKE 'AE-' || v_date || '-%';

  RETURN 'AE-' || v_date || '-' || LPAD(v_seq::TEXT, 4, '0');
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION finance.generate_entry_number IS 'Generate sequential accounting entry number: AE-YYYYMMDD-NNNN';


-- ---------------------------------------------------------------------------
-- Helper 2: GL account lookup by account_code
-- Raises exception if account not found.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION finance.get_gl_account_id(p_code TEXT)
RETURNS UUID AS $$
DECLARE
  v_id UUID;
BEGIN
  SELECT id INTO v_id
  FROM shared.gl_accounts
  WHERE account_code = p_code
  LIMIT 1;

  IF v_id IS NULL THEN
    RAISE EXCEPTION 'GL account % not found', p_code;
  END IF;

  RETURN v_id;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION finance.get_gl_account_id IS 'Lookup shared.gl_accounts.id by account_code; raises exception if not found';


-- ---------------------------------------------------------------------------
-- Helper 3: Get GL accounts from material_type (FIX-4: dynamic GL lookup)
-- p_direction: 'receipt' -> default_debit/credit_gl_id
--              'issue'   -> issue_debit/credit_gl_id
-- Falls back to 146000 (원재료) / 251000 (매입채무) if no material_type found.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION finance.get_material_gl_accounts(
  p_parts_id  UUID,
  p_direction VARCHAR  -- 'receipt' or 'issue'
)
RETURNS TABLE(debit_gl_id UUID, credit_gl_id UUID) AS $$
BEGIN
  IF p_direction = 'receipt' THEN
    RETURN QUERY
    SELECT mt.default_debit_gl_id, mt.default_credit_gl_id
    FROM shared.parts_master pm
    JOIN shared.material_types mt ON mt.id = pm.material_type_id
    WHERE pm.id = p_parts_id;
  ELSIF p_direction = 'issue' THEN
    RETURN QUERY
    SELECT mt.issue_debit_gl_id, mt.issue_credit_gl_id
    FROM shared.parts_master pm
    JOIN shared.material_types mt ON mt.id = pm.material_type_id
    WHERE pm.id = p_parts_id;
  END IF;

  -- Fallback if no material_type mapping found
  IF NOT FOUND THEN
    RETURN QUERY
    SELECT finance.get_gl_account_id('146000'),
           finance.get_gl_account_id('251000');
  END IF;
END;
$$ LANGUAGE plpgsql STABLE;

COMMENT ON FUNCTION finance.get_material_gl_accounts IS 'Dynamic GL account resolution from material_type (FIX-4). Fallback: 146000/251000';


-- =========================================================================
-- TRIGGER 1: Goods Receipt -> Accounting Entry
-- =========================================================================

-- ---------------------------------------------------------------------------
-- finance.trg_goods_receipt_entry()
-- AFTER INSERT on mm.goods_receipts
-- DR: 재고자산 (from material_type.default_debit_gl_id)
-- CR: 매입채무 (from material_type.default_credit_gl_id)
--
-- I5 NOTE: This trigger fires on EVERY INSERT unconditionally.
-- This is INTENTIONAL — all goods receipts immediately generate a 'draft'
-- accounting entry. The entry must be reviewed/posted via the workflow
-- (draft → reviewed → posted). Invalid GRs can be corrected by creating
-- a reversal entry (is_reversal = TRUE) rather than deleting.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION finance.trg_goods_receipt_entry()
RETURNS TRIGGER AS $$
DECLARE
  v_dr      UUID;
  v_cr      UUID;
  v_costing TEXT;
  v_amount  NUMERIC(15,2);
BEGIN
  -- Get GL accounts from material_type (FIX-4: dynamic lookup)
  SELECT debit_gl_id, credit_gl_id INTO v_dr, v_cr
  FROM finance.get_material_gl_accounts(NEW.parts_id, 'receipt');

  -- Get costing method from cost_settings (per parts_type)
  SELECT cs.costing_method INTO v_costing
  FROM finance.cost_settings cs
  JOIN shared.parts_master pm ON pm.parts_type = cs.parts_type
  WHERE pm.id = NEW.parts_id
    AND cs.effective_to IS NULL
  LIMIT 1;

  -- Calculate amount (must be > 0 per CHECK constraint)
  v_amount := COALESCE(NEW.total_cost, 0);
  IF v_amount <= 0 THEN
    -- Cannot create entry with zero/negative amount; skip silently
    RETURN NEW;
  END IF;

  INSERT INTO finance.accounting_entries (
    entry_number, entry_date, entry_type,
    source_table, source_id,
    debit_account_id, credit_account_id, amount,
    quantity, unit_cost, costing_method,
    tax_invoice_no, vat_amount,
    fiscal_year, fiscal_period,
    status
  ) VALUES (
    finance.generate_entry_number(),
    COALESCE(NEW.posting_date, NEW.actual_receipt_date, CURRENT_DATE),
    'goods_receipt',
    'mm.goods_receipts', NEW.id,
    v_dr, v_cr, v_amount,
    NEW.received_qty,
    NEW.unit_cost,
    COALESCE(v_costing, 'weighted_avg'),
    NEW.tax_invoice_no, NEW.vat_amount,
    TO_CHAR(COALESCE(NEW.posting_date, CURRENT_DATE), 'YYYY'),
    TO_CHAR(COALESCE(NEW.posting_date, CURRENT_DATE), 'MM'),
    'draft'
  );

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION finance.trg_goods_receipt_entry IS 'Auto-generate accounting entry on goods receipt (dynamic GL from material_type)';

DROP TRIGGER IF EXISTS trg_goods_receipt_accounting ON mm.goods_receipts;

CREATE TRIGGER trg_goods_receipt_accounting
  AFTER INSERT ON mm.goods_receipts
  FOR EACH ROW
  EXECUTE FUNCTION finance.trg_goods_receipt_entry();

COMMENT ON TRIGGER trg_goods_receipt_accounting ON mm.goods_receipts
  IS 'Auto-create draft accounting entry when a goods receipt is recorded';


-- =========================================================================
-- TRIGGER 2: Stock Movement -> Accounting Entry (selective movement types)
-- =========================================================================

-- ---------------------------------------------------------------------------
-- finance.trg_stock_movement_entry()
-- AFTER INSERT OR UPDATE OF status on mm.stock_movements
-- Only fires for specific movement types when status = 'completed':
--   261: Assembly Issue   -> DR: 재공품(WIP 147000)   / CR: 원재료 (from issue GL)
--   262: Assembly Receipt -> DR: 제품(150000)          / CR: 재공품(147000)
--   601: Goods Issue      -> DR: 매출원가 (from issue GL) / CR: 재고자산 (from issue GL)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION finance.trg_stock_movement_entry()
RETURNS TRIGGER AS $$
DECLARE
  v_dr         UUID;
  v_cr         UUID;
  v_entry_type VARCHAR(30);
  v_amount     NUMERIC(15,2);
BEGIN
  -- Only process completed movements
  IF NEW.status <> 'completed' THEN
    RETURN NEW;
  END IF;

  -- -----------------------------------------------------------------------
  -- Determine GL accounts and entry type by movement type
  -- -----------------------------------------------------------------------
  IF NEW.movement_type = '261' THEN
    -- Assembly Issue: DR 재공품(WIP) / CR 원재료 (from material_type issue GL)
    SELECT mt.issue_debit_gl_id, mt.issue_credit_gl_id INTO v_dr, v_cr
    FROM shared.parts_master pm
    JOIN shared.material_types mt ON mt.id = pm.material_type_id
    WHERE pm.id = NEW.parts_id;

    -- Override debit: assembly issue goes to WIP (147000), not COGS
    v_dr := COALESCE(
      (SELECT id FROM shared.gl_accounts WHERE account_code = '147000'),
      v_dr
    );
    v_entry_type := 'assembly_issue';

  ELSIF NEW.movement_type = '262' THEN
    -- Assembly Receipt: DR 제품(150000) / CR 재공품(WIP 147000)
    v_dr := (SELECT id FROM shared.gl_accounts WHERE account_code = '150000');
    v_cr := (SELECT id FROM shared.gl_accounts WHERE account_code = '147000');
    v_entry_type := 'assembly_receipt';

  ELSIF NEW.movement_type = '601' THEN
    -- Goods Issue (Customer Delivery): DR 매출원가 / CR 재고자산 (from material_type)
    SELECT debit_gl_id, credit_gl_id INTO v_dr, v_cr
    FROM finance.get_material_gl_accounts(NEW.parts_id, 'issue');
    v_entry_type := 'goods_issue';

  ELSE
    -- No accounting entry for other movement types
    RETURN NEW;
  END IF;

  -- Guard: both accounts must be resolved
  IF v_dr IS NULL OR v_cr IS NULL THEN
    -- Cannot determine GL accounts; skip entry (avoid blocking the movement)
    RAISE WARNING 'finance.trg_stock_movement_entry: GL accounts not resolved for movement % (type=%, parts_id=%). Skipping entry.',
      NEW.movement_number, NEW.movement_type, NEW.parts_id;
    RETURN NEW;
  END IF;

  -- Calculate amount
  v_amount := COALESCE(NEW.total_cost, 0);
  IF v_amount <= 0 THEN
    RETURN NEW;
  END IF;

  INSERT INTO finance.accounting_entries (
    entry_number, entry_date, entry_type,
    source_table, source_id,
    debit_account_id, credit_account_id, amount,
    quantity, unit_cost, costing_method,
    fiscal_year, fiscal_period,
    status
  ) VALUES (
    finance.generate_entry_number(),
    COALESCE(NEW.posting_date, NEW.actual_date, CURRENT_DATE),
    v_entry_type,
    'mm.stock_movements', NEW.id,
    v_dr, v_cr, v_amount,
    NEW.actual_qty,
    NEW.unit_cost_at_movement,
    'weighted_avg',
    TO_CHAR(COALESCE(NEW.posting_date, CURRENT_DATE), 'YYYY'),
    TO_CHAR(COALESCE(NEW.posting_date, CURRENT_DATE), 'MM'),
    'draft'
  );

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION finance.trg_stock_movement_entry IS 'Auto-generate accounting entry for assembly issue(261), assembly receipt(262), goods issue(601)';

DROP TRIGGER IF EXISTS trg_stock_movement_accounting ON mm.stock_movements;

CREATE TRIGGER trg_stock_movement_accounting
  AFTER INSERT OR UPDATE OF status ON mm.stock_movements
  FOR EACH ROW
  WHEN (NEW.status = 'completed')
  EXECUTE FUNCTION finance.trg_stock_movement_entry();

COMMENT ON TRIGGER trg_stock_movement_accounting ON mm.stock_movements
  IS 'Auto-create draft accounting entry when specific movement types are completed (261, 262, 601)';


-- =========================================================================
-- TRIGGER 3: Freight Order Billing -> Accounting Entry
-- =========================================================================

-- ---------------------------------------------------------------------------
-- finance.trg_freight_order_billing_entry()
-- AFTER UPDATE OF billing_status on tms.freight_orders
-- When billing_status changes to 'billed':
--   DR: 운반비 (831000) / CR: 미지급금 (253000)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION finance.trg_freight_order_billing_entry()
RETURNS TRIGGER AS $$
DECLARE
  v_dr     UUID;
  v_cr     UUID;
  v_amount NUMERIC(15,2);
BEGIN
  -- Only fire when billing_status transitions TO 'billed'
  IF NEW.billing_status <> 'billed' THEN
    RETURN NEW;
  END IF;
  IF OLD.billing_status = 'billed' THEN
    -- Already billed; no duplicate entry
    RETURN NEW;
  END IF;

  -- DR: 운반비 (Freight Expense)
  v_dr := finance.get_gl_account_id('831000');
  -- CR: 미지급금 (Accounts Payable - Freight)
  v_cr := finance.get_gl_account_id('253000');

  -- Amount = freight_cost (carrier cost to us)
  v_amount := COALESCE(NEW.freight_cost, 0);
  IF v_amount <= 0 THEN
    RETURN NEW;
  END IF;

  INSERT INTO finance.accounting_entries (
    entry_number, entry_date, entry_type,
    source_table, source_id,
    debit_account_id, credit_account_id, amount,
    tax_invoice_no,
    fiscal_year, fiscal_period,
    status
  ) VALUES (
    finance.generate_entry_number(),
    COALESCE(NEW.confirmed_shipment_date, NEW.planned_shipment_date, CURRENT_DATE),
    'freight',
    'tms.freight_orders', NEW.id,
    v_dr, v_cr, v_amount,
    NEW.tax_invoice_no,
    TO_CHAR(COALESCE(NEW.confirmed_shipment_date, CURRENT_DATE), 'YYYY'),
    TO_CHAR(COALESCE(NEW.confirmed_shipment_date, CURRENT_DATE), 'MM'),
    'draft'
  );

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION finance.trg_freight_order_billing_entry IS 'Auto-generate freight expense entry when freight order is billed: DR 운반비(831000) / CR 미지급금(253000)';

DROP TRIGGER IF EXISTS trg_freight_order_billing_accounting ON tms.freight_orders;

CREATE TRIGGER trg_freight_order_billing_accounting
  AFTER UPDATE OF billing_status ON tms.freight_orders
  FOR EACH ROW
  WHEN (NEW.billing_status = 'billed')
  EXECUTE FUNCTION finance.trg_freight_order_billing_entry();

COMMENT ON TRIGGER trg_freight_order_billing_accounting ON tms.freight_orders
  IS 'Auto-create draft freight expense entry when billing_status changes to billed';


-- =========================================================================
-- TRIGGER 4: Inventory Count Adjustment -> Accounting Entry
-- =========================================================================

-- ---------------------------------------------------------------------------
-- finance.trg_inventory_adjustment_entry()
-- AFTER UPDATE OF adjustment_approved on wms.inventory_count_items
-- When adjustment_approved changes to TRUE and difference <> 0:
--   Surplus (difference > 0): DR 재고자산 (from material_type) / CR 잡이익 (909000)
--   Shortage (difference < 0): DR 잡손실 (909100) / CR 재고자산 (from material_type)
--
-- Cost is estimated using weighted average from recent goods receipts.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION finance.trg_inventory_adjustment_entry()
RETURNS TRIGGER AS $$
DECLARE
  v_dr         UUID;
  v_cr         UUID;
  v_inv_gl     UUID;  -- inventory asset GL from material_type
  v_unit_cost  NUMERIC(15,4);
  v_amount     NUMERIC(15,2);
  v_abs_diff   INTEGER;
  v_entry_type VARCHAR(30) := 'inventory_adjustment';
BEGIN
  -- Only fire when adjustment_approved transitions to TRUE
  IF NEW.adjustment_approved IS NOT TRUE THEN
    RETURN NEW;
  END IF;
  IF OLD.adjustment_approved IS TRUE THEN
    -- Already processed; no duplicate entry
    RETURN NEW;
  END IF;

  -- Skip zero difference
  IF COALESCE(NEW.difference, 0) = 0 THEN
    RETURN NEW;
  END IF;

  v_abs_diff := ABS(NEW.difference);

  -- Get inventory asset GL account from material_type (receipt debit = inventory asset)
  SELECT debit_gl_id INTO v_inv_gl
  FROM finance.get_material_gl_accounts(NEW.parts_id, 'receipt');

  -- Estimate unit cost using weighted average from recent goods receipts
  SELECT COALESCE(
    (SELECT SUM(gr.total_cost) / NULLIF(SUM(gr.received_qty), 0)
     FROM mm.goods_receipts gr
     WHERE gr.parts_id = NEW.parts_id
       AND gr.total_cost IS NOT NULL
       AND gr.total_cost > 0
       AND gr.actual_receipt_date >= (CURRENT_DATE - INTERVAL '12 months')
    ),
    0
  ) INTO v_unit_cost;

  v_amount := ROUND(v_abs_diff * v_unit_cost, 2);

  -- Skip if cost cannot be determined
  IF v_amount <= 0 THEN
    RAISE WARNING 'finance.trg_inventory_adjustment_entry: Cannot determine cost for parts_id=% (difference=%). Skipping entry.',
      NEW.parts_id, NEW.difference;
    RETURN NEW;
  END IF;

  IF NEW.difference > 0 THEN
    -- Surplus (+): DR 재고자산 / CR 잡이익(909000)
    v_dr := v_inv_gl;
    v_cr := finance.get_gl_account_id('909000');
  ELSE
    -- Shortage (-): DR 잡손실(909100) / CR 재고자산
    v_dr := finance.get_gl_account_id('909100');
    v_cr := v_inv_gl;
  END IF;

  -- Guard
  IF v_dr IS NULL OR v_cr IS NULL THEN
    RAISE WARNING 'finance.trg_inventory_adjustment_entry: GL accounts not resolved for parts_id=%. Skipping.', NEW.parts_id;
    RETURN NEW;
  END IF;

  INSERT INTO finance.accounting_entries (
    entry_number, entry_date, entry_type,
    source_table, source_id,
    debit_account_id, credit_account_id, amount,
    quantity, unit_cost, costing_method,
    fiscal_year, fiscal_period,
    status
  ) VALUES (
    finance.generate_entry_number(),
    CURRENT_DATE,
    v_entry_type,
    'wms.inventory_count_items', NEW.id,
    v_dr, v_cr, v_amount,
    v_abs_diff,
    v_unit_cost,
    'weighted_avg',
    TO_CHAR(CURRENT_DATE, 'YYYY'),
    TO_CHAR(CURRENT_DATE, 'MM'),
    'draft'
  );

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION finance.trg_inventory_adjustment_entry IS 'Auto-generate inventory adjustment entry on count approval. Surplus: DR inventory/CR 잡이익. Shortage: DR 잡손실/CR inventory.';

DROP TRIGGER IF EXISTS trg_inventory_adjustment_accounting ON wms.inventory_count_items;

CREATE TRIGGER trg_inventory_adjustment_accounting
  AFTER UPDATE OF adjustment_approved ON wms.inventory_count_items
  FOR EACH ROW
  WHEN (NEW.adjustment_approved = TRUE AND COALESCE(NEW.difference, 0) <> 0)
  EXECUTE FUNCTION finance.trg_inventory_adjustment_entry();

COMMENT ON TRIGGER trg_inventory_adjustment_accounting ON wms.inventory_count_items
  IS 'Auto-create draft inventory adjustment entry when count adjustment is approved with nonzero difference';


-- ################################################################
-- ## 017_rls_policies.sql
-- ################################################################

-- ============================================================================
-- Migration 017: Row Level Security (RLS) Policies
--
-- SCM 시스템 전체 테이블에 대한 RLS 정책 설정
-- 6개 schema, ~51개 테이블 중 주요 운영 테이블 대상
--
-- Strategy:
--   1. Enable RLS on main operational tables (NOT reference/config tables)
--   2. Authenticated users get SELECT on all data
--   3. Write policies are role-based (future: custom_access_token_hook)
--   4. Finance tables have restricted write (finance team only)
--
-- Excluded from RLS (reference/config — globally readable, admin-writable):
--   shared: organizations, users, gl_accounts, material_types,
--           material_groups, units_of_measure, locations
--   tms:    carriers, dispatch_schedules, packaging_materials, routes
--   wms:    warehouses, storage_types, storage_bins, batches
--   pp:     bom_headers, bom_items, work_centers, routings
--   finance: cost_settings
--
-- NOTE: Retool service account connects as authenticated user.
--       Service role (supabase admin) bypasses RLS entirely.
--
-- Dependencies:
--   001_create_schemas.sql
--   002–011 (all table-creation migrations)
-- ============================================================================


-- ============================================================================
-- SECTION 1: ENABLE ROW LEVEL SECURITY
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1a. shared schema
-- ---------------------------------------------------------------------------
ALTER TABLE shared.projects            ENABLE ROW LEVEL SECURITY;
ALTER TABLE shared.clients             ENABLE ROW LEVEL SECURITY;
ALTER TABLE shared.vendors             ENABLE ROW LEVEL SECURITY;
ALTER TABLE shared.goods_master        ENABLE ROW LEVEL SECURITY;
ALTER TABLE shared.item_master         ENABLE ROW LEVEL SECURITY;
ALTER TABLE shared.parts_master        ENABLE ROW LEVEL SECURITY;
ALTER TABLE shared.material_valuation  ENABLE ROW LEVEL SECURITY;
ALTER TABLE shared.vendor_evaluations  ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 1b. tms schema
-- ---------------------------------------------------------------------------
ALTER TABLE tms.transportation_requirements  ENABLE ROW LEVEL SECURITY;
ALTER TABLE tms.freight_orders               ENABLE ROW LEVEL SECURITY;
ALTER TABLE tms.logistics_releases           ENABLE ROW LEVEL SECURITY;
ALTER TABLE tms.logistics_release_items      ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 1c. wms schema
-- ---------------------------------------------------------------------------
ALTER TABLE wms.quants                ENABLE ROW LEVEL SECURITY;
ALTER TABLE wms.inventory_count_docs  ENABLE ROW LEVEL SECURITY;
ALTER TABLE wms.inventory_count_items ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 1d. mm schema
-- ---------------------------------------------------------------------------
ALTER TABLE mm.purchase_requisitions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE mm.purchase_orders        ENABLE ROW LEVEL SECURITY;
ALTER TABLE mm.purchase_order_items   ENABLE ROW LEVEL SECURITY;
ALTER TABLE mm.goods_receipts         ENABLE ROW LEVEL SECURITY;
ALTER TABLE mm.stock_movements        ENABLE ROW LEVEL SECURITY;
ALTER TABLE mm.invoice_verifications  ENABLE ROW LEVEL SECURITY;
ALTER TABLE mm.reservations           ENABLE ROW LEVEL SECURITY;
ALTER TABLE mm.return_orders          ENABLE ROW LEVEL SECURITY;
ALTER TABLE mm.quality_inspections    ENABLE ROW LEVEL SECURITY;
ALTER TABLE mm.scrap_records          ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 1e. pp schema
-- ---------------------------------------------------------------------------
ALTER TABLE pp.production_orders            ENABLE ROW LEVEL SECURITY;
ALTER TABLE pp.production_order_components  ENABLE ROW LEVEL SECURITY;
ALTER TABLE pp.production_confirmations     ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 1f. finance schema
-- ---------------------------------------------------------------------------
ALTER TABLE finance.accounting_entries  ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.douzone_sync_log   ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.period_closes      ENABLE ROW LEVEL SECURITY;


-- ============================================================================
-- SECTION 2: SELECT POLICIES — Authenticated read access on all RLS tables
-- ============================================================================
-- All authenticated users (including Retool service account) can read all data.
-- auth.role() returns 'authenticated' for any logged-in user in Supabase.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 2a. shared schema — SELECT
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_read_projects"
    ON shared.projects FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_clients"
    ON shared.clients FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_vendors"
    ON shared.vendors FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_goods_master"
    ON shared.goods_master FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_item_master"
    ON shared.item_master FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_parts_master"
    ON shared.parts_master FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_material_valuation"
    ON shared.material_valuation FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_vendor_evaluations"
    ON shared.vendor_evaluations FOR SELECT
    USING (auth.role() = 'authenticated');

-- ---------------------------------------------------------------------------
-- 2b. tms schema — SELECT
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_read_transportation_requirements"
    ON tms.transportation_requirements FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_freight_orders"
    ON tms.freight_orders FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_logistics_releases"
    ON tms.logistics_releases FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_logistics_release_items"
    ON tms.logistics_release_items FOR SELECT
    USING (auth.role() = 'authenticated');

-- ---------------------------------------------------------------------------
-- 2c. wms schema — SELECT
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_read_quants"
    ON wms.quants FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_inventory_count_docs"
    ON wms.inventory_count_docs FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_inventory_count_items"
    ON wms.inventory_count_items FOR SELECT
    USING (auth.role() = 'authenticated');

-- ---------------------------------------------------------------------------
-- 2d. mm schema — SELECT
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_read_purchase_requisitions"
    ON mm.purchase_requisitions FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_purchase_orders"
    ON mm.purchase_orders FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_purchase_order_items"
    ON mm.purchase_order_items FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_goods_receipts"
    ON mm.goods_receipts FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_stock_movements"
    ON mm.stock_movements FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_invoice_verifications"
    ON mm.invoice_verifications FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_reservations"
    ON mm.reservations FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_return_orders"
    ON mm.return_orders FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_quality_inspections"
    ON mm.quality_inspections FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_scrap_records"
    ON mm.scrap_records FOR SELECT
    USING (auth.role() = 'authenticated');

-- ---------------------------------------------------------------------------
-- 2e. pp schema — SELECT
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_read_production_orders"
    ON pp.production_orders FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_production_order_components"
    ON pp.production_order_components FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_production_confirmations"
    ON pp.production_confirmations FOR SELECT
    USING (auth.role() = 'authenticated');

-- ---------------------------------------------------------------------------
-- 2f. finance schema — SELECT
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_read_accounting_entries"
    ON finance.accounting_entries FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_douzone_sync_log"
    ON finance.douzone_sync_log FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_period_closes"
    ON finance.period_closes FOR SELECT
    USING (auth.role() = 'authenticated');


-- ============================================================================
-- SECTION 3: WRITE POLICIES — Operational tables (non-finance)
-- ============================================================================
-- All authenticated users can INSERT/UPDATE/DELETE on operational tables.
-- Future: replace with role-based checks via custom_access_token_hook
--         e.g., (auth.jwt() ->> 'user_role') IN ('scm_admin', 'mm_manager')
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 3a. shared schema — INSERT / UPDATE / DELETE
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_insert_projects"
    ON shared.projects FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_projects"
    ON shared.projects FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_projects"
    ON shared.projects FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_clients"
    ON shared.clients FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_clients"
    ON shared.clients FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_clients"
    ON shared.clients FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_vendors"
    ON shared.vendors FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_vendors"
    ON shared.vendors FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_vendors"
    ON shared.vendors FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_goods_master"
    ON shared.goods_master FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_goods_master"
    ON shared.goods_master FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_goods_master"
    ON shared.goods_master FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_item_master"
    ON shared.item_master FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_item_master"
    ON shared.item_master FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_item_master"
    ON shared.item_master FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_parts_master"
    ON shared.parts_master FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_parts_master"
    ON shared.parts_master FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_parts_master"
    ON shared.parts_master FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_material_valuation"
    ON shared.material_valuation FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_material_valuation"
    ON shared.material_valuation FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_material_valuation"
    ON shared.material_valuation FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_vendor_evaluations"
    ON shared.vendor_evaluations FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_vendor_evaluations"
    ON shared.vendor_evaluations FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_vendor_evaluations"
    ON shared.vendor_evaluations FOR DELETE
    USING (auth.role() = 'authenticated');

-- ---------------------------------------------------------------------------
-- 3b. tms schema — INSERT / UPDATE / DELETE
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_insert_transportation_requirements"
    ON tms.transportation_requirements FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_transportation_requirements"
    ON tms.transportation_requirements FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_transportation_requirements"
    ON tms.transportation_requirements FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_freight_orders"
    ON tms.freight_orders FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_freight_orders"
    ON tms.freight_orders FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_freight_orders"
    ON tms.freight_orders FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_logistics_releases"
    ON tms.logistics_releases FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_logistics_releases"
    ON tms.logistics_releases FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_logistics_releases"
    ON tms.logistics_releases FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_logistics_release_items"
    ON tms.logistics_release_items FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_logistics_release_items"
    ON tms.logistics_release_items FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_logistics_release_items"
    ON tms.logistics_release_items FOR DELETE
    USING (auth.role() = 'authenticated');

-- ---------------------------------------------------------------------------
-- 3c. wms schema — INSERT / UPDATE / DELETE
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_insert_quants"
    ON wms.quants FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_quants"
    ON wms.quants FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_quants"
    ON wms.quants FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_inventory_count_docs"
    ON wms.inventory_count_docs FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_inventory_count_docs"
    ON wms.inventory_count_docs FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_inventory_count_docs"
    ON wms.inventory_count_docs FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_inventory_count_items"
    ON wms.inventory_count_items FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_inventory_count_items"
    ON wms.inventory_count_items FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_inventory_count_items"
    ON wms.inventory_count_items FOR DELETE
    USING (auth.role() = 'authenticated');

-- ---------------------------------------------------------------------------
-- 3d. mm schema — INSERT / UPDATE / DELETE
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_insert_purchase_requisitions"
    ON mm.purchase_requisitions FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_purchase_requisitions"
    ON mm.purchase_requisitions FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_purchase_requisitions"
    ON mm.purchase_requisitions FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_purchase_orders"
    ON mm.purchase_orders FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_purchase_orders"
    ON mm.purchase_orders FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_purchase_orders"
    ON mm.purchase_orders FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_purchase_order_items"
    ON mm.purchase_order_items FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_purchase_order_items"
    ON mm.purchase_order_items FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_purchase_order_items"
    ON mm.purchase_order_items FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_goods_receipts"
    ON mm.goods_receipts FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_goods_receipts"
    ON mm.goods_receipts FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_goods_receipts"
    ON mm.goods_receipts FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_stock_movements"
    ON mm.stock_movements FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_stock_movements"
    ON mm.stock_movements FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_stock_movements"
    ON mm.stock_movements FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_invoice_verifications"
    ON mm.invoice_verifications FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_invoice_verifications"
    ON mm.invoice_verifications FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_invoice_verifications"
    ON mm.invoice_verifications FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_reservations"
    ON mm.reservations FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_reservations"
    ON mm.reservations FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_reservations"
    ON mm.reservations FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_return_orders"
    ON mm.return_orders FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_return_orders"
    ON mm.return_orders FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_return_orders"
    ON mm.return_orders FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_quality_inspections"
    ON mm.quality_inspections FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_quality_inspections"
    ON mm.quality_inspections FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_quality_inspections"
    ON mm.quality_inspections FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_scrap_records"
    ON mm.scrap_records FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_scrap_records"
    ON mm.scrap_records FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_scrap_records"
    ON mm.scrap_records FOR DELETE
    USING (auth.role() = 'authenticated');

-- ---------------------------------------------------------------------------
-- 3e. pp schema — INSERT / UPDATE / DELETE
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_insert_production_orders"
    ON pp.production_orders FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_production_orders"
    ON pp.production_orders FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_production_orders"
    ON pp.production_orders FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_production_order_components"
    ON pp.production_order_components FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_production_order_components"
    ON pp.production_order_components FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_production_order_components"
    ON pp.production_order_components FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_production_confirmations"
    ON pp.production_confirmations FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_production_confirmations"
    ON pp.production_confirmations FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_production_confirmations"
    ON pp.production_confirmations FOR DELETE
    USING (auth.role() = 'authenticated');


-- ============================================================================
-- SECTION 4: FINANCE WRITE POLICIES — Restricted access
-- ============================================================================
-- Finance tables have tighter write controls:
--   - accounting_entries: INSERT allowed, UPDATE restricted to status transitions
--     (draft -> reviewed -> posted), DELETE not allowed
--   - douzone_sync_log: INSERT/UPDATE allowed (sync operations), DELETE not allowed
--   - period_closes: INSERT/UPDATE allowed (closing workflow), DELETE not allowed
--
-- Future: replace auth.role() checks with JWT role claims:
--   (auth.jwt() ->> 'user_role') IN ('finance_manager', 'finance_admin')
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 4a. finance.accounting_entries — INSERT (draft entries only)
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_insert_accounting_entries"
    ON finance.accounting_entries FOR INSERT
    WITH CHECK (
        auth.role() = 'authenticated'
        AND status = 'draft'                      -- new entries must start as draft
    );

-- ---------------------------------------------------------------------------
-- 4b. finance.accounting_entries — UPDATE
--     NOTE: PostgreSQL RLS WITH CHECK cannot reference OLD.
--     Status transition enforcement (draft→reviewed→posted) is handled by
--     a BEFORE UPDATE trigger instead. RLS only checks authentication.
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_update_accounting_entries"
    ON finance.accounting_entries FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

-- Status transition enforcement via trigger (replaces invalid OLD in RLS)
CREATE OR REPLACE FUNCTION finance.fn_enforce_entry_status_transition()
RETURNS TRIGGER AS $$
BEGIN
  -- Allowed transitions: draft→reviewed, reviewed→posted, posted→posted (douzone_slip_no backfill)
  IF NOT (
    (OLD.status = 'draft' AND NEW.status = 'reviewed')
    OR (OLD.status = 'reviewed' AND NEW.status = 'posted')
    OR (OLD.status = 'posted' AND NEW.status = 'posted')
  ) THEN
    RAISE EXCEPTION 'Invalid status transition: % → %', OLD.status, NEW.status;
  END IF;

  -- Protect immutable fields on posted entries (only douzone_slip_no can change)
  IF OLD.status = 'posted' THEN
    IF NEW.amount <> OLD.amount
       OR NEW.debit_account_id <> OLD.debit_account_id
       OR NEW.credit_account_id <> OLD.credit_account_id
       OR NEW.entry_type <> OLD.entry_type THEN
      RAISE EXCEPTION 'Cannot modify immutable fields on posted accounting entries';
    END IF;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_enforce_entry_status ON finance.accounting_entries;
CREATE TRIGGER trg_enforce_entry_status
  BEFORE UPDATE ON finance.accounting_entries
  FOR EACH ROW
  EXECUTE FUNCTION finance.fn_enforce_entry_status_transition();

-- NOTE: No DELETE policy on accounting_entries — posted entries must never be deleted.
-- Use reversal entries (is_reversal = TRUE) instead.

-- ---------------------------------------------------------------------------
-- 4c. finance.douzone_sync_log — INSERT / UPDATE (sync operations)
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_insert_douzone_sync_log"
    ON finance.douzone_sync_log FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_douzone_sync_log"
    ON finance.douzone_sync_log FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

-- NOTE: No DELETE policy on douzone_sync_log — audit trail must be preserved.

-- ---------------------------------------------------------------------------
-- 4d. finance.period_closes — INSERT / UPDATE (closing workflow)
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_insert_period_closes"
    ON finance.period_closes FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

-- UPDATE only allowed when period is NOT yet closed
-- Once is_closed = TRUE, the record becomes immutable
CREATE POLICY "authenticated_update_period_closes"
    ON finance.period_closes FOR UPDATE
    USING (
        auth.role() = 'authenticated'
        AND is_closed = FALSE                     -- cannot modify closed periods
    )
    WITH CHECK (auth.role() = 'authenticated');

-- NOTE: No DELETE policy on period_closes — closing snapshots must be preserved.


-- ============================================================================
-- SECTION 5: FORCE RLS FOR TABLE OWNERS
-- ============================================================================
-- By default, table owners bypass RLS. FORCE ROW LEVEL SECURITY ensures
-- that even the table owner (postgres role) is subject to policies.
-- This is a safety net — Retool and application code should never use
-- the postgres role directly, but this prevents accidental bypass.
--
-- NOTE: Supabase service_role key still bypasses RLS regardless of this
-- setting, which is the intended behavior for admin/migration operations.
-- ============================================================================

-- shared
ALTER TABLE shared.projects            FORCE ROW LEVEL SECURITY;
ALTER TABLE shared.clients             FORCE ROW LEVEL SECURITY;
ALTER TABLE shared.vendors             FORCE ROW LEVEL SECURITY;
ALTER TABLE shared.goods_master        FORCE ROW LEVEL SECURITY;
ALTER TABLE shared.item_master         FORCE ROW LEVEL SECURITY;
ALTER TABLE shared.parts_master        FORCE ROW LEVEL SECURITY;
ALTER TABLE shared.material_valuation  FORCE ROW LEVEL SECURITY;
ALTER TABLE shared.vendor_evaluations  FORCE ROW LEVEL SECURITY;

-- tms
ALTER TABLE tms.transportation_requirements  FORCE ROW LEVEL SECURITY;
ALTER TABLE tms.freight_orders               FORCE ROW LEVEL SECURITY;
ALTER TABLE tms.logistics_releases           FORCE ROW LEVEL SECURITY;
ALTER TABLE tms.logistics_release_items      FORCE ROW LEVEL SECURITY;

-- wms
ALTER TABLE wms.quants                FORCE ROW LEVEL SECURITY;
ALTER TABLE wms.inventory_count_docs  FORCE ROW LEVEL SECURITY;
ALTER TABLE wms.inventory_count_items FORCE ROW LEVEL SECURITY;

-- mm
ALTER TABLE mm.purchase_requisitions  FORCE ROW LEVEL SECURITY;
ALTER TABLE mm.purchase_orders        FORCE ROW LEVEL SECURITY;
ALTER TABLE mm.purchase_order_items   FORCE ROW LEVEL SECURITY;
ALTER TABLE mm.goods_receipts         FORCE ROW LEVEL SECURITY;
ALTER TABLE mm.stock_movements        FORCE ROW LEVEL SECURITY;
ALTER TABLE mm.invoice_verifications  FORCE ROW LEVEL SECURITY;
ALTER TABLE mm.reservations           FORCE ROW LEVEL SECURITY;
ALTER TABLE mm.return_orders          FORCE ROW LEVEL SECURITY;
ALTER TABLE mm.quality_inspections    FORCE ROW LEVEL SECURITY;
ALTER TABLE mm.scrap_records          FORCE ROW LEVEL SECURITY;

-- pp
ALTER TABLE pp.production_orders            FORCE ROW LEVEL SECURITY;
ALTER TABLE pp.production_order_components  FORCE ROW LEVEL SECURITY;
ALTER TABLE pp.production_confirmations     FORCE ROW LEVEL SECURITY;

-- finance
ALTER TABLE finance.accounting_entries  FORCE ROW LEVEL SECURITY;
ALTER TABLE finance.douzone_sync_log   FORCE ROW LEVEL SECURITY;
ALTER TABLE finance.period_closes      FORCE ROW LEVEL SECURITY;


-- ============================================================================
-- SUMMARY
-- ============================================================================
-- Tables with RLS enabled:              31
--   shared:   8 tables
--   tms:      4 tables
--   wms:      3 tables
--   mm:      10 tables
--   pp:       3 tables
--   finance:  3 tables
--
-- Policy counts:
--   SELECT policies:                    31 (one per table, authenticated read)
--   INSERT policies:                    31 (28 general + 3 finance-specific)
--   UPDATE policies:                    31 (28 general + 3 finance-specific)
--   DELETE policies:                    28 (non-finance tables only)
--   Total policies:                    121
--
-- Finance restrictions:
--   - accounting_entries: INSERT draft only, UPDATE status transitions only, no DELETE
--   - douzone_sync_log:  INSERT/UPDATE only, no DELETE (audit trail)
--   - period_closes:     INSERT/UPDATE only (UPDATE blocked when is_closed=TRUE), no DELETE
--
-- Tables WITHOUT RLS (reference/config — admin-managed):
--   shared: organizations, users, gl_accounts, material_types,
--           material_groups, units_of_measure, locations
--   tms:    carriers, dispatch_schedules, packaging_materials, routes
--   wms:    warehouses, storage_types, storage_bins, batches
--   pp:     bom_headers, bom_items, work_centers, routings
--   finance: cost_settings
--
-- Future enhancements:
--   1. Add custom_access_token_hook to embed user_role in JWT
--   2. Replace auth.role() = 'authenticated' with role-based checks:
--      (auth.jwt() ->> 'user_role') IN ('scm_admin', 'mm_manager', ...)
--   3. Add row-level filtering (e.g., users see only their organization's data)
-- ============================================================================


-- ################################################################
-- ## 018_quick_wins_qm_otif_rop_pir.sql
-- ################################################################

-- ============================================================================
-- Migration 018: Quick Wins — QM Defect Catalog, OTIF Records, Reorder Alerts,
--                              Purchasing Info Records
-- New tables: mm.defect_catalogs, mm.inspection_defects, mm.purchasing_info_records,
--             tms.otif_records
-- New views:  mm.v_qc_defect_trend, mm.v_defect_pareto, tms.v_otif_trend,
--             shared.v_reorder_alerts, mm.v_current_prices, mm.v_parts_without_prices
-- Seed data:  21 defect codes for packaging/printing industry
-- ============================================================================

\i migrations/018_quick_wins_qm_otif_rop_pir.sql
