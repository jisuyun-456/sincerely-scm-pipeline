# Notion Meeting Notes — Multi-Agent Discussion Capture

**Date:** 2026-05-15
**Status:** Design — pending user approval
**Scope:** Universal Project Harness (global `~/.claude/harness/`) + 3 consumer projects (SCM_WORK, STOCK_WORK, side projects)

## Motivation

Current `notion-sync` produces Notion Meeting Notes pages with **flat properties only** (title, attendees, decisions, action_items, outcome). The page body is empty. The user wants Meeting Notes to render like the reference screenshots — a structured summary with attributed agent claims and explicit agreement/disagreement, like agents had a discussion before recording the meeting.

The reference screenshots show an Ad-hoc Observation note with:
- Issue summary citing external refs (Slack, Linear)
- Cause analysis explicitly attributed ("정성결님 분석에 동의")
- Numbered solution proposals
- Impact assessment against other ongoing work
- Receipts / discussion thread

This design extends the harness to capture **real multi-agent dialogue** (not narrative attribution) at 3 named gates and renders it to Notion as a summary + collapsible discussion log.

## Decisions (locked during brainstorming)

| Q | Decision |
|---|---|
| Q1: Trigger scenarios | **D** — All 3 gates: `sprint_review` + `checkpoint` + `observation` |
| Q2: Source of body content | **C** — Real multi-agent dialogue capture (not narrative attribution by a single author) |
| Q3: Posting cadence | **A** — Linear single-pass: each agent posts **at most one `claim` post** per meeting at end of their turn. Reactive stances (`agree`/`disagree`/`question`/`answer`) may be posted additionally, each referencing exactly one prior post via `refs`. This lets `harness-validator` agree with one worker and disagree with another in the same meeting without violating the rule. |
| Q4: Render format | **C** — Issue-summary (top) + collapsible discussion log (bottom) hybrid |
| Q5: Lifecycle | **C** — Local JSONL during execution + batched Notion render at meeting close |
| Q6: Observation trigger | **D** — Worker-escalation + validator auto-detect + `/observation` slash command |

## Architecture

### Components

| Component | Type | Role |
|---|---|---|
| `~/.claude/harness/meetings/<meeting-id>/discussion.jsonl` | New filesystem | Append-only post log per meeting |
| `~/.claude/harness/meetings/<meeting-id>/meta.yaml` | New filesystem | Meeting metadata: gate, participants, timestamps, Notion sync result |
| `~/.claude/harness/meetings/active.yaml` | New filesystem | List of currently-open meeting IDs (concurrent gates allowed — e.g., a `checkpoint` may fire mid-sprint while a `sprint_review` would later open at sprint end). Read by workers to decide where to append. |
| `~/.claude/harness/meetings/INDEX.jsonl` | New filesystem | Append-only index of all meetings (open/close events) |
| `meeting-coordinator` | Modified agent | Opens/closes meetings, dispatches participants, writes `synthesis` post, triggers Notion render |
| `harness-validator` | Modified agent | Writes JSONL post at verdict; emits `escalate_observation` flag on cross-cutting findings |
| `code/data/design-worker` | Modified agent | At end of turn, append JSONL post if a meeting is active |
| `checkpoint-reporter` | Modified agent | Opens `checkpoint` meeting on timer; dispatches participants |
| `notion-sync` | Modified agent | New `discussion_render` event — reads meta + JSONL, renders summary + log to Notion page body |
| `/observation` slash command | New | User trigger for ad-hoc gate with explicit `--affects` participant list |
| `notion-mapping.yaml` | Modified config | Add `discussion_render` event with per-gate body templates |

### Data flow (Sprint Review gate)

```
Sprint workers complete
    ↓
harness-validator emits verdict
    ↓
harness-orchestrator → meeting-coordinator (open sprint_review meeting)
    ↓
coordinator writes meta.yaml, empty discussion.jsonl, updates active.yaml
    ↓
coordinator dispatches each participant inline:
  "Read your report. Append one JSONL post (stance/refs/summary/evidence) to {path}."
    ↓
each worker + validator: appends 1 line to discussion.jsonl
    ↓
coordinator reads JSONL, writes synthesis post (stance: synthesis)
    ↓
coordinator marks meta.yaml status=closed, calls notion-sync (discussion_render)
    ↓
notion-sync reads meta + JSONL → renders Notion page body (summary top + log bottom)
    ↓
notion-sync writes back notion.page_id, url, rendered_at into meta.yaml
```

### Ad-hoc Observation gate differences

