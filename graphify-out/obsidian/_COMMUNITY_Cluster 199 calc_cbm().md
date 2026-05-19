---
type: community
cohesion: 0.26
members: 13
---

# Cluster 199: calc_cbm()

**Cohesion:** 0.26 - loosely connected
**Members:** 13 nodes

## Members
- [['88x88x163', '24819033', '200x300', '55x160mm 펼침...' 등 파싱.     Returns (W, H,]] - rationale - scripts/cbm_inbound_check.py
- [[calc_cbm()]] - code - scripts/cbm_inbound_check.py
- [[cbm_inbound_check.py]] - code - scripts/cbm_inbound_check.py
- [[cbm_inbound_check.py ───────────────────────────────────────────────────────────]] - rationale - scripts/cbm_inbound_check.py
- [[get_all_records()]] - code - scripts/cbm_inbound_check.py
- [[load_sync_parts_lookup()]] - code - scripts/cbm_inbound_check.py
- [[main()_20]] - code - scripts/cbm_inbound_check.py
- [[parse_date()]] - code - scripts/cbm_inbound_check.py
- [[parse_dims_mm()]] - code - scripts/cbm_inbound_check.py
- [[parse_inbound_item()]] - code - scripts/cbm_inbound_check.py
- [[parse_week()]] - code - scripts/cbm_inbound_check.py
- [[이동물품 파싱.     형식 PT3137-사각스티커_화이트  PNA35889_어텐션스포츠보틀  에이원지식산업센터]] - rationale - scripts/cbm_inbound_check.py
- [[치수 문자열 × 수량 → CBM (m³).     Returns (cbm, parsed_ok)]] - rationale - scripts/cbm_inbound_check.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_199_calc_cbm
SORT file.name ASC
```
