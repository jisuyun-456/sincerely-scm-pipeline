---
type: community
cohesion: 0.22
members: 14
---

# Cluster 187: calc_cbm()

**Cohesion:** 0.22 - loosely connected
**Members:** 14 nodes

## Members
- [['88x88x163', '24819033', '200x300', '55x160mm 펼침...' 파싱.     Returns (W, H, D)]] - rationale - utils/cbm_utils.py
- [['이동물품' 필드 파싱.     형식 PT3137-사각스티커_화이트  PNA35889_어텐션스포츠보틀  에이원지식산업센터]] - rationale - utils/cbm_utils.py
- [[_headers()_2]] - code - utils/cbm_utils.py
- [[calc_cbm()_1]] - code - utils/cbm_utils.py
- [[cbm_utils.py]] - code - utils/cbm_utils.py
- [[fetch_inbound_cbm()]] - code - utils/cbm_utils.py
- [[get_all_records()_3]] - code - utils/cbm_utils.py
- [[load_sync_parts_lookup()_2]] - code - utils/cbm_utils.py
- [[movement(이동목적=생산산출) 조회 → CBM 집계.     sinceuntil 입하예상일 범위 (inclusive).     week]] - rationale - utils/cbm_utils.py
- [[parse_date()_2]] - code - utils/cbm_utils.py
- [[parse_dims_mm()_2]] - code - utils/cbm_utils.py
- [[parse_inbound_item()_1]] - code - utils/cbm_utils.py
- [[utilscbm_utils.py ─────────────────────────────────────────────────────────────]] - rationale - utils/cbm_utils.py
- [[치수 문자열 × 수량 → CBM (m³). Returns (cbm, ok).]] - rationale - utils/cbm_utils.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_187_calc_cbm
SORT file.name ASC
```

## Connections to other communities
- 2 edges to [[_COMMUNITY_Cluster 235 calc_running_balan]]
- 1 edge to [[_COMMUNITY_WMS TMS Analysis Functions]]
- 1 edge to [[_COMMUNITY_Cluster 23 analyze_cbm_balanc]]

## Top bridge nodes
- [[fetch_inbound_cbm()]] - degree 10, connects to 3 communities