- **Opening trigger**: worker/validator escalation (`escalate_observation: true` + `affects: [agent...]` in report) OR `/observation` slash command
- **Participants**: originator + named affected agents (not all sprint workers)
- **External refs**: `triggered_by.external_refs.slack` / `.linear` populated when escalation includes them
- **Top-half template** uses `## 이슈 요약` / `## 원인 분석` / `## 해결 방향 제안` / `## 영향도 평가` / `## 후속 조치` sections

## Data formats

### `meta.yaml` (per meeting)

```yaml
meeting_id: m-2026-05-15-sprint2-review
gate_type: sprint_review | checkpoint | observation
opened_at: 2026-05-15T14:00:00Z
closed_at: 2026-05-15T14:32:11Z  # null until closed
status: open | closed | degraded | failed

mission: build-dashboard      # null if ad-hoc outside mission
sprint: 2                     # null if not sprint-bound
project: SCM_WORK
title: "Sprint 2 Review — build-dashboard"

participants:
  - agent: meeting-coordinator
    role: facilitator         # facilitator | participant | observer
    posted: true
  - agent: code-worker
    role: participant
    posted: true
  - agent: harness-validator
    role: participant
    posted: true

triggered_by:                 # required for observation gate
  agent: harness-validator    # or "user" for slash command
  reason: "C3 impl touches files outside Sprint 2 contract"
  external_refs:
    slack: "C0AACQG7RSL/2026-05-15T14:13"
    linear: "CTRL-247"

notion:
  page_id: null               # populated after successful render
  url: null
  rendered_at: null
  render_attempts: 0
```

### `discussion.jsonl` (append-only, one post per line)

```jsonl
{"ts":"2026-05-15T14:05:12Z","agent":"code-worker","stance":"claim","refs":[],"summary":"POST /shipments 구현 완료 — C3·C4 충족","evidence":["tests/test_shipments.py 12/12 pass","git HEAD abc1234"],"concerns":[],"contract_items":["C3","C4"]}
{"ts":"2026-05-15T14:08:33Z","agent":"data-worker","stance":"claim","refs":[],"summary":"tms_shipments 백필 794건 완료","evidence":["batch_size=10","duration=4m12s"],"concerns":["TO-238 1건 누락 — Project_PNA null"],"contract_items":["C5"]}
{"ts":"2026-05-15T14:15:02Z","agent":"harness-validator","stance":"agree","refs":["code-worker@2026-05-15T14:05:12Z"],"summary":"code-worker C3·C4 증거 검증 통과","evidence":["pytest output 확인","파일 diff 검토"],"concerns":[],"contract_items":["C3","C4"]}
{"ts":"2026-05-15T14:18:44Z","agent":"harness-validator","stance":"disagree","refs":["data-worker@2026-05-15T14:08:33Z"],"summary":"TO-238 누락은 Contract C5 미충족","evidence":["meta.yaml의 C5 must_pass='794 records OR explicit skip rationale' — explicit skip 누락"],"concerns":["다음 Sprint에서 보완 필요"],"contract_items":["C5"]}
{"ts":"2026-05-15T14:30:00Z","agent":"meeting-coordinator","stance":"synthesis","refs":[],"summary":"C3·C4 통과, C5 부분 충족(794/795). TO-238 carry-over 권고.","evidence":[],"concerns":[],"action_items":["다음 Sprint Plan에 TO-238 backfill 포함","Contract C5 수정 권고 — '명시적 skip 사유 동시 요구'"]}
```

### `active.yaml` (workspace-level pointer)

```yaml
open_meetings:
  - meeting_id: m-2026-05-15-sprint2-review
    opened_at: 2026-05-15T14:00:00Z
    gate_type: sprint_review
  - meeting_id: m-2026-05-15-cp4h
    opened_at: 2026-05-15T13:00:00Z
    gate_type: checkpoint
```

Empty when no gates are open: `open_meetings: []`. Workers iterate this list and append posts to every meeting where they are listed as participant.

### Post schema (every JSONL line)

| Field | Type | Required | Notes |
|---|---|---|---|
| `ts` | ISO-8601 UTC | yes | Append time |
| `agent` | string | yes | Agent identifier from `~/.claude/agents/*.md` filename |
| `stance` | enum | yes | `claim` \| `agree` \| `disagree` \| `question` \| `answer` \| `synthesis` |
| `refs` | array | yes (empty allowed) | `["{agent}@{ts}", ...]` — required non-empty for `agree`/`disagree`/`answer` |
| `summary` | string ≤300 chars | yes | One-line claim |
| `evidence` | array of strings | yes (empty allowed) | Concrete proofs: test output, file paths, git SHA |
| `concerns` | array of strings | yes (empty allowed) | Worker-flagged risks |
| `contract_items` | array of strings | optional | C-IDs addressed |
| `action_items` | array of strings | optional (synthesis only) | Coordinator's outputs to next sprint |

