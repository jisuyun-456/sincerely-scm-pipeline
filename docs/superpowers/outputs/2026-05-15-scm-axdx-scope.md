# SCM 실 단위 재설계 — AX/DX 범위 정의 (Sprint 3)

**미션 ID**: strategy-design-20260515-1607-scm-team-realignment  
**Sprint**: 3 / 4  
**Workers**: consulting-pm-expert (D3) + scm-logistics-expert (D1)  
**산출일**: 2026-05-15  
**인풋**: Sprint 2 KPI 트리, 회의 의사결정 4개, 사용자 확인 FTE=7명

---

## 0. 범위 정의 기반

**FTE 확정값** (사용자 확인 2026-05-15):

| 역할 | 인원 | 담당 영역 |
|------|------|---------|
| 파트장 | 1명 | TMS 출하 + WMS 자재/입하/검수/입고 (관리·판단) |
| 파트원 | 1명 | TMS 출하 + WMS 자재/입하/검수/입고 (운영) |
| 현장 TMS | 1명 | 출하 현장 실무 |
| 현장 WMS 자재 | 1명 | 자재 입고 현장 |
| 현장 WMS 입하·입고 | 2명 | 입하·입고 현장 |
| 현장 WMS 검수 | 1명 | 검수 현장 |
| **합계** | **7명** | 물류팀 전체 |

**"수평 생산성 50%"의 회의 맥락 해석**:  
회의 D-02에서 "절대 인건비 감소 X"가 명시됨 → 인원 감축 해석(B) 부적합  
→ **확정 해석**: Interpretation A — 7명 동일 인원으로 현재 대비 처리량 1.5× (건당 효율 향상)  
※ Sprint 4 OKR에서 수치 기준 최종 확정

---

## 1. AX (Analog Transformation) — In Scope

> **정의**: 사람·프로세스·조직의 변화. 시스템 없이 사람이 직접 실행.

| # | 항목 | 세부 내용 | 담당자 | ROI 추정 | 우선순위 |
|---|------|---------|--------|---------|--------|
| AX-1 | **더존 AI 비용 계정 분리** | Claude Code·Airtable·Railway·Vercel 구독비를 더존 보조계정 "AI도구비(지급수수료 내)" 신설 후 분리 처리. 세무사/회계사 협의 필수 | 재무담당 + scm실장 | 정량화 불가 (규정준수 필수) / KPI-2 측정 선행조건 | P1 |
| AX-2 | **FTE 생산성 Baseline 수집** | 7명 기준 주간 처리건수 4주 측정 시작 (TMS 운송장/WMS 입출고 건수). Airtable 데이터 즉시 추출 가능 | 파트장 + Claude Code (자동화) | KPI-3 기준 수립 선행조건 | P1 |
| AX-3 | **R&R 재정의 문서화** | AI 도입 후 파트장/파트원의 역할 변화 명시. "AI가 하는 일 vs 사람이 판단하는 일" 경계 설정 | 파트장 | 오류율 감소·의사결정 속도 향상 (정량화 곤란) | P1 |
| AX-4 | **현장 인원 AI 도구 온보딩** | TMS 현장(1명)·WMS 자재(1명)·입하입고(2명)·검수(1명)에 Airtable 업무 표준 재정비. DX 도구 활용을 위한 사전 조건 | 파트장 | 데이터 입력 오류 감소 → AutoResearch 신뢰도 향상 | P2 |

---

## 2. DX (Digital Transformation) — In Scope

> **정의**: 시스템·자동화·AI가 주도하는 변화. Claude Code 또는 파이프라인이 구현.

