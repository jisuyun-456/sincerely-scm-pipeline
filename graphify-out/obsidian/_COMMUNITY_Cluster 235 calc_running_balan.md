---
type: community
cohesion: 0.27
members: 10
---

# Cluster 235: calc_running_balan

**Cohesion:** 0.27 - loosely connected
**Members:** 10 nodes

## Members
- [[TMS Shipment.총 CBM 기간 합계.     sinceuntil 출하일 범위 (inclusive). until 미지정 시 오늘까지.]] - rationale - scripts/wms_cbm_ledger.py
- [[YTD 또는 지정 기간의 입하 vs 출하 CBM 대비로 창고 Running Balance 계산.      Returns       since]] - rationale - scripts/wms_cbm_ledger.py
- [[_tms_headers()_1]] - code - scripts/wms_cbm_ledger.py
- [[calc_running_balance()]] - code - scripts/wms_cbm_ledger.py
- [[get_total_outbound_cbm()]] - code - scripts/wms_cbm_ledger.py
- [[get_weekly_inbound_cbm()]] - code - scripts/wms_cbm_ledger.py
- [[main()_47]] - code - scripts/wms_cbm_ledger.py
- [[scriptswms_cbm_ledger.py ──────────────────────────────────────────────────────]] - rationale - scripts/wms_cbm_ledger.py
- [[wms_cbm_ledger.py]] - code - scripts/wms_cbm_ledger.py
- [[주간 입하 CBM 합계. week_str 예 '2026-W21'.]] - rationale - scripts/wms_cbm_ledger.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_235_calc_running_balan
SORT file.name ASC
```

## Connections to other communities
- 2 edges to [[_COMMUNITY_Cluster 187 calc_cbm()]]
- 1 edge to [[_COMMUNITY_WMS TMS Analysis Functions]]
- 1 edge to [[_COMMUNITY_Cluster 23 analyze_cbm_balanc]]

## Top bridge nodes
- [[calc_running_balance()]] - degree 7, connects to 3 communities
- [[get_weekly_inbound_cbm()]] - degree 3, connects to 1 community