---
type: community
cohesion: 0.40
members: 13
---

# Cluster 202: create_records()

**Cohesion:** 0.40 - loosely connected
**Members:** 13 nodes

## Members
- [[create_records()]] - code - scripts/wms_sap_weekly.py
- [[delete_all_records()]] - code - scripts/wms_sap_weekly.py
- [[get_existing_refs()]] - code - scripts/wms_sap_weekly.py
- [[get_last_monday()]] - code - scripts/wms_sap_weekly.py
- [[get_records()_1]] - code - scripts/wms_sap_weekly.py
- [[main()_48]] - code - scripts/wms_sap_weekly.py
- [[recalculate_ledger()]] - code - scripts/wms_sap_weekly.py
- [[update_goods_receipt()]] - code - scripts/wms_sap_weekly.py
- [[update_inventory_transactions()]] - code - scripts/wms_sap_weekly.py
- [[update_wave_and_tasks()]] - code - scripts/wms_sap_weekly.py
- [[wms_sap_weekly.py]] - code - scripts/wms_sap_weekly.py
- [[wms_sap_weekly.py ─────────────────────────────────────────────────────────────]] - rationale - scripts/wms_sap_weekly.py
- [[기존 레코드의 특정 필드값 집합 반환 (중복 체크용)]] - rationale - scripts/wms_sap_weekly.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_202_create_records
SORT file.name ASC
```
