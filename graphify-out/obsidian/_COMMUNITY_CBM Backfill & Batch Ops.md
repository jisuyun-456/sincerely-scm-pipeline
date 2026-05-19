---
type: community
cohesion: 0.05
members: 62
---

# CBM Backfill & Batch Ops

**Cohesion:** 0.05 - loosely connected
**Members:** 62 nodes

## Members
- [[10건 이하 batch PATCH. Returns (ok_count, error_count).]] - rationale - scripts/backfill/backfill_total_cbm_safe.py
- [[500원 단위 올림 — 1~499원은 500원으로, 501~999원은 1,000원으로]] - rationale - harness/settlement/settlement_calc.py
- [[CBM 기반 상하차비용 + 총 CBM 계산 공용 모듈. Product 테이블(tblBNh6oGDlTKGrdQ)에서 품목 룩업을 빌드하고, 출]] - rationale - harness/settlement/cbm_calc.py
- [[Fetch all Shipments for the given week with a 배송파트너 linked.]] - rationale - harness/settlement/settlement_calc.py
- [[MM 외주임가공 → 다영기획 배송 여부 판별.     SC id가 'MM'으로 시작 + 수령인(주소)에 '다영기획' + 배송요청사항에 '외주임]] - rationale - harness/settlement/settlement_calc.py
- [[PNA 프로젝트 고객납품건 여부 — project code 필드에 'PNA' 포함.]] - rationale - harness/settlement/settlement_calc.py
- [[Product 테이블 전체 조회 → 품목명(lower)견적코드(lower) → entry dict.     entry {rec_id, na]] - rationale - harness/settlement/cbm_calc.py
- [[Return (monday, sunday) ISO dates for the week containing week_start.]] - rationale - harness/settlement/settlement_calc.py
- [[Total_CBM = 0 또는 blank인 Shipment 전체 조회.]] - rationale - scripts/backfill/backfill_total_cbm_safe.py
- [[Total_CBM 안전 소급 백필.  - 대상 전체 Shipment 중 Total_CBM = 0 또는 미입력인 건 - 상하차비용(F_UN]] - rationale - scripts/backfill/backfill_total_cbm_safe.py
- [[Update 운송비용 and 상하차비용 on a Shipment record.]] - rationale - harness/settlement/settlement_calc.py
- [[_is_outsource()]] - code - harness/settlement/settlement_calc.py
- [[_is_pna()]] - code - harness/settlement/settlement_calc.py
- [[_jaccard()]] - code - harness/settlement/cbm_calc.py
- [[_patch_batch()]] - code - scripts/backfill/backfill_total_cbm_safe.py
- [[_round500()]] - code - harness/settlement/settlement_calc.py
- [[_str()_3]] - code - scripts/backfill/backfill_total_cbm_safe.py
- [[_str()_4]] - code - scripts/backfill/backfill_상하차비용.py
- [[_str()_2]] - code - harness/settlement/simulate_park_dayoung_cbm.py
- [[_str_field()_1]] - code - harness/settlement/settlement_calc.py
- [[_tokenize()]] - code - harness/settlement/cbm_calc.py
- [[backfill_total_cbm_safe.py]] - code - scripts/backfill/backfill_total_cbm_safe.py
- [[backfill_상하차비용.py]] - code - scripts/backfill/backfill_상하차비용.py
- [[calc_cho()]] - code - harness/settlement/settlement_calc.py
- [[calc_from_products()]] - code - harness/settlement/cbm_calc.py
- [[calc_lee()]] - code - harness/settlement/settlement_calc.py
- [[calc_park()]] - code - harness/settlement/settlement_calc.py
- [[cbm_calc.py]] - code - harness/settlement/cbm_calc.py
- [[estimate_dest_coord()_1]] - code - harness/settlement/settlement_calc.py
- [[fetch_empty_cbm_records()]] - code - scripts/backfill/backfill_total_cbm_safe.py
- [[fetch_park_dayoung()]] - code - harness/settlement/simulate_park_dayoung_cbm.py
- [[fetch_park_records()_1]] - code - scripts/backfill/backfill_상하차비용.py
- [[fetch_week()]] - code - harness/settlement/settlement_calc.py
- [[haversine_km()_1]] - code - harness/settlement/settlement_calc.py
- [[load_product_lookup()]] - code - harness/settlement/cbm_calc.py
- [[main()_55]] - code - scripts/backfill/backfill_total_cbm_safe.py
- [[main()_56]] - code - scripts/backfill/backfill_상하차비용.py
- [[main()_9]] - code - harness/settlement/settlement_calc.py
- [[main()_10]] - code - harness/settlement/simulate_park_dayoung_cbm.py
- [[match_product()]] - code - harness/settlement/cbm_calc.py
- [[notify_slack()]] - code - harness/settlement/settlement_calc.py
- [[parse_product_lines()]] - code - harness/settlement/cbm_calc.py
- [[parse_unload_fee()_2]] - code - scripts/backfill/backfill_상하차비용.py
- [[parse_unload_fee()_1]] - code - harness/settlement/settlement_calc.py
- [[patch_record()]] - code - scripts/backfill/backfill_상하차비용.py
- [[run()_22]] - code - scripts/backfill/backfill_total_cbm_safe.py
- [[run()_26]] - code - scripts/backfill/backfill_상하차비용.py
- [[settlement_calc.py]] - code - harness/settlement/settlement_calc.py
- [[simulate_park_dayoung_cbm.py]] - code - harness/settlement/simulate_park_dayoung_cbm.py
- [[today_iso()]] - code - harness/settlement/settlement_calc.py
- [[update_record()]] - code - harness/settlement/settlement_calc.py
- [[week_range()]] - code - harness/settlement/settlement_calc.py
- [[기사님 운임비 정산 자동화 스크립트 Usage   py harnesssettlementsettlement_calc.py --week 2]] - rationale - harness/settlement/settlement_calc.py
- [[박종성 + 다영기획 출발 Shipment 조회.]] - rationale - harness/settlement/simulate_park_dayoung_cbm.py
- [[박종성 다영기획 출발 상하차비용 CBM 시뮬레이션 (2024-01-01 ~ 현재)  목적   - F_BOX_TEXT(외박스 수량 rollup)]] - rationale - harness/settlement/simulate_park_dayoung_cbm.py
- [[박종성 상하차비용 + Total_CBM 소급 백필.  대상 박종성 담당 전체 Shipment (2024-01~현재) 중 상하차비용=0 또는]] - rationale - scripts/backfill/backfill_상하차비용.py
- [[박종성       일반건 운송비용 = PARK_BASE_FARE + PARK_KM_RATE × road_km               상]] - rationale - harness/settlement/settlement_calc.py
- [[이장훈 160,000원day ÷ 당일 배송건수]] - rationale - harness/settlement/settlement_calc.py
- [[조희선 (360,000 + max(0, 경기도건수-1) × 30,000)  당일 배송건수     경기도 판단 수령인(주소) 에 '경기']] - rationale - harness/settlement/settlement_calc.py
- [[출하 품목+수량 텍스트 → (품목명, 수량), ....     수량 없으면 0 반환.     예 굿이너프 비치타월×40  Solid]] - rationale - harness/settlement/cbm_calc.py
- [[품목+수량 텍스트 → {unload_fee, total_cbm, matched, unmatched}.      qty_hint]] - rationale - harness/settlement/cbm_calc.py
- [[품목명 → lookup 매칭. exact 먼저, 실패 시 Jaccard(≥0.4).     Returns (matched_key, entry]] - rationale - harness/settlement/cbm_calc.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/CBM_Backfill__Batch_Ops
SORT file.name ASC
```

## Connections to other communities
- 1 edge to [[_COMMUNITY_Cluster 97 assert_week_in_win]]
- 1 edge to [[_COMMUNITY_Cluster 75 calc.py]]

## Top bridge nodes
- [[calc_from_products()]] - degree 9, connects to 1 community
- [[load_product_lookup()]] - degree 7, connects to 1 community