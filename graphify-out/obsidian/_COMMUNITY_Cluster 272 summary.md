---
type: community
cohesion: 0.25
members: 8
---

# Cluster 272: summary

**Cohesion:** 0.25 - loosely connected
**Members:** 8 nodes

## Members
- [[actual_qc_cnt]] - code - history/2026-03_monthly.json
- [[defect_rate_1]] - code - history/2026-03_monthly.json
- [[qc_cnt]] - code - history/2026-03_monthly.json
- [[sample_rate]] - code - history/2026-03_monthly.json
- [[summary_1]] - code - history/2026-03_monthly.json
- [[target_met]] - code - history/2026-03_monthly.json
- [[total_defect]] - code - history/2026-03_monthly.json
- [[total_qc_qty]] - code - history/2026-03_monthly.json

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_272_summary
SORT file.name ASC
```

## Connections to other communities
- 1 edge to [[_COMMUNITY_Cluster 215 W13]]

## Top bridge nodes
- [[summary_1]] - degree 8, connects to 1 community