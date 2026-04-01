# Claude Code 셋팅 레이어 구조 가이드

> 팀원 공유용 — Claude Code를 프로젝트에 체계적으로 설정하는 6개 레이어 정리

---

## 전체 구조 한눈에 보기

```
┌──────────────────────────────────────────────────────────┐
│  Layer 6: Orchestration  (조율)                           │
│  여러 Subagent를 병렬 실행하고 결과를 취합                  │
├──────────────────────────────────────────────────────────┤
│  Layer 5: Team Agent  (팀 에이전트)                        │
│  .claude/agents/*.md — 역할별 전문 에이전트 정의            │
├──────────────────────────────────────────────────────────┤
│  Layer 4: Subagent  (서브에이전트)                         │
│  Agent tool — 독립 컨텍스트 창에서 단일 작업 위임            │
├──────────────────────────────────────────────────────────┤
│  Layer 3: Skills & Commands  (워크플로우 패턴)              │
│  .claude/skills/*.md + .claude/commands/*.md              │
│  ~/.claude/plugins/**  (superpowers, feature-dev 등)      │
├──────────────────────────────────────────────────────────┤
│  Layer 2: Harness / settings.json  (자동화)                │
│  hooks: PreToolUse / PostToolUse / Stop / Notification    │
├──────────────────────────────────────────────────────────┤
│  Layer 1: CLAUDE.md  (컨텍스트 · 지시)                    │
│  자동으로 컨텍스트에 주입되는 프로젝트 규칙서               │
└──────────────────────────────────────────────────────────┘
```

아래에서 아래 레이어부터 위 레이어 순서로 설명한다.

---

## Layer 1 — CLAUDE.md (컨텍스트 레이어)

**역할:** Claude가 프로젝트를 열 때 자동으로 컨텍스트에 주입되는 규칙서.
기술 스택, 아키텍처, 금지 사항, 워크플로우 원칙 등을 정의한다.
명시하지 않으면 Claude는 기본 동작으로 돌아간다.

### 파일 위치 및 적용 범위

| 위치 | 적용 범위 |
|------|-----------|
| `~/.claude/CLAUDE.md` | 내 모든 프로젝트 (글로벌) |
| `{project}/CLAUDE.md` | 해당 프로젝트 전체 |
| `{project}/{subdir}/CLAUDE.md` | 해당 디렉토리 이하만 (계층 상속) |

> **팁:** 모노레포라면 `frontend/CLAUDE.md`, `backend/CLAUDE.md`를 따로 두어 디렉토리별로 다른 규칙을 적용할 수 있다.

### 작성 예시

```markdown
# My Project

## 기술 스택
- 프론트엔드: Next.js 14 (App Router)
- 백엔드: NestJS + PostgreSQL
- 배포: Vercel (FE) / Railway (BE)

## 코딩 원칙
- 컴포넌트는 반드시 TypeScript로 작성
- 함수형 컴포넌트만 사용, class 컴포넌트 금지
- CSS-in-JS 대신 Tailwind CSS 사용

## 금지 사항
- console.log를 커밋에 포함하지 말 것
- any 타입 사용 금지

## 세션 시작 시 자동 실행
1. `cat .claude/progress.txt` — 이전 세션 이어보기
2. `git log --oneline -5` — 최근 작업 확인
```

---

## Layer 2 — settings.json + Hooks (Harness 레이어)

**역할:** Claude의 행동을 자동화하는 설정.
Hook은 Claude가 특정 툴을 사용할 때 **시스템이 자동으로 실행**하는 셸 명령어다.
"매번 파일 저장 후 린트 실행", "세션 종료 전 git status 확인" 같은 자동화가 가능하다.

### 파일 위치

```
~/.claude/settings.json          # 글로벌 설정 (모든 프로젝트)
{project}/.claude/settings.json  # 프로젝트별 설정 (우선순위 높음)
```

### 설정 구조 예시

```json
{
  "permissions": {
    "allow": ["Bash(npm run:*)"],
    "deny":  ["Bash(rm -rf:*)"]
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "echo '[LOG] Bash 명령 실행 시작'"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "npm run lint --silent"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "git status"
          }
        ]
      }
    ]
  }
}
```

### 사용 가능한 Hook 이벤트

| Hook | 실행 시점 | 활용 예시 |
|------|-----------|-----------|
| `PreToolUse` | 툴 실행 직전 | 안전 검사, 위험 명령 차단, 로깅 |
| `PostToolUse` | 툴 실행 직후 | 자동 린트, 포맷팅, 테스트 실행 |
| `Stop` | Claude 응답 완료 후 | 자동 커밋, 진행 기록 저장 |
| `Notification` | Claude 알림 발생 시 | Slack/Teams 알림 전송 |
| `SubagentStop` | 서브에이전트 종료 시 | 서브에이전트 결과 후처리 |

### Harness Engineering이란

Hook을 조합해 Claude의 행동을 자동으로 제어하는 인프라를 구축하는 것.
사람이 매번 확인하지 않아도 품질/안전 규칙이 자동으로 적용된다.

