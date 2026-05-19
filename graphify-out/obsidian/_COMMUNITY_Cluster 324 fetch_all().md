---
type: community
cohesion: 0.39
members: 8
---

# Cluster 324: fetch_all()

**Cohesion:** 0.39 - loosely connected
**Members:** 8 nodes

## Members
- [[Probe next_week shipments — show TF_ITEM + matching result per line.  목적 mat]] - rationale - scripts/probe_next_week_match.py
- [[_headers()_1]] - code - scripts/probe_next_week_match.py
- [[fetch_all()_2]] - code - scripts/probe_next_week_match.py
- [[main()_36]] - code - scripts/probe_next_week_match.py
- [[match_current()]] - code - scripts/probe_next_week_match.py
- [[next_week_range()_1]] - code - scripts/probe_next_week_match.py
- [[probe_next_week_match.py]] - code - scripts/probe_next_week_match.py
- [[현재 로직 — generate_scm_report.py와 동일.]] - rationale - scripts/probe_next_week_match.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_324_fetch_all
SORT file.name ASC
```
