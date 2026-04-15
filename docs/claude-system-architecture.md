# Claude Code 시스템 아키텍처 — 전체 구조 & 세션 워크플로우

> 작성일: 2026-04-14 | SCM_WORK 프로젝트 기준

---

## 1. 레이어 구조 (6단계)

```
┌──────────────────────────────────────────────────────────────┐
│  Layer 6: KNOWLEDGE LAYER (Obsidian + LightRAG + Graphify)   │  ← 장기 기억 + 코드 구조
├──────────────────────────────────────────────────────────────┤
│  Layer 5: MEMORY LAYER (auto-memory / MEMORY.md)             │  ← 세션 간 지식 영속
├──────────────────────────────────────────────────────────────┤
│  Layer 4: SKILL LAYER (Superpowers + 프로젝트 Skills)         │  ← 재사용 가능한 워크플로우
├──────────────────────────────────────────────────────────────┤
│  Layer 3: AGENT LAYER (14개 전문가 에이전트)                   │  ← 도메인 전문화
├──────────────────────────────────────────────────────────────┤
│  Layer 2: INSTRUCTION LAYER (CLAUDE.md ×2)                   │  ← 글로벌/프로젝트 규칙
├──────────────────────────────────────────────────────────────┤
│  Layer 1: HARNESS LAYER (settings.json + Hooks + Plugins)    │  ← 실행 환경 제어
└──────────────────────────────────────────────────────────────┘
```

---

## Layer 1: HARNESS LAYER

**파일:** `~/.claude/settings.json`

### 훅 (Hooks)

**글로벌 (`~/.claude/settings.json`)**

| 이벤트 | 동작 | 목적 |
|--------|------|------|
| `Stop` | Session End Checklist 출력 | 세션 종료 시 git commit 리마인더 |
| `Notification` | `powershell beep(800,300)` | 작업 완료 알림음 |

**프로젝트 레벨 (`project/.claude/settings.json`) — 실행 시점별 분류**

| 시점 | 매처 | 훅 파일 | 역할 |
|------|------|---------|------|
| `PreToolUse` | `Bash` | `check-sql-safety.sh` | UPDATE/DELETE 원장 차단 |
| `PreToolUse` | `Bash` | `protect-branch.sh` | force push 차단 |
| `PreToolUse` | `Edit\|Write` | `protect-sensitive-files.sh` | .env 수정 차단 |
| `PostToolUse` | `Edit\|Write` | `auto-format.sh` | Prettier 자동 포맷 |
| `PostToolUse` | `Edit\|Write` | `typecheck.sh` | `tsc --noEmit` 자동 실행 |
| `PostToolUse` | `Edit\|Write` | `test-on-change.sh` | Jest 자동 실행 |
| `Stop` | — | `build-gate.sh` | `npm run build` 검증 (세션 종료) |
| `SubagentStop` | — | `log-agent-usage.sh` | 서브에이전트 사용 로그 기록 |

### 플러그인 (Plugins) — `enabledPlugins`

| 플러그인 | 소스 | 주요 기능 |
|---------|------|----------|
| `superpowers` | anthropics/claude-plugins-official | 핵심 워크플로우 스킬 번들 |
| `feature-dev` | anthropics/claude-plugins-official | 기능 개발 가이드 |
| `frontend-design` | anthropics/claude-plugins-official | UI/UX 디자인 전문 |
| `code-review` | anthropics/claude-plugins-official | 코드 리뷰 |
| `playground` | anthropics/claude-plugins-official | 인터랙티브 HTML 플레이그라운드 |
| `playwright` | anthropics/claude-plugins-official | 브라우저 자동화 |
| `typescript-lsp` | anthropics/claude-plugins-official | TS 타입 검사 (LSP) |
| `security-guidance` | anthropics/claude-plugins-official | 보안 가이드 |
| `ui-ux-pro-max` | nextlevelbuilder/ui-ux-pro-max-skill | 50+ 스타일, 161 팔레트 |
| `bencium-controlled-ux-designer` | bencium/bencium-claude-code-design-skill | 접근성 UI/UX 전문 |

