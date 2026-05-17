---
name: tms-weekly-report
description: Weekly TMS AutoResearch report — 4-iteration KPI analysis writing to _AutoResearch/SCM/outputs/. Identical to Step 2 of .github/workflows/weekly-full-pipeline.yml. Read-only analysis; safe to invoke mid-conversation.
allowed-tools: Bash(python:*), Read
---

# TMS Weekly AutoResearch Report

**CRON PARITY:** Wraps `scripts/tms_weekly_runner.py` — identical to Step 2 of
`.github/workflows/weekly-full-pipeline.yml`. If the script changes, update workflow yaml in the same commit.

## Canonical Command

```bash
python scripts/tms_weekly_runner.py
```

## Required Environment Variables

| Variable | Source |
|---------|--------|
| `AIRTABLE_PAT` | `AIRTABLE_PAT` secret |

## Dependencies

```bash
pip install -r requirements-autoresearch.txt
```

## What This Script Does
- 4-iteration analysis: KPI summary → statistical analysis → anomaly detection → predictions
- Reads from: `mcp__scm_airtable__tms_otif`, `tms_shipments`, `tms_delivery_events`
- Writes to: `_AutoResearch/SCM/outputs/TMS-YYYY-WXX.md`
- Includes vehicle utilization v2 (CBM-weighted, commit CBM-PHASE-D-01)
- Escalates cost anomalies (±15% 4wk moving avg) to SK-09 tms-cost-lane

## Output Location
`_AutoResearch/SCM/outputs/TMS-{YEAR}-W{WEEK}.md`

## Note: Read-Only
This script only reads Airtable and writes a markdown report file.
No Airtable writes — safe to invoke anytime without dry-run protocol.
