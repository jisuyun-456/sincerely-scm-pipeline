# 6-Layer 최종 정리 (L1 restructure 2026-05-17 반영)

**Status:** Applied (post L1 restructure)
**Companion docs:**
- Phase 2 6-Layer audit design: `docs/superpowers/specs/2026-05-16-6-layer-audit-design.md`
- Phase 2 6-Layer audit findings: `docs/superpowers/outputs/2026-05-16-6-layer-audit-report.md`
- L1 restructure plan: `~/.claude/plans/strategy-design-duration-4h-robust-squid.md`
- L1 산출물: `docs/superpowers/outputs/2026-05-17-L1-claude-md-final.md`

---

## 6-Layer 최종 구조

| L | Layer | 경로 | 크기 (2026-05-17) | 본 restructure 영향 |
|---|-------|------|-------------------|---------------------|
| **L1** | Global CLAUDE.md | `~/.claude/CLAUDE.md` | **130줄** (이전 236) | **rewrite** (Hybrid 구조) |
| **L2** | Project CLAUDE.md | `SCM_WORK/CLAUDE.md` | ~150줄 | 변경 없음 |
| **L3** | Universal Project Harness | `~/.claude/harness/` | README.md 280줄 + spec/yaml | **Hook Lifecycle 섹션 추가** (~15줄) |
| **L4** | Agents | `~/.claude/agents/` (글로벌 14) + `SCM_WORK/.claude/agents/` (14) = **28** | 각 50~150줄 | 변경 없음 |
| **L5** | Hooks | `~/.claude/settings.json` | 4 hooks × 4 events | 변경 없음 |
| **L6** | Skills + slash commands | system available-skills (~35) + `~/.claude/commands/` (3) + `~/.claude/skills/` (9) | metadata only | 변경 없음 |

---

## L1 신구조 (Hybrid)

새 L1 = **[A] 매 세션 결정 규칙** + **[B] 디테일은 lower layer 1줄 reference**.

| 섹션 | 줄 수 | 내용 |
|------|-------|------|
| 1. 라우팅 & 모델 | ~20 | 에이전트 라우팅 + 모델 표 + L2 override 허용 |
| 2. 워크플로우 | ~13 | 스킵 매트릭스 + 5단계 1줄 압축 + 특수 경로 |
| 3. 미션 모드 | ~17 | 미션 자동 감지 트리거 + lower layer 6 reference |
| 4. 언어 설정 | 1 | "Always respond in English" |
| 5. 공통 데이터 원칙 | ~5 | Immutable Ledger / Risk-First / Data > Opinion |
| 6. Coding Principles (Karpathy) | **65** | GitHub 원본 4원칙 + closing footer |
| 7. 참조 스킬 | ~3 | obsidian-routing, agent-template |
| (빈 줄 + 구분선) | ~6 | — |
| **총** | **~130** | — |

---

## 6-Layer audit findings 보존 매트릭스 (19/19)

| Audit ID | 도메인 | 현재 상태 | L1 restructure 영향 |
|----------|--------|----------|---------------------|
| AUDIT-X1 | global | done | Phase 1 FSM reference 1줄 L1 유지 ✅ |
| AUDIT-X2 | scm | done | L2 변경 없음 ✅ |
| AUDIT-X3-NOTION | harness | done | notion-sync.md 변경 없음 ✅ |
| AUDIT-X3-WFA | harness | done | workflow-architect.md 변경 없음 ✅ |
| AUDIT-X3-RC | harness | done | reality-checker.md 변경 없음 ✅ |
| AUDIT-X3-COE | harness | done | codebase-onboarding-engineer.md 변경 없음 ✅ |
| AUDIT-X3-EC | harness | done | evidence-collector.md 변경 없음 ✅ |
| AUDIT-X4 | harness | done | event-log-spec.md 변경 없음 ✅ |
| AUDIT-X5 | harness | done | notion-mapping.yaml emit() 변경 없음 ✅ |
| AUDIT-X6 | global | done | 모델 표 + L2 override 1줄 L1 유지 ✅ |
| AUDIT-X7 | scm | done | L2 변경 없음 ✅ |
| AUDIT-X8 | harness | done | strategy-design.yaml 변경 없음 ✅ |
| AUDIT-X9 | scm | done | L2 변경 없음 ✅ |
| AUDIT-X10 | global | done | "Always respond in English" L1 유지 ✅ |
| AUDIT-X11-A | hooks | done | settings.json git-guardrails 변경 없음 ✅ |
| AUDIT-X11-B | hooks | done | SubagentStop 훅 변경 없음 ✅ |
| AUDIT-X11-C | hooks | done | PreCompact 훅 변경 없음 ✅ |
| **AUDIT-L1-HOOK-01** | global | **done + superseded** | enumerate → reference 1줄, harness/README.md SSOT ⚠️→✅ |
| **AUDIT-L1-GAP-01** | global | **done + superseded** | 6 DB enumerate → reference 1줄, notion-mapping.yaml SSOT ⚠️→✅ |

