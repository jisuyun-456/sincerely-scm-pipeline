# 6-Layer MECE Audit — Findings Report

**Date:** 2026-05-16
**Spec:** `docs/superpowers/specs/2026-05-16-6-layer-audit-design.md`
**Method:** 3 parallel Explore agents × 6 layers × 7 dimensions
**Total findings:** 63 raw → 52 unique (after cross-layer dedup)

---

## Executive Summary

| Severity | Count | 즉시 fix 가능? |
|----------|-------|---------------|
| **P0** | 2 | ✅ 이번 세션 |
| **P1** | 24 | 일부 (5건 docs 갱신), 나머지 후속 미션 |
| **P2** | 26 (10 backlog 등재 + 16 informational) | low priority |
| **합계** | 52 unique findings | |

**Biggest gap (oh-my-claudecode 비교):** Hook coverage — 4 hooks × 4 events vs 그쪽 20 hooks × 11 events. P1 hooks 3건 추가 권고 (PreToolUse / SubagentStop / PreCompact).

**Phase 1 drift:** 이번 Phase 2가 가장 많이 발견한 카테고리는 **CrossLayer**(7건) 와 **Gap**(7건). Phase 1 FSM 도입 후 L1·L2 docs가 미반영 상태.

---

## Findings Matrix (6 × 7 = 42 cells)

각 셀: `P0+P1 / [P2]`. `·` = 0건.

| | **Drift** | **Overlap** | **Gap** | **Staleness** | **CrossLayer** | **Karpathy** | **HookCoverage** |
|---|---|---|---|---|---|---|---|
| **L1** | · / [1] | · / · | 1 / · | 1 / · | · / · | · / [1] | 1 / · |
| **L2** | 1 / [1] | 1 / · | 2 / [2] | · / [1] | 1 / · | · / [1] | 1 / · |
| **L3** | 1 / · | · / · | 1 / [1] | · / [1] | 1 / · | 1 / · | · / · |
| **L4** | 2 / · | 3 / · | · / [1] | · / [2] | 5 / · | · / [3] | · / · |
| **L5** | 1 / · | · / [1] | 2 / [2] | · / [1] | · / · | 1 / · | 1 / · |
| **L6** | · / [1] | · / · | 1 / [2] | · / [1] | · / · | · / · | · / · |
| **합계** | 5 / [3] | 4 / [1] | 7 / [8] | 1 / [6] | 7 / · | 2 / [5] | 3 / · |

**MECE 검증:** unique 52 (raw 63 - cross-layer dedup 11)

---

## Cross-Layer Conflicts (11건, X1~X11)

여러 layer에 동시 영향 — 단일 backlog 항목으로 통합:

### X1 — Phase 1 FSM 미반영 (P1, L1·L2)
- **Evidence:** L1 (line 191) "참조 섹션"이 `event-log-spec.md` 미언급. `/mission resume/list/abort` 새 subcommand 미선언. L2 (line 46) "Harness 미개입" 진술이 Phase 1 event-log 기록 시작 후 부정확.
- **Recommendation:** L1·L2 모두 갱신 — Phase 1 섹션 추가, Known Limitations 동기화.

### X2 — `/learn` 슬래시 커맨드 부재 (P1, L2·L6)
- **Evidence:** L2 라우팅 table (line 81) `| 실수 기록, learn | /learn |`. L2 line 106 "반복 실수 발생 시 `/learn`". 실제 commands/ 에는 `/lesson`만 존재.
- **Recommendation:** L2 두 곳 `/learn` → `/lesson` 교체.

### X3 — Event Log Discipline 5 agents 누락 (P1, L4·L3)
- **Evidence:** Phase 1에서 9 agents에 추가됨. 누락 5개: notion-sync, workflow-architect, reality-checker, codebase-onboarding-engineer, evidence-collector.
- **Recommendation:** 
  - notion-sync, workflow-architect, reality-checker, codebase-onboarding-engineer: Event Log Discipline 섹션 추가
  - evidence-collector: build-dashboard 전용 narrow scope이므로 의도적 제외 사유 명시

### X4 — `runtime.snapshot` 카탈로그 불일치 (P1, L3)
- **Evidence:** `event_log.py` VALID_TYPES (line 42)에 `runtime.snapshot` 있음 (linter 추가). `event-log-spec.md` 카탈로그 표 (lines 64-93)에 없음.
- **Recommendation:** spec 카탈로그에 `runtime.snapshot` 행 추가 (phase=Runtime, no lock, terminal=no, cardinality=0..∞) 또는 VALID_TYPES에서 제거.

