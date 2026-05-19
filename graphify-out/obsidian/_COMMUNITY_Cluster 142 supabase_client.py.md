---
type: community
cohesion: 0.21
members: 15
---

# Cluster 142: supabase_client.py

**Cohesion:** 0.21 - loosely connected
**Members:** 15 nodes

## Members
- [[Call a Postgres stored procedurefunction.]] - rationale - harness/virtual_sap/supabase_client.py
- [[INSERT rows into a sap. table. No-ops in dry_run mode.]] - rationale - harness/virtual_sap/supabase_client.py
- [[Return singleton Supabase client (service_role key).]] - rationale - harness/virtual_sap/supabase_client.py
- [[SELECT rows from a sap. table. Returns  in dry_run mode.]] - rationale - harness/virtual_sap/supabase_client.py
- [[Simple retry with exponential backoff on 5xx.]] - rationale - harness/virtual_sap/supabase_client.py
- [[Supabase client wrapper — INSERT-only, dry-run gate, retry.]] - rationale - harness/virtual_sap/supabase_client.py
- [[UPDATE rows — allowed only for non-ledger tables (status fields, snapshots).]] - rationale - harness/virtual_sap/supabase_client.py
- [[_retry()]] - code - harness/virtual_sap/supabase_client.py
- [[get_client()]] - code - harness/virtual_sap/supabase_client.py
- [[insert()]] - code - harness/virtual_sap/supabase_client.py
- [[reset_client()]] - code - harness/virtual_sap/supabase_client.py
- [[rpc()]] - code - harness/virtual_sap/supabase_client.py
- [[select()]] - code - harness/virtual_sap/supabase_client.py
- [[supabase_client.py]] - code - harness/virtual_sap/supabase_client.py
- [[update()]] - code - harness/virtual_sap/supabase_client.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_142_supabase_clientpy
SORT file.name ASC
```

## Connections to other communities
- 4 edges to [[_COMMUNITY_Cluster 162 _log_agent_event()]]
- 1 edge to [[_COMMUNITY_TMS Alert & Claim Agents]]

## Top bridge nodes
- [[supabase_client.py]] - degree 9, connects to 1 community
- [[get_client()]] - degree 7, connects to 1 community
- [[insert()]] - degree 5, connects to 1 community
- [[select()]] - degree 5, connects to 1 community
- [[update()]] - degree 5, connects to 1 community