# CBM Backbone P2a Implementation Plan (출고 상시화 + pkg hop)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop forward-coverage decay by wiring the deterministic CBM replay into the wave_recommender cron, and light the order→pkg_schedule tier-2 fallback hop.

**Architecture:** Pure key-resolution logic stays in `harness/backbone/keys.py` (testable, no IO); Airtable fetches stay in `scripts/backbone/replay_outbound_cbm.py`; cron scheduling is YAML-only in `.github/workflows/wave_recommender.yml`. The fallback map is built once per replay run: sync_item(굿즈명→굿즈코드) bridges pkg_schedule(PNA→goods names) because **pkg_schedule has no goods-code field** (2026-06-10 schema verification).

**Tech Stack:** Python 3.12, pytest, requests, GitHub Actions, Airtable REST API.

**Evidence baseline (2026-06-10 read-only measurement, forward 90d = 965 shipments):**
- valid now 75.0% / partial_skip 13.0% / blank project code 11.8% / no_order 0%.
- Blank 굿즈코드 orders: 33/20,872 (0.2%); pkg-path resolves 6 of them; forward shipment coverage delta **+0.0%p**.
- Handoff's "~24% 회수" premise does not hold → Task 2a.2 gate redefined as **hop lit + recovery measured/reported** (handoff already allowed: "gate 목표는 측정 후 확정").
- Fallback still wanted: P6 connectivity deliverable + catches sync_itemdb linkage lag (7d blank rate 0.9% vs 90d 0.2% — recent orders lag, fallback covers the gap window).

**Deviation from handoff (justified):** map *builder* `build_pkg_goods_map` lives in keys.py as a pure function (TDD-able); the handoff put "맵 빌드" in the replay script, but its parsing logic (PNA regex + parse_goods + normalize + ambiguity filter) needs unit tests. Fetch stays in the script per spec ("fetch는 호출자").

**Verified IDs/fields (Meta API, 2026-06-10):**
- WMS pkg_schedule mirror: `tblae2NqJaexwjN9R` — `프로젝트 코드 (PK) (from project)`, `주문 굿즈 리스트 (자동) (from project)`, `단품 굿즈 품목 및 수량`
- WMS sync_item: `tblwnNgHQxZ0WhDBh` — `굿즈명`, `굿즈코드`
- TMS Shipment `CBM_유효`: `fldRQxI4HOWydlwEh` (formula)
- GHA secrets in use elsewhere: `AIRTABLE_API_KEY_TMS` (this workflow), `AIRTABLE_API_KEY_WMS` (deploy_pages.yml, weekly-full-pipeline.yml maps it to `AIRTABLE_WMS_PAT`)

---

### Task 1: keys.py — PNA_RE + tier-2 resolve + pure map builder (TDD)

**Files:**
- Modify: `harness/backbone/keys.py`
- Test: `tests/backbone/test_keys.py`

- [ ] **Step 1: Write the failing tests** — append to `tests/backbone/test_keys.py`:

```python
class TestResolveGoodsCodePkgFallback:
    PKG = {"PNA50702": "SBAT"}

    def test_direct_wins_over_pkg(self):
        row = {"굿즈코드 (from sync_itemdb)": "SSSV", "project_code": "PNA50702_심볼"}
        assert resolve_goods_code(row, self.PKG) == ("SSSV", "direct")

    def test_blank_falls_back_to_pkg(self):
        assert resolve_goods_code({"project_code": "PNA50702_심볼"}, self.PKG) == ("SBAT", "pkg")

    def test_blank_and_unknown_project_none(self):
        assert resolve_goods_code({"project_code": "PNA99999_없음"}, self.PKG) == (None, "none")

    def test_blank_no_pna_none(self):
        assert resolve_goods_code({"project_code": "기타"}, self.PKG) == (None, "none")

    def test_no_map_backward_compat(self):
        assert resolve_goods_code({}) == (None, "none")


class TestBuildPkgGoodsMap:
    N2C = {"심볼아크릴트로피": "SSSV", "시그니처보조배터리": "SBAT"}

    def test_single_code_project_mapped(self):
        rows = [{"프로젝트 코드 (PK) (from project)": "PNA50702_심볼",
                 "주문 굿즈 리스트 (자동) (from project)": "심볼아크릴트로피 125"}]
        assert build_pkg_goods_map(rows, self.N2C) == {"PNA50702": "SSSV"}

    def test_multi_code_project_excluded(self):
        rows = [{"프로젝트 코드 (PK) (from project)": "PNA1_x",
                 "주문 굿즈 리스트 (자동) (from project)": "심볼아크릴트로피 125, 시그니처보조배터리 30"}]
        assert build_pkg_goods_map(rows, self.N2C) == {}

    def test_service_and_unknown_names_skipped(self):
        rows = [{"프로젝트 코드 (PK) (from project)": "PNA2_y",
                 "주문 굿즈 리스트 (자동) (from project)": "배송 다마스 1, 미지의굿즈 10"}]
        assert build_pkg_goods_map(rows, self.N2C) == {}

    def test_second_source_also_read(self):
        rows = [{"프로젝트 코드 (PK) (from project)": "PNA3_z",
                 "단품 굿즈 품목 및 수량": "심볼아크릴트로피 10"}]
        assert build_pkg_goods_map(rows, self.N2C) == {"PNA3": "SSSV"}

    def test_same_code_multiple_rows_merged(self):
        rows = [{"프로젝트 코드 (PK) (from project)": "PNA4_a",
                 "주문 굿즈 리스트 (자동) (from project)": "심볼아크릴트로피 5"},
                {"프로젝트 코드 (PK) (from project)": "PNA4_a",
                 "주문 굿즈 리스트 (자동) (from project)": "심볼아크릴트로피 5"}]
        assert build_pkg_goods_map(rows, self.N2C) == {"PNA4": "SSSV"}
```

Update the import line at the top to include `build_pkg_goods_map`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/backbone/test_keys.py -q`
Expected: ImportError (`build_pkg_goods_map` not defined) / fallback tests FAIL.

- [ ] **Step 3: Implement in `harness/backbone/keys.py`**

Add after `PT_RE`:
```python
PNA_RE = re.compile(r"\b(PNA\d+)\b")
```

Replace `resolve_goods_code` with:
```python
def resolve_goods_code(
    row: dict, pkg_goods_by_project: dict[str, str] | None = None
) -> tuple[str | None, str]:
    """order/shipment row → (견적코드, 출처). 우선순위: order.굿즈코드 → pkg_schedule 폴백 → None.
    Returns (code_upper, 'direct'|'pkg'|'none'). Airtable lookup 필드는 list로 올 수 있어 언랩."""
    raw = row.get("굿즈코드 (from sync_itemdb)")
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    code = str(raw or "").strip().upper()
    if code:
        return code, "direct"
    if pkg_goods_by_project:
        m = PNA_RE.search(str(row.get("project_code") or ""))
        if m and m.group(1) in pkg_goods_by_project:
            return pkg_goods_by_project[m.group(1)].strip().upper(), "pkg"
    return None, "none"


