---
type: community
cohesion: 0.60
members: 5
---

# Cluster 361: _fetch_dispatch()

**Cohesion:** 0.60 - moderately connected
**Members:** 5 nodes

## Members
- [[_fetch_dispatch()]] - code - scripts/backfill/backfill_운임합계.py
- [[_fetch_shipments()]] - code - scripts/backfill/backfill_운임합계.py
- [[backfill_운임합계.py]] - code - scripts/backfill/backfill_운임합계.py
- [[run()_27]] - code - scripts/backfill/backfill_운임합계.py
- [[배차일지 운임합계 백필 - 조건 대상 주간 Shipment의 운송비용+상하차비용 합계를 날짜×기사 단위로 집계 - 동작 매칭되는 배차일지]] - rationale - scripts/backfill/backfill_운임합계.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_361__fetch_dispatch
SORT file.name ASC
```
