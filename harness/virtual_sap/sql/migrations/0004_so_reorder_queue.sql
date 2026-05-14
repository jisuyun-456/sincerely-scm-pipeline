-- Migration 0004: SO Reorder Queue
-- Populated by quality_reject_agent when AQL fails; consumed by step_01 next tick.

CREATE TABLE IF NOT EXISTS sap.so_reorder_queue (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    qi_id           UUID NOT NULL REFERENCES sap.qi_inspection(qi_id),
    material_id     TEXT NOT NULL REFERENCES sap.material(material_id),
    plant_id        TEXT NOT NULL REFERENCES sap.plant(plant_id),
    qty             NUMERIC(14,3) NOT NULL CHECK (qty > 0),
    reason          TEXT NOT NULL DEFAULT 'aql_rejected',
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processed','cancelled')),
    processed_so_id TEXT REFERENCES sap.sales_order(so_id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS so_reorder_queue_status_idx ON sap.so_reorder_queue (status);
CREATE INDEX IF NOT EXISTS so_reorder_queue_qi_id_idx  ON sap.so_reorder_queue (qi_id);
