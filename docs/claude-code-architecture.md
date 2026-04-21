# Claude Code 하네스 아키텍처 — Sincerely SCM (TMS / WMS)

> Claude Code를 단순 코딩 도우미가 아닌 **도메인 전문가 팀 + 자동화 안전망**으로 구성한 방법을 설명합니다.

---

## 전체 레이어 구조

```
┌──────────────────────────────────────────────────────────────────────┐
│                         USER / CLAUDE CODE CLI                        │
├──────────────┬───────────────────────────┬───────────────────────────┤
│  Layer 0     │ CLAUDE.md                 │ 프로젝트 컨텍스트 주입     │
├──────────────┼───────────────────────────┼───────────────────────────┤
│  Layer 1     │ .claude/settings.json     │ 권한 + 훅 설정 (harness)  │
├──────────────┼───────────────────────────┼───────────────────────────┤
│  Layer 2     │ .claude/hooks/            │ 이벤트 기반 자동 안전망    │
├──────────────┼───────────────────────────┼───────────────────────────┤
│  Layer 3a    │ .claude/commands/         │ 슬래시 커맨드 (워크플로우) │
│  Layer 3b    │ .claude/skills/           │ 도메인 지식 라이브러리     │
├──────────────┼───────────────────────────┼───────────────────────────┤
│  Layer 4     │ .claude/agents/           │ 도메인 전문가 에이전트 팀  │
│              │ .claude/agent-memory/     │ 에이전트 장기 기억         │
├──────────────┼───────────────────────────┼───────────────────────────┤
│  Layer 5     │ NestJS + Supabase + Airtable │ 비즈니스 로직 (코드)   │
└──────────────┴───────────────────────────┴───────────────────────────┘
```

**핵심 철학:**
- **Airtable = 운영 입력 레이어** (API로만 읽기, 직접 수정 금지)
- **Supabase = 불변 원장** (INSERT ONLY, UPDATE/DELETE 절대 금지)
- **에이전트 = 오케스트레이션** (도메인 판단, 패턴 매칭, 지식 적용)
- AI 판단이 데이터 무결성을 우회하지 못하도록 훅이 독립적으로 방어

---

## Layer 0 — CLAUDE.md (컨텍스트 주입)

파일: `CLAUDE.md` (프로젝트 루트)

Claude Code가 프로젝트를 열 때 자동으로 읽는 **시스템 프롬프트** 역할입니다.

### 담는 내용

| 섹션 | 역할 |
|------|------|
| 세션 시작 자동 실행 | `git log` + AutoResearch 상태 복원 → 매 세션 컨텍스트 유지 |
| 데이터 정합성 원칙 | Airtable/Supabase 역할 분리, INSERT ONLY 원칙 명시 |
| 회계/ERP 기준 | K-IFRS, 더존 아마란스10 계정코드, SAP 이동유형 |
| 에이전트 라우팅 테이블 | 키워드 → 어느 에이전트로 위임할지 |
| 검증 체크포인트 | 코딩 완료 후 반드시 실행할 훅 결과 확인 순서 |
| 금지 표현 | 증거 없이 "완료" 선언 시스템 수준 차단 |

### 에이전트 라우팅 테이블 (키워드 → 에이전트)

| 키워드 | 에이전트 | 코드 |
|--------|---------|------|
| 품목코드, 로케이션, 공급사, 바코드, ROP | wms-master-data | SK-01 |
| 입하, 검수, GR, ASN, AQL, Dock-to-Stock | wms-inbound | SK-02 |
| 재고 불일치, 사이클카운팅, 음수재고 | wms-inventory | SK-03 |
| 피킹, 패킹, Wave, SSCC, 출고지시 | wms-outbound | SK-04 |
| 운송장, 택배, 배송추적, POD | tms-shipment | SK-05 |
| OTIF, KPI 달성률, Dock-to-Stock 시간 | tms-otif-kpi | SK-06 |
| 반품, 역물류, RESTOCK, DISPOSE | wms-return | SK-07 |
| 회의록, 회의 분석, 액션아이템 | meeting-analysis | SK-08 |
| 재고 전략, 물류 컨설팅, SCM 개선 | scm-logistics-expert | D1 |
| 분개, 전표, 세금, K-IFRS, 더존 | tax-accounting-expert | D2 |
| 코드, API, DB, 배포, 아키텍처 | tech-architect | D3 |
| UI, 디자인, CSS, 컴포넌트 | frontend-design-expert | D4 |
| 프로젝트 계획, KPI, MECE, 일정 | project-manager | D5 |
| 복합 요청, 종합 분석, 제안서 | orchestrator | — |

