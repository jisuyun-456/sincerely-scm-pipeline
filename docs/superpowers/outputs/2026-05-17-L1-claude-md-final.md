# 최종 L1 CLAUDE.md (2026-05-17 restructure)

**Status:** Applied · git commit (자세한 hash는 commit 시점에 추가)
**File path:** `C:/Users/yjisu/.claude/CLAUDE.md`
**Companion plan:** `C:/Users/yjisu/.claude/plans/strategy-design-duration-4h-robust-squid.md`
**Before/after:** 236줄 → 130줄 (-45%)

---

## 변경 요약

| 항목 | 이전 | 이후 |
|------|------|------|
| 총 줄 수 | 236 | 130 |
| Karpathy 65줄 | 부분 (footer 누락) | GitHub 원본 + closing footer 추가 |
| 모델 라우팅 표 | 유지 | 유지 (`L2 override 허용` 명시) |
| 워크플로우 스킵 매트릭스 | 유지 | 유지 |
| 5단계 워크플로우 설명 | 5줄 bullet | 1줄 압축 (스킬 reference 유지) |
| 공통 데이터 원칙 (3원칙) | 유지 | 유지 |
| 미션 자동 감지 트리거 | 유지 | 유지 |
| Harness 에이전트 14개 표 | enumerate 20줄 | reference 1줄 → `harness/README.md` |
| Notion 6 DB 매핑 | enumerate 8줄 | reference 1줄 → `notion-mapping.yaml` |
| Hook Lifecycle 4-row 표 | enumerate 6줄 | reference 1줄 → `settings.json` + `harness/README.md` 새 섹션 |
| Validator 스코프 표 | enumerate 4줄 | (참조 1줄에 포함) `harness/README.md` |
| 미션 사용법 코드 블록 | 6줄 | reference 1줄 → `commands/*.md` |
| Retro-Learning 동작 | enumerate 6줄 | reference 1줄 → `harness/lessons/` |
| 참조 스킬 | 2줄 | 유지 |

---

## 새 L1 CLAUDE.md 전체 (130줄)

