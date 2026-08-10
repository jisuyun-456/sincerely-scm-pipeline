# 핸드오프 — 전환 KPI 완결성 + 운영 KPI 실측화 (다음 세션 착수용)

**작성일** 2026-08-03 · **브랜치** `v2-cascade-code-alias` · **선행 브리프** [2026-07-31 주간 KPI 보드 cascade 핸드오프](2026-07-31-weekly-kpi-board-cascade-handoff.md)
**구현 계획** `~/.claude/plans/kpi-sorted-planet.md` · **상세 맥락** 이전 세션 트랜스크립트 `e8241d2c-…jsonl`

---

## 0. 한 줄 목표

SCM 물류팀의 "가장 기본적인 물류 자동화 계산"(**CBM · M/H**)을 **완결성 100%**로 끌어올리고, 합성(random)으로 채워진 운영 KPI를 **실측 데이터로 전환**한 뒤, 멈춰있던 주간 리포트를 웹에 복구한다. 이것이 이후 디지털 트윈 · capa 확장 의사결정의 데이터 기초.

---

## 1. 이번 세션에 완료한 것 ✅

| 항목 | 상태 | 증거 |
|---|---|---|
| CI secret 재매핑 (`AIRTABLE_PAT` → `AIRTABLE_API_KEY_TMS`) | ✅ 커밋·push | `c55f36e`, `weekly-full-pipeline.yml` 34·42행 · `scorecard.yml` 35행 |
| `permissions: contents: write` 추가 + `git push \|\| true` | ✅ | 위 두 워크플로 |
| `capacity_snapshot_run.py` 재시도 이식 (7주 ReadTimeout 실패 해소) | ✅ 커밋 | `_get_with_retry()` 이식, `py_compile` 통과, dry-run 그린(7주 만에 첫 성공) |
| scorecard 워크플로 dry-run 그린 | ✅ | GitHub Actions 확인 |
| **W31(7/27~31) 운영 KPI 대시보드** | ✅ Artifact 게시 | 3탭(입고·검수·출하), CSS 막대그래프, 실측/proxy/하한 라벨 |
| **합성→실측 전환 방안 확정** | ✅ | 아래 §3 |

**W31 실측 핵심 수치** (대시보드 근거): 입고 247건(완료 99.6%) · **QC 불합격률 0.40%**(품질이슈 1건/247, movement 이슈카테고리 기준 **실측**) · 출고 54건 · 창고 가동율 42.5%(하한, CBM 커버리지 희박) · 기사별 적재율(배차일지 미입력으로 하한).

---

## 2. 확정 사실 — 재확인·재조사 불필요 (전제로 사용)

- **CBM 완결성 baseline = 81.2%** (`최종 외박스 수량 값` + `CBM_유효` 동시 유효, 순수 고객납품 1,645건 기준). "77~78%"는 오라벨이었음.
  - 로드맵: P1(코드) `box✓cbm✗` 152건 매칭 → ~87% / P2(운영) 다영기획 외주 156건 박스수량 입력 → ~95% / P3(타팀) Lv3 자재 PT 규격 표준화(품질혁신·안나님) → 100%.
- **M/H 2층 모델**: ① 입력 완결성 입하·검수·입고 **99.7%** ✅ (프리패키징 7.9%, WMS movement, 7월~ 입력 시작) · ② 측정 정합성 **29% completeness** (작업 시작 타임스탬프 부재로 원천 검증 불가).
- **M/H 표준 검증** (3명 편성 = 입하 1 · 입고 1 · 검수 1, 각 주 40h): 입고 표준 신뢰(40MH의 73%). 입하·검수는 **겸업**(프리패키징·검수 병행)으로 저평가. 현재 유휴시간 김 → **올해 4분기 재측정이 편함**.
- **검수 정의 = 2.875분/프로젝트** 로 통일 (현 backfill 4.60/rec 아님).
- **M/H 공식** (커스텀, `mh_calculator.py` — ELS 표준 아님): 입하 `min(5.0, max(0.5, CBM×4.0))×1.15` · 검수 `2.5×1.15=2.875/proj` · 입고 `(3.0+min(2, CBM×7))×1.15 + 2.5 + counting(2~7min)`.
- **제외 확정**: 피킹 정확도 · 자재 피킹수 · 내부 소화율 · 재고 정확도 · 6개 가지치기 운영 KPI(후속 단계).

---

## 3. 다음 세션 착수 — 우선순위 순

### ★ 1순위 — Phase 2: `wms_sap_weekly.py` 합성→실측 교체 (코드만, 신규 현장입력 0)

