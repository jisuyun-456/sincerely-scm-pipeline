---
type: community
cohesion: 0.25
members: 9
---

# Cluster 240: cli.py

**Cohesion:** 0.25 - loosely connected
**Members:** 9 nodes

## Members
- [[CLI entry point python -m harness.virtual_sap.cli subcommand]] - rationale - harness/virtual_sap/cli.py
- [[Check that all required master data tables have rows.]] - rationale - harness/virtual_sap/seed/seed_master.py
- [[Insert all master data. Returns count per table.]] - rationale - harness/virtual_sap/seed/seed_master.py
- [[One-shot master data seeder.  Usage     python -m harness.virtual_sap.cli seed]] - rationale - harness/virtual_sap/seed/seed_master.py
- [[cli.py]] - code - harness/virtual_sap/cli.py
- [[main()_12]] - code - harness/virtual_sap/cli.py
- [[seed_all()]] - code - harness/virtual_sap/seed/seed_master.py
- [[seed_master.py]] - code - harness/virtual_sap/seed/seed_master.py
- [[verify_seed()]] - code - harness/virtual_sap/seed/seed_master.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_240_clipy
SORT file.name ASC
```

## Connections to other communities
- 2 edges to [[_COMMUNITY_TMS Alert & Claim Agents]]
- 1 edge to [[_COMMUNITY_Cluster 141 engine.py]]

## Top bridge nodes
- [[seed_master.py]] - degree 5, connects to 1 community
- [[main()_12]] - degree 4, connects to 1 community