```markdown
# Claude Code 글로벌 지침

## 라우팅 & 모델

### 에이전트 라우팅
프로젝트 `.claude/agents/` 매칭 에이전트로 위임. 없으면 재무/기술/프론트/PM 전문가로 직접 응답.
복수 도메인 → Agent 툴 병렬 호출. 판별 불가 → 사용자에게 질문.

### 모델 선택 (Advisor Strategy)
기본 모델: **Sonnet 4.6** (`settings.json` `"model": "sonnet"` 유지)

| 모델 | 역할 | 사용 상황 |
|------|------|----------|
| `haiku` | Worker | 단순 반복, 파일 조회, 키워드 검색, 포맷/변환, Explore(quick) |
| `sonnet` | Executor (기본) | 코드 구현, 버그 수정, 기능 수정, Explore(medium), 코드 리뷰 |
| `opus` | Advisor | 아키텍처 설계, 심층 분석, **Plan 에이전트**, 다중 도메인, "깊게/정밀하게" |

- Agent 호출 시 표에 따라 `model` 명시 (생략 시 sonnet). **Plan 에이전트는 항상 opus.**
- Explore: quick=haiku, medium=sonnet(기본), thorough=opus
- **L2 override 허용**: 프로젝트 CLAUDE.md는 도메인 깊이 큰 라우팅에 한해 정당화된 1줄 사유 동반으로 override 가능

## 워크플로우

사용자가 명시적으로 생략 요청 시에만 건너뜀.

### 스킵 매트릭스
| 요청 유형 | 1구상 | 2계획 | 3실행 | 4검토 | 5검증 |
|---------|:-----:|:-----:|:-----:|:-----:|:-----:|
| 질문, 설명, 분석 | skip | skip | skip | skip | skip |
| 오타/변수명/1~2줄 수정 | skip | skip | 바로 | skip | skip |
| 버그 수정 | skip | skip | 필수 | 필수 | 필수 |
| 기존 기능 수정/확장 | skip | 필수 | 필수 | 필수 | 필수 |
| 새 기능/아키텍처 (`/brainstorm`) | 필수 | 필수 | 필수 | 필수 | 필수 |

5단계: 1구상(`superpowers:brainstorming`, `/brainstorm` 명시 시) → 2계획(`superpowers:writing-plans` + Validation Contract) → 3실행(`superpowers:executing-plans`) → 4검토(`feature-dev:code-reviewer` + `harness-validator` 병행) → 5검증(`superpowers:verification-before-completion` + Contract 통과 확인).

특수 경로: 버그 → `superpowers:systematic-debugging` / 디자인 → `frontend-design:frontend-design`.

## 미션 모드 (Harness Engineering)

8h~24h 자율 멀티 에이전트 미션은 `/mission <template> --duration <h>` 진입. 단발 작업은 기존 키워드 라우팅(Harness 개입 없음).

### 미션 자동 감지 (2개 이상 해당 시 제안)
- 추정 소요 2h+ 다단계 작업
- 새 파일 3개 이상 생성 예상
- 복수 레이어 동시 작업 (DB+API+UI 등)
- 키워드: "구축", "설계해줘", "시스템", "파이프라인", "대시보드", "API 서버", "자동화"

제안 포맷: `이 작업은 [N]단계, 약 [Xh] 예상입니다. 미션 모드로 진행할까요? → /mission build-X --duration Xh --project <name>`
응답 `ㅇ`/`응`/`yes`/`좋아`/`ㄱㄱ` → 미션 모드, `바로`/`그냥`/`스킵` → 단발 진행.

### 참조 (디테일은 lower layer SSOT)
- Harness 구조·에이전트 14개·진행 흐름·Validator 스코프 → `~/.claude/harness/README.md`
- 미션 명령 (`/mission`·`/checkpoint`·`/lesson`) → `~/.claude/commands/*.md`
- Phase 1 FSM Event Log (`/mission resume/list/abort`) → `~/.claude/harness/event-log-spec.md`
- Notion AgentOps 6 DB 매핑 → `~/.claude/harness/notion-mapping.yaml`
- Retro-Learning 누적 학습 → `~/.claude/harness/lessons/`
- Hook Lifecycle (4 hooks) → `~/.claude/settings.json` + `~/.claude/harness/README.md`

## 언어 설정
**Always respond in English**, regardless of the language the user writes in.

## 공통 데이터 원칙
- **Immutable Ledger**: 금융·재고·거래 데이터 INSERT ONLY, 정정은 역분개(Storno)/보정 레코드. UPDATE/DELETE 절대 금지
- **Risk-First**: 모든 제안에 리스크/부작용 먼저 명시. 세무·법률은 법령 근거 없이 결론 금지
- **Data > Opinion**: 주장에는 데이터·출처 명시. 근거 없는 KPI 목표치·수익률 예측 금지

## Coding Principles (Karpathy)

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding
**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First
**Minimum code that solves the problem. Nothing speculative.**
- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes
**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution
**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
\`\`\`
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
\`\`\`

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## 참조 스킬 (자동 호출)

- **`obsidian-routing`** — Obsidian Vault 검색·저장·세션 연속성·LightRAG 라우팅 (Vault·SCM·STOCK 작업 시 자동)
- **`agent-template`** — `.claude/agents/*.md` 신규 작성 표준 구조
```

---

## Verification (적용 직후 grep 결과)

| 검증 | 기준 | 결과 |
|------|------|------|
| 총 줄 수 | ≤ 130 | **130** ✅ |
| [A] 결정 규칙 키워드 (haiku/sonnet/opus/스킵 매트릭스/Immutable Ledger/미션 자동 감지/Karpathy) | ≥ 7 | **10** ✅ |
| Karpathy closing footer 존재 | 1 매치 | ✅ |
| [B] enumerate 부재 — Notion 6 DB | 0 매치 | **0** ✅ |
| [B] enumerate 부재 — Hook 4-row 표 | 0 매치 | **0** ✅ |
| [B] enumerate 부재 — Core 9 + Specialized 5 표 | 0 매치 | **0** ✅ |

---

## Related changes (동일 commit)

1. `~/.claude/harness/README.md` — Hook Lifecycle 섹션 추가 (~15줄)
2. `SCM_WORK/.claude/feature_list.json` — AUDIT-L1-HOOK-01 + AUDIT-L1-GAP-01에 `superseded_by` + `note` 메모 추가

## Rollback

`git revert <commit-sha>` 단일 명령 (3 파일 + 2 산출물 atomic commit).
