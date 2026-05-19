---
type: community
cohesion: 0.60
members: 5
---

# Cluster 382: last_week_range()

**Cohesion:** 0.60 - moderately connected
**Members:** 5 nodes

## Members
- [[_notify_slack()]] - code - scripts/tms_weekly_backfill.py
- [[last_week_range()_1]] - code - scripts/tms_weekly_backfill.py
- [[main()_44]] - code - scripts/tms_weekly_backfill.py
- [[tms_weekly_backfill.py]] - code - scripts/tms_weekly_backfill.py
- [[tms_weekly_backfill.py ────────────────────────────────────────────────────────]] - rationale - scripts/tms_weekly_backfill.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_382_last_week_range
SORT file.name ASC
```
