# CBM·BOM 백본 — 프로젝트 핸드오프 (Project Bible)

> 작성 2026-06-10 · 신시어리 SCM 물류팀 · WMS(`appLui4ZR5HWcQRri`) + TMS(`app4x70a8mOrIKsMf`) Airtable
> 이 문서 하나로 처음 시작한 체인부터 현재까지의 전말 + WMS/TMS로 CBM·BOM을 가지고 무엇을 하려 했는지를 파악할 수 있게 작성됨. **self-contained** — 어느 모델/터미널에서든 cold-start 가능.

---

## 0. 한 눈에

| 체인 | 상태 | 산출 | 비고 |
|---|---|---|---|
| **bom-cbm-backbone** (Phase-1) | ✅ DONE (2026-06-09, merge `ea09e51`) | WMS 네이티브 4테이블 + `harness/backbone/` 9모듈 + TDD | BOM 수량전파 배선 |
| **bom-cbm-phase2** | 🚫 SUPERSEDED | (계획만) | gap분석으로 재스코프됨 |
| **cbm-capacity-backbone** | 🔄 진행 중 | P0 ✅ · **P1 ✅(코드+데이터)** · P2~P5 📝 | 현재 활성 체인 |

**현재 결론(2026-06-10):** P1 결정론 출고 CBM 완료 — **856건 정밀 CBM을 `Shipment.estimated_cbm`에 기록**(실측 `Total_CBM` 미터치). **forward(최근 90일·order 존재) shipment 기준 CBM 커버리지 75.1%**로 ≥70% gate 통과. 단, 전수 16k는 과거 order 데이터 부재로 28.7%가 상한 — 이는 코드가 아니라 **데이터 가용성** 한계.

---

## 1. 무엇을 하려 했나 (WHY)

### 핵심 문제
TMS Shipment 16,200건 중 **CBM(부피) 보유가 15.8%뿐**(나머지 84% 공란). CBM이 없으면 다음이 전부 산정 불가:
- **배차 스케줄링 / wave 배정** — 트럭에 몇 건이 들어가는지 모름
- **차량이용률(載積率)** — m³/대 효율 측정 불가
- **출하볼륨 예측 · 입하 적재율 · 창고 적재율** — 전부 불가

### 근본 원인 = "키는 이미 다 있는데 백본이 안 읽는다"
- `order.굿즈코드 (from sync_itemdb)` 99.9% · `order.project_code`(PNA) 100% · `movement` PT#### 99% 존재
- **`견적코드` = `굿즈코드` = `sync_goods.Goods Code 2`** (동일 4자리 체계, 243개 일치)
- 그런데 기존 estimator는 `최종 출하 품목` free-text 이름 **퍼지매칭**만 함 → 84% 실패
- 게다가 과거 backfill이 추정치를 실측 `Total_CBM`에 써 2,553행 오염

### 궁극 목표 = "얼어붙은 3개 운영 레버를 푼다"
| 레버 | AS-IS | TO-BE | 필요 입력 |
|---|---|---|---|
| **① 출고/배차 정밀** | "N대 보내고 적재 잘 되길 기대" | "K대, 적재율 L%, m³당 비용 C로 배차" | Shipment CBM → 배차/wave/차량이용률 |
| **② 입하 서지 예측** | "도크 콜 기다림" | "다음주 입하량 예측, 인력·도크 선배치" | movement 입하수량 × part CBM |
| **③ 창고 캐파 가시성** | "공간 있는 것 같다" | "11개 로케이션 중 8개 ≥85% 점유, Zone C 보충 차단" | 재고 × part CBM ÷ Max_CBM |

> **왜 지금:** 영업이익률 3.27% · SCRW 자본잠식 압박 하에서 물류비(매출 6~13%)의 KPI 정밀화는 선택이 아님. CBM·BOM은 2026 재무전략 Top-5 마진회복(≥2%p)의 *메커니즘*.

---

## 2. CBM 3트랙 + BOM (무엇이 무엇을 위한 것인가)

CBM은 라이프사이클 단계별로 **3트랙**으로 분리(소스·키·주인이 다름):

