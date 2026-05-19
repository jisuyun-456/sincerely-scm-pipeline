---
source_file: "scripts/backfill/backfill_운임합계.py"
type: "rationale"
community: "Cluster 361: _fetch_dispatch()"
location: "L1"
tags:
  - graphify/rationale
  - graphify/EXTRACTED
  - community/Cluster_361__fetch_dispatch
---

# 배차일지 운임합계 백필 - 조건: 대상 주간 Shipment의 운송비용+상하차비용 합계를 날짜×기사 단위로 집계 - 동작: 매칭되는 배차일지

## Connections
- [[backfill_운임합계.py]] - `rationale_for` [EXTRACTED]

#graphify/rationale #graphify/EXTRACTED #community/Cluster_361__fetch_dispatch