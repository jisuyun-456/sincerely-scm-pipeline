# SCM 실 단위 재설계 — Sprint 1: AS-IS 진단 + 회의 의사결정 합성

**Mission:** strategy-design-20260515-1607-scm-team-realignment
**Sprint:** 1 / 4 (AS-IS 진단)
**작성일:** 2026-05-15
**작성:** harness-orchestrator (consulting-pm-expert D3 + scm-logistics-expert D1 lens)
**범위:** Sprint 1만 — KPI 트리(Sprint 2) · AX/DX 매트릭스(Sprint 3) · OKR/WBS(Sprint 4) 포함 금지

---

## 회의 의사결정 4개 (원본 인용)

출처: `C:/Users/yjisu/Documents/ClaudeVault/SCM/_AutoResearch/wiki/log.md` line 1793-1801 (원문 verbatim)

> **[공통] 재무 구조 연계 KPI 수립 및 AX/DX 범위 정의**
>
> - **결정:** 재무 지표 기반 통일 목표 → AX/DX Scope 사전 확정 → 추진
> - **핵심 관리 지표:**
>   - 인건비 절감 자체보다 **매출액 대비 인건비 비율** 감소
>   - AI 전환을 통한 **수수료 계정** 활용도 향상
> - **2026 목표:** 수평 생산성 50% 향상
> - **리스크 차단 포인트:** 범위·성공 기준 모호 시 → 미활용 시스템 구축 / 낮은 ROI / 과도한 비용

회의 결정은 위 4개로 식별한다 (이하 D-1 ~ D-4).

| 코드 | 결정 / 지표 | 출처 |
|------|------------|------|
| **D-1** | 매출액 대비 **인건비 비율** 감소 (인건비 절감 자체 아님) | log.md 1798 |
| **D-2** | AI 전환을 통한 **수수료 계정** 활용도 향상 | log.md 1799 |
| **D-3** | 2026 목표 — **수평 생산성 50% 향상** | log.md 1800 |
| **D-4** | **범위·성공 기준 모호 시 리스크 차단** — 미활용 시스템 / 낮은 ROI / 과도한 비용 3가지 차단 포인트 | log.md 1801 |

본 문서 이하 분석은 위 4개 결정을 *임의 변경·확장하지 않는다* (must_not S1.N1, MN3).

---

## Pyramid (SCQA) Synthesis

Barbara Minto의 Pyramid Principle 적용 — Situation / Complication / Question / Answer 구조로 4개 결정을 1-page 합성.

### Situation (현재 상황)

지난 1~2분기 동안 Claude Code 기반 프로젝트들 — SAP 시뮬레이션, TMS AutoResearch, Universal Project Harness, paper-trading 연동 — 은 **개인 주도로** 진행되어 SCM 실 공동 목표와의 명시적 연결 고리가 약했다 (log.md 1790). 동시에 SCM 실은 Airtable WMS+TMS를 단일 진실 원천(SSOT)으로 운영하면서, AI/자동화 도입의 ROI를 재무 지표로 환산해 보고할 압력이 누적된 상태이다.

### Complication (어려움 / 변화 압력)

- 인건비 절감을 일차 KPI로 잡으면 매출 성장이 동반될 때 신호가 왜곡된다 — 단위는 같아도 *비율*이 의사결정에 맞는 지표이다 (D-1).
- AI 도입 비용이 회계상 어디로 흘러가는지 (수수료 계정 vs 인건비 vs 별도 계정) 가시화되지 않으면 ROI 측정 자체가 불가능하다 (D-2).
- "수평 생산성 50% 향상"이라는 정량 목표(D-3)는 baseline·측정 방식 없이는 사후 검증 불가하다.
- 회의 합의된 3대 리스크 — 미활용 시스템 / 낮은 ROI / 과도한 비용 — 은 *범위 모호*가 공통 원인이다 (D-4).

### Question (이번 미션이 답해야 할 질문)

