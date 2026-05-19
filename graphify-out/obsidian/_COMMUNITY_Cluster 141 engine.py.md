---
type: community
cohesion: 0.16
members: 15
---

# Cluster 141: engine.py

**Cohesion:** 0.16 - loosely connected
**Members:** 15 nodes

## Members
- [[Dry-run tick tests — no Supabase connection required.]] - rationale - tests/virtual_sap/test_dry_run_tick.py
- [[Execute one simulation tick. Returns summary dict.]] - rationale - harness/virtual_sap/engine.py
- [[Send a Slack DM on engine failure. No-ops if SLACK_BOT_TOKEN is not set.]] - rationale - harness/virtual_sap/notifier.py
- [[Slack DM notifier — sends failure alerts to a configured user.]] - rationale - harness/virtual_sap/notifier.py
- [[Virtual SAP Simulation — Engine orchestrator.]] - rationale - harness/virtual_sap/engine.py
- [[_get_git_sha()]] - code - harness/virtual_sap/engine.py
- [[_run_verifiers()]] - code - harness/virtual_sap/engine.py
- [[dry_run_env()]] - code - tests/virtual_sap/test_dry_run_tick.py
- [[engine.py]] - code - harness/virtual_sap/engine.py
- [[notifier.py]] - code - harness/virtual_sap/notifier.py
- [[notify_failure()]] - code - harness/virtual_sap/notifier.py
- [[run_tick()]] - code - harness/virtual_sap/engine.py
- [[test_dry_run_tick.py]] - code - tests/virtual_sap/test_dry_run_tick.py
- [[test_full_tick_dry_run()]] - code - tests/virtual_sap/test_dry_run_tick.py
- [[test_step_order_creates_docs()]] - code - tests/virtual_sap/test_dry_run_tick.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_141_enginepy
SORT file.name ASC
```

## Connections to other communities
- 2 edges to [[_COMMUNITY_TMS Alert & Claim Agents]]
- 1 edge to [[_COMMUNITY_Cluster 240 cli.py]]
- 1 edge to [[_COMMUNITY_Cluster 162 _log_agent_event()]]

## Top bridge nodes
- [[run_tick()]] - degree 8, connects to 2 communities
- [[engine.py]] - degree 7, connects to 1 community