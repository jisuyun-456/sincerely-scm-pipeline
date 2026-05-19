---
type: community
cohesion: 0.21
members: 14
---

# Cluster 162: _log_agent_event()

**Cohesion:** 0.21 - loosely connected
**Members:** 14 nodes

## Members
- [[.__post_init__()]] - code - harness/virtual_sap/config.py
- [[Config validation tests.]] - rationale - tests/virtual_sap/test_config.py
- [[Phase E — 임가공출고요청 자동화 에이전트.  Trigger sap.mat_document 중 movement_type='261'이고]] - rationale - harness/virtual_sap/agents/oem_release_agent.py
- [[Send OEM work requests for movement_type=261 documents. Returns count processed.]] - rationale - harness/virtual_sap/agents/oem_release_agent.py
- [[SimConfig]] - code - harness/virtual_sap/config.py
- [[_log_agent_event()_4]] - code - harness/virtual_sap/agents/oem_release_agent.py
- [[_reset()]] - code - tests/virtual_sap/test_config.py
- [[get_config()]] - code - harness/virtual_sap/config.py
- [[oem_release_agent.py]] - code - harness/virtual_sap/agents/oem_release_agent.py
- [[run()_8]] - code - harness/virtual_sap/agents/oem_release_agent.py
- [[test_config.py]] - code - tests/virtual_sap/test_config.py
- [[test_dry_run_false_by_default()]] - code - tests/virtual_sap/test_config.py
- [[test_dry_run_true_from_env()]] - code - tests/virtual_sap/test_config.py
- [[test_invalid_mode_raises()]] - code - tests/virtual_sap/test_config.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_162__log_agent_event
SORT file.name ASC
```

## Connections to other communities
- 11 edges to [[_COMMUNITY_TMS Alert & Claim Agents]]
- 5 edges to [[_COMMUNITY_Virtual SAP Process Steps]]
- 4 edges to [[_COMMUNITY_Cluster 142 supabase_client.py]]
- 2 edges to [[_COMMUNITY_Cluster 41 PartnerType]]
- 1 edge to [[_COMMUNITY_Cluster 141 engine.py]]
- 1 edge to [[_COMMUNITY_Cluster 349 _log_agent_event()]]
- 1 edge to [[_COMMUNITY_Cluster 329 _build_confirmatio]]
- 1 edge to [[_COMMUNITY_Cluster 113 _allocate()]]
- 1 edge to [[_COMMUNITY_Cluster 350 _generate_tracking]]
- 1 edge to [[_COMMUNITY_Cluster 330 step_03_inventory.]]

## Top bridge nodes
- [[get_config()]] - degree 30, connects to 10 communities
- [[oem_release_agent.py]] - degree 5, connects to 1 community
- [[SimConfig]] - degree 3, connects to 1 community