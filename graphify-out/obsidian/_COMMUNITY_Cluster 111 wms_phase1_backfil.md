---
type: community
cohesion: 0.20
members: 17
---

# Cluster 111: wms_phase1_backfil

**Cohesion:** 0.20 - loosely connected
**Members:** 17 nodes

## Members
- [[Create records in batches of 10 (Airtable limit).]] - rationale - _archive/wms/wms_phase1_backfill.py
- [[Determine Qty_Change based on movement type.]] - rationale - _archive/wms/wms_phase1_backfill.py
- [[Extract PT code from 이동물품 field, e.g. 'PT1373-...' → 'PT1373'.]] - rationale - _archive/wms/wms_phase1_backfill.py
- [[Infer ToFrom location record IDs based on 이동목적.]] - rationale - _archive/wms/wms_phase1_backfill.py
- [[Paginate through all records (or up to max_records).]] - rationale - _archive/wms/wms_phase1_backfill.py
- [[WMS Phase 1 Historical Backfill -------------------------------- Creates WMS_Inv]] - rationale - _archive/wms/wms_phase1_backfill.py
- [[airtable_get()_9]] - code - _archive/wms/wms_phase1_backfill.py
- [[backfill_ledger()]] - code - _archive/wms/wms_phase1_backfill.py
- [[backfill_ncr()]] - code - _archive/wms/wms_phase1_backfill.py
- [[backfill_transactions()]] - code - _archive/wms/wms_phase1_backfill.py
- [[batch_create()]] - code - _archive/wms/wms_phase1_backfill.py
- [[build_material_map()_2]] - code - _archive/wms/wms_phase1_backfill.py
- [[extract_pt_code()_1]] - code - _archive/wms/wms_phase1_backfill.py
- [[fetch_all()_4]] - code - _archive/wms/wms_phase1_backfill.py
- [[get_qty()]] - code - _archive/wms/wms_phase1_backfill.py
- [[location_for_purpose()]] - code - _archive/wms/wms_phase1_backfill.py
- [[wms_phase1_backfill.py]] - code - _archive/wms/wms_phase1_backfill.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_111_wms_phase1_backfil
SORT file.name ASC
```
