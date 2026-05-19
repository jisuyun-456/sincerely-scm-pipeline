---
type: community
cohesion: 1.00
members: 2
---

# Cluster 563: Golden Tests (tms_

**Cohesion:** 1.00 - tightly connected
**Members:** 2 nodes

## Members
- [[CI Golden Tests Workflow]] - code - .github/workflows/ci.yml
- [[Golden Tests (tms_settlement, 90% coverage gate)]] - code - .github/workflows/ci.yml

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_563_Golden_Tests_tms_
SORT file.name ASC
```
