# .claude/skills — Sincerely SCM Skill Registry

Human-readable index of all 12 Skills. Not a SKILL.md — this file is documentation only.

## Architecture

Skills are ADDITIVE alongside the 14 Subagents (SK-01~09, D-TMS1/2, D1~D3).
- Subagent routing always takes priority over Skill autoload.
- Knowledge Skills autoload by description match (no `disable-model-invocation`).
- Script Skills require explicit invocation (`disable-model-invocation: true`).

---

## Track A — Knowledge Skills (5)

| Skill | Autoload | Agents Using It | Description |
|-------|----------|----------------|-------------|
| `sap-movement-accounts` | Yes | SK-02, SK-03, SK-04, SK-07, D2 | SAP 101~551 codes + K-IFRS/더존 accounts |
| `aql-sampling` | Yes | SK-02, SK-07 | ANSI/ASQ Z1.4 lot size → sample size → Ac/Re |
| `abc-xyz-rop-eoq` | Yes | SK-01, D1 | ABC/XYZ classification + ROP + EOQ formulas |
| `storno-immutable-ledger` | Yes | SK-03, D2 | Storno 역분개 pattern + INSERT-ONLY rules |
| `scm-kpi-formulas` | Yes | SK-05, SK-06, SK-04 | OTIF, POR, D2S, Vehicle Util, Consolidation ROI |

---

## Track B — Script Skills (7)

| Skill | Autoload | Agent Aware | Cron Parity | Destructive |
|-------|----------|-------------|-------------|-------------|
| `tms-settlement-daily` | No | SK-05 | `tms_settlement.yml` daily 12:00 UTC | Yes — writes Airtable |
| `tms-weekly-backfill` | No | SK-09 | `weekly-full-pipeline.yml` Step 1 | Yes — writes Airtable |
| `tms-weekly-report` | Yes | SK-06 | `weekly-full-pipeline.yml` Step 2 | No — read+file write |
| `wms-weekly-report` | Yes | SK-06 | `weekly-full-pipeline.yml` Step 4 | No — read+file write |
| `wms-sap-weekly-sync` | No | — | `weekly-full-pipeline.yml` Step 3 | Yes — writes Airtable |
| `virtual-sap-tick` | No | — | `virtual-sap-sim.yml` every 30min | Yes — writes Supabase |
| `pdf-from-template` | Yes | SK-01 | `generate_pdf.yml` fallback | No — local file write |

---

## Cron Parity Matrix

| Skill | Workflow File | Step | CLI Command |
|-------|-------------|------|-------------|
| tms-settlement-daily | `.github/workflows/tms_settlement.yml` | write job | `python -m harness.tms_settlement.main --date YYYY-MM-DD --auto-confirm` |
| tms-weekly-backfill | `.github/workflows/weekly-full-pipeline.yml` | Step 1 | `python scripts/tms_weekly_backfill.py` |
| tms-weekly-report | `.github/workflows/weekly-full-pipeline.yml` | Step 2 | `python scripts/tms_weekly_runner.py` |
| wms-weekly-report | `.github/workflows/weekly-full-pipeline.yml` | Step 4 | `python scripts/wms_weekly_runner.py` |
| wms-sap-weekly-sync | `.github/workflows/weekly-full-pipeline.yml` | Step 3 | `python scripts/wms_sap_weekly.py` |
| virtual-sap-tick | `.github/workflows/virtual-sap-sim.yml` | tick job | `python -m harness.virtual_sap.cli tick --mode {mode}` |
| pdf-from-template | `.github/workflows/generate_pdf.yml` | generate | `python pdf/출고확인서_tms.py --record-id REC_ID` |

**Rule:** If a CLI command changes, update BOTH the workflow yaml AND the SKILL.md in the same commit.

---

## Rollback

Each Skill is independently removable:
```bash
rm -rf .claude/skills/<name>/
# revert trailing ## Available Skills block in affected agents
git restore .claude/agents/<name>.md
```

Cron jobs are unaffected — they call the Python modules directly.
