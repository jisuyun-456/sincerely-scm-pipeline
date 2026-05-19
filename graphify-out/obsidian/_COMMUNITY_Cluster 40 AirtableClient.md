---
type: community
cohesion: 0.15
members: 27
---

# Cluster 40: AirtableClient

**Cohesion:** 0.15 - loosely connected
**Members:** 27 nodes

## Members
- [[.__init__()_3]] - code - harness/_core/airtable.py
- [[.__init__()_2]] - code - harness/_core/airtable.py
- [[.__init__()_4]] - code - harness/_core/http_session.py
- [[.__init__()_5]] - code - harness/_core/http_session.py
- [[._check_response()]] - code - harness/_core/airtable.py
- [[._raise_for_status()]] - code - harness/_core/http_session.py
- [[._url()]] - code - harness/_core/http_session.py
- [[.acquire()]] - code - harness/_core/airtable.py
- [[.assert_audit_table_exists()]] - code - harness/_core/airtable.py
- [[.check_schema_drift()]] - code - harness/_core/airtable.py
- [[.close()]] - code - harness/_core/http_session.py
- [[.get()]] - code - harness/_core/http_session.py
- [[.get_records()]] - code - harness/_core/airtable.py
- [[.patch()]] - code - harness/_core/http_session.py
- [[.patch_record()]] - code - harness/_core/airtable.py
- [[.post()]] - code - harness/_core/http_session.py
- [[AirtableClient]] - code - harness/_core/airtable.py
- [[AuditTableMissingError]] - code - harness/_core/airtable.py
- [[AuthError]] - code - harness/_core/http_session.py
- [[Exception]] - code
- [[HttpSession]] - code - harness/_core/http_session.py
- [[In-process 3 reqs sliding-window limiter (thread-safe).      Cross-process file]] - rationale - harness/_core/airtable.py
- [[SchemaError]] - code - harness/_core/airtable.py
- [[_RateLimiter]] - code - harness/_core/airtable.py
- [[airtable.py]] - code - harness/_core/airtable.py
- [[get_or_create()]] - code - harness/_core/airtable.py
- [[http_session.py]] - code - harness/_core/http_session.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_40_AirtableClient
SORT file.name ASC
```

## Connections to other communities
- 5 edges to [[_COMMUNITY_Cluster 222 AirtableViewRegist]]
- 4 edges to [[_COMMUNITY_Cluster 236 StructuredLogger]]
- 3 edges to [[_COMMUNITY_Cluster 237 Notifier]]
- 1 edge to [[_COMMUNITY_Cluster 214 assert_domain()]]
- 1 edge to [[_COMMUNITY_Cluster 251 write.py]]
- 1 edge to [[_COMMUNITY_Cluster 367 ConfigBase]]
- 1 edge to [[_COMMUNITY_Cluster 250 Daily audit-vs-Air]]

## Top bridge nodes
- [[AirtableClient]] - degree 16, connects to 5 communities
- [[Exception]] - degree 6, connects to 2 communities
- [[HttpSession]] - degree 16, connects to 1 community
- [[_RateLimiter]] - degree 7, connects to 1 community
- [[SchemaError]] - degree 7, connects to 1 community