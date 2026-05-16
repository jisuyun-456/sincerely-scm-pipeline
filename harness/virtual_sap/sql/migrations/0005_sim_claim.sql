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

-- RLS: INSERT-only (consistent with other transaction tables)
ALTER TABLE sap.sim_claim ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS sim_claim_select ON sap.sim_claim;
DROP POLICY IF EXISTS sim_claim_insert ON sap.sim_claim;
CREATE POLICY sim_claim_select ON sap.sim_claim FOR SELECT USING (true);
CREATE POLICY sim_claim_insert ON sap.sim_claim FOR INSERT WITH CHECK (true);

GRANT USAGE ON SCHEMA sap TO anon, authenticated, service_role;
GRANT SELECT, INSERT ON sap.sim_claim TO anon, authenticated, service_role;
