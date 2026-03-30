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
