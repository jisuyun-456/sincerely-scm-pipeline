# 신시어리 SCM — CBM·BOM 부피 캐파 백본 설계 (배선·백필·가드레일)

> 작성일 2026-06-09 · superpowers:brainstorming 산출 · 대상 base: WMS `appLui4ZR5HWcQRri` / TMS `app4x70a8mOrIKsMf` / MES `appNSAPadsHbfaSHv`(SCR Production MES)
> 근거: 3-base 전수 인벤토리 + 7-critic 적대적 gap 분석(~572K tokens). 선행 설계 `2026-06-09-bom-cbm-backbone-design.md`(Phase-1) 후속.
> 상태: **승인됨** (ExitPlanMode 2026-06-09). 구 chain `bom-cbm-phase2` 재스코프·superseded.

---

## 0. Executive Summary — 핵심 재정의

신시어리 물류팀의 CBM/BOM 자동화는 **새로 만드는 게 아니라, 이미 깔린 기계에 CBM을 흘려넣고 + 백필 + 가드레일**을 거는 일이다.

**문제(실측):** TMS Shipment 16,190건 중 CBM 보유 **15.8%뿐(84.2% 공란)** → 배차 스케줄링·출하볼륨 예측·입하/보관 적재율·WMS M/H 전부 산정 불가.

**근본 원인:** 키 코드는 **이미 스파인에 다 있는데 백본이 안 읽는다.**
- `order.굿즈코드 (from sync_itemdb)` 99.9% · `order.project_code` 100% · `movement` PT#### 99%.
- `견적코드` = `sync_goods.Goods Code 2` = `order.굿즈코드` (243개 일치, 동일 4-char 체계).
- `harness/settlement/cbm_calc.load_product_lookup`이 **견적코드로 색인까지 해두고 호출 안 함** — `harness/dispatch/cbm_estimator.estimate_shipment_cbm`(line 171)은 `최종 출하 품목` free-text를 이름 퍼지매칭만 함.
- 결과: 출고 CBM이 전부 퍼지매칭 의존(84% 실패). 추가로 `backfill_total_cbm_safe.py`가 추정치를 `Total_CBM`(실측 SSOT)에 써 2,553행 오염.

**재정의:** 출고 체인(estimator · `Shipment.estimated_cbm`/`estimation_confidence`/`estimation_updated_at` · `wave_recommender` CBM coalesce · 배차일지/Capa/운임/배송파트너 CBM 롤업)은 **전부 배선돼 있고 입력 CBM 숫자 1개만 기다린다.** 진짜 새로 만들 건 작다.

---

## 1. 아키텍처 불변식 (반드시 준수)

- **Derived Native Propagation Layer:** 소스(⚡미러=SERPA sync, MES, TMS *입력* 필드)는 READ-ONLY. 쓰기는 네이티브 `WMS_*` + TMS-native 자동화 필드(`estimated_cbm`/wave 등)에만.
- **Immutable Ledger:** movement/ledger INSERT-only. 추정 vs 실측 분리(추정→`estimated_cbm`, 실측→`Total_CBM`).
- **No silent under-count:** 모든 CBM 숫자에 **커버리지% + 신뢰도** 동반.

---

## 2. 확정 결정 (사용자 승인)

1. **추정 CBM → `estimated_cbm`로 분리.** `Total_CBM`은 실측 전용. 기존 2,553 자동기입행 재분류 검토, `backfill_total_cbm_safe.py` auto경로 freeze.
2. **부분출하 = skip + 폴백.** 1출하 프로젝트(95%)만 결정론 풀 CBM(conf 1.0). 다차 출하는 `partial_skip`(conf 0) + 기존 퍼지 estimator 폴백.
3. **누락 굿즈코드(SSSV 등 20개) = sync_goods에서 먼저 백필.** 243 일치 코드로 TMS Product 보충 후 출고 백필.
4. **빌드 순서 = P0 안전 + P1 출고 먼저.** 본 spec은 3트랙 전체를 다루되 구현은 P0→P5.

**권장 디폴트(체크포인트 조정 가능):** qty=`주문수량` primary·`발주요청수량` fallback / wave 자동배차 신뢰도 floor **0.8** / STORAGE Phase-1 point-in-time만 / 128 WMS-only·19% blank-code = 범위 외 / TMS↔WMS 조인키 = PNA project_code.

---

## 3. 3트랙 (CBM 3종류) + 이중키

| 트랙 | 단위·키 | CBM 소스 | 용도 | 상태 |
|---|---|---|---|---|
| **출고** | 굿즈 `견적코드` | TMS Product(243) + sync_goods 백필 + 박스유도 | shipment CBM → 배차/Capa/wave/운임/차량이용률 | 인프라 **이미 배선**, CBM만 주입 |
| **입하** | 파츠 `PT####` | material parts-stock 치수 79.5% + QC버킷 폴백 | movement→입하 적재율·다음주 입하. M/H는 **이미 pkg_task/MES에 존재(재구축 금지)** | 용량 분모 신설 필요 |
| **보관** | 파츠 `PT####` | 파츠 CBM × `WMS_InventoryLedger`(301 PT) | 창고 적재율 | 용량 분모 신설 필요 |

