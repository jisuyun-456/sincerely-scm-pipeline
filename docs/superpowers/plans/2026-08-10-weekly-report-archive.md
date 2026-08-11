# 주간 리포트 랜딩 교체 + 주차 아카이브 사이드바 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** GitHub Pages 랜딩을 크림+클레이 주간 리포트로 교체하고, 좌측 사이드바에 주차별 리포트를 누적(W31·W32 시드)해 클릭으로 과거 주를 열람한다.

**Architecture:** `compute(week)`(Airtable 수집)와 `render(dict)`(HTML)를 분리한다. 각 주 데이터를 `history/reports/<week>.json`으로 **프리즈**하고, 배포마다 아카이브의 모든 주를 각 JSON에서 렌더(API 0회)해 정적 페이지를 만든다. 사이드바는 각 페이지에 정적으로 구워지고, `index.html`은 최신 주다.

**Tech Stack:** Python 3.11 · requests · 기존 `generate_scm_report`/`tms_weekly_runner` 재사용 · pytest · GitHub Actions Pages.

**Spec:** `docs/superpowers/specs/2026-08-10-weekly-report-archive-redesign-design.md`

## Global Constraints

- W31 = **2026-07-27(월)~07-31(금)**, W32 = **2026-08-03(월)~08-07(금)**. week_id 포맷 `2026-W31`.
- 검증된 KPI 로직(`generate_scm_report`·`tms_weekly_runner`)은 **재사용만** — 재구현 금지.
- 아카이브는 **데이터(JSON)**를 얼린다 — HTML 아님(디자인 변경 시 전 주 재렌더 위함).
- 봇의 protected-main push는 **하지 않는다** (지속성은 별도 레포설정, 이 계획 범위 밖).
- 기존 크림+클레이 디자인 토큰/구조 보존. 렌더러는 Airtable 미접근이어야 한다(`render_from_data`).
- 신규 무거운 의존성 추가 금지.
- 파일 경로: 렌더러 `pages/render_weekly_report.py`, 데이터 `pages/weekly_report_data.py`, 템플릿 `pages/weekly_report.template.html`, 프리즈 `history/reports/`, 워크플로 `.github/workflows/deploy_pages.yml`, 테스트 `tests/pages/`.

---

## File Structure

| 파일 | 책임 |
|---|---|
| `pages/weekly_report_data.py` | `compute(week_id)→dict`. **JSON 직렬화 가능**하게 보정 + `week_range`/`label` 포함. |
| `pages/render_weekly_report.py` | `freeze_week` · `load_report` · `render_from_data` · `build_sidebar` · `rebuild_index` · `render_all_archive`. `render(week_id)`는 편의 래퍼. |
| `pages/weekly_report.template.html` | 2컬럼 레이아웃(`.layout`+`.sidebar`+`.wrap`) + `@@SIDEBAR@@` 토큰 + CSS. |
| `history/reports/<week>.json` | 주별 프리즈 스냅샷(=compute dict + generated_at). |
| `history/reports/index.json` | 사이드바 소스 `[{week_id,label,range,file,generated_at}]`. |
| `.github/workflows/deploy_pages.yml` | render 루프 · `index.html`=최신 · `dashboard.html` 랜딩 제거. |
| `tests/pages/test_weekly_report_render.py` | freeze/load·render·sidebar·archive 순수 로직 테스트. |

---

## Task 1: compute() JSON 직렬화 보정 + freeze/load 헬퍼

**Files:**
- Modify: `pages/weekly_report_data.py` (compute 반환부에 `label`/직렬화 보정)
- Create: `pages/render_weekly_report.py` 에 `freeze_week`/`load_report` (기존 파일 수정)
- Create: `tests/pages/__init__.py`, `tests/pages/test_weekly_report_render.py`

**Interfaces:**
- Produces: `freeze_week(week_id: str, reports_dir: Path = REPORTS_DIR) -> Path` — `compute` 호출→dict에 `generated_at` 추가→`reports_dir/<week_id>.json` 저장→경로 반환.
- Produces: `load_report(path: str|Path) -> dict` — json 로드.
- Produces: `_jsonable(d: dict) -> dict` — Counter/set/tuple→dict/list, date/datetime→isoformat 문자열 재귀 변환.