### 권한 설정 (permissions) — 프로젝트 레벨

```json
// allow (명시적 허용)
"Bash(python3 -:*)"
"Bash(npm run:*)"
"Bash(git:*)"
"Bash(bash .claude/hooks/*)"
"mcp__claude_ai_Airtable__list_tables_for_base"
"mcp__claude_ai_Airtable__list_records_for_table"
"mcp__claude_ai_Airtable__create_records_for_table"
"mcp__claude_ai_Airtable__update_records_for_table"
"mcp__claude_ai_Airtable__get_table_schema"

// deny (명시적 차단)
"Bash(rm -rf:*)"
```

### 핵심 설정 (글로벌)

```json
"effortLevel": "max"       // 최대 사고 품질
"autoMemoryEnabled": true  // 자동 메모리 저장
"model": "sonnet"          // 기본 모델 Sonnet 4.6
```

### 슬래시 커맨드 (`project/.claude/commands/`)

| 커맨드 | 파일 | 동작 |
|--------|------|------|
| `/start` | `start.md` | git log -10 + 다음 태스크 제안 |
| `/wms-master-data` | `wms-master-data.md` | SK-01 직접 호출 |
| `/wms-inbound` | `wms-inbound.md` | SK-02 직접 호출 |
| `/wms-inventory` | `wms-inventory.md` | SK-03 직접 호출 |
| `/wms-outbound` | `wms-outbound.md` | SK-04 직접 호출 |
| `/wms-return` | `wms-return.md` | SK-07 직접 호출 |

> 자동 위임(키워드)으로 충분하지만, 특정 에이전트를 명시적으로 시작할 때 사용

---

## Layer 2: INSTRUCTION LAYER

**2개의 CLAUDE.md가 계층적으로 적용된다.**

```
~/.claude/CLAUDE.md          ← 글로벌 (모든 프로젝트에 적용)
    ↓ 하위 프로젝트에서 확장/오버라이드
SCM_WORK/CLAUDE.md           ← 프로젝트 특화
```

### 글로벌 CLAUDE.md 핵심 내용

- **전문가 정체성 D2~D5** 정의 (D1은 SCM_WORK에서 정의)
- **자동 라우팅 규칙**: 키워드 → 도메인 → 에이전트 매핑
- **메인 워크플로우 사이클**: 구상→계획→실행→검토→검증
- **Obsidian 메모리 규칙**: Vault 위치, 저장 경로, 검색 라우팅
- **모델 라우팅 규칙**: Haiku/Sonnet/Opus 3단계 전략

### SCM_WORK CLAUDE.md 핵심 내용

- **D1 SCM/물류 전문가** 정의 (APICS CSCP+CPIM+CLTD 수준)
- **D2 세무/회계 SCM 특화** (더존 아마란스10, SAP FI/CO/MM)
- **프로젝트 특화 에이전트 8개** 키워드 라우팅
- **Graphify 코드베이스 그래프** 설정
- **검증 체크포인트**: 훅 결과 확인 → 보고 → 다음단계 확인

---

## Layer 3: AGENT LAYER

### 구조
```
.claude/agents/
├── (SCM 특화 — SK-01~SK-08)
│   ├── wms-master-data.md    SK-01  품목·로케이션·공급사
│   ├── wms-inbound.md        SK-02  입하·검수·입고
│   ├── wms-inventory.md      SK-03  재고원장·사이클카운팅
│   ├── wms-outbound.md       SK-04  피킹·패킹·Wave·SSCC
│   ├── tms-shipment.md       SK-05  출하·배송추적·POD
│   ├── tms-otif-kpi.md       SK-06  OTIF·KPI 대시보드
│   ├── wms-return.md         SK-07  반품·역물류
│   └── meeting-analysis.md   SK-08  회의록 분석·PDF 생성
│
└── (범용 전문가 — D1~D5 + Orchestrator)
    ├── scm-logistics-expert.md   D1
    ├── tax-accounting-expert.md  D2
    ├── tech-architect.md         D3
    ├── frontend-design-expert.md D4
    ├── project-manager.md        D5
    └── orchestrator.md           복합 요청 조율
```