> SCM 실의 모든 AI/자동화 활동을, **재무 지표에 직결된 통일 KPI** 위에 정렬하고, **AX/DX 범위를 사전 확정**해 리스크 3개(미활용/낮은ROI/과비용)를 구조적으로 차단할 방법은 무엇인가?

### Answer (Pyramid Top — Governing Thought)

> SCM 실은 4개 회의 결정을 **단일 OKR 트리**로 묶고, 그 아래 **AX(프로세스·R&R·의사결정)** 와 **DX(시스템·자동화·AI)** 를 MECE로 분할한 다음, 각 항목에 baseline·목표·측정 주기·owner를 부착해야 한다.

이 governing thought는 4개 결정을 다음과 같이 종속시킨다:

```
[Top] SCM 실 통일 OKR — 재무 KPI + AX/DX 범위 사전 확정
        ├── D-1: 매출액 대비 인건비 비율 (재무 측정 축 — "Y축")
        ├── D-2: 수수료 계정 활용도 (AI 비용 가시화 — "비용 흐름 추적")
        ├── D-3: 수평 생산성 50% (운영 측정 축 — "X축, 시점 목표")
        └── D-4: 범위·성공 기준 차단 (가드레일 — Scope·ROI·Cost 3리스크)
```

D-1과 D-3은 *측정 축* (재무 / 운영), D-2는 *비용 흐름 가시화*, D-4는 *집행 가드레일*. 4개가 직교(MECE)하며 같이 갖춰져야 미션이 작동한다 — 1개라도 빠지면 "측정 가능 가설이지만 ROI 추적 불가" 또는 "ROI 추적 가능하지만 범위가 모호" 식의 부분 실패가 발생한다.

---

## Issue Tree (MECE 검증 포함)

4개 결정(D-1 ~ D-4)을 root로 두고 sub-issue를 MECE 원칙으로 분해. 본 트리는 Sprint 2~4가 풀어야 할 *문제 공간*만 정의 — *해답*은 후속 Sprint에서 작성 (S1.N3 준수).

### D-1: 매출액 대비 인건비 비율 감소

```
D-1 매출액 대비 인건비 비율 ↓
├── L1-A. 분자(인건비) 측면
│   ├── L2-a1. 직접 인건비 (정규직 급여)
│   ├── L2-a2. 간접 인건비 (외주·파트너 비용)
│   └── L2-a3. AI 대체 인건비 (자동화로 절감된 인건비 환산)
├── L1-B. 분모(매출) 측면
│   ├── L2-b1. 매출 성장 (영업 기여)
│   └── L2-b2. SCM 실 활동의 매출 기여도 측정 가능성 (현재: 직접 측정 어려움)
└── L1-C. 비율 측정 인프라
    ├── L2-c1. 재무 데이터 접근권 (더존 아마란스10 — K-IFRS 1xxx~5xxx 계정코드)
    ├── L2-c2. SCM 실 인력 비용 분리 가능성 (계정 분할)
    └── L2-c3. 측정 주기 (월/분기/연)
```

### D-2: 수수료 계정 활용도 향상 (AI 전환 비용 가시화)

```
D-2 수수료 계정 활용도 ↑
├── L1-A. AI/자동화 비용을 수수료 계정으로 인식 (분류)
│   ├── L2-a1. 현재 계정 분류 — 어디로 비용이 흘러가는가? (조사 필요)
│   ├── L2-a2. 더존 아마란스10에서 "수수료" 매핑 가능한 계정코드 (예: 837 운반비, 814 통신비, 등 — Sprint 2에서 확정)
│   └── L2-a3. 인건비→수수료 이전 시 회계상 영향 (K-IFRS 비용 분류)
├── L1-B. 활용도 측정
│   ├── L2-b1. 수수료 계정 절대값 (KRW)
│   ├── L2-b2. 수수료 계정 비중 (총 비용 대비 %)
│   └── L2-b3. 인건비→수수료 이전 추적 (시계열)
└── L1-C. AI 도입 사업당 비용 추적 (단위 산출당)
    ├── L2-c1. Claude 구독 비용 (paper-trading 메모: $0 — 구독토큰)
    ├── L2-c2. Anthropic API 비용 (build-pipeline 등 미션 토큰)
    └── L2-c3. 외부 SaaS (Airtable PAT, Slack, GitHub Actions, fly.io, Vercel, Supabase free)
```

