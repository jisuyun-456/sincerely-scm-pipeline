---
name: tms-weekly-backfill
description: Weekly TMS data backfill — computes and back-fills missing TMS analysis fields. Identical to Step 1 of .github/workflows/weekly-full-pipeline.yml cron (Mon 12:00 UTC). Destructive — manual invocation only.
allowed-tools: Bash(python:*), Read
disable-model-invocation: true
---

# TMS Weekly Backfill — Manual Invocation Guide

**CRON PARITY:** This Skill wraps `scripts/tms_weekly_backfill.py` — identical to Step 1 of
`.github/workflows/weekly-full-pipeline.yml`. If the script changes, update workflow yaml in the same commit.

## Canonical Command

```bash
python scripts/tms_weekly_backfill.py
```

## Required Environment Variables

| Variable | Source |
|---------|--------|
| `AIRTABLE_PAT` | `AIRTABLE_PAT` secret |
| `SLACK_BOT_TOKEN` | `SLACK_BOT_TOKEN` secret |
| `SLACK_DM_USER_ID` | `SLACK_DM_USER_ID` secret |

## Dependencies

```bash
pip install -r requirements-autoresearch.txt
```

## What This Script Does
- Reads TMS shipment records with missing analysis fields
- Back-fills: OTIF flags, fare amounts, CBM values, carrier categorization
- Writes to `scripts/backfill/` intermediate files
- Reports filled/skipped/errors counts

## Dry-Run-First Protocol
No built-in `--dry-run` flag. Before running live:
1. Check recent git log for last backfill date
2. Query Airtable for null-field count (estimate scope)
3. Ask user: "백필 실행하면 N개 레코드 갱신됩니다. 진행할까요?"
4. Run and report: "filled: N / skipped: M / errors: K"

## Immutable Ledger Note
Backfill only fills NULL fields — never overwrites existing values. Verified by `backfill_total_cbm_safe.py` guard logic.
