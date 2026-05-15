# SCM 구현 미션 Backlog (Sprint 4 산출)

**미션 ID**: strategy-design-20260515-1607-scm-team-realignment  
**산출일**: 2026-05-15  
**기준**: Sprint 3 AX/DX 범위 확정 + Sprint 4 WBS Work Package 연계

---

## 즉시 착수 가능 미션 (P1)

### M-01: KPI-3 생산성 Proxy Dashboard

```
/mission build-dashboard --duration 4h --project scm-kpi-dashboard
```

| 항목 | 내용 |
|------|------|
| **목적** | Airtable WMS/TMS → 물류팀 7명 처리건수 KPI-3 자동 시각화 |
| **산출물** | 대시보드 (파트별 처리건수/FTE, 월별 추세, OTIF 연동) |
| **연계 WP** | WP-DX1 |
| **선행 조건** | 없음 (AX-2 Baseline 수집과 병렬 가능. Proxy로 먼저 구현 후 Baseline 확정 시 수치 업데이트) |
| **의존 미션** | 없음 |
| **KR 연결** | KR-1 (처리건수/FTE), KR-4 (Dashboard 운영) |
| **예상 착수** | 2026-05-22 (이번 미션 종료 후 즉시) |
| **리스크** | 현장 인원이 Airtable 입력을 정확히 해야 데이터 신뢰 → AX-4 온보딩과 병행 |

**주요 Sprint 내용 (4h)**:
- Sprint 1 (1h): Airtable WMS/TMS 처리건수 집계 쿼리 설계
- Sprint 2 (1h): React 대시보드 구성 (파트별 건수, FTE=7, 월별 차트)
- Sprint 3 (1h): OTIF + 처리건수 복합 뷰 + KPI 목표 대비 현황
- Sprint 4 (1h): Vercel 배포 + 주간 자동 갱신

---

### M-02: TMS AutoResearch Iter 2

```
/mission build-pipeline --duration 4h --project tms-autoResearch-iter2
```

| 항목 | 내용 |
|------|------|
| **목적** | 차량이용률 버그 수정(현재 19.4% 저평가 이슈) + 주간 자동 실행 스케줄 |
| **산출물** | 수정된 AutoResearch 스크립트 + GitHub Actions 주간 스케줄 |
| **연계 WP** | WP-DX2 |
| **선행 조건** | 없음 (독립 착수 가능) |
| **의존 미션** | 없음 |
| **KR 연결** | KR-2 (주간 보고 완전 자동화, 수동 실행 0회/주) |
| **예상 착수** | 2026-05-22 (M-01과 병렬 가능) |
| **리스크** | 차량이용률 버그 수정 후 실제 수치가 더 낮을 수 있음 → 데이터 해석 주의 |

**주요 Sprint 내용 (4h)**:
- Sprint 1 (1h): 차량이용률 계산 로직 버그 진단 + 수정
- Sprint 2 (1h): OTIF 재계산 (수정된 기준 적용)
- Sprint 3 (1h): GitHub Actions 주간 스케줄 설정
- Sprint 4 (1h): 리포트 포맷 개선 + Slack/이메일 자동 발송

---

## 조건부 착수 미션 (P2)

### M-03: W-NEW-01 SAP 이동유형 마스터

```
/mission build-pipeline --duration 4h --project wms-sap-movement-master
```

| 항목 | 내용 |
|------|------|
| **목적** | Airtable WMS에 SAP 이동유형 코드 마스터 구축 (재고 정합성 추적) |
| **산출물** | WMS 이동유형 마스터 테이블 + 기존 movement 데이터 백필 |
| **연계 WP** | WP-DX3 |
| **선행 조건** | 없음 (독립 착수 가능) |
| **의존 미션** | 없음. M-01 Dashboard와 독립 |
| **KR 연결** | KR-1 (처리건수 분류 정확도 향상 → Dashboard 데이터 품질) |
| **예상 착수** | 2026-Q3 (M-01, M-02 완료 후) |
| **우선순위 근거** | AS-IS 진단에서 이동유형 추적 부재가 재고 정합성 갭으로 확인. M-01/M-02보다 덜 긴급 |
| **리스크** | 기존 movement 레코드 Immutable Ledger 원칙 — 백필은 보정 레코드로만 처리 |

**SAP 이동유형 코드 기준**:
- 101 입고 / 201 출고 / 261 생산출고 / 311 이전 / 601 납품 / 701 조정 / 122 반품입고 / 551 폐기

---

### M-04: 더존 KPI-1/2 추출 파이프라인 (조건부)

```
/mission build-pipeline --duration 8h --project douzone-kpi-pipeline
```

| 항목 | 내용 |
|------|------|
| **목적** | 더존 아마란스10 → 인건비율(KPI-1) + 수수료 계정(KPI-2) 월별 자동 추출 |
| **산출물** | 더존 데이터 추출 스크립트 + KPI-1/2 자동 계산 파이프라인 |
| **연계 WP** | WP-DX4, WP-DX4b |
| **선행 조건** | ⚠️ **WP-DX4 더존 API/내보내기 경로 확인 필수** — API 없으면 착수 불가 |
| **의존 미션** | WP-AX1 (계정 분리 완료) 필수 |
| **KR 연결** | KR-3 (AI 비용 추적) + KR-1 보완 (인건비율 정확한 baseline) |
| **예상 착수** | 2026-Q3 이후 (WP-DX4 조사 결과에 따라) |
| **리스크** | 더존 API 미지원 시 월 1회 수동 엑셀 추출 프로세스로 대체. 8h 미션 불필요 |

---

## 미션 실행 순서 및 의존성 요약

```
즉시 (2026-05 말)
  M-01 build-dashboard 4h  ──────┐ 병렬 가능
  M-02 build-pipeline 4h   ──────┘

Q3 (2026-07~09)
  AX-1 더존 계정분리 완료 확인
  AX-2 Baseline 4주 수집 완료 → KR-1 Baseline 수치 확정
  M-03 build-pipeline 4h (SAP 이동유형)

Q3 후반 (조건부)
  WP-DX4 더존 API 가용성 확인
  └→ 가능: M-04 build-pipeline 8h
  └→ 불가: 수동 추출 SOP 작성 (미션 불필요)

Q4 (2026-10~12)
  KR-1/2/3/4 달성 현황 점검 → 미달성 항목 추가 스프린트
```

---

## 비-미션 AX 작업 (사용자 직접 실행)

이 항목들은 `/mission` 없이 사용자가 직접 수행:

| 작업 | 담당 | 예상 시간 | 완료 기준 |
|------|------|--------|---------|
| 더존 AI비용 계정 분리 (WP-AX1) | 재무담당 + 세무사 | 5h | 더존 계정과목 업데이트 완료 |
| 현재 AI 지출 소급 분류 (WP-AX1b) | 재무담당 | 3h | 과거 3개월 전표 정리 |
| R&R 재정의 워크숍 (WP-AX3) | 파트장 + scm실장 | 2h | R&R 문서 완성 |
| 현장 인원 온보딩 (WP-AX4) | 파트장 | 4h | 5명 현장 교육 완료 |

---

*원본 출처:*  
*[1] Sprint 3 AX/DX 범위 (2026-05-15-scm-axdx-scope.md)*  
*[2] Sprint 4 WBS (2026-05-15-scm-okr-wbs.md §2.2)*  
*[3] CLAUDE.md: 허용 미션 템플릿 4개 (build-pipeline/build-dashboard/build-api/strategy-design)*  
*[4] CLAUDE.md SCM: Immutable Ledger 원칙 (백필=보정 레코드)*
