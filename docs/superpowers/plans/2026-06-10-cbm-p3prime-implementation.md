# CBM Backbone P3' — 구현 기록 (part_cbm + 보관·입하 통합)

> Chain `cbm-capacity-backbone` P3' · 2026-06-10 실행 완료 · plan 원본: `~/.claude/plans/chain-nifty-aho.md`
> Specs: `2026-06-09-cbm-capacity-backbone-design.md` §1–§6 + `2026-06-10-cbm-connectivity-first-rescope-design.md` §3
> 검증: pytest **337 passed** + 1 known fail(W1, P5) · code-reviewer 3건 수정 · harness-validator **PASS 6/6 + must-not 4/4**

## 실행 결과 (커밋 8개)

| Task | 산출물 | 측정치 |
|---|---|---|
| T1 | `harness/backbone/part_cbm.py` (tier 사다리·QC버킷 tertile·sanity bounds) + `utils/cbm_utils.py` shim + `cbm_inbound_check.py` 중복 5함수 제거 | 18 tests. QC tertile: t1=2.635e-05 / t2=2.8653e-04 m³ (n=726, 2026-06-10) |
| T2 | `scripts/backbone/part_cbm_backfill.py` — **CP① 승인** 후 write | PT 837행 중 **356 해소(42.5%)**: sp 261 + mov 95. **351행 PATCH err=0**, 출처='치수파싱'(typecast 신설). 미산출: 규격없음 466·파싱실패 15. QC버킷 tier dormant(분류 소스 부재) |
| T7 | kit-CBM 재측정 (replay dry-run 전/후, 코드 변경 0) | **kit 폴백 0 → 108 엔트리** · 굿즈 CBM 커버리지 **86.7% → 89.2%** (176→181/203, Gate ≥85% PASS) · kit 적용 shipment 0→7 · **binding constraint = BOM 굿즈명→sync_item name-bridge** (1,702행 → 108 엔트리) — part_cbm 실패 아님 |
| T3 | `harness/backbone/storage.py` + `scripts/backbone/storage_occupied.py` (report-only) | **베스트원 occupied 306.24 m³** (ledger 433행, STORAGE·UNRESTRICTED). PT 커버리지 44.9%(135/301), 미해소 재고 295,852개 동반 보고. Max_CBM 주입 경로: `--max-cbm-seed` + `[미주입 보류]` 출력 검증 |
| T4 | `movement_purpose_profile.py` + `fetch_inbound_cbm(purposes·require_actual_date)` 인자화 — **CP② 승인** | 프로파일 26,051행 → **외부입하 = {생산산출, 재고생산, 고객물품}** (실제입하일·입하수량 보유율 94.8/94.7·93.4/86.7·93.1/96.6%). 실적 subset 4,889행 중 3,906 규격 해소 = **79.9% ≥70% gate PASS**, 총 2,156.79 m³ |
| T5 | `scripts/backbone/bom_component_type.py` — **CP③ 승인** 후 write | **630/1,702행(37.0%) PATCH err=0** (포장재 441·원부자재 186·임가공 3). 미매핑: PT_미등록 635(sync_parts 미러 밖 과거 PT)·Phantom 433·유형없음 4. 재실행 idempotent 확인(기적용 630·PATCH 0) |
| T6 | `harness/backbone/mes_forecast.py` + `scripts/backbone/mes_delivery_forecast.py` (read-only) | MES ver2.0 306행 → **다음 7d 2.49 m³ / 14d 4.83 m³**. join 30·코드 미매칭 114·과거 납기 158 정직 보고 |
| review | ZeroDivision 가드·MES v1 dead fetch 제거·join 라벨 명확화 | f39ffb4 |

## Gate 판정 (plan §Gate)

| Gate | 판정 | 증거 |
|---|---|---|
| ① part_cbm 커버리지+QC 분포 | ✅ | 42.5% (dims sp/mov 분리), QC 분포 소101/중123/대132, sanity 거부 15 |
| ② occupied 분자 + Max_CBM 경로 | ✅ | 306.24 m³ + 44.9% 커버리지 + 주입 경로 출력 (분모는 실측 도착 시) |
| ③ kit 자동 점등 측정 | ✅ | 0→108 엔트리, 86.7→89.2%, bridge 한계 명시 |
| ④ 소스 write 0·movement 쓰기 0·pytest | ✅ | PATCH는 ItemMaster·WMS_BOM(allowlist)만, Total_CBM 불가침, 337 green |

## 사용자 체크포인트 기록
- **CP①** 승인: 출처 choice '치수파싱' 신설(typecast — Meta API field update는 options 변경 미지원) + 351행 write. 'QC버킷' choice는 첫 사용 시 typecast 자동 생성 예정.
- **CP②** 승인: 외부입하 = 생산산출+재고생산+고객물품 (`EXTERNAL_INBOUND_PURPOSES`, 테스트로 고정). 재고이동(20.4%)·생산샘플(24.4%) 제외.
- **CP③** 승인: 구성유형 630행 PATCH. Phantom·키트 추측 금지 유지.

## Rollback
- ItemMaster: `출처='치수파싱'` 필터 351행 → CBM·출처 blank revert.
- WMS_BOM 구성유형: pre-state 전부 blank → 매핑된 630행 blank revert (스크립트 재실행으로 식별 가능).
- 기타 산출물 read-only.

## P4로 넘기는 것 / 미해결
- **Max_CBM 실측치** (베스트원·에이원센터/STORAGE 3존) — 도착 시: WMS_Location(`tblRwUTP5kWnHFt5P`)에 Max_CBM number 필드 신설 + `storage_occupied.py --max-cbm-seed` 검증 → 필드 영속화. **TMS Location.Max_CBM(`tblSObcLUA5iO1TTx`) 재사용 금지** (다른 물리량, spec §4 — 핸드오프의 해당 참조는 오기였음).
- 미산출 PT 481 (규격없음 466·파싱실패 15 — '23cm'·'펼침465x365' 등 개선 후보), QC버킷 분류 소스(IBSA CBM_지수는 규격 파생이라 독립 소스 아님 — 사용자 size-class 제공 시 점등).
- BOM name-bridge 개선(960/1,319 그룹 실패 — kit binding constraint), PT_미등록 635(과거 PT 소스 = P5 no_order와 동일 뿌리).
- 에이원센터 InventoryLedger 0행 (보관 분자가 베스트원 단일 — ledger 소스 확장 여부 P4~P5 판단).
