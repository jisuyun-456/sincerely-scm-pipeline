---
type: community
cohesion: 0.25
members: 8
---

# Cluster 250: Daily audit-vs-Air

**Cohesion:** 0.25 - loosely connected
**Members:** 8 nodes

## Members
- [[.__init__()_8]] - code - harness/_core/reconciler.py
- [[.run_daily()]] - code - harness/_core/reconciler.py
- [[.run_monthly_sum()]] - code - harness/_core/reconciler.py
- [[Compare harness_writes_audit entries against current Airtable values.          O]] - rationale - harness/_core/reconciler.py
- [[Daily audit-vs-Airtable diff and monthly cross-week sum reconciler.      Full im]] - rationale - harness/_core/reconciler.py
- [[Reconciler]] - code - harness/_core/reconciler.py
- [[Sum all settlement weeks in the rolling month per driver.          Compare again]] - rationale - harness/_core/reconciler.py
- [[reconciler.py]] - code - harness/_core/reconciler.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_250_Daily_audit-vs-Air
SORT file.name ASC
```

## Connections to other communities
- 1 edge to [[_COMMUNITY_Cluster 40 AirtableClient]]
- 1 edge to [[_COMMUNITY_Cluster 236 StructuredLogger]]
- 1 edge to [[_COMMUNITY_Cluster 237 Notifier]]

## Top bridge nodes
- [[Reconciler]] - degree 8, connects to 3 communities