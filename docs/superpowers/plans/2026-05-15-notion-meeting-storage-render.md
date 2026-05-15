# Notion Meeting Discussion — Storage & Render Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the storage primitives (meta.yaml + append-only discussion.jsonl + active.yaml + INDEX.jsonl) and render functions (gate-templated body builders) needed for multi-agent discussion capture, exposed as a Python CLI + pytest-covered library — independent of any agent integration.

**Architecture:** Pure-Python module `meeting_storage.py` owns the on-disk format (open/append/close/list). `render_meeting.py` reads stored meetings and produces Notion-ready block payloads (dicts) that the notion-sync agent will later consume via MCP. A `cli.py` argparse dispatcher exposes `open / post / close / list / render` subcommands so agents (or a human operator) can drive meetings without writing Python. Storage paths default to `~/.claude/harness/meetings/` but are overridable for testing via `--base-dir` and pytest fixtures. No Notion network call happens in this plan — render output is a JSON payload only.

**Tech Stack:** Python 3.14, PyYAML (new dependency), pytest 9 (already installed). No external network calls. Standard library only beyond YAML.

**Spec reference:** `c:\Users\yjisu\Desktop\SCM_WORK\docs\superpowers\specs\2026-05-15-notion-meeting-agent-discussion-design.md`

**Out-of-scope for this plan (deferred to follow-up plans):**
- Agent integration (meeting-coordinator / harness-validator / workers reading active.yaml) — Plan B
- Actual Notion API calls via notion-sync MCP — Plan B
- Checkpoint and Observation gate templates (only `sprint_review` top-half template is in this plan) — Plan C
- `/observation` slash command — Plan C
- Archive / GC / retention — Plan D

---

## File Structure

**All paths under `~/.claude/harness/` (a separate git repo from SCM_WORK).**

| Path | Purpose | Created or Modified |
|---|---|---|
| `~/.claude/harness/scripts/meeting_storage.py` | Core module: dataclasses, open/append/close, validation | **Create** |
| `~/.claude/harness/scripts/render_meeting.py` | Render meeting to Notion block payload | **Create** |
| `~/.claude/harness/scripts/cli.py` | Argparse dispatcher with sub-commands | **Create** |
| `~/.claude/harness/scripts/__init__.py` | Empty (makes scripts a package) | **Create** |
| `~/.claude/harness/scripts/tests/__init__.py` | Empty | **Create** |
| `~/.claude/harness/scripts/tests/conftest.py` | Pytest fixtures (tmp meetings dir) | **Create** |
| `~/.claude/harness/scripts/tests/test_meeting_storage.py` | Unit tests for storage | **Create** |
| `~/.claude/harness/scripts/tests/test_render_meeting.py` | Unit tests for render | **Create** |
| `~/.claude/harness/scripts/tests/test_cli_e2e.py` | End-to-end CLI smoke test | **Create** |
| `~/.claude/harness/scripts/README.md` | Usage docs | **Create** |
| `~/.claude/harness/meetings/.gitkeep` | Placeholder to keep dir tracked | **Create** |
| `~/.claude/harness/.gitignore` | Exclude live `meetings/m-*/` directories | **Create or Modify** |
| `~/.claude/harness/notion-mapping.yaml` | Add `discussion_render` event spec | **Modify** |

**Module boundaries:**
- `meeting_storage.py` knows nothing about Notion or rendering. Pure I/O + validation.
- `render_meeting.py` depends on `meeting_storage.py` (reads via `load_meeting()`). Returns dict payloads, never writes.
- `cli.py` depends on both. Argparse wiring only — no business logic.
- Tests import from these modules; never duplicate logic.

---

### Task 1: Project setup — directories, dependencies, gitignore

**Files:**
- Create: `~/.claude/harness/scripts/__init__.py`
- Create: `~/.claude/harness/scripts/tests/__init__.py`
- Create: `~/.claude/harness/meetings/.gitkeep`
- Create or Modify: `~/.claude/harness/.gitignore`
- Create: `~/.claude/harness/scripts/README.md`

- [ ] **Step 1: Install PyYAML**

Run: `py -m pip install pyyaml`
Expected: success message, `Successfully installed pyyaml-X.Y.Z`. Verify with `py -c "import yaml; print(yaml.__version__)"` — should print a version string.

- [ ] **Step 2: Create package directories and empty `__init__.py` files**

Run (PowerShell):
```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.claude\harness\scripts\tests"
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.claude\harness\meetings"
New-Item -ItemType File -Force -Path "$env:USERPROFILE\.claude\harness\scripts\__init__.py"
New-Item -ItemType File -Force -Path "$env:USERPROFILE\.claude\harness\scripts\tests\__init__.py"
New-Item -ItemType File -Force -Path "$env:USERPROFILE\.claude\harness\meetings\.gitkeep"
```
Expected: directories exist, four files exist (empty).

- [ ] **Step 3: Create `.gitignore` for `~/.claude/harness/` to exclude live meeting data**

Path: `~/.claude/harness/.gitignore` (create if not present; otherwise append the block).

Content (if file does not exist — create with this body):

```gitignore
# Live meeting data — never commit; treat as runtime
meetings/m-*/
meetings/INDEX.jsonl
meetings/active.yaml
meetings/archive/

# Existing harness runtime exclusions (preserved)
logs/

# Python build / cache (in case dev artifacts appear under scripts/)
__pycache__/
*.pyc
.pytest_cache/
```

If a file already exists, append only the four "Live meeting data" lines and the three `__pycache__` lines (skip duplicates).

- [ ] **Step 4: Create `~/.claude/harness/scripts/README.md`**

Content:

```markdown
# Harness Meeting Scripts

Storage + render foundation for multi-agent discussion capture. See
`<SCM_WORK>/docs/superpowers/specs/2026-05-15-notion-meeting-agent-discussion-design.md`
for the full design.

## Layout

| File | Role |
|---|---|
| `meeting_storage.py` | Open / append / close / load meetings on disk |
| `render_meeting.py`  | Build Notion-ready block payload from a closed meeting |
| `cli.py`             | `python -m scripts.cli <subcommand>` CLI dispatcher |
| `tests/`             | pytest suite — run with `py -m pytest scripts/tests/` |

## Usage (CLI)

```bash
# Open a sprint_review meeting
py -m scripts.cli open \
  --gate sprint_review \
  --mission build-dashboard \
  --sprint 2 \
  --project SCM_WORK \
  --participants meeting-coordinator,code-worker,harness-validator

# Append a post
py -m scripts.cli post \
  --meeting m-2026-05-15-sprint2-review \
  --agent code-worker \
  --stance claim \
  --summary "POST /shipments 구현 완료" \
  --evidence "tests pass" "git HEAD abc1234" \
  --contract-items C3 C4

# Close with synthesis post (coordinator)
py -m scripts.cli post \
  --meeting m-2026-05-15-sprint2-review \
  --agent meeting-coordinator \
  --stance synthesis \
  --summary "C3·C4 통과" \
  --action-items "Next sprint: TO-238 backfill"

py -m scripts.cli close --meeting m-2026-05-15-sprint2-review

# Render to Notion block payload (JSON)
py -m scripts.cli render --meeting m-2026-05-15-sprint2-review --out payload.json
```

## Testing

```bash
py -m pytest "$env:USERPROFILE/.claude/harness/scripts/tests/" -v
```

Run a single test: `py -m pytest scripts/tests/test_meeting_storage.py::test_open_creates_files -v`
```

- [ ] **Step 5: Verify pytest discovers the empty tests dir**

Run (PowerShell): `py -m pytest "$env:USERPROFILE/.claude/harness/scripts/tests/" -v`
Expected: `collected 0 items` (no tests yet) — exit code 5 (no tests collected) is OK at this stage; non-zero exit is acceptable here. The point is pytest finds the directory and doesn't crash on import.

- [ ] **Step 6: Commit (in ~/.claude repo)**

Run (PowerShell):
```powershell
cd $env:USERPROFILE\.claude
git add harness/.gitignore harness/meetings/.gitkeep harness/scripts/__init__.py harness/scripts/tests/__init__.py harness/scripts/README.md
git commit -m "harness(meetings): scaffold scripts package + meetings runtime dir + gitignore"
cd $env:USERPROFILE\Desktop\SCM_WORK
```
Expected: one commit created in `~/.claude` repo, working tree clean afterward in that path.

---

### Task 2: Storage data types — dataclasses + validation rules

**Files:**
- Create: `~/.claude/harness/scripts/meeting_storage.py` (initial: dataclasses + post validation only)
- Create: `~/.claude/harness/scripts/tests/conftest.py` (pytest fixtures)
- Create: `~/.claude/harness/scripts/tests/test_meeting_storage.py` (first tests)

- [ ] **Step 1: Write failing test for post stance validation**

File: `~/.claude/harness/scripts/tests/test_meeting_storage.py`

