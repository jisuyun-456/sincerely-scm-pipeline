---
source_file: "harness/settlement/cbm_calc.py"
type: "rationale"
community: "CBM Backfill & Batch Ops"
location: "L54"
tags:
  - graphify/rationale
  - graphify/EXTRACTED
  - community/CBM_Backfill__Batch_Ops
---

# Product 테이블 전체 조회 → 품목명(lower)/견적코드(lower) → entry dict.     entry: {rec_id, na

## Connections
- [[load_product_lookup()]] - `rationale_for` [EXTRACTED]

#graphify/rationale #graphify/EXTRACTED #community/CBM_Backfill__Batch_Ops