# SCM Realignment Mission — Direct Entry (smoke skipped)

**Date**: 2026-05-15
**Author**: brainstorming session (model: opus 4.7)
**Status**: Approved (v3 — smoke skipped, Mission 2 SCM realignment is the entry)

## Context

Universal Project Harness v2 was completed 2026-05-15 (14 agents: Core 9 + Specialized 5 + Retro-Learning). Three pending items from prep log:

1. ~~Harness v2 smoke test~~ — **skipped** (see decision history below)
2. SCM 실 단위 재설계 mission — **this mission, direct entry**
3. scm-validator TMS-only build — deferred until after this mission

### Decision history (this session)

- v1 plan: hybrid smoke (Harness lifecycle + W-NEW-01 + TMS Iter2 real work) → rejected because mission interruption could leave Airtable inconsistent
- v2 plan: pure synthetic dummy ETL 4h smoke → rejected after user asked "what is this smoke test actually for?" — synthetic deliverables had zero downstream value, and the SCM realignment mission's design-doc deliverables can themselves serve as the smoke vehicle (Sprint 1 = AS-IS diagnosis acts as natural Harness verification)
- v3 plan: direct entry to SCM realignment, Slack disabled → user questioned why Harness can't resume after mid-mission stop. Honest answer: multi-agent orchestration state isn't serialized in v2 (Phase 5+ deferral, README Known Limitations). User accepted "restart from scratch on interrupt" risk after weighing it against the alternative (skip Harness entirely + use single-agent delegation).
- **v4 (current): direct entry to SCM realignment, Slack DM enabled.** User will respond to 4h/8h checkpoints to confirm intermediate state. First Sprint of the real mission validates Harness lifecycle; design-doc deliverables mean low downside if interrupted.
- Subscription tokens only; no separate Anthropic API billing (verified: no `ANTHROPIC_API_KEY` env var, no `anthropic` SDK imports in Harness code, MCPs use OAuth/local auth)
- PC stays on for the mission's duration; on interrupt, partial Sprint outputs already saved to disk are preserved across the restart

## Mission — SCM 실 단위 재설계 (this session, 8h)

### Pre-requisite (must complete before `/mission` starts)

Author `~/.claude/harness/missions/strategy-design.yaml` template — done as a single-shot pre-task in this same session, before mission entry.

### Mission launch command

```
/mission strategy-design --duration 8h --project scm-team-realignment
```

### Sprint structure (4 Sprints × 2h)

| Sprint | Title | Duration | Primary Worker | Output |
|--------|-------|----------|----------------|--------|
| 1 | AS-IS 진단 + 회의 의사결정 합성 | 2h | consulting-pm-expert (D3) | AS-IS 문서 + 이슈 트리 |
| 2 | 재무 KPI 트리 수립 | 2h | scm-logistics-expert (D1) + tax-accounting-expert (D2) | 재무 KPI tree (인건비율·수수료계정·생산성) |
| 3 | AX/DX 범위 정의 (MECE) | 2h | consulting-pm-expert (D3) + scm-logistics-expert (D1) | AX/DX scope matrix |
| 4 | OKR/WBS/RACI + 구현 미션 backlog | 2h | consulting-pm-expert (D3) | OKR 1-page + WBS + 다음 구현 미션 후보 N개 |

### Sprint 1 — AS-IS 진단 + 회의 의사결정 합성

**Source-of-truth** (already captured, no fresh interview needed):
- `ClaudeVault/SCM/_AutoResearch/wiki/log.md` 2026-05-15 prep entry (line 1787+)
- 강한 메모리: `project_meeting_participants.md`, `project_scm_redesign.md`, `project_tms_gap_completed.md`
- 회의 핵심 의사결정 4개:
  1. 매출액 대비 인건비 비율 감소 (절대 인건비 X)
  2. AI 전환 → 수수료 계정 활용도 향상
  3. 2026 수평 생산성 50% 향상
  4. 리스크: 범위·성공기준 모호 시 미활용 시스템 / 낮은 ROI

**Tasks**:
- 회의 결정 4개를 Issue Tree로 분해 (MECE)
- 현재 SCM 실 운영 활동을 AS-IS 매핑 (Airtable WMS/TMS 운영 + SAP 시뮬레이션 + TMS AutoResearch + 정산 harness)
- 갭 분석: 현재 활동 ↔ 회의 결정 사이의 격차

