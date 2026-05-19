---
type: community
cohesion: 0.24
members: 10
---

# Cluster 222: AirtableViewRegist

**Cohesion:** 0.24 - loosely connected
**Members:** 10 nodes

## Members
- [[.__init__()_12]] - code - harness/_core/views.py
- [[.fetch_view()]] - code - harness/_core/views.py
- [[.register()]] - code - harness/_core/views.py
- [[.validate_all()]] - code - harness/_core/views.py
- [[AirtableViewRegistry]] - code - harness/_core/views.py
- [[Paginated fetch by view ID with silent-zero-record detection.]] - rationale - harness/_core/views.py
- [[SilentDropError]] - code - harness/_core/views.py
- [[Verify all registered view IDs still exist in the Airtable metadata.]] - rationale - harness/_core/views.py
- [[ViewNotFoundError]] - code - harness/_core/views.py
- [[views.py]] - code - harness/_core/views.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_222_AirtableViewRegist
SORT file.name ASC
```

## Connections to other communities
- 5 edges to [[_COMMUNITY_Cluster 40 AirtableClient]]
- 3 edges to [[_COMMUNITY_Cluster 236 StructuredLogger]]

## Top bridge nodes
- [[AirtableViewRegistry]] - degree 7, connects to 2 communities
- [[SilentDropError]] - degree 5, connects to 2 communities
- [[ViewNotFoundError]] - degree 5, connects to 2 communities