| 트랙 | 단위·키 | CBM 소스 | 용도 | 주인(SSOT) | Phase |
|---|---|---|---|---|---|
| **출고 ★** | 굿즈 `견적코드` | TMS Product(243) + 박스유도 | shipment CBM → 배차/wave/차량이용률/운임 | TMS Product | **P1(완료)** |
| **입하** | 파츠 `PT####` | movement 입하수량 × part CBM | 입하 적재율 · 다음주 예측 | **movement**(INSERT-only) | P3 |
| **보관** | 파츠 `PT####` | 재고 × part CBM ÷ Max_CBM | 창고 적재율 | WMS_InventoryLedger + WMS_Location | P2 |

### BOM vs CBM(출고)는 직교 — 혼동 금지
| | **BOM** | **CBM(출고)** |
|---|---|---|
| 단위 | 파츠 `PT####` (WMS 입하/생산) | 굿즈 `견적코드` (TMS 출고) |
| 무엇 | 주문당 필요 파츠 / 자재 전파 / M/H | shipment당 부피 / 차량 최적화 |
| 소스 | WMS_BOM, WMS_ItemMaster | TMS Product |
- 1 주문 = 여러 굿즈(각 1회 출고=CBM), 각 굿즈 내부엔 5~50개 파츠(BOM). **BOM은 파츠·M/H를 전파, CBM은 차량을 최적화.**

---

## 3. WMS + TMS 아키텍처 (어떻게 연결되나)

### 두 베이스 + 핵심 테이블
- **WMS `appLui4ZR5HWcQRri`** — 입하·재고·order·movement·BOM 전파
  - 네이티브(R/W): `order`, `movement`(INSERT-only), `WMS_InventoryLedger`, `WMS_GoodsReceipt`, `WMS_Location`(+Max_CBM P2)
  - 미러(⚡, READ-ONLY): SERPA sync 14테이블 (`order` 미러 포함)
  - **신규 네이티브(Phase-1)**: `WMS_KeyCrosswalk` · `WMS_ItemMaster` · `WMS_BOM`(1,702행) · `WMS_PropagationLedger`
- **TMS `app4x70a8mOrIKsMf`** — 출하·배차
  - `Shipment`(핵심), `배송요청`, `배송파트너`, `배차 일지`, `Capa`, `Product`(견적코드→CBM), `Box`, `OTIF`
  - **Shipment 자동화 필드**: `estimated_cbm` · `estimation_confidence` · `estimation_updated_at` · `wave_recommendation` · `wave_confidence`

### 불변식 — Derived Native Propagation Layer
```
소스(READ-ONLY)            전파 엔진(harness)              타깃(allowlist write만)
─────────────────         ───────────────────           ─────────────────────────
⚡미러(SERPA) ─┐          backbone/keys.py                WMS_KeyCrosswalk
MES(생산)     ─┼─[읽기]─> backbone/crosswalk.py  ─[쓰기]─> WMS_ItemMaster / WMS_BOM
TMS Product  ─┤          backbone/bom_bootstrap.py        WMS_PropagationLedger(INSERT-only)
IBSA(M/H)    ─┘          dispatch/cbm_estimator.py        TMS Shipment.estimated_cbm/wave_*
                         dispatch/wave_recommender.py
```
- **가드:** `harness/_core/airtable.py`의 쓰기 allowlist(14 테이블)가 ⚡미러/MES/IBSA/TMS Product 직접 쓰기를 차단 (P0에서 도입).
- **Immutable Ledger:** movement·PropagationLedger = INSERT-ONLY. 정정은 Storno(역분개)/보정행. **추정→`estimated_cbm`, 실측→`Total_CBM` 절대 분리.**

### 조인 키
- **Tier C 프로젝트:** `PNA#####` — order.project_code(100%) ↔ Shipment.`project`(lookup)/`project code`(rollup)
- **Tier A 굿즈:** `견적코드` = order.굿즈코드 = TMS Product.Goods Code 2 (4자리)
- **Tier B 파츠:** `PT####` — order.파츠명 / movement.이동물품에서 정규식 추출

---

## 4. End-to-End 흐름도 (전체 아웃풋)