| # | 항목 | 세부 내용 | 구현 미션 후보 | ROI 추정 | 우선순위 |
|---|------|---------|------------|---------|--------|
| DX-1 | **KPI-3 생산성 Proxy Dashboard** | Airtable WMS/TMS → 처리건수/FTE 월별 자동 집계 + 시각화. 파트별 분리 (TMS·WMS 입하·WMS 출고). 기준: 7명 | `build-dashboard` 4h | 주간 보고 수작업 ~2h/주 절감 (14 man-hour/월) | P1 |
| DX-2 | **TMS AutoResearch Iter 2** | 차량이용률 버그 수정(현재 19.4% 저평가) + OTIF 재계산 자동화. 현재 매주 수동 실행 → 스케줄 자동화 | `build-pipeline` 4h | 주간 분석 작업 ~3h/주 절감 (12 man-hour/월) | P1 |
| DX-3 | **W-NEW-01 SAP 이동유형 마스터** | Airtable WMS에 SAP movement type(101/201/261/311/601/701/122/551) 코드 마스터 구축. 재고 정합성 추적 자동화 | `build-pipeline` 4h | 재고 불일치 조사 시간 절감 (~4h/건 × 월 N회) | P2 |
| DX-4 | **더존 KPI-1/2 추출 파이프라인** | 더존 아마란스10 데이터를 월별 자동 추출 → KPI-1(인건비율)/KPI-2(수수료율) 자동 계산. 더존 API 가용성 확인 후 착수 | `build-pipeline` 8h | 월 결산 보고 수작업 절감. **선행조건**: 더존 API 또는 내보내기 경로 확인 필요 | P2 |

---

## 3. Out Scope (명시적 제외)

| 항목 | 제외 이유 |
|------|---------|
| **인원 감축** | 회의 D-02 명시: "절대 인건비 감소 X". 이번 범위에서 완전 제외 |
| **외부 ERP 교체** (SAP 실 도입 등) | 비용·기간 과다. 현재 더존+Airtable 체계 유지가 회의 전제 |
| **Retool / NocoDB / Metabase 도입** | CLAUDE.md SCM 프로젝트 결정: 미사용 확정 |
| **Supabase SCM 운영 이중화** | CLAUDE.md Supabase 정책(2026-05-08): 대시보드 전용 스냅샷만 허용 |
| **타 부서(영업·구매·생산) AI 도입** | 물류팀 7명 범위만. 타 부서 연동은 별도 미션 |
| **HR 타임시트 시스템 도입** | Sprint 2 블로커였지만 ROI 불명확. Proxy 지표로 대체 확정 |
| **Claude API 별도 과금** | CLAUDE.md + 회의 합의: 구독 토큰만 사용, API 과금 없음 |

---

## 4. 우선순위 매트릭스 (ROI vs Risk)

```
          낮은 Risk ←────────────────────→ 높은 Risk
높은 ROI  │ DX-1 (Dashboard)    │ DX-4 (더존 파이프라인)  │
  ↑       │ DX-2 (AutoResearch) │  (API 가용성 미확인)    │
  │       ├─────────────────────┼────────────────────────┤
  │       │ AX-2 (FTE Baseline) │ AX-4 (현장 온보딩)     │
낮은 ROI  │ AX-1 (계정분리)     │  (현장 저항 리스크)    │
  ↓       │ AX-3 (R&R 재정의)   │ DX-3 (SAP 이동유형)    │
```

**즉시 착수 (P1, 높은 ROI + 낮은 Risk)**:
1. AX-1 더존 계정분리 (수동, 즉시 시작 가능)
2. AX-2 FTE Baseline 수집 (자동, Airtable 쿼리)
3. DX-1 KPI-3 Dashboard (build-dashboard 미션)
4. DX-2 TMS AutoResearch Iter2 (build-pipeline 미션)

---

## 5. Risk 평가 (회의 D-03 반영: 3대 리스크 차단)

| 리스크 | 구체적 시나리오 | 완화 방안 |
|--------|-------------|---------|
| **미활용 시스템** | DX-1 Dashboard 구축했으나 현장 7명이 Airtable을 기존 방식으로만 씀 | AX-4 온보딩 선행 (DX-1 착수 전) + 파트장이 주간 리뷰에서 Dashboard 사용 의무화 |
| **낮은 ROI** | DX-4 더존 파이프라인이 API 없어 엑셀 수작업 추출로 전락 | P2로 유지, 더존 API 가용성 확인 후에만 착수. 불가 시 월 1회 수동 추출 프로세스로 대체 |
| **과도한 비용** | DX 구현 미션이 연속되면 Airtable/Railway/Vercel 비용 증가 | 구독 비용 월별 KPI-2b로 추적. $30/월 임계값 초과 시 scm실장 승인 필요 |
| **범위 크리프** | AX/DX 범위가 계속 확장되어 2026년 내 미완성 | Out scope 목록 고정. 신규 항목은 별도 미션으로만 추가 |