### 에이전트 표준 구조

```yaml
---
name: {agent-id}
description: > 트리거 키워드 포함 한 줄 설명
tools: [Read, Edit, Write, Bash, Glob, Grep, ...]
model: claude-sonnet-4-6
permissionMode: acceptEdits
memory: project
---
```

내부 섹션: When Invoked → Memory 관리 → 역할 정의 → 참조 표준 → 도메인 지식 → 출력 형식 → 금지사항

### 라우팅 우선순위

```
사용자 요청
    ↓
[세밀한 키워드 매칭] → SK-01~SK-08 (프로젝트 특화)
    ↓ 미매칭
[일반 키워드 매칭] → D1~D5, Orchestrator (범용 전문가)
    ↓ 미매칭
[글로벌 CLAUDE.md 전문가 지식] 직접 적용
    ↓ 도메인 판별 불가
사용자에게 질문
```

### 오케스트레이터 5가지 패턴

| 패턴 | 구조 | 예시 |
|------|------|------|
| 병렬 독립 | `D1+D2 병렬 → 통합` | 재고 분석 + 회계 영향 |
| 순차 파이프라인 | `D1 → D3 → D5` | 프로세스 분석 → 설계 → 일정 |
| 감사/검증 | `D2 → D3 교차검증` | 마감 → 정합성 |
| 컨설팅 보고서 | `D5+D1+D3 병렬 → D5 통합` | 개선 제안서 |
| 풀스택 개발 | `D3+D4+D1/D2 병렬` | 대시보드 구축 |

---

## Layer 4: SKILL LAYER

### Superpowers (핵심 워크플로우 스킬)

| 스킬 | 트리거 | 역할 |
|------|--------|------|
| `using-superpowers` | 세션 시작 | 스킬 시스템 진입점, 1% 룰 강제 |
| `brainstorming` | `/brainstorm` 명시 시만 | 구상 단계 |
| `writing-plans` | 새 기능/수정 계획 전 | 계획 작성 |
| `executing-plans` | 계획 승인 후 | 단계별 실행 |
| `requesting-code-review` | 구현 완료 후 | 검토 요청 |
| `receiving-code-review` | 리뷰 피드백 수신 시 | 피드백 반영 |
| `verification-before-completion` | "완료" 선언 전 | 빌드/테스트 검증 |
| `systematic-debugging` | 버그/에러 발생 시 | 원인 분석 |
| `using-git-worktrees` | 독립 기능 병렬 개발 | 워크트리 격리 |
| `dispatching-parallel-agents` | 독립 태스크 2개 이상 | 병렬 에이전트 |
| `subagent-driven-development` | 독립 태스크 현 세션 실행 | 서브에이전트 |
| `finishing-a-development-branch` | 브랜치 완료 후 | 머지 전 체크 |
| `test-driven-development` | 기능/버그 구현 전 | TDD |

### 프로젝트 전용 스킬

| 스킬 | 트리거 | 역할 |
|------|--------|------|
| `start` | `/start` | 세션 시작 루틴 (git log + 다음 태스크 제안) |
| `learn` | `/learn` | 실수 → CLAUDE.md 강제 규칙 기록 |
| `worktree` | `/worktree` | 워크트리 격리 작업 공간 생성 |
| `graphify` | `/graphify` | 코드베이스 → 지식 그래프 탐색 |
| `meeting-analysis` | 회의록 첨부 시 | 회의록 분석 + PDF 생성 |
| `tms-otif-kpi` | KPI/OTIF 요청 시 | KPI 계산·집계·트렌드 |
| `tms-shipment` | 출하/배송 요청 시 | 배송 추적 에이전트 |
| `wms-*` (6개) | 각 WMS 도메인 | WMS 각 영역 전문 처리 |
| `logen-waybill-save` | 로젠 운송장 | Airtable 자동 저장 |
| `투입리스트` | 투입리스트 조회 | 자재 보충 현황 리포트 |
| `orchestrate` | 복합 요청 | 멀티 에이전트 조율 |
| `schedule` | 스케줄 설정 | 자동화 트리거 |

