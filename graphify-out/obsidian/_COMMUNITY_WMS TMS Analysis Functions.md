---
type: community
cohesion: 0.12
members: 40
---

# WMS TMS Analysis Functions

**Cohesion:** 0.12 - loosely connected
**Members:** 40 nodes

## Members
- [[CBM 우선순위 Total_CBM(수동)  박스파싱  product 예상(use_estimate=True일 때만)     use_esti]] - rationale - pages/generate_scm_report.py
- [[Product 마스터 → (정규화된 품목명, cbm_per_unit) 리스트 반환.     fldCeJ0RqSUGlfEw4 = CBM 필드]] - rationale - pages/generate_scm_report.py
- [[Sincerely SCM 통합 리포트 생성기 ======================================================]] - rationale - pages/generate_scm_report.py
- [[_c()]] - code - pages/generate_scm_report.py
- [[_calc_weekly_km_breakdown()]] - code - pages/generate_scm_report.py
- [[_fetch_all()]] - code - pages/generate_scm_report.py
- [[_get_with_retry()]] - code - pages/generate_scm_report.py
- [[_mat_headers()]] - code - pages/generate_scm_report.py
- [[_sel()]] - code - pages/generate_scm_report.py
- [[_tms_headers()]] - code - pages/generate_scm_report.py
- [[_wms_headers()]] - code - pages/generate_scm_report.py
- [[analyze_inbound()]] - code - pages/generate_scm_report.py
- [[analyze_picking()]] - code - pages/generate_scm_report.py
- [[analyze_qc()]] - code - pages/generate_scm_report.py
- [[analyze_tms()]] - code - pages/generate_scm_report.py
- [[fetch_additional_usage()]] - code - pages/generate_scm_report.py
- [[fetch_box_cbm_live()]] - code - pages/generate_scm_report.py
- [[fetch_issue_list()]] - code - pages/generate_scm_report.py
- [[fetch_movement()]] - code - pages/generate_scm_report.py
- [[fetch_picking()]] - code - pages/generate_scm_report.py
- [[fetch_product_cbm()]] - code - pages/generate_scm_report.py
- [[fetch_shipments_tms()]] - code - pages/generate_scm_report.py
- [[generate_scm_report.py]] - code - pages/generate_scm_report.py
- [[get_cbm_tms()]] - code - pages/generate_scm_report.py
- [[get_period_range()]] - code - pages/generate_scm_report.py
- [[inject_html()]] - code - pages/generate_scm_report.py
- [[last_week_range()]] - code - pages/generate_scm_report.py
- [[main()_13]] - code - pages/generate_scm_report.py
- [[next_week_range()]] - code - pages/generate_scm_report.py
- [[parse_box_cbm()]] - code - pages/generate_scm_report.py
- [[prev_month_range()]] - code - pages/generate_scm_report.py
- [[prev_week_range()]] - code - pages/generate_scm_report.py
- [[this_week_range()]] - code - pages/generate_scm_report.py
- [[view_type project  a1_to_partner     project       이동목적=조립투입 + 자재투입현황=자재]] - rationale - pages/generate_scm_report.py
- [[week_label_for()]] - code - pages/generate_scm_report.py
- [[week_number_of_month()]] - code - pages/generate_scm_report.py
- [[검수 로직 반영     - 취소 레코드 제외 후 집계     - 검수 건수 = 유효 입하건수 (표본 검수 방식이므로 모든 건에 대해 검수]] - rationale - pages/generate_scm_report.py
- [[자재관리 base sync_parts 테이블에서 2026 누적 추가사용액 조회.     기간별 금액은 fetch_issue_list()의 us]] - rationale - pages/generate_scm_report.py
- [[자재관리 base 재고팀_이슈정리 테이블 조회]] - rationale - pages/generate_scm_report.py
- [[피킹 레코드 → 건수 + 날짜별 건수 (project 임가공예정일 파싱 후 범위 필터링)]] - rationale - pages/generate_scm_report.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/WMS_TMS_Analysis_Functions
SORT file.name ASC
```

## Connections to other communities
- 6 edges to [[_COMMUNITY_Cluster 385 calc_routing()]]
- 4 edges to [[_COMMUNITY_Cluster 358 _bigram_dice()]]
- 1 edge to [[_COMMUNITY_Cluster 187 calc_cbm()]]
- 1 edge to [[_COMMUNITY_Cluster 235 calc_running_balan]]

## Top bridge nodes
- [[main()_13]] - degree 25, connects to 3 communities
- [[generate_scm_report.py]] - degree 39, connects to 2 communities
- [[_c()]] - degree 11, connects to 1 community
- [[get_cbm_tms()]] - degree 6, connects to 1 community