- [ ] **Step 1: 실패 테스트 작성** — `tests/pages/test_weekly_report_render.py`

```python
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "pages"))
import render_weekly_report as R

def test_freeze_load_roundtrip(tmp_path):
    d = {"week_id": "2026-W32", "inbound_count": 247,
         "chart_inbound_by_date": [{"date": "2026-08-03", "cnt": 60}],
         "material_picking_by_purpose": {"조립투입": 320}}
    p = R._write_report_json(d, tmp_path / "2026-W32.json")
    assert p.exists()
    back = R.load_report(p)
    assert back["inbound_count"] == 247
    assert back["chart_inbound_by_date"][0]["cnt"] == 60
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest tests/pages/test_weekly_report_render.py::test_freeze_load_roundtrip -v` → FAIL (`module render_weekly_report has no attribute _write_report_json`).

- [ ] **Step 3: 최소 구현** — `pages/render_weekly_report.py` 상단(기존 import 아래)에 추가:

```python
import json, datetime
from collections import Counter
REPORTS_DIR = ROOT / "history" / "reports"

def _jsonable(o):
    if isinstance(o, dict):   return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, Counter):return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)): return [_jsonable(v) for v in o]
    if isinstance(o, (datetime.date, datetime.datetime)): return o.isoformat()
    return o

def _write_report_json(d, path):
    path = pathlib.Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(d), ensure_ascii=False, indent=2), encoding="utf-8")
    return path

def load_report(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))

def freeze_week(week_id, reports_dir=REPORTS_DIR):
    d = compute(week_id)
    d["generated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    return _write_report_json(d, pathlib.Path(reports_dir) / f"{week_id}.json")
```

- [ ] **Step 4: 통과 확인** — Run: `python -m pytest tests/pages/test_weekly_report_render.py::test_freeze_load_roundtrip -v` → PASS.

- [ ] **Step 5: compute() 에 label 필드 추가** — `pages/weekly_report_data.py` 의 `compute` 최종 반환 dict에 아래 키가 있는지 확인/추가 (`week_range`는 이미 있음; `label` 신규):

```python
    # compute() 반환 dict 안:
    out["label"] = f'W{week_id.split("-W")[1]} ({out["week_range"].split("~")[0].strip().replace("2026-","").replace("-","/")}~)'
```
(예: week_range `2026-08-03 ~ 2026-08-07` → label `W32 (08/03~)`. week_range 실제 포맷은 파일에서 확인 후 슬라이스 맞출 것.)

- [ ] **Step 6: 커밋** — `git add pages/render_weekly_report.py pages/weekly_report_data.py tests/pages/ && git commit -m "feat(report): freeze/load 헬퍼 + compute JSON 직렬화·label"`

---

## Task 2: W31·W32 시드 (compute 라이브 → 프리즈 JSON)

**Files:**
- Create: `history/reports/2026-W31.json`, `history/reports/2026-W32.json` (생성물)

**Interfaces:**
- Consumes: `freeze_week` (Task 1)
- Produces: 실제 프리즈 JSON 2개 — 이후 Task 3~6 테스트의 픽스처.

> ⚠️ 이 태스크는 Airtable 라이브 호출. 로컬 `.env`(AIRTABLE_WMS_PAT·AIRTABLE_PAT·AIRTABLE_IBSA_PAT)가 있어야 함.

- [ ] **Step 1: W31 프리즈** — Run:
```bash
cd /c/Users/yjisu/Desktop/SCM_WORK
python -c "import sys; sys.path.insert(0,'pages'); import render_weekly_report as R; print(R.freeze_week('2026-W31'))"
```
Expected: `history/reports/2026-W31.json` 출력.

- [ ] **Step 2: W32 프리즈** — Run 위와 동일, `'2026-W32'`. Expected: `history/reports/2026-W32.json`.

- [ ] **Step 3: 값 검증** — Run:
```bash
python -c "import json; d=json.load(open('history/reports/2026-W32.json',encoding='utf-8')); print(d['week_id'], d['week_range'], d['inbound_count'], d['outbound_count'], d.get('label'))"
```
Expected: `2026-W32 ... <숫자> <숫자> W32 (08/03~)` — week_range가 8/3~8/7, 숫자 0 아님 확인. (W31도 동일 확인 → 7/27~7/31.)

