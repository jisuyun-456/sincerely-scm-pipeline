# ANSI/ASQ Z1.4 — AQL Table (Normal Inspection, Single Sampling)

## Sample Sizes by Code Letter

| Code | Sample Size (n) |
|------|----------------|
| A | 2 |
| B | 3 |
| C | 5 |
| D | 8 |
| E | 13 |
| F | 20 |
| G | 32 |
| H | 50 |
| J | 80 |
| K | 125 |
| L | 200 |
| M | 315 |
| N | 500 |
| P | 800 |
| Q | 1,250 |
| R | 2,000 |

## Acceptance Numbers (Ac/Re) by AQL Level

| Code | n | AQL 0.65 Ac/Re | AQL 1.0 Ac/Re | AQL 1.5 Ac/Re | AQL 2.5 Ac/Re | AQL 4.0 Ac/Re |
|------|---|----------------|----------------|----------------|----------------|----------------|
| A | 2 | ↑ | ↑ | ↑ | ↑ | 0/1 |
| B | 3 | ↑ | ↑ | ↑ | 0/1 | 0/1 |
| C | 5 | ↑ | ↑ | 0/1 | 0/1 | 0/1 |
| D | 8 | ↑ | 0/1 | 0/1 | 0/1 | 1/2 |
| E | 13 | 0/1 | 0/1 | 0/1 | 1/2 | 1/2 |
| F | 20 | 0/1 | 0/1 | 1/2 | 1/2 | 2/3 |
| G | 32 | 0/1 | 1/2 | 1/2 | 2/3 | 3/4 |
| H | 50 | 1/2 | 1/2 | 2/3 | 3/4 | 5/6 |
| J | 80 | 1/2 | 2/3 | 3/4 | 5/6 | 7/8 |
| K | 125 | 2/3 | 3/4 | 5/6 | 7/8 | 10/11 |
| L | 200 | 3/4 | 5/6 | 7/8 | 10/11 | 14/15 |
| M | 315 | 5/6 | 7/8 | 10/11 | 14/15 | 21/22 |

↑ = Use next larger sample size code

## Notes
- **Normal inspection** (Level II) applies by default
- **Tightened**: reduce acceptance number by 1 (supplier performance trigger)
- **Reduced**: increase acceptance number by 1 (supplier performance reward)
- **Defect classification**: Critical (0 Ac) / Major (AQL 1.0) / Minor (AQL 2.5)
- Re-inspect if borderline — do not override, document decision

## Sincerely Standard
- 신시어리 기본 AQL: 2.5% (외관·치수 불량), 0% (Critical — 안전·법규 불량)
- 불합격 시: NCR INSERT → LOT격리(W-NEW-02) → SK-07 wms-return 위임
