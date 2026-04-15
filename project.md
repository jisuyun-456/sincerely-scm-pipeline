# TMS AutoResearch Project

> 최초 작성: 2026-04-15  
> 베이스: `app4x70a8mOrIKsMf` (TMS)  
> 목적: Karpathy AutoResearch 패턴으로 TMS 운영 데이터를 반복 분석, Q2 KPI 달성 근거 도출

---

## 연구 목표

| KPI | Q1 실적 | Q2 목표 | 해결 방향 |
|-----|---------|---------|---------|
| 차량이용률 | 27~57% | ≥70% | Iteration 2 — 배차 최적화 |
| OTIF 달성률 | proxy (측정 시작) | ≥90% | Iteration 4 — SLA 기반 실측 전환 |
| 운송비 | 월 8.5M원 | 절감 시뮬레이션 | Iteration 3 — 방식별 ROI |
| 미입하 | 107건 | ≤10건 | WMS Phase 연계 |

---

## 데이터 소스

| 테이블 | ID | 주요 필드 | 건수 |
|--------|-----|---------|-----|
| Shipment | `tbllg1JoHclGYer7m` | 출하확정일, 구간유형, 약속납기일 | ~700건↑ |
| 배차일지 | `tbl0YCjOC7rYtyXHV` | 날짜, 차량이용률, 배정물량_합계 | 102건+ |
| OTIF | `tbl4WfEuGLDlqCTQH` | On_Time, In_Full, OTIF_Score | 348건+ |
| 운임단가 | `tblQA1ev9fjbowUoP` | 구간유형, 기본운임, CBM당_추가운임 | 15건 |
| 배송SLA | `tblbPC6z0AsbvcVxJ` | 구간유형, 배송방식, 목표배송일수 | 9건 |
| 택배추적로그 | `tblonyqcHGa5V5zbj` | 운송장번호, 추적상태 | 73건+ |

---

## SLA 리드타임 마스터 (백필 기준)

| 구간유형 | 배송방식 | 목표배송일수 | OTIF목표 |
|---------|---------|------------|---------|
| 수도권 | 직배송 | 1 | 95% |
| 수도권 | 택배 | 3 | 90% |
| 수도권 | 퀵 | 1 | 98% |
| 지방(광역시) | 직배송 | 2 | 90% |
| 지방(광역시) | 택배 | 5 | 85% |
| 지방(광역시) | 퀵 | 2 | 92% |
| 지방(기타) | 직배송 | 3 | 85% |
| 지방(기타) | 택배 | 7 | 80% |
| 도서산간 | 택배 | 10 | 70% |

---

## Iteration 계획

### Iteration 1: Baseline — 배송 볼륨 패턴
**연구질문:** 어떤 요일/주차에 출하가 집중되는가?  
**데이터:** Shipment 전체 (출하확정일 분포)  
**분석:**
- 요일별·주차별·월별 볼륨 히스토그램
- 드라이버별 평균 배정물량
- 구간유형 비율 (수도권 vs 지방)

**가설:** 특정 요일 집중 → 오버부킹 원인  
**산출:** `_AutoResearch/SCM/outputs/iter1_volume_baseline.md`

---

### Iteration 2: 차량이용률 최적화
**연구질문:** 왜 이용률이 27~57%인가? 어떻게 70% 이상으로 올릴 수 있나?  
**데이터:** 배차일지 + Shipment 연결  
**분석:**
- 이용률 분포 + 드라이버별 편차
- 오버부킹 3건 날짜·원인 분석 (3/13, 3/16, 4/3)
- 볼륨과 이용률 상관관계 (Pearson r)
- 최적 배정물량 구간 추정

**가설:** 고정 배차 + 볼륨 예측 없음 → 불균형  
**산출:** `_AutoResearch/SCM/outputs/iter2_utilization_analysis.md`

---

