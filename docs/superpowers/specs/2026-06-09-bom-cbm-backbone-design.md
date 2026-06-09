# 신시어리 SCM — BOM·CBM 수량전파 백본 설계 (Vision Blueprint + Phase-1)

> 작성일 2026-06-09 · brainstorming 산출 · 대상 base: WMS `appLui4ZR5HWcQRri` / TMS `app4x70a8mOrIKsMf` / MES `appNSAPadsHbfaSHv`(SCR Production MES) · SERPA 3.0 무시(원본 SSOT)
> 산출 범위: **비전 블루프린트 + Phase-1 딥스펙.** 실제 Airtable 생성·파이프라인 코드는 writing-plans 후 다음 라운드.

---

## 0. Executive Summary

신시어리 물류팀 운영은 SERPA 아래 **6개 모듈이 섬처럼** 분리되어 있다:
`project(고객주문) → order → task(생산·임가공) → pkg(패키징) → movement(자재투입) → TMS(배송)`.
섬들은 Airtable 네이티브 링크가 아니라 **텍스트 키 매칭**으로 위태롭게 이어져, 고객 주문이 들어와도 **자재·패키징 수량이 자동으로 흐르지 않는다.**

진짜 북극성은 BOM/CBM "마스터 만들기"가 아니라 **수량전파 백본** — 같은 품목키와 BOM이 모듈 경계를 가로질러 수량을 운반하고, CBM이 그 위에 부피를 입혀 capa·청구·배차를 자동화한다. MES read-only 분석 + 실프로젝트 3건 추적 + dry-run 실측으로 **전제가 성립함을 검증**했다.

**아키텍처:** 소스 모듈 무변경. WMS 네이티브 신규 테이블이 옆에서 모듈 간 수량 링크를 **read-only로 계산·저장**(`wave_recommender`가 검증한 add-on 패턴). SERPA·⚡미러·MES·TMS는 one-way READ.

---

## 1. 데이터 아키텍처 (현황)

```
SERPA 3.0 (원본 SSOT — 절대 무시)
   ├─ sync ───────────► WMS base : ⚡테이블 = 읽기전용 미러 + WMS_* 네이티브
   ├─ logistics_release ─ sync ──► TMS base : 배송요청(synced) → Shipment(native)
   └─ ───────────────────────────► MES base : 생산·임가공(인쇄) — 인쇄대상 파츠만 커버
```

- WMS `⚡`-prefix 14테이블 = 미러(READ ONLY 소스컬럼), `WMS_*` 9테이블 = 네이티브(편집 가능)
- TMS `Product`(CBM 마스터)/`Shipment`/`OTIF`/`운임단가`… = 네이티브
- MES `[sync]파츠별_자재이동`/`내부인쇄_제품 DB`/`재고관리` = 생산 contributor

---

## 2. 진단 (증거 기반)

### 2-1. 연결성 — "없다"가 아니라 "텍스트로 박혀 있다"
실프로젝트 3건 추적(read-only):

| 단계 | PNA50702-위스타트 | PNA51949-벙커 | PNA52189-미래과학아카데미 |
|---|---|---|---|
| 굿즈 | 심볼아크릴트로피×125 | 시그니처다이어리×50 | 핸디링미니선풍기×200 |
| WMS order / task / movement | 17 / 3 / 13 | 9 / 2 / 8 | 10 / 2 / 7 |
| MES 파츠이동 | 0 | 0 | 1 (PT3339만) |
| TMS Shipment | 1 / **CBM 없음** | 1 / **CBM 없음** | 1 / **CBM 없음** |

- `order.파츠명="PT4917-아크릴트로피_추상적산출물"`, `movement.이동물품="PT4911-... || PNA50702_... || 좌표"`, `MES.파츠코드="PT3339"`
- **`PT####`(파츠코드) = 범용 품목키.** WMS project→order→task→movement는 견고히 연결됨. Crosswalk = 임베드된 PT#### 추출·정규화.

### 2-2. BOM — 구조는 없지만 order에 잠재
- 굿즈주문수량(`심볼아크릴트로피 125`)으로 묶인 파츠 라인들이 곧 그 굿즈의 **구성품**. 소요량 = 주문수량 / 굿즈수량.
- → 부트스트랩 = **order 라인 그룹핑**(노이즈 비율추정 폐기).

### 2-3. MES — spine 아닌 contributor
- 2/3 프로젝트 MES 0행. SCR(인쇄공장)는 **인쇄·임가공 대상 파츠만** 커버. 스티커·박스·에어캡·조립산출물은 MES 미수집.
- → 백본 척추 = WMS order/movement, MES = 인쇄파츠 보강 + 생산표준(M/H·리드타임·원가) 소스.

