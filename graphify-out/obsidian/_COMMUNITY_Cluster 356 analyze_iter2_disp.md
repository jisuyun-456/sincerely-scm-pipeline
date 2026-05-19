---
type: community
cohesion: 0.33
members: 6
---

# Cluster 356: analyze_iter2_disp

**Cohesion:** 0.33 - loosely connected
**Members:** 6 nodes

## Members
- [[Iteration 2 배송 효율 (내부 소화율 + 기사별 운행일)]] - rationale - scripts/tms_weekly_runner.py
- [[Iteration 6b 고고엑스 내부 흡수 가능성 갭 분석 (CBM 기준)]] - rationale - scripts/tms_weekly_runner.py
- [[analyze_iter2_dispatch_efficiency()]] - code - scripts/tms_weekly_runner.py
- [[analyze_iter6_absorption_gap()]] - code - scripts/tms_weekly_runner.py
- [[classify_partner()]] - code - scripts/tms_weekly_runner.py
- [[배송파트너 이름 → 'internal'  'gogox'  'external]] - rationale - scripts/tms_weekly_runner.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_356_analyze_iter2_disp
SORT file.name ASC
```

## Connections to other communities
- 5 edges to [[_COMMUNITY_Cluster 66 analyze_iter1_volu]]
- 2 edges to [[_COMMUNITY_Cluster 71 _actual_weekly_shi]]
- 1 edge to [[_COMMUNITY_Cluster 201 analyze_iter8_driv]]

## Top bridge nodes
- [[classify_partner()]] - degree 7, connects to 3 communities
- [[analyze_iter2_dispatch_efficiency()]] - degree 4, connects to 1 community
- [[analyze_iter6_absorption_gap()]] - degree 4, connects to 1 community