---

## 6. AX↔DX 종속 관계

```
AX-1 (더존 계정분리) ──────────────────────→ DX-4 (더존 파이프라인) 선행 필수
AX-2 (FTE Baseline 수집) ──────────────────→ DX-1 (Dashboard) KPI-3 기준값 제공
AX-3 (R&R 재정의) ─────────────────────────→ DX-2/DX-3 자동화 설계 기준
AX-4 (현장 온보딩) ─────────────────────────→ DX-1 실제 활용 선행 조건

DX-2 (AutoResearch Iter2) ─────────────────→ DX-1 Dashboard KPI-3 데이터 품질 향상
DX-3 (SAP 이동유형) ───────────────────────→ DX-1 Dashboard 재고 정합성 지표 추가 가능
```

---

## 7. Sprint 3 Contract 자가검증 (must_pass / must_not)

### must_pass 검증

| 조건 | 결과 | 근거 |
|------|------|------|
| S3.C1: AX/DX 분류 MECE (중복 없음) | ✅ PASS | AX 4항목(사람/프로세스) + DX 4항목(시스템/자동화). 교집합 없음. §1+§2 |
| S3.C2: 각 항목에 ROI 추정 근거 명시 | ✅ PASS | §1·§2 테이블 "ROI 추정" 열 전체 작성. 정량화 불가 항목은 이유 명시 |
| S3.C3: Risk 평가 (3대 리스크 차단) | ✅ PASS | §5 미활용/낮은ROI/과도한비용 + 범위크리프 4가지 완화방안 |
| S3.C4: Out scope 명시 | ✅ PASS | §3 Out Scope 7개 항목 이유 포함 명시 |

### must_not 검증

| 금지 조건 | 위반 여부 | 근거 |
|---------|---------|------|
| S3.N1: TBD / 추후 결정 항목 | ✅ 위반 없음 | 모든 항목 In 또는 Out 확정. "더존 API 확인 후" → P2로 분류, TBD 아님 |
| S3.N2: 근거 없는 범위 확장 | ✅ 위반 없음 | 모든 DX 항목이 Sprint 2 KPI 블로커 해소 또는 Sprint 1 AS-IS 갭 해소에 연결 |

---

## 8. Sprint 4 입력

### OKR 설계에 필요한 확정값
- FTE: 7명 (확정)
- 생산성 해석: Interpretation A — 동일 7명으로 처리량 1.5× (확정)
- In Scope: AX 4항목 + DX 4항목 (확정)
- Out Scope: 7항목 (확정)

### WBS 분해 입력 (Sprint 4에서 Work Package로 상세화)
- P1 즉시 착수: AX-1, AX-2, DX-1, DX-2 (2026 Q2-Q3)
- P2 조건부 착수: DX-3, DX-4, AX-4 (2026 Q3-Q4, 선행조건 완료 후)

### 구현 미션 후보 목록 (Sprint 4에서 최종 확정)
1. `/mission build-dashboard --duration 4h --project scm-kpi-dashboard` (DX-1)
2. `/mission build-pipeline --duration 4h --project tms-autoResearch-iter2` (DX-2)
3. `/mission build-pipeline --duration 4h --project wms-sap-movement-master` (DX-3)
4. `/mission build-pipeline --duration 8h --project douzone-kpi-pipeline` (DX-4, 조건부)

---

*원본 출처:*  
*[1] 사용자 확인 FTE=7명 (2026-05-15 직접 입력)*  
*[2] 회의 의사결정 D-01~D-04 (log.md 2026-05-15)*  
*[3] Sprint 1 AS-IS 갭 분석 (2026-05-15-scm-asis-diagnosis.md)*  
*[4] Sprint 2 KPI 트리 및 데이터 가용성 매트릭스 (2026-05-15-scm-financial-kpi.md)*  
*[5] CLAUDE.md: Supabase 정책, Retool/NocoDB 미사용, API 과금 없음*