### D-3: 수평 생산성 50% 향상 (2026 목표)

```
D-3 수평 생산성 50% ↑
├── L1-A. "수평 생산성" 정의 (정의 필요 — Sprint 2 input)
│   ├── L2-a1. 단위 처리량 / 시간 (예: WMS 출고 라인 수 / 시간)
│   ├── L2-a2. 단위 처리량 / 인력 FTE
│   └── L2-a3. 단위 처리량 / KRW 인건비 (= D-1과 종속)
├── L1-B. Baseline 측정
│   ├── L2-b1. 현재 처리량 (Airtable movement, shipment 기준)
│   ├── L2-b2. 측정 기간 (어느 시점부터 baseline?)
│   └── L2-b3. 데이터 가용성 (월별 집계 가능 여부)
└── L1-C. 50% 달성 경로
    ├── L2-c1. 자동화 wins (자동화로 단위 시간 단축)
    ├── L2-c2. AI 보조 (검수·이상탐지로 재작업 감소)
    └── L2-c3. 프로세스 표준화 (AX) — 표준 없이는 자동화 효과 측정 불가
```

### D-4: 범위·성공 기준 모호 차단 (가드레일)

```
D-4 범위 모호 → 3대 리스크 차단
├── L1-A. 미활용 시스템 차단
│   ├── L2-a1. 구축 전 사용 시나리오 확정 (use case)
│   ├── L2-a2. 사용자 명시 (누가 매일·주간·월간 사용)
│   └── L2-a3. 비사용 시 sunset 기준 (예: 3개월 미사용 → 폐기)
├── L1-B. 낮은 ROI 차단
│   ├── L2-b1. ROI 추정 (Sprint 3 매트릭스)
│   ├── L2-b2. ROI 측정 (Sprint 2 KPI tree와 연결)
│   └── L2-b3. ROI 추적 주기
└── L1-C. 과도한 비용 차단
    ├── L2-c1. 사전 비용 추정 (token / SaaS / 인력 시간)
    ├── L2-c2. 비용 모니터링 (cost_guardrail — 본 미션은 $30 hard stop)
    └── L2-c3. 비용 vs 가치 손익분기 (break-even)
```

### MECE 자가 검증 (필수 섹션)

**Mutually Exclusive (상호 배타) — overlap 검사:**

각 L1 노드(D-1A/B/C, D-2A/B/C, D-3A/B/C, D-4A/B/C — 총 12개)를 cross-product로 비교했다.

| 잠재 중복 후보 | 판정 | 근거 |
|--------------|------|------|
| D-1.L1-A.L2-a3 (AI 대체 인건비) ↔ D-2.L1-A (AI 비용 수수료 분류) | **분리** | D-1은 "절감된 인건비 환산값", D-2는 "지출된 AI 비용". 부호 반대, 측정 대상 다름. |
| D-1.L1-A ↔ D-3.L1-C.L2-c3 (프로세스 표준화) | **분리** | D-1은 *비율 측정*, D-3.c3은 *50% 달성 경로*. 측정 vs 수단. |
| D-3.L1-A.L2-a3 (단위/KRW 인건비) ↔ D-1 (전체) | **명시적 종속** | 트리에 명시 — "= D-1과 종속". 중복 아닌 *cross-link*. |
| D-4.L1-B (낮은 ROI) ↔ D-2/D-3 (KPI 측정) | **분리** | D-4는 *가드레일* (해당 시 차단/중단 trigger), D-2/D-3은 *측정 트리*. 다른 레이어. |

→ **Overlap = 0** 확인.

**Collectively Exhaustive (전부 포함) — gap 검사:**