```python
import pytest
from scripts.meeting_storage import Post, validate_post, PostValidationError


def test_claim_post_with_empty_refs_is_valid():
    post = Post(
        ts="2026-05-15T14:05:12Z",
        agent="code-worker",
        stance="claim",
        refs=[],
        summary="POST /shipments 구현 완료",
        evidence=["tests pass"],
        concerns=[],
        contract_items=["C3", "C4"],
    )
    validate_post(post)  # raises if invalid


def test_agree_post_requires_non_empty_refs():
    post = Post(
        ts="2026-05-15T14:15:02Z",
        agent="harness-validator",
        stance="agree",
        refs=[],
        summary="validator agrees",
        evidence=[],
        concerns=[],
    )
    with pytest.raises(PostValidationError, match="agree.*requires.*refs"):
        validate_post(post)


def test_disagree_post_requires_non_empty_refs():
    post = Post(
        ts="2026-05-15T14:18:44Z",
        agent="harness-validator",
        stance="disagree",
        refs=[],
        summary="validator disagrees",
        evidence=[],
        concerns=[],
    )
    with pytest.raises(PostValidationError, match="disagree.*requires.*refs"):
        validate_post(post)


def test_answer_post_requires_non_empty_refs():
    post = Post(
        ts="2026-05-15T14:20:00Z",
        agent="code-worker",
        stance="answer",
        refs=[],
        summary="answer",
        evidence=[],
        concerns=[],
    )
    with pytest.raises(PostValidationError, match="answer.*requires.*refs"):
        validate_post(post)


def test_unknown_stance_rejected():
    post = Post(
        ts="2026-05-15T14:05:12Z",
        agent="code-worker",
        stance="bogus",
        refs=[],
        summary="bogus",
        evidence=[],
        concerns=[],
    )
    with pytest.raises(PostValidationError, match="unknown stance.*bogus"):
        validate_post(post)


def test_summary_length_limit_300_chars():
    long_summary = "x" * 301
    post = Post(
        ts="2026-05-15T14:05:12Z",
        agent="code-worker",
        stance="claim",
        refs=[],
        summary=long_summary,
        evidence=[],
        concerns=[],
    )
    with pytest.raises(PostValidationError, match="summary.*300"):
        validate_post(post)


def test_synthesis_allows_action_items():
    post = Post(
        ts="2026-05-15T14:30:00Z",
        agent="meeting-coordinator",
        stance="synthesis",
        refs=[],
        summary="C3·C4 pass",
        evidence=[],
        concerns=[],
        action_items=["next sprint: TO-238 backfill"],
    )
    validate_post(post)  # passes
```

- [ ] **Step 2: Run tests to verify they fail with ImportError**

Run: `py -m pytest "$env:USERPROFILE/.claude/harness/scripts/tests/test_meeting_storage.py" -v`
Expected: errors at collection (`ModuleNotFoundError: No module named 'scripts.meeting_storage'` or similar).

- [ ] **Step 3: Implement minimal `meeting_storage.py` to make tests pass**

File: `~/.claude/harness/scripts/meeting_storage.py`

```python
"""Storage primitives for harness multi-agent meeting discussion logs."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

STANCES = {"claim", "agree", "disagree", "question", "answer", "synthesis"}
STANCES_REQUIRING_REFS = {"agree", "disagree", "answer"}
SUMMARY_MAX_CHARS = 300


class PostValidationError(ValueError):
    """Raised when a Post violates schema rules."""


@dataclass
class Post:
    ts: str
    agent: str
    stance: str
    refs: List[str]
    summary: str
    evidence: List[str]
    concerns: List[str]
    contract_items: List[str] = field(default_factory=list)
    action_items: List[str] = field(default_factory=list)


def validate_post(post: Post) -> None:
    if post.stance not in STANCES:
        raise PostValidationError(
            f"unknown stance: {post.stance!r} (allowed: {sorted(STANCES)})"
        )
    if post.stance in STANCES_REQUIRING_REFS and not post.refs:
        raise PostValidationError(
            f"stance {post.stance!r} requires non-empty refs"
        )
    if len(post.summary) > SUMMARY_MAX_CHARS:
        raise PostValidationError(
            f"summary exceeds {SUMMARY_MAX_CHARS} chars (got {len(post.summary)})"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest "$env:USERPROFILE/.claude/harness/scripts/tests/test_meeting_storage.py" -v`
Expected: 7 passed.

- [ ] **Step 5: Add pytest fixtures in conftest.py**

File: `~/.claude/harness/scripts/tests/conftest.py`

```python
"""Shared pytest fixtures for meeting storage tests."""
import pytest


@pytest.fixture
def tmp_meetings_dir(tmp_path):
    """Provide a temp directory as the meetings base_dir for tests."""
    meetings_dir = tmp_path / "meetings"
    meetings_dir.mkdir()
    return meetings_dir
```

- [ ] **Step 6: Commit**

Run (PowerShell):
```powershell
cd $env:USERPROFILE\.claude
git add harness/scripts/meeting_storage.py harness/scripts/tests/conftest.py harness/scripts/tests/test_meeting_storage.py
git commit -m "harness(meetings): Post dataclass + stance/refs/summary validation"
cd $env:USERPROFILE\Desktop\SCM_WORK
```

---

### Task 3: Open meeting — create meta.yaml + empty JSONL + INDEX entry + active.yaml update

**Files:**
- Modify: `~/.claude/harness/scripts/meeting_storage.py` (add `open_meeting`, `_read_active`, `_write_active`, `_append_index`)
- Modify: `~/.claude/harness/scripts/tests/test_meeting_storage.py` (append tests)

- [ ] **Step 1: Write failing tests for `open_meeting`**

Append to `~/.claude/harness/scripts/tests/test_meeting_storage.py`:

```python
from pathlib import Path
import yaml
from scripts.meeting_storage import (
    open_meeting,
    Meeting,
    MeetingExistsError,
)


def test_open_creates_meta_and_empty_jsonl(tmp_meetings_dir):
    meeting = open_meeting(
        base_dir=tmp_meetings_dir,
        gate_type="sprint_review",
        title="Sprint 2 Review — build-dashboard",
        mission="build-dashboard",
        sprint=2,
        project="SCM_WORK",
        participants=[
            ("meeting-coordinator", "facilitator"),
            ("code-worker", "participant"),
            ("harness-validator", "participant"),
        ],
    )
    assert isinstance(meeting, Meeting)
    assert meeting.meeting_id.startswith("m-")
    assert meeting.gate_type == "sprint_review"
    assert meeting.status == "open"

    meta_path = tmp_meetings_dir / meeting.meeting_id / "meta.yaml"
    jsonl_path = tmp_meetings_dir / meeting.meeting_id / "discussion.jsonl"
    assert meta_path.exists()
    assert jsonl_path.exists()
    assert jsonl_path.read_text() == ""

    meta = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
    assert meta["gate_type"] == "sprint_review"
    assert meta["status"] == "open"
    assert meta["mission"] == "build-dashboard"
    assert meta["sprint"] == 2
    assert len(meta["participants"]) == 3
    for p in meta["participants"]:
        assert p["posted"] is False


def test_open_updates_active_yaml(tmp_meetings_dir):
    meeting = open_meeting(
        base_dir=tmp_meetings_dir,
        gate_type="sprint_review",
        title="t",
        mission="m",
        sprint=1,
        project="P",
        participants=[("meeting-coordinator", "facilitator")],
    )
    active = yaml.safe_load((tmp_meetings_dir / "active.yaml").read_text(encoding="utf-8"))
    assert len(active["open_meetings"]) == 1
    assert active["open_meetings"][0]["meeting_id"] == meeting.meeting_id
    assert active["open_meetings"][0]["gate_type"] == "sprint_review"


def test_open_appends_to_index(tmp_meetings_dir):
    meeting = open_meeting(
        base_dir=tmp_meetings_dir,
        gate_type="sprint_review",
        title="t",
        mission="m",
        sprint=1,
        project="P",
        participants=[("meeting-coordinator", "facilitator")],
    )
    index_lines = (tmp_meetings_dir / "INDEX.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(index_lines) == 1
    import json
    entry = json.loads(index_lines[0])
    assert entry["event"] == "opened"
    assert entry["meeting_id"] == meeting.meeting_id
    assert entry["gate_type"] == "sprint_review"


def test_open_two_meetings_with_same_id_appends_suffix(tmp_meetings_dir):
    common_kwargs = dict(
        base_dir=tmp_meetings_dir,
        gate_type="sprint_review",
        title="t",
        mission="m",
        sprint=1,
        project="P",
        participants=[("meeting-coordinator", "facilitator")],
        _now_iso="2026-05-15T14:00:00Z",  # forces same id
    )
    m1 = open_meeting(**common_kwargs)
    m2 = open_meeting(**common_kwargs)
    assert m1.meeting_id != m2.meeting_id
    assert m2.meeting_id.endswith("-2")


def test_open_two_concurrent_meetings_both_in_active(tmp_meetings_dir):
    m1 = open_meeting(
        base_dir=tmp_meetings_dir,
        gate_type="sprint_review",
        title="sprint review",
        mission="m",
        sprint=1,
        project="P",
        participants=[("meeting-coordinator", "facilitator")],
    )
    m2 = open_meeting(
        base_dir=tmp_meetings_dir,
        gate_type="checkpoint",
        title="cp 4h",
        mission="m",
        sprint=1,
        project="P",
        participants=[("checkpoint-reporter", "facilitator")],
    )
    active = yaml.safe_load((tmp_meetings_dir / "active.yaml").read_text(encoding="utf-8"))
    ids = {entry["meeting_id"] for entry in active["open_meetings"]}
    assert ids == {m1.meeting_id, m2.meeting_id}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest "$env:USERPROFILE/.claude/harness/scripts/tests/test_meeting_storage.py" -v`
Expected: 5 new test errors (`ImportError: cannot import name 'open_meeting'`).

- [ ] **Step 3: Extend `meeting_storage.py` with `Meeting` + `open_meeting`**

Append the following to `~/.claude/harness/scripts/meeting_storage.py`:

```python
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence, Tuple
import yaml

DEFAULT_BASE_DIR = Path.home() / ".claude" / "harness" / "meetings"

GATE_SHORT = {
    "sprint_review": lambda mission, sprint, *_: f"sprint{sprint}-review",
    "checkpoint": lambda mission, sprint, suffix: f"cp{suffix or '4h'}",
    "observation": lambda mission, sprint, suffix: f"observation-{suffix or 'adhoc'}",
}


class MeetingExistsError(RuntimeError):
    """Raised when a meeting id collides and no suffix could be assigned."""


@dataclass
class Meeting:
    meeting_id: str
    gate_type: str
    opened_at: str
    closed_at: Optional[str]
    status: str
    mission: Optional[str]
    sprint: Optional[int]
    project: Optional[str]
    title: str
    participants: List[dict]
    triggered_by: Optional[dict]
    notion: dict


def _now_iso_default() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _candidate_meeting_id(gate_type, mission, sprint, now_iso, suffix=None):
    date_part = now_iso[:10]
    short = GATE_SHORT[gate_type](mission, sprint, suffix)
    return f"m-{date_part}-{short}"


def _read_active(base_dir: Path) -> dict:
    path = base_dir / "active.yaml"
    if not path.exists():
        return {"open_meetings": []}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {"open_meetings": []}
    if "open_meetings" not in loaded or not isinstance(loaded["open_meetings"], list):
        return {"open_meetings": []}
    return loaded


def _write_active(base_dir: Path, data: dict) -> None:
    path = base_dir / "active.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _append_index(base_dir: Path, entry: dict) -> None:
    path = base_dir / "INDEX.jsonl"
    line = json.dumps(entry, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def open_meeting(
    *,
    base_dir: Path,
    gate_type: str,
    title: str,
    mission: Optional[str],
    sprint: Optional[int],
    project: Optional[str],
    participants: Sequence[Tuple[str, str]],
    triggered_by: Optional[dict] = None,
    _now_iso: Optional[str] = None,
) -> Meeting:
    if gate_type not in GATE_SHORT:
        raise ValueError(f"unknown gate_type: {gate_type!r}")
    now_iso = _now_iso or _now_iso_default()

    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)

    # Resolve meeting_id with collision suffix
    candidate = _candidate_meeting_id(gate_type, mission, sprint, now_iso)
    meeting_id = candidate
    suffix = 2
    while (base_dir / meeting_id).exists():
        meeting_id = f"{candidate}-{suffix}"
        suffix += 1
        if suffix > 99:
            raise MeetingExistsError(f"too many collisions for {candidate}")

    meeting_dir = base_dir / meeting_id
    meeting_dir.mkdir()  # raises FileExistsError if race (acceptable; will retry caller-side)

    participants_data = [
        {"agent": agent, "role": role, "posted": False}
        for agent, role in participants
    ]

    meta = {
        "meeting_id": meeting_id,
        "gate_type": gate_type,
        "opened_at": now_iso,
        "closed_at": None,
        "status": "open",
        "mission": mission,
        "sprint": sprint,
        "project": project,
        "title": title,
        "participants": participants_data,
        "triggered_by": triggered_by,
        "notion": {
            "page_id": None,
            "url": None,
            "rendered_at": None,
            "render_attempts": 0,
        },
    }
    (meeting_dir / "meta.yaml").write_text(
        yaml.safe_dump(meta, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    (meeting_dir / "discussion.jsonl").write_text("", encoding="utf-8")

    # Update active.yaml
    active = _read_active(base_dir)
    active["open_meetings"].append(
        {"meeting_id": meeting_id, "gate_type": gate_type, "opened_at": now_iso}
    )
    _write_active(base_dir, active)

    # Append INDEX
    _append_index(base_dir, {
        "ts": now_iso,
        "event": "opened",
        "meeting_id": meeting_id,
        "gate_type": gate_type,
    })

    return Meeting(
        meeting_id=meeting_id,
        gate_type=gate_type,
        opened_at=now_iso,
        closed_at=None,
        status="open",
        mission=mission,
        sprint=sprint,
        project=project,
        title=title,
        participants=participants_data,
        triggered_by=triggered_by,
        notion=meta["notion"],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest "$env:USERPROFILE/.claude/harness/scripts/tests/test_meeting_storage.py" -v`
Expected: 12 passed (7 prior + 5 new).

- [ ] **Step 5: Commit**

```powershell
cd $env:USERPROFILE\.claude
git add harness/scripts/meeting_storage.py harness/scripts/tests/test_meeting_storage.py
git commit -m "harness(meetings): open_meeting + active.yaml + INDEX.jsonl"
cd $env:USERPROFILE\Desktop\SCM_WORK
```

---

### Task 4: Append post — write JSONL line + mark participant posted

**Files:**
- Modify: `~/.claude/harness/scripts/meeting_storage.py` (add `append_post`, `load_meeting`)
- Modify: `~/.claude/harness/scripts/tests/test_meeting_storage.py`

- [ ] **Step 1: Write failing tests for `append_post`**

Append to `~/.claude/harness/scripts/tests/test_meeting_storage.py`:

```python
from scripts.meeting_storage import append_post, load_meeting, ParticipantNotInMeetingError


def _make_meeting(tmp_meetings_dir, **overrides):
    kwargs = dict(
        base_dir=tmp_meetings_dir,
        gate_type="sprint_review",
        title="Sprint 2 Review",
        mission="build-dashboard",
        sprint=2,
        project="SCM_WORK",
        participants=[
            ("meeting-coordinator", "facilitator"),
            ("code-worker", "participant"),
            ("harness-validator", "participant"),
        ],
    )
    kwargs.update(overrides)
    return open_meeting(**kwargs)


def test_append_post_writes_jsonl_line(tmp_meetings_dir):
    meeting = _make_meeting(tmp_meetings_dir)
    post = Post(
        ts="2026-05-15T14:05:12Z",
        agent="code-worker",
        stance="claim",
        refs=[],
        summary="POST /shipments 구현 완료",
        evidence=["pytest 12/12 pass"],
        concerns=[],
        contract_items=["C3", "C4"],
    )
    append_post(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id, post=post)
    jsonl = (tmp_meetings_dir / meeting.meeting_id / "discussion.jsonl").read_text(encoding="utf-8")
    lines = jsonl.strip().splitlines()
    assert len(lines) == 1
    import json
    entry = json.loads(lines[0])
    assert entry["agent"] == "code-worker"
    assert entry["stance"] == "claim"
    assert entry["summary"] == "POST /shipments 구현 완료"
    assert entry["contract_items"] == ["C3", "C4"]


def test_append_post_marks_participant_posted(tmp_meetings_dir):
    meeting = _make_meeting(tmp_meetings_dir)
    post = Post(
        ts="2026-05-15T14:05:12Z",
        agent="code-worker",
        stance="claim",
        refs=[],
        summary="done",
        evidence=[],
        concerns=[],
    )
    append_post(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id, post=post)
    loaded = load_meeting(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id)
    by_agent = {p["agent"]: p["posted"] for p in loaded.participants}
    assert by_agent["code-worker"] is True
    assert by_agent["harness-validator"] is False


def test_append_post_rejects_non_participant(tmp_meetings_dir):
    meeting = _make_meeting(tmp_meetings_dir)
    post = Post(
        ts="2026-05-15T14:05:12Z",
        agent="rogue-agent",
        stance="claim",
        refs=[],
        summary="not in participants",
        evidence=[],
        concerns=[],
    )
    with pytest.raises(ParticipantNotInMeetingError, match="rogue-agent"):
        append_post(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id, post=post)


def test_append_post_runs_validation(tmp_meetings_dir):
    meeting = _make_meeting(tmp_meetings_dir)
    bad_post = Post(
        ts="2026-05-15T14:05:12Z",
        agent="harness-validator",
        stance="agree",
        refs=[],  # missing refs for agree
        summary="agree",
        evidence=[],
        concerns=[],
    )
    with pytest.raises(PostValidationError, match="agree.*requires.*refs"):
        append_post(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id, post=bad_post)


def test_append_multiple_posts_preserves_order(tmp_meetings_dir):
    meeting = _make_meeting(tmp_meetings_dir)
    posts = [
        Post(
            ts=f"2026-05-15T14:0{i}:00Z",
            agent="code-worker" if i == 0 else "harness-validator",
            stance="claim" if i == 0 else "agree",
            refs=[] if i == 0 else ["code-worker@2026-05-15T14:00:00Z"],
            summary=f"post {i}",
            evidence=[],
            concerns=[],
        )
        for i in range(2)
    ]
    for p in posts:
        append_post(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id, post=p)
    lines = (tmp_meetings_dir / meeting.meeting_id / "discussion.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    import json
    assert json.loads(lines[0])["summary"] == "post 0"
    assert json.loads(lines[1])["summary"] == "post 1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest "$env:USERPROFILE/.claude/harness/scripts/tests/test_meeting_storage.py" -v`
Expected: 5 new errors (`ImportError: cannot import name 'append_post'`).

- [ ] **Step 3: Implement `append_post` and `load_meeting` in `meeting_storage.py`**

Append to `~/.claude/harness/scripts/meeting_storage.py`:

```python
class ParticipantNotInMeetingError(RuntimeError):
    """Raised when a post's agent isn't listed in the meeting participants."""


class MeetingNotFoundError(FileNotFoundError):
    """Raised when a meeting_id directory doesn't exist."""


def load_meeting(*, base_dir: Path, meeting_id: str) -> Meeting:
    meeting_dir = Path(base_dir) / meeting_id
    if not meeting_dir.exists():
        raise MeetingNotFoundError(f"no meeting: {meeting_id}")
    meta = yaml.safe_load((meeting_dir / "meta.yaml").read_text(encoding="utf-8"))
    return Meeting(
        meeting_id=meta["meeting_id"],
        gate_type=meta["gate_type"],
        opened_at=meta["opened_at"],
        closed_at=meta.get("closed_at"),
        status=meta.get("status", "open"),
        mission=meta.get("mission"),
        sprint=meta.get("sprint"),
        project=meta.get("project"),
        title=meta["title"],
        participants=meta.get("participants", []),
        triggered_by=meta.get("triggered_by"),
        notion=meta.get("notion") or {
            "page_id": None,
            "url": None,
            "rendered_at": None,
            "render_attempts": 0,
        },
    )


def _save_meta(meeting_dir: Path, meeting: Meeting) -> None:
    meta = {
        "meeting_id": meeting.meeting_id,
        "gate_type": meeting.gate_type,
        "opened_at": meeting.opened_at,
        "closed_at": meeting.closed_at,
        "status": meeting.status,
        "mission": meeting.mission,
        "sprint": meeting.sprint,
        "project": meeting.project,
        "title": meeting.title,
        "participants": meeting.participants,
        "triggered_by": meeting.triggered_by,
        "notion": meeting.notion,
    }
    (meeting_dir / "meta.yaml").write_text(
        yaml.safe_dump(meta, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def append_post(*, base_dir: Path, meeting_id: str, post: Post) -> None:
    base_dir = Path(base_dir)
    meeting_dir = base_dir / meeting_id
    if not meeting_dir.exists():
        raise MeetingNotFoundError(f"no meeting: {meeting_id}")

    validate_post(post)

    meeting = load_meeting(base_dir=base_dir, meeting_id=meeting_id)
    known_agents = {p["agent"] for p in meeting.participants}
    if post.agent not in known_agents:
        raise ParticipantNotInMeetingError(
            f"{post.agent!r} not in participants {sorted(known_agents)}"
        )

    payload = {
        "ts": post.ts,
        "agent": post.agent,
        "stance": post.stance,
        "refs": post.refs,
        "summary": post.summary,
        "evidence": post.evidence,
        "concerns": post.concerns,
    }
    if post.contract_items:
        payload["contract_items"] = post.contract_items
    if post.action_items:
        payload["action_items"] = post.action_items

    line = json.dumps(payload, ensure_ascii=False)
    with (meeting_dir / "discussion.jsonl").open("a", encoding="utf-8") as f:
        f.write(line + "\n")

    # Mark participant as posted
    for p in meeting.participants:
        if p["agent"] == post.agent:
            p["posted"] = True
            break
    _save_meta(meeting_dir, meeting)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest "$env:USERPROFILE/.claude/harness/scripts/tests/test_meeting_storage.py" -v`
Expected: 17 passed (12 prior + 5 new).

- [ ] **Step 5: Commit**

```powershell
cd $env:USERPROFILE\.claude
git add harness/scripts/meeting_storage.py harness/scripts/tests/test_meeting_storage.py
git commit -m "harness(meetings): append_post + load_meeting + participant tracking"
cd $env:USERPROFILE\Desktop\SCM_WORK
```

---

### Task 5: Close meeting — validate refs + require synthesis + update status

**Files:**
- Modify: `~/.claude/harness/scripts/meeting_storage.py` (add `close_meeting`, `load_posts`)
- Modify: `~/.claude/harness/scripts/tests/test_meeting_storage.py`

- [ ] **Step 1: Write failing tests for `close_meeting`**

Append to `~/.claude/harness/scripts/tests/test_meeting_storage.py`:

```python
from scripts.meeting_storage import (
    close_meeting,
    load_posts,
    SynthesisMissingError,
    RefIntegrityError,
    MeetingNotOpenError,
)


def _post(ts, agent, stance="claim", refs=None, summary="x", action_items=None):
    return Post(
        ts=ts,
        agent=agent,
        stance=stance,
        refs=refs or [],
        summary=summary,
        evidence=[],
        concerns=[],
        action_items=action_items or [],
    )


def test_close_succeeds_with_synthesis_last(tmp_meetings_dir):
    meeting = _make_meeting(tmp_meetings_dir)
    append_post(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id,
                post=_post("2026-05-15T14:00:00Z", "code-worker"))
    append_post(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id,
                post=_post("2026-05-15T14:05:00Z", "harness-validator",
                           stance="agree",
                           refs=["code-worker@2026-05-15T14:00:00Z"]))
    append_post(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id,
                post=_post("2026-05-15T14:30:00Z", "meeting-coordinator",
                           stance="synthesis", action_items=["follow up"]))
    closed = close_meeting(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id)
    assert closed.status == "closed"
    assert closed.closed_at is not None


def test_close_fails_without_synthesis(tmp_meetings_dir):
    meeting = _make_meeting(tmp_meetings_dir)
    append_post(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id,
                post=_post("2026-05-15T14:00:00Z", "code-worker"))
    with pytest.raises(SynthesisMissingError):
        close_meeting(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id)


def test_close_fails_if_synthesis_not_last(tmp_meetings_dir):
    meeting = _make_meeting(tmp_meetings_dir)
    append_post(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id,
                post=_post("2026-05-15T14:00:00Z", "meeting-coordinator",
                           stance="synthesis"))
    append_post(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id,
                post=_post("2026-05-15T14:05:00Z", "code-worker"))
    with pytest.raises(SynthesisMissingError, match="must be last"):
        close_meeting(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id)


def test_close_fails_on_dangling_refs(tmp_meetings_dir):
    meeting = _make_meeting(tmp_meetings_dir)
    append_post(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id,
                post=_post("2026-05-15T14:00:00Z", "code-worker"))
    append_post(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id,
                post=_post("2026-05-15T14:05:00Z", "harness-validator",
                           stance="agree",
                           refs=["nonexistent-agent@2026-05-15T00:00:00Z"]))
    append_post(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id,
                post=_post("2026-05-15T14:30:00Z", "meeting-coordinator",
                           stance="synthesis"))
    with pytest.raises(RefIntegrityError, match="nonexistent-agent"):
        close_meeting(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id)


def test_close_removes_from_active(tmp_meetings_dir):
    meeting = _make_meeting(tmp_meetings_dir)
    append_post(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id,
                post=_post("2026-05-15T14:30:00Z", "meeting-coordinator",
                           stance="synthesis"))
    close_meeting(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id)
    active = yaml.safe_load((tmp_meetings_dir / "active.yaml").read_text(encoding="utf-8"))
    assert active["open_meetings"] == []


def test_close_appends_index_event(tmp_meetings_dir):
    meeting = _make_meeting(tmp_meetings_dir)
    append_post(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id,
                post=_post("2026-05-15T14:30:00Z", "meeting-coordinator",
                           stance="synthesis"))
    close_meeting(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id)
    lines = (tmp_meetings_dir / "INDEX.jsonl").read_text(encoding="utf-8").splitlines()
    import json
    events = [json.loads(line)["event"] for line in lines]
    assert events == ["opened", "closed"]


def test_close_twice_raises_meeting_not_open(tmp_meetings_dir):
    meeting = _make_meeting(tmp_meetings_dir)
    append_post(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id,
                post=_post("2026-05-15T14:30:00Z", "meeting-coordinator",
                           stance="synthesis"))
    close_meeting(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id)
    with pytest.raises(MeetingNotOpenError):
        close_meeting(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id)


def test_load_posts_returns_all_in_order(tmp_meetings_dir):
    meeting = _make_meeting(tmp_meetings_dir)
    append_post(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id,
                post=_post("2026-05-15T14:00:00Z", "code-worker", summary="first"))
    append_post(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id,
                post=_post("2026-05-15T14:05:00Z", "harness-validator",
                           stance="agree", refs=["code-worker@2026-05-15T14:00:00Z"],
                           summary="second"))
    posts = load_posts(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id)
    assert [p.summary for p in posts] == ["first", "second"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest "$env:USERPROFILE/.claude/harness/scripts/tests/test_meeting_storage.py" -v`
Expected: 8 new errors (`ImportError: cannot import name 'close_meeting'`).

- [ ] **Step 3: Implement `close_meeting` and `load_posts`**

Append to `~/.claude/harness/scripts/meeting_storage.py`:

```python
class SynthesisMissingError(RuntimeError):
    """Raised when close attempt finds no synthesis or synthesis isn't last."""


class RefIntegrityError(RuntimeError):
    """Raised when a post's refs point to non-existent prior posts."""


class MeetingNotOpenError(RuntimeError):
    """Raised when close_meeting is called on an already-closed meeting."""


def load_posts(*, base_dir: Path, meeting_id: str) -> List[Post]:
    base_dir = Path(base_dir)
    jsonl_path = base_dir / meeting_id / "discussion.jsonl"
    if not jsonl_path.exists():
        raise MeetingNotFoundError(f"no meeting: {meeting_id}")
    posts: List[Post] = []
    for raw in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Partial / corrupt last line — skip; caller may mark degraded.
            continue
        posts.append(Post(
            ts=data["ts"],
            agent=data["agent"],
            stance=data["stance"],
            refs=data.get("refs", []),
            summary=data["summary"],
            evidence=data.get("evidence", []),
            concerns=data.get("concerns", []),
            contract_items=data.get("contract_items", []),
            action_items=data.get("action_items", []),
        ))
    return posts


def _post_key(post: Post) -> str:
    return f"{post.agent}@{post.ts}"


def close_meeting(*, base_dir: Path, meeting_id: str, _now_iso: Optional[str] = None) -> Meeting:
    base_dir = Path(base_dir)
    meeting = load_meeting(base_dir=base_dir, meeting_id=meeting_id)
    if meeting.status != "open":
        raise MeetingNotOpenError(f"meeting {meeting_id} status={meeting.status}")

    posts = load_posts(base_dir=base_dir, meeting_id=meeting_id)
    if not posts or posts[-1].stance != "synthesis":
        raise SynthesisMissingError(
            f"meeting {meeting_id} requires a synthesis post as the last entry; must be last"
        )

    # Ref integrity check
    keys = {_post_key(p) for p in posts}
    for p in posts:
        for r in p.refs:
            if r not in keys:
                raise RefIntegrityError(
                    f"post {_post_key(p)} refs unknown post {r!r}"
                )

    now_iso = _now_iso or _now_iso_default()
    meeting.status = "closed"
    meeting.closed_at = now_iso
    _save_meta(base_dir / meeting_id, meeting)

    # Remove from active.yaml
    active = _read_active(base_dir)
    active["open_meetings"] = [
        e for e in active["open_meetings"] if e["meeting_id"] != meeting_id
    ]
    _write_active(base_dir, active)

    # Append INDEX
    _append_index(base_dir, {
        "ts": now_iso,
        "event": "closed",
        "meeting_id": meeting_id,
        "gate_type": meeting.gate_type,
    })

    return meeting
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest "$env:USERPROFILE/.claude/harness/scripts/tests/test_meeting_storage.py" -v`
Expected: 25 passed (17 prior + 8 new).

