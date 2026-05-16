# 6-Layer MECE Audit — Design

**Date:** 2026-05-16
**Origin:** Phase 1 FSM 완료 후 사용자 요청 — Yeachan Heo "Harness Engineering" 분석 → Phase 2 "L1~L6 전체 stack MECE 감사"
**Phase:** 2 of harness-engineering upgrade roadmap
**Status:** Audit completed (this spec) — backlog items become individual missions
**Companion outputs:**
- `docs/superpowers/outputs/2026-05-16-6-layer-audit-report.md` (findings matrix + cross-layer)
- `.claude/feature_list.json` (P0/P1/P2 backlog 36건 append)

## Context

Phase 1에서 미션 상태 implicit 라는 단일 큰 갭을 해소. Phase 2는 *전체 stack의 MECE 자가검증* — drift/overlap/gap/staleness/cross-layer/Karpathy/hook 7 dimensions × 6 layers = 42 cells.

**Why now:** Phase 1 FSM 도입 후 docs/agents가 최신 상태와 sync 안 됨 → drift 누적 전 점검 필요. 또한 oh-my-claudecode가 20 hooks × 11 lifecycle events vs 우리 4 hooks × 4 events → 객관적 비교 reference 확보됨.

**Non-goal:** 실제 fix 실행은 본 audit scope 외 — P0/P1/P2 backlog로 분리 후 후속 미션/단발 작업으로 처리.

## Methodology

### 6 Layers (감사 대상)

| L | Layer | 위치 | 자산 |
|---|-------|------|------|
| L1 | Global CLAUDE.md | `~/.claude/CLAUDE.md` | ~200줄 |
| L2 | Project CLAUDE.md | `SCM_WORK/CLAUDE.md` | ~140줄 |
| L3 | Universal Project Harness | `~/.claude/harness/` | Phase 1 직후 |
| L4 | Agents | 글로벌 14 + SCM_WORK 14 = 28 | `.md` 명세 |
| L5 | Hooks | `~/.claude/settings.json` | 4 entries |
| L6 | Skills + slash commands | system available-skills | ~35 |

### 7 Dimensions (각 layer에 적용)

| Dim | 검사 항목 |
|-----|----------|
| **Drift** | 파일/경로/에이전트 참조 → 실재 검증 |
| **Overlap** | 두 에이전트·스킬이 같은 트리거 키워드에 match (MECE 위반) |
| **Gap** | 선언된 기능이 미구현, 또는 그 반대 |
| **Staleness** | 3개월 이상 미수정 + deprecated feature 참조 |
| **Cross-layer inconsistency** | L_i가 X 선언, L_j가 ¬X 구현 |
| **Karpathy violation** | over-abstraction, dead code/agent, premature feature |
| **Hook coverage** | lifecycle events 누락 (vs oh-my-claudecode 11 events) |

### Dispatch Pattern

3 parallel Explore agents (`subagent_type="Explore"`), 각자 2 layers 담당. 메인 세션이 결과를 6×7 매트릭스로 synthesize.

```
[Main session]
    ├─ Agent A: L1 + L2  (docs)
    ├─ Agent B: L3 + L5  (infrastructure)
    └─ Agent C: L4 + L6  (executable units)
        ↓
[Main session] synthesis matrix + cross-layer dedup + backlog generation
```

총 wall-clock: ~30분 (3 agents 병렬 + synthesis).

### Severity Classification

- **P0** = 운영 차단, 보안 리스크, 데이터 무결성 위협
- **P1** = MECE 위반, cross-layer 불일치, 사용가능 capability missing
- **P2** = staleness, cosmetic, "있으면 좋음"

### Backlog Schema

`.claude/feature_list.json`의 기존 항목 스키마 유지 + 신규 source 필드 추가:

```json
{
  "id": "AUDIT-L<i>-<DIM>-<seq>",
  "title": "<short action>",
  "priority": "critical | high | medium | low",
  "domain": "global | scm | harness | hooks | skills",
  "status": "pending",
  "source": "6-layer-audit-2026-05-16",
  "finding_severity": "P0 | P1 | P2",
  "finding_dimension": "Drift | Overlap | Gap | Staleness | CrossLayer | Karpathy | HookCoverage",
  "updated_at": "2026-05-16"
}
```

Cross-layer 충돌은 `AUDIT-X<n>` ID로 별도 prefix.

## Architecture (감사 자체 + 후속 액션 흐름)

