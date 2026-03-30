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
