---
type: community
cohesion: 0.15
members: 17
---

# Cluster 97: assert_week_in_win

**Cohesion:** 0.15 - loosely connected
**Members:** 17 nodes

## Members
- [[Airtable fetch for settlement — uses field IDs in filterByFormula (via returnFie]] - rationale - harness/tms_settlement/fetch.py
- [[Fetch Shipment records for the week that include at least one settlement driver.]] - rationale - harness/tms_settlement/fetch.py
- [[Load CBM product lookup for 박종성 unload fee (optional — failure is non-fatal).]] - rationale - harness/tms_settlement/fetch.py
- [[Partition records by driver ID. Records with multiple drivers are     included o]] - rationale - harness/tms_settlement/fetch.py
- [[TMS Settlement — thin CLI orchestrator.  Usage   py -m harness.tms_settlement.m]] - rationale - harness/tms_settlement/main.py
- [[_end_excl()]] - code - harness/tms_settlement/fetch.py
- [[_parse_args()]] - code - harness/tms_settlement/main.py
- [[assert_week_in_window()]] - code - harness/_core/calendar.py
- [[calendar.py]] - code - harness/_core/calendar.py
- [[fetch.py]] - code - harness/tms_settlement/fetch.py
- [[fetch_week()_1]] - code - harness/tms_settlement/fetch.py
- [[load_cbm_lookup()]] - code - harness/tms_settlement/fetch.py
- [[main()_11]] - code - harness/tms_settlement/main.py
- [[main.py]] - code - harness/tms_settlement/main.py
- [[split_by_driver()]] - code - harness/tms_settlement/fetch.py
- [[today_kst()]] - code - harness/_core/calendar.py
- [[week_range()_1]] - code - harness/_core/calendar.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_97_assert_week_in_win
SORT file.name ASC
```

## Connections to other communities
- 1 edge to [[_COMMUNITY_CBM Backfill & Batch Ops]]
- 1 edge to [[_COMMUNITY_Cluster 214 assert_domain()]]
- 1 edge to [[_COMMUNITY_Cluster 237 Notifier]]
- 1 edge to [[_COMMUNITY_Cluster 205 verifier.py]]
- 1 edge to [[_COMMUNITY_Cluster 69 BatchedRunner]]
- 1 edge to [[_COMMUNITY_Cluster 251 write.py]]
- 1 edge to [[_COMMUNITY_Cluster 367 ConfigBase]]

## Top bridge nodes
- [[main()_11]] - degree 10, connects to 4 communities
- [[fetch.py]] - degree 6, connects to 1 community
- [[assert_week_in_window()]] - degree 4, connects to 1 community
- [[load_cbm_lookup()]] - degree 4, connects to 1 community