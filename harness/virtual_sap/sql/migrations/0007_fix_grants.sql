-- Migration 0007: Fix missing GRANT + RLS on tables added in 0003-0006
-- Run this against the live DB to unblock claim_agent and invoice_agent.

GRANT USAGE ON SCHEMA sap TO anon, authenticated, service_role;

-- sim_agent_event (0003)
GRANT SELECT, INSERT ON sap.sim_agent_event TO anon, authenticated, service_role;

-- so_reorder_queue (0004)
GRANT SELECT, INSERT, UPDATE ON sap.so_reorder_queue TO anon, authenticated, service_role;

-- sim_claim (0005) — INSERT-only transaction table
ALTER TABLE sap.sim_claim ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS sim_claim_select ON sap.sim_claim;
DROP POLICY IF EXISTS sim_claim_insert ON sap.sim_claim;
CREATE POLICY sim_claim_select ON sap.sim_claim FOR SELECT USING (true);
CREATE POLICY sim_claim_insert ON sap.sim_claim FOR INSERT WITH CHECK (true);
GRANT SELECT, INSERT ON sap.sim_claim TO anon, authenticated, service_role;

-- sim_invoice (0006) — INSERT-only transaction table
ALTER TABLE sap.sim_invoice ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS sim_invoice_select ON sap.sim_invoice;
DROP POLICY IF EXISTS sim_invoice_insert ON sap.sim_invoice;
CREATE POLICY sim_invoice_select ON sap.sim_invoice FOR SELECT USING (true);
CREATE POLICY sim_invoice_insert ON sap.sim_invoice FOR INSERT WITH CHECK (true);
GRANT SELECT, INSERT ON sap.sim_invoice TO anon, authenticated, service_role;