```
Phase 2: Audit (this work — 2026-05-16)
   ├─ 3 parallel Explore agents
   ├─ 6×7 matrix synthesis
   ├─ Cross-layer dedup (raw 63 → unique 52)
   └─ P0/P1/P2 backlog generation
        ↓
Phase 2.5: Immediate P0 fixes (이번 세션, ≤30분 work)
   ├─ AUDIT-L4-DRIFT-01: meeting-analysis.md model name 1줄 fix
   └─ AUDIT-X8: strategy-design.yaml missing agents — project-conditional 또는 stub
        ↓
Phase 3+: Individual missions / 단발 fix (별도 세션)
   ├─ P1 docs 갱신 (단발, ~5 항목)
   ├─ P1 agents Event Log Discipline (단발, 5 agents)
   ├─ P1 harness 보완 (단발, 4 항목)
   ├─ AUDIT-X11-A: PreToolUse 훅 — 별도 brainstorm (git-guardrails)
   └─ P2 cleanup (low priority, 후속)
```

## Acceptance Criteria

Audit 자체가 "완료"되려면:

1. ✅ 3 Explore agents 모두 응답, findings ≥ 5/layer (실제 6/12/9/21/9/6)
2. ✅ 매트릭스 42 cells 모두 표시 (`·` 또는 숫자)
3. ✅ Cross-layer 충돌 섹션 ≥ 1건 (실제: 11건 X1~X11)
4. ✅ 모든 backlog 항목 evidence + recommendation 동반
5. ✅ `.claude/feature_list.json` 신규 항목 schema 일치
6. ✅ MECE 자가검증 — raw 63 → unique 52 (dedup 11)
7. ✅ 3 산출 파일 생성 (spec/report/backlog)
8. ✅ P0 2건 이번 세션 즉시 fix
9. ✅ AutoResearch log 갱신 + git commit

## Reuse from Phase 1

- `~/.claude/harness/scripts/event_log.py` — 본 audit에서 *읽기만* (코드 path 검증)
- `~/.claude/harness/event-log-spec.md` — audit dimension "Drift" 검증의 기준
- `.claude/feature_list.json` — 기존 schema 그대로 사용, source 필드만 추가
- `_AutoResearch/SCM/wiki/log.md` — Phase 1 entry 패턴 따라 audit 완료 기록

## Out of Scope (YAGNI — 별도 후속)

| 제외 | 이유 |
|------|------|
| 실제 P1/P2 fix 실행 | 본 audit은 진단만, 처방은 후속 미션 |
| oh-my-claudecode plugin 풀 도입 | 기존 자산 보존 우선, 비교 reference만 |
| `~/.claude/projects/*/memory/*` audit | auto-memory 자동 관리 영역 |
| LightRAG·Notion 무결성 검증 | 별도 시스템, 본 audit 외 |
| 글로벌-프로젝트 CLAUDE.md 의도된 중복 | 자급자족 디자인 결정 |
| Notion AgentOps 대시보드 데이터 검증 | 별도 노션 sync 무결성 audit 필요 시 처리 |

## Verification (audit 자체 검증)

1. `git log --oneline -1` 본 audit commit 표시
2. `python -c "import json; d=json.load(open('.claude/feature_list.json')); print(len(d['tasks']))"` → 48+ 확인
3. P0 fix 후: `grep "model:" SCM_WORK/.claude/agents/meeting-analysis.md` → `model: sonnet`
4. P0 #2 fix 후: `~/.claude/harness/missions/strategy-design.yaml` project-conditional 또는 stub 추가
5. 매트릭스 cell 합계 = 표시된 raw count
6. Cross-layer 11건 모두 unique 이슈 (중복 없음)

## File Paths Reference

**Audit 입력:**
- `C:/Users/yjisu/.claude/CLAUDE.md` (L1)
- `c:/Users/yjisu/Desktop/SCM_WORK/CLAUDE.md` (L2)
- `C:/Users/yjisu/.claude/harness/**` (L3)
- `C:/Users/yjisu/.claude/agents/*.md` + `c:/Users/yjisu/Desktop/SCM_WORK/.claude/agents/*.md` (L4)
- `C:/Users/yjisu/.claude/settings.json` (L5)
- `C:/Users/yjisu/.claude/commands/*.md` + system skills (L6)

**Audit 산출:**
- `c:/Users/yjisu/Desktop/SCM_WORK/docs/superpowers/specs/2026-05-16-6-layer-audit-design.md` (이 파일)
- `c:/Users/yjisu/Desktop/SCM_WORK/docs/superpowers/outputs/2026-05-16-6-layer-audit-report.md` (findings 상세)
- `c:/Users/yjisu/Desktop/SCM_WORK/.claude/feature_list.json` (backlog 36건 append)

**비교 reference:**
- `https://github.com/Yeachan-Heo/oh-my-claudecode` — 20 hooks × 11 lifecycle events

## Self-Review

- ✅ 모든 acceptance criteria 명시
- ✅ Methodology 재현 가능 (3 parallel Explore + matrix synthesis)
- ✅ Backlog schema 기존 `.claude/feature_list.json` 호환
- ✅ Out of Scope에 사유 동반
- ✅ Verification 6 step 명시
- ✅ Phase 3+ 후속 흐름 명시
