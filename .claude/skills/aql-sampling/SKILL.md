---
name: aql-sampling
description: Reference for ANSI/ASQ Z1.4 AQL sampling — lot size to sample size, acceptance/rejection numbers for Level II inspection. Use when determining inspection sample counts for inbound GR or return inspection.
allowed-tools: Read
---

# AQL Sampling — ANSI/ASQ Z1.4

## Standard Reference
- **Standard**: ANSI/ASQ Z1.4 (Sampling Procedures for Attribute Inspection)
- **Default Inspection Level**: Level II (General)
- **Default AQL**: 1.0% (tight) or 2.5% (normal) — per agreement with supplier

## Sample Size Code Letters (Inspection Level II)

| Lot Size | Code Letter |
|----------|------------|
| 2 – 8 | A |
| 9 – 15 | B |
| 16 – 25 | C |
| 26 – 50 | D |
| 51 – 90 | E |
| 91 – 150 | F |
| 151 – 280 | G |
| 281 – 500 | H |
| 501 – 1,200 | J |
| 1,201 – 3,200 | K |
| 3,201 – 10,000 | L |
| 10,001 – 35,000 | M |

## Accept/Reject Numbers by Code Letter

Full table with accept (Ac) / reject (Re) numbers per AQL level → `references/ansi-z14-table.md`

## Quick Decision Formula

```
1. Determine lot size N
2. Look up Code Letter (Level II table above)
3. Look up sample size n + Ac/Re from AQL table
4. Inspect n units
5. defects ≤ Ac → ACCEPT (proceed to GR, movement 101)
6. defects ≥ Re → REJECT (NCR + LOT격리 + SK-07 wms-return)
```

## Escalation Triggers
- Same supplier: ≥3 rejections in rolling 90 days → Tightened Inspection (Level II → Level I)
- Same supplier: 0 rejections in 5 consecutive lots → Reduced Inspection (Level II → Level III)
- AQL override requires D2 tax-accounting-expert sign-off (regulatory compliance)