---

## Layer 1 — settings.json (하네스 설정)

파일: `.claude/settings.json`

```json
{
  "permissions": {
    "allow": [
      "Bash(python3 -:*)",
      "Bash(npm run:*)",
      "Bash(git:*)",
      "mcp__claude_ai_Airtable__list_records_for_table"
    ],
    "deny": [
      "Bash(rm -rf:*)"
    ]
  },
  "hooks": {
    "PreToolUse":  { ... },   // 실행 전 차단
    "PostToolUse": { ... },   // 실행 후 자동 검증
    "Stop":        { ... },   // 세션 종료 시 빌드 게이트
    "SubagentStop":{ ... }    // 에이전트 종료 시 로깅
  }
}
```

### 이벤트별 훅 매핑

| 이벤트 | 조건 | 실행 훅 |
|--------|------|--------|
| `PreToolUse` | `Bash` 실행 전 | check-sql-safety + protect-branch |
| `PreToolUse` | `Edit\|Write` 전 | protect-sensitive-files |
| `PostToolUse` | `Edit\|Write` 후 | auto-format + typecheck + test-on-change |
| `Stop` | 세션 종료 시 | build-gate |
| `SubagentStop` | 에이전트 종료 시 | log-agent-usage |

### MCP 도구 권한 (Airtable 연동)
```
"mcp__claude_ai_Airtable__list_records_for_table"   ← 읽기 허용
"mcp__claude_ai_Airtable__list_tables_for_base"     ← 구조 조회 허용
```
쓰기 MCP 도구는 에이전트별로 `tools:` 필드에서 개별 선언 → 최소 권한 원칙 적용.

---

## Layer 2 — Hooks (도메인 안전망 7개)

디렉토리: `.claude/hooks/`

SCM 특성상 **불변 원장 보호**와 **빌드 품질 게이트**가 핵심입니다.

### 훅 목록

```
.claude/hooks/
├── check-sql-safety.sh        ← INSERT ONLY 원칙 위반 감지 (PreToolUse)
├── protect-branch.sh          ← main 브랜치 직접 수정 차단 (PreToolUse)
├── protect-sensitive-files.sh ← .env, 자격증명 파일 보호 (PreToolUse)
├── auto-format.sh             ← 파일 수정 후 자동 포맷 (PostToolUse)
├── typecheck.sh               ← TypeScript 타입 검증 (PostToolUse)
├── test-on-change.sh          ← 변경된 파일 관련 테스트 실행 (PostToolUse)
├── build-gate.sh              ← 세션 종료 전 빌드 통과 필수 (Stop)
└── log-agent-usage.sh         ← 에이전트 실행 감사 로그 (SubagentStop)
```

### 핵심 훅 상세

#### check-sql-safety.sh — 불변 원장 보호

```bash
# PreToolUse:Bash 훅 — INSERT ONLY 원칙 자동 강제
PROTECTED="mat_document|stock_balance|inventory_transaction|accounting_entries|period_close"
if echo "$CMD" | grep -iE "(UPDATE|DELETE)\s.*($PROTECTED)"; then
  echo "BLOCK: INSERT ONLY 원칙 위반"
  exit 2  # Hard block — 실행 중단
fi
```