| 회의 결정 항목 (log.md 1793-1801) | 트리 노드 매핑 | 누락? |
|--------------------------------|--------------|------|
| "재무 지표 기반 통일 목표" (1796) | D-1.L1-C (재무 데이터 접근권) + Top-level governing thought | 포함 |
| "AX/DX Scope 사전 확정" (1796) | Sprint 3 산출물에서 — D-1~D-4 모두가 AX/DX로 분할될 후보 | 포함 (Sprint 3 input) |
| "매출액 대비 인건비 비율 감소" (1798) | D-1 (전체) | 포함 |
| "AI 전환을 통한 수수료 계정 활용도 향상" (1799) | D-2 (전체) | 포함 |
| "수평 생산성 50% 향상" (1800) | D-3 (전체) | 포함 |
| "범위·성공 기준 모호" (1801) | D-4.L1-A 미활용, L1-B 낮은 ROI, L1-C 과비용 | 포함 (3개 리스크 모두) |

→ **Gap = 0** 확인.

**MECE 검증 결과 요약: overlap=0, gap=0**

---

## AS-IS — 현재 SCM 실 운영 활동

기준 시점: 2026-05-15. 출처: `c:/Users/yjisu/Desktop/SCM_WORK/CLAUDE.md` (기술 스택 표), `project_scm_redesign.md`, `project_tms_gap_completed.md`. **현재 운영 중인 활동만 기재 — 가설·미래 계획은 별도 marked 섹션 외 사용 금지 (S1.C3)**.

### A. 운영 데이터 레이어 (Airtable SSOT)

| 시스템 | 베이스 ID | 역할 | 운영 상태 |
|-------|---------|------|---------|
| WMS Airtable | appLui4ZR5HWcQRri | 입하·재고·출고 운영 입력 (movement INSERT ONLY) | 운영 중 |
| TMS Airtable | app4x70a8mOrIKsMf | 운송·OTIF·정산 (17테이블, 백필 796건 완료) | 운영 중 (project_tms_gap_completed.md) |
| Barcode Airtable | app4LvuNIDiqTmhnv | 피킹리스트·출고확인서·바코드 | 운영 중 (project_meeting_participants.md 인근 메모) |

**원칙 (변경 금지):** Airtable이 단일 진실 원천. 운영 데이터(movement/inventory) Supabase 이중화 금지. NocoDB/Metabase/Retool 미사용 확정 (`project_scm_redesign.md` line 13-15).

### B. 백엔드·자동화 레이어

| 컴포넌트 | 위치 | 역할 | 운영 상태 |
|---------|------|------|---------|
| FastAPI on Railway | `api/app.py` | PDF 생성 등 일부 자동화 | 운영 중 |
| GitHub Actions cron | repo workflows | 파이프라인 스케줄 | 운영 중 |
| fly.io PDF 서버 | secrets 분리 | PDF 생성 (256MB+auto_stop, ~$0/월) | 운영 중 (memory `project_flyio_config`) |
| PostToolUse 훅 | Claude 훅 | 회의록 → Obsidian Vault + Slack 공유폴더 백업 | 운영 중 |
| Stop 훅 | Claude 훅 | 세션 종료 시 git status / 미커밋 경고 | 운영 중 |

### C. 분석·리포팅 레이어

| 산출물 | 위치 | 빈도 | 운영 상태 |
|-------|------|------|---------|
| TMS AutoResearch | `ClaudeVault/SCM/_AutoResearch/` + outputs | 비정기 (첫 분석 완료 — 차량이용률 19.4%, OTIF 100% — 다음 Iter2 대기) | 운영 중 (memory `project_tms_autoResearch`) |
| 주간 운영 회의 분석 | meeting-analysis (SK-08) | 주간 | 운영 중 |
| 출고확인서 / Packing List | 자동 생성 | 출하 단위 | 운영 중 (최근 commits 0787976, 2dcf77d, c4a0f52) |

### D. 별도 서브프로젝트

| 프로젝트 | 레포 | 스택 | 운영 상태 |
|---------|------|------|---------|
| sincerely-scm-dashboard | 별도 레포 | React on Vercel + Supabase + GitHub Actions cron | 운영 중 (Supabase free tier — 대시보드 스냅샷만, `project_scm_redesign.md` line 13) |
| Paper Trading System | 별도 레포 | Alpaca + Claude 구독토큰 (Paperclip 6에이전트 연동 예정) | 운영 중 — 35포지션 체결 (memory `project_paper_trading`, `project_paperclip_integration`) |