미래 예측 = CBM × 날짜. 신뢰 가능 날짜: 출고 `출하일자/확정출하일`, 입하 `입하예정일`·`GoodsReceipt.Expected_Arrival`, 생산 `MES 납기일`(100%). (movement 미래날짜·인쇄완료예정일은 sparse → 사용 금지.)

---

## 4. 데이터 모델 변경 (최소 — 새 테이블 금지)

| 변경 | 대상 | 목적 |
|---|---|---|
| +2 필드 | `WMS_Location` `Max_CBM`(number, 수동시드 10행) + `Occupancy_Rate`(formula) | 적재율 분모 (WMS에 부피용량 전무; Capacity_Units는 개수). TMS Capa/Location 재사용 금지(다른 물리량) |
| +1 formula | `Shipment` `CBM_유효 = IF(Total_CBM>0, Total_CBM, estimated_cbm)` | 배차일지/Capa/배송파트너 롤업 재연결 (wave 코드는 이미 coalesce) |
| +1 lookup | `pkg_schedule` order.굿즈코드 (order→project→pkg_schedule 링크) | 임가공 hop에서 견적코드 가독 (pkg_task 캐스케이드) |
| 백필 | `WMS_BOM.구성유형`(0%) ← `sync_parts.파츠 유형`(100%) 매핑 + 외박스 2차패스(TMS Box.cbm) | BOM 포장재 분류 |
| 신규 모듈 | `keys.resolve_goods_code(row)` 리졸버 | 정밀도 순서 1곳 집중(order.굿즈코드→pkg_schedule→crosswalk→fuzzy 태그) |
| 가드 | `_core/airtable.py` 쓰기 allowlist(~15줄) | ⚡미러/MES/SERPA 쓰기 거부 |
| 외부 | `capacity_series.json`(sincerely-scm-dashboard Supabase, GHA cron append) | 대시보드 시계열 (신규 Airtable 테이블 아님, 2026-05-08 정책) |

---

## 5. 컴포넌트 경계 (isolation)

- `harness/dispatch/cbm_estimator.py` — `estimate_shipment_cbm_deterministic(shipment, order_by_project, product_by_code)` 추가. 입력=사전조인 dict, 출력=`{estimated_cbm, confidence, mode}`. 기존 퍼지 경로는 blank project_code 폴백으로만.
- `harness/backbone/keys.py` — `resolve_goods_code(row)` 순수 함수(기존 필드 읽기만, 저장 없음).
- `harness/settlement/cbm_calc.load_product_lookup` — 중복 견적코드(6개) 결정론 해소(formula>0 우선) 추가.
- `harness/_core/airtable.py` — write-target allowlist 가드(소스 보호).
- `harness/backbone/part_cbm.py`(신규) — PT#### → material 치수 파싱 → m³ (입하/보관 공용). 2축/펼침/+N 노이즈 처리, QC버킷 폴백.
- `harness/backbone/capacity_snapshot.py`(신규) — 3트랙 event-boundary 집계 → capacity_series.json.

각 모듈은 단일 책임 + 기존 필드 read 우선. 재사용: `keys.extract_pt`, `cbm_master.cbm_from_box_dims`, `AirtableClient`(idempotent·batch·3req/s), `wave_recommender` 날짜버킷.

---

## 6. CBM 산출 로직

**출고(결정론, 퍼지 제거):**
```
Shipment.project_code(PNA) → 사전그룹된 order rows → order.굿즈코드 → product_by_code[견적코드]
  → ceil(qty/박스당제품수) × 박스당CBM → Σ → estimated_cbm (+confidence, +updated_at)
1출하 프로젝트만 기록(conf 1.0). 다차 → partial_skip. blank project_code(19%) → 기존 퍼지 폴백.
```
배치: order/Product/Shipment 각 1회 페이징 풀 → 메모리 조인 → batch PATCH 10/req (롤업 필터 불가 → client-side join, ~200 batch).

**입하:** subset = `이동목적 ∈ {외부입하 목록}` AND `실제입하일 NOT BLANK`. CBM = `입하수량`(number) × per-part CBM. 박스수 텍스트필드 금지. 다음주 = `입하예정일` 7일내(커버 ~20% 명시).

**보관:** `WMS_InventoryLedger.Current_Stock` × per-part CBM → Σ occupied. 적재율 = occupied / `WMS_Location.Max_CBM`. 치수없는 ~20% → `입하부피 by QC`(소/중/대) 폴백 + 커버리지%. MES 재고관리(1행 dead) 제외.

**신뢰도:** 실측 Total_CBM 1.0 / Product formula 0.9 / 박스유도 0.7 / BOX_TYPE fallback 0.6 / 2축치수 0.55 / QC버킷 0.40 / 퍼지 ≤0.4.

