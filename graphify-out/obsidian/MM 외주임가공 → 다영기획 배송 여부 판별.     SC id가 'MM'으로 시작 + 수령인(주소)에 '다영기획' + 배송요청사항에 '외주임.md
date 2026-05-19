---
source_file: "harness/settlement/settlement_calc.py"
type: "rationale"
community: "CBM Backfill & Batch Ops"
location: "L373"
tags:
  - graphify/rationale
  - graphify/EXTRACTED
  - community/CBM_Backfill__Batch_Ops
---

# MM 외주임가공 → 다영기획 배송 여부 판별.     SC id가 'MM'으로 시작 + 수령인(주소)에 '다영기획' + 배송요청사항에 '외주임

## Connections
- [[_is_outsource()]] - `rationale_for` [EXTRACTED]

#graphify/rationale #graphify/EXTRACTED #community/CBM_Backfill__Batch_Ops