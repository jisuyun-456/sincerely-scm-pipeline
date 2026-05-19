---
source_file: "harness/settlement/estimate_unload_by_product.py"
type: "rationale"
community: "Cluster 203: estimate_unload_by"
location: "L98"
tags:
  - graphify/rationale
  - graphify/EXTRACTED
  - community/Cluster_203_estimate_unload_by
---

# 품목 텍스트 → Counter({box_text: count}) 룩업 테이블 빌드     같은 품목에 여러 박스 구성이 있으면 가장 많이 쓰인

## Connections
- [[build_lookup()]] - `rationale_for` [EXTRACTED]

#graphify/rationale #graphify/EXTRACTED #community/Cluster_203_estimate_unload_by