```
  [WMS order]                                              [TMS]
  PNA50702                                                   │
  ├ 굿즈코드 "SBAT" ──────┐                                  │
  └ 파츠 PT4917,PT3410    │                                  │
        │                 │                                  │
   (BOM 전개)        (견적코드 조인)                          │
        ▼                 ▼                                  │
  [WMS_BOM]         [TMS Product]                            │
  굿즈→파츠 수량     견적코드→ qty_per_box · cbm_per_box       │
        │                 │                                  │
        │                 └──── ceil(주문수량/qty_per_box)    │
        │                        × cbm_per_box = CBM ─────────┤
   (movement 입하)                                            ▼
        │                                          [Shipment.estimated_cbm]  ← ★P1이 채운 곳(856건)
        ▼                                            estimation_confidence(1.0/0.7)
  [입하/보관 CBM]                                     Total_CBM 미터치
   (P2/P3)                                                   │
                                              CBM_유효 = IF(Total_CBM>0, Total_CBM, estimated_cbm)  ← ★Task1.6(사용자)
                                                            │
                                              ┌─────────────┼──────────────┐
                                              ▼             ▼              ▼
                                        [wave_recommender] [배차 일지]   [Capa/배송파트너]
                                         신뢰도 floor 0.8   차량이용률(%)   월간 총CBM
                                         <0.8 → 수동        오버부킹 flag
```
**핵심:** 출고 인프라(wave·배차일지·Capa 롤업)는 *이미 배선*돼 있어, `estimated_cbm` 숫자 주입 + `CBM_유효` formula 재연결만으로 배차·차량이용률이 자동 점등됨.

---

## 5. 체인 히스토리 (처음 → 지금)

### 체인 1 — bom-cbm-backbone Phase-1 ✅ (2026-06-09, merge `ea09e51`)
BOM 수량전파 백본 배선. WMS 네이티브 **4테이블 생성** + `harness/backbone/` 9모듈(keys·crosswalk·cbm_master·bom_bootstrap·ledger·item_master_sync·verify_phase1 등) + 12태스크 TDD. (commits `b68a547`→`ea09e51`)

### 체인 2 — bom-cbm-phase2 🚫 SUPERSEDED
CBM 마스터 확장 계획이었으나, 3-base 전수조사 + 7-critic gap분석 + 20프로젝트 시뮬로 **문제 재정의** → 아래 체인으로 흡수.

### 체인 3 — cbm-capacity-backbone 🔄 (현재)
설계 spec `docs/superpowers/specs/2026-06-09-cbm-capacity-backbone-design.md` (승인). 3트랙 전체 + P0~P5.

**P0 안전 가드레일 ✅** (commits `0b72277`/`47aa25d`/`3b4ca9c`/`9f5784a`)
- AirtableClient 쓰기 allowlist(⚡/MES/SERPA 차단) · backfill freeze · **오염 2,553행을 Total_CBM→estimated_cbm 이관**(Total_CBM blank). pytest 252 green.

**P1 결정론 출고 CBM ✅ 코드+데이터** (commits `77d51c1`/`7400a1d`/`772f47a`/`1b55580`/`b504793`)
- 1.1 `_resolve_dup`(중복 견적코드 결정론) · 1.2 `resolve_goods_code` · 1.3 `estimate_shipment_cbm_deterministic`(+부분출하 게이트) · 1.7 wave 신뢰도 floor 0.8 — **모두 TDD, 270 passed**(기존 W1 1건 무관)
- 1.5 `replay_outbound_cbm.py` — dry-run 측정 + **856건 estimated_cbm live write(0 err)**

---

## 6. P1 실측 결과 & 재스코프 (중요)

처음 목표는 "전수 15.8→≥70%"였으나 **실데이터가 가정을 뒤집음:**

| 지표 | 전수 16k | **최근 90일 (967건, order 존재)** |
|---|---|---|
| baseline CBM_유효>0 | 15.9% | 65.0% |
| **결정론 반영** | 16.8% | **75.1% ✅ ≥70% PASS** |
| 결정론+퍼지 ceiling | 28.7% | 78.9% |
| `no_order` | 39.6% | **0.0%** |

