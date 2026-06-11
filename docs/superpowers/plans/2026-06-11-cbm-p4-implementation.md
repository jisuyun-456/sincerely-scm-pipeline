# CBM Capacity Backbone P4 — 대시보드 시계열 (capacity_snapshot + GHA cron) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** P3'까지 점등된 3트랙(출고/보관/입하) CBM 입력을 `capacity_snapshot.py`로 event-boundary 집계해 `data/capacity_series.json` 시계열로 만들고, GHA 일일 cron으로 상시화한다.

**Architecture:** 순수 로직(`harness/backbone/capacity_snapshot.py`) ↔ IO runner(`scripts/backbone/capacity_snapshot_run.py`) 분리 — P3' storage/mes_forecast와 동일 패턴. 각 트랙은 자기 event boundary 1곳에서만 카운트(출고=`shipment.출하확정일`, 보관=`InventoryLedger` point-in-time, 입하=`movement.입하예상일`)하고 **트랙 간 합산 필드를 만들지 않아** "1주문 트랙간 중복 0" gate를 구조적으로 충족. 시계열 persistence는 repo 기존 패턴(scorecard.yml의 GHA commit+push) 재사용.

**Tech Stack:** Python 3.12 / pytest / Airtable REST(read-only — 유일한 write는 seed 스크립트의 WMS_Location 1행) / GitHub Actions cron.

**사용자 체크포인트 (2026-06-11 확정):**
- 예측 horizon = **14일** (MES forecast 기존 (7,14) 윈도우와 정합)
- Max_CBM 실측치 = **에이원센터 입하장(A1-IB-001) 57.6m³** (1,200³mm ×12 = 20.736 + 800×600×1,200mm ×64 = 36.864). 보관(베스트원 ST) 분모는 계속 pending — 분자+커버리지%만 emit.
- MES GHA secret `AIRTABLE_API_KEY_MES` **미등록** → runner는 PAT 부재 시 `mes_forecast: null` 우아한 생략. secret 등록은 사용자 액션(Exit Handoff에 기재).