- [ ] **Step 5: Commit**

```powershell
cd $env:USERPROFILE\.claude
git add harness/scripts/meeting_storage.py harness/scripts/tests/test_meeting_storage.py
git commit -m "harness(meetings): close_meeting + ref integrity + synthesis-last validation"
cd $env:USERPROFILE\Desktop\SCM_WORK
```

---

### Task 6: Render — sprint_review top half (synthesis prose)

**Files:**
- Create: `~/.claude/harness/scripts/render_meeting.py`
- Create: `~/.claude/harness/scripts/tests/test_render_meeting.py`

- [ ] **Step 1: Write failing tests for `render_top_half_sprint_review`**

File: `~/.claude/harness/scripts/tests/test_render_meeting.py`

```python
import pytest
from scripts.meeting_storage import (
    open_meeting, append_post, close_meeting, Post,
)
from scripts.render_meeting import (
    render_top_half,
    render_bottom_half,
    render_meeting_to_blocks,
    UnsupportedGateError,
)


def _seed_sprint_review(tmp_meetings_dir):
    meeting = open_meeting(
        base_dir=tmp_meetings_dir,
        gate_type="sprint_review",
        title="Sprint 2 Review — build-dashboard",
        mission="build-dashboard",
        sprint=2,
        project="SCM_WORK",
        participants=[
            ("meeting-coordinator", "facilitator"),
            ("code-worker", "participant"),
            ("data-worker", "participant"),
            ("harness-validator", "participant"),
        ],
    )
    append_post(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id, post=Post(
        ts="2026-05-15T14:05:12Z", agent="code-worker", stance="claim", refs=[],
        summary="POST /shipments 구현 완료 — C3·C4 충족",
        evidence=["tests/test_shipments.py 12/12 pass", "git HEAD abc1234"],
        concerns=[], contract_items=["C3", "C4"],
    ))
    append_post(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id, post=Post(
        ts="2026-05-15T14:08:33Z", agent="data-worker", stance="claim", refs=[],
        summary="tms_shipments 백필 794건 완료",
        evidence=["batch_size=10", "duration=4m12s"],
        concerns=["TO-238 1건 누락 — Project_PNA null"],
        contract_items=["C5"],
    ))
    append_post(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id, post=Post(
        ts="2026-05-15T14:15:02Z", agent="harness-validator", stance="agree",
        refs=["code-worker@2026-05-15T14:05:12Z"],
        summary="code-worker C3·C4 증거 검증 통과",
        evidence=["pytest output 확인"], concerns=[], contract_items=["C3", "C4"],
    ))
    append_post(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id, post=Post(
        ts="2026-05-15T14:18:44Z", agent="harness-validator", stance="disagree",
        refs=["data-worker@2026-05-15T14:08:33Z"],
        summary="TO-238 누락은 Contract C5 미충족",
        evidence=["meta C5='794 records OR explicit skip rationale' — skip 사유 누락"],
        concerns=["다음 Sprint에서 보완 필요"], contract_items=["C5"],
    ))
    append_post(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id, post=Post(
        ts="2026-05-15T14:30:00Z", agent="meeting-coordinator", stance="synthesis",
        refs=[],
        summary="C3·C4 통과, C5 부분 충족(794/795). TO-238 carry-over 권고.",
        evidence=[], concerns=[],
        action_items=["다음 Sprint Plan에 TO-238 backfill 포함",
                      "Contract C5 수정 권고 — '명시적 skip 사유 동시 요구'"],
    ))
    close_meeting(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id)
    return meeting.meeting_id


def test_top_half_sprint_review_contains_synthesis_summary(tmp_meetings_dir):
    meeting_id = _seed_sprint_review(tmp_meetings_dir)
    blocks = render_top_half(base_dir=tmp_meetings_dir, meeting_id=meeting_id)
    assert isinstance(blocks, list)
    text_blob = _flatten_block_text(blocks)
    assert "스프린트 결과 요약" in text_blob
    assert "C3·C4 통과, C5 부분 충족" in text_blob


def test_top_half_sprint_review_lists_passed_contract_items(tmp_meetings_dir):
    meeting_id = _seed_sprint_review(tmp_meetings_dir)
    blocks = render_top_half(base_dir=tmp_meetings_dir, meeting_id=meeting_id)
    text_blob = _flatten_block_text(blocks)
    assert "통과한 Contract Items" in text_blob
    assert "C3" in text_blob
    assert "C4" in text_blob


def test_top_half_sprint_review_lists_action_items(tmp_meetings_dir):
    meeting_id = _seed_sprint_review(tmp_meetings_dir)
    blocks = render_top_half(base_dir=tmp_meetings_dir, meeting_id=meeting_id)
    text_blob = _flatten_block_text(blocks)
    assert "Action Items" in text_blob
    assert "TO-238 backfill" in text_blob


def test_top_half_sprint_review_attributes_agreements(tmp_meetings_dir):
    meeting_id = _seed_sprint_review(tmp_meetings_dir)
    blocks = render_top_half(base_dir=tmp_meetings_dir, meeting_id=meeting_id)
    text_blob = _flatten_block_text(blocks)
    # "원인 분석 (agent 합의 표시)" pattern — agree posts named explicitly
    assert "harness-validator" in text_blob


def test_top_half_unsupported_gate_raises(tmp_meetings_dir):
    meeting = open_meeting(
        base_dir=tmp_meetings_dir,
        gate_type="checkpoint",
        title="cp 4h",
        mission="m",
        sprint=1,
        project="P",
        participants=[("checkpoint-reporter", "facilitator")],
    )
    append_post(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id, post=Post(
        ts="2026-05-15T14:30:00Z", agent="checkpoint-reporter", stance="synthesis",
        refs=[], summary="cp synthesis", evidence=[], concerns=[],
    ))
    close_meeting(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id)
    with pytest.raises(UnsupportedGateError):
        render_top_half(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id)


def _flatten_block_text(blocks):
    """Helper to concatenate all visible text from a Notion block list."""
    out = []
    for b in blocks:
        if isinstance(b, dict):
            # Block dict — walk known text-bearing fields
            for k, v in b.items():
                if isinstance(v, dict) and "rich_text" in v:
                    for rt in v["rich_text"]:
                        if isinstance(rt, dict) and "text" in rt:
                            out.append(rt["text"].get("content", ""))
                elif isinstance(v, list):
                    out.append(_flatten_block_text(v))
                elif isinstance(v, dict):
                    out.append(_flatten_block_text([v]))
    return " ".join(s for s in out if s)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest "$env:USERPROFILE/.claude/harness/scripts/tests/test_render_meeting.py" -v`
Expected: `ModuleNotFoundError: No module named 'scripts.render_meeting'`.

- [ ] **Step 3: Create `render_meeting.py` with `render_top_half` for sprint_review**

File: `~/.claude/harness/scripts/render_meeting.py`