**must_pass**:
1. AS-IS 문서가 회의 결정 4개 전부 다룸 (one-to-many mapping)
2. Issue Tree MECE 검증 (overlap 0, gap 0)
3. AS-IS 매핑이 *현재 운영* 기준 (가설·미래 X)

**must_not**:
- 회의 결정 임의 변경·확장
- 미참여 회의 추측 (log.md 외 추측 금지)

### Sprint 2 — 재무 KPI 트리

**Tasks**:
- "매출액 대비 인건비 비율" 분해 — 매출 driver / 인건비 driver / AI 영향 경로
- "수수료 계정 활용도" 분해 — 더존 아마란스 수수료 계정 코드 + AI 전환 시 발생 비용 추적 경로
- "수평 생산성 50%" 분해 — 측정 지표·baseline·목표값
- 각 KPI에 대해 baseline → 목표 → 측정 주기 → owner 정의

**must_pass**:
1. KPI 3개 전부 baseline·목표·측정 주기·owner 정의
2. K-IFRS·더존 아마란스 계정코드 매핑 (정성 X, 코드 명시)
3. 산출 공식이 SCM 현재 데이터(Airtable)에서 계산 가능한지 검증

**must_not**:
- 추정치를 baseline으로 단정 ("데이터 없음"이면 명시)
- 수치 목표를 데이터 없이 단정 (CLAUDE.md 글로벌 원칙)

### Sprint 3 — AX/DX 범위 정의 (MECE)

**Tasks**:
- AX(Analog Transformation) 범위: 프로세스·조직·R&R
- DX(Digital Transformation) 범위: 시스템·자동화·AI
- 각 범위에 대해 In / Out 명시 (MECE)
- 우선순위 매트릭스: ROI vs Risk

**must_pass**:
1. AX/DX 양쪽 분류가 MECE (한 항목이 양쪽에 중복 X)
2. 각 항목에 ROI 추정 근거 명시
3. Risk 평가 (회의 우려사항 "미활용 시스템 / 낮은 ROI" 반영)

**must_not**:
- 범위에 "TBD" 또는 "추후 결정" 항목 포함 (이게 회의 우려사항)

### Sprint 4 — OKR/WBS/RACI + 구현 미션 backlog

**Tasks**:
- 2026 OKR 1-page (Objective 1개 + Key Results 3-5개)
- WBS — Sprint 3에서 정의한 범위를 Work Package로 분해
- RACI — Work Package별 책임자 (사용자 / 메인 Claude / 도메인 에이전트)
- 다음 구현 미션 후보 N개 정의 — 각각 `/mission <template> --duration <h> --project <name>` 명령 + 산출물 목록

**must_pass**:
1. OKR Objective가 회의 의사결정 4개를 종합 반영
2. WBS 모든 leaf에 owner + 추정시간
3. 구현 미션 후보가 priority + dependency 명시
4. 모든 산출물 docs/superpowers/specs/ 또는 ClaudeVault outputs/ 에 저장

**must_not**:
- OKR Key Result에 측정 불가 항목 ("개선한다", "강화한다")
- 구현 미션 후보가 strategy-design.yaml 재호출 (재귀 금지)

### Harness Lifecycle Verification — secondary acceptance criteria

This is the *side effect* — Mission 1 of Harness usage. Pass conditions identical to v2 smoke spec H1~H14, captured as side observations:

| Check | Pass criterion |
|-------|----------------|
| H1. Mission lock | `.mission-lock` file created on start, removed on end |
| H2. Orchestrator decomposition | harness-orchestrator produces Sprint Plan |
| H3. Sprint planner internal split | sprint-planner divides each Sprint |
| H4. Worker delegation | domain experts (D1/D2/D3) invoked correctly per routing |
| H5. harness-validator per Sprint | Contract PASS/FAIL verdict |
| H6. meeting-coordinator | Handoff doc between Sprints |
| H7. Notion AgentOps sync | 6 DBs updated |
| H8. Retro-Learning extraction | ≥ 1 lesson candidate at end |
| H9. reality-checker triggered | mode=data, duration=8h ≥ 8h threshold → triggered correctly |
| H10. checkpoint reports | 4h checkpoint sent via Slack DM to user (target U026S3U7KSP); 8h checkpoint at mission end |
| H11. cost guardrail | warn at $10, hard stop at $30 |
| H12. Karpathy enforcement | validator rejects scope creep |
| H13. mission-lock cleanup | removed on success |
| H14. workflow-architect — NOT triggered | duration=8h < 12h → correctly skipped |

→ Lessons surfaced about Harness itself go to `lessons/global.md`; lessons about SCM domain go to `lessons/domain:scm.md`.

