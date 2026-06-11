# CBM·BOM 백본 — P6 Order-Trigger 캐스케이드 설계 (북극성 통합)

> 작성일 2026-06-11 · superpowers:brainstorming 산출 (chain `cbm-capacity-backbone` P6)
> 상태: **설계 승인** (사용자 2026-06-11 — 트리거/출력모드/아키텍처 3결정 인터랙티브 승인)
> 북극성 정의: `2026-06-10-cbm-connectivity-first-rescope-design.md` §0.5 · 선행 spec §1~§6 유효
> 컨텍스트 맵: ultracode 7-agent 탐사 (backbone-core·dispatch·scripts·gha-crons·airtable-surface·order-intake·tms-consumption)

---

## 0. 목적 & 확정 결정

**목적**: 주문(PNA)이 order 미러에 등록되면 — MRP·입하CBM·M/H·창고CBM·배차 프리뷰·운임 프리뷰가 **출하 전에 전부 사전 계산**되어 PropagationLedger 1행 + 리포트로 떨어지는 단일 캐스케이드 (Order-Driven Forward Planning).

| # | 결정 | 선택 (사용자 승인) | 근거 |
|---|---|---|---|
| D1 | 트리거·지연 | **cron 폴링 3×/day (~2-4h)** | order 테이블 자체가 SERPA 비동기 미러 → webhook 실시간성 무의미. 신규 인프라 0 |
| D2 | 출력 모드 | **Ledger + 리포트만** (운영 테이블 write-through 없음) | shipment 미존재 시점 — 배차·운임은 프리뷰만 가능. 안전 최우선, 신규 테이블 0 |
| D3 | 아키텍처 | **단일 orchestrator** `scripts/backbone/order_cascade.py` + 전용 GHA cron | 전 스테이지가 기존 순수 함수 — 신규 코드는 글루만. cron tick = 자연 재시도 루프 |

전제: **forward-only** — 캐스케이드는 신규 주문만 처리. 과거 no_order 39.6% 백로그는 P5 (불변).

---

## 1. 캐스케이드 스테이지 그래프 — §0.5 8요소 전부 매핑 (gap 0)

cron 1 tick의 흐름. 단위 = (PNA, 굿즈) — 기존 전파ID 규약 `{project_code}_{goods_name}` 준수.

```
[S0 감지] → [S1 키해소] → [S2 MRP] → [S3 입하·M/H·MES] → [S4 창고] → [S5 배차 프리뷰] → [S6 운임 프리뷰] → [S7 Ledger+리포트]
                 │ 실패 → 끊김 마킹 후 계속(S2~S6 스킵 불가 항목만), 절대 abort 없음
```