```python
"""Render a closed meeting into Notion-ready block payload."""
from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any

from scripts.meeting_storage import (
    Meeting,
    Post,
    load_meeting,
    load_posts,
)


class UnsupportedGateError(NotImplementedError):
    """Raised when a render template is not yet implemented for a gate."""


SUPPORTED_TOP_HALF_GATES = {"sprint_review"}  # Plan A scope; observation/checkpoint added in Plan C


def _text(content: str) -> Dict[str, Any]:
    return {"type": "text", "text": {"content": content}}


def _heading_2(content: str) -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [_text(content)]},
    }


def _paragraph(content: str) -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [_text(content)]},
    }


def _bullet(content: str) -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": [_text(content)]},
    }


def render_top_half(*, base_dir: Path, meeting_id: str) -> List[Dict[str, Any]]:
    meeting = load_meeting(base_dir=base_dir, meeting_id=meeting_id)
    if meeting.gate_type not in SUPPORTED_TOP_HALF_GATES:
        raise UnsupportedGateError(
            f"top-half template for gate {meeting.gate_type!r} not implemented "
            f"in this plan (sprint_review only). Add in Plan C."
        )
    posts = load_posts(base_dir=base_dir, meeting_id=meeting_id)
    return _render_sprint_review_top(meeting, posts)


def _render_sprint_review_top(meeting: Meeting, posts: List[Post]) -> List[Dict[str, Any]]:
    synthesis = next((p for p in reversed(posts) if p.stance == "synthesis"), None)
    if synthesis is None:
        raise RuntimeError(
            f"meeting {meeting.meeting_id} has no synthesis post; "
            f"this shouldn't happen for a closed meeting"
        )

    blocks: List[Dict[str, Any]] = []

    # 1. 스프린트 결과 요약
    blocks.append(_heading_2("스프린트 결과 요약"))
    blocks.append(_paragraph(synthesis.summary))

    # 2. 통과한 Contract Items
    passed = sorted({
        ci
        for p in posts
        if p.stance == "agree"
        for ci in p.contract_items
    })
    if passed:
        blocks.append(_heading_2("통과한 Contract Items"))
        for ci in passed:
            agree_posts = [
                p for p in posts
                if p.stance == "agree" and ci in p.contract_items
            ]
            attribution = ", ".join(p.agent for p in agree_posts)
            blocks.append(_bullet(f"{ci} — 검증: {attribution}"))

    # 3. Carry-over (disagree posts indicate non-passing items)
    failed = sorted({
        ci
        for p in posts
        if p.stance == "disagree"
        for ci in p.contract_items
    })
    if failed:
        blocks.append(_heading_2("Carry-over"))
        for ci in failed:
            disagree_posts = [
                p for p in posts
                if p.stance == "disagree" and ci in p.contract_items
            ]
            reason = disagree_posts[0].summary if disagree_posts else ""
            blocks.append(_bullet(f"{ci} — {reason}"))

    # 4. 회고: Went well / Got stuck / Learned — derived heuristically
    blocks.append(_heading_2("회고"))
    went_well = [p for p in posts if p.stance == "agree"]
    got_stuck = [c for p in posts for c in p.concerns]
    if went_well:
        blocks.append(_paragraph(
            f"Went well: {', '.join(p.summary for p in went_well[:3])}"
        ))
    if got_stuck:
        blocks.append(_paragraph(
            f"Got stuck: {'; '.join(got_stuck[:3])}"
        ))

    # 5. Action Items
    if synthesis.action_items:
        blocks.append(_heading_2("Action Items"))
        for item in synthesis.action_items:
            blocks.append(_bullet(item))

    return blocks


# Bottom half + full render — implemented in Task 7
def render_bottom_half(*, base_dir: Path, meeting_id: str) -> List[Dict[str, Any]]:
    raise NotImplementedError("implemented in Task 7")


def render_meeting_to_blocks(*, base_dir: Path, meeting_id: str) -> List[Dict[str, Any]]:
    raise NotImplementedError("implemented in Task 7")
```

- [ ] **Step 4: Run tests to verify the top-half tests pass**

Run: `py -m pytest "$env:USERPROFILE/.claude/harness/scripts/tests/test_render_meeting.py" -v -k "top_half"`
Expected: 5 passed (the four `test_top_half_sprint_review_*` tests + `test_top_half_unsupported_gate_raises`).

- [ ] **Step 5: Commit**

```powershell
cd $env:USERPROFILE\.claude
git add harness/scripts/render_meeting.py harness/scripts/tests/test_render_meeting.py
git commit -m "harness(meetings): render top half — sprint_review template"
cd $env:USERPROFILE\Desktop\SCM_WORK
```

---

### Task 7: Render — bottom-half discussion log + full meeting render

**Files:**
- Modify: `~/.claude/harness/scripts/render_meeting.py` (implement `render_bottom_half` + `render_meeting_to_blocks`)
- Modify: `~/.claude/harness/scripts/tests/test_render_meeting.py` (append tests)

- [ ] **Step 1: Write failing tests for `render_bottom_half` and `render_meeting_to_blocks`**

Append to `~/.claude/harness/scripts/tests/test_render_meeting.py`:

```python
def test_bottom_half_toggle_contains_post_count(tmp_meetings_dir):
    meeting_id = _seed_sprint_review(tmp_meetings_dir)
    blocks = render_bottom_half(base_dir=tmp_meetings_dir, meeting_id=meeting_id)
    text_blob = _flatten_block_text(blocks)
    # 5 posts total in seed
    assert "5 posts" in text_blob
    assert "💬 Agent Discussion Log" in text_blob


def test_bottom_half_includes_every_post(tmp_meetings_dir):
    meeting_id = _seed_sprint_review(tmp_meetings_dir)
    blocks = render_bottom_half(base_dir=tmp_meetings_dir, meeting_id=meeting_id)
    text_blob = _flatten_block_text(blocks)
    for needle in [
        "POST /shipments 구현 완료",
        "tms_shipments 백필 794건 완료",
        "code-worker C3·C4 증거 검증 통과",
        "TO-238 누락",
        "C3·C4 통과, C5 부분 충족",
    ]:
        assert needle in text_blob, f"missing in bottom half: {needle}"


def test_bottom_half_marks_disagree_post(tmp_meetings_dir):
    meeting_id = _seed_sprint_review(tmp_meetings_dir)
    blocks = render_bottom_half(base_dir=tmp_meetings_dir, meeting_id=meeting_id)
    text_blob = _flatten_block_text(blocks)
    assert "🔻" in text_blob  # disagree marker


def test_render_meeting_to_blocks_combines_top_and_bottom(tmp_meetings_dir):
    meeting_id = _seed_sprint_review(tmp_meetings_dir)
    blocks = render_meeting_to_blocks(base_dir=tmp_meetings_dir, meeting_id=meeting_id)
    text_blob = _flatten_block_text(blocks)
    # Both sections appear
    assert "스프린트 결과 요약" in text_blob       # top
    assert "💬 Agent Discussion Log" in text_blob  # bottom


def test_render_open_meeting_raises(tmp_meetings_dir):
    """Closed-meeting precondition: rendering an open meeting is an error."""
    meeting = open_meeting(
        base_dir=tmp_meetings_dir,
        gate_type="sprint_review",
        title="t",
        mission="m",
        sprint=1,
        project="P",
        participants=[("meeting-coordinator", "facilitator")],
    )
    with pytest.raises(RuntimeError, match="not closed"):
        render_meeting_to_blocks(base_dir=tmp_meetings_dir, meeting_id=meeting.meeting_id)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest "$env:USERPROFILE/.claude/harness/scripts/tests/test_render_meeting.py" -v -k "bottom_half or render_meeting_to_blocks or render_open_meeting"`
Expected: 5 errors (`NotImplementedError`).

- [ ] **Step 3: Implement `render_bottom_half` and `render_meeting_to_blocks`**

Replace the placeholder bottom half / full render in `~/.claude/harness/scripts/render_meeting.py` with this complete implementation (find the two `raise NotImplementedError(...)` lines and replace with the bodies below):

```python
STANCE_ICON = {
    "claim": "▸",
    "agree": "✅",
    "disagree": "🔻",
    "question": "❓",
    "answer": "↪",
    "synthesis": "☑️",
}


def _toggle(summary_text: str, children: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "object": "block",
        "type": "toggle",
        "toggle": {
            "rich_text": [_text(summary_text)],
            "children": children,
        },
    }


def _format_post_header(post: Post) -> str:
    icon = STANCE_ICON.get(post.stance, "•")
    time_short = post.ts[11:16] if "T" in post.ts else post.ts
    head = f"{icon} [{post.agent} · {post.stance} · {time_short}]"
    if post.refs:
        head += f" → {', '.join(post.refs)}"
    return head


def _post_children(post: Post) -> List[Dict[str, Any]]:
    children: List[Dict[str, Any]] = []
    children.append(_paragraph(post.summary))
    if post.evidence:
        children.append(_paragraph("Evidence:"))
        for e in post.evidence:
            children.append(_bullet(e))
    if post.contract_items:
        children.append(_paragraph(f"Contract: {', '.join(post.contract_items)}"))
    if post.concerns:
        children.append(_paragraph("Concerns:"))
        for c in post.concerns:
            children.append(_bullet(c))
    if post.stance == "synthesis" and post.action_items:
        children.append(_paragraph("Action Items:"))
        for a in post.action_items:
            children.append(_bullet(a))
    return children


def render_bottom_half(*, base_dir: Path, meeting_id: str) -> List[Dict[str, Any]]:
    posts = load_posts(base_dir=base_dir, meeting_id=meeting_id)
    n = len(posts)
    children: List[Dict[str, Any]] = []
    for p in posts:
        children.append(_toggle(_format_post_header(p), _post_children(p)))
    outer = _toggle(f"💬 Agent Discussion Log ({n} posts)", children)
    return [outer]


def render_meeting_to_blocks(*, base_dir: Path, meeting_id: str) -> List[Dict[str, Any]]:
    meeting = load_meeting(base_dir=base_dir, meeting_id=meeting_id)
    if meeting.status != "closed":
        raise RuntimeError(
            f"meeting {meeting_id} is not closed (status={meeting.status}); "
            f"render only valid after close"
        )
    blocks: List[Dict[str, Any]] = []
    blocks.extend(render_top_half(base_dir=base_dir, meeting_id=meeting_id))
    blocks.extend(render_bottom_half(base_dir=base_dir, meeting_id=meeting_id))
    return blocks
```

- [ ] **Step 4: Run all render tests to verify they pass**

Run: `py -m pytest "$env:USERPROFILE/.claude/harness/scripts/tests/test_render_meeting.py" -v`
Expected: 10 passed (5 top-half + 5 new).

- [ ] **Step 5: Commit**

```powershell
cd $env:USERPROFILE\.claude
git add harness/scripts/render_meeting.py harness/scripts/tests/test_render_meeting.py
git commit -m "harness(meetings): render bottom half toggle log + render_meeting_to_blocks"
cd $env:USERPROFILE\Desktop\SCM_WORK
```

---

### Task 8: CLI dispatcher — open / post / close / list / render subcommands

**Files:**
- Create: `~/.claude/harness/scripts/cli.py`
- Create: `~/.claude/harness/scripts/tests/test_cli_e2e.py`

- [ ] **Step 1: Write failing end-to-end CLI smoke test**

File: `~/.claude/harness/scripts/tests/test_cli_e2e.py`

