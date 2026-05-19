---
type: community
cohesion: 0.09
members: 35
---

# Cluster 22: calc_outbound_qc_m

**Cohesion:** 0.09 - loosely connected
**Members:** 35 nodes

## Members
- [['88x88x163', '24819033', '200x300', '55x160mm 펼침...' → (W,H,D) mm.     cbm_inb]] - rationale - scripts/mh_calculator.py
- [[PT3137-...  PNA35889_어텐션스포츠보틀  ...' → 'PNA35889'.]] - rationale - scripts/mh_calculator.py
- [[PT3137-사각스티커  PNA35889_...' → 'PT3137'.]] - rationale - scripts/mh_calculator.py
- [[Paginated fetch. stop_predicate(record) → True 시 즉시 중단.     Karpathy filterByFo]] - rationale - scripts/mh_calculator.py
- [[TMS shipment 1건 = dispatch + docs MH_std.     returns (mh_std_minutes, basis, m]] - rationale - scripts/mh_calculator.py
- [[WMS movement은 receiving ledger. 실제입하일 + 입하 qty 보유 → 'receiving'.]] - rationale - scripts/mh_calculator.py
- [[_extract_project_code()]] - code - scripts/mh_calculator.py
- [[_extract_pt_code()]] - code - scripts/mh_calculator.py
- [[_parse_date()]] - code - scripts/mh_calculator.py
- [[_to_float()]] - code - scripts/mh_calculator.py
- [[calc_outbound_qc_mh_per_project()]] - code - scripts/mh_calculator.py
- [[calc_picking_mh()]] - code - scripts/mh_calculator.py
- [[calc_putaway_mh()]] - code - scripts/mh_calculator.py
- [[calc_qc_mh_per_project()]] - code - scripts/mh_calculator.py
- [[calc_receiving_mh()]] - code - scripts/mh_calculator.py
- [[calc_tms_shipment_mh()]] - code - scripts/mh_calculator.py
- [[calc_unloading_mh_for_project()]] - code - scripts/mh_calculator.py
- [[classify_movement()]] - code - scripts/mh_calculator.py
- [[generate_report()]] - code - scripts/mh_calculator.py
- [[get_records()]] - code - scripts/mh_calculator.py
- [[iso_week()]] - code - scripts/mh_calculator.py
- [[load_sync_parts_lookup()_1]] - code - scripts/mh_calculator.py
- [[main()_29]] - code - scripts/mh_calculator.py
- [[mh_calculator.py]] - code - scripts/mh_calculator.py
- [[mh_calculator.py ───────────────────────────────────────────────────────────────]] - rationale - scripts/mh_calculator.py
- [[parse_dims_mm()_1]] - code - scripts/mh_calculator.py
- [[spec_to_cbm()]] - code - scripts/mh_calculator.py
- [[sync_parts → {PT_code 규격} 1회 사전 로드. field ID 사용 (이름 변동 면역).]] - rationale - scripts/mh_calculator.py
- [[규격 문자열 × 수량 → CBM (m³). returns (cbm, parsed_ok).]] - rationale - scripts/mh_calculator.py
- [[입고 MH. 사용자 표명 적은 수량부피 3분 ~ 큰 부피·파렛트·다이어리 류 max 10분.     수식 base 3 + min(7, c]] - rationale - scripts/mh_calculator.py
- [[입하 MH_std. spec×qty→CBM 1차 path (cbm_inbound_check 로직 재사용).     우선순위       1]] - rationale - scripts/mh_calculator.py
- [[입하검수 프로젝트 1개당 표본검수 MH. caller가 distinct projects 갯수와 곱함.]] - rationale - scripts/mh_calculator.py
- [[출고검수 project 1개당 A3 박스 단위 매칭 MH. caller가 distinct outbound projects 갯수와 곱함.]] - rationale - scripts/mh_calculator.py
- [[피킹 MH_std. batch pick 패턴 자사는 piece가 박스바스켓에 묶여 있어     qty가 50~200이어도 핸들링 1~2]] - rationale - scripts/mh_calculator.py
- [[하차 MH. 사용자 측정 3~8분프로젝트 (mid 5.5min), CBM-weighted.]] - rationale - scripts/mh_calculator.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Cluster_22_calc_outbound_qc_m
SORT file.name ASC
```