### 모델 선택 전략

```
요청 복잡도
    ↓
haiku  — 파일 조회, 키워드 검색, 단순 변환, Explore(quick)
sonnet — 코드 구현, 버그 수정, 기능 수정, Explore(medium) [기본값]
opus   — 아키텍처 설계, 심층 분석, Plan 에이전트, Explore(very thorough)
```

---

## Layer 5: MEMORY LAYER

**자동 메모리** (`autoMemoryEnabled: true`)

- 위치: `~/.claude/projects/c--Users-yjisu-Desktop-SCM-WORK/memory/`
- 인덱스: `MEMORY.md` (200줄 제한, 항상 컨텍스트 로드)

### 메모리 타입

| 타입 | 저장 내용 | 저장 시점 |
|------|----------|----------|
| `user` | 역할, 선호도, 지식 수준 | 사용자 특성 파악 시 |
| `feedback` | 교정 사항, 검증된 접근법 | 수정 요청 또는 확인 시 |
| `project` | 진행 중인 작업, 결정사항 | 프로젝트 상태 변경 시 |
| `reference` | 외부 시스템 위치/목적 | 외부 리소스 발견 시 |

### 현재 MEMORY.md 주요 항목

- SCM Redesign: Supabase 6스키마 55테이블 배포 완료, Retool 10페이지 운영
- TMS GAP 완료: 17테이블/백필796건, WMS Phase0 대기
- STOCK_WORK: Alpaca Paper Trading, Paperclip 6에이전트 연동 예정
- Airtable PAT, Stitch MCP 연결 완료

---

## Layer 6: KNOWLEDGE LAYER

### 3개 지식 시스템의 역할 분리

```
┌─────────────────────────────────────────────────────────────┐
│                     KNOWLEDGE LAYER                          │
│                                                              │
│  Obsidian Vault              LightRAG              Graphify  │
│  (ClaudeVault)               (의미 검색)           (코드 그래프) │
│  C:\Users\yjisu\             로컬+글로벌            graphify-out/│
│  Documents\ClaudeVault\      그래프 인덱스           graph.json  │
│                                                              │
│  리터럴 검색 ←               의미/교차 참조          코드 구조  →  │
│  노트 읽기/쓰기               요약/연관 분석          커뮤니티 탐색 │
└─────────────────────────────────────────────────────────────┘
```

### A. Obsidian Vault

**Vault 위치:** `C:\Users\yjisu\Documents\ClaudeVault\`

**폴더 구조:**

```
ClaudeVault/
├── SCM/
│   ├── TMS/          ← 택배사, 배송, OTIF, SCM AutoResearch
│   └── WMS/          ← 입하, 재고, 출고, 반품
├── SCM/Decisions/    ← 아키텍처 결정사항, SOP
├── STOCK/            ← 주식 전략, Paperclip, STOCK AutoResearch
├── _Common/          ← 공통, 개인, 템플릿
└── _AutoResearch/
    ├── SCM/wiki/log.md     ← SCM AutoResearch 연속성 로그
    └── STOCK/wiki/log.md   ← STOCK AutoResearch 연속성 로그
