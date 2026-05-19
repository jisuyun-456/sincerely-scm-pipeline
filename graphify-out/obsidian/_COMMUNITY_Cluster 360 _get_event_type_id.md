---
type: community
cohesion: 0.50
members: 5
---

# Cluster 360: _get_event_type_id

**Cohesion:** 0.50 - moderately connected
**Members:** 5 nodes

## Members
- [[_get_event_type_id()]] - code - scripts/backfill/backfill_배송이벤트.py
- [[backfill_배송이벤트.py]] - code - scripts/backfill/backfill_배송이벤트.py
- [[run()_24]] - code - scripts/backfill/backfill_배송이벤트.py
- [[배송이벤트 주간 백필 - 조건 출하확정일이 대상 주간이고, 배송이벤트 레코드 없음 - 동작 이벤트유형=배송접수 초기 이벤트 생성]] - rationale - scripts/backfill/backfill_배송이벤트.py
- [[이벤트유형 singleSelect choice ID 조회 (배송접수)]] - rationale - scripts/backfill/backfill_배송이벤트.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_360__get_event_type_id
SORT file.name ASC
```
