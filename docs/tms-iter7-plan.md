# TMS AutoResearch Iter7 — Plan (drafted 2026-05-17)

> Author: SK-06 tms-otif-kpi · Reviewer: D1 scm-logistics-expert (pending)
> Triggered by: D-mission candidate C (Phase 2 follow-up handoff)
> Prior state: Iter1-6 operational (`scripts/tms_weekly_runner.py`), latest reports W16-W19, CBM-PHASE-D-01 (util_v2) shipped.

---

## 분석 목표 (3 lines)
1. **내부 소화율 4주 정체 (W16 56.2 → W17 61.8 → W18 60.0 → W19 60.5%) 의 구조적 원인 진단** — 박종성 여유 14일/월 vs 기사 1명 추가 투입 vs 고고엑스 단가 재협상 3-way ROI 비교.
2. **차량이용률 v1(count-based, deprecated) ↔ v2(CBM-weighted) 사후 비교** — v1 폐기 정당화 증거 수집 및 v2 단독 운영의 신뢰구간 측정 (n=38 표본 한계 극복용 6주 확장).
3. **Forecast 정확도(MAPE) 백테스트** — Iter5 예측 vs W17~W19 실측 편차 추적 → 추세 보정계수 0.3 적정성 검증.

## 주요 KPI

| # | 지표 | 산식 | 출처 | 목표 |
|---|---|---|---|---|
| K1 | 내부 소화율 (퀵 수도권) | 자체기사 출하 / 퀵수도권 총건 | tms_weekly_runner Iter2 | ≥80% |
| K2 | **차량이용률 v2** (CBM 적재율) | Σ Total_CBM / (트럭용량 × 운행일) | Iter2 (per-driver) | ≥70% |
| K3 | **차량이용률 v1 shadow** (count-based) | 운행건수 / (운행일 × 기사 capacity 10건/일) | **신규 — Iter7만 한시 계산** | 비교용 (deprecate 증거) |
| K4 | 오버부킹율 | 배차일지 오버부킹=true 건 / 전체 배차 | dispatch 테이블 | <5% |
| K5 | OTIF On-Time | On-Time=true / 전체 OTIF | Iter4 | ≥90% |
| K6 | In-Full | In-Full=true / 전체 OTIF | Iter4 | ≥95% |
| K7 | **Forecast MAPE** (신규) | Σ \|예측-실측\|/실측 ÷ N | W17~W19 백테스트 | <15% |
| K8 | **약속납기일 백필 sample size** | n (이번 분기 OTIF 레코드 수) | OTIF 테이블 | ≥200건/4w |
| K9 | Lane별 평균 CBM (top 5 zones) | Σ Total_CBM / N per zone | 신규 — Iter7 hint | 정보 |
| K10 | 미분류 배송방식 비율 | 미분류 건 / 전체 | Iter3 | <3% (W18: 8.7%) |

## 데이터 기간 — **6주 확장 (W14~W19, 2026-04-06 ~ 2026-05-17)**

- 사유: 기존 30일 윈도우는 n=38로 ±5%p 변동성 → 6주(약 n=60~70) 확장 시 95% CI 폭 절반으로 축소 예상
- 백테스트 영역: W17~W19 실측 vs 각 주 Iter5 예측치 3-pair MAPE
- 백필 대상은 변경 없음 (직전 7일 약속납기일 그대로)

## 실행 커맨드

```powershell
# 0. 평소 주간 러너 (Iter1-6 그대로) — 회귀 baseline 확보
py -m scripts.tms_weekly_runner

# 1. Iter7 신규 분석기 (별도 모듈, 기존 러너 비침습)
py -m scripts.tms_iter7_analyzer `
    --weeks 6 `
    --backtest-from 2026-04-20 --backtest-to 2026-05-15 `
    --output _AutoResearch/SCM/outputs/TMS-2026-W20-Iter7.md `
    --emit-v1-shadow

# 2. (옵션) dry-run으로 데이터만 확인
py -m scripts.tms_iter7_analyzer --weeks 6 --dry-run
```

> 신규 스크립트: `scripts/tms_iter7_analyzer.py` — 기존 `tms_weekly_runner.py`의 `step_pull_data` / `analyze_iter*` 함수 **import 재사용**, 신규 함수 4개 추가:
> - `analyze_iter7_internal_rate_3way_roi(data)` — 박종성 +7일 / 기사 추가 / 고고엑스 단가 -X% 시나리오 NPV
> - `analyze_iter7_v1_v2_shadow(data)` — v1·v2 동시 계산 + 상관계수 + Bland-Altman 편차
> - `analyze_iter7_forecast_mape(historical_forecasts, actuals)` — W17~W19 백테스트
> - `analyze_iter7_lane_cbm(data)` — 구간유형별 평균 CBM·고고엑스 흡수 잠재력

