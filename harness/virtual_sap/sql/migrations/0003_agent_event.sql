-- Migration 0003: Agent automation event log
-- Stores processing records from Python harness agents (출고확인서, 배차추천, etc.)

CREATE TABLE IF NOT EXISTS sap.sim_agent_event (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    agent_name  TEXT NOT NULL,   -- '출고확인서' | '배차추천' | '재고파악'
    target_id   TEXT,            -- dlv_id / so_id / material_id etc.
    status      TEXT NOT NULL,   -- 'ok' | 'failed' | 'skipped'
    message     TEXT,
    sim_run_id  UUID REFERENCES sap.sim_run(id)
);

CREATE INDEX IF NOT EXISTS sim_agent_event_created_at_idx ON sap.sim_agent_event (created_at DESC);
CREATE INDEX IF NOT EXISTS sim_agent_event_agent_name_idx ON sap.sim_agent_event (agent_name);
CREATE INDEX IF NOT EXISTS sim_agent_event_sim_run_id_idx ON sap.sim_agent_event (sim_run_id);
