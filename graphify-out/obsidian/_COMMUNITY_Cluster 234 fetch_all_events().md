---
type: community
cohesion: 0.38
members: 10
---

# Cluster 234: fetch_all_events()

**Cohesion:** 0.38 - loosely connected
**Members:** 10 nodes

## Members
- [[fetch_all_events()]] - code - scripts/fix_event_backfill.py
- [[fetch_missing_shipments()]] - code - scripts/fix_event_backfill.py
- [[fetch_shipments_by_rec_ids()]] - code - scripts/fix_event_backfill.py
- [[fix_event_backfill.py]] - code - scripts/fix_event_backfill.py
- [[main()_24]] - code - scripts/fix_event_backfill.py
- [[paginate()_2]] - code - scripts/fix_event_backfill.py
- [[patch_batch()_1]] - code - scripts/fix_event_backfill.py
- [[post_batch()]] - code - scripts/fix_event_backfill.py
- [[record ID 리스트로 Shipment 출하확정일 조회]] - rationale - scripts/fix_event_backfill.py
- [[배송이벤트 없는 완료 Shipment (2026-01-01 이후)]] - rationale - scripts/fix_event_backfill.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_234_fetch_all_events
SORT file.name ASC
```
