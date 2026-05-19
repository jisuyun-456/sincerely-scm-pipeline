---
type: community
cohesion: 0.22
members: 11
---

# Cluster 214: assert_domain()

**Cohesion:** 0.22 - loosely connected
**Members:** 11 nodes

## Members
- [[.__init__()_9]] - code - harness/_core/runner.py
- [[LocalProdWriteForbidden]] - code - harness/_core/_guard.py
- [[Raised when a shipment record has a driver ID not in KNOWN_DRIVERS.]] - rationale - harness/tms_settlement/fetch.py
- [[Refuse writes that land outside the gitignored state tree.      Also blocks any]] - rationale - harness/_core/_guard.py
- [[RuntimeError]] - code
- [[UnregisteredDriverError]] - code - harness/tms_settlement/fetch.py
- [[_guard.py]] - code - harness/_core/_guard.py
- [[assert_domain()]] - code - harness/_core/_guard.py
- [[assert_state_path()]] - code - harness/_core/_guard.py
- [[paths.py]] - code - harness/_core/paths.py
- [[state_dir()]] - code - harness/_core/paths.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_214_assert_domain
SORT file.name ASC
```

## Connections to other communities
- 2 edges to [[_COMMUNITY_Cluster 69 BatchedRunner]]
- 1 edge to [[_COMMUNITY_Cluster 97 assert_week_in_win]]
- 1 edge to [[_COMMUNITY_Cluster 40 AirtableClient]]
- 1 edge to [[_COMMUNITY_Cluster 236 StructuredLogger]]

## Top bridge nodes
- [[UnregisteredDriverError]] - degree 5, connects to 3 communities
- [[RuntimeError]] - degree 3, connects to 1 community
- [[.__init__()_9]] - degree 2, connects to 1 community