### 2-4. CBM — 굿즈 단위, 그리고 미전파
- CBM 마스터 = **완제품(굿즈) 단위** TMS Product `견적코드`(4자리, 382품목). BOM/PT#### = **파츠 단위**. **조인은 굿즈명**(코드 아님).
- 3 shipment 전부 CBM 공란 → 마스터는 있으나 안 흐름.

---

## 3. dry-run 실측 (2026-06-09 · `scripts/analysis/bom_cbm_dryrun.py` · 쓰기 0)

| Gate | 측정 | 결과 | 판정 |
|---|---|---|---|
| 2b | 파츠명 PT#### 추출 | **100%** (1498/1498) | ✅ Tier B 견고 |
| 3 | BOM 부트스트랩(굿즈 그룹핑→소요량) | **93.1%** (980/1053) | ✅ 강함 |
| 2 | TMS Product CBM>0 커버리지 | **98.2%** (375/382) | ✅ 충실 |
| 1 | 굿즈명→CBM 매칭 | **48%→53%**(정규화) | ⚠️ **약한 고리** |

> **핵심:** Gate 1 병목 = 매칭 로직이 아니라 **CBM 마스터 커버리지.** 1500 order에 distinct 굿즈 413종, 382 마스터가 절반만 커버.
> 미등록 신제품 **186종**(클리어리유저블컵·미스트워터보틀·디자이너노트…)이 미매칭 핵심. 정규화(대괄호·괄호·_접미 제거)는 +5p뿐.
> ∴ CBM 자동전파 = "estimator 실행"이 아니라 **"마스터 확장 → 전파"** 순. 확장 소스: order `박스규격/박스수량`, MES `내부인쇄_제품 DB` 치수.

---

## 4. 아키텍처 결정 — Derived Native Propagation Layer

```
MES base  ─┐                          WMS_KeyCrosswalk      (2-tier: 굿즈 identity + 파츠 identity)
WMS base  ─┼─ READ ─►[Propagation ─► WMS_ItemMaster        (CBM 앵커 + 품목 정체성)
TMS base  ─┘          Engine]        WMS_BOM               (소요량 폭발: 제품 BOM + 포장 BOM)
                          │          WMS_PropagationLedger (order→자재→포장→CBM→shipment, INSERT-only)
                          ▼
                    KPI snapshots ─────► Dashboard (생산 / WMS / TMS 통합)
```

**기각:** (A) 소스 write-back — Immutable Ledger 위반 + ⚡미러 재싱크 충돌. (B) 풀 ERP 통합 — monolith 거부.
**채택 근거:** `wave_recommender` 검증 패턴(⚡미러 위 네이티브 add-on). 쓰기는 WMS 네이티브 한정.

---

## 5. Deliverable 1 — 비전 블루프린트 (4 레이어)

**Layer 1 — 연결 백본:** `WMS_KeyCrosswalk`(`MES copy 2/3` 중복 재연결 종식) + `WMS_PropagationLedger`(order→shipment 수량 1줄 추적). 6 섬 → 1 흐름.

**Layer 2 — 운영:**
| 운영 | 입력 | 산출 | 상태 |
|---|---|---|---|
| 자재소요(MRP) | order 소요량 × 고객주문 | 파츠별 소요 | 신규 |
| 패키징 자재 소요·재고 | 포장 BOM × 출고단위 | 박스/완충재/라벨 소요 + 차감예측 | 신규 |
| Kitting 지시 | 제품 BOM 폭발 | 키트 피킹리스트 | 신규 |
| 자재차감 정합성 | 계획 vs 출고 vs movement | 편차·누락 alert | 신규 |
| **CBM 자동전파(★1순위)** | 굿즈명→Product CBM (+마스터 확장) | shipment CBM 채움 | **현재 공란** |
| CBM→capa/billing/wave | 굿즈 CBM×수량 | 가동률·이송단가·배차 | 일부 가동 |

**Layer 3 — KPI 자동화:** 전파정합성%·자재부족 alert·패키징재 회전·CBM 신뢰도·OTIF×BOM·견적↔실투입 편차·M/H·리드타임·제조원가 대비 물류비.

**Layer 4 — 대시보드:** 생산(MES 실데이터+BOM 소요) / WMS(재고·차감·패키징) / TMS(CBM·wave·OTIF). 공급: Propagation 스냅샷 → GH Actions weekly → Supabase → `sincerely-scm-dashboard`(별도 레포, 후속 Phase). Phase-1은 스냅샷 계약만.

