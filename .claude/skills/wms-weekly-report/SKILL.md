---
name: wms-weekly-report
description: Weekly WMS AutoResearch report — inventory KPI analysis writing to _AutoResearch/SCM/outputs/. Identical to Step 4 of .github/workflows/weekly-full-pipeline.yml. Read-only analysis; safe to invoke mid-conversation.
allowed-tools: Bash(python:*), Read
---

# WMS Weekly AutoResearch Report

**CRON PARITY:** Wraps `scripts/wms_weekly_runner.py` — identical to Step 4 of
`.github/workflows/weekly-full-pipeline.yml`. If the script changes, update workflow yaml in the same commit.

## Canonical Command

```bash
python scripts/wms_weekly_runner.py
```

## Required Environment Variables

| Variable | Source |
|---------|--------|
| `AIRTABLE_WMS_PAT` | `AIRTABLE_API_KEY_WMS` secret |

## Dependencies

```bash
pip install -r requirements-autoresearch.txt
```

## What This Script Does
- Reads WMS inventory + movement data from Airtable
- Computes: inventory accuracy, cycle count results, negative stock incidents, ABC distribution
- Writes to: `_AutoResearch/SCM/outputs/WMS-YYYY-WXX.md`

## Output Location
`_AutoResearch/SCM/outputs/WMS-{YEAR}-W{WEEK}.md`

## Note: Read-Only
No Airtable writes — safe to invoke anytime without dry-run protocol.
