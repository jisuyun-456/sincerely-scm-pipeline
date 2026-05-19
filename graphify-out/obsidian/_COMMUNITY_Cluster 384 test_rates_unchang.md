---
type: community
cohesion: 0.40
members: 5
---

# Cluster 384: test_rates_unchang

**Cohesion:** 0.40 - moderately connected
**Members:** 5 nodes

## Members
- [[Fingerprint test — detects accidental changes to fare constants.  If this test f]] - rationale - tests/tms_settlement/test_rates_unchanged.py
- [[test_max_blocked_ratio_sentinel()]] - code - tests/tms_settlement/test_rates_unchanged.py
- [[test_rate_history_fingerprint()]] - code - tests/tms_settlement/test_rates_unchanged.py
- [[test_rates_unchanged.py]] - code - tests/tms_settlement/test_rates_unchanged.py
- [[test_withholding_rate_is_zero_until_t01_resolved()]] - code - tests/tms_settlement/test_rates_unchanged.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_384_test_rates_unchang
SORT file.name ASC
```