**보존 결과**: 19/19 audit findings 모두 추적 가능. HOOK-01 / GAP-01 두 건은 의식적 supersede (L1-restructure-2026-05-17).

---

## Layer 간 의존성 확인 (L1 변경 후)

| 의존 방향 | 검증 결과 |
|----------|----------|
| L2 → L1 직접 reference | L2가 L1을 직접 reference하지 않음 (L2는 `~/.claude/harness/` 디렉토리만 참조). 깨질 link 0건 ✅ |
| L3 → L1 reference | `harness/README.md` line 263에 `~/.claude/CLAUDE.md` 참조 1줄, 새 L1에도 동일 유효 ✅ |
| L4 (Agents) → L1 reference | 14 글로벌 agent frontmatter에서 L1 직접 reference 없음 (각 agent description self-contained) ✅ |
| L5 → L1 reference | `settings.json`은 L1 무관 (JSON hook config) ✅ |
| L6 → L1 reference | skills/commands는 system available-skills에서 자동 로드, L1 reference 없음 ✅ |

**결론**: L1 변경이 L2~L6에 미친 영향 = **0건**. 다른 5 layer는 변경 없이 그대로 동작.

---

## L3 추가 항목 (harness/README.md)

새로 추가된 `Hook Lifecycle (settings.json SSOT)` 섹션:

```markdown
## Hook Lifecycle (settings.json SSOT)

Phase 2 audit 2026-05-16 기준 활성 훅 4개. 실제 정의는 `~/.claude/settings.json` (SSOT).

| 이벤트 | 동작 | matcher |
|--------|------|---------|
| `SessionStart` | 30일+ 묵은 project memory + SCM/STOCK AutoResearch log 최근 3개 표시 | — |
| `PostToolUse` | `.py` 파일 syntax check (py_compile) | Edit\|Write |
| `Stop` | git status + uncommitted 경고 + 선택적 Supabase agent_events POST (env vars 미설정 시 silent skip) | — |
| `Notification` | Windows PowerShell beep (800Hz 300ms) | — |

향후 추가 후보 (AUDIT-X11 — 별도 brainstorm/미션 필요):
- `PreToolUse` (git-guardrails — push --force/reset --hard/branch -D 차단)
- `SubagentStop` (자동 worker.completed 이벤트 emit)
- `PreCompact` (context compression 전 mission state snapshot)

oh-my-claudecode와 비교 시 11 lifecycle events 중 8건 미구현 (Phase 2 audit X11 reference). 운영 차단 아님 — 필요 시점에 추가.
```

---

## 검증 결과 (L1 restructure 직후 grep)

| Check | Target | Result | Status |
|-------|--------|--------|--------|
| 새 L1 줄 수 | ≤ 130 | 130 | ✅ |
| [A] 결정 규칙 키워드 빈도 | ≥ 7 | 10 | ✅ |
| Karpathy closing footer | 1 매치 | 1 매치 | ✅ |
| Notion 6 DB enumerate | 0 매치 | 0 | ✅ |
| Hook Lifecycle 4-row 표 enumerate | 0 매치 | 0 | ✅ |
| Core 9 + Specialized 5 표 enumerate | 0 매치 | 0 | ✅ |
| `harness/README.md` Hook Lifecycle 섹션 | 1 매치 | 1 매치 | ✅ |
| `feature_list.json` JSON parse | OK | OK | ✅ |
| AUDIT-L1-HOOK-01 supersede 메모 | 존재 | 존재 | ✅ |
| AUDIT-L1-GAP-01 supersede 메모 | 존재 | 존재 | ✅ |

---

## Rollback

`git revert <commit-sha>` 단일 명령. 변경 5 파일 (CLAUDE.md, harness/README.md, feature_list.json + 2 산출물) atomic commit.

---

## Sign-off

- ✅ L1 = Karpathy 65줄 GitHub 원본 + closing footer + [A] 결정 규칙 minimal
- ✅ [B] 디테일 모두 lower layer SSOT 이동, MECE 중복 0
- ✅ 19/19 6-Layer audit findings 보존 (HOOK-01 / GAP-01 의식적 supersede 명시)
- ✅ L2~L6에 영향 0건 (L1 단독 변경 + L3 Hook 섹션 추가만)
- ✅ Rollback 단일 명령 가능