`scripts/wms_sap_weekly.py`의 `random` 생성 3곳을 실측 소스로 교체. **모두 기존 실데이터에 소스 존재 확인됨.**

| 지표 | 현재(합성) | 실측 소스 | 방법 |
|---|---|---|---|
| Dock-to-Stock | `random.randint(60,480)` | IBSA `sync_movement` 타임스탬프 | `입하완료처리시간` → `입고수량입력시간` diff (음수·이상치 제거) |
| 공급사 납기 | (합성) | movement `입하예정일` vs 실제 입하 | 협력사별 지연 계산 |
| QC 불합격률 | `random.uniform(...)` | movement `이슈카테고리` = **품질이슈** | 품질이슈 ÷ 입고건수 (**W31=0.40% 이미 검증**) |
| ~~피킹정확도·자재피킹수~~ | `random.uniform(97,100)` | — | **제외** (합성 제거 후 미측정 표기) |

- **검증**: random import 제거 확인 · 각 지표가 실측 소스 분포에서 나오는지 대조 · Immutable Ledger 준수(INSERT-only/PATCH 재계산만).
- **주의**: `weekly-full-pipeline.yml` full run은 합성 데이터를 **재생성**하므로 Phase 2 완료 전 실행 금지.

### 2순위 — PR #3 병합 ⚠️ 사용자 최종 확인 필요

- `A3/B3/D1` 패널 · `cbm_panels.py`가 `v2-cascade-code-alias`에만 있고 main에 부재.
- `gh pr merge 3 --admin --merge` (병합커밋 유지). **admin 우회 = 본인 리뷰 게이트 우회이므로 반드시 사용자 승인 후 실행.**

### 3순위 — `deploy_pages.yml` 복구 (대시보드 웹 게시)

- GH006(main 브랜치 보호가 워크플로 self-push 차단, 2026-05-12 이후 Pages 재배포 0회).
- `capacity-data` 패턴의 side-branch(`pages-history`) force-push로 우회 + capacity-data restore 스텝 추가.
- ⚠️ `pages-history` 신설 = 두 번째 특수 브랜치, 장기 운영 동의 필요.

### 4순위 — 주간 리포트 W31 실측 반영

- `_AutoResearch/SCM/outputs/WeeklyReport-물류파트-2026-W32.md`가 현재 예시 데이터 → W31 실측치로 갱신.
- 전환 KPI 섹션(CBM 완결성·M/H 완결성) + 운영 KPI 4탭 각 지표에 데이터 상태 라벨(실측/합성→실측/proxy/하한) 유지.

---

## 4. 열린 리스크 / 사용자 확인 대기

1. **PR #3 admin 병합** — 리뷰 게이트 우회, 진행 전 승인.
2. **`pages-history` side-branch 신설** — 장기 운영 동의.
3. **운영 습관 의존 항목**(코드 아님): 다영기획 박스수량(CBM P2) · 프리패키징 입력(M/H) · 배차일지 재개(차량 적재율). 물류팀 실행 필요 — 리포트엔 진행상태로 표기.

---

## 5. 핵심 파일·경로·산출물

- **CI**: `.github/workflows/{weekly-full-pipeline,scorecard,deploy_pages,capacity_snapshot,order_cascade}.yml`
- **실측화 대상**: `scripts/wms_sap_weekly.py` (random 3곳)
- **재시도 참조 구현**: `scripts/backbone/capacity_snapshot_run.py::_get_with_retry` (이미 완료, 패턴 복사용)
- **주간 리포트**: `_AutoResearch/SCM/outputs/WeeklyReport-물류파트-2026-W32.md`
- **베이스**: WMS `appLui4ZR5HWcQRri` · TMS `app4x70a8mOrIKsMf` · IBSA `app6DGHCPI3Yh3IFS`(sync_movement `tblhzYiltSBm6vxBz`)
- **라이브 조회용 서브에이전트**: tms-otif-kpi (읽기전용, 필요시 재기동)
- **W31 대시보드 Artifact**: https://claude.ai/code/artifact/597bbf8c-5aaa-4722-9e51-d824d5742d83

---

## 6. 다음 세션 첫 액션 (권장)

```
1. 이 문서 읽기 → §2 확정사실 전제, §3 우선순위 확인
2. scripts/wms_sap_weekly.py Read → random 3곳 위치·현행 로직 파악
3. IBSA sync_movement / WMS movement 필드 실측 스키마 라이브 확인 (tms-otif-kpi or REST)
4. Phase 2 코드 교체 → 검증(random 제거·분포 대조) → 커밋
5. 이어서 PR#3(사용자 확인) → deploy_pages → 리포트 반영
```
