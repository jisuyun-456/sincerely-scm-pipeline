---
name: virtual-sap-tick
description: Virtual SAP simulation tick — runs one simulation cycle of the SAP order-to-delivery lifecycle. Identical to .github/workflows/virtual-sap-sim.yml (every 30min + daily). Destructive — writes to Supabase virtual-SAP tables. Manual invocation only.
allowed-tools: Bash(python:*), Read
disable-model-invocation: true
---

# Virtual SAP Simulation Tick — Manual Invocation Guide

**CRON PARITY:** Wraps `harness/virtual_sap/cli.py` — identical to the `tick` job in
`.github/workflows/virtual-sap-sim.yml`. If the CLI changes, update workflow yaml in the same commit.

## Canonical Commands

### Dry-run tick (no DB writes)
```bash
VSAP_DRY_RUN=true python -m harness.virtual_sap.cli tick --mode continuous
```

### Live tick modes
```bash
# Continuous (standard 30-min tick)
python -m harness.virtual_sap.cli tick --mode continuous

# Daily batch (period-close check included)
python -m harness.virtual_sap.cli tick --mode daily

# Manual single tick
python -m harness.virtual_sap.cli tick --mode manual

# Backfill
python -m harness.virtual_sap.cli tick --mode backfill
```

## Required Environment Variables

| Variable | Source |
|---------|--------|
| `VSAP_SUPABASE_URL` | `SUPABASE_URL` secret |
| `VSAP_SUPABASE_SERVICE_KEY` | `SUPABASE_SERVICE_KEY` secret |
| `VSAP_MODE` | CLI arg (continuous/daily/manual/backfill) |
| `VSAP_DRY_RUN` | "true"/"false" |
| `VSAP_ORDERS_PER_TICK` | Default "2" |
| `SLACK_BOT_TOKEN` | `SLACK_BOT_TOKEN` secret (optional, for alerts) |
| `SLACK_DM_USER_ID` | `SLACK_DM_USER_ID` secret (optional) |

## Dependencies

```bash
pip install -r requirements-virtual-sap.txt
```

## Dry-Run-First Protocol
1. Run `VSAP_DRY_RUN=true` first — confirm order generation looks reasonable
2. Ask user: "시뮬레이션 틱 실행합니다 (mode: {mode}). 진행할까요?"
3. Run live tick and report: orders created, state transitions, any errors

## Supabase Note
Virtual SAP is the ONLY subsystem allowed to write to Supabase.
WMS/TMS operational data remains Airtable-only (see CLAUDE.md Supabase policy).
