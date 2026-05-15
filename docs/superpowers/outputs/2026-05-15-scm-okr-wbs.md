# SCM 실 단위 재설계 — OKR / WBS / RACI (Sprint 4)

**미션 ID**: strategy-design-20260515-1607-scm-team-realignment  
**Sprint**: 4 / 4  
**Worker**: consulting-pm-expert (D3) + scm-logistics-expert (D1)  
**산출일**: 2026-05-15  
**입력**: Sprint 1 AS-IS 갭 / Sprint 2 KPI 트리 / Sprint 3 AX/DX 범위 (FTE=7명 확정)

---

## 1. 2026 OKR — 1-Page

### Objective

> **"SCM 물류팀(7명)이 AI 전환을 통해 2026년 내 측정 가능한 재무·생산성 지표를 확립하고, 동일 인원으로 처리 역량 1.5배를 달성한다"**

*근거 traceability*:
- D-01 통일된 목표(재무지표 기반) → "측정 가능한 재무·생산성 지표"
- D-02 인건비율 감소 + 수수료 계정 활용 → "AI 전환"
- D-03 리스크 차단 → "확립하고" (범위 확정 전제)
- D-04 수평 생산성 50% + 파트별 정렬 → "처리 역량 1.5배"

---

### Key Results

| # | Key Result | 측정 지표 | 기준값 | 목표값 | 달성 시점 | Owner | 측정 주기 |
|---|-----------|---------|------|------|---------|-------|--------|
| KR-1 | 물류팀 처리건수/FTE ≥ 현재 대비 +50% | Airtable 월별 집계 건수 ÷ 7명 | **미확인** — AX-2 Baseline 수집 후 확정 (4주 후) | Baseline × 1.5 | 2026-12-31 | 파트장 | 월 1회 |
| KR-2 | TMS AutoResearch 주간 보고 완전 자동화 | 수동 실행 횟수 = 0회/주 | 현재 수동 N회/주 (AutoResearch 스크립트 로그 확인) | 0회/주 | 2026-09-30 | Claude Code (DX-2 담당) | 주 1회 |
| KR-3 | AI 비용 더존 수수료 계정 내 별도 추적 시작 | 더존 보조계정 "AI도구비" 신설 완료 | 미신설 (현재 수수료비 혼합) | 신설 완료 + 3개월 이상 분류 데이터 보유 | 2026-08-31 | 재무담당 (AX-1 담당) | 월 1회 |
| KR-4 | KPI-3 생산성 Dashboard 운영 중 | Dashboard 접근 횟수 + 파트장 주간 리뷰 기록 | 0 (미구현) | Dashboard 운영 + 주간 리뷰 4주 연속 완료 | 2026-09-30 | 파트장 (DX-1 담당) | 주 1회 |

> **KR-1 주의**: Baseline 미확인으로 절대 수치 단정 불가. AX-2 완료(4주 후) 후 Baseline 수치 확정 → 목표값 갱신.  
> **KR-2 주의**: "현재 수동 N회/주"는 AutoResearch 실행 로그 확인 후 채움.

---

## 2. WBS (Work Breakdown Structure)

### 2.1 구조도

```
2026 SCM AX/DX 전환 프로그램
│
├── 1. AX 트랙 (사람·프로세스 변화)
│   ├── 1.1 더존 AI 비용 계정 분리 (AX-1)          ← 수동, 즉시 착수 가능
│   ├── 1.2 FTE 생산성 Baseline 수집 (AX-2)         ← 자동화, 즉시 착수 가능
│   ├── 1.3 R&R 재정의 문서화 (AX-3)                ← 수동, AX-1 후 착수
│   └── 1.4 현장 인원 AI 도구 온보딩 (AX-4)         ← 수동, DX-1 구현 전 착수
│
└── 2. DX 트랙 (시스템·자동화 변화)
    ├── 2.1 KPI-3 생산성 Proxy Dashboard (DX-1)      ← build-dashboard 미션
    ├── 2.2 TMS AutoResearch Iter 2 (DX-2)            ← build-pipeline 미션
    ├── 2.3 W-NEW-01 SAP 이동유형 마스터 (DX-3)      ← build-pipeline 미션
    └── 2.4 더존 KPI-1/2 추출 파이프라인 (DX-4)      ← build-pipeline 미션 (조건부)
```

### 2.2 Leaf-Level Work Packages