**실전 활용 예:**
- 파일 저장(`Write`) 후 → 자동 린트 + 타입 체크 실행
- 세션 종료(`Stop`) 시 → 진행 기록 파일 자동 업데이트
- 위험한 Bash 명령 실행 전 → 확인 프롬프트 표시

---

## Layer 3 — Skills & Commands (워크플로우 레이어)

**역할:** Claude가 특정 작업을 어떻게 접근할지 정의하는 패턴.
"새 기능을 만들 때는 이 순서대로 해라", "버그를 고칠 때는 이 체크리스트를 따라라"처럼 작업 방식을 표준화한다.

### 3A. Skills (스킬)

```
{project}/.claude/skills/*.md   # 프로젝트 전용 스킬
~/.claude/plugins/              # 외부 플러그인 스킬
  ├── superpowers/              # brainstorming, planning, debugging 등
  ├── feature-dev/              # 기능 개발 워크플로우
  └── frontend-design/          # UI/디자인 작업 가이드
```

**호출:** `Skill tool`을 통해 명시적으로 불러와야 활성화됨 (자동 로드 아님)

**스킬 파일 구조 예시:**

```markdown
---
name: api-endpoint
description: >
  새 API 엔드포인트를 만들 때 사용.
  "라우터 추가", "API 만들어줘" 등의 요청에 사용.
---

## 작업 순서
1. [ ] 기존 유사 엔드포인트 패턴 파악
2. [ ] DTO 및 유효성 검사 정의
3. [ ] 컨트롤러 → 서비스 → 레포지토리 순서로 구현
4. [ ] 단위 테스트 작성
5. [ ] API 문서(Swagger) 업데이트
```

**자주 쓰는 superpowers 스킬:**

| 스킬 | 언제 사용 |
|------|-----------|
| `superpowers:brainstorming` | 새 기능 구상 시작 전 |
| `superpowers:writing-plans` | 코드 작성 전 구현 계획 수립 |
| `superpowers:executing-plans` | 계획을 단계별로 실행할 때 |
| `superpowers:systematic-debugging` | 버그/에러 발생 시 |
| `superpowers:requesting-code-review` | 구현 완료 후 검토 요청 |
| `superpowers:verification-before-completion` | "완료" 선언 전 최종 검증 |
| `superpowers:dispatching-parallel-agents` | 독립 작업을 병렬로 처리할 때 |

### 3B. Commands (슬래시 커맨드)

```
{project}/.claude/commands/*.md   # 프로젝트 커맨드
~/.claude/commands/*.md           # 글로벌 커맨드
```

**호출:** 채팅창에 `/command-name` 입력 → 미리 정의된 프롬프트로 확장됨

> Skills과 차이: Skills는 "어떻게 일할지(how)"를 정의, Commands는 "자주 쓰는 작업 단축키(shortcut)"

**커맨드 파일 예시:**

```markdown
---
description: 새 기능 브랜치 시작 루틴
---

다음 순서로 새 기능 브랜치 작업을 시작합니다:

1. `git pull origin main` — 최신 코드 동기화
2. `git checkout -b feature/{{ 기능명 }}`
3. feature_list.json에서 해당 태스크를 in_progress로 변경
4. 관련 기존 코드 파악 후 구현 시작
```

---

## Layer 4 — Subagent (서브에이전트 레이어)

**역할:** 독립적인 컨텍스트 창에서 특정 작업 하나만 전담 처리.
메인 Claude의 컨텍스트를 오염시키지 않고, 여러 작업을 동시에 실행할 수 있다.

### 작동 방식

```
메인 Claude
  └── Agent tool 호출
        └── 별도 컨텍스트 창 생성
              └── 작업 수행
                    └── 결과만 메인으로 반환
```

### 내장 서브에이전트 타입

| 타입 | 용도 |
|------|------|
| `general-purpose` | 범용 리서치, 복잡한 탐색 작업 |
| `Explore` | 코드베이스 빠른 파악 |
| `Plan` | 구현 계획 설계 |
| `feature-dev:code-explorer` | 기존 기능 심층 분석 |
| `feature-dev:code-architect` | 아키텍처 설계 |
| `feature-dev:code-reviewer` | 코드 리뷰 |

### 핵심 장점

| 항목 | 설명 |
|------|------|
| 독립 컨텍스트 | 서브에이전트 작업이 메인 대화에 영향 없음 |
| 병렬 실행 | 여러 서브에이전트를 동시에 돌릴 수 있음 |
| 결과만 반환 | 긴 탐색 과정은 안 보이고 요약 결과만 수신 |
| Worktree 격리 | `isolation: "worktree"` 옵션으로 git 충돌 방지 |

---

## Layer 5 — Team Agent (팀 에이전트 레이어)

**역할:** 프로젝트 도메인에 특화된 전문가 에이전트를 파일로 정의.
역할, 전문 지식, 사용 가능한 툴을 미리 설정해 어떤 대화에서도 일관된 동작을 보장한다.

### 파일 위치

```
{project}/.claude/agents/
  ├── backend-dev.md     # 백엔드 개발 전담
  ├── db-reviewer.md     # DB 스키마 검토 전담
  └── test-writer.md     # 테스트 작성 전담
```

