---
source_file: "scripts/backfill_tracking_fields.py"
type: "rationale"
community: "Cluster 233: carrier_from_partn"
location: "L46"
tags:
  - graphify/rationale
  - graphify/EXTRACTED
  - community/Cluster_233_carrier_from_partn
---

# 배송파트너 lookup 값(str or list) → 택배사 문자열     매핑 불가 + '택배' 포함이면 '기타' 반환

## Connections
- [[carrier_from_partner()]] - `rationale_for` [EXTRACTED]

#graphify/rationale #graphify/EXTRACTED #community/Cluster_233_carrier_from_partn