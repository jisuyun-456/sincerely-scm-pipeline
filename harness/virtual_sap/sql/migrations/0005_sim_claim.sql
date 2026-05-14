-- Migration 0005: Delivery Claims
-- Populated by claim_agent when pod_status='exception'.

CREATE TABLE IF NOT EXISTS sap.sim_claim (
    claim_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ship_id         TEXT NOT NULL REFERENCES sap.shipment(ship_id),
    reason          TEXT NOT NULL DEFAULT 'pod_exception',
    status          TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','investigating','resolved','closed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS sim_claim_ship_id_idx  ON sap.sim_claim (ship_id);
CREATE INDEX IF NOT EXISTS sim_claim_status_idx   ON sap.sim_claim (status);
