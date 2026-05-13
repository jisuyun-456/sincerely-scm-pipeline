-- Ops Console — Agent Activity Log
-- Unified event table for both harness batch jobs and Claude Code AI agent calls.
-- INSERT-only (enforced via RLS). Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS public.ops_event (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    source      TEXT NOT NULL CHECK (source IN ('harness','hook')),
    agent_id    TEXT NOT NULL,          -- e.g. 'tms_settlement', 'tms-otif-kpi'
    domain      TEXT,                  -- TMS / WMS / SAP / FI / SCM / OPS / PM
    session_id  TEXT,                  -- Claude Code session ID (hook only)
    week        TEXT,                  -- ISO week start date (harness only, e.g. '2026-05-06')
    status      TEXT NOT NULL CHECK (status IN ('started','completed','failed')),
    duration_ms INT,
    summary     TEXT,
    meta        JSONB
);

ALTER TABLE public.ops_event ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS ops_select ON public.ops_event;
DROP POLICY IF EXISTS ops_insert ON public.ops_event;
CREATE POLICY ops_select ON public.ops_event FOR SELECT USING (true);
CREATE POLICY ops_insert ON public.ops_event FOR INSERT WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_ops_event_ts     ON public.ops_event(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ops_event_agent  ON public.ops_event(agent_id);
CREATE INDEX IF NOT EXISTS idx_ops_event_source ON public.ops_event(source);
