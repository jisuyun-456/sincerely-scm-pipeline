---
type: community
cohesion: 0.67
members: 4
---

# Cluster 390: count_records()

**Cohesion:** 0.67 - moderately connected
**Members:** 4 nodes

## Members
- [[count_records()]] - code - scripts/dryrun_tms_backfill_count.py
- [[dryrun_tms_backfill_count.py]] - code - scripts/dryrun_tms_backfill_count.py
- [[main()_23]] - code - scripts/dryrun_tms_backfill_count.py
- [[페이지네이션으로 전체 레코드 카운트. 패턴이 주어지면 클라이언트 측 매칭 카운트.]] - rationale - scripts/dryrun_tms_backfill_count.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_390_count_records
SORT file.name ASC
```