```

**세션 종료 시 자동 저장 규칙:**
- "저장해줘", "끝났어", "다음에 이어서" → 해당 프로젝트 폴더에 저장

### B. LightRAG (의미 검색)

**도구:** `mcp__lightrag__lightrag_query`

**Vault 검색 라우팅:**

| 질의 유형 | 사용 툴 |
|----------|---------|
| 파일명·키워드 리터럴 | `obsidian_simple_search` |
| **의미 검색·요약·교차참조** | **`lightrag_query`** (핵심) |
| 특정 노트 전문 조회 | `obsidian_get_file_contents` |
| 최근 변경 이력 | `obsidian_get_recent_changes` |

**프로젝트 스코프:**

| `project` 파라미터 | 인덱스 범위 |
|-------------------|------------|
| `tms` | SCM/TMS/ + _AutoResearch/SCM/ |
| `wms` | SCM/WMS/ |
| `stock` | STOCK/ + _AutoResearch/STOCK/ |
| `common` | Decisions/Architecture/SOPs + _Common |
| `all` | 4개 인덱스 병렬 (범위 불명확 시 기본값) |

**모드:**

| `mode` | 설명 |
|--------|------|
| `mix` (기본) | 로컬+글로벌 혼합 |
| `local` | 엔티티 중심 ("CJ 택배사 이슈") |
| `global` | 문서 전반 요약 ("TMS Phase1 핵심") |
| `naive` | 벡터만, 빠름 |

### C. Graphify (코드 구조 그래프)

**설치:** `pip install graphifyy` (Karpathy Wiki 패턴)

**그래프 위치:** `graphify-out/graph.json`
- 현재: 441 nodes, 506 edges, 93 communities

**사용법:**
```bash
/graphify query "입고 확정 처리 흐름"   # 코드 구조 탐색 (BFS)
/graphify path "GoodsReceipt" "InventoryLedger"  # 두 노드 간 최단 경로
/graphify explain "WmsInboundService"   # 특정 클래스/함수 설명 조회
graphify update .                       # 수동 업데이트
```

**자동 업데이트:** git commit 시 훅으로 자동 실행

---

## 세션 워크플로우 — 새 세션 시작부터 완료까지

### Phase 0: 세션 초기화 (자동)

```
세션 시작
    │
    ├─ [자동] MEMORY.md 로드 (항상)
    │      → 이전 세션 컨텍스트 복원
    │
    ├─ [자동] CLAUDE.md ×2 로드
    │      글로벌 (~/.claude/CLAUDE.md)
    │      + 프로젝트 (SCM_WORK/CLAUDE.md)
    │
    └─ [스킬] /start 실행 (사용자 요청 시 또는 프로젝트 열기 시)
           git log --oneline -10
           + Obsidian AutoResearch log.md 읽기
           → "현재 상태 요약 + 다음 추천 태스크 1개" 보고
```

### Phase 1: 요청 수신 & 라우팅

```
사용자 요청 입력
    │
    ├─ [스킬 시스템] 1% 룰 — 관련 스킬 있으면 반드시 호출
    │
    ├─ [도메인 감지] 키워드 → 도메인 분류
    │      세밀한 키워드 → SK-01~SK-08
    │      일반 키워드  → D1~D5 / orchestrator
    │      복수 도메인  → orchestrator 5패턴 선택
    │
    └─ [요청 유형 분류] 스킵 매트릭스 적용
           질문/설명/분석 → 즉시 응답 (워크플로우 생략)
           1~2줄 수정    → 즉시 실행
           버그 수정     → systematic-debugging → 실행 → 검토 → 검증
           기존 기능 수정 → 계획 → 실행 → 검토 → 검증
           새 기능       → (brainstorm →) 계획 → 실행 → 검토 → 검증
```

### Phase 2: 실행 워크플로우 (5단계 사이클)

```
1. [구상] — /brainstorm 명시 시만
   superpowers:brainstorming 호출
   아이디어 발산 → 방향 결정
        ↓
2. [계획] — 코드 작성 전 필수
   superpowers:writing-plans 호출
   단계별 구현 계획 작성
   사용자 승인 후 진행 (승인 없이 코드 수정 금지)
        ↓
3. [실행] — 계획대로
   superpowers:executing-plans 호출
   에이전트/스킬 선택 → 병렬 또는 순차 실행
   태스크마다 체크포인트 확인
        ↓
4. [검토] — 구현 완료 후
   superpowers:requesting-code-review 호출
   계획 대비 구현 검토
   Critical/Important → 3으로 돌아가 수정
   Minor → TODO 기록 후 5로 진행
        ↓
