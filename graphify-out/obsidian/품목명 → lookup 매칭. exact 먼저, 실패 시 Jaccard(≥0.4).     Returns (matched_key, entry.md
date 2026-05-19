---
source_file: "harness/settlement/cbm_calc.py"
type: "rationale"
community: "CBM Backfill & Batch Ops"
location: "L123"
tags:
  - graphify/rationale
  - graphify/EXTRACTED
  - community/CBM_Backfill__Batch_Ops
---

# 품목명 → lookup 매칭. exact 먼저, 실패 시 Jaccard(≥0.4).     Returns: (matched_key, entry

## Connections
- [[match_product()]] - `rationale_for` [EXTRACTED]

#graphify/rationale #graphify/EXTRACTED #community/CBM_Backfill__Batch_Ops