| WP ID | Work Package | Deliverable | Owner | 추정 시간 | 선행 의존성 |
|-------|-------------|------------|-------|--------|-----------|
| WP-AX1 | 더존 보조계정 "AI도구비" 신설 협의·실행 | 더존 계정과목 업데이트 확인 | 재무담당 + scm실장 | 2h (더존 설정) + 1h (세무사 협의) | 없음 |
| WP-AX1b | AI 관련 기존 지출 소급 분류 (과거 3개월) | 더존 전표 수정 내역 | 재무담당 | 3h | WP-AX1 완료 후 |
| WP-AX2 | Airtable 처리건수 4주 Baseline 쿼리 자동화 | 주간 처리건수 집계 스크립트 | Claude Code | 2h (스크립트 작성) | 없음 |
| WP-AX2b | Baseline 확정 보고 | KR-1 Baseline 수치 문서 | 파트장 | 0.5h | WP-AX2 4주 수집 후 |
| WP-AX3 | R&R 재정의 워크숍 | R&R 문서 (파트장/파트원/현장 역할 명시) | 파트장 + scm실장 | 2h | WP-AX1 완료 후 |
| WP-AX4 | 현장 인원 Airtable 업무 표준 재정비 | SOP 문서 + 교육 1회 | 파트장 | 4h | WP-AX3 완료 후 |
| WP-DX1 | KPI-3 Dashboard 구현 | `build-dashboard` 미션 산출물 | Claude Code | 4h (미션) | WP-AX2 Baseline 확보 후 (또는 Proxy로 먼저 구현) |
| WP-DX2 | TMS AutoResearch Iter2 (차량이용률 버그 + 자동화) | 수정된 AutoResearch 스크립트 + 스케줄 | Claude Code | 4h (미션) | 없음 (독립 가능) |
| WP-DX3 | SAP 이동유형 마스터 구축 | Airtable WMS 이동유형 마스터 테이블 | Claude Code | 4h (미션) | 없음 (독립 가능) |
| WP-DX4 | 더존 API/내보내기 경로 확인 | 가용성 조사 보고서 | scm실장 + 재무담당 | 1h | WP-AX1 완료 후 |
| WP-DX4b | 더존 KPI-1/2 파이프라인 구현 | 월별 자동 추출 스크립트 | Claude Code | 8h (미션) | WP-DX4 (API 가용 확인) |

---

## 3. RACI 매트릭스

> R=Responsible(실행) / A=Accountable(책임) / C=Consulted(자문) / I=Informed(통보)

| Work Package | 사용자(scm실장·파트장) | Claude Code | 도메인 에이전트 | 재무담당 |
|-------------|-------------------|-------------|--------------|--------|
| WP-AX1 더존 계정분리 | R·A | I | tax-accounting-expert (C) | R |
| WP-AX1b 소급 분류 | A | I | tax-accounting-expert (C) | R |
| WP-AX2 Baseline 쿼리 | A | R | scm-logistics-expert (C) | I |
| WP-AX2b Baseline 확정 | R·A | C | — | I |
| WP-AX3 R&R 재정의 | R·A | C | consulting-pm-expert (C) | I |
| WP-AX4 현장 온보딩 | R·A | I | — | I |
| WP-DX1 Dashboard | A | R | design-worker / tms-otif-kpi (C) | I |
| WP-DX2 AutoResearch Iter2 | A | R | tms-otif-kpi (C) | I |
| WP-DX3 SAP 이동유형 | A | R | wms-master-data (C) | I |
| WP-DX4 더존 가용성 조사 | R·A | I | tax-accounting-expert (C) | R |
| WP-DX4b 파이프라인 구현 | A | R | tax-accounting-expert (C) | C |

---

## 4. Sprint 4 Contract 자가검증

| 조건 | 결과 | 근거 |
|------|------|------|
| S4.C1: OKR Objective가 회의 의사결정 4개 종합 반영 | ✅ PASS | §1 Objective 하단 D-01~D-04 traceability 명시 |
| S4.C2: Key Results 측정 가능 (정량 + 시점) | ✅ PASS | KR 1-4 모두 측정 지표·달성 시점·Owner 정의. KR-1 baseline TBD는 이유 명시 |
| S4.C3: WBS 모든 leaf에 owner + 추정시간 | ✅ PASS | §2.2 WP 11개 전체 Owner·추정시간 정의 |
| S4.C4: 구현 미션 후보 priority + dependency 명시 | ✅ PASS | §2.2 "선행 의존성" 열 + implementation-mission-backlog.md priority |
| S4.C5: 미션 templates는 존재하는 4개만 참조 | ✅ PASS | build-dashboard / build-pipeline 만 사용 |
| S4.N1: 측정 불가 KR 없음 | ✅ 위반 없음 | KR 1-4 모두 정량 지표 + 측정 방법 명시 |
| S4.N2: strategy-design 재귀 호출 없음 | ✅ 위반 없음 | 미션 후보 4개 모두 build-* 계열 |
| S4.N3: owner 미정의 Work Package 없음 | ✅ 위반 없음 | WP 11개 전체 Owner 열 채움 |

---

*원본 출처:*  
*[1] 회의 의사결정 D-01~D-04 (log.md 2026-05-15)*  
*[2] Sprint 3 AX/DX 범위 (2026-05-15-scm-axdx-scope.md)*  
*[3] Sprint 2 KPI 트리 (2026-05-15-scm-financial-kpi.md)*  
*[4] 사용자 확인 FTE=7명 (2026-05-15 직접 입력)*  
*[5] CLAUDE.md: build-pipeline/build-dashboard/build-api/strategy-design 템플릿 4개*