### X5 — Notion event_* 매핑 emit 미구현 (P1, L3·L4)
- **Evidence:** 6 신규 매핑 (event_mission_resumed, event_runtime_capability_missing, event_runtime_cost_halted, event_sprint_rolled_back, event_lesson_approved, event_mission_aborted)이 notion-mapping.yaml에 선언됨. 그러나 어떤 코드 path도 이 type들을 emit하지 않음.
- **Recommendation:** orchestrator/checkpoint-reporter agent .md에 해당 lifecycle 시점에 emit() 호출 추가.

### X6 — Model preference 불일치 (P1, L1·L2·L4)
- **Evidence:** L1 model strategy = sonnet 기본 (executor). L2 routing이 opus 다수 할당 (SK-06 tms-otif-kpi, D-TMS1~2, D1~D3 = opus). L4 agent frontmatter는 일부 모델 미명시.
- **Recommendation:** L1·L2에 "L1 = 기본값, L2 = 도메인 정당화된 override" 패턴 명시. opus 할당 사유를 L2 routing table 옆에 1줄 justification 추가.

### X7 — Agent routing keyword 충돌 (P1, L2·L4) — 4 pair
- **Evidence:**
  1. SK-06 tms-otif-kpi vs D-TMS1 tms-improvement on "Gap 분석"
  2. D-TMS1 tms-improvement vs D3 consulting-pm-expert on "Issue Tree, MECE, Pyramid"
  3. SK-09 tms-cost-lane vs D1 scm-logistics-expert on "lane, 거점"
  4. SK-08 meeting-analysis vs harness meeting-coordinator on "회의록"
- **Recommendation:** L2 "분기 충돌 시" 섹션 확장 — 4 pair 각각 분리 기준 명시.

### X8 — strategy-design.yaml 미존재 에이전트 참조 (P0, L3·L4)
- **Evidence:** `~/.claude/harness/missions/strategy-design.yaml` line 18 `primary_worker: consulting-pm-expert`, secondary_workers: [scm-logistics-expert, tax-accounting-expert]. 이 3 에이전트는 SCM_WORK 프로젝트에만 존재 (`SCM_WORK/.claude/agents/`), 글로벌 `~/.claude/agents/` 에는 없음.
- **Impact:** 다른 프로젝트에서 `/mission strategy-design` 시도 시 dispatch 실패.
- **Recommendation:** (a) 글로벌에 stub 에이전트 추가, 또는 (b) mission template에 `project_specific: scm` 플래그 추가하여 project-conditional dispatch.

### X9 — PostToolUse 훅 선언/구현 불일치 (P1, L2·L5)
- **Evidence:** L2 (line 32) "회의록 백업 | PostToolUse 훅 → Obsidian Vault + Slack 공유폴더" 선언. 실제 settings.json PostToolUse 훅은 Python syntax check만 수행.
- **Recommendation:** L2 진술을 실제 구현과 일치시키기 (현재 "회의록 백업" 기능 미구현 명시) 또는 실제 회의록 백업 훅 구현.

### X10 — L1-L2 언어 정책 중복 (P2, L1·L2)
- **Evidence:** L1 line 59 + L2 line 40 모두 "Always respond in English" 명시. 어느 층이 "주" 지시인지 불명, 회의록 등 한국어 예외 정책 미기술.
- **Recommendation:** L2에서 "L1 상속" 으로 명시, 회의록·특정 산출물에 한한 한국어 예외 정책 추가.

### X11 — Hook 커버리지 8 lifecycle 누락 (P1, L5·L1)
- **Evidence:** 현재 4 훅 (Stop, Notification, PostToolUse, SessionStart). 누락 8개 (oh-my-claudecode 기준): PreToolUse, SubagentStop, PreCompact, UserPromptSubmit, SessionEnd, PermissionRequest, PostToolUseFailure, SubagentStart.
- **Recommendation (Karpathy lens, 가치 순):**
  - **X11-A** `PreToolUse` → git-guardrails (push --force, reset --hard, branch -D 차단). 별도 brainstorm 진입.
  - **X11-B** `SubagentStop` → Worker 종료 시 자동 `worker.completed` emit.
  - **X11-C** `PreCompact` → context compression 전 mission state snapshot.
  - 나머지 5 (UserPromptSubmit, SessionEnd, PermissionRequest, PostToolUseFailure, SubagentStart): YAGNI — 실제 필요 시점에 추가.

---

## Per-Layer Findings 상세

### L1 — Global CLAUDE.md (6 findings)

