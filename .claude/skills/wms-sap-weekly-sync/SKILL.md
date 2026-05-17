---
name: wms-sap-weekly-sync
description: Weekly WMS SAP movement backfill — syncs SAP movement type fields in Airtable WMS records. Identical to Step 3 of .github/workflows/weekly-full-pipeline.yml cron (Mon 12:00 UTC). Destructive — manual invocation only.
allowed-tools: Bash(python:*), Read
disable-model-invocation: true
---

# WMS SAP Weekly Sync — Manual Invocation Guide

**CRON PARITY:** Wraps `scripts/wms_sap_weekly.py` — identical to Step 3 of
`.github/workflows/weekly-full-pipeline.yml`. If the script changes, update workflow yaml in the same commit.

## Canonical Command

```bash
python scripts/wms_sap_weekly.py
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
- Reads WMS movement records missing SAP movement type classification
- Back-fills SAP movement type (101/201/261/311/601/701/122/551) based on movement context
- Writes back to Airtable WMS base (DESTRUCTIVE — updates movement type fields)

## Dry-Run-First Protocol
Before running live:
1. Query scope: how many records have null SAP movement type?
2. Ask user: "N개 레코드 SAP 이동유형 동기화됩니다. 진행할까요?"
3. Run and report updated count

## Immutable Ledger Note
This script updates classification metadata fields only — NOT the movement quantity/date/type audit fields. Movement records themselves remain INSERT-ONLY per Immutable Ledger policy.