- [ ] **Step 4: 커밋** — `git add history/reports/2026-W31.json history/reports/2026-W32.json && git commit -m "chore(report): W31·W32 프리즈 시드"`

---

## Task 3: render_from_data (compute/render 분리)

**Files:**
- Modify: `pages/render_weekly_report.py` (기존 `render` 분해)
- Modify: `tests/pages/test_weekly_report_render.py`

**Interfaces:**
- Consumes: `load_report` (Task 1), `build_operational_section`/`_hydrate_conversion`(기존)
- Produces: `render_from_data(d: dict, sidebar_html: str = "", template_path=TEMPLATE, out_path=None) -> str` — dict→HTML(Airtable 미접근). `out_path` 있으면 파일 기록.

- [ ] **Step 1: 실패 테스트 추가** — 실제 시드 JSON 픽스처 사용:

```python
FIX = pathlib.Path(__file__).resolve().parents[2] / "history" / "reports" / "2026-W32.json"

def test_render_from_data_divbalanced():
    d = R.load_report(FIX)
    html = R.render_from_data(d, sidebar_html="<aside id='sb'></aside>")
    assert "2026-W32" in html
    assert "<aside id='sb'>" in html
    assert html.count("<div") == html.count("</div"), "div 불균형"
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest tests/pages/test_weekly_report_render.py::test_render_from_data_divbalanced -v` → FAIL(`no attribute render_from_data`).

- [ ] **Step 3: 구현** — 기존 `render()`(L260~278)를 아래로 분해. `compute` 호출을 제거하고 `d`를 인자로 받음. 사이드바는 `@@SIDEBAR@@` 토큰 치환:

```python
def render_from_data(d, sidebar_html="", template_path=TEMPLATE, out_path=None):
    src = pathlib.Path(template_path).read_text(encoding="utf-8")
    i1 = src.index(SPLIT_HEAD); i2 = src.index(SPLIT_TAIL)
    head, tail = src[:i1], src[i2:]
    wk = d["week_id"]
    head = re.sub(r'Weekly Report — 2026-W\d+', f'Weekly Report — {wk}', head)
    head = _hydrate_conversion(head, d)
    head = head.replace("@@SIDEBAR@@", sidebar_html)
    middle = build_operational_section(d)
    out = head + middle + "\n\n</div>\n\n" + tail
    if out_path:
        outp = pathlib.Path(out_path); outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(out, encoding="utf-8")
    return out

def render(week_id, template_path=TEMPLATE, out_path=DEFAULT_OUT):
    """단일 주 편의 래퍼: compute→freeze→render_from_data (사이드바 없음)."""
    freeze_week(week_id)
    d = load_report(REPORTS_DIR / f"{week_id}.json")
    return render_from_data(d, template_path=template_path, out_path=out_path)
```
(주의: 템플릿에 `@@SIDEBAR@@`가 아직 없으면 replace는 무해히 no-op. Task 5에서 토큰 추가.)

- [ ] **Step 4: 통과 확인** — Run: `python -m pytest tests/pages/test_weekly_report_render.py::test_render_from_data_divbalanced -v` → PASS.

- [ ] **Step 5: 커밋** — `git add pages/render_weekly_report.py tests/pages/ && git commit -m "refactor(report): render_from_data 로 compute/render 분리"`

---

## Task 4: 사이드바 빌더 + 아카이브 인덱스

**Files:**
- Modify: `pages/render_weekly_report.py`
- Modify: `tests/pages/test_weekly_report_render.py`

**Interfaces:**
- Consumes: `load_report`
- Produces: `rebuild_index(reports_dir=REPORTS_DIR) -> list` — `reports_dir/*.json`(index.json 제외) 스캔→`{week_id,label,range,file,generated_at}` 리스트(week_id desc)→`index.json` 기록→리스트 반환.
- Produces: `build_sidebar(index: list, current_week: str) -> str` — `<aside class="sidebar">` HTML, current 주 `aria-current`/`active`.

- [ ] **Step 1: 실패 테스트 추가**

