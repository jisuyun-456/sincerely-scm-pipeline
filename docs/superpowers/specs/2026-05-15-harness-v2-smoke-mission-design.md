# Harness v2 Smoke + SCM Realignment — 2-Mission Sequence

**Date**: 2026-05-15
**Author**: brainstorming session (model: opus 4.7)
**Status**: Approved — proceed with Mission 1 in this session

## Context

Universal Project Harness v2 was completed 2026-05-15 (14 agents: Core 9 + Specialized 5) along with the Retro-Learning System. Before relying on it for the larger "SCM team realignment" strategy mission, we need to verify the full lifecycle works end-to-end in production conditions. Three pending items from the 2026-05-15 prep log:

1. Harness v2 smoke test — `/mission build-pipeline --duration 4h --project tms-test`
2. SCM 실 단위 재설계 mission — consulting-first (financial KPI + AX/DX scope)
3. scm-validator TMS-only build — **deferred**, to be re-discussed after #2

User decided:
- Smoke test → SCM realignment, in that order
- One mission per session (PC must stay on; Claude Code is a local CLI, not a background service)
- Smoke test gets **real work payload** (W-NEW-01 + TMS Iter2), not synthetic dummy — full Harness lifecycle exercised with concrete deliverables
- Slack DM disabled for smoke test — checkpoints surface in main conversation; auto-continue on Contract pass
- Subscription tokens only; no separate Anthropic API billing

## Mission 1 — Harness v2 Smoke + Real Work (this session, 8h)

```
/mission build-pipeline --duration 8h --project tms-test
```

### Sprint structure (2 Sprints × 4h, compressed from build-pipeline's default 4×3h)

| Sprint | Title | Duration | Worker | Domain |
|--------|-------|----------|--------|--------|
| 1 | W-NEW-01: SAP_이동유형 마스터 + WMS FK | 4h | data-worker (+ wms-master-data SK-01 if invoked) | WMS Phase 0 |
| 2 | TMS Iter2: 차량이용률 재계산 + AutoResearch report | 4h | data-worker + code-worker | TMS KPI |

### Sprint 1 — W-NEW-01 SAP_이동유형 마스터

**Tasks**:
- Create new Airtable table `SAP_이동유형` in WMS base (`appLui4ZR5HWcQRri`)
- Seed 8 SAP movement type rows: 101 (입고), 201 (출고), 261 (생산출고), 311 (이전), 601 (납품), 701 (조정), 122 (반품입고), 551 (폐기)
- Add FK column `movement.이동유형` → `SAP_이동유형.code`
- Backfill existing `movement` rows where movement_type matches one of the 8 codes
- Verification script: count rows where `이동유형` is null vs total

**Validation Contract (must_pass)**:
1. `SAP_이동유형` table exists with exactly 8 seed rows
2. `movement.이동유형` FK populated for ≥ 95% of historical rows (unmatched codes logged)
3. Idempotency: re-running seed script produces 0 inserts/updates
4. Immutable Ledger preserved — no `movement` UPDATE/DELETE (Storno-only if correction needed)
5. Backfill script committed to `scripts/wms_backfill/` with `--dry-run` and `--force` modes

**must_not**:
- Hardcoded Airtable PAT in source
- `movement` table UPDATE for non-Storno purpose
- Schema change applied without backup of pre-state row counts

### Sprint 2 — TMS Iter2 차량이용률 + OTIF 재계산

**Context**: First TMS AutoResearch iteration (memory: `project_tms_autoResearch.md`) found 차량이용률 = 19.4%, OTIF = 100%. The 19.4% number is suspected to be wrong because most shipments had `Total_CBM = 0` (the CBM master fix on 2026-05-12 restored CBM data for 98% of products → re-calculation now possible).

