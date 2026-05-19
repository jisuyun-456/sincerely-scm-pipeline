---
type: community
cohesion: 0.67
members: 3
---

# Cluster 560: 배차 일지 주간 백필 - 조건: 

**Cohesion:** 0.67 - moderately connected
**Members:** 3 nodes

## Members
- [[backfill_배차일지.py]] - code - scripts/backfill/backfill_배차일지.py
- [[run()_25]] - code - scripts/backfill/backfill_배차일지.py
- [[배차 일지 주간 백필 - 조건 출하확정일이 대상 주간이고, 내부기사(배송파트너) 배정되어 있으나 배차 일지 미링크 - 동작 날짜×기사 단]] - rationale - scripts/backfill/backfill_배차일지.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_560_____-__
SORT file.name ASC
```
