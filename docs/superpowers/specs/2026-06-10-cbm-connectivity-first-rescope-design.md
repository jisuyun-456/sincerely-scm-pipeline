# CBM·BOM 백본 — Connectivity-First 재스코프 설계 (P2a/P2b/P3' 재배열)

> 작성일 2026-06-10 · superpowers:brainstorming + ultracode deep review(8 agents, 적대검증) 산출
> 상태: **승인됨** (ExitPlanMode 2026-06-10). 선행 spec `2026-06-09-cbm-capacity-backbone-design.md`의 **§7 Phase Plan을 본 문서가 대체(amendment)** — §1~§6(3트랙·데이터모델·CBM 로직)은 그대로 유효.
> 사용자 최종 목표 재확인: **project → pkg → MES → task → movement → TMS 데이터 연결성 무단절** (CBM·BOM 키가 전 구간에 흐르는 상태) + 용량 KPI — **통합 로드맵, 연결성 먼저**.

---

## 0. Executive Summary

P0·P1은 코드 레벨에서 전부 실재·정확함이 검증됨(allowlist 14테이블·결정론 estimator·856건 write·Task 1.6 rollup 실점등). 그러나 deep review가 2개의 구조 결함과 4개의 미점등 hop을 확정:

1. 🔴 **결정론 estimator가 라이브 파이프라인에 없음** — replay 1회성 스크립트만 호출. `wave_recommender.py:25`는 퍼지 estimator만 import, 신규 shipment는 estimated_cbm 미기록(폴백 0.5m³·conf 0.3→floor 0.8에 걸려 전부 수동行). **forward 75.1%는 방치 시 즉시 감쇠.**
2. 🟡 `CBM_유효`가 Airtable엔 live이나 `schema_pin.json` 미핀 → 드리프트 리스크.
3. ❌ 미점등 hop 4개: **order→pkg_schedule 폴백**(keys.py '향후' 주석, 0%) · **MES**(통합 0%) · **task→BOM**(라벨 PDF read만) · **WMS_BOM 1,702행 런타임 미소비**(kit CBM 미구현 — 굿즈 CBM 커버리지 46→85% 레버 방치).

**재정의:** 기존 P2(보관)·P3(입하)를 뒤로 물리고, **연결성 완결 phase 2개(P2a·P2b)를 먼저** 배치. 구 P2+P3은 P3'로 통합(분자 먼저, Max_CBM은 도착 시 주입 → circular gate 해소).

---

## 0.5 북극성 (사용자 명시, 2026-06-10) — Order-Driven Forward Planning

> **"고객 주문수량(예: 어떤 품목 200개)이 project에 등록되는 순간, order→task→pkg_schedule→movement→sync_parts/material→MES→TMS가 전부 자연스럽게 연결되어 — 자재소요량(MRP)·입하 CBM·WMS M/H·창고 CBM·기사 배정·운임까지 — 물건이 고객에게 가기 전에 입하부터 자재·생산·출하까지 이미 다 셋팅돼 있는 상태."** (글로벌 물류회사 수준의 주문 시점 사전 계획)

각 요소의 phase 귀속:

| 북극성 요소 | 메커니즘 | Phase |
|---|---|---|
| 주문 등록 → 키 연결 (order·PNA·굿즈코드) | P1 결정론 조인 (완료) + 상시화 | P1 ✅ / **P2a** |
| 출하 CBM → wave·기사 배정·차량이용률·운임 | estimated_cbm cron persist + CBM_유효 rollup (배선 완료) | P1 ✅ / **P2a** |
| BOM 전개 → 필요 파츠·수량 (MRP 원료) | WMS_BOM 1,702행 런타임 소비 (kit-CBM이 첫 소비자) | **P2b** |
| MES 생산·task 연결 | MES 크로스워크 + task↔BOM 검증 | **P2b** |
| 입하 CBM·도크/인력(M/H) 사전배치 | part_cbm × movement + MES 납기일 forecast + IBSA M/H | **P3'** |
| 창고 CBM (보관 적재율) | occupied ÷ Max_CBM | **P3'** |
| 자재소요량 계획(MRP) 리포트 = BOM×주문수량 − 현재고 | P2b(BOM)+P3'(part·재고) 산출물 결합 | **P3'~P4** |
| **주문 1건 등록 → 전 트랙 사전 셋팅 자동 캐스케이드** | 위 전부를 order-trigger 단일 파이프라인으로 묶기 | **P6(최종 통합, P4 후)** |