```python
def test_rebuild_index_and_sidebar(tmp_path):
    for wk, rng in [("2026-W31","2026-07-27 ~ 2026-07-31"), ("2026-W32","2026-08-03 ~ 2026-08-07")]:
        R._write_report_json({"week_id":wk,"week_range":rng,"label":f"{wk[-3:]} ({rng[5:10]}~)",
                              "generated_at":"2026-08-10T00:00:00"}, tmp_path/f"{wk}.json")
    idx = R.rebuild_index(tmp_path)
    assert [e["week_id"] for e in idx] == ["2026-W32","2026-W31"]  # 최신 위
    assert (tmp_path/"index.json").exists()
    sb = R.build_sidebar(idx, "2026-W32")
    assert "W32" in sb and "W31" in sb
    assert "weekly-report-2026-W31.html" in sb   # 링크
    assert sb.count("aria-current") == 1          # 현재 주만 표시
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest tests/pages/test_weekly_report_render.py::test_rebuild_index_and_sidebar -v` → FAIL.

- [ ] **Step 3: 구현**

```python
def rebuild_index(reports_dir=REPORTS_DIR):
    reports_dir = pathlib.Path(reports_dir); entries = []
    for p in reports_dir.glob("*.json"):
        if p.name == "index.json": continue
        d = load_report(p)
        entries.append({"week_id": d["week_id"], "label": d.get("label", d["week_id"]),
                        "range": d.get("week_range",""), "file": f"weekly-report-{d['week_id']}.html",
                        "generated_at": d.get("generated_at","")})
    entries.sort(key=lambda e: e["week_id"], reverse=True)
    (reports_dir / "index.json").write_text(
        json.dumps({"reports": entries}, ensure_ascii=False, indent=2), encoding="utf-8")
    return entries

def build_sidebar(index, current_week):
    rows = []
    for e in index:
        cur = ' aria-current="page" class="wk-item active"' if e["week_id"] == current_week else ' class="wk-item"'
        rows.append(f'<a href="{e["file"]}"{cur}><span class="wk-key">{_esc(e["label"])}</span>'
                    f'<span class="wk-range">{_esc(e["range"])}</span></a>')
    return ('<aside class="sidebar">\n  <div class="sb-head">주차 이력</div>\n  <nav class="wk-list">\n    '
            + "\n    ".join(rows) + '\n  </nav>\n</aside>')
```

- [ ] **Step 4: 통과 확인** — Run: `python -m pytest tests/pages/test_weekly_report_render.py::test_rebuild_index_and_sidebar -v` → PASS.

- [ ] **Step 5: 커밋** — `git add pages/render_weekly_report.py tests/pages/ && git commit -m "feat(report): 사이드바 빌더 + 아카이브 인덱스"`

---

## Task 5: 템플릿 2컬럼 레이아웃 + @@SIDEBAR@@ 토큰

**Files:**
- Modify: `pages/weekly_report.template.html` (CSS `<style>` 끝부분 + `.wrap` 래핑)
- Modify: `tests/pages/test_weekly_report_render.py`

**Interfaces:**
- Consumes: `render_from_data`, `build_sidebar`
- Produces: 렌더 결과에 `.layout`/`.sidebar` 존재, 사이드바 주입됨.

- [ ] **Step 1: 실패 테스트 추가**

```python
def test_template_two_column_layout():
    d = R.load_report(FIX)
    idx = R.rebuild_index()   # 시드 W31·W32
    html = R.render_from_data(d, R.build_sidebar(idx, "2026-W32"))
    assert 'class="layout"' in html
    assert 'class="sidebar"' in html
    assert "weekly-report-2026-W31.html" in html   # 사이드바 실제 주입
    assert html.count("<div") == html.count("</div")
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest tests/pages/test_weekly_report_render.py::test_template_two_column_layout -v` → FAIL (`class="layout"` 없음).

- [ ] **Step 3: 템플릿 수정** — `<style>` 마지막(닫기 `</style>` 직전)에 CSS 추가:

```css
  .layout{display:flex; align-items:flex-start; gap:0; max-width:1240px; margin:0 auto}
  .sidebar{position:sticky; top:0; align-self:flex-start; width:210px; flex:none; height:100vh;
           overflow-y:auto; padding:32px 14px; border-right:1px solid var(--border); background:var(--surface-2)}
  .sb-head{font-size:11.5px; letter-spacing:.12em; text-transform:uppercase; color:var(--accent); font-weight:700; margin:0 0 14px}
  .wk-list{display:flex; flex-direction:column; gap:4px}
  .wk-item{display:flex; flex-direction:column; padding:9px 11px; border-radius:9px; text-decoration:none;
           color:var(--muted); border:1px solid transparent}
  .wk-item:hover{background:var(--surface); border-color:var(--border)}
  .wk-item.active{background:var(--accent-tint); border-color:var(--border-strong); color:var(--accent-ink)}
  .wk-key{font-size:13.5px; font-weight:700}
  .wk-range{font-size:11px; color:var(--faint)}
  .layout .wrap{flex:1; min-width:0}
  @media(max-width:820px){.layout{flex-direction:column} .sidebar{position:static; width:100%; height:auto; border-right:none; border-bottom:1px solid var(--border); display:flex; gap:16px; align-items:center}
    .wk-list{flex-direction:row; overflow-x:auto}}
```

- [ ] **Step 4: `.wrap` 를 `.layout` 로 감싸기** — 템플릿에서 `<div class="wrap">` 여는 지점 **직전**에 아래를 삽입:
```html
<div class="layout">
@@SIDEBAR@@
```
그리고 리포트 본문의 `.wrap` 닫는 `</div>`(render가 `middle` 뒤에 붙이는 `</div>`) **뒤에** `.layout` 닫기가 필요. render_from_data의 조립부를 `out = head + middle + "\n\n</div>\n</div>\n\n" + tail` 로 수정(.wrap + .layout 두 개 닫기).
(정확한 `.wrap` 여는 위치·닫기 개수는 파일 확인 후 div 밸런스 유지하도록 맞출 것 — Step 5 테스트가 검증.)

- [ ] **Step 5: 통과 확인** — Run: `python -m pytest tests/pages/test_weekly_report_render.py::test_template_two_column_layout -v` → PASS (div 밸런스 포함).

- [ ] **Step 6: 커밋** — `git add pages/weekly_report.template.html pages/render_weekly_report.py tests/pages/ && git commit -m "feat(report): 2컬럼 레이아웃 + 사이드바 주입"`

---

## Task 6: render_all_archive + index.html=최신

**Files:**
- Modify: `pages/render_weekly_report.py`
- Modify: `tests/pages/test_weekly_report_render.py`

**Interfaces:**
- Consumes: `rebuild_index`, `build_sidebar`, `render_from_data`, `load_report`
- Produces: `render_all_archive(reports_dir=REPORTS_DIR, out_dir=ROOT/"docs") -> list` — 전 주 렌더 → `out_dir/weekly-report-<week>.html`, 최신 주 복사 → `out_dir/index.html`. 렌더된 week_id 리스트 반환.

- [ ] **Step 1: 실패 테스트 추가**

```python
def test_render_all_archive(tmp_path):
    weeks = R.render_all_archive(out_dir=tmp_path)   # 시드 W31·W32 사용
    assert set(weeks) == {"2026-W31","2026-W32"}
    assert (tmp_path/"weekly-report-2026-W31.html").exists()
    assert (tmp_path/"weekly-report-2026-W32.html").exists()
    idx_html = (tmp_path/"index.html").read_text(encoding="utf-8")
    assert "2026-W32" in idx_html and 'class="sidebar"' in idx_html   # index=최신+사이드바
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest tests/pages/test_weekly_report_render.py::test_render_all_archive -v` → FAIL.

- [ ] **Step 3: 구현**

```python
def render_all_archive(reports_dir=REPORTS_DIR, out_dir=ROOT / "docs"):
    out_dir = pathlib.Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    index = rebuild_index(reports_dir)
    done = []
    for e in index:
        d = load_report(pathlib.Path(reports_dir) / f'{e["week_id"]}.json')
        sb = build_sidebar(index, e["week_id"])
        render_from_data(d, sb, out_path=out_dir / e["file"])
        done.append(e["week_id"])
    if index:  # 최신(맨 위) → index.html
        latest = index[0]
        (out_dir / "index.html").write_text(
            (out_dir / latest["file"]).read_text(encoding="utf-8"), encoding="utf-8")
    return done
```

- [ ] **Step 4: 통과 확인** — Run: `python -m pytest tests/pages/test_weekly_report_render.py -v` → 전체 PASS.

