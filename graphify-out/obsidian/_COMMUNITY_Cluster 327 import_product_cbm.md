---
type: community
cohesion: 0.36
members: 8
---

# Cluster 327: import_product_cbm

**Cohesion:** 0.36 - loosely connected
**Members:** 8 nodes

## Members
- [[Return only fields that differ from the existing record.]] - rationale - harness/settlement/import_product_cbm.py
- [[_changed()]] - code - harness/settlement/import_product_cbm.py
- [[_fields_from()]] - code - harness/settlement/import_product_cbm.py
- [[_load_existing()]] - code - harness/settlement/import_product_cbm.py
- [[import_product_cbm.py]] - code - harness/settlement/import_product_cbm.py
- [[main()_6]] - code - harness/settlement/import_product_cbm.py
- [[견적코드 → {rec_id, name, box_type, qty_per_box, cbm}]] - rationale - harness/settlement/import_product_cbm.py
- [[영업팀 CBM 마스터 데이터를 TMS Product 테이블에 UPSERT.  Usage   py harnesssettlementimp]] - rationale - harness/settlement/import_product_cbm.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_327_import_product_cbm
SORT file.name ASC
```
