---
type: community
cohesion: 0.36
members: 9
---

# Cluster 237: Notifier

**Cohesion:** 0.36 - loosely connected
**Members:** 9 nodes

## Members
- [[.__init__()_7]] - code - harness/_core/notifier.py
- [[._dedup_key()]] - code - harness/_core/notifier.py
- [[._is_duplicate()]] - code - harness/_core/notifier.py
- [[._try_github_issue()]] - code - harness/_core/notifier.py
- [[._try_gmail()]] - code - harness/_core/notifier.py
- [[._try_slack()]] - code - harness/_core/notifier.py
- [[.notify()]] - code - harness/_core/notifier.py
- [[Notifier]] - code - harness/_core/notifier.py
- [[notifier.py_1]] - code - harness/_core/notifier.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_237_Notifier
SORT file.name ASC
```

## Connections to other communities
- 3 edges to [[_COMMUNITY_Cluster 40 AirtableClient]]
- 1 edge to [[_COMMUNITY_Cluster 97 assert_week_in_win]]
- 1 edge to [[_COMMUNITY_Cluster 236 StructuredLogger]]
- 1 edge to [[_COMMUNITY_Cluster 250 Daily audit-vs-Air]]

## Top bridge nodes
- [[Notifier]] - degree 12, connects to 4 communities
- [[._try_github_issue()]] - degree 3, connects to 1 community
- [[._try_slack()]] - degree 3, connects to 1 community