| Stage | 북극성 요소 (§0.5) | 소유 모듈 (전부 기존) | 산출 |
|---|---|---|---|
| S0 감지 | ⑧ 주문 1건 → 캐스케이드 진입 | `bom_bootstrap.fetch_orders` 패턴 + Ledger 최신행 dedup | 신규/변경 (PNA,굿즈) 목록 |
| S1 키해소 | ① 주문 등록 → 키 연결 | `keys.resolve_goods_code`(tier1 직접+tier2 pkg), `extract_pts`, `normalize_goods` | 견적코드, PT 목록 |
| S2 MRP | ③ BOM 전개 → 필요 파츠·수량 + ⑦ MRP 리포트 | `bom_bootstrap.build_bom_rows` + WMS_BOM 검증완료행 우선 + InventoryLedger(UNRESTRICTED) 현재고 + 신규 `mrp.py` | PT별 부족분 = Σ(소요량×주문수량) − 현재고 |
| S3 입하·M/H·MES | ⑤ 입하 CBM·도크/인력 사전배치 + ④ MES 생산·task 연결 | `part_cbm.part_cbm_for_pt`(4-tier) × 부족수량 → 입하CBM · IBSA 표준 M/H(`mh_backfill_to_ibsa` 상수) × 수량 → M/H · **MES hop**: P2b 크로스워크로 생산중 파츠 납기일 forecast(P3' `build_inbound_forecast` 재사용), task↔BOM은 검증완료행 소비로 충족 | 입하CBM_예상, MH_예상, 입고예정일 타임라인 |
| S4 창고 | ⑥ 창고 CBM | `storage.aggregate_occupied` + S3 입하 delta + S5 출하 delta → Max_CBM 대비 투영 (현재 분모: 입하 A1-IB-001 57.6m³만 — 베스트원 ST 도착 시 자동 확장) | 창고적재_예상 |
| S5 배차 프리뷰 | ② 출하 CBM → wave·기사 배정·차량이용률 | `cbm_estimator.estimate_shipment_cbm_deterministic` — orchestrator가 order 행을 **shipment-shape dict로 변환하는 명시적 어댑터** 경유(필드명 불일치 silent-unmatched 방지, 어댑터 단위테스트 필수). wave 프리뷰 = `assign_waves` 배정이 아니라 **capacity-feasibility 체크**(출하CBM vs DRIVER_LIMITS tier 잔여 — 주문 시점엔 slot confidence < 0.8이라 배정 dry-call은 전건 '수동'이 되므로 무의미) | 출하CBM_예상, 수용 가능 기사 tier |
| S6 운임 프리뷰 | ② 운임 | `tms_settlement.calc` 요율 로직 — 주소 있으면 park 거리식, 없으면 CBM bracket 범위 추정 | 운임_예상범위 |
| S7 영속 | ⑧ 단일 캐스케이드 완결 | `ledger.build_propagation_row` 확장 + AirtableClient INSERT | Ledger 1행 + 리포트 + Slack |

---

## 2. 컴포넌트 경계 — 재사용율 명시 (Karpathy)

**신규 (4파일, 글루만)**:
1. `harness/backbone/mrp.py` — 순수 함수: `net_requirements(bom_rows, order_qty, stock_by_pt) → [{pt, gross, stock, shortfall}]` (~50 LOC)
2. `scripts/backbone/order_cascade.py` — orchestrator (감지→S1~S7 순차, dry-run 기본, `--write` 게이트, audit jsonl) (~300-400 LOC)
3. `.github/workflows/order_cascade.yml` — cron 3×/day KST 10:00/15:00/18:00 (wave_recommender 09/14/17 + 1h 오프셋 — 같은 Shipment 테이블 동시 접근 회피)
4. `tests/backbone/test_order_cascade.py`, `test_mrp.py`

**재사용 (11개 기존 모듈 — 수정 0)**: `keys.py` · `bom_bootstrap.py` · `part_cbm.py` · `storage.py` · `cbm_estimator.py` · `slot_decider.py` · `region_classifier.py` · `wave_assigner.py` · `tms_settlement/calc.py` · `settlement/cbm_calc.py` · `utils/cbm_utils.py`. `ledger.py`만 확장(시그니처 하위호환 — 신규 트랙 인자 optional).

**수정 (1파일)**: `ledger.py` per-track 인자 추가 (optional, 하위호환). `harness/_core/airtable.py` 변경 **없음** — PropagationLedger 이미 allowlist 내.

---

## 3. 데이터 계약

### 3.1 PropagationLedger 필드 확장 (기존 allowlist 테이블에 필드만 추가 — P2b `출처`·P4 `Max_CBM` 패턴)

| 신규 필드 | 타입 | 내용 |
|---|---|---|
| `부족자재_요약` | multilineText | `PT0123×500(재고 200/소요 700)` 줄 단위 |
| `입하CBM_예상_m3` | number(4) | S3 부족분 입하 CBM |
| `MH_예상_h` | number(2) | S3 입하검수 표준 M/H 합 |
| `창고적재_예상` | singleLineText | `staging 83%→97% (입하일 기준)` 형태 |
| `wave_프리뷰` | singleLineText | `W2 가능 (CBM 2.4/잔여 5.1)` / `부분: 주소 미확정` |
| `운임_예상범위` | singleLineText | `₩38,000~52,000 (CBM bracket)` |
| `cascade_실행ID` | singleLineText | `YYYYMMDD-HHMM` run id (audit join 키) |

기존 `전파상태` 의미 유지: **완결** = S1~S6 전 트랙 산출 / **부분** = ≥1 트랙 입력 결손(사유 필드에 기록) / **끊김** = S1 키해소 실패.

**소비자 계약**: Ledger는 INSERT-only 이력 — 소비자(대시보드·리포트)는 반드시 **전파ID별 최신행(생성시각 max)** 만 현재 상태로 읽는다. 단일행 가정 금지.

### 3.2 리포트 & 알림
- **리포트**: GHA artifact `order-cascade-report` (json+md, 14d retention) — **repo commit 안 함** (P4 GH006 교훈, capacity-data 같은 별도 브랜치도 불필요: 영속 기록은 Ledger가 담당)
- **Slack**: 신규 주문 ≥1건인 tick만 digest (주문 수·부족자재 top·창고 경고). 기존 `SLACK_BOT_TOKEN` 재사용

---

## 4. MRP 리포트 설계 (§0.5 요소 ⑦)

주문별: PT / 소요량_개당 / gross(소요×주문수량) / 현재고(InventoryLedger UNRESTRICTED) / **부족분** / 입하CBM_예상 / MH_예상 / MES 납기 forecast(생산중인 경우).
집계: **협력사별 부족분 묶음** (발주 액션 단위). 산출 위치: 리포트 md 섹션 + Ledger `부족자재_요약` + Slack digest. Airtable 신규 테이블 **없음**.

---

## 5. 실패 모드·재시도·Idempotency

| 모드 | 처리 |
|---|---|
| 스테이지 실패 (키 미해소, Product 미매칭, 재고 데이터 결손) | 해당 트랙 부분/끊김 마킹 후 **계속** — abort 없음, 부분 가시성이 곧 기능 |
| Airtable 429/5xx | 기존 AirtableClient rate-limit·backoff + cron tick 자연 재시도 |
| Idempotency | 전파ID별 최신행(생성시각 max) 비교 — **상태·수치 변동 시에만 신규 INSERT** (UPDATE/DELETE 절대 없음). 동일 입력 재실행 = 0 write |
| 부분 주문 재처리 | 부분/끊김 상태 + 주문등록 ≤14d → 매 tick 재시도 (입력 보강 시 완결로 승급행 INSERT) |
| 쓰기 안전 | write 표면 = PropagationLedger INSERT **단 1개** + artifact + Slack. Total_CBM·소스(⚡/MES/SERPA) 불가침. allowlist 변경 0 |
| cron 충돌 | wave_recommender와 1h 오프셋 + 캐스케이드는 Shipment **read-only** |
| 긴급 중단 (rollback) | **kill switch = GHA workflow disable (1클릭, <1분)**. 오염 행 정정 = DELETE 금지, 차기 run의 정정행 INSERT가 최신행 의미론으로 supersede (§3.1 소비자 계약) |

---

## 6. Validation Contract

| # | Gate | 판정 |
|---|---|---|
| VC-1 | 최근 실주문 1건 replay → 다음 tick → Ledger 1행, 6트랙 필드 전부 기입(완결 또는 사유 있는 부분), 경과 ≤ 2 tick — **경과 기준 = order 미러 행의 Airtable record `createdTime` 메타데이터** (미러에 등록시각 필드 없음) | end-to-end |
| VC-2 | 동일 tick 재실행 → 신규 INSERT 0 | idempotency |
| VC-3 | forward 90d 키 커버리지 ≥ 75% baseline 유지 **+ 캐스케이드 출하CBM_예상 커버리지도 동일 baseline 비퇴행** (S5 어댑터 silent-unmatched 감지 게이트) | 회귀 |
| VC-4 | 표본 K=5 주문 MRP 부족분 == 수기 BOM×수량−재고 정확 일치 | 정합 |
| VC-5 | audit jsonl: PropagationLedger 외 write 0 | 안전 |
| VC-6 | pytest 전체 green (기존 363+신규) + GHA cron 첫 run success | 정착 |

---

## 7. Out of Scope (명시)

운영 테이블 write-through(프리뷰 정확도 검증 후 후속 sub-phase에서 승급 검토) · webhook/실시간 · 과거 no_order 백로그(P5) · 배차일지 자동 생성 · DRIVER_LIMITS Airtable화 · MES 소비 확대(P3' 배선 초과분) · 다중 shipment 통합(PNA 단위 consolidation) · OTIF 사전 추정.

---

## 8. 구현 sub-phase 분해 (P6 설계 종료 시 tracker 반영)

| Sub-phase | Scope | Gate |
|---|---|---|
| **P6a 코어** (1 세션 예상) | `mrp.py` + `order_cascade.py` (S0~S7, dry-run) + `ledger.py` 확장 + 테스트 — TDD | pytest green + dry-run 리포트 1회 산출 (VC-4·5) |
| **P6b 점등** (0.5 세션 + cron 관찰 수일) | Ledger 필드 7개 신설 + `--write` 첫 INSERT + GHA cron + Slack | VC-1·2·3·6 전체 PASS |

**최소 가치 컷 (P6a 지연 시 fallback)**: S0–S3+S7 — MRP·입하CBM·M/H만으로도 발주 액션이 가능한 절반. S4–S6은 부분 마킹으로 자연 degrade (abort 없음 설계라 컷 적용에 코드 분기 불필요).

**총 비용 추정**: 2 세션 (11개 모듈 통합 표면 + IO 3종 — InventoryLedger·IBSA·MES — 별도 PAT·shape 작업이 "글루만" 낙관을 상쇄. P2b 1세션/3hop 실측 기준).