| Dim | Severity | Line | Evidence | Recommendation |
|-----|----------|------|----------|----------------|
| Staleness | P1 | 191 | 참조 섹션이 Harness README 언급하지만 Phase 1 신규 자산(event-log-spec.md, /mission resume) 미언급 | Phase 1 섹션 추가 |
| Gap | P1 | 109 | `mission.md, checkpoint.md, lesson.md` 3 파일만 명시. resume/list/abort 미선언 | mission.md 서브커맨드 명시 |
| Gap | P2 | 104 | "프레임워크 + 에이전트" 만 언급, event-sourced FSM 미언급 | "event-sourced FSM (events.jsonl)" 추가 |
| Karpathy | P2 | 161 | Notion 6 DB 추상적 ("notion-mapping.yaml" 참조) | 6 DB 인라인 enumerate |
| HookCoverage | P1 | null | L1에 Hook 관련 내용 전무. settings.json 4 hooks 실재하나 미언급 | "Hook Lifecycle" 섹션 신설 |
| Drift | P2 | 196 | obsidian-routing 스킬 참조 시 ClaudeVault 경로 미기술 | ClaudeVault 절대경로 명시 |

### L2 — SCM_WORK CLAUDE.md (12 findings)

| Dim | Severity | Line | Evidence | Recommendation |
|-----|----------|------|----------|----------------|
| Drift | P0 | 36 | `메모리 project_scm_redesign 참조` 맥락 불명확 | "(프로젝트 메모리 및 회의 로그 참조)"로 명확화 |
| Gap | P1 | 88 | `feature_list.json` 참조하지만 관리 프로세스(언제/누가 갱신) 미기술 | 관리 섹션 추가 |
| Gap | P2 | 46 | Harness Worker wrapping 프로세스 미기술 | 예시 추가 |
| Overlap | P1 | 83 | "분기 충돌 시" 섹션 4 pair 부족 | SK-06/D-TMS1, D-TMS1/D3, SK-09/D1, SK-08/MC 분리 기준 |
| CrossLayer | P1 | 40 | L1과 동일 "Always respond in English" 중복 | L1 상속 명시 |
| Staleness | P2 | 35 | Supabase 정책 (2026-05-08) 진행 상태 미명시 | "현황: 운영 중" 추가 |
| Gap | P1 | 90 | Contract 포맷·과거 Contract 위치 미기술 | `~/.claude/harness/contracts/template.md` 링크 |
| Karpathy | P2 | 98 | 금지 표현 명시되나 대안 표현 미제시 | 승인된 표현 예시 추가 |
| HookCoverage | P1 | 32 | "PostToolUse 훅 → Obsidian/Slack 회의록" 선언이 실제 구현(py syntax check만)과 불일치 | 실제 구현과 일치시키기 |
| Gap | P2 | 62 | SK-08 회의록 형식·저장 위치·트리거 미기술 | SK-08 운영 가이드 추가 |
| Drift | P1 | 11 | ClaudeVault 절대 경로 미제시 | 첫 장에 경로 명시 |
| Staleness | P2 | 46 | "Harness 미개입" 진술이 Phase 1 event-log 도입 후 부정확 | 진술 갱신 |

### L3 — Universal Project Harness (9 findings)

| Dim | Severity | File | Evidence | Recommendation |
|-----|----------|------|----------|----------------|
| Drift | P0/P1 | strategy-design.yaml:18 | consulting-pm-expert / scm-logistics-expert / tax-accounting-expert 글로벌 미존재 (X8) | stub 또는 project-conditional |
| Gap | P1 | event-log-spec.md | `runtime.snapshot` catalog 누락 (X4) | catalog 추가 |
| Karpathy | P1 | build-dashboard.yaml:70 | evidence-collector hard-code | skip matrix로 일반화 |
| CrossLayer | P1 | sprint-config.yaml:5 | 4h default vs strategy-design 2h sprint | per-mission override 필드 추가 |
| Gap | P2 | notion-mapping.yaml:259 | 6 event_* 매핑 (X5) emit 코드 path 부재 | emit() 호출 추가 |
| Staleness | P2 | lessons/global.md | 1일 전 4건, 모두 confidence=1 (healthy) | 모니터만, action 없음 |
| Gap | P1 | README.md:256 | "Phase 2" 디퍼럴 항목이 이번 작업으로 해소 | README 갱신 |
| Karpathy | P2 | build-dashboard.yaml:45 | Sprint 2/3 must_not 별도 보안 검사 | 직교 — no action |
| CrossLayer | P2 | lessons/global.md:20 | H4 check가 mission contracts에 실제 추가됐는지 검증 필요 | template에 H4 line 추가 |

