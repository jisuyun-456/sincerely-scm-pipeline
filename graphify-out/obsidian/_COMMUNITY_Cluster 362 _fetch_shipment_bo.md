---
type: community
cohesion: 0.60
members: 5
---

# Cluster 362: _fetch_shipment_bo

**Cohesion:** 0.60 - moderately connected
**Members:** 5 nodes

## Members
- [[_fetch_shipment_boxes()]] - code - scripts/backfill/backfill_전주평균CBM.py
- [[_parse_total_boxes()]] - code - scripts/backfill/backfill_전주평균CBM.py
- [[backfill_전주평균CBM.py]] - code - scripts/backfill/backfill_전주평균CBM.py
- [[run()_28]] - code - scripts/backfill/backfill_전주평균CBM.py
- [[배차일지 전주평균CBM 백필 - 조건 대상 주간 배차일지의 linked Shipments에서 '총N박스' 파싱 - 동작 평균 박스수건을]] - rationale - scripts/backfill/backfill_전주평균CBM.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_362__fetch_shipment_bo
SORT file.name ASC
```
