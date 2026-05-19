---
type: community
cohesion: 0.14
members: 24
---

# Cluster 66: analyze_iter1_volu

**Cohesion:** 0.14 - loosely connected
**Members:** 24 nodes

## Members
- [[Iteration 1 배송 볼륨 패턴]] - rationale - scripts/tms_weekly_runner.py
- [[Iteration 3 운송비 (배송방식 분포 기반 추정)]] - rationale - scripts/tms_weekly_runner.py
- [[Iteration 4 OTIF 실측 전환 현황 + 배송클레임 분석]] - rationale - scripts/tms_weekly_runner.py
- [[Iteration 6a 2026-05-04 백필(372건) 이후 구간유형 커버리지 측정]] - rationale - scripts/tms_weekly_runner.py
- [[_compute_week_label()]] - code - scripts/tms_weekly_runner.py
- [[_delta()]] - code - scripts/tms_weekly_runner.py
- [[_load_prior_kpis()]] - code - scripts/tms_weekly_runner.py
- [[_notify_slack_report()]] - code - scripts/tms_weekly_runner.py
- [[analyze_iter1_volume()]] - code - scripts/tms_weekly_runner.py
- [[analyze_iter3_cost()]] - code - scripts/tms_weekly_runner.py
- [[analyze_iter4_otif()]] - code - scripts/tms_weekly_runner.py
- [[analyze_iter6_post_backfill()]] - code - scripts/tms_weekly_runner.py
- [[get_all_records()_1]] - code - scripts/tms_weekly_runner.py
- [[main()_45]] - code - scripts/tms_weekly_runner.py
- [[patch_records()_1]] - code - scripts/tms_weekly_runner.py
- [[step_backfill()]] - code - scripts/tms_weekly_runner.py
- [[step_pull_data()]] - code - scripts/tms_weekly_runner.py
- [[step_save_report()]] - code - scripts/tms_weekly_runner.py
- [[step_update_log()]] - code - scripts/tms_weekly_runner.py
- [[tms_weekly_runner.py]] - code - scripts/tms_weekly_runner.py
- [[tms_weekly_runner.py ──────────────────────────────────────────────────────────]] - rationale - scripts/tms_weekly_runner.py
- [[실행일 기준 직전 주 레이블 계산.      Returns         week_id    2026-W16  (ISO 주차, 파일]] - rationale - scripts/tms_weekly_runner.py
- [[주간 AutoResearch 리포트 요약을 Slack DM으로 발송.]] - rationale - scripts/tms_weekly_runner.py
- [[직전 주 리포트에서 KPI 수치를 추출해 delta 계산용으로 반환.]] - rationale - scripts/tms_weekly_runner.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_66_analyze_iter1_volu
SORT file.name ASC
```

## Connections to other communities
- 5 edges to [[_COMMUNITY_Cluster 356 analyze_iter2_disp]]
- 3 edges to [[_COMMUNITY_Cluster 393 analyze_iter5_fore]]

## Top bridge nodes
- [[tms_weekly_runner.py]] - degree 21, connects to 2 communities
- [[main()_45]] - degree 14, connects to 2 communities