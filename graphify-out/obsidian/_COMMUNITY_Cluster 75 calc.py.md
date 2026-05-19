---
type: community
cohesion: 0.17
members: 21
---

# Cluster 75: calc.py

**Cohesion:** 0.17 - loosely connected
**Members:** 21 nodes

## Members
- [[MM 외주임가공 → 다영기획 배송 여부.      SC id starts with 'MM' + destination contains '다영기획']] - rationale - harness/tms_settlement/calc.py
- [[PNA 프로젝트 고객납품건 — project code contains 'PNA'.]] - rationale - harness/tms_settlement/calc.py
- [[Parse box counts from formula string → 상하차비용, capped at 50,000 KRW.]] - rationale - harness/tms_settlement/calc.py
- [[Pure fare calculation functions — no IO, no Airtable calls.  SettlementItem.far]] - rationale - harness/tms_settlement/calc.py
- [[Return (gross, withholding, net). withholding=0 until T0-1 is resolved.]] - rationale - harness/tms_settlement/calc.py
- [[Return the fare rate row effective on `target_date` (YYYY-MM-DD).]] - rationale - harness/tms_settlement/config.py
- [[SettlementItem]] - code - harness/tms_settlement/calc.py
- [[_apply_withholding()]] - code - harness/tms_settlement/calc.py
- [[_is_outsource()_1]] - code - harness/tms_settlement/calc.py
- [[_is_pna()_1]] - code - harness/tms_settlement/calc.py
- [[_make_item()]] - code - harness/tms_settlement/calc.py
- [[_parse_unload_fee()]] - code - harness/tms_settlement/calc.py
- [[_str_field()_2]] - code - harness/tms_settlement/calc.py
- [[calc.py]] - code - harness/tms_settlement/calc.py
- [[calc_cho()_1]] - code - harness/tms_settlement/calc.py
- [[calc_lee()_1]] - code - harness/tms_settlement/calc.py
- [[calc_park()_1]] - code - harness/tms_settlement/calc.py
- [[rates_for()]] - code - harness/tms_settlement/config.py
- [[박종성       일반건 haversine × road_factor × park_km + park_base (ceiling 500)]] - rationale - harness/tms_settlement/calc.py
- [[이장훈 160,000원day ÷ 당일 배송건수 (ceiling to 500 KRW).]] - rationale - harness/tms_settlement/calc.py
- [[조희선 (360,000 + max(0, 경기도건수-1)×30,000)  당일 배송건수.]] - rationale - harness/tms_settlement/calc.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_75_calcpy
SORT file.name ASC
```

## Connections to other communities
- 1 edge to [[_COMMUNITY_CBM Backfill & Batch Ops]]
- 1 edge to [[_COMMUNITY_Cluster 205 verifier.py]]
- 1 edge to [[_COMMUNITY_Cluster 251 write.py]]
- 1 edge to [[_COMMUNITY_Cluster 345 ConfigBase]]

## Top bridge nodes
- [[SettlementItem]] - degree 4, connects to 2 communities
- [[calc_park()_1]] - degree 9, connects to 1 community
- [[rates_for()]] - degree 5, connects to 1 community