---
type: community
cohesion: 0.18
members: 17
---

# Cluster 109: conftest.py

**Cohesion:** 0.18 - loosely connected
**Members:** 17 nodes

## Members
- [[NOTE 해운대구 contains 대구 as a substring → Daegu false-match; use 수영구]] - rationale - tests/tms_settlement/test_calc_golden.py
- [[Build a minimal fake Airtable Shipment record for unit tests.]] - rationale - tests/tms_settlement/conftest.py
- [[Golden suite — 10 cases locking in fare calc correctness.  Lee  ×2 2-ship day (]] - rationale - tests/tms_settlement/test_calc_golden.py
- [[Shared record builder for tms_settlement calc tests.  All tests use raw dict rec]] - rationale - tests/tms_settlement/conftest.py
- [[conftest.py]] - code - tests/tms_settlement/conftest.py
- [[rec()]] - code - tests/tms_settlement/conftest.py
- [[test_calc_golden.py]] - code - tests/tms_settlement/test_calc_golden.py
- [[test_cho_gyeonggi1_seoul1()]] - code - tests/tms_settlement/test_calc_golden.py
- [[test_cho_gyeonggi3()]] - code - tests/tms_settlement/test_calc_golden.py
- [[test_lee_three_ships_same_day()]] - code - tests/tms_settlement/test_calc_golden.py
- [[test_lee_two_ships_same_day()]] - code - tests/tms_settlement/test_calc_golden.py
- [[test_park_busan()]] - code - tests/tms_settlement/test_calc_golden.py
- [[test_park_gangnam()]] - code - tests/tms_settlement/test_calc_golden.py
- [[test_park_gwangju()]] - code - tests/tms_settlement/test_calc_golden.py
- [[test_park_no_coord()]] - code - tests/tms_settlement/test_calc_golden.py
- [[test_park_outsource_single()]] - code - tests/tms_settlement/test_calc_golden.py
- [[test_park_unload_fee()]] - code - tests/tms_settlement/test_calc_golden.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_109_conftestpy
SORT file.name ASC
```
