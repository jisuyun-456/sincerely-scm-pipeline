# Sub-Spec 5 — Scorecard + KPI Design

> Lane Strategy v3 | P5 | 2026-05-28
> Output: Slack DM 상세형 | Cron: 매월 1일 00:01 KST

---

## 1. 목표

월간 carrier·자체 기사 9개사 대상 4축 Scorecard 자동 산출 + KPI 3종 시계열 추적.
결과를 Slack DM 상세형으로 발송. RFQ 트리거·대시보드는 P5 스코프 외.

---

## 2. 아키텍처

### 파일 구조

```
harness/scorecard/
  __init__.py
  calc.py           ← 4축 점수 산출 (carrier별, 전월 기준)
  kpi_tracker.py    ← KPI 3종 계산 + JSONL 히스토리 적재

scripts/scorecard/
  run_monthly.py    ← 오케스트레이터: calc → kpi → Slack DM
  scorecard_history.jsonl  ← 월간 스냅샷 누적 (INSERT ONLY)

tests/scorecard/
  test_calc.py
  test_kpi_tracker.py

.github/workflows/
  scorecard.yml     ← 매월 1일 00:01 KST (cron: "1 15 1 * *")
```

### 데이터 흐름

```
[매월 1일 cron]
  → run_monthly.py
    → calc.py
        · 배송파트너 9개사 목록 조회
        · Shipment (전월 출하완료 + estimated_cbm)
        · OTIF 테이블 (On_Time / In_Full, 전월)
        · 배송클레임 (발생일 기준 전월)
        · 운임단가 (carrier별 target_rate)
      → carrier별 4축 점수 dict 반환
    → kpi_tracker.py
        · K-LC-1/2/3 계산
        · scorecard_history.jsonl append (이번 달 스냅샷)
        · 직전 스냅샷 diff → 전월 비교값 반환
    → Slack DM 조립 (상세형 B) → notifier.py 경유 발송
```

---

## 3. 4축 Scorecard

### 축 구성 (Flexibility 제거 — 추적 데이터 없음)

| 축 | 가중치 | 데이터 소스 |
|---|---|---|
| Cost | 30% | 운임단가 테이블 + Shipment.운송비용 + estimated_cbm |
| Reliability | 35% | OTIF 테이블 (On_Time/In_Full) + otif_estimator 가정값 |
| Capacity | 20% | Shipment 건수 + 배송파트너.max_daily_orders |
| Damage | 15% | 배송클레임 테이블 (배송파트너 링크) |

### 점수 공식

**Cost (0~100)**
```python
actual_rate = total_운송비용 / total_estimated_cbm  # ₩/CBM
target_rate = 운임단가[carrier].target_rate
score = min(100, (target_rate / actual_rate) * 100)
# 운임단가 target_rate 없는 carrier → Cost 축 N/A (총점 계산 시 제외)
```

**Reliability (0~100)**
```python
otif_records = OTIF[배송방식_SHP == carrier, month == prev_month]
score = (On_Time_count / total_count) * 100
# OTIF 레코드 없는 carrier → otif_estimator 가정값 사용
```

**Capacity (0~100)**
```python
# 자체 기사 (이장훈·조희선·박종성)
utilization = shipments / (max_daily_orders * 영업일수)
score = min(100, utilization * 100)

# 외주 carrier
score = min(100, (this_month_count / prev_month_count) * 50) if prev_month_count else 50
```

**Damage (0~100)**
```python
claim_count = 배송클레임[배송파트너 == carrier, 발생일.month == prev_month].count()
shipment_count = Shipment[carrier == carrier, month == prev_month].count()
claim_rate = claim_count / max(shipment_count, 1)
score = max(0, 100 - claim_rate * 5000)
# 0건 → 100점 / 2% → 0점
```

**총점**
```python
total = Cost*0.30 + Reliability*0.35 + Capacity*0.20 + Damage*0.15
# N/A 축 있으면 나머지 가중치로 재정규화
```

---

## 4. KPI 3종

K-LC-4(RFQ 트리거)·K-LC-5는 P5 스코프 외.

### K-LC-1: 자체 기사 활용도

```
value   = (이장훈+조희선+박종성 배송 건수) / (W1+W2+W3+수동 전체 자동 대상 건수) × 100
baseline = scorecard_history.jsonl 첫 항목의 K_LC_1.value
target  = baseline + 20%p
```