5. [검증] — "완료" 선언 전 필수
   superpowers:verification-before-completion 호출
   typecheck ✅ / 테스트 ✅ N개 통과 확인
   빌드 게이트 통과
   증거 없이 "완료" 선언 금지
```

### Phase 3: 지식 동기화 (세션 종료)

```
작업 완료
    │
    ├─ git commit (필수, CLAUDE.md 강제 규칙)
    │
    ├─ Obsidian 저장 (결정사항·완료항목·이슈·다음 할 일)
    │      SCM 관련 → SCM/TMS/ 또는 SCM/WMS/ 또는 SCM/Decisions/
    │      STOCK 관련 → STOCK/
    │
    ├─ AutoResearch log.md 업데이트
    │      ## [YYYY-MM-DD] {타입} | {제목} 형식으로 기록
    │
    ├─ Graphify 자동 업데이트 (git hook)
    │      graph.json 재생성 (변경된 코드 반영)
    │
    └─ [자동] MEMORY.md 업데이트
           새로운 결정/피드백/프로젝트 상태 저장
```

---

## 특수 경로 & 단축 흐름

### 버그 발생 시

```
에러/예상치 못한 동작
    → superpowers:systematic-debugging (원인 분석 필수)
    → 원인 파악 후 수정
    → 메인 사이클 4 (검토)부터 합류
```

### 병렬 작업 시

```
독립 기능 2개 이상
    → /worktree 커맨드
    → .worktrees/<브랜치명> 생성
    → superpowers:dispatching-parallel-agents
    → 각 에이전트 독립 실행
    → 결과 통합
```

### 디자인/UI 작업 시

```
UI/스타일 변경
    → frontend-design:frontend-design 스킬 호출
    → 렌더링 시뮬레이션
    → 디자인 확정 후 메인 사이클 3 (실행)으로
```

### 지식 검색 시 (어떤 툴을 쓸지)

```
질의 성격 판단
    │
    ├─ "파일명 or 특정 단어 존재?"
    │      → obsidian_simple_search
    │
    ├─ "왜 그렇게 됐지? / 요약해줘 / 연관된 게 뭐야?"
    │      → lightrag_query (project + mode 파라미터 선택)
    │
    ├─ "코드에서 이 함수가 어떻게 연결돼?"
    │      → /graphify query "..."
    │
    └─ "이미 경로 아는 노트 전문"
           → obsidian_get_file_contents
```

---

## 전체 시스템 흐름도 (요약)

```
사용자 메시지
    │
    ▼
[Layer 1: Harness]
settings.json 설정 + Hooks 이벤트 감시
    │
    ▼
[Layer 2: Instructions]
글로벌 CLAUDE.md + 프로젝트 CLAUDE.md 규칙 적용
    │
    ▼
[Layer 4: Skills]
1% 룰 — 관련 스킬 있으면 반드시 호출
    │
    ▼
[Layer 3: Agents]
도메인 키워드 → SK-01~SK-08 / D1~D5 / Orchestrator
    │
    ▼
[Layer 5: Memory]
MEMORY.md 현재 컨텍스트 참조
    │
    ▼
[Layer 6: Knowledge]
Obsidian (노트) + LightRAG (의미) + Graphify (코드)
    │
    ▼
실행 → 검증 → git commit → Obsidian 저장 → 메모리 갱신
```

---

## 빠른 참조 카드

### 내가 쓸 수 있는 주요 커맨드

| 커맨드 | 동작 |
|--------|------|
| `/start` | 세션 시작 (git log + 다음 태스크) |
| `/brainstorm` | 구상 단계 시작 |
| `/graphify query "..."` | 코드 구조 질의 |
| `/graphify path A B` | 두 노드 경로 탐색 |
| `/graphify explain "클래스명"` | 특정 클래스/함수 설명 |
| `/worktree` | 병렬 작업 격리 공간 생성 |
| `/learn` | 이번 세션 실수 → CLAUDE.md 기록 |
| `/model opus` | 주 대화 모델을 Opus로 전환 |
| `/model haiku` | 주 대화 모델을 Haiku로 전환 |

### 에이전트 호출 키워드 요약

```
품목/로케이션/공급사 → SK-01  |  피킹/패킹/Wave → SK-04
입하/검수/GR        → SK-02  |  운송장/배송추적 → SK-05
재고불일치/사이클   → SK-03  |  OTIF/KPI       → SK-06
                              |  반품/역물류     → SK-07
                              |  회의록          → SK-08
