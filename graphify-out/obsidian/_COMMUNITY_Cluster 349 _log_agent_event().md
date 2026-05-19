---
type: community
cohesion: 0.47
members: 6
---

# Cluster 349: _log_agent_event()

**Cohesion:** 0.47 - moderately connected
**Members:** 6 nodes

## Members
- [[Notify customers for GI-posted deliveries. Returns count of notifications sent.]] - rationale - harness/virtual_sap/agents/customer_notify_agent.py
- [[Phase E — 고객출고알림 자동화 에이전트.  Trigger outbound_delivery 중 goods_issue_status='pos]] - rationale - harness/virtual_sap/agents/customer_notify_agent.py
- [[_log_agent_event()]] - code - harness/virtual_sap/agents/customer_notify_agent.py
- [[_send_customer_email()]] - code - harness/virtual_sap/agents/customer_notify_agent.py
- [[customer_notify_agent.py]] - code - harness/virtual_sap/agents/customer_notify_agent.py
- [[run()_1]] - code - harness/virtual_sap/agents/customer_notify_agent.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_349__log_agent_event
SORT file.name ASC
```

## Connections to other communities
- 2 edges to [[_COMMUNITY_TMS Alert & Claim Agents]]
- 1 edge to [[_COMMUNITY_Cluster 162 _log_agent_event()]]

## Top bridge nodes
- [[customer_notify_agent.py]] - degree 6, connects to 1 community
- [[run()_1]] - degree 5, connects to 1 community