---
source_file: "harness/settlement/cbm_calc.py"
type: "code"
community: "CBM Backfill & Batch Ops"
location: "L53"
tags:
  - graphify/code
  - graphify/INFERRED
  - community/CBM_Backfill__Batch_Ops
---

# load_product_lookup()

## Connections
- [[Product 테이블 전체 조회 → 품목명(lower)견적코드(lower) → entry dict.     entry {rec_id, na]] - `rationale_for` [EXTRACTED]
- [[cbm_calc.py]] - `contains` [EXTRACTED]
- [[load_cbm_lookup()]] - `calls` [INFERRED]
- [[main()_9]] - `calls` [INFERRED]
- [[main()_10]] - `calls` [INFERRED]
- [[run()_22]] - `calls` [INFERRED]
- [[run()_26]] - `calls` [INFERRED]

#graphify/code #graphify/INFERRED #community/CBM_Backfill__Batch_Ops