> P2a~P4는 각 hop·트랙을 점등하는 단계이고, **P6이 이들을 "주문 등록 1 이벤트 → 전체 사전 셋팅" 단일 캐스케이드로 통합**하는 종착점. P6 상세 설계는 P3' 종료 후(모든 입력이 실데이터로 점등된 뒤) 착수 — 지금 설계하면 추측 기반이 됨.

---

## 1. Deep Review 판정 요약 (증거는 plan 파일 `chain-wondrous-tower.md` §A–D)

### 연결성 매트릭스 (목표 체인 기준)
| Hop | 키 | 판정 |
|---|---|---|
| project→order | PNA | ✅ 결정론 |
| order→굿즈코드→Product CBM | 견적코드 | ✅ 결정론 (P1) |
| order→shipment→wave/배차일지/Capa | PNA+CBM_유효 | ✅ 결정론 (P1+1.6) — 단 **상시화 안 됨**(위 🔴) |
| order→pkg_schedule 폴백 | 굿즈코드 | ❌ 0% → **P2a** |
| MES↔PT/굿즈코드 | — | ❌ 0% → **P2b** (크로스워크만) |
| task→BOM | PT | ❌ 라벨 read만 → **P2b** (검증·승급만) |
| WMS_BOM→kit CBM | 굿즈→PT | ❌ 미소비 → **P2b** |
| movement→part CBM (입하) | PT | ⏳ → **P3'** |
| 보관 occupied/Max_CBM | PT+Location | ⏳ → **P3'** |

### P2~P5 기존 계획의 결함
- `part_cbm.py`(P2·P3 공용 임계경로) 미존재, QC버킷 매핑 미정의(~20% 치수 결손).
- 구 P2 circular gate: Max_CBM(사용자 실측)이 gate를 막지만 분자(occupied)는 지금 빌드 가능 — 병렬화 미문서화.
- P3 '외부입하' 이동목적 값 목록 미정의(`mh_backfill_to_ibsa.py` '생산산출' 하드코딩).
- `WMS_BOM.구성유형` 0% 백필 소유 불명 → P3'로 확정.
- `capacity_snapshot.py`(P4) 미존재, GHA/Supabase 계약 미정의.
- 과거 백로그(no_order 39.6%) order 미러 window 확장 — 무소유 → P5로 확정.

---

## 2. 확정 결정 (사용자 승인, 2026-06-10)