### E. AI/Agent 레이어 (Claude Code)

| 활동 | 설정 위치 | 역할 | 운영 상태 |
|------|---------|------|---------|
| SCM 운영 특화 에이전트 (SK-01~09) | `.claude/agents/wms-*.md`, `tms-*.md` | 도메인 작업 위임 | 운영 중 |
| SCM 도메인 전문가 (D-TMS1/2, D1/D2/D3) | `.claude/agents/*-expert.md` | 전략·진단·설계 | 운영 중 (본 미션이 D1·D3 활용 사례) |
| Universal Project Harness | `~/.claude/harness/` + `~/.claude/agents/` (Core 9 + Specialized 5) | 미션 모드 멀티 에이전트 오케스트레이션 | 운영 중 (본 미션이 사용 중) |
| Validation Contract 시스템 | `~/.claude/harness/contracts/` | 사전 검증 조건 정의 + harness-validator | 운영 중 |

### F. 회계·정산 활동

| 활동 | 빈도 | 도구 | 운영 상태 |
|-----|------|------|---------|
| 운임 정산 (TMS) | 월 (3월 8,553,350원 / 4월 미정산) | Airtable 정산관리 (tblf0BClxZtnQfOJL) | 운영 중 (memory `project_tms_gap_completed` line 19) |
| K-IFRS / 더존 아마란스10 계정 매핑 | 정정 시 | 더존 시스템 (외부) | 운영 중 |

### G. 데이터 정합성 가드

| 가드 | 적용 범위 | 운영 상태 |
|-----|---------|---------|
| Immutable Ledger (movement·mat_document INSERT ONLY) | WMS+TMS Airtable | 운영 중 (글로벌 CLAUDE.md, 프로젝트 CLAUDE.md 양쪽 명시) |
| Storno (역분개) 정정 | 운영 데이터 모든 정정 | 운영 중 |
| scm-validator | (TMS 한정 lightweight 구현 검토 중 — log.md 1818-1822) | **미구축** — Sprint 4 미션 백로그 후보 |

---

## Gap 분석 — 결정 ↔ 현재 활동

각 회의 결정에 대해 "현재 활동 ✓" / "필요 활동 — 현재 미구축 ✗" 매핑. *Sprint 1 범위에서는 gap을 식별만* 하고, 해결책(KPI/AX/DX/OKR)은 후속 Sprint 산출.

### D-1: 매출액 대비 인건비 비율 감소

| 필요 활동 | 현재 상태 | Gap |
|---------|---------|-----|
| 매출액 데이터 정기 수집 | 현재 SCM 실 자체 보유 X (더존 외부 시스템) | ✗ — 재무 데이터 접근권 / 추출 경로 필요 |
| SCM 실 인건비 분리 (직접/간접/AI 대체) | 분리 미수행 | ✗ — 계정 분류 정의 필요 (Sprint 2) |
| 월/분기 자동 비율 계산 | 미구축 | ✗ — 산출 공식 + 데이터 파이프라인 필요 (Sprint 2 KPI 트리) |
| baseline 시점 합의 | 없음 | ✗ — 회의 결정 시점 (2026-05-15) 기준? 또는 2026 회계연도 시작? |

### D-2: 수수료 계정 활용도 향상

| 필요 활동 | 현재 상태 | Gap |
|---------|---------|-----|
| AI/자동화 비용 계정 분류 (현재 → 목표) | 현재 분류 미상 | ✗ — 더존 계정코드 매핑 조사 필요 |
| Claude 구독·Anthropic API 비용 추적 | paper-trading은 $0 — 구독토큰 (memory) / 미션 토큰은 cost_guardrail에서만 trace | 부분 — 단위 사업당 추적 미구축 |
| 외부 SaaS 비용 합계 (Airtable, Slack, GitHub, fly.io, Vercel, Supabase free) | 산발적, 합계 미산정 | ✗ — 통합 비용 시트 필요 |
| 수수료 계정 활용도 비율 산출 | 미구축 | ✗ — 정의 필요 (절대값? 비중? 시계열?) |

