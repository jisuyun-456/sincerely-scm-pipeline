---
name: pdf-from-template
description: Generate outgoing confirmation PDF (출고확인서) from Airtable record. Wraps pdf/generate_pdf.py and pdf/출고확인서_tms.py. Read-only Airtable access + local PDF write; safe to invoke.
allowed-tools: Bash(python:*), Read
---

# PDF Generation — 출고확인서

**CRON PARITY:** Wraps `pdf/출고확인서_tms.py` — same code path as emergency fallback in
`.github/workflows/generate_pdf.yml`. Primary path is Railway FastAPI (`api/app.py`).
If the CLI changes, update workflow yaml in the same commit.

## Canonical Commands

### 출고확인서 (TMS — standard)
```bash
python pdf/출고확인서_tms.py --record-id REC_ID_HERE
```

### General PDF from template
```bash
python pdf/generate_pdf.py --record-id REC_ID_HERE --output /tmp/output.pdf
```

### Packing List PDF (WMS outbound)
```bash
python scripts/packing_list.py --record-id REC_ID_HERE
```

### Picking List PDF
```bash
python scripts/picking_list_pdf.py --record-id REC_ID_HERE
```

## Required Environment Variables

| Variable | Source | Notes |
|---------|--------|-------|
| `AIRTABLE_PAT` | `AIRTABLE_API_KEY_TMS` secret | TMS record access |
| `PDF_OUTPUT_DIR` | `/tmp` | Output directory |

## Dependencies

```bash
pip install -r pdf/TMS_pdf_requirements.txt
# Korean font (NanumGothic) required — pre-installed in Railway/GitHub Actions
# Local: sudo apt-get install -y fonts-nanum
```

## Output
PDF written to `PDF_OUTPUT_DIR/{record_id}.pdf`
Upload to Airtable attachment via `mcp__scm_airtable__upload_pdf` if needed.

## Note: Safe to Invoke
PDF generation only reads Airtable (no writes to operational tables) and writes a local file.
No dry-run required — safe to invoke directly from conversation.