---

## 6. Deliverable 2 — Phase-1 파운데이션 스펙

> 쓰기 = WMS 네이티브(`appLui4ZR5HWcQRri`) 신규 테이블만. ⚡/MES/TMS read-only.

### 6-1. 신규 네이티브 테이블 3종 (2-tier)
- **WMS_KeyCrosswalk** — *Tier A 굿즈*: PK=굿즈명 ↔ TMS 견적코드 ↔ CBM (name 매칭, `match_product`). *Tier B 파츠*: PT#### ↔ WMS 아이템코드(order.파츠명/movement.이동물품에서 `^PT\d+` 추출) ↔ MES 파츠코드. 공통: 매칭방식·신뢰도·검증상태.
- **WMS_ItemMaster** — PK=PT####/굿즈명. CBM_개당_m3(굿즈, Product 정규화) / L·W·H / 박스규격·박스당수량·박스당CBM / 품목유형(완제품·키트·단품·부자재·포장재) / BOM 양방향링크.
- **WMS_BOM** — 모(굿즈)→소(PT#### 파츠) / 소요량_Qty_Per(=주문수량/굿즈수량) / 구성유형(키트·임가공·포장재·원부자재) / Scrap율 / 검증상태(이송·검증완료·폐기) / 신뢰도 / 구성_CBM(formula).

### 6-2. 부트스트랩 (order 그룹핑)
- 1차: WMS order를 굿즈주문수량으로 그룹핑 → 같은 그룹 파츠(PT####)가 구성품, 소요량=주문수량/굿즈수량. (실측 93.1% 적용가능)
- 2차: MES 파츠이동 + movement.이동물품 PT#### → order 누락 보완.
- status=`이송(draft)`+신뢰도 → 물류팀 검증 → `검증완료`.
- 재사용: `match_product`, `AirtableClient`(idempotent·3req/s), `product_loader`(TTL 24h).

### 6-3. CBM 정규화 + **마스터 확장** (dry-run 반영)
- TMS Product(text) → ItemMaster 숫자. 재사용 `load_product_lookup`·`BOX_TYPE_TO_CBM_M3`·`import_product_cbm`(→AirtableClient 이관).
- **신규 워크스트림: 미등록 굿즈 186종 box/CBM 채움** (소스: order 박스규격/박스수량, MES 내부인쇄_제품 DB 치수). → Gate 1 목표 ≥85%.
- 키트 CBM = Σ(소품목 소요량 × CBM): `cbm_estimator` BOM-aware 확장.

### 6-4. PropagationLedger v0
- 샘플 1 고객주문으로 order→자재→포장→CBM→shipment end-to-end 1줄 전파 증명(INSERT-only).

### 6-5. TMS 무중단 (Option A)
- ItemMaster=SSOT, TMS Product=하위 미러 유지. `load_product_lookup`이 ItemMaster를 읽게 되면 배차·이송 코드 무변경 동작.

---

## 7. 검증 게이트 (Validation Contract 초안)
1. 키 매칭률 (Tier A 굿즈명, Tier B PT####) — 목표 Tier A ≥85%(마스터 확장 후), Tier B ≥99%
2. CBM 커버리지 (Product CBM>0 + 매칭 굿즈 CBM 확보)
3. BOM 부트스트랩 적용율 (굿즈 그룹핑 소요량) — 실측 93.1%
4. 링크 안전성 — ⚡/MES/TMS one-way READ, TMS Product 변경 0
5. 전파 정합 — Ledger 샘플 1건 수량·CBM 무손실

---

## 8. 재사용 자산 (탐색·dry-run 검증)
- `harness/settlement/cbm_calc.py` — `load_product_lookup`, `match_product`, `BOX_TYPE_TO_CBM_M3`
- `harness/dispatch/cbm_estimator.py` — `estimate_shipment_cbm`(완성), BOM-aware 확장 대상
- `harness/dispatch/product_loader.py` — TTL 24h 캐시
- `harness/_core/airtable.py` — `AirtableClient`(idempotent PATCH, 3req/s)
- `scripts/analysis/bom_cbm_dryrun.py` — 본 검증 dry-run (read-only)
- 패턴: `harness/dispatch/wave_recommender.py` (네이티브 add-on over ⚡미러)

## 9. 다음 단계
1. `superpowers:writing-plans`로 Phase-1 실행계획 (테이블 생성 → 부트스트랩 → CBM 정규화+마스터확장 → Ledger v0)
2. feature_list.json·Obsidian log·git commit
