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