**Validation rules** (enforced by `meeting-coordinator` at close):
- Exactly one `synthesis` post per meeting, and it must be the last
- `agree`/`disagree`/`answer` must have non-empty `refs`
- All `refs` entries must point to existing posts in the same JSONL
- Unknown `stance` values → meeting marked `degraded`
- All `agent` values must appear in `meta.yaml participants[]`

## Gate triggers

| Gate | Opens when | Opened by | Synthesizer (writes final post) | Participants | Closes when |
|---|---|---|---|---|---|
| `sprint_review` | All sprint workers done + validator verdict in | `meeting-coordinator` | `meeting-coordinator` | All sprint workers + harness-validator + coordinator | Synthesizer writes `synthesis` post |
| `checkpoint` | 4h/8h/16h timer fires | `checkpoint-reporter` | `checkpoint-reporter` (acts as facilitator for checkpoint gates) | Active workers (last 4h) + validator + coordinator + reporter | Synthesizer writes `synthesis` post |
| `observation` | (a) `escalate_observation: true` in any agent report, OR (b) validator cross-cutting finding, OR (c) `/observation "<title>" --affects <list>` | `meeting-coordinator` | `meeting-coordinator` | Originator + named affected agents | Synthesizer writes `synthesis` after all participants posted OR timeout (default 10min wall) |

**Posting rule** (Q3 — Linear single-pass refined):
- Each participant writes **at most one `claim` post** per meeting (their primary turn-end output).
- Participants may post additional reactive entries (`agree` / `disagree` / `question` / `answer`), each referencing exactly one prior post via `refs`. This lets `harness-validator` agree with one worker and disagree with another in the same meeting without violating the cadence.
- The synthesizer (per gate) writes exactly one `synthesis` post and it must be last.
- If a participant needs to respond to a later post that arrived after their own, they may append one reactive post; deeper multi-round debate requires opening a new `observation` meeting.

## Notion render templates

### Page properties (already in `meeting_notes` schema)

| Property | Source |
|---|---|
| `Title` | `meta.title` |
| `Mission` | `meta.mission` |
| `Sprint` | `meta.sprint` |
| `Date` | `meta.opened_at` |
| `Type` | `meta.gate_type` mapped to `Sprint Review` / `Checkpoint` / `Ad-hoc` |
| `Attendees` | `meta.participants[].agent` (multi-select) |
| `Decisions` | synthesis `summary` |
| `Action Items` | synthesis `action_items` joined by newline |
| `Outcome` | derived from synthesis (success / partial / failed / in-progress) |

### Page body (two halves)

**Top half — summary (prose, gate-templated):**

| Gate | Top-half headings |
|---|---|
| `sprint_review` | `## 스프린트 결과 요약` / `## 통과한 Contract Items` / `## Carry-over` / `## 회고: Went well / Got stuck / Learned` / `## Action Items` |
| `checkpoint` | `## 현 진행 상황` / `## 필요한 사용자 결정` / `## 옵션 (A/B/C)` / `## 리스크 플래그` |
| `observation` | `## 이슈 요약` (with `triggered_by.external_refs`) / `## 원인 분석 (agent 합의 표시)` / `## 해결 방향 제안` / `## 영향도 평가` / `## 후속 조치` |

