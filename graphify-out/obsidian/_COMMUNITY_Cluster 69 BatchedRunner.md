---
type: community
cohesion: 0.13
members: 22
---

# Cluster 69: BatchedRunner

**Cohesion:** 0.13 - loosely connected
**Members:** 22 nodes

## Members
- [[.__enter__()]] - code - harness/_core/runner.py
- [[.__exit__()]] - code - harness/_core/runner.py
- [[._check_free_space()]] - code - harness/_core/runner.py
- [[._install_sigterm()]] - code - harness/_core/runner.py
- [[._load_checkpoint()]] - code - harness/_core/runner.py
- [[._start_deadline_timer()]] - code - harness/_core/runner.py
- [[.check_shutdown()]] - code - harness/_core/runner.py
- [[.is_batch_done()]] - code - harness/_core/runner.py
- [[.is_done()]] - code - harness/_core/runner.py
- [[.mark_batch_done()]] - code - harness/_core/runner.py
- [[.mark_done()]] - code - harness/_core/runner.py
- [[.save_checkpoint()]] - code - harness/_core/runner.py
- [[BatchedRunner]] - code - harness/_core/runner.py
- [[Checkpoint at batch granularity using a hash of batch contents.]] - rationale - harness/_core/runner.py
- [[IdempotentRunner]] - code - harness/_core/runner.py
- [[WallClockDeadline]] - code - harness/_core/runner.py
- [[Wrap untrusted Airtable string values to prevent log injection.      Idempotent]] - rationale - harness/_core/sanitize.py
- [[assert_no_template_chars()]] - code - harness/_core/sanitize.py
- [[runner.py]] - code - harness/_core/runner.py
- [[sanitize.py]] - code - harness/_core/sanitize.py
- [[scrub_pii_in_state()]] - code - harness/_core/sanitize.py
- [[strip_control_chars()]] - code - harness/_core/sanitize.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_69_BatchedRunner
SORT file.name ASC
```

## Connections to other communities
- 3 edges to [[_COMMUNITY_Cluster 236 StructuredLogger]]
- 2 edges to [[_COMMUNITY_Cluster 214 assert_domain()]]
- 1 edge to [[_COMMUNITY_Cluster 97 assert_week_in_win]]
- 1 edge to [[_COMMUNITY_Cluster 251 write.py]]
- 1 edge to [[_COMMUNITY_Cluster 328 OutboundLedger]]

## Top bridge nodes
- [[IdempotentRunner]] - degree 16, connects to 4 communities
- [[WallClockDeadline]] - degree 4, connects to 2 communities
- [[BatchedRunner]] - degree 6, connects to 1 community
- [[runner.py]] - degree 4, connects to 1 community