**Tasks**:
- Re-run `tms_daily_volume.utilization_rate` calculation using restored CBM data
- Re-compute OTIF with cleaned shipment status enum
- Generate AutoResearch report → `ClaudeVault/SCM/_AutoResearch/outputs/2026-05-15_tms_iter2_utilization.md`
- Update `outputs/index.md` link
- Identify outliers (shipments where utilization > 100% or < 5%)

**Validation Contract (must_pass)**:
1. Utilization rate calculation reuses `cbm_calc.py` (no duplicate logic)
2. Output report covers all 4 carriers (이장훈 / 조희선 / 박종성 / 로젠)
3. Comparison delta vs Iter1 (19.4%) documented with reason
4. OTIF recomputation respects original Immutable Ledger (no in-place edits to shipments)
5. Report saved + `index.md` updated + committed

**must_not**:
- Mutate `tms_shipments` rows (read-only analysis)
- Hardcode carrier names (use partners registry)

### Harness Lifecycle Verification (Smoke Test Acceptance Criteria)

These are the **smoke test** must_passes — independent of the work product:

| Check | Pass criterion |
|-------|----------------|
| H1. Mission lock | `.mission-lock` file created on start, removed on end |
| H2. Orchestrator decomposition | harness-orchestrator produces Sprint Plan with Contracts |
| H3. Sprint planner internal split | sprint-planner divides each Sprint into Worker tasks |
| H4. Worker delegation | data-worker / code-worker invoked, domain agent (SK-01) optionally |
| H5. harness-validator runs each Sprint | Contract check produces PASS/FAIL verdict |
| H6. meeting-coordinator synthesizes | Handoff doc generated between Sprints |
| H7. Notion AgentOps sync | 6 DBs (Roadmap/Tasks/Meeting Notes/Decisions/Operating Principles/Team Roster) updated |
| H8. Retro-Learning extraction | meeting-coordinator surfaces ≥ 1 lesson candidate at mission end |
| H9. reality-checker final cert | Mode = `data`, default NEEDS_WORK, override to PASS with evidence |
| H10. checkpoint reports | Captured in main conversation (Slack DM disabled per session config) |
| H11. cost guardrail | Token usage tracked; warning at $10 estimate, hard stop at $30 |
| H12. Karpathy enforcement | harness-validator rejects any work that exceeds Sprint scope |

### Per-session Overrides for this mission

```yaml
# Passed to harness-orchestrator at mission start (in_memory override, no file edit)
overrides:
  notification.slack_target: ""                    # empty target → harness fallback chain
                                                   # (slack send no-op → logs → main convo display)
  auto_continue_on_pass: true                      # already default
  retro_learning.enabled: true
  cost_guardrail.warn_token_threshold_usd: 10
  cost_guardrail.hard_stop_token_threshold_usd: 30
```