Coordinator fills the top half by reading JSONL. For `observation`, "원인 분석" enumerates `agree` posts as "[agent] 분석에 동의" (matches screenshot's "정성결님 분석에 동의" pattern).

**Bottom half — universal discussion log:**

Toggle block `💬 Agent Discussion Log (N posts)`, collapsed by default. Each JSONL line renders as:

```
▸ [code-worker · claim · 14:05]
  POST /shipments 구현 완료 — C3·C4 충족
  Evidence:
    • tests/test_shipments.py 12/12 pass
    • git HEAD abc1234
  Contract: C3, C4
```

- `agree` → green callout icon ✅
- `disagree` → red callout icon 🔻 with `refs` rendered as "→ {agent}@{ts}"
- `synthesis` → final callout ☑️ with action_items list

## Storage lifecycle

**Paths:**
```
~/.claude/harness/meetings/
  active.yaml                                   # pointer to currently-open meeting
  INDEX.jsonl                                   # append-only meeting open/close events
  m-2026-05-15-sprint2-review/
    meta.yaml
    discussion.jsonl
  m-2026-05-15-observation-ctrl247/
    meta.yaml
    discussion.jsonl
  archive/
    2026-04/
      m-*.tar.gz                                # closed meetings >30 days
```

**Naming**: `m-{YYYY-MM-DD}-{gate_short}-{context_slug}` where `gate_short` ∈ {`sprint{N}-review`, `cp{Nh}`, `observation`}. Collisions append `-2`, `-3`.

**Concurrency**:
- One directory per meeting; per-meeting JSONL append is atomic on POSIX for writes ≤4KB (each post ≤1KB).
- `active.yaml` updated only by coordinator at open/close. Workers read-only.
- `INDEX.jsonl` is append-only (single line per event); coordinator writes.

**Retention**:
- Closed meetings ≤30 days: live in `meetings/<id>/`
- 30–365 days: compressed in `meetings/archive/{YYYY-MM}/`
- >365 days: deleted (audit retention exhausted)

**Idempotency**:
- Once `meta.notion.page_id` is set, re-renders call `update_page` (no duplicate Notion pages).
- Re-render with different template version allowed (format iteration); JSONL itself never mutated.

## Agent integration deltas

### `meeting-coordinator`
- **New responsibilities**: open meeting (write meta.yaml + active.yaml + INDEX line), dispatch participants for posting, validate JSONL on close, write `synthesis` post, call `notion-sync` (`discussion_render`), update meta.yaml with Notion result.
- **Existing synthesis YAML output unchanged** — still returned to `harness-orchestrator`. The `synthesis` JSONL post is *additional*.
- New helper script: `~/.claude/harness/scripts/open-meeting.sh` and `close-meeting.sh`.

### `harness-validator`
- **At verdict time**: in addition to existing verdict YAML, append one JSONL post with `stance: agree` or `disagree` per worker claim. `refs` point to worker posts.
- **Cross-cutting detection**: if verdict touches files outside current Sprint Contract scope, emit `escalate_observation: {affects: [...], reason: "..."}` in verdict payload.

### `code-worker` / `data-worker` / `design-worker`
- At end of turn, read `~/.claude/harness/meetings/active.yaml` (a list of open meeting IDs). For each open meeting where the worker is in `participants[]`, append one `claim` JSONL post summarizing their report. (Workers normally have one active meeting; the list shape handles the rare overlap case.)
- Existing report format unchanged.

### `checkpoint-reporter`
- On 4h/8h/16h fire, open a `checkpoint` meeting (in addition to existing Slack DM), dispatch active workers + validator + coordinator to post, then close.

### `notion-sync`
- **New event** `discussion_render`:
  1. Read `meta.yaml` + `discussion.jsonl`
  2. Build properties from meta
  3. Select body template per `gate_type`
  4. Render top half (coordinator's synthesis prose) + bottom half (toggle log)
  5. Call `notion-create-pages` (or `notion-update-page` if `meta.notion.page_id` set)
  6. Write back `page_id`, `url`, `rendered_at`, increment `render_attempts`
- Existing flat-property events (`sprint_review`, `checkpoint`, `meeting_recorded`) remain functional for backward compat but are superseded by `discussion_render` when a meeting JSONL exists.

### `harness-orchestrator`
- On mission start: initialize `~/.claude/harness/meetings/active.yaml` as an empty list (`open_meetings: []`). On sprint open: leave it empty until a coordinator/reporter opens a meeting.
- On mission end: verify list is empty (any meetings left open are forcibly closed with `status: degraded` and a synthesizer-auto-generated synthesis post).

### `/observation` slash command (new)
- Args: `/observation "<title>" --affects <agent1>,<agent2> [--external-slack <url>] [--external-linear <id>]`
- Behavior: writes a minimal `escalate_observation` payload to `~/.claude/harness/meetings/observation-queue.jsonl`. `meeting-coordinator` polls this queue (or is invoked by orchestrator) and opens an observation meeting.

### `notion-mapping.yaml` additions

```yaml
discussion_render:
  trigger: "meeting-coordinator (또는 checkpoint-reporter)가 meeting을 close 직후"
  target_db: meeting_notes
  action: create_or_update_page  # update_page if meta.notion.page_id 존재
  match_by: meta.notion.page_id
  fields:
    title: meeting.title
    mission: meeting.mission
    sprint: meeting.sprint
    date: meeting.opened_at
    type: "{Sprint Review | Checkpoint | Ad-hoc}"
    attendees: meeting.participants[].agent
    decisions: synthesis.summary
    action_items: synthesis.action_items | join "\n"
    outcome: meeting.outcome
  body_template: "scripts/render-meeting.py — gate_type별 분기"
```

## Failure modes

| Failure | Behavior |
|---|---|
| JSONL append fails (disk full / locked) | Agent reports failure; logged to `~/.claude/harness/logs/discussion-write-fail.log`. Agent's regular report still succeeds. Meeting marked `status: degraded`. |
| Agent crashes mid-post (partial line) | Coordinator detects JSONL parse error on last line at close. Discards partial line. Marks meeting `degraded`. Proceeds with synthesis. |
| Participant doesn't post within timeout | Coordinator proceeds without their post. Synthesis notes "X did not post." `meta.participants[X].posted = false`. |
| Notion render fails | meta.yaml retains all data. `notion-sync.log` records failure. Mission proceeds. Re-render via `discussion_render` is idempotent. |
| Two agents try to open same meeting_id | meta.yaml exclusive-create (`O_EXCL`). Second open fails → retries with `-2` suffix. |
| `active.yaml` corruption | Workers treat unparseable active.yaml as `open_meetings: []` → fall back to existing report-only path. Coordinator rewrites active.yaml on next open. |
| Two concurrent meetings open (e.g., checkpoint fires during sprint) | Both meeting IDs appear in `active.yaml.open_meetings[]`. Workers append a post to each meeting they're a participant in (so a worker active during a checkpoint that gets reviewed at sprint_review may post in both). Coordinator close logic is per-meeting, idempotent. |
| Mission ends with open meetings | `harness-orchestrator` forcibly closes each, marking `status: degraded`, with auto-generated synthesis ("force-closed at mission end"). |
| `synthesis` post missing at close | Coordinator generates a minimal synthesis ("auto-generated, X participants, see log") and continues. |
| `refs` points to nonexistent post | Validator flags `degraded`; post kept in log (don't erase agent intent), synthesis notes the inconsistency. |

## Backward compatibility

| Existing behavior | Preserved? |
|---|---|
| `meeting-coordinator` synthesis YAML | ✅ Unchanged. New JSONL post is additional. |
| Worker report formats | ✅ Unchanged. JSONL post is a separate additional output. |
| `notion-sync` flat-property events (`sprint_review`, `checkpoint`, `meeting_recorded`) | ⚠️ Still functional, superseded when JSONL exists. Existing Notion pages untouched. |
| `harness-validator` verdict format | ✅ Unchanged. JSONL post is additional. |
| Lessons learning system | ✅ Reads existing synthesis YAML, unaffected. |
| Existing Notion Meeting Notes DB schema | ✅ Unchanged (properties stay the same). Only body content gains structure. |
| Existing `notion-mapping.yaml` events | ✅ Preserved. New `discussion_render` event added. |

## Non-goals

- **Real-time threading UI**: linear single-pass posting (Q3 decision) does not support multi-round debate. If multi-round is needed, open a new observation meeting.
- **Inter-mission discussions**: each meeting is scoped to one sprint or one observation. No cross-sprint discussions.
- **Agent-to-Slack mirroring**: posts go to local JSONL → Notion. Slack DMs remain the `checkpoint-reporter` channel (unchanged).
- **JSONL editing UI**: append-only. Corrections go in a new post with `stance: claim` referencing the prior post.
- **Real-time Notion comments mid-execution**: ruled out by Q5 (lifecycle C — batched at end).

## Open questions (none — all resolved in brainstorming)

All 6 design questions resolved: D / C / A / C / C / D.

## Implementation phasing (preview for plan)

Phase 1 — **Storage primitives**: `meta.yaml` / `discussion.jsonl` / `active.yaml` / `INDEX.jsonl` schemas + open/close helper scripts. No agent changes yet.

Phase 2 — **Coordinator + Validator integration**: `meeting-coordinator` opens/closes sprint_review meetings, validates JSONL, writes synthesis. `harness-validator` writes JSONL post at verdict.

Phase 3 — **Worker integration**: workers read `active.yaml` and append JSONL post at end of turn.

Phase 4 — **Notion render**: new `discussion_render` event in `notion-sync` + body templates (3 gate variants). Backward-compat fallback for existing events.

Phase 5 — **Checkpoint gate**: extend `checkpoint-reporter` to open checkpoint meetings.

Phase 6 — **Observation gate**: `escalate_observation` flag handling in worker reports, validator cross-cutting detection, `/observation` slash command.

Phase 7 — **Retention / GC**: archive compression + 1-year deletion.

Detailed implementation steps deferred to `writing-plans` skill.