```

---

## MCP 서버 설정

```bash
# 1. Airtable MCP — 환경변수 설정 후 Claude Code에서 자동 연결
#    Claude Code → Settings → MCP → Add
AIRTABLE_PAT=patXXXXXXXXXXXXXX    # 환경변수로 주입

# 2. Obsidian Local REST API — Obsidian 실행 중이면 자동 연결
#    Obsidian → Settings → Community Plugins → obsidian-local-rest-api → Enable
#    Port: 27124 (기본값)

# 3. LightRAG MCP 서버 — 의미 검색용
pip install lightrag-hku
claude mcp add lightrag --url http://localhost:8020
```

**연결 상태 확인:**
```bash
claude mcp list    # 등록된 MCP 서버 목록
```

---

## WMS 도메인 규칙

### Stock Type (재고 유형 5종)

| Stock Type | 설명 |
|-----------|------|
| `UNRESTRICTED` | 출고 가능한 실재고 |
| `QUALITY_INSPECTION` | QC 검수 중 |
| `BLOCKED` | 불량·격리 재고 |
| `IN_TRANSIT` | 입하 중 (창고 미도착) |
| `RESERVED` | Wave 피킹 예약됨 |

### Movement Type (SAP 이동유형 8종)

| 코드 | 유형 | 동작 |
|------|------|------|
| `101` | RECEIVE | 입고 확정 |
| `122` | RETURN_TO_SUPPLIER | 공급사 반품 |
| `201` | ISSUE_INTERNAL | 출고 |
| `261` | ISSUE_PRODUCTION | 생산 출고 |
| `311` | TRANSFER | 창고 간 이전 |
| `601` | SHIP | 배송 출고 |
| `701` | ADJUST_PLUS | 재고 조정+ |
| `702` | ADJUST_MINUS | 재고 조정- |

### Stock Type 전환 상태머신

```
입하:    없음 → IN_TRANSIT
검수:    IN_TRANSIT → QUALITY_INSPECTION
합격:    QUALITY_INSPECTION → UNRESTRICTED   (Movement 101)
불합격:  QUALITY_INSPECTION → BLOCKED        (격리)
피킹예약: UNRESTRICTED → RESERVED
출고:    RESERVED → 삭제, qty 감소           (Movement 601)
반품:    없음 → BLOCKED (QC_HOLD)
재입고:  BLOCKED → UNRESTRICTED             (Movement 701)
폐기:    BLOCKED → 삭제                     (Movement 702)
```

### KPI 목표

| KPI | 목표 |
|-----|------|
| Dock-to-Stock | ≤ 8시간 (480분) |
| 피킹 정확도 | ≥ 99.5% |
| 재고 정확도 | ≥ 99% |
| 반품율 | ≤ 0.5% |
| AQL 합격 기준 | 불량률 ≤ 1.0% |

### 절대 금지 규칙

- `InventoryTransaction` UPDATE/DELETE → **REVERSAL 트랜잭션**으로만 처리
- 마스터 데이터 DELETE → `is_active = false`로 비활성화
- QcRecord 없이 입고 확정 → AQL 샘플링 필수
- Wave 없이 직접 피킹 → Wave → PickingTask 경로 필수

---

*이 문서는 세션 구조를 빠르게 파악하기 위한 레퍼런스입니다.*  
*실제 규칙의 원본은 CLAUDE.md 파일들과 각 에이전트/스킬 파일을 참조하세요.*
