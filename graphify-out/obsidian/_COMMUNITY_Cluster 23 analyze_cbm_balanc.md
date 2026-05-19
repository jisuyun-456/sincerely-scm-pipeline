---
type: community
cohesion: 0.09
members: 35
---

# Cluster 23: analyze_cbm_balanc

**Cohesion:** 0.09 - loosely connected
**Members:** 35 nodes

## Members
- [[Iter 4~7 SAP EWM 섹션 마크다운 빌드]] - rationale - scripts/wms_weekly_runner.py
- [[Iter 8~11 CBM 섹션 마크다운 빌드.]] - rationale - scripts/wms_weekly_runner.py
- [[WMS_GoodsReceipt  WMS_InventoryLedger  WMS_Wave  WMS_PickingTask Pull]] - rationale - scripts/wms_weekly_runner.py
- [[WMS_GoodsReceipt.defect_code 기반 QC 불량코드 Pareto]] - rationale - scripts/wms_weekly_runner.py
- [[WMS_GoodsReceipt.dock_to_stock_min 기반 Dock-to-Stock KPI]] - rationale - scripts/wms_weekly_runner.py
- [[WMS_GoodsReceipt.promised_date vs received_at 기반 공급사 납기 준수율]] - rationale - scripts/wms_weekly_runner.py
- [[WMS_InventoryLedger × WMS_PickingTask 기반 재고 정확도]] - rationale - scripts/wms_weekly_runner.py
- [[YTD 창고 Running Balance 계산.]] - rationale - scripts/wms_weekly_runner.py
- [[_build_cbm_section()]] - code - scripts/wms_weekly_runner.py
- [[_build_sap_section()]] - code - scripts/wms_weekly_runner.py
- [[_compute_week_label()_1]] - code - scripts/wms_weekly_runner.py
- [[analyze_cbm_balance()]] - code - scripts/wms_weekly_runner.py
- [[analyze_cbm_dts_corr()]] - code - scripts/wms_weekly_runner.py
- [[analyze_cbm_weekly()]] - code - scripts/wms_weekly_runner.py
- [[analyze_dock_to_stock()]] - code - scripts/wms_weekly_runner.py
- [[analyze_inventory_accuracy()]] - code - scripts/wms_weekly_runner.py
- [[analyze_qc_defect()]] - code - scripts/wms_weekly_runner.py
- [[analyze_qc_pareto()]] - code - scripts/wms_weekly_runner.py
- [[analyze_supplier_lead_time()]] - code - scripts/wms_weekly_runner.py
- [[analyze_supplier_ontime()]] - code - scripts/wms_weekly_runner.py
- [[analyze_volume_trend()]] - code - scripts/wms_weekly_runner.py
- [[get_all_records()_2]] - code - scripts/wms_weekly_runner.py
- [[main()_50]] - code - scripts/wms_weekly_runner.py
- [[movement.이동목적 × 생성일자 주간 집계]] - rationale - scripts/wms_weekly_runner.py
- [[parse_date()_1]] - code - scripts/wms_weekly_runner.py
- [[step_pull_data()_1]] - code - scripts/wms_weekly_runner.py
- [[step_pull_sap_data()]] - code - scripts/wms_weekly_runner.py
- [[step_save_report()_1]] - code - scripts/wms_weekly_runner.py
- [[step_update_log()_1]] - code - scripts/wms_weekly_runner.py
- [[wms_weekly_runner.py]] - code - scripts/wms_weekly_runner.py
- [[wms_weekly_runner.py ───────────────────────────────────────────────────────────]] - rationale - scripts/wms_weekly_runner.py
- [[미입하 발생이력 checkbox 기반 공급사별 미입하 건수 + 입하예상일 vs 실제입하일 diff]] - rationale - scripts/wms_weekly_runner.py
- [[이동목적(생산산출재고생산) × 이슈카테고리 multiSelect 기반 QC proxy]] - rationale - scripts/wms_weekly_runner.py
- [[이번 주 입하 CBM 집계 + 창고 용적 신호.]] - rationale - scripts/wms_weekly_runner.py
- [[일별 입하 CBM vs Dock-to-Stock 평균 상관 분석.]] - rationale - scripts/wms_weekly_runner.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_23_analyze_cbm_balanc
SORT file.name ASC
```

## Connections to other communities
- 1 edge to [[_COMMUNITY_Cluster 235 calc_running_balan]]
- 1 edge to [[_COMMUNITY_Cluster 187 calc_cbm()]]

## Top bridge nodes
- [[analyze_cbm_balance()]] - degree 4, connects to 1 community
- [[analyze_cbm_weekly()]] - degree 4, connects to 1 community