불변 원장 테이블 5개에 UPDATE/DELETE 시도 시 **AI가 실행하기 전에 시스템이 차단**합니다. 역분개(Storno)로만 정정 가능.

#### build-gate.sh — 세션 종료 게이트

```bash
# Stop 훅 — 세션이 끝날 때마다 자동 실행
if grep -q '"build"' package.json; then
  npm run build
  # 실패 시 exit 2 → Claude가 세션을 종료하지 못하고 오류 보고
fi
```

세션 종료 시 빌드가 깨져 있으면 종료를 차단하고 사용자에게 알립니다.

#### typecheck.sh + test-on-change.sh — 즉각 피드백 루프

파일을 수정할 때마다 자동으로 타입 검증과 관련 테스트가 실행됩니다. 에이전트가 코드를 작성하는 즉시 품질을 확인합니다.

---

## Layer 3a — Commands (슬래시 커맨드 / 워크플로우)

디렉토리: `.claude/commands/`

사용자가 `/wms-inbound` 처럼 입력하면 해당 파일을 로드해 절차를 따릅니다.

### 커맨드 목록

```
.claude/commands/
├── start.md              ← /start → 세션 시작 (git log + 상태 복원)
├── wms-inbound.md        ← /wms-inbound → 입하 관리 에이전트 호출
├── wms-inventory.md      ← /wms-inventory → 재고 관리
├── wms-master-data.md    ← /wms-master-data → 마스터 데이터
├── wms-outbound.md       ← /wms-outbound → 출고 관리
├── wms-return.md         ← /wms-return → 반품 처리
├── tms-shipment.md       ← /tms-shipment → 출하·배송추적
├── tms-otif-kpi.md       ← /tms-otif-kpi → OTIF KPI 분석
├── meeting-analysis.md   ← /meeting-analysis → 회의록 분석
├── migrate.md            ← /migrate → DB 마이그레이션 실행
├── orchestrate.md        ← /orchestrate → 다중 에이전트 조율
├── worktree.md           ← /worktree → 병렬 작업 격리 브랜치
├── learn.md              ← /learn → 실수 기록 + 학습
└── 투입리스트.md          ← /투입리스트 → 포장재 투입 리스트 생성
```

**commands vs skills 차이:**
- `commands/` = **워크플로우 트리거** ("이걸 실행해라")
- `skills/` = **도메인 지식 라이브러리** ("이렇게 판단해라")

---

## Layer 3b — Skills (도메인 지식 라이브러리)

디렉토리: `.claude/skills/`

에이전트가 참조하는 **전문 지식 절차서**입니다. 커맨드와 달리 직접 호출이 아니라 에이전트가 내부적으로 사용합니다.

```
.claude/skills/
├── scm/
│   ├── sap-movement.md          ← SAP 이동유형 결정 로직 + Storno 처리
│   └── pdf-pipeline.md          ← PDF 문서 생성 파이프라인
├── accounting/
│   ├── k-ifrs-journal-entry.md  ← K-IFRS 분개 생성 절차
│   ├── 3way-invoice-match.md    ← 3-Way Invoice Matching (PO/GR/Invoice)
│   └── period-close.md          ← 기간 마감 절차
├── tech/
│   ├── db-data-integrity.md     ← DB 정합성 검증 패턴
│   └── db-query-optimizer.md    ← 쿼리 최적화 가이드
├── design/
│   └── wcag-audit.md            ← WCAG 2.1 접근성 감사
└── pm/
    ├── mece-decomposition.md    ← MECE 문제 분해
    └── risk-register.md         ← 리스크 레지스터 작성
```

### skill 파일 구조 예시 (sap-movement.md)

에이전트가 SAP 이동유형을 결정해야 할 때 참조하는 지식:

```
에어테이블 '이동목적' → SAP Movement Type 매핑:
재고이동   → 311 (창고간 이동)
재고생산   → 101 (발주 입고, GR)
생산투입   → 201 (원가센터 출고)
고객납품   → 601 (고객 출고)
...

Storno(역분개) 처리 절차:
1. 원본 전표 조회 (doc_number로 검색)
2. STORNO-{원본doc_number} 역방향 전표 INSERT
3. direction: 원본 * -1 (역방향)
```