### K-LC-2: Wave 자동화 비중

```
value  = wave_recommendation ≠ '수동' AND IS NOT NULL 건수
         / 전체 자동 대상 Shipment 건수 × 100
target = 70%+
```

### K-LC-3: 외주 Spillover 비용

```
value    = wave_recommendation ∈ {spillover_고고엑스, spillover_로젠} 건의 운송비용 합계 (₩)
baseline = scorecard_history.jsonl 첫 항목의 K_LC_3.value
target   = baseline × 0.80
```

---

## 5. JSONL 스냅샷 스키마

`scripts/scorecard/scorecard_history.jsonl` — INSERT ONLY, 월 1 row.

```json
{
  "month": "2026-06",
  "generated_at": "2026-07-01T00:01:00+09:00",
  "carriers": {
    "이장훈": {
      "cost": 95.0, "reliability": 91.0, "capacity": 80.0, "damage": 100.0,
      "total": 91.2, "cost_na": false
    },
    "로젠": {
      "cost": 72.0, "reliability": 85.0, "capacity": 50.0, "damage": 90.0,
      "total": 77.5, "cost_na": false
    }
  },
  "kpi": {
    "K_LC_1": {"value": 0.61, "baseline": 0.43, "delta": 0.18, "target": 0.63},
    "K_LC_2": {"value": 0.82, "target": 0.70},
    "K_LC_3": {"value": 1050000, "baseline": 1200000, "delta_pct": -0.125, "target": 960000}
  }
}
```

---

## 6. Slack DM 포맷 (상세형 B)

```
📊 [2026-06] Carrier Scorecard
대상 9개사 · 기준: 2026-06-01 ~ 2026-06-30

── 이장훈 (91.2/100) ──
Cost        30% × 95.0pt = 28.5
Reliability 35% × 91.0pt = 31.9
Capacity    20% × 80.0pt = 16.0
Damage      15% × 100.0pt = 15.0

── 박종성 (82.4/100) ──
...

⚠️ 주의 (70점 미만)
  다영기획 54.1 / 베스트원 48.7

──────────────────────
KPI 상세 (전월 비교)
K-LC-1 자체기사 활용도  61% → 64% (+3%p) ↑  [목표: 63%]
K-LC-2 Wave 자동화 비중 82%          ✅       [목표: 70%]
K-LC-3 Spillover 비용  ₩1,050,000 (-12.5%)   [목표: ₩960,000]
```

70점 미만 carrier는 `⚠️ 주의` 섹션에 별도 표시.

---

## 7. Validation Contract

| # | 조건 | 검증 |
|---|---|---|
| C1 | `scorecard.yml` cron 매월 1일 정상 실행 | GitHub Actions dry-run trigger 확인 |
| C2 | 9개 carrier 전원 4축 점수 + 총점 계산 | `test_calc.py` mock 데이터 수치 검증 |
| C3 | K-LC-1/2/3 계산 + JSONL 스냅샷 적재 (첫 달 baseline 설정·두 번째 달 전월 비교) | `test_kpi_tracker.py` 2-run 시나리오 |
| C4 | Slack DM 발송 (상세형 B 포맷, ⚠️ 주의 섹션 포함) | dry-run 후 DM 수신 + 포맷 육안 검증 |

**C4 원본 (6개월 ROI 비교 보고서):** 자동화 검증 불가. 시스템 가동 2026-12월 수동 리뷰.

---

## 8. Out of Scope (P5)

- RFQ 트리거 알림 (K-LC-4)
- sincerely-scm-dashboard 대시보드 페이지
- Flexibility 축 (데이터 없음)
- 운임 자동 입력 파이프라인 (Slack → Dropbox PDF → Airtable PATCH) → feature_list 별도 항목

---

## 9. 의존성

| 의존 | 상태 |
|---|---|
| Sub-Spec 2 estimated_cbm | ✅ 완료 |
| Sub-Spec 3 wave_recommendation 필드 | ✅ 완료 |
| Sub-Spec 4 otif_estimator + change_detector | ✅ 완료 |
| 배송파트너.max_daily_orders (Sub-Spec 1) | ✅ 완료 |
| harness/_core/notifier.py (Slack 발송) | ✅ 완료 |
