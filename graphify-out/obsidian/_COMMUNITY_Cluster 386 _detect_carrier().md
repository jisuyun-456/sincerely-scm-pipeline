---
type: community
cohesion: 0.67
members: 4
---

# Cluster 386: _detect_carrier()

**Cohesion:** 0.67 - moderately connected
**Members:** 4 nodes

## Members
- [[_detect_carrier()]] - code - scripts/backfill/backfill_택배추적로그.py
- [[backfill_택배추적로그.py]] - code - scripts/backfill/backfill_택배추적로그.py
- [[run()_29]] - code - scripts/backfill/backfill_택배추적로그.py
- [[택배추적로그 주간 백필 - 조건 출하확정일이 대상 주간이고, 운송장번호 있으나 택배추적로그 없음 - 동작 택배사운송장번호 기반 초기 추]] - rationale - scripts/backfill/backfill_택배추적로그.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_386__detect_carrier
SORT file.name ASC
```