## 예상 산출물

| 파일 | 형식 | 위치 |
|---|---|---|
| 메인 리포트 | `TMS-2026-W20-Iter7.md` | `C:\Users\yjisu\Documents\ClaudeVault\SCM\_AutoResearch\outputs\` |
| 백테스트 raw | `TMS-Iter7-mape-backtest.csv` | 동일 outputs/ |
| log.md 엔트리 | `## [2026-05-XX] WEEKLY+ITER7 \| ...` | `.../SCM/_AutoResearch/wiki/log.md` |
| index.md 행 | 1 row | `.../SCM/_AutoResearch/wiki/index.md` |
| Slack DM | KPI 5종 + 3-way ROI 요약 | `_notify_slack_report` 확장 |

**리포트 섹션 구조:**
1. KPI 요약 표 (K1~K10, W19 대비 Δ 컬럼)
2. Iter1-6 기존 분석 (러너 결과 그대로 임베드)
3. **Iter7-A: 내부 소화율 3-way ROI**
   - 시나리오 1: 박종성 운행일 15→22일 (월 7건 추가 흡수, 인건비 +α)
   - 시나리오 2: 4번째 내부 기사 정규직 채용 (월 ~70건 흡수, 인건비 +β)
   - 시나리오 3: 고고엑스 단가 10·15·20% 인하 협상 가정 (소화율 무변, 비용만 ↓)
   - NPV 12개월 비교 표 + 권장안
4. **Iter7-B: v1 vs v2 shadow** (n=6주, Pearson r, 평균 편차, deprecate 결정 근거)
5. **Iter7-C: Forecast MAPE 백테스트** (요일별·전체 MAPE, 0.3 보정계수 sensitivity)
6. **Iter7-D: Lane별 CBM 분포** (수도권 vs 지방광역시 vs 도서산간 — SK-09 인계용 hint)
7. 다음 Iter8 후보 + Validation Contract 통과 확인

## Validation Contract (Karpathy 준수)

- **must_pass (4):**
  1. 리포트가 outputs/에 저장되고 log.md / index.md 동기 갱신
  2. 6주 데이터 fetch 시 표본 ≥ 50건 (n=38 한계 극복 증거)
  3. v1·v2 shadow 상관계수 ≥ 0.7 또는 < 0.7 (둘 다 valid finding, 사전 가설 없음)
  4. Forecast MAPE 백테스트가 3-pair 모두 산출됨 (NaN 없음)
- **must_not (3):**
  1. Airtable 직접 UPDATE/DELETE 금지 — backfill PATCH는 기존 `step_backfill`만 사용
  2. `tms_weekly_runner.py` 본 파일 수정 금지 — 신규 모듈로 분리 (회귀 방지)
  3. Slack DM 토큰·PAT를 리포트에 echo 금지

## 다음 Iter8 후보 (planning 중 식별)

1. **Lane 단가 × CBM 통합 ROI (SK-09 위임 후보)** — Iter7-D 결과 토대로 `tms_cost_lane` 테이블 신설 검토. 현 러너에 운임 비용 섹션이 명목상 있지만 (CLAUDE.md "운임 비용 섹션 포함" 요구) 실제 미구현 — Iter8에서 정식 편입. **트리거**: Iter7-D에서 lane 간 CBM 편차 30%+ 확인 시.
2. **Driver fatigue / 회전율 분석** — 박종성 +7일 시나리오의 risk 점검. 이장훈·조희선 29일/월 풀가동 지속 시 burnout·이직 리스크 정량화. **트리거**: Iter7-A 시나리오 1 채택 시 필수 선행.

(부수 후보 — 우선순위 낮음)
- Bullwhip ratio (Iter5 forecast vs 실측 진동폭 / 수주 진동폭) — SCOR 표준 KPI 보강
- 배송클레임 lead indicator 후보 (지연일수 vs 클레임 발생률 회귀) — n=4 미달로 6개월 누적 후 재시도

---

## 우선순위 / 일정 권고

- **착수 시점**: 차주 월요일(2026-05-18) 정기 weekly 러너 실행 직후, 같은 데이터 스냅샷으로 Iter7 분석 1회 실행
- **소요**: 신규 스크립트 작성 2~3h + 검증 1h = 3~4h (단발 가능, 미션 불요)
- **모델**: SK-06 (opus, 본 에이전트 자체) — Iter7-A NPV 시나리오는 D1 scm-logistics-expert 위임 검토
- **리스크**: 6주 확장 시 Airtable rate-limit (현 0.2s sleep) — 페이지네이션 한도 모니터링 필요