---

## 7. Phase Plan (구현 P0→P5)

| Phase | Scope | Gate | 체크포인트(사용자 데이터) |
|---|---|---|---|
| **P0 안전** | `backfill_total_cbm_safe.py` auto freeze; allowlist 가드; 2,553행 ruling | 추정치 Total_CBM 미기입(테스트); allowlist ⚡쓰기 거부 | 2,553행 재분류 방식 |
| **P1 출고(★)** | `estimate_shipment_cbm_deterministic`; `resolve_goods_code`; `crosswalk --write`; sync_goods→Product 누락코드 백필; 부분출하 게이트; wave 신뢰도 floor; `CBM_유효`+롤업 재연결 | **shipment CBM resolvable 15.8→≥70%**(dry-run); partial_skip; 차량이용률 다차레인 미인플레; 배차/wave 자동점등 | qty 필드 확정 |
| **P2 보관** | `WMS_Location.Max_CBM` 시드; occupied=Σ(Current_Stock×part CBM); 창고-total 우선 | 창고-total 적재율 + 커버리지% | **Max_CBM 실측치** |
| **P3 입하/용량** | `Occupancy_Rate` formula; inbound subset 필터; 입하 CBM; 다음주 forecast; `WMS_BOM.구성유형` 백필 | 입하 적재율 + 미해결PT율; phantom 제외 | **이동목적 외부입하 분류** |
| **P4 대시보드** | `capacity_series.json` GHA cron; 트랙별 event-boundary 태깅 | 1주문 트랙간 중복0; forward curve | 예측 horizon |
| **P5 백로그** | 6 중복코드·소요량 정합·128/95 비교차·blank-code 19% 실측성 | (deferrable) | — |

---

## 8. Validation Contract

| Gate | Baseline | Target | Phase |
|---|---|---|---|
| Shipment CBM resolvable | 15.8% | ≥70% | P1 |
| 추정치 Total_CBM 오염 | 2,553행 | 0 | P0 |
| 굿즈 CBM 커버리지(견적코드) | 87% | ≥95% | P1 |
| 차량이용률 다차레인 인플레 | 위험 | 0 | P1 |
| 보관 적재율 커버(CBM) | 0 | ≥80% + 커버% | P2 |
| 입하 적재율 movement 커버 | 0 | subset ≥70% | P3 |
| 소스 write(⚡/MES/SERPA) | — | 0 (allowlist) | 전 phase |

---

## 9. Risks & Mitigations

1. **Scope-creep illusion** — 이미 있는 걸 재구축 유혹. 새 테이블 금지(WMS_Location +2, Shipment +1, pkg_schedule +1만).
2. **Inflation regression** — blind 합산이 19x 버그류(710c81b) 재발. 부분출하 게이트 필수.
3. **Silent under-count** — 87% 코드커버가 라인레벨엔 더 낮음(SSSV 최다빈 누락). 커버리지% 항상 동반.
4. **False-precision** — Product 98%가 5-entry BOX_TYPE fallback(17x 스프레드). 신뢰도가 fallback 인코딩.
5. **Cross-base SSOT 오염** — TMS Capa/Location 재사용 금지; ⚡미러 쓰기 = SERPA 재싱크 충돌. allowlist가 보험.
6. **Lifecycle 4중 카운트** — 같은 unit이 생산→입하→보관→출고 4번. 트랙별 단일 event-boundary.
7. **빈 미래날짜 forecast** — movement 미래날짜·인쇄완료예정일 sparse. order.입고예정일/GoodsReceipt/MES 납기일 사용.

---

## 10. 재사용 자산
- `harness/settlement/cbm_calc.py` — `load_product_lookup`(견적코드 색인 ★이미 존재), `match_product`, `BOX_TYPE_TO_CBM_M3`
- `harness/dispatch/cbm_estimator.py` — `estimate_shipment_cbm`(퍼지, 폴백으로 유지), `parse_product_lines_v2`
- `harness/dispatch/wave_recommender.py` — CBM coalesce(184-193)·날짜버킷·신뢰도 plumbing(238)
- `harness/backbone/{keys,cbm_master,crosswalk,ledger,schema_def,create_tables}.py`
- `harness/_core/airtable.py` — `AirtableClient`(idempotent PATCH·batch 10/req·3req/s), `audit.py`(cbm_transitions/anomalies jsonl)
- `WMS_InventoryLedger`(on-hand SSOT, 301 PT), `WMS_GoodsReceipt`(native inbound, 109행), TMS `Box`(6 박스 cbm)

## 11. 다음 단계
1. (본 spec) commit.
2. `/chain init cbm-capacity-backbone` → P0~P5 트래커, 구 `bom-cbm-phase2` superseded.
3. `superpowers:writing-plans`로 **P0+P1** 상세계획 + Validation Contract.
4. P0(안전) → P1(결정론 출고) 실행 → dry-run replay 검증.