코드가 아닌 **절차와 판단 기준**을 담습니다.

---

## Layer 4 — Agents (도메인 전문가 팀 13명)

디렉토리: `.claude/agents/`

### 에이전트 구성

```
.claude/agents/
│
│  ── WMS 도메인 (운영 특화) ──
├── wms-master-data.md      ← SK-01: 품목코드·로케이션·공급사 마스터
├── wms-inbound.md          ← SK-02: 입하·검수·AQL·Dock-to-Stock
├── wms-inventory.md        ← SK-03: 재고 실사·불일치·사이클카운팅
├── wms-outbound.md         ← SK-04: 피킹·패킹·Wave·SSCC·출고
├── wms-return.md           ← SK-07: 반품·역물류
│
│  ── TMS 도메인 (운송 특화) ──
├── tms-shipment.md         ← SK-05: 출하·택배사 연동·배송추적·POD
├── tms-otif-kpi.md         ← SK-06: OTIF·KPI 계산·대시보드
│
│  ── 업무 지원 ──
├── meeting-analysis.md     ← SK-08: 회의록 분석·액션아이템 추출
│
│  ── 범용 전문가 (D1~D5) ──
├── scm-logistics-expert.md ← D1: APICS CSCP+CPIM, SCOR, SAP EWM/TM
├── tax-accounting-expert.md← D2: CPA+CTA, K-IFRS, 더존 아마란스10
├── tech-architect.md       ← D3: NestJS, Supabase, API, CI/CD
├── frontend-design-expert.md ← D4: UI/UX, WCAG 2.1, 반응형
├── project-manager.md      ← D5: PMBOK, Agile, MECE, OKR
└── orchestrator.md         ← 복합 요청 조율 (패턴 5가지)
```

### 에이전트 파일 구조

```markdown
---
name: wms-inbound
description: >
  WMS 인바운드 전문 에이전트 (SK-02). GoodsReceipt 생성, AQL 샘플링 검수.
  입하·입고·검수·GR·ASN·QC·AQL·Dock-to-Stock 관련 시 자동 위임.
  Use proactively after 공급사 납품 도착 또는 ASN 수신 시.
tools: Read, Edit, Write, Bash, Glob, Grep,
       mcp__claude_ai_Airtable__list_records_for_table,
       mcp__claude_ai_Airtable__update_records_for_table
model: claude-sonnet-4-6
permissionMode: acceptEdits
memory: project
---

## When Invoked (즉시 실행 체크리스트)
1. agent-memory에서 공급사별 QC 불량 패턴 확인
2. AQL 샘플 수량 자동 계산: ceil(√total_qty × 10), 최소 5개
3. 작업 실행 → Dock-to-Stock 시간 기록
...
```

### 주요 필드 설명

| 필드 | 설명 |
|------|------|
| `description` | 자동 라우팅 트리거 키워드 포함 — Claude가 이 텍스트로 언제 호출할지 판단 |
| `tools` | 이 에이전트만 사용 가능한 도구 목록 (Airtable 쓰기 권한은 일부만 부여) |
| `model` | 에이전트별 모델 (현재 전원 sonnet, orchestrator는 필요시 opus) |
| `permissionMode: acceptEdits` | 에이전트가 파일 수정 시 사용자 확인 없이 진행 |
| `memory: project` | 프로젝트 레벨 메모리 공유 |
| `Use proactively after ...` | Claude가 특정 상황에서 자동으로 에이전트를 호출하는 조건 |

---

## Agent Memory (에이전트 장기 기억)

디렉토리: `.claude/agent-memory/`

에이전트가 세션을 넘어 **누적 지식을 유지**하는 공간입니다.