1. **로드맵 = C안 "연결성 전부 먼저"** — 연결성 hop 점등(P2a·P2b) 후 용량 KPI(P3').
2. **MES hop 스코프 = 크로스워크+리포트만** — MES 품목↔PT/굿즈코드 키 해소를 `WMS_KeyCrosswalk`에 기록 + 매칭률 리포트. 소비(납기일 forecast·규격 보강)는 P3'. *YAGNI 가드: P2b에서 MES 데이터 집계·예측 금지.*
3. **task hop 스코프 = 검증+승급만** — task 투입자재 vs WMS_BOM 비교 리포트 + 일치 row `검증상태` 승급(이상→검증완료). **신규 BOM INSERT 금지**, 불일치는 리포트만.
4. **이번 세션은 설계·검토만** — P2a 구현은 다음 체인 세션.
5. Max_CBM 실측치 미보유 — P3' gate에서만 요구, 분자 빌드는 선행 가능.

---

## 3. 재배열 로드맵 (본 문서가 SSOT — phase-status.md에 미러)

| Phase | Scope | Gate | 사용자 체크포인트 |
|---|---|---|---|
| **P2a 출고 상시화 + pkg hop** | ① `wave_recommender.yml`에 `replay_outbound_cbm.py --recent 7 --write` step 추가(3×/day, WRITE_TOL idempotent) → 신규 shipment estimated_cbm 자동 persist, 기존 coalesce(`wave_recommender.py:186-195`)가 필드에서 픽업 ② `resolve_goods_code` tier-2: code-side pkg_schedule join(blank 굿즈코드→project→pkg_schedule) ③ `schema_pin.json`에 `CBM_유효` 핀 ④ repo hygiene(*.bak gitignore·삭제, 회의록·briefs commit) | **rolling 7d forward coverage ≥70% 자동 유지** + blank-code 회수율 측정 | 없음 (코드만) |
| **P2b MES·task·BOM hop 점등** | ① MES 품목↔PT/굿즈코드 해소 → `WMS_KeyCrosswalk` INSERT + 매칭률 리포트(소스 read-only) ② task 투입자재 vs `WMS_BOM` 비교 리포트 + 검증상태 승급 ③ **kit-CBM 폴백**: Product CBM 없는 굿즈 → Σ(WMS_BOM 소요량 × WMS_ItemMaster.CBM_개당_m3) | hop 매트릭스 전 구간 키 해소율 리포트 + 굿즈 CBM 커버리지 46%→측정 (목표 85%) | 없음 |
| **P3' part_cbm + 보관·입하** (구 P2+P3 통합) | `part_cbm.py`(PT→dims→m³·QC버킷·신뢰도, `utils/cbm_utils.py`·`scripts/cbm_inbound_check.py` 파서 통합) → occupied 분자 빌드 → **Max_CBM 도착 시 주입** → movement 입하 CBM + `WMS_BOM.구성유형` 백필 + MES 납기일 forecast(P2b 크로스워크 소비) | 보관·입하 적재율 + 커버리지% (분모 도착 후) | **Max_CBM 실측치** · **이동목적 외부입하 분류** |
| **P4 대시보드** | `capacity_snapshot.py` + capacity_series.json GHA cron (기존안 유지) | forward curve · 트랙간 중복 0 | horizon |
| **P5 백로그** | 기존안 + **과거 order 소스 확보(no_order 39.6%)** + W1 slot filter test 수정 + 6 중복코드 | deferrable | — |

## 4. 컴포넌트 경계 (P2a·P2b)

- **P2a-①** `.github/workflows/wave_recommender.yml` — recommend step 앞에 replay step 1개 추가(YAML ~10줄). 코드 수술 없음. `.env` secrets 기존 재사용.
- **P2a-②** `harness/backbone/keys.py` — `resolve_goods_code(row, pkg_goods_by_project=None)` tier-2 인자 추가(순수 함수 유지). pkg_schedule fetch·project맵 빌드는 replay 스크립트 측. 반환 mode `'pkg'` 신설.
- **P2a-③** `harness/_core/schema_pin.json` — `CBM_유효` 필드ID 핀(Airtable 조회 후) + 커밋.
- **P2b-①** 신규 `scripts/backbone/mes_crosswalk.py` — MES read(`AIRTABLE_MES_PAT`) → 키 매칭 → `WMS_KeyCrosswalk` INSERT(allowlist 내) + stdout 리포트. dry-run 기본, `--write` 게이트.
- **P2b-②** 신규 `scripts/backbone/task_bom_verify.py` — ⚡task read → WMS_BOM 대조 → 리포트 + 일치 row `검증상태` PATCH(allowlist 내). dry-run 기본.
- **P2b-③** `harness/dispatch/cbm_estimator.py` — 결정론 경로에 kit-CBM 폴백 tier 추가. confidence = min(자식 part CBM 신뢰도) × 0.9 (상한 0.8 — Product formula 직접조인 0.9~1.0보다 항상 낮게, 기존 신뢰도 사다리 §6과 정렬). `WMS_BOM`·`WMS_ItemMaster` 로더는 `harness/backbone/` 기존 모듈 재사용.

## 5. Validation Contract (갱신)

| Gate | Baseline | Target | Phase |
|---|---|---|---|
| forward coverage 자동 유지 (rolling 7d) | 1회성 75.1% | **≥70% 상시** (cron 산출물로 증빙) | P2a |
| blank-code(프로젝트無 24%) pkg 폴백 회수율 | 0% | 측정·보고 (목표치는 측정 후 확정) | P2a |
| hop 키 해소율 매트릭스 | 4 hop ❌ | 전 hop 측정치 보고 | P2b |
| 굿즈 CBM 커버리지 (kit-CBM 포함) | 46.2% | ≥85% | P2b |
| 보관·입하 적재율 + 커버리지% | 0 | spec §8 기존 목표 유지 | P3' |
| 소스 write(⚡/MES/SERPA) | — | 0 (allowlist 불변) | 전 phase |

## 6. 리스크 & 가드

1. **cron write 폭주** — replay는 WRITE_TOL idempotent + `--recent 7` 한정. 첫 도입 주는 audit jsonl 모니터.
2. **kit-CBM 이중계상** — Product CBM 존재 굿즈에는 폴백 미적용(우선순위 사다리 고정). partial_skip 게이트 불변.
3. **MES/task 스코프 크리프** — §2 YAGNI 가드 명문화: P2b는 키 해소·검증만, 집계·예측·BOM 신규행 금지.
4. **Immutable Ledger 불변** — movement·PropagationLedger INSERT-only, 추정→estimated_cbm only, Total_CBM 미터치.

## 7. 다음 단계

1. (본 spec) commit + 트래커/핸드오프 미러 갱신.
2. 다음 세션: `/chain next` → P2a handoff(`~/.claude/plans/cbm-capacity-backbone-p2a-handoff.md`) → `superpowers:writing-plans`로 P2a TDD 상세계획 → 구현.
