---
type: community
cohesion: 0.38
members: 7
---

# Cluster 328: OutboundLedger

**Cohesion:** 0.38 - loosely connected
**Members:** 7 nodes

## Members
- [[.__init__()_10]] - code - harness/_core/runner.py
- [[._append()]] - code - harness/_core/runner.py
- [[.claim()]] - code - harness/_core/runner.py
- [[.commit()]] - code - harness/_core/runner.py
- [[.is_committed()]] - code - harness/_core/runner.py
- [[OutboundLedger]] - code - harness/_core/runner.py
- [[Two-phase INTENTCOMMIT ledger for idempotent outbound writes.      INTENT recor]] - rationale - harness/_core/runner.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_328_OutboundLedger
SORT file.name ASC
```

## Connections to other communities
- 1 edge to [[_COMMUNITY_Cluster 236 StructuredLogger]]
- 1 edge to [[_COMMUNITY_Cluster 69 BatchedRunner]]

## Top bridge nodes
- [[OutboundLedger]] - degree 8, connects to 2 communities