```
.claude/agent-memory/
└── scm-logistics-expert/
    ├── MEMORY.md              ← 에이전트 인덱스 (매 세션 자동 로드)
    ├── project_context.md     ← 프로젝트 현황 (AS-IS/TO-BE 상태)
    └── gap_analysis_2026q1.md ← Q1 Gap Analysis 결과
```

**어떻게 동작하나:**
- `wms-inbound` 에이전트는 검수 시작 전 `agent-memory`에서 해당 공급사의 이전 QC 불량 패턴을 확인합니다
- 반복 불량 공급사 발견 시 자동으로 기록을 업데이트합니다
- 다음 세션에서도 이 패턴이 유지됩니다

---

## 오케스트레이션 패턴 (orchestrator 에이전트)

복수 도메인이 교차하는 복합 요청 시 `orchestrator`가 전문가를 조합합니다.

### 5가지 조합 패턴

| 패턴 | 언제 사용 | 예시 |
|------|----------|------|
| **1. 병렬 독립** | 독립 분석 여러 개 | 재고 분석(D1) + 회계 영향(D2) 동시 실행 |
| **2. 순차 파이프라인** | 앞 결과 → 뒤 입력 | 프로세스 분석(D1) → 설계(D3) → 일정(D5) |
| **3. 감사/검증** | 실행 후 교차 검증 | 기간 마감(D2) → 정합성 검증(D3) |
| **4. 컨설팅 보고서** | PM이 구조, 전문가가 내용 | D5+D1+D3 병렬 → D5 통합 |
| **5. 풀스택 개발** | 코드 복합 작업 | D3+D4+D1 병렬, worktree 격리 |

### 실행 흐름 예시: OTIF 개선 제안서 요청

```
User: "4월 OTIF 분석해서 개선 제안서 만들어줘"
  │
  ▼
[orchestrator] — 패턴 4 선택 (컨설팅 보고서)
  │
  ├── [tms-otif-kpi (SK-06)] — Airtable에서 OTIF 데이터 수집 + KPI 계산
  ├── [scm-logistics-expert (D1)] — SCOR 관점 프로세스 갭 분석
  └── [project-manager (D5)] — MECE 구조화 + 제안서 형식 작성
  │
  ▼
[orchestrator] — 3개 결과 통합 → 최종 제안서
```

---

## Worktree (병렬 독립 개발)

명령어: `/worktree`

독립 기능을 **브랜치 충돌 없이 동시 개발**할 수 있습니다.

```bash
# 예시: WMS 출고 기능과 TMS 대시보드를 동시 개발
/worktree wms-outbound-wave    # .worktrees/wms-outbound-wave/ 생성
/worktree tms-dashboard        # .worktrees/tms-dashboard/ 생성
```

각 worktree는 독립적인 git 브랜치로, 메인 코드베이스와 분리되어 작업합니다.

---

## 외부 연동 (MCP)

### Airtable MCP

에이전트가 자연어로 Airtable 데이터를 조회/수정합니다:

```
mcp__claude_ai_Airtable__list_records_for_table   ← 레코드 조회
mcp__claude_ai_Airtable__update_records_for_table ← 레코드 수정 (일부 에이전트만)
```

**중요:** Airtable은 운영 입력 레이어이므로 조회는 자유, 수정은 해당 도메인 에이전트만 허용.

### Obsidian + LightRAG

세션 간 지식 지속성을 위해 Obsidian Vault를 활용합니다:

```
Vault: C:\Users\yjisu\Documents\ClaudeVault\
  SCM/TMS/   ← TMS 관련 노트
  SCM/WMS/   ← WMS 관련 노트
  _AutoResearch/SCM/   ← 자동 분석 결과
```

LightRAG로 의미 검색 ("4월에 어떤 배송 이슈가 있었어?") 지원.

---

## 디렉토리 구조 한눈에 보기

