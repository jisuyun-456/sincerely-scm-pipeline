---
type: community
cohesion: 0.20
members: 16
---

# Cluster 113: _allocate()

**Cohesion:** 0.20 - loosely connected
**Members:** 16 nodes

## Members
- [[.can_take()]] - code - harness/virtual_sap/agents/dispatch_advisor.py
- [[Allocate deliveries to carriers using CBM+distance rules.]] - rationale - harness/virtual_sap/agents/dispatch_advisor.py
- [[Allocation]] - code - harness/virtual_sap/agents/dispatch_advisor.py
- [[DriverLoad]] - code - harness/virtual_sap/agents/dispatch_advisor.py
- [[Generate dispatch recommendations. Returns count of deliveries allocated.]] - rationale - harness/virtual_sap/agents/dispatch_advisor.py
- [[Phase C — 배차 추천 에이전트 (Dispatch Advisor).  Runs daily at 0800 KST. Looks at GI-p]] - rationale - harness/virtual_sap/agents/dispatch_advisor.py
- [[Rough km estimate from warehouse to delivery region.]] - rationale - harness/virtual_sap/agents/dispatch_advisor.py
- [[_allocate()]] - code - harness/virtual_sap/agents/dispatch_advisor.py
- [[_estimate_distance_km()]] - code - harness/virtual_sap/agents/dispatch_advisor.py
- [[_estimate_fare()]] - code - harness/virtual_sap/agents/dispatch_advisor.py
- [[_is_metro()]] - code - harness/virtual_sap/agents/dispatch_advisor.py
- [[_log_agent_event()_2]] - code - harness/virtual_sap/agents/dispatch_advisor.py
- [[_slack_notify()_3]] - code - harness/virtual_sap/agents/dispatch_advisor.py
- [[dispatch_advisor.py]] - code - harness/virtual_sap/agents/dispatch_advisor.py
- [[remaining_cbm()]] - code - harness/virtual_sap/agents/dispatch_advisor.py
- [[run()_4]] - code - harness/virtual_sap/agents/dispatch_advisor.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_113__allocate
SORT file.name ASC
```

## Connections to other communities
- 2 edges to [[_COMMUNITY_TMS Alert & Claim Agents]]
- 1 edge to [[_COMMUNITY_Cluster 162 _log_agent_event()]]

## Top bridge nodes
- [[dispatch_advisor.py]] - degree 13, connects to 1 community
- [[run()_4]] - degree 7, connects to 1 community