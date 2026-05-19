---
type: community
cohesion: 0.33
members: 10
---

# Cluster 233: carrier_from_partn

**Cohesion:** 0.33 - loosely connected
**Members:** 10 nodes

## Members
- [[Shipment 운송장번호 + 배송파트너 배치 조회]] - rationale - scripts/backfill_tracking_fields.py
- [[backfill_tracking_fields.py]] - code - scripts/backfill_tracking_fields.py
- [[carrier_from_partner()]] - code - scripts/backfill_tracking_fields.py
- [[fetch_incomplete_trk()]] - code - scripts/backfill_tracking_fields.py
- [[fetch_ship_data()]] - code - scripts/backfill_tracking_fields.py
- [[main()_18]] - code - scripts/backfill_tracking_fields.py
- [[paginate()_1]] - code - scripts/backfill_tracking_fields.py
- [[patch_batch()]] - code - scripts/backfill_tracking_fields.py
- [[배송파트너 lookup 값(str or list) → 택배사 문자열     매핑 불가 + '택배' 포함이면 '기타' 반환]] - rationale - scripts/backfill_tracking_fields.py
- [[택배사 또는 운송장번호가 비어 있는 TRK 레코드 조회]] - rationale - scripts/backfill_tracking_fields.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_233_carrier_from_partn
SORT file.name ASC
```