```python
"""End-to-end smoke: drive a full sprint_review meeting through CLI."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


HARNESS_SCRIPTS = Path.home() / ".claude" / "harness" / "scripts"


def _cli(base_dir: Path, *args: str) -> subprocess.CompletedProcess:
    """Invoke `py -m scripts.cli <args> --base-dir <base_dir>` from harness root."""
    cmd = [sys.executable, "-m", "scripts.cli", *args, "--base-dir", str(base_dir)]
    return subprocess.run(
        cmd,
        cwd=str(HARNESS_SCRIPTS.parent),  # parent dir so "scripts" is importable
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_cli_full_sprint_review_flow(tmp_meetings_dir):
    # 1. open
    r = _cli(tmp_meetings_dir, "open",
             "--gate", "sprint_review",
             "--title", "Sprint 2 Review",
             "--mission", "build-dashboard",
             "--sprint", "2",
             "--project", "SCM_WORK",
             "--participants", "meeting-coordinator,code-worker,harness-validator")
    assert r.returncode == 0, r.stderr
    open_out = json.loads(r.stdout)
    meeting_id = open_out["meeting_id"]
    assert meeting_id.startswith("m-")

    # 2. post (code-worker claim)
    r = _cli(tmp_meetings_dir, "post",
             "--meeting", meeting_id,
             "--agent", "code-worker",
             "--stance", "claim",
             "--summary", "POST /shipments 구현 완료",
             "--evidence", "pytest 12/12 pass", "git HEAD abc1234",
             "--contract-items", "C3", "C4",
             "--ts", "2026-05-15T14:05:12Z")
    assert r.returncode == 0, r.stderr

    # 3. post (validator agree)
    r = _cli(tmp_meetings_dir, "post",
             "--meeting", meeting_id,
             "--agent", "harness-validator",
             "--stance", "agree",
             "--summary", "code-worker 통과 확인",
             "--refs", "code-worker@2026-05-15T14:05:12Z",
             "--contract-items", "C3", "C4",
             "--ts", "2026-05-15T14:15:02Z")
    assert r.returncode == 0, r.stderr

    # 4. post (coordinator synthesis)
    r = _cli(tmp_meetings_dir, "post",
             "--meeting", meeting_id,
             "--agent", "meeting-coordinator",
             "--stance", "synthesis",
             "--summary", "C3·C4 통과",
             "--action-items", "다음 Sprint TO-238 backfill",
             "--ts", "2026-05-15T14:30:00Z")
    assert r.returncode == 0, r.stderr

    # 5. close
    r = _cli(tmp_meetings_dir, "close", "--meeting", meeting_id)
    assert r.returncode == 0, r.stderr
    close_out = json.loads(r.stdout)
    assert close_out["status"] == "closed"

    # 6. render
    out_file = tmp_meetings_dir / "payload.json"
    r = _cli(tmp_meetings_dir, "render", "--meeting", meeting_id, "--out", str(out_file))
    assert r.returncode == 0, r.stderr
    payload = json.loads(out_file.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    # Top half + bottom half present
    serialized = json.dumps(payload, ensure_ascii=False)
    assert "스프린트 결과 요약" in serialized
    assert "💬 Agent Discussion Log" in serialized
    assert "C3·C4 통과" in serialized


def test_cli_list_shows_open_and_closed(tmp_meetings_dir):
    # Open one, close one
    r = _cli(tmp_meetings_dir, "open",
             "--gate", "sprint_review",
             "--title", "S1",
             "--mission", "m", "--sprint", "1", "--project", "P",
             "--participants", "meeting-coordinator")
    assert r.returncode == 0, r.stderr
    mid = json.loads(r.stdout)["meeting_id"]

    r = _cli(tmp_meetings_dir, "list")
    assert r.returncode == 0, r.stderr
    listing = json.loads(r.stdout)
    assert any(m["meeting_id"] == mid and m["status"] == "open" for m in listing)


def test_cli_post_validation_error_exits_nonzero(tmp_meetings_dir):
    r = _cli(tmp_meetings_dir, "open",
             "--gate", "sprint_review",
             "--title", "t", "--mission", "m", "--sprint", "1", "--project", "P",
             "--participants", "meeting-coordinator,code-worker")
    mid = json.loads(r.stdout)["meeting_id"]

    # agree post with no refs → PostValidationError → nonzero exit
    r = _cli(tmp_meetings_dir, "post",
             "--meeting", mid,
             "--agent", "code-worker",
             "--stance", "agree",
             "--summary", "agree",
             "--ts", "2026-05-15T14:00:00Z")
    assert r.returncode != 0
    assert "requires" in r.stderr.lower() or "refs" in r.stderr.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest "$env:USERPROFILE/.claude/harness/scripts/tests/test_cli_e2e.py" -v`
Expected: errors — `ModuleNotFoundError: No module named 'scripts.cli'`. (subprocess will return non-zero.)

- [ ] **Step 3: Implement `cli.py`**

File: `~/.claude/harness/scripts/cli.py`

```python
"""CLI dispatcher for harness meeting storage + render."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.meeting_storage import (
    DEFAULT_BASE_DIR,
    open_meeting,
    append_post,
    close_meeting,
    load_meeting,
    Post,
    PostValidationError,
)
from scripts.render_meeting import render_meeting_to_blocks


def _add_base_dir(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=DEFAULT_BASE_DIR,
        help=f"Meetings root directory (default: {DEFAULT_BASE_DIR})",
    )


def cmd_open(args: argparse.Namespace) -> int:
    participants = []
    for entry in args.participants.split(","):
        entry = entry.strip()
        if not entry:
            continue
        # Default role: facilitator for meeting-coordinator/checkpoint-reporter, participant otherwise
        role = "facilitator" if entry in {"meeting-coordinator", "checkpoint-reporter"} else "participant"
        participants.append((entry, role))

    meeting = open_meeting(
        base_dir=args.base_dir,
        gate_type=args.gate,
        title=args.title,
        mission=args.mission,
        sprint=int(args.sprint) if args.sprint else None,
        project=args.project,
        participants=participants,
    )
    print(json.dumps({
        "meeting_id": meeting.meeting_id,
        "gate_type": meeting.gate_type,
        "opened_at": meeting.opened_at,
        "status": meeting.status,
    }, ensure_ascii=False))
    return 0


def cmd_post(args: argparse.Namespace) -> int:
    post = Post(
        ts=args.ts,
        agent=args.agent,
        stance=args.stance,
        refs=args.refs or [],
        summary=args.summary,
        evidence=args.evidence or [],
        concerns=args.concerns or [],
        contract_items=args.contract_items or [],
        action_items=args.action_items or [],
    )
    append_post(base_dir=args.base_dir, meeting_id=args.meeting, post=post)
    print(json.dumps({"ok": True, "agent": args.agent, "stance": args.stance}, ensure_ascii=False))
    return 0


def cmd_close(args: argparse.Namespace) -> int:
    meeting = close_meeting(base_dir=args.base_dir, meeting_id=args.meeting)
    print(json.dumps({
        "meeting_id": meeting.meeting_id,
        "status": meeting.status,
        "closed_at": meeting.closed_at,
    }, ensure_ascii=False))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    base = Path(args.base_dir)
    results = []
    if not base.exists():
        print(json.dumps([]))
        return 0
    for d in sorted(base.iterdir()):
        if not d.is_dir() or not d.name.startswith("m-"):
            continue
        try:
            meeting = load_meeting(base_dir=base, meeting_id=d.name)
        except Exception:
            continue
        results.append({
            "meeting_id": meeting.meeting_id,
            "gate_type": meeting.gate_type,
            "status": meeting.status,
            "opened_at": meeting.opened_at,
            "closed_at": meeting.closed_at,
        })
    print(json.dumps(results, ensure_ascii=False))
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    blocks = render_meeting_to_blocks(base_dir=args.base_dir, meeting_id=args.meeting)
    out = Path(args.out)
    out.write_text(json.dumps(blocks, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "blocks": len(blocks), "out": str(out)}, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="meeting-cli", description="Harness meeting storage + render CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_open = sub.add_parser("open", help="Open a new meeting")
    _add_base_dir(p_open)
    p_open.add_argument("--gate", required=True, choices=["sprint_review", "checkpoint", "observation"])
    p_open.add_argument("--title", required=True)
    p_open.add_argument("--mission")
    p_open.add_argument("--sprint")
    p_open.add_argument("--project")
    p_open.add_argument("--participants", required=True, help="Comma-separated agent names")
    p_open.set_defaults(func=cmd_open)

    p_post = sub.add_parser("post", help="Append a post to an open meeting")
    _add_base_dir(p_post)
    p_post.add_argument("--meeting", required=True)
    p_post.add_argument("--agent", required=True)
    p_post.add_argument("--stance", required=True, choices=["claim", "agree", "disagree", "question", "answer", "synthesis"])
    p_post.add_argument("--summary", required=True)
    p_post.add_argument("--ts", required=True, help="ISO-8601 UTC timestamp")
    p_post.add_argument("--refs", nargs="*", help="Prior post keys: agent@ts")
    p_post.add_argument("--evidence", nargs="*")
    p_post.add_argument("--concerns", nargs="*")
    p_post.add_argument("--contract-items", nargs="*")
    p_post.add_argument("--action-items", nargs="*")
    p_post.set_defaults(func=cmd_post)

    p_close = sub.add_parser("close", help="Close a meeting (requires synthesis post last)")
    _add_base_dir(p_close)
    p_close.add_argument("--meeting", required=True)
    p_close.set_defaults(func=cmd_close)

    p_list = sub.add_parser("list", help="List all meetings (open + closed)")
    _add_base_dir(p_list)
    p_list.set_defaults(func=cmd_list)

    p_render = sub.add_parser("render", help="Render closed meeting to Notion block JSON")
    _add_base_dir(p_render)
    p_render.add_argument("--meeting", required=True)
    p_render.add_argument("--out", required=True, help="Output JSON file path")
    p_render.set_defaults(func=cmd_render)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except PostValidationError as e:
        print(f"PostValidationError: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run end-to-end tests to verify they pass**

Run: `py -m pytest "$env:USERPROFILE/.claude/harness/scripts/tests/test_cli_e2e.py" -v`
Expected: 3 passed.

- [ ] **Step 5: Run the full test suite to confirm no regressions**

Run: `py -m pytest "$env:USERPROFILE/.claude/harness/scripts/tests/" -v`
Expected: 38 passed (25 storage + 10 render + 3 CLI).

- [ ] **Step 6: Commit**

```powershell
cd $env:USERPROFILE\.claude
git add harness/scripts/cli.py harness/scripts/tests/test_cli_e2e.py
git commit -m "harness(meetings): CLI dispatcher (open/post/close/list/render) + e2e smoke"
cd $env:USERPROFILE\Desktop\SCM_WORK
```

---

### Task 9: Wire `discussion_render` event into `notion-mapping.yaml` (spec only — no agent change yet)

**Files:**
- Modify: `~/.claude/harness/notion-mapping.yaml`

- [ ] **Step 1: Read current notion-mapping.yaml**

Run: `py -c "import pathlib; print(pathlib.Path.home() / '.claude' / 'harness' / 'notion-mapping.yaml')"` to confirm path, then open the file. Locate the end of the `sync_events:` block (just before `# Sync 정책` section).