### Per-session Overrides

```yaml
# Passed to harness-orchestrator at mission start
overrides:
  # notification.slack_target: keep sprint-config default ("U026S3U7KSP")
  # → 4h and 8h checkpoint reports sent via Slack DM
  # → User responds: `승인` / `수정 <지시>` / `중단` / `commit`
  # → 30-min response timeout (per sprint-config)
  auto_continue_on_pass: true                      # default — Sprints auto-advance on Contract pass
  retro_learning.enabled: true
  cost_guardrail.warn_token_threshold_usd: 10
  cost_guardrail.hard_stop_token_threshold_usd: 30
```

> 4h checkpoint = Sprint 1-2 완료 시점. 8h checkpoint = 미션 종료 시점 (Sprint 4 끝). Sprint 1·3 끝에서는 Contract pass 시 자동 다음 Sprint 진행 (체크포인트 DM 없음).

### Deliverables checklist

- [ ] AS-IS 진단 문서 → `docs/superpowers/outputs/2026-05-15-scm-asis-diagnosis.md`
- [ ] 재무 KPI 트리 → `docs/superpowers/outputs/2026-05-15-scm-financial-kpi.md`
- [ ] AX/DX scope matrix → `docs/superpowers/outputs/2026-05-15-scm-axdx-scope.md`
- [ ] OKR/WBS/RACI 1-page → `docs/superpowers/outputs/2026-05-15-scm-okr-wbs.md`
- [ ] 구현 미션 backlog → `docs/superpowers/outputs/2026-05-15-implementation-mission-backlog.md`
- [ ] 누적 학습 → `~/.claude/harness/lessons/global.md` + `domain:scm.md` 갱신
- [ ] Mission summary → `~/.claude/harness/logs/<mission-id>/`
- [ ] Notion AgentOps 6 DB 동기화 (Roadmap·Tasks·Meeting Notes·Decisions·Operating Principles·Team Roster)

## Verification (Mission end-to-end)

1. **Mission start**: `/mission strategy-design --duration 8h --project scm-team-realignment` triggers harness-orchestrator → Sprint Plan + Contract → user approves Contract in main conversation
2. **Per-Sprint** (after each Sprint closes):
   ```powershell
   ls docs/superpowers/outputs/2026-05-15-scm-*.md     # progressive deliverable check
   ```
3. **Harness lifecycle**: `~/.claude/harness/logs/<mission-id>/` per-Sprint logs, validator verdicts, meeting-coordinator handoffs
4. **Notion sync**: Notion "🤖 Agent Operations" workspace → mission row in Roadmap, Sprint rows in Tasks, ADR rows for Contract decisions
5. **Specialized agent triggers**:
   - reality-checker: log SHOULD contain reality-checker invocation (8h ≥ 8h, deliverables ≥ 3)
   - workflow-architect: log SHOULD NOT (8h < 12h)
6. **Lesson extraction**: meeting-coordinator presents lesson candidates → user approves → lessons/*.md updated

## Risks

| Risk | Mitigation |
|------|------------|
| PC sleeps mid-mission | 8h continuous PC-on required; if interrupted, deliverables in progress saved to disk but `/mission resume` not available → restart |
| Token rate limit hits | Mission auto-stops on hard guardrail; resume after window opens |
| Harness v2 bug surfaces in Sprint 1 | Captured as lesson; if fatal, mission halts, fix Harness, restart |
| Domain experts produce shallow output | harness-validator's Karpathy guard + Contract must_pass 검증 |
| Notion sync silent failure | non-blocking; mission completes |
| Sprint 4 backlog references non-existent templates | Spec restricts mission templates to existing 3 (build-pipeline/build-dashboard/build-api) + this new strategy-design |

## Future missions (deferred, defined by Sprint 4 output)

After Mission completes, Sprint 4 produces an implementation mission backlog. Likely candidates (to be confirmed by Mission):
- W-NEW-01 SAP_이동유형 마스터 (dedicated 4h `build-pipeline`)
- TMS Iter2 utilization recompute (dedicated 4h `build-pipeline`)
- scm-validator TMS build (dedicated, possibly without `/mission` — single-shot agent build)
- Dashboard for the new KPIs (dedicated `build-dashboard`)

## Open items

- /mission resume mechanism (Phase 5+ deferred per harness README)
- 회의록 raw 원본 (Slack/email) — only if log.md 요약 외에 추가 detail이 필요할 때 사용자 surfacing 요청