- [ ] **Step 5: 로컬 시각 검증** — Run: `python -c "import sys;sys.path.insert(0,'pages');import render_weekly_report as R;print(R.render_all_archive())"` 후 `docs/index.html`·`docs/weekly-report-2026-W31.html` 브라우저로 열어 사이드바·현재 하이라이트·전환/운영 KPI 확인.

- [ ] **Step 6: 커밋** — `git add pages/render_weekly_report.py tests/pages/ docs/index.html docs/weekly-report-2026-W31.html docs/weekly-report-2026-W32.html && git commit -m "feat(report): render_all_archive + index=최신 주"`

---

## Task 7: 배포 워크플로 갱신 (render 루프 · index 교체 · dashboard 은퇴)

**Files:**
- Modify: `.github/workflows/deploy_pages.yml`

**Interfaces:**
- Consumes: `render_all_archive`

- [ ] **Step 1: Render 스텝 교체** — 기존 "Render weekly report" 스텝(L78~85)의 `run:` 을 아래로 교체(현재 주 프리즈 → 전 주 렌더):
```yaml
        run: |
          python -c "import sys;sys.path.insert(0,'pages');import render_weekly_report as R;\
          import datetime;wk=R._default_week();R.freeze_week(wk);print('frozen',wk)"
          python -c "import sys;sys.path.insert(0,'pages');import render_weekly_report as R;\
          print('rendered', R.render_all_archive())"
```
(`_default_week`는 직전 ISO 주. `render_all_archive` 기본 out_dir=`docs/`.)

- [ ] **Step 2: Prepare site 수정** — L142 `cp pages/dashboard.html site/index.html` 를 삭제하고, 아카이브 산출물 복사로 교체:
```bash
          # 랜딩 = 최신 주 리포트 (render_all_archive 가 docs/index.html 생성)
          cp docs/index.html site/index.html
          cp docs/weekly-report-*.html site/ 2>/dev/null || true
          cp -r history/reports site/history/reports 2>/dev/null || true
```
기존 L150 `cp docs/weekly-report.html site/weekly-report.html` 라인은 제거(파일명 체계 변경).

- [ ] **Step 3: history 커밋 스텝에 reports 포함** — L130 부근 `git add history/` 는 `history/reports/` 도 포함하므로 그대로 유지(프리즈 JSON 커밋 시도, protected-main 실패는 기존 `|| echo` 로 무해).

- [ ] **Step 4: YAML 문법 검증** — Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/deploy_pages.yml',encoding='utf-8')); print('yaml ok')"` → `yaml ok`.

- [ ] **Step 5: 커밋** — `git add .github/workflows/deploy_pages.yml && git commit -m "ci(pages): 주차 아카이브 렌더 루프 + index=최신 주 + dashboard 은퇴"`

---

## Self-Review 결과 (작성자 점검)

- **Spec 커버리지:** 랜딩 교체(T7 index) · 사이드바 누적(T4·T6) · JSON 프리즈(T1·T2) · compute/render 분리(T3) · W31·W32 시드(T2) · 엣지(div밸런스 T3/T5, round-trip T1, compute실패는 freeze 미덮음 T1) · 검증(각 태스크 pytest) — 모두 태스크 존재. 지속성(봇 push)은 spec §6대로 계획 밖(레포설정).
- **Placeholder:** 없음(모든 스텝 실제 코드/명령). 단 T1-S5·T5-S4는 "파일 확인 후 슬라이스/닫기 맞출 것" 명시 — div밸런스 테스트가 가드.
- **타입 일관성:** `freeze_week`/`load_report`/`render_from_data(d,sidebar_html,...)`/`build_sidebar(index,current_week)`/`rebuild_index`/`render_all_archive` 시그니처가 태스크 간 일치. `@@SIDEBAR@@` 토큰은 T5(템플릿)·T3(치환) 동일.

## 검증 (전체 완료 후)

1. `python -m pytest tests/pages/ -v` 전체 PASS.
2. `docs/index.html` = W32 리포트 + 사이드바(W31·W32, W32 active).
3. `docs/weekly-report-2026-W31.html` 클릭 이동 시 W31 데이터(7/27~31).
4. div 밸런스 OK(테스트 내장).
5. `deploy_pages.yml` YAML 유효 + dashboard 랜딩 제거 확인.