def build_pkg_goods_map(pkg_rows, name_to_code: dict[str, str]) -> dict[str, str]:
    """pkg_schedule fields-dict 목록 + sync_item 굿즈명→굿즈코드 → {PNA: 견적코드}.
    pkg_schedule에는 굿즈코드 필드가 없어 굿즈명을 sync_item으로 브릿지.
    다중 코드 프로젝트는 order行 귀속 불가 → 제외(단일 코드만)."""
    by_pna: dict[str, set[str]] = {}
    for f in pkg_rows:
        m = PNA_RE.search(str(f.get("프로젝트 코드 (PK) (from project)") or ""))
        if not m:
            continue
        codes = by_pna.setdefault(m.group(1), set())
        for src in ("주문 굿즈 리스트 (자동) (from project)", "단품 굿즈 품목 및 수량"):
            for part in re.split(r"[,\n/]+", str(f.get(src) or "")):
                name = normalize_goods(parse_goods(part.strip())[0])
                if name and not is_service(name) and name in name_to_code:
                    codes.add(name_to_code[name])
    return {pna: next(iter(c)) for pna, c in by_pna.items() if len(c) == 1}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/backbone/test_keys.py -q`
Expected: all PASS (existing 20 + new 11).

- [ ] **Step 5: Commit**

```bash
git add harness/backbone/keys.py tests/backbone/test_keys.py
git commit -m "feat(backbone): resolve_goods_code tier-2 pkg_schedule fallback + build_pkg_goods_map (P2a Task 2a.2)"
```

### Task 2: replay script — inject fallback map + recovery report

**Files:**
- Modify: `scripts/backbone/replay_outbound_cbm.py`

- [ ] **Step 1: Add imports/constants**

After the existing harness imports:
```python
from harness.backbone.keys import (  # noqa: E402
    resolve_goods_code, build_pkg_goods_map, normalize_goods,
)
```
After `ORDER = ...`:
```python
PKG_SCHED = "tblae2NqJaexwjN9R"   # WMS ⚡pkg_schedule mirror
SYNC_ITEM = "tblwnNgHQxZ0WhDBh"   # WMS ⚡sync_item (굿즈명→굿즈코드)
```

- [ ] **Step 2: Add fallback-map fetch helper** (before `build_inputs`):

```python
def build_pkg_fallback():
    """sync_item 굿즈명→굿즈코드 + pkg_schedule → {PNA: 견적코드} (단일 코드 프로젝트만)."""
    print("pkg_schedule 폴백 맵 로딩...", flush=True)
    items = fetch(WMS, SYNC_ITEM, WP, ["굿즈명", "굿즈코드"])
    name2code = {}
    for r in items:
        f = r["fields"]
        nm = normalize_goods(str(f.get("굿즈명") or ""))
        cd = str(f.get("굿즈코드") or "").strip().upper()
        if nm and cd:
            name2code[nm] = cd
    pkgs = fetch(WMS, PKG_SCHED, WP, [
        "프로젝트 코드 (PK) (from project)",
        "주문 굿즈 리스트 (자동) (from project)",
        "단품 굿즈 품목 및 수량",
    ])
    pkg_map = build_pkg_goods_map((r["fields"] for r in pkgs), name2code)
    print(f"  pkg 폴백 맵: {len(pkg_map)} 프로젝트 (sync_item 매핑 {len(name2code)}건)", flush=True)
    return pkg_map
```

- [ ] **Step 3: Use the resolver in `build_inputs`** — replace the order loop:

```python
    pkg_map = build_pkg_fallback()
    opg = collections.defaultdict(collections.Counter)
    src_count = collections.Counter()
    for r in orders:
        f = r["fields"]
        m = PNA.search(str(f.get("project_code") or ""))
        if not m:
            continue
        code, src = resolve_goods_code(f, pkg_map)
        src_count[src] += 1
        if code:
            opg[m.group(0)][code] += n(f.get("주문수량"))
    blank_total = src_count["pkg"] + src_count["none"]
    rate = src_count["pkg"] / blank_total * 100 if blank_total else 0.0
    print(f"  굿즈코드 리졸브: direct={src_count['direct']} pkg폴백={src_count['pkg']} "
          f"미회수={src_count['none']} (blank-code 회수율 {rate:.1f}%)", flush=True)
