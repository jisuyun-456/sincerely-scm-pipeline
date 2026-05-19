---
type: community
cohesion: 0.16
members: 22
---

# Cluster 71: _actual_weekly_shi

**Cohesion:** 0.16 - loosely connected
**Members:** 22 nodes

## Members
- [[3 scenarios over 12 months, monthly NPV     S1 박종성 +7일월 추가 운행 (marginal cost]] - rationale - scripts/tms_iter7_analyzer.py
- [[Backtest W17W18W19 forecast came from prior week report.     W17 forecast ← W]] - rationale - scripts/tms_iter7_analyzer.py
- [[Count shipments (출하확정일) in the Mon-Fri window.]] - rationale - scripts/tms_iter7_analyzer.py
- [[Extract '주간 예측 합계 N건' from a weekly report.]] - rationale - scripts/tms_iter7_analyzer.py
- [[Gate C5 smoke-test all 4 analyzer functions with a minimal in-memory fixture.]] - rationale - scripts/tms_iter7_analyzer.py
- [[Per-week v1 (count-based) vs v2 (CBM-weighted) utilization.     Pearson r and Bl]] - rationale - scripts/tms_iter7_analyzer.py
- [[Pull data for `weeks` weeks window. Same structure as runner's step_pull_data.]] - rationale - scripts/tms_iter7_analyzer.py
- [[_actual_weekly_shipments()]] - code - scripts/tms_iter7_analyzer.py
- [[_build_report()]] - code - scripts/tms_iter7_analyzer.py
- [[_parse_forecast_total()]] - code - scripts/tms_iter7_analyzer.py
- [[_pearson_r()]] - code - scripts/tms_iter7_analyzer.py
- [[_run_self_test()]] - code - scripts/tms_iter7_analyzer.py
- [[_save_outputs()]] - code - scripts/tms_iter7_analyzer.py
- [[analyze_iter7_forecast_mape()]] - code - scripts/tms_iter7_analyzer.py
- [[analyze_iter7_internal_rate_3way_roi()]] - code - scripts/tms_iter7_analyzer.py
- [[analyze_iter7_lane_cbm()]] - code - scripts/tms_iter7_analyzer.py
- [[analyze_iter7_v1_v2_shadow()]] - code - scripts/tms_iter7_analyzer.py
- [[main()_42]] - code - scripts/tms_iter7_analyzer.py
- [[step_pull_data_6weeks()]] - code - scripts/tms_iter7_analyzer.py
- [[tms_iter7_analyzer.py]] - code - scripts/tms_iter7_analyzer.py
- [[tms_iter7_analyzer.py ──────────────────────────────────────────────────────────]] - rationale - scripts/tms_iter7_analyzer.py
- [[구간유형(lane)별 평균 CBM 분포 및 고고엑스 흡수 잠재력.]] - rationale - scripts/tms_iter7_analyzer.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_71__actual_weekly_shi
SORT file.name ASC
```

## Connections to other communities
- 2 edges to [[_COMMUNITY_Cluster 356 analyze_iter2_disp]]

## Top bridge nodes
- [[analyze_iter7_internal_rate_3way_roi()]] - degree 5, connects to 1 community
- [[_build_report()]] - degree 3, connects to 1 community