### D-3: 수평 생산성 50% 향상

| 필요 활동 | 현재 상태 | Gap |
|---------|---------|-----|
| "수평 생산성" 운영 정의 | 미정의 | ✗ — Sprint 2에서 단위 (처리량/시간/FTE/KRW) 확정 필요 |
| Baseline 측정 | Airtable movement·shipment 보유, 그러나 "생산성" 시점·단위 미정 | 부분 — 데이터는 있으나 정의 부재 |
| 50% 달성 경로별 측정 (자동화/AI/표준화) | 자동화·AI는 활동 중 (Harness, AutoResearch), 표준화(AX)는 미수행 | ✗ — AX 영역 부재 (Sprint 3) |
| 측정 주기 (월/분기) | 미정 | ✗ — Sprint 2 |

### D-4: 범위·성공 기준 모호 차단

| 필요 활동 | 현재 상태 | Gap |
|---------|---------|-----|
| 사용 시나리오 / 사용자 명시 (미활용 차단) | Harness 미션 모드는 사용자 본인 명시 — 그러나 SCM 실 다른 산출물 (TMS AutoResearch, 대시보드 등)의 사용자/주기 명시 부족 | 부분 — 일부 항목은 ad-hoc |
| ROI 사전 추정 + 사후 추적 | Validation Contract에 일부 (cost_guardrail $30) — 단 ROI 측정 메커니즘 부재 | ✗ — Sprint 3 ROI 매트릭스 필요 |
| Sunset 기준 (3개월 미사용 → 폐기 등) | 미정의 | ✗ — 거버넌스 룰 신규 |
| 비용 모니터링 통합 | cost_guardrail은 미션 단위만 | 부분 — 사업 단위 / 분기 단위 통합 부재 |
| scm-validator (gap 차단 자동화) | TMS 한정 lightweight 검토 중 (log.md 1818-1822) | ✗ — 구현 미정 (Sprint 4 백로그 후보) |

### Gap 분석 요약 (집계)

| 결정 | 완전 Gap (✗) | 부분 Gap (부분) | 비고 |
|-----|------------|---------------|------|
| D-1 | 4 | 0 | 재무 데이터 접근 + 계정 분류 + 산출 공식 부재 |
| D-2 | 3 | 1 | 비용 추적 일부 / 분류·산출 미구축 |
| D-3 | 3 | 1 | 데이터는 있으나 *정의*가 없음 |
| D-4 | 3 | 2 | 거버넌스 룰 + ROI 메커니즘 + 검증 자동화 부재 |

→ 13개 완전 Gap + 4개 부분 Gap. Sprint 2~4가 이를 단계별로 해소한다 (Sprint 2: D-1·D-2·D-3 측정 / Sprint 3: D-4 AX/DX 범위 / Sprint 4: OKR/WBS/RACI + 구현 미션 백로그).

---

## MECE 검증 결과

본 문서의 두 MECE 분해 — Issue Tree(4 root × L1 노드 12개) + Gap 분석 표(4 결정 × 필요 활동 16개) — 모두 자가 검증 완료.

| 검증 축 | 결과 |
|--------|------|
| Issue Tree overlap | **0** (cross-product 검사 — D-1.L2-a3 vs D-2.L1-A 등 4개 잠재 중복 후보 모두 *분리* 판정) |
| Issue Tree gap | **0** (log.md 1793-1801 6개 명시 항목 모두 트리 노드에 매핑) |
| Gap 표 overlap | **0** (각 결정의 필요 활동이 결정 간 중복 없음 — D-1 인건비 / D-2 AI 비용 분류 / D-3 운영 단위 / D-4 거버넌스로 직교) |
| Gap 표 exhaustive | **확인** (log.md "리스크 차단 포인트" 3개 — 미활용 / 낮은 ROI / 과비용 — 모두 D-4에 매핑) |