> When `slack_target` is empty, the existing fallback chain (per Harness v2 Critical Fix #35) routes checkpoints to logs and surfaces them in the next main-conversation message. No Slack DMs sent.

### Deliverables checklist (Mission 1)

- [ ] `SAP_이동유형` Airtable table + 8 seed rows
- [ ] `movement.이동유형` FK populated (≥95%)
- [ ] `scripts/wms_backfill/seed_sap_movement_types.py` (idempotent)
- [ ] `scripts/wms_backfill/backfill_movement_fk.py` (idempotent, dry-run/force)
- [ ] TMS Iter2 utilization report at `outputs/2026-05-15_tms_iter2_utilization.md`
- [ ] `outputs/index.md` updated
- [ ] Lesson candidate(s) surfaced and reviewed
- [ ] Mission summary in `~/.claude/harness/logs/<mission-id>/`

## Mission 2 — SCM 실 단위 재설계 (next session, 8h)

**Defer to next session.** This session ends after Mission 1 verification.

### Pre-requisites (must complete before mission 2 starts)

1. Author `~/.claude/harness/missions/strategy-design.yaml` template
   - Pattern: consulting-first (4 Sprint × 2h)
   - Sprint 1 — AS-IS diagnosis (consulting-pm-expert)
   - Sprint 2 — Financial KPI tree (scm-logistics-expert + tax-accounting-expert)
   - Sprint 3 — AX/DX scope matrix (MECE) (consulting-pm-expert)
   - Sprint 4 — OKR/WBS/RACI + downstream implementation mission backlog
   - Workers: domain experts only (D1/D2/D3 + D-TMS1/D-TMS2 routing)
   - Deliverables: design docs, not code
2. Meeting decisions already captured in `ClaudeVault/SCM/_AutoResearch/wiki/log.md` (entry: `## [2026-05-15] 준비 | SCM 실 단위 재설계 미션`, line 1787+). Mission 2 Sprint 1 reads this as the AS-IS source-of-truth. If the user has additional raw meeting notes (Slack/Obsidian), surface at Mission 2 kickoff — otherwise the log entry is treated as authoritative.
3. Confirm strategic anchors from prep log:
   - 매출액 대비 인건비 비율 감소 (not absolute headcount cut)
   - 수수료 계정 활용도 향상 via AI
   - 2026 목표: 수평 생산성 50% 향상
   - Risk: 범위·성공기준 모호 시 미활용 시스템·낮은 ROI

### Mission 2 launch command (next session)

```
/mission strategy-design --duration 8h --project scm-team-realignment
```

### scm-validator (deferred, 3rd in sequence)

After Mission 2 completes, re-discuss with user:
- Whether to build now (Airtable TMS already connected, no SSOT blocker for status enum check)
- Or wait until SCM realignment defines validator priorities

## Verification (Mission 1 end-to-end)

1. **Mission start check**: `/mission build-pipeline --duration 8h --project tms-test` triggers harness-orchestrator → produces Sprint Plan + Contract → user approves Contract in main conversation
2. **Sprint 1 verification**:
   ```powershell
   # After Sprint 1 closes
   python scripts/wms_backfill/seed_sap_movement_types.py --dry-run  # should show 0 inserts
   # In Airtable WMS base, table SAP_이동유형 visible with 8 rows
   ```
3. **Sprint 2 verification**:
   ```powershell
   # Report exists
   ls "C:/Users/yjisu/Documents/ClaudeVault/SCM/_AutoResearch/outputs/2026-05-15_tms_iter2_utilization.md"
   # Index updated
   git diff -- "C:/Users/yjisu/Documents/ClaudeVault/SCM/_AutoResearch/outputs/index.md"
   ```
4. **Harness lifecycle**: Inspect `~/.claude/harness/logs/<mission-id>/` for per-Sprint logs, validator verdicts, meeting-coordinator handoffs
5. **Notion sync**: Open Notion "🤖 Agent Operations" workspace → confirm mission row in Roadmap, Sprint rows in Tasks, ADR rows for Contract decisions
6. **Lesson extraction**: At mission end, meeting-coordinator presents lesson candidates → user approves → `~/.claude/harness/lessons/domain:scm.md` or `global.md` updated

## Risks

| Risk | Mitigation |
|------|------------|
| PC sleeps mid-mission | User keeps PC on; if interrupted, mission state lost (no `/mission resume` yet) |
| Token rate limit hits (subscription, not API billing) | Mission auto-stops on hard guardrail; resume after rate window opens |
| Airtable schema change collision (someone else editing) | Sprint 1 takes pre-state snapshot, restore script ready |
| TMS Iter2 numbers still anomalous after CBM fix | Sprint 2 documents reason instead of silent acceptance |
| Notion sync silent failure | non-blocking; mission completes even if sync fails — surfaced in final report |

## Open items (post-mission, not blockers)

- strategy-design.yaml authoring (Mission 2 prereq)
- 회의록 location confirmation (Mission 2 prereq)
- scm-validator decision (after Mission 2)
- /mission resume mechanism (Phase 5+ deferred per harness README)
