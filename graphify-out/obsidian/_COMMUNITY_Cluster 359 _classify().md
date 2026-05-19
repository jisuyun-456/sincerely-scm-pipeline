---
type: community
cohesion: 0.60
members: 5
---

# Cluster 359: _classify()

**Cohesion:** 0.60 - moderately connected
**Members:** 5 nodes

## Members
- [[_classify()]] - code - scripts/backfill/backfill_구간유형.py
- [[_str_field()_4]] - code - scripts/backfill/backfill_구간유형.py
- [[backfill_구간유형.py]] - code - scripts/backfill/backfill_구간유형.py
- [[run()_23]] - code - scripts/backfill/backfill_구간유형.py
- [[구간유형 자동분류 백필 - 조건 구간유형 blank AND 수령인(주소) 있는 Shipment - 동작 주소 키워드 기반으로 single]] - rationale - scripts/backfill/backfill_구간유형.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_359__classify
SORT file.name ASC
```
