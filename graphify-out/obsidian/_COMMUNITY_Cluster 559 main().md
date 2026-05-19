---
type: community
cohesion: 0.67
members: 3
---

# Cluster 559: main()

**Cohesion:** 0.67 - moderately connected
**Members:** 3 nodes

## Members
- [[TMS Product 테이블 박스사이즈 일괄 백필 (one-shot).  문제 328337 records have blank '박스사이즈']] - rationale - scripts/backfill/backfill_product_box_size.py
- [[backfill_product_box_size.py]] - code - scripts/backfill/backfill_product_box_size.py
- [[main()_54]] - code - scripts/backfill/backfill_product_box_size.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_559_main
SORT file.name ASC
```