### L4 — Agents (21 findings)

**Drift (2 P0/P1):**
- AUDIT-L4-DRIFT-01 **(P0)** `meeting-analysis.md` model: `claude-sonnet-4-6` (invalid) → `sonnet`
- L4 Drift #2 (P1) `tms-shipment.md` 의 `mcp__scm_airtable__tms_update_shipment` 가용성 검증

**Overlap (3 P1):**
- SK-06 vs D-TMS1, D-TMS1 vs D3, SK-09 vs D1, SK-08 vs meeting-coordinator — X7로 통합

**CrossLayer (5 P1):**
- notion-sync, workflow-architect, reality-checker, codebase-onboarding-engineer Event Log Discipline 누락 (X3)
- evidence-collector 의도적 제외 사유 명시 필요 (X3-EC)

**Karpathy (3 P2):**
- meeting-coordinator 334줄 (3 책임 분리 검토)
- workflow-architect 334줄
- checkpoint-reporter 306줄

**Staleness (2 P2):**
- wms-return / wms-inventory 12일+ 미수정, 작은 파일

**Gap (1 P2):**
- wms-master-data 에이전트 vs scm-airtable-pattern 스킬 경계 명시

### L5 — Hooks / settings.json (9 findings)

**HookCoverage (1 P1) — X11:**
- 8 lifecycle 누락 (X11-A/B/C 가치 순)

**Drift (1 P1):**
- Stop 훅 Supabase POST env var 미설정 시 silent skip — 의도 주석 또는 제거

**Gap (2 P1, 2 P2):**
- PostToolUse `Edit|Write`만 → Bash/JSON/YAML 추가 검토
- SessionStart 30일 stale memory check은 warn만 (P2)
- CLAUDE_SESSION_ID 일관성 (P2)

**Karpathy (1 P1):**
- PreToolUse 훅 부재 → git-guardrails 적용 가치 큼 (X11-A)

**Staleness (1 P2):**
- Notification beep Windows-only

**Overlap (1 P2 — acceptable):**
- Notification (beep) vs SessionStart (text) → 직교, no action

### L6 — Skills + Slash Commands (6 findings)

| Dim | Severity | Evidence | Recommendation |
|-----|----------|----------|----------------|
| Gap | P1 | `/learn` 부재 (X2) | `/lesson`으로 교체 |
| Drift | P2 | obsidian-routing ClaudeVault 경로 명시 (X10 연관) | 경로 검증 |
| Staleness | P2 | superpowers skills 30일 사용 빈도 미확인 | 사용 audit |
| Gap | P2 | Plugin vs agent 구분 모호 | 글로벌 docs 명시 |
| Drift | P2 | settings.json 비활성 plugins (playground 등) | no action (참조 없음) |
| Gap | P2 | security-review 슬래시 커맨드 미사용 | "not applicable to SCM_WORK" 명시 또는 사용 |

---

## Backlog Summary

총 36건 등재 → `.claude/feature_list.json` append.

| Severity | Count | 분류 |
|----------|-------|------|
| **P0** | 2 | drift fix (1줄 + harness) |
| **P1** | 24 | docs 8 / agents 7 / harness 4 / hooks 3 / 기타 2 |
| **P2** | 10 (backlog) | Karpathy 3 / staleness 4 / gap 3 |

상세 항목은 `.claude/feature_list.json` 직접 조회.

---

## Next Actions (Phase 2.5+)

1. **이번 세션 즉시 fix** (≤ 30분):
   - AUDIT-L4-DRIFT-01 (1줄 fix)
   - AUDIT-X8 (strategy-design.yaml project-conditional 또는 stub)
2. **Next session (단발 작업)**:
   - P1 docs 5건 (X1, X2, X9, X10, X6) — L1·L2 갱신
   - P1 agents 5건 (X3) — Event Log Discipline 5 agents
3. **별도 brainstorm**: AUDIT-X11-A (PreToolUse / git-guardrails)
4. **후속 미션**: P1 harness 4건 + P1 hooks 2건 (X11-B/C)
5. **Low priority**: P2 backlog (Karpathy cleanup 등)

## References

- Audit spec: `docs/superpowers/specs/2026-05-16-6-layer-audit-design.md`
- Phase 1 design: `~/.claude/plans/silly-giggling-fiddle.md`
- Yeachan Heo "Harness Engineering" 인스타 분석 (Phase 1 brainstorm 참조)
- oh-my-claudecode: https://github.com/Yeachan-Heo/oh-my-claudecode