→ Issue Tree와 Gap 분석 양 축에서 **overlap=0, gap=0**.

---

## 원본 출처

| 인용 | 출처 | 위치 |
|-----|------|-----|
| 회의 결정 4개 원문 | `C:/Users/yjisu/Documents/ClaudeVault/SCM/_AutoResearch/wiki/log.md` | line 1787-1827 (특히 1793-1801) |
| SCM 운영 SSOT 정책 (Airtable, Supabase 제한) | `C:/Users/yjisu/.claude/projects/c--Users-yjisu-Desktop-SCM-WORK/memory/project_scm_redesign.md` | line 9-15 |
| TMS Phase 1 완료 상태 (17테이블, 백필 796건, 정산 3월 8,553,350원) | `C:/Users/yjisu/.claude/projects/c--Users-yjisu-Desktop-SCM-WORK/memory/project_tms_gap_completed.md` | line 7-32 |
| 회의 참석자 / 장소 (에이원센터, 5명) | `C:/Users/yjisu/.claude/projects/c--Users-yjisu-Desktop-SCM-WORK/memory/project_meeting_participants.md` | line 7-21 |
| 기술 스택 표 (Airtable / FastAPI / GitHub Actions / Dashboard) | `c:/Users/yjisu/Desktop/SCM_WORK/CLAUDE.md` | "기술 스택" 섹션 |
| Immutable Ledger 원칙 | 글로벌 `~/.claude/CLAUDE.md` ("공통 데이터 원칙") + 프로젝트 `CLAUDE.md` ("데이터 정합성 원칙") | 양쪽 |
| paper-trading / paperclip 메모 (Claude 구독토큰 $0) | memory `project_paper_trading.md`, `project_paperclip_integration.md` | 전체 |
| TMS AutoResearch 첫 분석 결과 (차량이용률 19.4% / OTIF 100%) | memory `project_tms_autoResearch.md` | 전체 |
| fly.io PDF 서버 비용 (~$0/월) | memory `project_flyio_config.md` | 전체 |
| Harness Engineering / 미션 모드 / Validation Contract 시스템 | 글로벌 `~/.claude/CLAUDE.md` "Harness Engineering" 섹션 + `~/.claude/harness/README.md` | 전체 |

총 10건 인용 (요구 ≥3건의 333%).

---

## Sprint 1 산출 요약 (5-line abstract for handoff)

1. 회의 의사결정 4개(D-1 매출액 대비 인건비 비율 / D-2 수수료 계정 활용도 / D-3 수평 생산성 50% / D-4 범위 모호 차단)를 log.md 1793-1801 원문 그대로 식별.
2. Pyramid (SCQA) governing thought: "SCM 실은 4개 결정을 단일 OKR 트리로 묶고, 그 아래 AX/DX를 MECE로 분할한 다음, 각 항목에 baseline/목표/주기/owner를 부착해야 한다".
3. Issue Tree 분해 — 4 root × L1 12개 × L2 36개. MECE 자가 검증 통과 (overlap=0, gap=0).
4. AS-IS 매핑 — Airtable WMS+TMS+Barcode (SSOT), FastAPI/Railway, GitHub Actions cron, fly.io, sincerely-scm-dashboard(Vercel+Supabase free), TMS AutoResearch, 정산 (3월 8,553,350원), Claude Harness, 도메인 에이전트 14개 (SK-01~09 + D-TMS1/2 + D1-3) 모두 매핑.
5. Gap 분석 — 13개 완전 Gap + 4개 부분 Gap. 다수 Gap은 *측정·정의·거버넌스* 부재이며 운영 자체는 정상. Sprint 2(KPI 측정) → Sprint 3(AX/DX 범위) → Sprint 4(OKR/WBS + 구현 미션 백로그)로 해소 예정.

**Sprint 1 산출 한계 (must_not 준수):** 본 문서는 Sprint 2의 KPI 트리, Sprint 3의 AX/DX 매트릭스, Sprint 4의 OKR/WBS/구현 미션 백로그를 포함하지 않는다 (S1.N3 + Karpathy Surgical Changes).
