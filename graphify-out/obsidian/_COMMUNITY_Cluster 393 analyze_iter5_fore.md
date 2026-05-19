---
type: community
cohesion: 0.50
members: 4
---

# Cluster 393: analyze_iter5_fore

**Cohesion:** 0.50 - moderately connected
**Members:** 4 nodes

## Members
- [[2026-W18', '화' → 해당 주 그 요일의 date 반환 (공휴일 필터링용)]] - rationale - scripts/tms_weekly_runner.py
- [[Iteration 5 다음 주 배송 볼륨 예측 (요일 패턴 기반)]] - rationale - scripts/tms_weekly_runner.py
- [[_week_day_date()]] - code - scripts/tms_weekly_runner.py
- [[analyze_iter5_forecast()]] - code - scripts/tms_weekly_runner.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_393_analyze_iter5_fore
SORT file.name ASC
```

## Connections to other communities
- 3 edges to [[_COMMUNITY_Cluster 66 analyze_iter1_volu]]

## Top bridge nodes
- [[analyze_iter5_forecast()]] - degree 4, connects to 1 community
- [[_week_day_date()]] - degree 3, connects to 1 community