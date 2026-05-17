---
name: tms-settlement-daily
description: Daily TMS driver settlement — reads TMS shipments, computes fare, writes results to Airtable. Identical to .github/workflows/tms_settlement.yml cron at 12:00 UTC. Destructive — manual invocation only.
allowed-tools: Bash(python:*), Read
disable-model-invocation: true
---

# TMS Settlement Daily — Manual Invocation Guide

**CRON PARITY:** This Skill wraps the same code path as `.github/workflows/tms_settlement.yml`.
If the CLI changes, update BOTH the workflow yaml AND this SKILL.md in the same commit.

## Canonical Commands

### Dry-run (preview, no writes)
```bash
python -m harness.tms_settlement.main --date YYYY-MM-DD --dry-run --auto-confirm
```

### Week batch dry-run
```bash
python -m harness.tms_settlement.main --week YYYY-MM-DD --dry-run --auto-confirm
```

### Live run (DESTRUCTIVE — writes to Airtable)
```bash
# Step 1: always preview first
python -m harness.tms_settlement.main --date YYYY-MM-DD --dry-run --auto-confirm

# Step 2: only after user confirms "go"
python -m harness.tms_settlement.main --date YYYY-MM-DD --auto-confirm

# With force overwrite (existing fare values)
python -m harness.tms_settlement.main --date YYYY-MM-DD --auto-confirm --force
```

## Required Environment Variables

| Variable | Source | Notes |
|---------|--------|-------|
| `AIRTABLE_PAT` | `AIRTABLE_API_KEY_TMS` secret | TMS base access |
| `SLACK_BOT_TOKEN` | `SLACK_BOT_TOKEN` secret | Settlement notification |
| `SLACK_DM_USER_ID` | `SLACK_DM_USER_ID` secret | DM recipient |
| `SUPABASE_URL` | `SUPABASE_URL` secret | Dashboard snapshot (optional) |
| `SUPABASE_SERVICE_KEY` | `SUPABASE_KEY` secret | Dashboard snapshot (optional) |

## Dry-Run-First Protocol (MANDATORY)

1. Always run with `--dry-run --auto-confirm` first → review `settlement-preview.txt`
2. Check: no "blocked ratio > 0%" / no "fetch failed" / no "CRITICAL" in output
3. Ask user: "정산 미리보기 확인했습니까? 실제 쓰기 진행할까요?" — wait for explicit "go"
4. Only then run without `--dry-run`

## Module Structure (READ ONLY — do not modify)
- `harness/tms_settlement/main.py` — entry point
- `harness/tms_settlement/calc.py` — fare calculation
- `harness/tms_settlement/fetch.py` — Airtable data fetch
- `harness/tms_settlement/config.py` — driver/rate config
- `harness/tms_settlement/write.py` — Airtable write
- `harness/tms_settlement/verifier.py` — anomaly gate

## Immutable Ledger Note
Settlement writes use INSERT patterns — existing fare records are NOT overwritten unless `--force` is explicitly passed. Never run `--force` without user confirmation.
