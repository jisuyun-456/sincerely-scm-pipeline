---
type: community
cohesion: 0.47
members: 6
---

# Cluster 350: _generate_tracking

**Cohesion:** 0.47 - moderately connected
**Members:** 6 nodes

## Members
- [[Assign tracking numbers to pendingin_transit shipments. Returns count processed]] - rationale - harness/virtual_sap/agents/tracking_number_agent.py
- [[Phase E — 운송장기입 자동화 에이전트.  Trigger sap.shipment 중 pod_status='pending' 또는 'in_t]] - rationale - harness/virtual_sap/agents/tracking_number_agent.py
- [[_generate_tracking_no()]] - code - harness/virtual_sap/agents/tracking_number_agent.py
- [[_log_agent_event()_5]] - code - harness/virtual_sap/agents/tracking_number_agent.py
- [[run()_11]] - code - harness/virtual_sap/agents/tracking_number_agent.py
- [[tracking_number_agent.py]] - code - harness/virtual_sap/agents/tracking_number_agent.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_350__generate_tracking
SORT file.name ASC
```

## Connections to other communities
- 2 edges to [[_COMMUNITY_TMS Alert & Claim Agents]]
- 1 edge to [[_COMMUNITY_Cluster 162 _log_agent_event()]]

## Top bridge nodes
- [[tracking_number_agent.py]] - degree 6, connects to 1 community
- [[run()_11]] - degree 5, connects to 1 community