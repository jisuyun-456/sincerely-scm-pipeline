-- Virtual SAP Simulation — Initial Schema
-- All tables in schema: sap
-- Immutable Ledger: INSERT-only for all transaction tables (enforced via RLS)
-- K-IFRS GL codes, SAP movement types (101/201/261/311/601/701/122/551)
-- Idempotent: safe to re-run on a project that already has partial sap.* tables

CREATE SCHEMA IF NOT EXISTS sap;

-- ─────────────────────────────────────────────────────────
-- SIMULATION BOOKKEEPING (create first — referenced by all)
-- ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sap.sim_run (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    mode            TEXT NOT NULL CHECK (mode IN ('manual','daily','backfill')),
    status          TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','ok','failed')),
    seed            BIGINT,
    git_sha         TEXT,
    summary_json    JSONB,
    orders_created  INT DEFAULT 0,
    docs_created    INT DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sap.sim_step_log (
    step_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sim_run_id      UUID NOT NULL REFERENCES sap.sim_run(id),
    step_name       TEXT NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','ok','failed','skipped')),
    verifier_result_json JSONB,
    docs_created_count INT DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sap.sim_issue (
    issue_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sim_run_id      UUID NOT NULL REFERENCES sap.sim_run(id),
    step_id         UUID REFERENCES sap.sim_step_log(step_id),
    dim             TEXT NOT NULL CHECK (dim IN ('D1','D2','D3','D4','D5')),
    severity        TEXT NOT NULL CHECK (severity IN ('ERROR','WARN','INFO')),
    entity_type     TEXT,
    entity_id       TEXT,
    msg             TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─────────────────────────────────────────────────────────
-- MASTER DATA
-- ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sap.plant (
    plant_id        TEXT PRIMARY KEY,          -- e.g. P001
    name            TEXT NOT NULL,
    address         TEXT,
    country         TEXT DEFAULT 'KR',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sap.storage_location (
    plant_id        TEXT NOT NULL REFERENCES sap.plant(plant_id),
    sloc_id         TEXT NOT NULL,             -- e.g. WH01, STG01
    name            TEXT NOT NULL,
    sloc_type       TEXT NOT NULL CHECK (sloc_type IN ('warehouse','staging','production','quarantine')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (plant_id, sloc_id)
);

CREATE TABLE IF NOT EXISTS sap.material (
    material_id     TEXT PRIMARY KEY,          -- e.g. MAT-0001
    name            TEXT NOT NULL,
    material_group  TEXT NOT NULL,             -- carton / label / tote / packaging
    uom             TEXT NOT NULL DEFAULT 'EA',
    unit_weight_kg  NUMERIC(10,4) DEFAULT 0,
    unit_cbm        NUMERIC(10,6) DEFAULT 0,
    std_price       NUMERIC(14,2) DEFAULT 0,   -- KRW
    valuation_class TEXT NOT NULL DEFAULT '3000', -- SAP valuation class
    reorder_point   NUMERIC(10,2) DEFAULT 100,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sap.business_partner (
    bp_id           TEXT PRIMARY KEY,          -- C-0001 (customer) / V-0001 (vendor) / CA-0001 (carrier)
    name            TEXT NOT NULL,
    bp_type         TEXT NOT NULL CHECK (bp_type IN ('customer','vendor','carrier','internal')),
    address         TEXT,
    region          TEXT,                      -- 서울/경기/부산/etc
    incoterms       TEXT DEFAULT 'DAP',
    payment_terms   TEXT DEFAULT 'NET30',
    contact_email   TEXT,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sap.gl_account (
    gl_code         TEXT PRIMARY KEY,          -- K-IFRS / 더존 코드 e.g. 1110
    name            TEXT NOT NULL,
    account_type    TEXT NOT NULL CHECK (account_type IN ('asset','liability','equity','revenue','expense')),
    is_inventory    BOOLEAN DEFAULT FALSE,
    normal_balance  TEXT NOT NULL CHECK (normal_balance IN ('D','C')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Document number counter (for SAP-style sequential numbering)
CREATE TABLE IF NOT EXISTS sap.doc_counter (
    prefix          TEXT NOT NULL,             -- SO / PO / GR / DLV / SH / FI / MAT
    period          TEXT NOT NULL,             -- YYYYMM
    last_seq        INT NOT NULL DEFAULT 0,
    PRIMARY KEY (prefix, period)
);

-- ─────────────────────────────────────────────────────────
-- PROCUREMENT (Procure-to-Pay)
-- ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sap.purchase_order (
    po_id           TEXT PRIMARY KEY,          -- PO-YYYYMMDD-####
    vendor_id       TEXT NOT NULL REFERENCES sap.business_partner(bp_id),
    plant_id        TEXT NOT NULL REFERENCES sap.plant(plant_id),
    order_date      DATE NOT NULL,
    expected_delivery_date DATE,
    status          TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','partially_received','closed','cancelled')),
    sim_run_id      UUID REFERENCES sap.sim_run(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sap.purchase_order_item (
    po_id           TEXT NOT NULL REFERENCES sap.purchase_order(po_id),
    item_no         INT NOT NULL,
    material_id     TEXT NOT NULL REFERENCES sap.material(material_id),
    ordered_qty     NUMERIC(14,3) NOT NULL CHECK (ordered_qty > 0),
    received_qty    NUMERIC(14,3) NOT NULL DEFAULT 0,
    uom             TEXT NOT NULL DEFAULT 'EA',
    net_price       NUMERIC(14,2) NOT NULL DEFAULT 0,
    PRIMARY KEY (po_id, item_no)
);

-- ─────────────────────────────────────────────────────────
-- WMS INBOUND (Goods Receipt + QI)
-- ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sap.gr_document (
    gr_id           TEXT PRIMARY KEY,          -- GR-YYYYMMDD-####
    po_id           TEXT NOT NULL REFERENCES sap.purchase_order(po_id),
    posting_date    DATE NOT NULL,
    vendor_id       TEXT NOT NULL REFERENCES sap.business_partner(bp_id),
    plant_id        TEXT NOT NULL REFERENCES sap.plant(plant_id),
    sloc_id         TEXT NOT NULL,
    total_items     INT NOT NULL DEFAULT 0,
    sim_run_id      UUID REFERENCES sap.sim_run(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sap.qi_inspection (
    qi_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    gr_id           TEXT NOT NULL REFERENCES sap.gr_document(gr_id),
    material_id     TEXT NOT NULL REFERENCES sap.material(material_id),
    inspected_qty   NUMERIC(14,3) NOT NULL,
    aql_sample_size INT NOT NULL DEFAULT 0,
    aql_accepted_qty NUMERIC(14,3) NOT NULL DEFAULT 0,
    aql_rejected_qty NUMERIC(14,3) NOT NULL DEFAULT 0,
    disposition     TEXT NOT NULL DEFAULT 'release' CHECK (disposition IN ('release','block','scrap')),
    -- release → movement 101, scrap → movement 551
    inspector_note  TEXT,
    sim_run_id      UUID REFERENCES sap.sim_run(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ─────────────────────────────────────────────────────────
-- INVENTORY (Material Document = SAP MKPF/MSEG equivalent)
-- ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sap.mat_document (
    mat_doc_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_number      TEXT UNIQUE NOT NULL,      -- MAT-YYYYMMDD-####
    posting_date    DATE NOT NULL,
    movement_type   TEXT NOT NULL CHECK (movement_type IN ('101','201','261','311','601','701','122','551')),
    -- 101=입고 102=입고취소 201=출고 261=생산출고 311=이전 601=납품 701=조정 122=반품입고 551=폐기
    is_reversal     BOOLEAN NOT NULL DEFAULT FALSE,
    reverses_doc_id UUID REFERENCES sap.mat_document(mat_doc_id),
    source_doc_type TEXT CHECK (source_doc_type IN ('PO','SO','PROD','ADJ','TRANSFER',NULL)),
    source_doc_id   TEXT,
    sim_run_id      UUID REFERENCES sap.sim_run(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sap.mat_document_item (
    mat_doc_id      UUID NOT NULL REFERENCES sap.mat_document(mat_doc_id),
    item_no         INT NOT NULL,
    material_id     TEXT NOT NULL REFERENCES sap.material(material_id),
    plant_id        TEXT NOT NULL REFERENCES sap.plant(plant_id),
    sloc_id         TEXT NOT NULL,
    batch           TEXT,
    qty_signed      NUMERIC(14,3) NOT NULL,    -- + = receipt, - = issue
    uom             TEXT NOT NULL DEFAULT 'EA',
    value_local     NUMERIC(14,2) NOT NULL DEFAULT 0,  -- KRW
    PRIMARY KEY (mat_doc_id, item_no)
);

-- Materialized inventory snapshot (rebuilt each daily tick)
CREATE TABLE IF NOT EXISTS sap.inventory_snapshot (
    material_id     TEXT NOT NULL REFERENCES sap.material(material_id),
    plant_id        TEXT NOT NULL REFERENCES sap.plant(plant_id),
    sloc_id         TEXT NOT NULL,
    batch           TEXT NOT NULL DEFAULT '',
    as_of_date      DATE NOT NULL,
    qty_on_hand     NUMERIC(14,3) NOT NULL DEFAULT 0,
    qty_blocked     NUMERIC(14,3) NOT NULL DEFAULT 0,
    value_local     NUMERIC(14,2) NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (material_id, plant_id, sloc_id, batch, as_of_date)
);

-- ─────────────────────────────────────────────────────────
-- SALES ORDER (Order-to-Cash)
-- ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sap.sales_order (
    so_id           TEXT PRIMARY KEY,          -- SO-YYYYMMDD-####
    customer_id     TEXT NOT NULL REFERENCES sap.business_partner(bp_id),
    order_date      DATE NOT NULL,
    requested_delivery_date DATE,
    plant_id        TEXT NOT NULL REFERENCES sap.plant(plant_id),
    status          TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','picking','shipped','closed','cancelled')),
    total_value     NUMERIC(14,2) NOT NULL DEFAULT 0,
    sim_run_id      UUID REFERENCES sap.sim_run(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Status event log (keeps SO header immutable while tracking transitions)
CREATE TABLE IF NOT EXISTS sap.sales_order_status_event (
    event_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    so_id           TEXT NOT NULL REFERENCES sap.sales_order(so_id),
    from_status     TEXT,
    to_status       TEXT NOT NULL,
    event_ts        TIMESTAMPTZ NOT NULL DEFAULT now(),
    sim_run_id      UUID REFERENCES sap.sim_run(id)
);

CREATE TABLE IF NOT EXISTS sap.sales_order_item (
    so_id           TEXT NOT NULL REFERENCES sap.sales_order(so_id),
    item_no         INT NOT NULL,
    material_id     TEXT NOT NULL REFERENCES sap.material(material_id),
    ordered_qty     NUMERIC(14,3) NOT NULL CHECK (ordered_qty > 0),
    confirmed_qty   NUMERIC(14,3),
    uom             TEXT NOT NULL DEFAULT 'EA',
    net_price       NUMERIC(14,2) NOT NULL DEFAULT 0,
    PRIMARY KEY (so_id, item_no)
);

-- ─────────────────────────────────────────────────────────
-- WMS OUTBOUND
-- ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sap.outbound_delivery (
    dlv_id          TEXT PRIMARY KEY,          -- DLV-YYYYMMDD-####
    so_id           TEXT NOT NULL REFERENCES sap.sales_order(so_id),
    plant_id        TEXT NOT NULL REFERENCES sap.plant(plant_id),
    picking_status  TEXT NOT NULL DEFAULT 'not_started' CHECK (picking_status IN ('not_started','in_progress','completed')),
    packing_status  TEXT NOT NULL DEFAULT 'not_started' CHECK (packing_status IN ('not_started','in_progress','completed')),
    goods_issue_status TEXT NOT NULL DEFAULT 'pending' CHECK (goods_issue_status IN ('pending','posted','reversed')),
    goods_issue_mat_doc_id UUID REFERENCES sap.mat_document(mat_doc_id),
    goods_issue_date DATE,
    total_cbm       NUMERIC(10,4) DEFAULT 0,
    sim_run_id      UUID REFERENCES sap.sim_run(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sap.outbound_delivery_item (
    dlv_id          TEXT NOT NULL REFERENCES sap.outbound_delivery(dlv_id),
    item_no         INT NOT NULL,
    material_id     TEXT NOT NULL REFERENCES sap.material(material_id),
    delivery_qty    NUMERIC(14,3) NOT NULL,
    picked_qty      NUMERIC(14,3) NOT NULL DEFAULT 0,
    packed_qty      NUMERIC(14,3) NOT NULL DEFAULT 0,
    uom             TEXT NOT NULL DEFAULT 'EA',
    sscc            TEXT,                      -- packing unit barcode
    PRIMARY KEY (dlv_id, item_no)
);

-- ─────────────────────────────────────────────────────────
-- TMS (Shipment / Delivery)
-- ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sap.shipment (
    ship_id         TEXT PRIMARY KEY,          -- SH-YYYYMMDD-####
    carrier_id      TEXT NOT NULL REFERENCES sap.business_partner(bp_id),
    driver_name     TEXT,
    truck_id        TEXT,
    planned_pickup  TIMESTAMPTZ,
    actual_pickup   TIMESTAMPTZ,
    actual_delivery TIMESTAMPTZ,
    pod_status      TEXT NOT NULL DEFAULT 'pending' CHECK (pod_status IN ('pending','in_transit','delivered','exception')),
    total_cbm       NUMERIC(10,4) DEFAULT 0,
    total_fare      NUMERIC(14,2) DEFAULT 0,   -- KRW
    sim_run_id      UUID REFERENCES sap.sim_run(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sap.shipment_delivery_link (
    ship_id         TEXT NOT NULL REFERENCES sap.shipment(ship_id),
    dlv_id          TEXT NOT NULL REFERENCES sap.outbound_delivery(dlv_id),
    sequence_no     INT NOT NULL DEFAULT 1,
    PRIMARY KEY (ship_id, dlv_id)
);

CREATE TABLE IF NOT EXISTS sap.shipment_event (
    event_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ship_id         TEXT NOT NULL REFERENCES sap.shipment(ship_id),
    event_ts        TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_type      TEXT NOT NULL CHECK (event_type IN ('pickup','in_transit','out_for_delivery','delivered','exception')),
    note            TEXT,
    sim_run_id      UUID REFERENCES sap.sim_run(id)
);

-- ─────────────────────────────────────────────────────────
-- FINANCIAL ACCOUNTING (FI)
-- ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sap.period_close (
    period          TEXT PRIMARY KEY,          -- YYYYMM e.g. 202605
    status          TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','in_progress','closed')),
    closed_at       TIMESTAMPTZ,
    closed_by       TEXT DEFAULT 'sim_engine',
    inventory_revaluation_doc_id TEXT
);

CREATE TABLE IF NOT EXISTS sap.fi_document (
    fi_doc_id       TEXT PRIMARY KEY,          -- FI-YYYYMMDD-####
    posting_date    DATE NOT NULL,
    doc_type        TEXT NOT NULL CHECK (doc_type IN ('RE','WE','SD','GI','ADJ','REVAL')),
    -- RE=vendor invoice, WE=goods receipt, SD=sales, GI=goods issue, ADJ=adjustment, REVAL=revaluation
    source_mat_doc_id UUID REFERENCES sap.mat_document(mat_doc_id),
    period          TEXT NOT NULL,             -- YYYYMM
    is_reversal     BOOLEAN NOT NULL DEFAULT FALSE,
    reverses_fi_doc_id TEXT REFERENCES sap.fi_document(fi_doc_id),
    description     TEXT,
    sim_run_id      UUID REFERENCES sap.sim_run(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sap.fi_document_line (
    fi_doc_id       TEXT NOT NULL REFERENCES sap.fi_document(fi_doc_id),
    line_no         INT NOT NULL,
    gl_code         TEXT NOT NULL REFERENCES sap.gl_account(gl_code),
    debit_credit    TEXT NOT NULL CHECK (debit_credit IN ('D','C')),
    amount_local    NUMERIC(14,2) NOT NULL CHECK (amount_local > 0),  -- always positive; D/C indicates direction
    cost_center     TEXT,
    partner_id      TEXT REFERENCES sap.business_partner(bp_id),
    description     TEXT,
    PRIMARY KEY (fi_doc_id, line_no)
);

-- ─────────────────────────────────────────────────────────
-- TRIGGERS
-- ─────────────────────────────────────────────────────────

-- 1. Enforce double-entry: sum of debits must equal sum of credits per fi_doc
CREATE OR REPLACE FUNCTION sap.check_double_entry()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_debit  NUMERIC;
    v_credit NUMERIC;
BEGIN
    SELECT
        COALESCE(SUM(CASE WHEN debit_credit = 'D' THEN amount_local ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN debit_credit = 'C' THEN amount_local ELSE 0 END), 0)
    INTO v_debit, v_credit
    FROM sap.fi_document_line
    WHERE fi_doc_id = NEW.fi_doc_id;

    IF v_debit <> v_credit THEN
        RAISE EXCEPTION 'Double-entry violation on fi_doc_id=%: debit=% credit=%',
            NEW.fi_doc_id, v_debit, v_credit;
    END IF;
    RETURN NEW;
END;
$$;

-- Trigger fires AFTER each INSERT to fi_document_line (deferred check)
-- We use a statement-level trigger so it checks after all lines are inserted
CREATE OR REPLACE FUNCTION sap.check_double_entry_stmt()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    rec RECORD;
BEGIN
    FOR rec IN
        SELECT fi_doc_id,
               SUM(CASE WHEN debit_credit='D' THEN amount_local ELSE 0 END) AS total_d,
               SUM(CASE WHEN debit_credit='C' THEN amount_local ELSE 0 END) AS total_c
        FROM sap.fi_document_line
        WHERE fi_doc_id IN (SELECT DISTINCT fi_doc_id FROM sap.fi_document_line)
        GROUP BY fi_doc_id
        HAVING ABS(SUM(CASE WHEN debit_credit='D' THEN amount_local ELSE 0 END) -
                   SUM(CASE WHEN debit_credit='C' THEN amount_local ELSE 0 END)) > 0.01
    LOOP
        RAISE EXCEPTION 'Double-entry violation on fi_doc_id=%: debit=% credit=%',
            rec.fi_doc_id, rec.total_d, rec.total_c;
    END LOOP;
    RETURN NULL;
END;
$$;

-- 2. Block posting into closed period
CREATE OR REPLACE FUNCTION sap.enforce_period_closed()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    v_period TEXT;
    v_status TEXT;
BEGIN
    v_period := TO_CHAR(NEW.posting_date, 'YYYYMM');
    SELECT status INTO v_status FROM sap.period_close WHERE period = v_period;
    IF v_status = 'closed' AND NEW.is_reversal = FALSE THEN
        RAISE EXCEPTION 'Period % is closed. Cannot post new document.', v_period;
    END IF;
    RETURN NEW;
END;
$$;

-- Drop triggers before recreating (CREATE TRIGGER has no IF NOT EXISTS in PG14)
DROP TRIGGER IF EXISTS trg_period_closed_fi  ON sap.fi_document;
DROP TRIGGER IF EXISTS trg_period_closed_mat ON sap.mat_document;

CREATE TRIGGER trg_period_closed_fi
    BEFORE INSERT ON sap.fi_document
    FOR EACH ROW EXECUTE FUNCTION sap.enforce_period_closed();

CREATE TRIGGER trg_period_closed_mat
    BEFORE INSERT ON sap.mat_document
    FOR EACH ROW EXECUTE FUNCTION sap.enforce_period_closed();

-- ─────────────────────────────────────────────────────────
-- ROW LEVEL SECURITY (INSERT-only for transaction tables)
-- ─────────────────────────────────────────────────────────

ALTER TABLE sap.mat_document         ENABLE ROW LEVEL SECURITY;
ALTER TABLE sap.mat_document_item    ENABLE ROW LEVEL SECURITY;
ALTER TABLE sap.fi_document          ENABLE ROW LEVEL SECURITY;
ALTER TABLE sap.fi_document_line     ENABLE ROW LEVEL SECURITY;
ALTER TABLE sap.sales_order          ENABLE ROW LEVEL SECURITY;
ALTER TABLE sap.purchase_order       ENABLE ROW LEVEL SECURITY;
ALTER TABLE sap.gr_document          ENABLE ROW LEVEL SECURITY;
ALTER TABLE sap.outbound_delivery    ENABLE ROW LEVEL SECURITY;
ALTER TABLE sap.shipment             ENABLE ROW LEVEL SECURITY;

-- Drop policies before recreating (CREATE POLICY has no IF NOT EXISTS)
DROP POLICY IF EXISTS mat_doc_select   ON sap.mat_document;
DROP POLICY IF EXISTS mat_doc_insert   ON sap.mat_document;
DROP POLICY IF EXISTS mat_doc_item_sel ON sap.mat_document_item;
DROP POLICY IF EXISTS mat_doc_item_ins ON sap.mat_document_item;
DROP POLICY IF EXISTS fi_doc_select    ON sap.fi_document;
DROP POLICY IF EXISTS fi_doc_insert    ON sap.fi_document;
DROP POLICY IF EXISTS fi_line_select   ON sap.fi_document_line;
DROP POLICY IF EXISTS fi_line_insert   ON sap.fi_document_line;
DROP POLICY IF EXISTS so_select        ON sap.sales_order;
DROP POLICY IF EXISTS so_insert        ON sap.sales_order;
DROP POLICY IF EXISTS po_select        ON sap.purchase_order;
DROP POLICY IF EXISTS po_insert        ON sap.purchase_order;
DROP POLICY IF EXISTS gr_select        ON sap.gr_document;
DROP POLICY IF EXISTS gr_insert        ON sap.gr_document;
DROP POLICY IF EXISTS dlv_select       ON sap.outbound_delivery;
DROP POLICY IF EXISTS dlv_insert       ON sap.outbound_delivery;
DROP POLICY IF EXISTS ship_select      ON sap.shipment;
DROP POLICY IF EXISTS ship_insert      ON sap.shipment;

-- Allow authenticated/service_role to SELECT and INSERT (not UPDATE or DELETE)
-- mat_document
CREATE POLICY mat_doc_select   ON sap.mat_document FOR SELECT USING (true);
CREATE POLICY mat_doc_insert   ON sap.mat_document FOR INSERT WITH CHECK (true);
CREATE POLICY mat_doc_item_sel ON sap.mat_document_item FOR SELECT USING (true);
CREATE POLICY mat_doc_item_ins ON sap.mat_document_item FOR INSERT WITH CHECK (true);
-- fi_document
CREATE POLICY fi_doc_select    ON sap.fi_document FOR SELECT USING (true);
CREATE POLICY fi_doc_insert    ON sap.fi_document FOR INSERT WITH CHECK (true);
CREATE POLICY fi_line_select   ON sap.fi_document_line FOR SELECT USING (true);
CREATE POLICY fi_line_insert   ON sap.fi_document_line FOR INSERT WITH CHECK (true);
-- sales_order
CREATE POLICY so_select ON sap.sales_order FOR SELECT USING (true);
CREATE POLICY so_insert ON sap.sales_order FOR INSERT WITH CHECK (true);
-- purchase_order
CREATE POLICY po_select ON sap.purchase_order FOR SELECT USING (true);
CREATE POLICY po_insert ON sap.purchase_order FOR INSERT WITH CHECK (true);
-- gr_document
CREATE POLICY gr_select ON sap.gr_document FOR SELECT USING (true);
CREATE POLICY gr_insert ON sap.gr_document FOR INSERT WITH CHECK (true);
-- outbound_delivery
CREATE POLICY dlv_select ON sap.outbound_delivery FOR SELECT USING (true);
CREATE POLICY dlv_insert ON sap.outbound_delivery FOR INSERT WITH CHECK (true);
-- shipment
CREATE POLICY ship_select ON sap.shipment FOR SELECT USING (true);
CREATE POLICY ship_insert ON sap.shipment FOR INSERT WITH CHECK (true);

-- ─────────────────────────────────────────────────────────
-- INDEXES
-- ─────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_mat_doc_posting_date    ON sap.mat_document(posting_date);
CREATE INDEX IF NOT EXISTS idx_mat_doc_movement_type   ON sap.mat_document(movement_type);
CREATE INDEX IF NOT EXISTS idx_mat_doc_sim_run         ON sap.mat_document(sim_run_id);
CREATE INDEX IF NOT EXISTS idx_mat_doc_item_material   ON sap.mat_document_item(material_id, plant_id);
CREATE INDEX IF NOT EXISTS idx_fi_doc_period           ON sap.fi_document(period);
CREATE INDEX IF NOT EXISTS idx_fi_doc_sim_run          ON sap.fi_document(sim_run_id);
CREATE INDEX IF NOT EXISTS idx_so_status               ON sap.sales_order(status);
CREATE INDEX IF NOT EXISTS idx_so_customer             ON sap.sales_order(customer_id);
CREATE INDEX IF NOT EXISTS idx_dlv_so                  ON sap.outbound_delivery(so_id);
CREATE INDEX IF NOT EXISTS idx_dlv_gi_status           ON sap.outbound_delivery(goods_issue_status);
CREATE INDEX IF NOT EXISTS idx_ship_pod_status         ON sap.shipment(pod_status);
CREATE INDEX IF NOT EXISTS idx_sim_run_status          ON sap.sim_run(status);
CREATE INDEX IF NOT EXISTS idx_sim_issue_run           ON sap.sim_issue(sim_run_id);
CREATE INDEX IF NOT EXISTS idx_inv_snap_material       ON sap.inventory_snapshot(material_id, plant_id, as_of_date);
