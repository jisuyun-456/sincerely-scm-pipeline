---
type: community
cohesion: 0.36
members: 8
---

# Cluster 249: harness.virtual_sa

**Cohesion:** 0.36 - loosely connected
**Members:** 8 nodes

## Members
- [[GitHub Actions Virtual SAP Seed Master Data Workflow]] - code - .github/workflows/virtual-sap-seed.yml
- [[GitHub Actions Virtual SAP Simulation Workflow]] - code - .github/workflows/virtual-sap-sim.yml
- [[Rationale Supabase Restricted to Dashboard Snapshots Only (Not WMSTMS SSOT)]] - rationale - docs/superpowers/outputs/2026-05-15-scm-asis-diagnosis.md
- [[Slack DM Notification Integration]] - document - .github/workflows/tms_settlement.yml
- [[Supabase (Virtual SAP State Storage)]] - document - .github/workflows/virtual-sap-seed.yml
- [[Virtual SAP Agents (delivery_confirm, customer_notify, dispatch_advisor, etc.)]] - code - .github/workflows/virtual-sap-sim.yml
- [[Virtual SAP Simulation System]] - document - .github/workflows/virtual-sap-sim.yml
- [[harness.virtual_sap Python Module]] - code - .github/workflows/virtual-sap-sim.yml

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_249_harnessvirtual_sa
SORT file.name ASC
```

## Connections to other communities
- 1 edge to [[_COMMUNITY_Cluster 140 6-Layer Claude Cod]]
- 1 edge to [[_COMMUNITY_Cluster 72 Airtable WMS Base]]

## Top bridge nodes
- [[Slack DM Notification Integration]] - degree 2, connects to 1 community
- [[Rationale Supabase Restricted to Dashboard Snapshots Only (Not WMSTMS SSOT)]] - degree 2, connects to 1 community