### 에이전트 파일 구조

```markdown
---
name: backend-dev
description: >
  NestJS 백엔드 개발 전담 에이전트.
  API 엔드포인트, 서비스 로직, DB 연동 작업에 사용.
  "API 만들어줘", "서비스 레이어 추가" 등의 요청에 사용.
tools:
  - Read
  - Write
  - Bash
model: claude-sonnet-4-6
---

## 역할 및 책임
NestJS 기반 RESTful API 개발을 전담합니다.

## 코딩 원칙
- 컨트롤러는 HTTP 처리만, 비즈니스 로직은 서비스에
- 모든 입력값은 DTO + class-validator로 검증
- DB 접근은 반드시 레포지토리 패턴을 통해

## 금지 사항
- 컨트롤러에서 직접 DB 쿼리 금지
- any 타입 사용 금지
```

### Team Agent vs 일반 Subagent 비교

| 항목 | Team Agent | 일반 Subagent |
|------|-----------|---------------|
| 정의 위치 | `.claude/agents/*.md` | 코드 내 `subagent_type` 지정 |
| 도메인 지식 | 프로젝트 특화 규칙 포함 | 범용 |
| 툴 제한 | 파일에서 제어 가능 | 타입별 고정 |
| 재사용성 | 프로젝트 전체에서 일관 적용 | 매번 프롬프트 작성 필요 |

---

## Layer 6 — Orchestration (조율 레이어)

**역할:** 여러 서브에이전트를 병렬로 실행하고 결과를 합치는 패턴.
메인 Claude가 오케스트레이터(지휘자) 역할을 하며, 독립적인 작업들을 동시에 처리해 전체 시간을 단축한다.

### 기본 패턴

```
메인 Claude (오케스트레이터)
    ├── Agent A: 프론트엔드 파일 분석     ─┐
    ├── Agent B: 백엔드 API 목록 파악      ─┤  병렬 실행 (단일 메시지)
    └── Agent C: 테스트 커버리지 확인      ─┘
              ↓
         결과 취합 → 최종 응답
```

### 언제 쓰는가

| 상황 | 접근법 |
|------|--------|
| 작업이 서로 독립적 | 병렬 에이전트 실행 |
| 작업이 순서 의존적 | 순차 실행 |
| 결과를 합쳐야 할 때 | 오케스트레이터가 취합 |
| 코드 수정 충돌 우려 | `isolation: "worktree"` 격리 |

### 실전 예시 — 코드 리뷰 병렬화

```
사용자: "PR #42 전체 리뷰해줘"

오케스트레이터:
  ├── Agent A: 변경된 API 엔드포인트 보안 검토
  ├── Agent B: DB 쿼리 성능 분석
  └── Agent C: 누락된 테스트 케이스 파악

→ 세 가지를 동시에 분석 후 종합 리뷰 리포트 생성
```

### Worktree 격리 예시 — 독립 작업 동시 진행

```
사용자: "인증 모듈이랑 결제 모듈 동시에 리팩토링해줘"

오케스트레이터:
  ├── Agent A (worktree-1): auth 모듈 리팩토링
  └── Agent B (worktree-2): payment 모듈 리팩토링

→ 각자 독립 브랜치에서 작업 → 완료 후 각각 PR 생성
```

---

## 권장 셋팅 순서 (신규 프로젝트 기준)

```
1일차  → CLAUDE.md 작성
         프로젝트 기술 스택, 코딩 원칙, 금지 사항, 세션 루틴 정의

2~3일차 → settings.json 권한 설정
          허용/차단할 Bash 명령어 패턴 정의

1주차  → Commands 작성
         자주 쓰는 작업을 슬래시 커맨드로 등록 (/start, /review 등)

2주차  → Skills 작성
         도메인별 워크플로우 패턴 정의 (기능 개발, 버그 수정, 배포 등)

3주차  → Team Agents 정의
         역할별 전문 에이전트 파일 작성 (백엔드, 프론트, DB, 테스트 등)

4주차  → Hooks 설정 (Harness Engineering)
         자동 린트, 세션 종료 후 커밋 확인, 위험 명령 차단 등

1개월+  → Orchestration 도입
          독립 작업들을 병렬 에이전트로 처리하는 패턴 적용
```

---

## 레이어별 한 줄 요약

| 레이어 | 핵심 역할 | 설정 위치 |
|--------|-----------|-----------|
| 1. CLAUDE.md | Claude에게 프로젝트를 설명하는 규칙서 | `CLAUDE.md` |
| 2. Harness | 자동화 — 툴 실행 전후 동작 정의 | `settings.json` |
| 3. Skills & Commands | 작업 접근 방식 표준화 | `.claude/skills/`, `.claude/commands/` |
| 4. Subagent | 독립 컨텍스트에서 단일 작업 위임 | `Agent tool` |
| 5. Team Agent | 도메인 특화 전문 에이전트 정의 | `.claude/agents/` |
| 6. Orchestration | 다수 에이전트 병렬 조율 | 패턴 (파일 없음) |

---

*Claude Code 공식 문서: https://docs.anthropic.com/claude-code*
