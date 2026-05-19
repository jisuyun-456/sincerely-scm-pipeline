---
type: community
cohesion: 0.28
members: 13
---

# Cluster 200: discover_fields()

**Cohesion:** 0.28 - loosely connected
**Members:** 13 nodes

## Members
- [[Metadata API로 택배추적로그 + Shipment 필드 ID 매핑 반환]] - rationale - scripts/fix_tracking_backfill.py
- [[discover_fields()]] - code - scripts/fix_tracking_backfill.py
- [[fetch_all_tracking()]] - code - scripts/fix_tracking_backfill.py
- [[fetch_missing_shipments()_1]] - code - scripts/fix_tracking_backfill.py
- [[fetch_shipments_by_rec_ids()_1]] - code - scripts/fix_tracking_backfill.py
- [[fix_tracking_backfill.py]] - code - scripts/fix_tracking_backfill.py
- [[main()_25]] - code - scripts/fix_tracking_backfill.py
- [[map_carrier()]] - code - scripts/fix_tracking_backfill.py
- [[paginate()_3]] - code - scripts/fix_tracking_backfill.py
- [[patch_batch()_2]] - code - scripts/fix_tracking_backfill.py
- [[post_batch()_1]] - code - scripts/fix_tracking_backfill.py
- [[배송파트너 문자열 → 택배사 singleSelect 값]] - rationale - scripts/fix_tracking_backfill.py
- [[택배 배송, 완료, 추적로그 없음, 2026-01-01 이후]] - rationale - scripts/fix_tracking_backfill.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_200_discover_fields
SORT file.name ASC
```