```
SCM_WORK/
├── CLAUDE.md                       ← Layer 0: 프로젝트 컨텍스트
│
├── .claude/
│   ├── settings.json               ← Layer 1: 권한 + 훅 설정
│   │
│   ├── hooks/                      ← Layer 2: 자동 안전망
│   │   ├── check-sql-safety.sh     ← INSERT ONLY 강제
│   │   ├── protect-branch.sh       ← main 브랜치 보호
│   │   ├── protect-sensitive-files.sh ← .env 보호
│   │   ├── auto-format.sh          ← 자동 포맷
│   │   ├── typecheck.sh            ← TS 타입 검증
│   │   ├── test-on-change.sh       ← 변경 시 테스트
│   │   ├── build-gate.sh           ← 세션 종료 빌드 게이트
│   │   └── log-agent-usage.sh      ← 에이전트 감사 로그
│   │
│   ├── commands/                   ← Layer 3a: 슬래시 커맨드
│   │   ├── start.md                ← /start
│   │   ├── wms-inbound.md          ← /wms-inbound
│   │   ├── tms-shipment.md         ← /tms-shipment
│   │   ├── tms-otif-kpi.md         ← /tms-otif-kpi
│   │   ├── migrate.md              ← /migrate
│   │   ├── worktree.md             ← /worktree
│   │   └── ...
│   │
│   ├── skills/                     ← Layer 3b: 도메인 지식
│   │   ├── scm/sap-movement.md     ← SAP 이동유형 판단
│   │   ├── accounting/k-ifrs-journal-entry.md
│   │   ├── tech/db-data-integrity.md
│   │   └── ...
│   │
│   ├── agents/                     ← Layer 4: 전문가 팀
│   │   ├── orchestrator.md         ← 복합 요청 조율
│   │   ├── wms-inbound.md          ← SK-02
│   │   ├── tms-shipment.md         ← SK-05
│   │   └── ... (13명 총)
│   │
│   ├── agent-memory/               ← 에이전트 장기 기억
│   │   └── scm-logistics-expert/
│   │       ├── MEMORY.md
│   │       └── project_context.md
│   │
│   └── logs/
│       └── agent-usage.log         ← 에이전트 실행 감사 로그
│
├── src/                            ← Layer 5: NestJS 비즈니스 로직
│   ├── wms/
│   └── tms/
│
├── supabase/
│   ├── migrations/                 ← DB 스키마 (6스키마 51테이블)
│   └── seed/
│
├── airtable-pipeline/              ← Airtable → Supabase 파이프라인
│
└── graphify-out/
    └── graph.json                  ← 코드베이스 지식 그래프
```

---

## 핵심 설계 원칙

### 1. Immutable Ledger (불변 원장)
원장 데이터(재고, 회계, 거래)는 INSERT ONLY. 정정은 역분개(Storno)로만 처리. `check-sql-safety.sh` 훅이 시스템 레벨에서 강제합니다.

### 2. Defense in Depth (다층 방어)
```
CLAUDE.md 원칙 선언
  → check-sql-safety.sh 훅 (SQL 자동 차단)
  → 에이전트 금지사항 명시
  → NestJS Service 레이어 검증
  → Supabase RLS 정책
```
각 레이어가 독립적으로 방어하므로 하나가 뚫려도 다음 레이어가 막습니다.

### 3. 도메인 특화 에이전트
범용 AI에게 "입고 처리해줘"라고 하는 것과, AQL 샘플링 수식·Dock-to-Stock KPI·SAP 이동유형을 알고 있는 `wms-inbound` 에이전트에게 요청하는 것은 질적으로 다릅니다. 에이전트가 도메인 전문가 역할을 합니다.

### 4. 즉각 피드백 루프
코드 수정 → PostToolUse 훅 → 자동 타입 검증 + 테스트 실행 → 에이전트가 즉시 결과 확인. "나중에 테스트하겠습니다" 없이 수정 즉시 품질 확인됩니다.

### 5. 세션 연속성
세션이 끊겨도 `agent-memory`, Obsidian Vault, `git log` 3가지로 컨텍스트를 복원합니다.

---

*작성: 2026-04-16*