**재사용 자산 (전부 기존 검증됨):**
- `harness/backbone/storage.py` — `aggregate_occupied(ledger_rows, part_cbm_by_pt)` (P3' T3)
- `harness/backbone/mes_forecast.py` — `build_inbound_forecast(mes_rows, name_to_code, product_by_code, today, horizons=(7,14))` (P3' T6)
- `utils/cbm_utils.py` — `fetch_inbound_cbm(sp_lookup, since, until, purposes=EXTERNAL_INBOUND_PURPOSES)`, `load_sync_parts_lookup()` (P3' T4)
- `harness/settlement/cbm_calc.load_product_lookup` / `harness/backbone/keys.normalize_goods`
- `harness/_core/calendar.py` — `KST`, `today_kst()`
- Shipment 필드: `출하확정일`(fldQvmEwwzvQW95h9, date) · `CBM_유효`(fldRQxI4HOWydlwEh, formula — schema_pin 핀 완료)
- WMS_Location(tblRwUTP5kWnHFt5P)은 `_WRITE_ALLOWLIST` 포함 — seed 쓰기 허용 확인됨

**주의 (오늘 실측):** 로컬 Python requests가 Airtable 전체필드 fetch에서 read timeout 발생 이력 — 모든 fetch는 `fields[]` 명시 필수(이 plan의 fetcher 전부 준수). 재발 시 1회 재시도 후 진행.

---

## File Structure

| 파일 | 책임 |
|---|---|
| Create `harness/backbone/capacity_snapshot.py` | 순수 집계: outbound forward curve / inbound scheduled / snapshot 조립 / series append |
| Create `tests/backbone/test_capacity_snapshot.py` | 윈도우·커버리지·트랙분리(중복0 gate)·occupancy·append idempotency |
| Modify `utils/cbm_utils.py` (1줄 추가) | `fetch_inbound_cbm` records에 `center` 키 추가 (스냅샷 센터별 staging 점유율용) |
| Modify `tests/utils/test_cbm_utils.py` | center 키 테스트 1개 추가 |
| Create `scripts/backbone/seed_max_cbm.py` | WMS_Location `Max_CBM` 필드 신설(Meta API) + A1-IB-001=57.6 시드 (dry-run 기본, --write) |
| Create `scripts/backbone/capacity_snapshot_run.py` | IO runner: 3트랙 fetch → snapshot → `data/capacity_series.json` idempotent append |
| Create `data/capacity_series.json` | 시계열 (첫 real run 산출물, GHA가 daily commit) |
| Create `.github/workflows/capacity_snapshot.yml` | daily cron KST 07:30 + dry_run dispatch + series commit (scorecard 패턴) |

---

## Task 1: 순수 모듈 — `build_outbound_forward`

**Files:**
- Create: `harness/backbone/capacity_snapshot.py`
- Test: `tests/backbone/test_capacity_snapshot.py`

- [ ] **Step 1: Write the failing tests**

`tests/backbone/test_capacity_snapshot.py` 신규:

```python
"""capacity_snapshot 테스트 (P4) — 윈도우/커버리지/트랙분리/append idempotency."""
from datetime import date

from harness.backbone.capacity_snapshot import build_outbound_forward

TODAY = date(2026, 6, 11)


def _ship(d, cbm):
    return {"ship_date": d, "cbm_valid": cbm}


class TestOutboundForward:
    def test_window_includes_today_through_horizon(self):
        rows = [_ship("2026-06-11", 1.0), _ship("2026-06-25", 2.0),
                _ship("2026-06-26", 4.0)]  # +15d → 제외
        out = build_outbound_forward(rows, TODAY, horizon_days=14)
        assert out["forward_by_date"] == {"2026-06-11": 1.0, "2026-06-25": 2.0}
        assert out["forward_total_cbm"] == 3.0
        assert out["n_shipments_window"] == 2

    def test_past_and_blank_dates_excluded(self):
        rows = [_ship("2026-06-10", 1.0), _ship(None, 5.0), _ship("", 5.0)]
        out = build_outbound_forward(rows, TODAY)
        assert out["n_shipments_window"] == 0
        assert out["forward_total_cbm"] == 0.0

    def test_coverage_counts_zero_cbm_rows_in_denominator(self):
        rows = [_ship("2026-06-12", 2.0), _ship("2026-06-12", 0)]
        out = build_outbound_forward(rows, TODAY)
        assert out["n_shipments_window"] == 2
        assert out["n_with_cbm"] == 1
        assert out["coverage_pct"] == 50.0

    def test_same_date_accumulates(self):
        rows = [_ship("2026-06-12", 1.5), _ship("2026-06-12", 2.5)]
        out = build_outbound_forward(rows, TODAY)
        assert out["forward_by_date"] == {"2026-06-12": 4.0}

    def test_empty_input_no_zerodivision(self):
        out = build_outbound_forward([], TODAY)
        assert out["coverage_pct"] == 0.0
        assert out["forward_by_date"] == {}

    def test_datetime_string_truncated_to_date(self):
        out = build_outbound_forward([_ship("2026-06-12T09:00:00.000Z", 1.0)], TODAY)
        assert out["forward_by_date"] == {"2026-06-12": 1.0}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/backbone/test_capacity_snapshot.py -q`
Expected: FAIL — `ModuleNotFoundError` 또는 `ImportError: cannot import name 'build_outbound_forward'`

- [ ] **Step 3: Write minimal implementation**

`harness/backbone/capacity_snapshot.py` 신규:

```python
"""capacity_snapshot — 3트랙(출고/보관/입하) event-boundary 집계 (P4, pure logic).

각 트랙은 자기 event boundary 1곳에서만 카운트 (spec §9-6 lifecycle 4중 카운트 방지):
출고=shipment.출하확정일 / 보관=InventoryLedger point-in-time / 입하=movement.입하예상일.
트랙 간 합산 필드는 만들지 않는다 — "1주문 트랙간 중복 0" gate를 스키마로 충족.
MES 납기일 forecast는 입하 트랙 내 별도 컴포넌트 (scheduled와 합산 금지).
모든 집계에 커버리지% 동반 (no silent under-count).
"""
from __future__ import annotations

from datetime import date, timedelta

HORIZON_DAYS = 14   # 사용자 CP 2026-06-11

EVENT_BOUNDARIES = {
    "outbound": "shipment.출하확정일",
    "storage": "inventory_ledger.point_in_time",
    "inbound": "movement.입하예상일",
}


def _parse_date(raw) -> date | None:
    try:
        return date.fromisoformat(str(raw or "")[:10])
    except ValueError:
        return None


def build_outbound_forward(
    shipment_rows: list[dict], today: date, horizon_days: int = HORIZON_DAYS,
) -> dict:
    """[{ship_date, cbm_valid}] → 윈도우(today..today+h) forward curve.

    coverage_pct 분모 = 윈도우 내 shipment 전체 (CBM 0 행 포함 — no silent under-count).
    """
    end = today + timedelta(days=horizon_days)
    by_date: dict[str, float] = {}
    n_window = n_with_cbm = 0
    for row in shipment_rows:
        d = _parse_date(row.get("ship_date"))
        if d is None or not (today <= d <= end):
            continue
        n_window += 1
        cbm = float(row.get("cbm_valid") or 0)
        if cbm > 0:
            n_with_cbm += 1
            key = d.isoformat()
            by_date[key] = round(by_date.get(key, 0.0) + cbm, 4)
    return {
        "forward_by_date": dict(sorted(by_date.items())),
        "forward_total_cbm": round(sum(by_date.values()), 4),
        "n_shipments_window": n_window,
        "n_with_cbm": n_with_cbm,
        "coverage_pct": round(n_with_cbm / n_window * 100, 1) if n_window else 0.0,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/backbone/test_capacity_snapshot.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add harness/backbone/capacity_snapshot.py tests/backbone/test_capacity_snapshot.py
git commit -m "feat(backbone): 출고 forward curve 집계 — 14d 윈도우·커버리지% (P4 T1)"
```

---

## Task 2: 입하 scheduled 집계 + cbm_utils `center` 키

**Files:**
- Modify: `harness/backbone/capacity_snapshot.py` (함수 2개 추가)
- Modify: `utils/cbm_utils.py:249-257` (rows.append dict에 1줄)
- Test: `tests/backbone/test_capacity_snapshot.py`, `tests/utils/test_cbm_utils.py`

- [ ] **Step 1: Write the failing tests**

`tests/backbone/test_capacity_snapshot.py`에 추가:

```python
from harness.backbone.capacity_snapshot import (  # 기존 import 줄에 병합
    build_inbound_scheduled, build_outbound_forward, normalize_center,
)


def _mov(d, cbm, src="mov", center="에이원지식산업센터"):
    return {"exp_date": d, "cbm": cbm, "spec_src": src, "center": center}


class TestNormalizeCenter:
    def test_a1_variant_maps_to_warehouse_key(self):
        assert normalize_center("에이원지식산업센터") == "에이원센터"

    def test_bestone(self):
        assert normalize_center("베스트원") == "베스트원"

    def test_unknown_or_blank(self):
        assert normalize_center("") == "기타"
        assert normalize_center(None) == "기타"


class TestInboundScheduled:
    def test_window_filter_and_center_grouping(self):
        recs = [_mov("2026-06-12", 1.0), _mov("2026-06-13", 2.0, center="베스트원"),
                _mov("2026-06-26", 9.0)]  # +15d → 제외
        out = build_inbound_scheduled(recs, TODAY, horizon_days=14)
        assert out["scheduled_by_date"] == {"2026-06-12": 1.0, "2026-06-13": 2.0}
        assert out["scheduled_total_cbm"] == 3.0
        assert out["by_center"]["에이원센터"]["total_cbm"] == 1.0
        assert out["by_center"]["베스트원"]["by_date"] == {"2026-06-13": 2.0}

    def test_unmatched_rows_in_coverage_denominator(self):
        recs = [_mov("2026-06-12", 1.0), _mov("2026-06-13", 0.0, src="none")]
        out = build_inbound_scheduled(recs, TODAY)
        assert out["n_rows_window"] == 2
        assert out["coverage_pct"] == 50.0

    def test_dateless_rows_skipped(self):
        out = build_inbound_scheduled([_mov("날짜없음", 1.0)], TODAY)
        assert out["n_rows_window"] == 0

    def test_empty_no_zerodivision(self):
        out = build_inbound_scheduled([], TODAY)
        assert out["coverage_pct"] == 0.0
```

`tests/utils/test_cbm_utils.py`에 추가 (기존 파일의 mock/fixture 패턴을 따를 것 — `fetch_inbound_cbm`을 이미 테스트 중이면 그 픽스처에 center 단언 1개 추가, 없으면 `monkeypatch.setattr("utils.cbm_utils.get_all_records", ...)` 로 1건 주입):

```python
def test_fetch_inbound_cbm_records_include_center(monkeypatch):
    import utils.cbm_utils as cu

    fake = [{"fields": {
        cu.FLD_MOV_ITEM: "PT0001-박스 || PNA1_프로젝트 || 에이원지식산업센터",
        cu.FLD_MOV_IN_QTY: 2,
        cu.FLD_MOV_SPEC: "100*100*100",
        cu.FLD_MOV_EXP_DATE: "2026-06-12",
    }}]
    monkeypatch.setattr(cu, "get_all_records", lambda *a, **k: fake)
    out = cu.fetch_inbound_cbm({})
    assert out["records"][0]["center"] == "에이원지식산업센터"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/backbone/test_capacity_snapshot.py tests/utils/test_cbm_utils.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_inbound_scheduled'` / center `KeyError`

- [ ] **Step 3: Write minimal implementation**

`harness/backbone/capacity_snapshot.py`에 추가:

```python
def normalize_center(raw) -> str:
    """movement 이동물품 3번째 토큰('에이원지식산업센터' 등) → Location.Warehouse 키."""
    s = str(raw or "")
    if "에이원" in s:
        return "에이원센터"
    if "베스트원" in s:
        return "베스트원"
    return "기타"


def build_inbound_scheduled(
    records: list[dict], today: date, horizon_days: int = HORIZON_DAYS,
) -> dict:
    """fetch_inbound_cbm records → 윈도우 입하 예정 by_date/by_center.

    records: [{exp_date, cbm, spec_src, center}]. coverage_pct 분모 = 윈도우 행 전체,
    분자 = 규격 해소 성공(spec_src != 'none').
    """
    end = today + timedelta(days=horizon_days)
    by_date: dict[str, float] = {}
    by_center: dict[str, dict] = {}
    n_window = n_matched = 0
    for r in records:
        d = _parse_date(r.get("exp_date"))
        if d is None or not (today <= d <= end):
            continue
        n_window += 1
        if r.get("spec_src", "none") != "none":
            n_matched += 1
        cbm = float(r.get("cbm") or 0)
        if cbm <= 0:
            continue
        key = d.isoformat()
        by_date[key] = round(by_date.get(key, 0.0) + cbm, 4)
        ce = by_center.setdefault(normalize_center(r.get("center")),
                                  {"total_cbm": 0.0, "by_date": {}})
        ce["total_cbm"] = round(ce["total_cbm"] + cbm, 4)
        ce["by_date"][key] = round(ce["by_date"].get(key, 0.0) + cbm, 4)
    return {
        "scheduled_by_date": dict(sorted(by_date.items())),
        "scheduled_total_cbm": round(sum(by_date.values()), 4),
        "n_rows_window": n_window,
        "coverage_pct": round(n_matched / n_window * 100, 1) if n_window else 0.0,
        "by_center": by_center,
    }
```

`utils/cbm_utils.py` — `rows.append({...})` (line 249-257) dict에 1줄 추가:

```python
        rows.append({
            "parts_code": parts_code,
            "parts_name": parsed["parts_name"],
            "center":     parsed["center"],
            "supplier":   supplier,
            "exp_date":   d_key,
            "in_qty":     in_qty,
            "spec_src":   src,
            "cbm":        cbm,
        })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/backbone/test_capacity_snapshot.py tests/utils/test_cbm_utils.py -q`
Expected: 전부 passed (Task 1의 6개 + 신규 8개 + 기존 cbm_utils 테스트)

- [ ] **Step 5: Commit**

```bash
git add harness/backbone/capacity_snapshot.py utils/cbm_utils.py tests/backbone/test_capacity_snapshot.py tests/utils/test_cbm_utils.py
git commit -m "feat(backbone): 입하 scheduled 집계 + movement center 키 — 센터별 staging 점유율 입력 (P4 T2)"
```

---

## Task 3: snapshot 조립 + append_series — 트랙간 중복 0 gate

**Files:**
- Modify: `harness/backbone/capacity_snapshot.py`
- Test: `tests/backbone/test_capacity_snapshot.py`

- [ ] **Step 1: Write the failing tests**

```python
from harness.backbone.capacity_snapshot import (  # import 줄에 병합
    EVENT_BOUNDARIES, append_series, build_snapshot,
)

# aggregate_occupied 출력 스키마 그대로 (harness/backbone/storage.py)
STORAGE_AGG = {
    "by_warehouse": {"베스트원": {"occupied_cbm": 306.24, "n_rows": 100,
                                "pt_covered": 135, "pt_uncovered": 166,
                                "stock_uncovered": 5000.0}},
    "total_occupied_cbm": 306.24,
    "pt_coverage_pct": 44.9,
    "uncovered_pts": [],
    "n_rows_filtered": 100,
}


def make_snap(mes=None, storage_max=None, staging_max=None):
    outbound = build_outbound_forward([_ship("2026-06-12", 3.0)], TODAY)
    inbound = build_inbound_scheduled([_mov("2026-06-12", 1.0)], TODAY)
    return build_snapshot(TODAY, outbound, STORAGE_AGG, inbound, mes,
                          storage_max_cbm=storage_max, staging_max_cbm=staging_max,
                          generated_at="2026-06-11T07:30:00+09:00")


class TestSnapshotTrackSeparation:
    """Gate: 1주문 트랙간 중복 0 — 트랙 간 합산 필드 부재 + boundary 태깅."""

    def test_three_tracks_with_event_boundaries(self):
        snap = make_snap()
        assert set(snap["tracks"]) == {"outbound", "storage", "inbound"}
        for t, b in EVENT_BOUNDARIES.items():
            assert snap["tracks"][t]["event_boundary"] == b

    def test_no_cross_track_sum_field(self):
        snap = make_snap()
        # top-level에 트랙 횡단 합산 키 없음 — 각 트랙 숫자는 자기 입력만 반영
        assert not any("cbm" in k.lower() or "total" in k.lower() for k in snap)
        assert snap["tracks"]["outbound"]["forward_total_cbm"] == 3.0
        assert snap["tracks"]["inbound"]["scheduled_total_cbm"] == 1.0
        assert snap["tracks"]["storage"]["occupied_total_cbm"] == 306.24

    def test_mes_kept_separate_from_scheduled(self):
        mes = {"by_horizon": {7: 2.49, 14: 4.83}, "n_joined": 31, "n_total": 100}
        snap = make_snap(mes=mes)
        inb = snap["tracks"]["inbound"]
        assert inb["mes_forecast"]["by_horizon"] == {"7": 2.49, "14": 4.83}
        assert inb["scheduled_total_cbm"] == 1.0   # MES 미합산

    def test_mes_none_when_pat_missing(self):
        assert make_snap(mes=None)["tracks"]["inbound"]["mes_forecast"] is None


class TestOccupancy:
    def test_storage_occupancy_with_max(self):
        snap = make_snap(storage_max={"베스트원": 500.0})
        wh = snap["tracks"]["storage"]["by_warehouse"]["베스트원"]
        assert wh["occupancy_pct"] == 61.2          # 306.24/500

    def test_storage_occupancy_none_without_max(self):
        wh = make_snap()["tracks"]["storage"]["by_warehouse"]["베스트원"]
        assert wh["max_cbm"] is None and wh["occupancy_pct"] is None

    def test_staging_peak_day(self):
        snap = make_snap(staging_max={"에이원센터": 57.6})
        st = snap["tracks"]["inbound"]["staging"]["에이원센터"]
        assert st["max_cbm"] == 57.6
        assert st["peak_day_cbm"] == 1.0
        assert st["peak_day_pct"] == 1.7            # 1.0/57.6

    def test_staging_no_arrivals_zero_not_error(self):
        snap = make_snap(staging_max={"베스트원": 10.0})  # 베스트원 입하 0건
        st = snap["tracks"]["inbound"]["staging"]["베스트원"]
        assert st["peak_day_cbm"] == 0.0 and st["peak_date"] is None


class TestAppendSeries:
    def test_appends_new_date(self):
        s1 = make_snap()
        out = append_series([], s1)
        assert len(out) == 1

    def test_replaces_same_date_idempotent(self):
        s1, s2 = make_snap(), make_snap(mes={"by_horizon": {7: 1.0, 14: 2.0},
                                             "n_joined": 1, "n_total": 1})
        out = append_series([s1], s2)
        assert len(out) == 1
        assert out[0]["tracks"]["inbound"]["mes_forecast"] is not None

    def test_sorted_by_snapshot_date(self):
        a = dict(make_snap(), snapshot_date="2026-06-12")
        b = dict(make_snap(), snapshot_date="2026-06-10")
        out = append_series([a], b)
        assert [s["snapshot_date"] for s in out] == ["2026-06-10", "2026-06-12"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/backbone/test_capacity_snapshot.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_snapshot'`

- [ ] **Step 3: Write minimal implementation**

`harness/backbone/capacity_snapshot.py`에 추가:

```python
def _staging_occupancy(by_center: dict, staging_max_cbm: dict | None) -> dict:
    """센터별 입하 피크일 CBM vs 입하장 Max_CBM (시드된 센터만)."""
    out = {}
    for wh, mx in (staging_max_cbm or {}).items():
        dates = (by_center.get(wh) or {}).get("by_date") or {}
        if not dates or not mx:
            out[wh] = {"max_cbm": mx, "peak_date": None,
                       "peak_day_cbm": 0.0, "peak_day_pct": 0.0}
            continue
        peak_date, peak = max(dates.items(), key=lambda kv: kv[1])
        out[wh] = {"max_cbm": mx, "peak_date": peak_date,
                   "peak_day_cbm": peak,
                   "peak_day_pct": round(peak / mx * 100, 1)}
    return out


def build_snapshot(
    today: date,
    outbound: dict,
    storage_agg: dict,
    inbound_sched: dict,
    mes_forecast: dict | None,
    storage_max_cbm: dict | None = None,
    staging_max_cbm: dict | None = None,
    horizon_days: int = HORIZON_DAYS,
    generated_at: str | None = None,
) -> dict:
    """3트랙 스냅샷 1건 조립 — 트랙 간 합산 없음, 각 트랙 자기 boundary만.

    storage_agg = storage.aggregate_occupied() 출력 / mes_forecast =
    mes_forecast.build_inbound_forecast() 출력 또는 None(MES PAT 부재).
    *_max_cbm = {Warehouse: m³} — WMS_Location.Max_CBM 시드행만.
    """
    by_wh = {}
    for wh, e in storage_agg["by_warehouse"].items():
        mx = (storage_max_cbm or {}).get(wh)
        by_wh[wh] = {
            "occupied_cbm": round(e["occupied_cbm"], 4),
            "max_cbm": mx,
            "occupancy_pct": round(e["occupied_cbm"] / mx * 100, 1) if mx else None,
        }
    mes_part = None
    if mes_forecast is not None:
        mes_part = {
            "by_horizon": {str(h): v for h, v in mes_forecast["by_horizon"].items()},
            "n_joined": mes_forecast["n_joined"],
            "n_total": mes_forecast["n_total"],
        }
    inbound = {k: v for k, v in inbound_sched.items() if k != "by_center"}
    return {
        "snapshot_date": today.isoformat(),
        "generated_at": generated_at,
        "horizon_days": horizon_days,
        "tracks": {
            "outbound": {"event_boundary": EVENT_BOUNDARIES["outbound"], **outbound},
            "storage": {
                "event_boundary": EVENT_BOUNDARIES["storage"],
                "occupied_total_cbm": storage_agg["total_occupied_cbm"],
                "by_warehouse": by_wh,
                "pt_coverage_pct": storage_agg["pt_coverage_pct"],
            },
            "inbound": {
                "event_boundary": EVENT_BOUNDARIES["inbound"],
                **inbound,
                "staging": _staging_occupancy(inbound_sched.get("by_center", {}),
                                              staging_max_cbm),
                "mes_forecast": mes_part,
            },
        },
    }


def append_series(series: list[dict], snapshot: dict) -> list[dict]:
    """idempotent append — 같은 snapshot_date 항목 교체, 날짜순 정렬."""
    out = [s for s in series if s.get("snapshot_date") != snapshot["snapshot_date"]]
    out.append(snapshot)
    out.sort(key=lambda s: s.get("snapshot_date", ""))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/backbone/test_capacity_snapshot.py -q`
Expected: 전부 passed (누적 ~23개)

- [ ] **Step 5: Run full suite (regression)**

Run: `python -m pytest tests/ -q`
Expected: 기존 337 + 신규, 1 known fail(W1 — P5 불가침)

- [ ] **Step 6: Commit**

```bash
git add harness/backbone/capacity_snapshot.py tests/backbone/test_capacity_snapshot.py
git commit -m "feat(backbone): 3트랙 snapshot 조립 + series append — 트랙간 합산 0·occupancy·idempotent (P4 T3)"
```

---

## Task 4: `seed_max_cbm.py` — Max_CBM 필드 신설 + A1-IB-001 시드

**Files:**
- Create: `scripts/backbone/seed_max_cbm.py`

사용자 실측 도착(2026-06-11 CP 승인): A1-IB-001 = 57.6m³. WMS_Location은 `_WRITE_ALLOWLIST` 내, master data PATCH (ledger 아님 — Immutable Ledger 무관).
Meta API 필드 신설은 P3' 학습 반영: **number 필드 생성은 지원**(create_tables.py 선례), select options 변경만 미지원.

- [ ] **Step 1: Write the script**

```python
"""P4 — WMS_Location.Max_CBM 필드 신설 + 실측치 시드 (사용자 CP 2026-06-11).

실측(에이원센터 입하장 A1-IB-001):
  1,200×1,200×1,200mm ×12 = 20.736m³ + 800×600×1,200mm ×64 = 36.864m³ → 57.6m³
보관(베스트원 ST) 분모는 미도착 — 도착 시 SEEDS에 추가 후 재실행 (idempotent).
TMS Location.Max_CBM 재사용 금지(다른 물리량) — WMS_Location 네이티브 신설.

Usage:
  python scripts/backbone/seed_max_cbm.py            # dry-run
  python scripts/backbone/seed_max_cbm.py --write
"""
import argparse
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()
WP = os.environ["AIRTABLE_WMS_PAT"]
WMS = "appLui4ZR5HWcQRri"
LOC = "tblRwUTP5kWnHFt5P"
HEADERS = {"Authorization": f"Bearer {WP}", "Content-Type": "application/json"}

SEEDS = {"A1-IB-001": 57.6}   # Location_ID → m³ (실측 2026-06-11)


def field_exists() -> bool:
    r = requests.get(f"https://api.airtable.com/v0/meta/bases/{WMS}/tables",
                     headers=HEADERS, timeout=60)
    r.raise_for_status()
    tbl = next(t for t in r.json()["tables"] if t["id"] == LOC)
    return any(f["name"] == "Max_CBM" for f in tbl["fields"])


def create_field():
    r = requests.post(
        f"https://api.airtable.com/v0/meta/bases/{WMS}/tables/{LOC}/fields",
        headers=HEADERS, timeout=60,
        json={"name": "Max_CBM", "type": "number",
              "description": "물리 부피 용량 m³ (실측 시드 — P4 2026-06-11)",
              "options": {"precision": 3}},
    )
    r.raise_for_status()
    print("  Max_CBM 필드 신설 완료")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    exists = field_exists()
    print(f"Max_CBM 필드: {'있음' if exists else '없음 (신설 필요)'}")
    if not exists:
        if args.write:
            create_field()
        else:
            print("  [DRY-RUN] --write 시 신설")

    r = requests.get(f"https://api.airtable.com/v0/{WMS}/{LOC}",
                     headers=HEADERS, timeout=60,
                     params={"pageSize": 100,
                             "fields[]": ["Location_ID", "Max_CBM"]})
    r.raise_for_status()
    locs = {rec["fields"].get("Location_ID"): rec for rec in r.json()["records"]}

    for loc_id, target in SEEDS.items():
        rec = locs.get(loc_id)
        if not rec:
            print(f"  ❌ {loc_id}: Location 행 없음 — skip")
            continue
        cur = rec["fields"].get("Max_CBM")
        if cur == target:
            print(f"  = {loc_id}: 이미 {target}m³ — skip (idempotent)")
            continue
        if not args.write:
            print(f"  [DRY-RUN] {loc_id}: {cur} → {target}m³")
            continue
        pr = requests.patch(f"https://api.airtable.com/v0/{WMS}/{LOC}/{rec['id']}",
                            headers=HEADERS, timeout=60,
                            json={"fields": {"Max_CBM": target}})
        pr.raise_for_status()
        print(f"  ✅ {loc_id}: {cur} → {target}m³ PATCH 완료")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Dry-run으로 검증**

Run: `python scripts/backbone/seed_max_cbm.py`
Expected: `Max_CBM 필드: 없음 (신설 필요)` + `[DRY-RUN] A1-IB-001: None → 57.6m³`

- [ ] **Step 3: Write 실행**

Run: `python scripts/backbone/seed_max_cbm.py --write`
Expected: 필드 신설 + `✅ A1-IB-001: None → 57.6m³ PATCH 완료`

- [ ] **Step 4: 재실행 idempotency 확인**

Run: `python scripts/backbone/seed_max_cbm.py --write`
Expected: `= A1-IB-001: 이미 57.6m³ — skip (idempotent)`

- [ ] **Step 5: Commit**

```bash
git add scripts/backbone/seed_max_cbm.py
git commit -m "feat(backbone): WMS_Location.Max_CBM 신설 + A1-IB-001 57.6m³ 시드 — 입하장 실측 CP 승인 (P4 T4)"
```

---

## Task 5: IO runner `capacity_snapshot_run.py` + 첫 series 엔트리

**Files:**
- Create: `scripts/backbone/capacity_snapshot_run.py`
- Create (실행 산출물): `data/capacity_series.json`

- [ ] **Step 1: Write the runner**

```python
"""P4 — capacity_series.json 시계열 runner (Airtable write 0, 로컬 파일만).

3트랙을 스냅샷 1건으로 집계해 data/capacity_series.json에 idempotent append.
출고: TMS Shipment(출하확정일 14d 윈도우, CBM_유효) / 보관: InventoryLedger×ItemMaster
/ 입하: movement(입하예상일 14d 윈도우, EXTERNAL_INBOUND_PURPOSES) + MES 납기일
forecast(AIRTABLE_MES_PAT 부재·실패 시 null 생략 — 핵심 3트랙은 영향 없음).

Usage:
  python scripts/backbone/capacity_snapshot_run.py            # series append
  python scripts/backbone/capacity_snapshot_run.py --dry-run  # 스냅샷 출력만
"""
import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness._core.calendar import KST, today_kst  # noqa: E402
from harness.backbone.capacity_snapshot import (  # noqa: E402
    HORIZON_DAYS, append_series, build_inbound_scheduled,
    build_outbound_forward, build_snapshot,
)
from harness.backbone.keys import normalize_goods  # noqa: E402
from harness.backbone.mes_forecast import build_inbound_forecast  # noqa: E402
from harness.backbone.storage import (  # noqa: E402
    aggregate_occupied, parse_pt_from_ledger_key,
)
from harness.settlement.cbm_calc import load_product_lookup  # noqa: E402
from utils.cbm_utils import (  # noqa: E402
    EXTERNAL_INBOUND_PURPOSES, fetch_inbound_cbm, load_sync_parts_lookup,
)

load_dotenv()
TP = os.environ["AIRTABLE_PAT"]
WP = os.environ["AIRTABLE_WMS_PAT"]
MP = os.environ.get("AIRTABLE_MES_PAT")   # 없으면 MES forecast 생략
TMS = "app4x70a8mOrIKsMf"
WMS = "appLui4ZR5HWcQRri"
MES = "appNSAPadsHbfaSHv"
SHIP = "tbllg1JoHclGYer7m"
ITEM = "tbl5ZGY373D5SCONV"     # WMS_ItemMaster
LEDGER = "tbl4DcXQRHJj921MN"   # WMS_InventoryLedger
LOC = "tblRwUTP5kWnHFt5P"      # WMS_Location
MES_V2 = "tblg96ys2vfPdyxHq"   # MES ver.2.0 (primary)
SYNC_ITEM = "tblwnNgHQxZ0WhDBh"
SERIES_PATH = Path(__file__).resolve().parents[2] / "data" / "capacity_series.json"


def fetch(base, tid, pat, fields, formula=None):
    out, off = [], None
    while True:
        p = {"pageSize": 100, "fields[]": fields}
        if off:
            p["offset"] = off
        if formula:
            p["filterByFormula"] = formula
        r = requests.get(f"https://api.airtable.com/v0/{base}/{tid}",
                         headers={"Authorization": f"Bearer {pat}"},
                         params=p, timeout=60)
        r.raise_for_status()
        d = r.json()
        out += d["records"]
        off = d.get("offset")
        if not off:
            break
    return out


def n(x):
    try:
        return float(str(x).replace(",", "") or 0)
    except (ValueError, TypeError):
        return 0.0


def collect_outbound(today):
    """출하확정일 윈도우 서버필터 — CBM_유효 formula coalesce 소비."""
    end = today + timedelta(days=HORIZON_DAYS)
    formula = (
        "AND({출하확정일}!='', "
        f"IS_AFTER({{출하확정일}}, DATEADD('{today.isoformat()}', -1, 'days')), "
        f"IS_BEFORE({{출하확정일}}, DATEADD('{end.isoformat()}', 1, 'days')))"
    )
    recs = fetch(TMS, SHIP, TP, ["출하확정일", "CBM_유효"], formula)
    rows = [{"ship_date": r["fields"].get("출하확정일"),
             "cbm_valid": n(r["fields"].get("CBM_유효"))} for r in recs]
    print(f"  출고: 윈도우 {len(rows)}건", flush=True)
    return build_outbound_forward(rows, today)


def collect_storage_and_max():
    """보관 occupied 분자 (storage_occupied.py 패턴) + Max_CBM 분모 맵."""
    locs = {r["id"]: r["fields"]
            for r in fetch(WMS, LOC, WP, ["Warehouse", "Zone_Type", "Max_CBM"])}
    storage_max, staging_max = {}, {}
    for f in locs.values():
        mx = n(f.get("Max_CBM"))
        if mx <= 0:
            continue
        wh = f.get("Warehouse") or "미지정"
        if f.get("Zone_Type") == "STORAGE":
            storage_max[wh] = round(storage_max.get(wh, 0.0) + mx, 4)
        elif f.get("Zone_Type") == "INBOUND_STAGING":
            staging_max[wh] = round(staging_max.get(wh, 0.0) + mx, 4)
    items = fetch(WMS, ITEM, WP, ["품목키", "CBM_개당_m3"])
    part_cbm = {r["fields"]["품목키"]: r["fields"]["CBM_개당_m3"]
                for r in items
                if (r["fields"].get("CBM_개당_m3") or 0) > 0
                and parse_pt_from_ledger_key(str(r["fields"].get("품목키", "")))}
    ledger = fetch(WMS, LEDGER, WP,
                   ["Ledger_Key", "Current_Stock", "Location", "Stock_Type"])
    rows = []
    for rec in ledger:
        f = rec.get("fields", {})
        pt = parse_pt_from_ledger_key(str(f.get("Ledger_Key", "")))
        if not pt:
            continue
        loc_ids = f.get("Location") or []
        loc = locs.get(loc_ids[0], {}) if loc_ids else {}
        rows.append({"pt": pt, "stock": f.get("Current_Stock") or 0,
                     "warehouse": loc.get("Warehouse") or "미지정",
                     "zone_type": loc.get("Zone_Type") or "",
                     "stock_type": f.get("Stock_Type") or ""})
    agg = aggregate_occupied(rows, part_cbm)
    print(f"  보관: occupied {agg['total_occupied_cbm']}m³ "
          f"(PT 커버 {agg['pt_coverage_pct']}%) | Max 시드 "
          f"storage={storage_max} staging={staging_max}", flush=True)
    return agg, storage_max, staging_max


def collect_inbound(today):
    """movement 입하예상일 윈도우 — 외부입하 subset (CP② 분류)."""
    sp_lookup = load_sync_parts_lookup()
    out = fetch_inbound_cbm(sp_lookup, since=today,
                            until=today + timedelta(days=HORIZON_DAYS),
                            purposes=EXTERNAL_INBOUND_PURPOSES)
    print(f"  입하: 윈도우 {len(out['records'])}건 "
          f"(규격해소 {out['n_matched']}/{out['n_matched'] + out['n_unmatched']})",
          flush=True)
    return build_inbound_scheduled(out["records"], today)


def collect_mes(today):
    """MES 납기일 forecast — PAT 부재/요청 실패 시 None (graceful skip)."""
    if not MP:
        print("  MES: AIRTABLE_MES_PAT 미설정 — forecast 생략(null)", flush=True)
        return None
    try:
        mes = fetch(MES, MES_V2, MP, ["굿즈", "계획수량", "납기일", "작업 상태"])
        items = fetch(WMS, SYNC_ITEM, WP, ["굿즈명", "굿즈코드"])
        name2code = {}
        for r in items:
            f = r["fields"]
            nm = normalize_goods(str(f.get("굿즈명") or ""))
            cd = str(f.get("굿즈코드") or "").strip().upper()
            if nm and cd:
                name2code[nm] = cd
        lk = load_product_lookup({"Authorization": f"Bearer {TP}"})
        product_by_code = {}
        for e in lk.values():
            code = str(e.get("code") or "").strip().upper()
            if code and e.get("cbm_per_box", 0) > 0:
                product_by_code[code] = (e.get("qty_per_box") or 1, e["cbm_per_box"])
        out = build_inbound_forecast([r["fields"] for r in mes],
                                     name2code, product_by_code, today)
        print(f"  MES: join {out['n_joined']}/{out['n_total']} | "
              f"by_horizon {out['by_horizon']}", flush=True)
        return out
    except requests.RequestException as e:
        print(f"  MES: 요청 실패({e.__class__.__name__}) — forecast 생략(null)", flush=True)
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="스냅샷 출력만, 파일 미기록")
    args = ap.parse_args()

    today = today_kst()
    print(f"=== capacity snapshot {today} (horizon {HORIZON_DAYS}d) ===", flush=True)
    outbound = collect_outbound(today)
    storage_agg, storage_max, staging_max = collect_storage_and_max()
    inbound = collect_inbound(today)
    mes = collect_mes(today)

    snap = build_snapshot(today, outbound, storage_agg, inbound, mes,
                          storage_max_cbm=storage_max, staging_max_cbm=staging_max,
                          generated_at=datetime.now(KST).isoformat())

    print("\n--- snapshot 요약 ---")
    print(f"출고 forward 14d: {outbound['forward_total_cbm']}m³ "
          f"({outbound['n_shipments_window']}건, 커버 {outbound['coverage_pct']}%)")
    print(f"보관 occupied: {storage_agg['total_occupied_cbm']}m³ "
          f"(PT 커버 {storage_agg['pt_coverage_pct']}%)")
    print(f"입하 scheduled 14d: {inbound['scheduled_total_cbm']}m³ "
          f"({inbound['n_rows_window']}건, 커버 {inbound['coverage_pct']}%)")
    print(f"MES forecast: {'null' if mes is None else mes['by_horizon']}")

    if args.dry_run:
        print("\n[DRY-RUN] 파일 미기록. snapshot JSON:")
        print(json.dumps(snap, ensure_ascii=False, indent=2))
        return

    series = []
    if SERIES_PATH.exists():
        series = json.loads(SERIES_PATH.read_text(encoding="utf-8"))
    series = append_series(series, snap)
    SERIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=SERIES_PATH.parent,
                                     suffix=".tmp", delete=False) as tf:
        json.dump(series, tf, ensure_ascii=False, indent=1)
        tmp = tf.name
    os.replace(tmp, SERIES_PATH)
    print(f"\n[APPEND] {SERIES_PATH.name}: {len(series)} 엔트리 "
          f"(snapshot_date {snap['snapshot_date']})", flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Dry-run 실행 (Airtable read-only 검증)**

Run: `python scripts/backbone/capacity_snapshot_run.py --dry-run`
Expected: 3트랙 요약 + snapshot JSON 출력. 보관 occupied ≈ 306m³대(P3' 값 근방), staging max에 `에이원센터: 57.6` 표시(Task 4 시드 후), MES는 로컬 `.env`에 `AIRTABLE_MES_PAT` 있으므로 by_horizon 출력.

- [ ] **Step 3: Real run — 첫 series 엔트리 생성**

Run: `python scripts/backbone/capacity_snapshot_run.py`
Expected: `[APPEND] capacity_series.json: 1 엔트리`

- [ ] **Step 4: Idempotency 확인 (같은 날 재실행 = 교체)**

Run: `python scripts/backbone/capacity_snapshot_run.py`
Expected: 여전히 `1 엔트리` (중복 append 없음)

- [ ] **Step 5: Commit**

```bash
git add scripts/backbone/capacity_snapshot_run.py data/capacity_series.json
git commit -m "feat(backbone): capacity snapshot runner + 첫 series 엔트리 — 3트랙 실데이터 (P4 T5)"
```

---

## Task 6: GHA cron `.github/workflows/capacity_snapshot.yml`

**Files:**
- Create: `.github/workflows/capacity_snapshot.yml`

- [ ] **Step 1: Write the workflow** (scorecard.yml commit 패턴 + wave_recommender.yml log artifact 패턴)

```yaml
name: Capacity Snapshot

on:
  schedule:
    # KST 07:30 매일 (UTC 22:30 전일)
    - cron: '30 22 * * *'
  workflow_dispatch:
    inputs:
      dry_run:
        description: 'Dry run (series 파일 미기록·미커밋)'
        required: false
        default: 'false'

jobs:
  snapshot:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Install dependencies
        run: pip install -r harness/requirements.txt

      - name: Run capacity snapshot
        shell: bash
        env:
          AIRTABLE_PAT: ${{ secrets.AIRTABLE_API_KEY_TMS }}
          AIRTABLE_WMS_PAT: ${{ secrets.AIRTABLE_API_KEY_WMS }}
          AIRTABLE_MES_PAT: ${{ secrets.AIRTABLE_API_KEY_MES }}
        run: |
          if [ "${{ github.event.inputs.dry_run || 'false' }}" = "true" ]; then
            python scripts/backbone/capacity_snapshot_run.py --dry-run | tee snapshot_log.txt
          else
            python scripts/backbone/capacity_snapshot_run.py | tee snapshot_log.txt
          fi

      - name: Upload snapshot log
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: capacity-snapshot-log
          path: snapshot_log.txt
          retention-days: 90
          overwrite: true
          if-no-files-found: ignore

      - name: Commit capacity_series.json
        if: github.event.inputs.dry_run != 'true'
        run: |
          git config user.email "github-actions@github.com"
          git config user.name "GitHub Actions"
          git add data/capacity_series.json || true
          git diff --cached --quiet || git commit -m "chore(backbone): capacity snapshot $(date -u -d '+9 hours' +%Y-%m-%d) [skip ci]"
          git push || true
```

주: `AIRTABLE_API_KEY_MES` secret은 현재 미등록 — runner가 null 생략 처리하므로 워크플로는 깨지지 않음. secret 등록 = 사용자 액션(Exit Handoff 기재).

- [ ] **Step 2: YAML 문법 검증**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/capacity_snapshot.yml', encoding='utf-8')); print('YAML OK')"`
Expected: `YAML OK`

- [ ] **Step 3: Full suite (최종 regression)**

Run: `python -m pytest tests/ -q`
Expected: 신규 포함 전부 green, 1 known fail(W1)

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/capacity_snapshot.yml
git commit -m "ci(backbone): capacity snapshot daily cron — KST 07:30 series commit (P4 T6)"
```

---

## Task 7: Gate 검증 + 리뷰 + Exit Handoff

- [ ] **Step 1: Validation Contract 증거 수집**

| Gate (spec §5 / P4행) | 증거 |
|---|---|
| forward curve 산출 | `data/capacity_series.json` 첫 엔트리: outbound.forward_by_date(14d) + inbound.scheduled_by_date + mes_forecast.by_horizon |
| 1주문 트랙간 중복 0 | `test_no_cross_track_sum_field` + 트랙별 event_boundary 태깅 (스키마로 구조 충족) |
| 커버리지% 동반 (각 트랙) | outbound.coverage_pct / storage.pt_coverage_pct / inbound.coverage_pct 전부 snapshot에 존재 |
| cron 상시화 | capacity_snapshot.yml (push 후 workflow_dispatch 1회 — 사용자 push 후 확인) |
| Max_CBM 시드 | A1-IB-001=57.6 PATCH 로그 + 재실행 skip + snapshot staging에 반영 |
| 소스 write 0 | runner Airtable write 0 (read-only) / seed는 allowlist 내 WMS_Location 1행 |

- [ ] **Step 2: `feature-dev:code-reviewer` + `harness-validator` 병행 호출** (직교 스코프)

- [ ] **Step 3: 리뷰 findings 반영 commit** (있을 시)

- [ ] **Step 4: Exit Handoff (chain done 5단계)**
  - master tracker P4 row `✅ DONE` + P5/P6 row 갱신 (P6 = READY 조건 충족: 전 입력 실점등)
  - 구현 기록 doc (본 plan 파일에 결과 추기 또는 별도 기록)
  - Obsidian log.md 항목 + notion-sync
  - 최종 commit + **사용자 수동 push 요청** (git 훅 차단) + push 후 workflow_dispatch 1회 확인 요청
  - 사용자 액션 잔여: GH secret `AIRTABLE_API_KEY_MES` 등록 (MES forecast 점등용)

---

## Out of Scope (P4)

- 과거 order 소스·W1 test·중복코드(P5) / 북극성 order-trigger 캐스케이드(P6) / name-bridge 개선 / Supabase 적재(대시보드 서브프로젝트 소관 — series JSON이 인터페이스) / WMS_Location `Occupancy_Rate` formula 필드(Meta API가 formula 생성 미지원 — occupancy는 series JSON에서 계산하므로 불필요)

## Risks

1. **Airtable 필드명 직접 fetch** — `출하확정일`/`CBM_유효`는 schema_pin 핀 완료. 이름 변경 시 fetch 0건 → 출고 트랙 0으로 드러남(silent 아님, n_shipments_window=0 로그).
2. **로컬 requests 간헐 timeout** — fields[] 제한으로 응답 경량화 + GHA(ubuntu)에서는 미재현. 로컬 실패 시 1회 재시도.
3. **formula 에러값** — `CBM_유효`가 에러 객체 반환 가능 → `n()` coercion으로 0 처리.
4. **cron series 충돌** — daily 1회 + idempotent append + `git push || true` (scorecard 선례). 같은 날 재실행은 교체.

---

## 구현 결과 (2026-06-11 — P4 완료 기록)

**커밋 8개** (T1~T6 + review fix, 전부 main): 출고 forward(T1) → 입하 scheduled+center(T2) → snapshot 조립+append(T3) → Max_CBM 시드(T4) → runner+첫 엔트리(T5) → GHA cron(T6) → review fix.

**테스트**: pytest **363 passed** + 1 known fail(W1 — P5 불가침, parent commit에서 동일 실패 검증됨). 신규 25개(capacity_snapshot 24 + cbm_utils center 1).

**첫 스냅샷 (2026-06-11, 실데이터)**:
- 출고 forward 14d: **284.10m³** (108건, 커버 **83.3%**)
- 보관 occupied: **306.24m³** (PT 커버 44.9%, 분모 베스트원 ST 실측 대기)
- 입하 scheduled 14d: **246.40m³** (284건, 커버 27.5% — 입하예정일 sparse, spec ~20% 예상과 정합)
- MES forecast: 7d **3.56m³** / 14d **5.34m³** (join 30/310)
- **staging peak 403.2%** (06-11 당일 232.2m³ vs A1-IB-001 57.6m³) — 입하 백로그 집중 신호, 대시보드 존재 이유 입증

**Max_CBM 시드**: 필드 신설(Meta API, number precision 3) + A1-IB-001 = **57.6m³** (1.2³m×12=20.736 + 0.8×0.6×1.2m×64=36.864), 재실행 idempotent skip 검증.

**검증**: harness-validator **PASS 6/6** (forward curve·중복0·커버리지·cron·시드·소스write0). code-reviewer 3 major 수정 — ① 입하 coverage 분자 엄격화(spec해소∧CBM>0) ② workflow `permissions: contents: write` 명시 ③ seed 페이지네이션. minor 1(14d=15캘린더일 inclusive)은 docstring 명시로 처리(MES days<=h 의미론과 정렬).

**사용자 잔여 액션**: ① 수동 push ② GH secret `AIRTABLE_API_KEY_MES` 등록 ③ push 후 `Capacity Snapshot` workflow_dispatch 1회 확인. → **전부 완료 (2026-06-11)**: push `4d914c0` 반영, secret 등록(run에서 MES join 31/311 확인), dispatch run 27319107681 success.

### 후속 fix (2026-06-11 같은 날) — series push가 main 보호에 거부됨

dispatch run은 green이었으나 step log 정밀 확인 결과 **bot commit push가 GH006(main = PR-only 보호)으로 거부**되고 `git push || true`가 삼킴 — reviewer가 경고한 silent-fail 모드가 token scope 아닌 branch protection으로 현실화. (동일 원인으로 scorecard.yml 월간 스냅샷 커밋도 한 번도 landed 안 함 — bot 커밋 0개 확인, P5 백로그.)

**해결 (사용자 선택: data branch 안)**: 시계열 SSOT를 비보호 **`capacity-data` 브랜치**로 이전 — ① run 전 `origin/capacity-data`에서 최신 series 복원(누적 무결성) ② append 후 `git push --force origin HEAD:capacity-data` (`|| true` 제거 — 실패는 red로 노출). main은 PR-only 유지, 브랜치는 매일 교체되지만 series 파일이 누적 이력 보유. 대시보드 소비 URL: `raw.githubusercontent.com/<repo>/capacity-data/data/capacity_series.json`. main의 `data/capacity_series.json`은 부트스트랩 copy로 동결.
