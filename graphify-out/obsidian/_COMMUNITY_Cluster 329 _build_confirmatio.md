---
type: community
cohesion: 0.43
members: 7
---

# Cluster 329: _build_confirmatio

**Cohesion:** 0.43 - moderately connected
**Members:** 7 nodes

## Members
- [[Phase B — 출고확인서 자동 생성 에이전트.  Trigger GI 완료된 outbound_delivery 중 아직 sim_agent_ev]] - rationale - harness/virtual_sap/agents/delivery_confirm_agent.py
- [[Process unconfirmed deliveries. Returns count of confirmations generated.]] - rationale - harness/virtual_sap/agents/delivery_confirm_agent.py
- [[_build_confirmation_text()]] - code - harness/virtual_sap/agents/delivery_confirm_agent.py
- [[_log_agent_event()_1]] - code - harness/virtual_sap/agents/delivery_confirm_agent.py
- [[_slack_notify()_1]] - code - harness/virtual_sap/agents/delivery_confirm_agent.py
- [[delivery_confirm_agent.py]] - code - harness/virtual_sap/agents/delivery_confirm_agent.py
- [[run()_2]] - code - harness/virtual_sap/agents/delivery_confirm_agent.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_329__build_confirmatio
SORT file.name ASC
```

## Connections to other communities
- 2 edges to [[_COMMUNITY_TMS Alert & Claim Agents]]
- 1 edge to [[_COMMUNITY_Cluster 162 _log_agent_event()]]

## Top bridge nodes
- [[delivery_confirm_agent.py]] - degree 7, connects to 1 community
- [[run()_2]] - degree 6, connects to 1 community