```

(Behavior note: PNA-less orders no longer enter the resolver count — same as before, they were skipped.)

- [ ] **Step 4: Dry-run measurement (read-only) — record the recovery numbers**

Run: `python scripts/backbone/replay_outbound_cbm.py --recent 90`
Expected: `pkg폴백=6 미회수=27 (blank-code 회수율 ~18%)`, forward coverage unchanged ≥75%, PATCH 대상 small (only deterministic deltas). Record exact numbers for the exit report.

- [ ] **Step 5: Full pytest + commit**

Run: `python -m pytest tests/ -q` → expected 281 passed, 1 known W1 fail.
```bash
git add scripts/backbone/replay_outbound_cbm.py
git commit -m "feat(backbone): replay에 pkg_schedule tier-2 폴백 주입 + 회수율 리포트 (P2a Task 2a.2)"
```

### Task 3: wave_recommender.yml — cron replay step (Task 2a.1)

**Files:**
- Modify: `.github/workflows/wave_recommender.yml`

- [ ] **Step 1: Insert step before "Run wave recommender"** (after "Install dependencies"):

```yaml
      - name: Persist outbound estimated_cbm (deterministic replay)
        continue-on-error: true   # replay 실패가 배차 추천을 막지 않도록
        run: |
          if [ "${{ github.event.inputs.dry_run || 'false' }}" = "true" ]; then
            python scripts/backbone/replay_outbound_cbm.py --recent 7 | tee replay_log.txt
          else
            python scripts/backbone/replay_outbound_cbm.py --recent 7 --write | tee replay_log.txt
          fi
        env:
          AIRTABLE_PAT: ${{ secrets.AIRTABLE_API_KEY_TMS }}
          AIRTABLE_WMS_PAT: ${{ secrets.AIRTABLE_API_KEY_WMS }}

      - name: Upload replay log
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: outbound-cbm-replay-log
          path: replay_log.txt
          retention-days: 90
          overwrite: true
          if-no-files-found: ignore
```

- [ ] **Step 2: Validate YAML**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/wave_recommender.yml', encoding='utf-8'))"`
Expected: no error.

- [ ] **Step 3: Verify requirements** — `harness/requirements.txt` must contain `requests` and `python-dotenv` (replay imports both). If missing, add.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/wave_recommender.yml
git commit -m "feat(backbone): wave cron에 결정론 replay --recent 7 --write 편입 — forward coverage decay 차단 (P2a Task 2a.1)"
```

- [ ] **Step 5: Post-push verification (after exit-handoff push)**

Trigger `workflow_dispatch` with `dry_run=true` once; confirm replay step output in the run log + artifact. First week: monitor PATCH counts for runaway (expected per run: 0~tens).

### Task 4: schema_pin — pin CBM_유효 (Task 2a.3)

**Files:**
- Modify: `harness/_core/schema_pin.json`

- [ ] **Step 1: Add field entry** under `tables.tbllg1JoHclGYer7m.fields` (after `fld9YtjtpiOiZHJKu`):

```json
        "fldRQxI4HOWydlwEh": {
          "name": "CBM_유효",
          "type": "formula"
        }
```

- [ ] **Step 2: Validate JSON**

Run: `python -c "import json; json.load(open('harness/_core/schema_pin.json', encoding='utf-8'))"`
Expected: no error.

- [ ] **Step 3: Commit**

```bash
git add harness/_core/schema_pin.json
git commit -m "chore(backbone): schema_pin에 Shipment.CBM_유효(fldRQxI4HOWydlwEh) 핀 (P2a Task 2a.3)"
```

### Task 5: Verification gates

- [ ] Full pytest: `python -m pytest tests/ -q` → 281 passed, 1 known W1 fail only.
- [ ] `feature-dev:code-reviewer` agent on the diff + `harness-validator` in parallel → both PASS.
- [ ] Report: blank-code recovery numbers (Task 2 Step 4) + forward coverage state.

### Task 6: Exit Handoff (chain protocol — `/chain done`)

- [ ] Master tracker: P2a ✅ DONE + P2b ⏸ READY_TO_START; record evidence-based rescope note (~24% premise → measured 0.2%/+0.0%p).
- [ ] Write `~/.claude/plans/cbm-capacity-backbone-p2b-handoff.md` (MES 크로스워크·task 검증·kit-CBM — spec §3/§4).
- [ ] Obsidian log entry + notion-sync agent + `.claude/feature_list.json` 갱신.
- [ ] Final commit.

**Out of scope (P2a):** partial_skip 13% (다차 배분 — P5/P3' 후보), blank project code 11.8% (shipment에 PNA 자체가 없음 — 운영 입력 문제, P5), Task 1.4 deferred 0.2%.
