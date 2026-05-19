---
type: community
cohesion: 0.52
members: 7
---

# Cluster 343: classify()

**Cohesion:** 0.52 - moderately connected
**Members:** 7 nodes

## Members
- [[classify()_1]] - code - scripts/zone_classify.py
- [[fetch_targets()]] - code - scripts/zone_classify.py
- [[main()_51]] - code - scripts/zone_classify.py
- [[normalize()]] - code - scripts/zone_classify.py
- [[patch_batch()_3]] - code - scripts/zone_classify.py
- [[records {id, fields{F_ZONE '수도권'}}, ...  최대 10개씩]] - rationale - scripts/zone_classify.py
- [[zone_classify.py]] - code - scripts/zone_classify.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_343_classify
SORT file.name ASC
```