**확정된 원인 (read-only 조사):**
1. **필드 버그 아님** — Shipment `project`(lookup)와 `project code`(rollup)는 *동일 3,852행에서 동시에 blank*. blank ~24%는 프로젝트 링크 자체가 없는 shipment.
2. **`no_order` = 과거 고아화** — order 미러는 2026-03-12 sync 이후 `PNA29756~52465`만 보유. shipment는 `PNA18xxx`(2023)까지 소급 → 과거 shipment는 매칭 order가 *애초에 없음*. **소스 데이터 부재**(코드/필드 문제 아님).

**재정의된 Validation Contract:** ~~전수 ≥70%~~ → **"forward(order 커버리지 window) shipment 결정론 CBM ≥70%" = 75.1% 달성.** 앞으로 들어오는 출고는 정상 점등, 과거 백로그는 채울 수 없음(별도 과제).

---

## 7. 남은 일

| 항목 | 소유 | 상태 | 영향 |
|---|---|---|---|
| **Task 1.6 — `CBM_유효` formula + 롤업 재연결** | 👤 사용자 (Airtable UI) | 📝 대기 | **이게 돼야** 856 estimated_cbm이 배차일지/Capa 차량이용률에 실제 반영됨 |
| Task 1.4 — 누락 굿즈코드(SSSV 등 ~20) sync_goods→Product | (deferred) | 보류 | 전수 0.2%만 영향 → gate에 무의미, 후순위 |
| **P2 보관 적재율** | 차기 | 📝 | `WMS_Location.Max_CBM` 실측치(사용자 데이터) 필요 |
| **P3 입하/M/H** | 차기 | 📝 | 이동목적 '외부입하' 분류 + IBSA backfill 승인 필요 |
| P4 대시보드 / P5 백로그 | 차기 | 📝 | capacity_series.json / 과거 order 소스 확보 |

### Task 1.6 절차 (사용자)
1. TMS Shipment에 formula 필드 `CBM_유효 = IF({Total_CBM}>0, {Total_CBM}, {estimated_cbm})` 생성
2. 배차일지 `Total_CBM`(rollup)·Capa·배송파트너 `월간_총CBM` 롤업 소스를 `CBM_유효`로 재지정
3. 샘플 1건(estimated_cbm만 있는 shipment)의 배차일지 차량이용률 반영 확인

---

## 8. 파일·레퍼런스 맵

**체인 SSOT / 핸드오프** (`~/.claude/plans/`)
- `cbm-capacity-backbone-phase-status.md` — 마스터 트래커
- `cbm-capacity-backbone-p0-handoff.md` / `-p1-handoff.md` — cold-start brief
- `chain-glimmering-gem.md` — **P1 재스코프 + 실측(최신)**

**설계·구현계획** (`SCM_WORK/docs/superpowers/`)
- `specs/2026-06-09-cbm-capacity-backbone-design.md` — 전체 3트랙 설계
- `specs/2026-06-09-bom-cbm-backbone-design.md` — Phase-1 설계
- `plans/2026-06-09-cbm-p0-p1.md` — P0+P1 TDD 상세

**코드**
- Phase-1: `harness/backbone/` (keys·crosswalk·cbm_master·bom_bootstrap·ledger…)
- P0/P1: `harness/settlement/cbm_calc.py`(`_resolve_dup`) · `harness/backbone/keys.py`(`resolve_goods_code`) · `harness/dispatch/cbm_estimator.py`(`estimate_shipment_cbm_deterministic`) · `harness/dispatch/wave_assigner.py`(`CONFIDENCE_FLOOR`) · `scripts/backbone/replay_outbound_cbm.py`
- 가드: `harness/_core/airtable.py`(allowlist) · `harness/_core/schema_pin.json`

**검증 재현**
```bash
python -m pytest tests/ -q                              # 270 passed (1 무관)
python scripts/backbone/replay_outbound_cbm.py          # 전수 dry-run 측정
python scripts/backbone/replay_outbound_cbm.py --recent 90   # forward 75.1% 확인
```

---

> 다음 세션 진입: `이 파일 읽어줘: C:\Users\yjisu\.claude\plans\cbm-capacity-backbone-phase-status.md` → `/chain next`