- [ ] **Step 2: Append the `discussion_render` event spec**

Insert *before* the `# Sync 정책` line, **immediately after** the last existing event under `sync_events:` (which is `milestone_update:`). Add:

```yaml

  # ── 다중 에이전트 토론 캡처 (2026-05-15 신규) ──────────────────────────
  # Plan A: storage + render foundation only. Notion API call is NOT yet
  # performed here — notion-sync agent will consume the rendered payload
  # in a follow-up plan (Plan B — agent integration).

  discussion_render:
    trigger: "meeting-coordinator 또는 checkpoint-reporter가 meeting close 직후. Plan A에서는 CLI(`py -m scripts.cli render`)가 payload.json만 생성하며 실제 Notion 호출은 Plan B에서 추가."
    target_db: meeting_notes
    action: create_or_update_page          # update_page if meta.notion.page_id 존재
    match_by: meta.notion.page_id          # null이면 create_page
    payload_source: "<base_dir>/<meeting_id>/payload.json  (Plan A CLI output)"
    fields:
      title: meta.title
      mission: meta.mission
      sprint: meta.sprint
      date: meta.opened_at
      type: "{Sprint Review | Checkpoint | Ad-hoc}"  # gate_type 매핑 — Plan A는 Sprint Review만 지원
      attendees: meta.participants[].agent
      decisions: synthesis.summary
      action_items: synthesis.action_items | join "\n"
      outcome: meta.outcome                # derived (success/partial/failed/in-progress)
    body_template: "Plan A scripts/render_meeting.py — sprint_review 만 지원. checkpoint/observation 템플릿은 Plan C에서 추가."
```

- [ ] **Step 3: Sanity-check YAML validity**

Run: `py -c "import yaml, pathlib; yaml.safe_load(pathlib.Path.home().joinpath('.claude/harness/notion-mapping.yaml').read_text(encoding='utf-8')); print('OK')"`
Expected: prints `OK`. If you see a `YAMLError`, fix indentation (the new block must be indented exactly 2 spaces under `sync_events:`).

- [ ] **Step 4: Verify the new event is discoverable**

Run:
```powershell
py -c "import yaml, pathlib; m = yaml.safe_load(pathlib.Path.home().joinpath('.claude/harness/notion-mapping.yaml').read_text(encoding='utf-8')); print('discussion_render found:', 'discussion_render' in m['sync_events'])"
```
Expected: `discussion_render found: True`

- [ ] **Step 5: Commit**

```powershell
cd $env:USERPROFILE\.claude
git add harness/notion-mapping.yaml
git commit -m "harness(notion): add discussion_render event spec (Plan A — payload only)"
cd $env:USERPROFILE\Desktop\SCM_WORK
```

---

### Task 10: Final smoke — drive a real meeting end-to-end and inspect the output

**Files:**
- No source changes — verification only.

- [ ] **Step 1: Run the full pytest suite one more time**

Run (PowerShell):
```powershell
py -m pytest "$env:USERPROFILE/.claude/harness/scripts/tests/" -v
```
Expected: 38 passed, 0 failed, 0 errors.

- [ ] **Step 2: Drive a real sprint_review meeting via CLI against the real `~/.claude/harness/meetings/` dir**

Run (PowerShell, one block):
```powershell
cd $env:USERPROFILE\.claude\harness
py -m scripts.cli open --gate sprint_review --title "Smoke Test — Plan A" --mission smoke --sprint 1 --project PlanA --participants "meeting-coordinator,code-worker,harness-validator"
```
Capture the printed `meeting_id` (e.g., `m-2026-05-15-sprint1-review`). Let's call it `$MID`.

- [ ] **Step 3: Append the three sample posts**

```powershell
$MID = "m-2026-05-15-sprint1-review"   # replace with actual id from Step 2
py -m scripts.cli post --meeting $MID --agent code-worker --stance claim --summary "smoke claim from code-worker" --evidence "evidence-1" "evidence-2" --contract-items C1 --ts "2026-05-15T15:00:00Z"
py -m scripts.cli post --meeting $MID --agent harness-validator --stance agree --summary "validator agrees with code-worker" --refs "code-worker@2026-05-15T15:00:00Z" --contract-items C1 --ts "2026-05-15T15:05:00Z"
py -m scripts.cli post --meeting $MID --agent meeting-coordinator --stance synthesis --summary "smoke synthesis — C1 통과" --action-items "follow-up 1" "follow-up 2" --ts "2026-05-15T15:10:00Z"
```
Each command prints `{"ok": true, ...}`.

- [ ] **Step 4: Close and render**

```powershell
py -m scripts.cli close --meeting $MID
py -m scripts.cli render --meeting $MID --out "meetings/$MID/payload.json"
```
Expected: close prints `{"status": "closed", ...}`. Render prints `{"ok": true, "blocks": N, ...}` where N ≥ 4.

- [ ] **Step 5: Inspect the rendered payload**

```powershell
Get-Content "$env:USERPROFILE\.claude\harness\meetings\$MID\payload.json" | py -c "import json,sys; d=json.load(sys.stdin); print('blocks:', len(d)); print('top types:', [b['type'] for b in d])"
```
Expected output shape:
```
blocks: 7
top types: ['heading_2', 'paragraph', 'heading_2', 'bulleted_list_item', 'heading_2', 'heading_2', 'toggle']
```
(Exact counts may vary; confirm at least one `heading_2` and one `toggle` block is present.)

- [ ] **Step 6: Verify the meeting directory contents**

```powershell
Get-ChildItem "$env:USERPROFILE\.claude\harness\meetings\$MID"
```
Expected files: `meta.yaml`, `discussion.jsonl`, `payload.json`.

```powershell
Get-Content "$env:USERPROFILE\.claude\harness\meetings\$MID\meta.yaml" | Select-String "status:"
```
Expected: `status: closed`

- [ ] **Step 7: Confirm active.yaml is empty and INDEX has both events**

```powershell
Get-Content "$env:USERPROFILE\.claude\harness\meetings\active.yaml"
```
Expected: `open_meetings: []`

```powershell
Get-Content "$env:USERPROFILE\.claude\harness\meetings\INDEX.jsonl"
```
Expected: at least two lines, the first with `"event": "opened"` and the second with `"event": "closed"` for the smoke meeting (more lines if any earlier development meetings exist).

- [ ] **Step 8: Final commit (no source change — capture smoke artifact in plan completion log)**

There's nothing to commit code-wise (the smoke creates runtime data in gitignored paths). Confirm clean state:

```powershell
cd $env:USERPROFILE\.claude
git status
cd $env:USERPROFILE\Desktop\SCM_WORK
```
Expected: `working tree clean` (no tracked changes from the smoke; only ignored `meetings/m-*/` paths show as untracked if any, and `.gitignore` excludes them).

---

## Plan Complete — Handoff to Plan B

At the end of Task 10 you have:

- A pytest-covered storage library (`meeting_storage.py`) with 25 tests
- A pytest-covered render library (`render_meeting.py`) with 10 tests
- A working CLI (`cli.py`) with 3 end-to-end tests
- An updated `notion-mapping.yaml` advertising the `discussion_render` event
- A successful real-world smoke meeting on disk

**Plan B (agent integration, follow-up):**
- Modify `meeting-coordinator.md` to open meetings, dispatch participants, write synthesis posts via CLI
- Modify `harness-validator.md` to write JSONL posts at verdict
- Modify `code/data/design-worker.md` to read `active.yaml` and post at turn end
- Modify `notion-sync.md` to handle `discussion_render` event — read `payload.json` and call `mcp__claude_ai_Notion__notion-create-pages`

**Plan C (additional gates, follow-up):**
- Add `checkpoint` + `observation` top-half templates to `render_meeting.py`
- Add `/observation` slash command
- Extend `checkpoint-reporter.md` to open checkpoint meetings
- Add validator cross-cutting detection (escalate_observation flag)

**Plan D (retention, follow-up):**
- Archive compression for meetings >30 days
- 1-year retention sweep