### Iteration 3: 운송비 최적화
**연구질문:** 배송방식별 실제 단가 vs 효율이 어떻게 다른가?  
**데이터:** 운임단가 + Shipment.구간유형/배송방식 + 정산관리  
**분석:**
- 방식별 건당 비용 (직배송 vs 택배 vs 퀵)
- 구간유형별 최적 방식 매핑
- 월별 운송비 정확 재계산 (전체 기준)
- 방식 전환 시 절감액 시뮬레이션

**가설:** 특정 구간은 택배가 직배송보다 저렴  
**산출:** `_AutoResearch/SCM/outputs/iter3_cost_optimization.md`

---

### Iteration 4: OTIF 실측 전환
**연구질문:** SLA 기준 약속납기일 적용 시 OTIF가 어떻게 바뀌는가?  
**데이터:** 배송SLA + Shipment.구간유형 + OTIF  
**분석:**
- proxy → 실측 전환 후 On_Time 비율 변화
- 구간유형별 OTIF 실적 vs 목표 gap
- 리스크 구간 (지방/도서산간) 식별
- 납기차이일 분포

**선행조건:** `scripts/backfill_promised_delivery.py` 실행 완료  
**산출:** `_AutoResearch/SCM/outputs/iter4_otif_conversion.md`

---

## Agent 구조

```python
AGENTS = {
    "LogisticsAnalyst": "배송 패턴, 볼륨, 구간, 드라이버 분석",
    "CostAnalyst":      "운임비용, 정산, 배송방식별 ROI",
    "CapacityAnalyst":  "차량이용률, 배차 최적화, 오버부킹 예방",
    "QualityAnalyst":   "OTIF, SLA 준수, 납기 실적",
}
# 각 Agent → insight(str) + confidence(float 0~1) + recommendation(str)
# 가중 합의: confidence 기반 평균 → 최종 권고안
```

---

## 실행 방식

**주간 통합 러너 (매주 월요일):**
```bash
python scripts/tms_weekly_runner.py
```

| 단계 | 내용 | 자동/수동 |
|------|------|---------|
| 1. 약속납기일 백필 | 지난 7일 Shipment 약속납기일 갱신 | 자동 |
| 2. 데이터 Pull | Shipment/배차일지/OTIF 최신 데이터 조회 | 자동 |
| 3. Iteration 분석 | 4개 분석 순서대로 실행 | 자동 |
| 4. 리포트 저장 | `_AutoResearch/SCM/outputs/week_YYYYMMDD.md` | 자동 |
| 5. log.md 업데이트 | 세션 기록 추가 | 자동 |

**최초 1회만 수동:**
```bash
python scripts/backfill_promised_delivery.py --mode all --dry-run  # 확인
python scripts/backfill_promised_delivery.py --mode all             # 전체 백필
```

---

## 파일 구조

```
SCM_WORK/
├── project.md                          ← 이 파일
├── scripts/
│   ├── backfill_promised_delivery.py   ← 약속납기일 주간 백필
│   └── tms_weekly_runner.py            ← 주간 통합 러너 (백필+분석+리포트)
├── _AutoResearch/SCM/
│   ├── wiki/
│   │   ├── log.md                      ← 세션별 iteration 기록
│   │   └── index.md                    ← outputs/ 링크 인덱스
│   └── outputs/
│       ├── iter1_volume_baseline.md
│       ├── iter2_utilization_analysis.md
│       ├── iter3_cost_optimization.md
│       └── iter4_otif_conversion.md
```

---

## 성공 지표 (Q2 2026)

| 지표 | 현재 | 목표 | 확인 방법 |
|------|------|------|---------|
| 차량이용률 | 27~57% | ≥70% | 배차일지 월평균 |
| OTIF 달성률 | proxy | ≥90% | OTIF 테이블 실측 |
| 운송비 절감 | 기준 없음 | 시뮬레이션 안 도출 | Iteration 3 산출 |
| 약속납기일 실측 전환율 | 0% | 100% | Shipment.약속납기일 ≠ 출하확정일 비율 |
