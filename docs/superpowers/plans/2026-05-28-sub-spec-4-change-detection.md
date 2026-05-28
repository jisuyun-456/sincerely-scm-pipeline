# Sub-Spec 4 Change Detection + 가정 OTIF — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** wave_recommender 파이프라인에 (1) 신규 TO 감지·Slack 알림 및 (2) 배송방식별 가정 OTIF 예측·JSONL 로그를 추가한다.

**Architecture:** `change_detector.py`와 `otif_estimator.py` 두 모듈을 신규 작성하고, `wave_recommender.py`의 `main()`이 이를 순서대로 호출한다. 스냅샷은 GitHub Actions artifact(90일 TTL)로 저장·복원한다. Airtable 스키마 변경 없음.

**Tech Stack:** Python 3.12, pytest, Airtable REST API, GitHub Actions `actions/upload-artifact@v4` / `actions/download-artifact@v4`

---

## File Map

| 상태 | 경로 | 역할 |
|---|---|---|
| **신규** | `harness/dispatch/change_detector.py` | 스냅샷 비교 → ChangeReport |
| **신규** | `harness/dispatch/otif_estimator.py` | 가정 POD 계산 → JSONL 기록 |
| **신규** | `tests/dispatch/test_logen_days.py` | C3: add_logen_days 일요일 skip |
| **신규** | `tests/dispatch/test_change_detector.py` | C1, C2: 신규/취소/변경 감지 |
| **신규** | `tests/dispatch/test_otif_estimator.py` | C4, C5: OTIF 4케이스 + JSONL |
| **수정** | `harness/dispatch/scheduling.py` | `add_logen_days()` 추가 |
| **수정** | `harness/dispatch/wave_recommender.py` | orchestration + digest 업데이트 |
| **수정** | `.github/workflows/wave_recommender.yml` | artifact 다운/업로드 스텝 추가 |

---

## Task 0: Pre-flight

**Files:** (없음)

- [ ] **Step 1: 기존 pytest baseline 확인**

```bash
cd "c:/Users/yjisu/Desktop/SCM_WORK"
python -m pytest tests/dispatch/ -q
```

Expected: `137 passed` (0 failures). 실패가 있으면 먼저 수정 후 진행.

- [ ] **Step 2: git status 확인**

```bash
git status
```

Expected: working tree clean (untracked 파일 외 modified 없음).

---

## Task 1: `add_logen_days` — scheduling.py TDD

**Files:**
- Create: `tests/dispatch/test_logen_days.py`
- Modify: `harness/dispatch/scheduling.py`

### 배경

로젠 SLA = 월~토 배송(일요일 휴무). `add_logen_days(start, n)` — `start`부터 일요일(weekday=6)만 건너뛰며 n일 전진.

- 2026-05-29 = 금요일
- 2026-05-30 = 토요일
- 2026-05-31 = 일요일

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/dispatch/test_logen_days.py
"""Tests for add_logen_days — 로젠 SLA (월~토, 일요일 skip)."""
from __future__ import annotations

from datetime import date

import pytest

from harness.dispatch.scheduling import add_logen_days


class TestAddLogenDays:
    """Contract C3 — 일요일 skip, 토요일 포함."""

    def test_friday_plus3_is_tuesday(self):
        # 금(05-29) → 토(+1) → 일 skip → 월(+2) → 화(+3)
        assert add_logen_days(date(2026, 5, 29), 3) == date(2026, 6, 2)

    def test_saturday_plus3_is_wednesday(self):
        # 토(05-30) → 일 skip → 월(+1) → 화(+2) → 수(+3)
        assert add_logen_days(date(2026, 5, 30), 3) == date(2026, 6, 3)

    def test_sunday_plus3_is_wednesday(self):
        # 일(05-31) → 월(+1) → 화(+2) → 수(+3)
        assert add_logen_days(date(2026, 5, 31), 3) == date(2026, 6, 3)

    def test_monday_plus3_is_thursday(self):
        # 월(06-01) → 화(+1) → 수(+2) → 목(+3) — 일요일 없음
        assert add_logen_days(date(2026, 6, 1), 3) == date(2026, 6, 4)

    def test_thursday_plus3_skips_sunday(self):
        # 목(06-04) → 금(+1) → 토(+2) → 일 skip → 월(+3)
        assert add_logen_days(date(2026, 6, 4), 3) == date(2026, 6, 8)
```

- [ ] **Step 2: 실패 확인**

```bash
python -m pytest tests/dispatch/test_logen_days.py -v
```

Expected: `ImportError` or `AttributeError: module 'harness.dispatch.scheduling' has no attribute 'add_logen_days'`

- [ ] **Step 3: `add_logen_days` 구현 (scheduling.py 맨 끝에 추가)**

`harness/dispatch/scheduling.py` 맨 끝에 다음을 추가:

```python
def add_logen_days(start: date, days: int) -> date:
    """출하확정일 + N일 (일요일만 skip). 로젠 SLA 기준 — 월~토 배송."""
    d, remaining = start, days
    while remaining > 0:
        d += timedelta(days=1)
        if d.weekday() != 6:  # 6 = Sunday
            remaining -= 1
    return d
```

- [ ] **Step 4: 통과 확인**

```bash
python -m pytest tests/dispatch/test_logen_days.py -v
```

Expected: `5 passed`

- [ ] **Step 5: 전체 회귀 확인**

```bash
python -m pytest tests/dispatch/ -q
```

Expected: `142 passed` (137 + 5)

- [ ] **Step 6: 커밋**

```bash
git add harness/dispatch/scheduling.py tests/dispatch/test_logen_days.py
git commit -m "feat(dispatch): add_logen_days 로젠 SLA (월~토, 일요일 skip) — C3"
```

---

## Task 2: `change_detector.py` TDD

**Files:**
- Create: `harness/dispatch/change_detector.py`
- Create: `tests/dispatch/test_change_detector.py`

### 배경

`detect(snapshot, current)` — 직전 스캔 스냅샷과 현재 Airtable 레코드를 비교해서 ChangeReport를 반환한다.

**스냅샷 포맷** (`{record_id: normalized_dict}`):
```json
{
  "recABC": {
    "출하확정일": "2026-06-01",
    "배송방식": "택배",
    "주소": "서울 강남구",
    "발송상태": "배송준비",
    "cbm": 1.5
  }
}
```

**Airtable 원시 레코드 포맷:**
```json
{"id": "recABC", "fields": {
  "fldQvmEwwzvQW95h9": "2026-06-01",
  "flduzH5tS7orqGG3o": ["택배"],
  "fldyJHUh9gN44Ggnh": ["서울 강남구"],
  "fldOhibgxg6LIpRTi": "배송준비",
  "fldaP8D9AM8CHEZ2o": 1.5
}}
```

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/dispatch/test_change_detector.py
"""Tests for change_detector — Contract C1 (신규 감지) / C2 (변경 감지)."""
from __future__ import annotations

import pytest

from harness.dispatch.change_detector import ChangeReport, detect


# ─── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _rec(
    id_: str,
    ship_date: str = "2026-06-01",
    method: str = "택배",
    address: str = "서울 강남구",
    status: str = "배송준비",
    cbm: float = 1.5,
) -> dict:
    return {
        "id": id_,
        "fields": {
            "fldQvmEwwzvQW95h9": ship_date,
            "flduzH5tS7orqGG3o": [method],
            "fldyJHUh9gN44Ggnh": [address],
            "fldOhibgxg6LIpRTi": status,
            "fldaP8D9AM8CHEZ2o": cbm,
        },
    }


# ─── C1: 신규 TO 감지 ─────────────────────────────────────────────────────────

class TestAdded:
    """Contract C1 — 신규 TO 감지."""

    def test_empty_snapshot_all_added(self):
        recs = [_rec("rec001"), _rec("rec002")]
        report, _ = detect({}, recs)
        assert set(report.added) == {"rec001", "rec002"}
        assert report.removed == []
        assert report.critical_modified == []

    def test_new_id_detected(self):
        snapshot = {"rec001": {"출하확정일": "2026-06-01", "배송방식": "택배",
                                "주소": "서울 강남구", "발송상태": "배송준비", "cbm": 1.5}}
        recs = [_rec("rec001"), _rec("rec002")]
        report, _ = detect(snapshot, recs)
        assert report.added == ["rec002"]
        assert report.removed == []

    def test_no_change_no_added(self):
        snapshot = {"rec001": {"출하확정일": "2026-06-01", "배송방식": "택배",
                                "주소": "서울 강남구", "발송상태": "배송준비", "cbm": 1.5}}
        recs = [_rec("rec001")]
        report, _ = detect(snapshot, recs)
        assert report.added == []


# ─── C2: 취소 / Critical 변경 감지 ───────────────────────────────────────────

class TestRemovedAndModified:
    """Contract C2 — 취소 및 Critical 필드 변경 감지."""

    def test_removed_when_id_disappears(self):
        snapshot = {
            "rec001": {"출하확정일": "2026-06-01", "배송방식": "택배",
                        "주소": "서울 강남구", "발송상태": "배송준비", "cbm": 1.5},
            "rec002": {"출하확정일": "2026-06-02", "배송방식": "퀵",
                        "주소": "경기 성남시", "발송상태": "배송준비", "cbm": 0.8},
        }
        recs = [_rec("rec001")]  # rec002 사라짐
        report, _ = detect(snapshot, recs)
        assert report.removed == ["rec002"]

    def test_critical_ship_date_change(self):
        snapshot = {"rec001": {"출하확정일": "2026-06-01", "배송방식": "택배",
                                "주소": "서울 강남구", "발송상태": "배송준비", "cbm": 1.5}}
        recs = [_rec("rec001", ship_date="2026-06-05")]  # 출하확정일 변경
        report, _ = detect(snapshot, recs)
        assert len(report.critical_modified) == 1
        assert report.critical_modified[0]["id"] == "rec001"
        assert report.critical_modified[0]["field"] == "출하확정일"

    def test_critical_method_change(self):
        snapshot = {"rec001": {"출하확정일": "2026-06-01", "배송방식": "택배",
                                "주소": "서울 강남구", "발송상태": "배송준비", "cbm": 1.5}}
        recs = [_rec("rec001", method="퀵")]
        report, _ = detect(snapshot, recs)
        assert any(m["field"] == "배송방식" for m in report.critical_modified)

    def test_critical_address_change(self):
        snapshot = {"rec001": {"출하확정일": "2026-06-01", "배송방식": "택배",
                                "주소": "서울 강남구", "발송상태": "배송준비", "cbm": 1.5}}
        recs = [_rec("rec001", address="부산 해운대구")]
        report, _ = detect(snapshot, recs)
        assert any(m["field"] == "주소" for m in report.critical_modified)

    def test_minor_cbm_change_not_critical(self):
        snapshot = {"rec001": {"출하확정일": "2026-06-01", "배송방식": "택배",
                                "주소": "서울 강남구", "발송상태": "배송준비", "cbm": 1.5}}
        recs = [_rec("rec001", cbm=2.0)]
        report, _ = detect(snapshot, recs)
        assert report.critical_modified == []
        assert len(report.minor_modified) == 1

    def test_new_snapshot_reflects_current(self):
        recs = [_rec("rec001", ship_date="2026-06-03")]
        _, new_snap = detect({}, recs)
        assert "rec001" in new_snap
        assert new_snap["rec001"]["출하확정일"] == "2026-06-03"
```

- [ ] **Step 2: 실패 확인**

```bash
python -m pytest tests/dispatch/test_change_detector.py -v
```

Expected: `ModuleNotFoundError: No module named 'harness.dispatch.change_detector'`

- [ ] **Step 3: `change_detector.py` 구현**

```python
# harness/dispatch/change_detector.py
"""Sub-Spec 4 Change Detection — 직전 스캔 대비 신규/취소/변경 감지.

snapshot 포맷: {record_id: {"출하확정일": str, "배송방식": str, "주소": str,
                             "발송상태": str, "cbm": float}}
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Airtable field IDs (Shipment table)
FLD_SHIP_DATE = "fldQvmEwwzvQW95h9"  # 출하확정일
FLD_METHOD = "flduzH5tS7orqGG3o"     # 배송 방식 (rollup)
FLD_ADDRESS = "fldyJHUh9gN44Ggnh"    # 수령인(주소) (rollup)
FLD_STATUS = "fldOhibgxg6LIpRTi"     # 발송상태_TMS
FLD_EST_CBM = "fldaP8D9AM8CHEZ2o"    # estimated_cbm

CRITICAL_FIELDS = ("출하확정일", "배송방식", "주소")


def _first(val) -> str:
    """multipleLookupValues 또는 plain 값 → 첫 번째 문자열."""
    if isinstance(val, list):
        return str(val[0]) if val else ""
    return str(val) if val is not None else ""


def _normalize(rec: dict) -> dict:
    """Airtable 원시 레코드 → 스냅샷용 normalized dict."""
    f = rec.get("fields", {})
    return {
        "출하확정일": f.get(FLD_SHIP_DATE, ""),
        "배송방식": _first(f.get(FLD_METHOD)),
        "주소": _first(f.get(FLD_ADDRESS)),
        "발송상태": f.get(FLD_STATUS, ""),
        "cbm": float(f.get(FLD_EST_CBM) or 0),
    }


@dataclass
class ChangeReport:
    added: list[str] = field(default_factory=list)             # record IDs
    removed: list[str] = field(default_factory=list)           # record IDs
    critical_modified: list[dict] = field(default_factory=list)  # [{id, field, old, new}]
    minor_modified: list[dict] = field(default_factory=list)     # [{id, field, old, new}]


def detect(
    snapshot: dict[str, dict],
    current: list[dict],
) -> tuple[ChangeReport, dict[str, dict]]:
    """스냅샷 vs 현재 레코드 비교 → (ChangeReport, new_snapshot).

    new_snapshot은 caller가 artifact 또는 파일로 저장.
    """
    report = ChangeReport()
    new_snapshot: dict[str, dict] = {}

    current_map = {rec["id"]: rec for rec in current}

    # added: 현재에 있지만 snapshot에 없는 ID
    for rec_id, rec in current_map.items():
        norm = _normalize(rec)
        new_snapshot[rec_id] = norm
        if rec_id not in snapshot:
            report.added.append(rec_id)
        else:
            prev = snapshot[rec_id]
            for field_name in CRITICAL_FIELDS:
                if norm[field_name] != prev.get(field_name, ""):
                    report.critical_modified.append(
                        {"id": rec_id, "field": field_name,
                         "old": prev.get(field_name, ""), "new": norm[field_name]}
                    )
            if norm["cbm"] != prev.get("cbm", 0):
                report.minor_modified.append(
                    {"id": rec_id, "field": "cbm",
                     "old": prev.get("cbm", 0), "new": norm["cbm"]}
                )

    # removed: snapshot에 있지만 현재에 없는 ID
    for rec_id in snapshot:
        if rec_id not in current_map:
            report.removed.append(rec_id)

    return report, new_snapshot
```

- [ ] **Step 4: 통과 확인**

```bash
python -m pytest tests/dispatch/test_change_detector.py -v
```

Expected: `8 passed`

- [ ] **Step 5: 전체 회귀 확인**

```bash
python -m pytest tests/dispatch/ -q
```

Expected: `150 passed`

- [ ] **Step 6: 커밋**

```bash
git add harness/dispatch/change_detector.py tests/dispatch/test_change_detector.py
git commit -m "feat(dispatch): change_detector 신규/취소/Critical 변경 감지 (C1~C2)"
```

---

## Task 3: `otif_estimator.py` TDD

**Files:**
- Create: `harness/dispatch/otif_estimator.py`
- Create: `tests/dispatch/test_otif_estimator.py`

### 배경

`estimate_all(raw_records)` — 각 shipment에 대해 가정 OTIF를 계산하고 JSONL에 append한다.

| 조건 | assumed_pod | on_time |
|---|---|---|
| POD_확인일시 있음 | None | None (실제 OTIF 테이블이 처리) |
| 약속납기일 or 출하확정일 None | None | None (측정불가) |
| 배송방식 = 퀵/자체기사/바로고 | 출하확정일 당일 | pod ≤ 약속납기일 |
| 배송방식 = 택배/로젠 | add_logen_days(출하확정일, 3) | pod ≤ 약속납기일 |
| 배송방식 None or 기타 | None | None (측정불가) |

**Airtable field IDs 추가:**
- `fldyYIfBhhu7sEX1P` — 약속납기일 (date)
- `fldNPH5xLdYevknfZ` — POD_확인일시 (dateTime)
- `fldQvmEwwzvQW95h9` — 출하확정일 (date, 이미 fetch됨)
- `flduzH5tS7orqGG3o` — 배송 방식 (rollup, 이미 fetch됨)

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# tests/dispatch/test_otif_estimator.py
"""Tests for otif_estimator — Contract C4 (OTIF 4케이스) / C5 (JSONL append)."""
from __future__ import annotations

import json
import tempfile
from datetime import date
from pathlib import Path

import pytest

from harness.dispatch.otif_estimator import OtifResult, estimate_all, otif_summary_by_wave


# ─── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _rec(
    id_: str,
    ship_date: str | None = "2026-06-02",   # 월요일
    promise_date: str | None = "2026-06-05",
    method: str | None = "택배",
    pod_confirmed: str | None = None,
) -> dict:
    fields: dict = {}
    if ship_date:
        fields["fldQvmEwwzvQW95h9"] = ship_date
    if promise_date:
        fields["fldyYIfBhhu7sEX1P"] = promise_date
    if method:
        fields["flduzH5tS7orqGG3o"] = [method]
    if pod_confirmed:
        fields["fldNPH5xLdYevknfZ"] = pod_confirmed
    return {"id": id_, "fields": fields}


# ─── C4: OTIF 4케이스 ─────────────────────────────────────────────────────────

class TestOtifCases:
    """Contract C4 — 배송방식별 가정 OTIF."""

    def test_quick_on_time(self, tmp_path):
        # 퀵: assumed_pod = 출하확정일 당일
        # 출하 06-02 ≤ 약속 06-05 → on_time=True
        recs = [_rec("rec001", ship_date="2026-06-02", promise_date="2026-06-05", method="퀵")]
        results = estimate_all(recs, log_path=tmp_path / "otif.jsonl")
        assert len(results) == 1
        r = results[0]
        assert r.on_time is True
        assert r.assumed_pod == date(2026, 6, 2)
        assert r.method == "당일"

    def test_logen_on_time(self, tmp_path):
        # 택배: 월(06-02) +3 일요일skip → 목(06-05) ≤ 약속(06-05) → True
        # 06-02(월) → 06-03(화+1) → 06-04(수+2) → 06-05(목+3)
        recs = [_rec("rec001", ship_date="2026-06-02", promise_date="2026-06-05", method="택배")]
        results = estimate_all(recs, log_path=tmp_path / "otif.jsonl")
        r = results[0]
        assert r.on_time is True
        assert r.assumed_pod == date(2026, 6, 5)
        assert r.method == "로젠+3일"

    def test_logen_at_risk(self, tmp_path):
        # 택배: 월(06-02) +3 → 목(06-05) > 약속(06-04) → False
        recs = [_rec("rec001", ship_date="2026-06-02", promise_date="2026-06-04", method="택배")]
        results = estimate_all(recs, log_path=tmp_path / "otif.jsonl")
        r = results[0]
        assert r.on_time is False

    def test_skip_if_pod_confirmed(self, tmp_path):
        # POD 확인 완료 → None (실제 OTIF 테이블이 처리)
        recs = [_rec("rec001", pod_confirmed="2026-06-03T14:00:00.000Z")]
        results = estimate_all(recs, log_path=tmp_path / "otif.jsonl")
        r = results[0]
        assert r.on_time is None
        assert r.method == "POD확인완료"

    def test_null_promise_date(self, tmp_path):
        recs = [_rec("rec001", promise_date=None)]
        results = estimate_all(recs, log_path=tmp_path / "otif.jsonl")
        r = results[0]
        assert r.on_time is None
        assert r.method == "측정불가"

    def test_null_method(self, tmp_path):
        recs = [_rec("rec001", method=None)]
        results = estimate_all(recs, log_path=tmp_path / "otif.jsonl")
        r = results[0]
        assert r.on_time is None
        assert r.method == "측정불가"


# ─── C5: JSONL append-only ────────────────────────────────────────────────────

class TestJsonlAppend:
    """Contract C5 — JSONL append-only, 2회 호출 시 2배 줄수."""

    def test_appends_one_line_per_shipment(self, tmp_path):
        log = tmp_path / "otif.jsonl"
        recs = [_rec("rec001"), _rec("rec002")]
        estimate_all(recs, log_path=log)
        lines = log.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2

    def test_second_call_appends(self, tmp_path):
        log = tmp_path / "otif.jsonl"
        recs = [_rec("rec001")]
        estimate_all(recs, log_path=log)
        estimate_all(recs, log_path=log)
        lines = log.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2  # 두 번 호출 → 2줄 (중복 없음, 각 run 1줄씩)

    def test_jsonl_valid_json(self, tmp_path):
        log = tmp_path / "otif.jsonl"
        recs = [_rec("rec001", method="퀵")]
        estimate_all(recs, log_path=log)
        for line in log.read_text(encoding="utf-8").strip().splitlines():
            obj = json.loads(line)
            assert "ts" in obj
            assert "record_id" in obj
            assert "method" in obj


# ─── otif_summary_by_wave ─────────────────────────────────────────────────────

class TestOtifSummary:
    def test_summary_groups_by_wave(self):
        from harness.dispatch.wave_assigner import Shipment, WavePlan
        results = [
            OtifResult(record_id="r1", on_time=True, assumed_pod=date(2026,6,5), method="당일"),
            OtifResult(record_id="r2", on_time=False, assumed_pod=date(2026,6,6), method="로젠+3일"),
            OtifResult(record_id="r3", on_time=None, assumed_pod=None, method="측정불가"),
        ]
        from dataclasses import dataclass, field as dc_field
        w1 = WavePlan("W1")
        w1.shipments = [Shipment(id="r1", project_code="P1", slot="오전", region="tier1_seoul", cbm=1.0)]
        w2 = WavePlan("W2")
        w2.shipments = [Shipment(id="r2", project_code="P2", slot="오전", region="tier1_seoul", cbm=1.0)]
        manual = WavePlan("수동")
        manual.shipments = [Shipment(id="r3", project_code="P3", slot=None, region="tier1_seoul", cbm=0.5)]
        plans = {"W1": w1, "W2": w2, "수동": manual}

        summary = otif_summary_by_wave(results, plans)
        assert summary["W1"] == {"total": 1, "on_time": 1, "at_risk": 0}
        assert summary["W2"] == {"total": 1, "on_time": 0, "at_risk": 1}
        # r3 on_time=None → not in summary
        assert "수동" not in summary
```

- [ ] **Step 2: 실패 확인**

```bash
python -m pytest tests/dispatch/test_otif_estimator.py -v
```

Expected: `ModuleNotFoundError: No module named 'harness.dispatch.otif_estimator'`

- [ ] **Step 3: `otif_estimator.py` 구현**

```python
# harness/dispatch/otif_estimator.py
"""Sub-Spec 4 가정 OTIF 추정 — 배송방식별 가정 POD + 납기 준수 예측.

실제 OTIF는 Airtable OTIF 테이블(formula)이 처리. 본 모듈은 미출하 shipment의
예측값만 계산 → JSONL 로그 (P5 Scorecard 집계용).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from harness.dispatch.scheduling import add_logen_days

# Airtable field IDs (Shipment table)
FLD_SHIP_DATE = "fldQvmEwwzvQW95h9"   # 출하확정일
FLD_PROMISE = "fldyYIfBhhu7sEX1P"      # 약속납기일
FLD_METHOD = "flduzH5tS7orqGG3o"       # 배송 방식 (rollup)
FLD_POD = "fldNPH5xLdYevknfZ"          # POD_확인일시

DEFAULT_LOG_PATH = Path("_AutoResearch/SCM/outputs/audit_log/assumed_otif.jsonl")

SAME_DAY_METHODS = {"퀵", "자체기사", "바로고"}
LOGEN_METHODS = {"택배", "로젠"}


def _first(val) -> str:
    if isinstance(val, list):
        return str(val[0]) if val else ""
    return str(val) if val is not None else ""


@dataclass
class OtifResult:
    record_id: str
    on_time: Optional[bool]
    assumed_pod: Optional[date]
    method: str  # "당일" | "로젠+3일" | "측정불가" | "POD확인완료"


def _estimate_one(rec: dict) -> OtifResult:
    record_id = rec["id"]
    f = rec.get("fields", {})

    # POD 이미 확인됨 → 실제 OTIF 테이블이 처리
    if f.get(FLD_POD):
        return OtifResult(record_id=record_id, on_time=None,
                          assumed_pod=None, method="POD확인완료")

    ship_date_raw = f.get(FLD_SHIP_DATE, "")
    promise_raw = f.get(FLD_PROMISE, "")
    method_raw = _first(f.get(FLD_METHOD))

    if not ship_date_raw or not promise_raw or not method_raw:
        return OtifResult(record_id=record_id, on_time=None,
                          assumed_pod=None, method="측정불가")

    ship_date = date.fromisoformat(ship_date_raw[:10])
    promise_date = date.fromisoformat(promise_raw[:10])

    if method_raw in SAME_DAY_METHODS:
        assumed_pod = ship_date
        method = "당일"
    elif method_raw in LOGEN_METHODS:
        assumed_pod = add_logen_days(ship_date, 3)
        method = "로젠+3일"
    else:
        return OtifResult(record_id=record_id, on_time=None,
                          assumed_pod=None, method="측정불가")

    return OtifResult(
        record_id=record_id,
        on_time=assumed_pod <= promise_date,
        assumed_pod=assumed_pod,
        method=method,
    )


def estimate_all(
    raw_records: list[dict],
    log_path: Path | None = None,
) -> list[OtifResult]:
    """각 shipment 가정 OTIF 계산 → JSONL append + list 반환."""
    if log_path is None:
        log_path = DEFAULT_LOG_PATH
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    results = [_estimate_one(rec) for rec in raw_records]
    ts = datetime.now().isoformat()

    with open(log_path, "a", encoding="utf-8") as f:
        for r in results:
            entry = {
                "ts": ts,
                "record_id": r.record_id,
                "on_time": r.on_time,
                "assumed_pod": r.assumed_pod.isoformat() if r.assumed_pod else None,
                "method": r.method,
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return results


def otif_summary_by_wave(
    results: list[OtifResult],
    plans: dict,
) -> dict[str, dict]:
    """record_id → wave 역매핑 후 wave별 on_time / at_risk 집계.

    on_time=None (측정불가/POD확인완료)은 집계에서 제외.
    """
    id_to_wave: dict[str, str] = {}
    for wave_id, plan in plans.items():
        for s in plan.shipments:
            id_to_wave[s.id] = wave_id

    summary: dict[str, dict] = {}
    for r in results:
        if r.on_time is None:
            continue
        wave = id_to_wave.get(r.record_id, "수동")
        if wave not in summary:
            summary[wave] = {"total": 0, "on_time": 0, "at_risk": 0}
        summary[wave]["total"] += 1
        if r.on_time:
            summary[wave]["on_time"] += 1
        else:
            summary[wave]["at_risk"] += 1

    return summary
```

- [ ] **Step 4: 통과 확인**

```bash
python -m pytest tests/dispatch/test_otif_estimator.py -v
```

Expected: `10 passed`

- [ ] **Step 5: 전체 회귀 확인**

```bash
python -m pytest tests/dispatch/ -q
```

Expected: `160 passed`

- [ ] **Step 6: 커밋**

```bash
git add harness/dispatch/otif_estimator.py tests/dispatch/test_otif_estimator.py
git commit -m "feat(dispatch): otif_estimator 가정 OTIF + JSONL 로그 (C4~C5)"
```

---

## Task 4: `wave_recommender.py` orchestration 통합

**Files:**
- Modify: `harness/dispatch/wave_recommender.py`

### 변경 내용 요약

1. import 추가: `change_detector`, `otif_estimator`
2. `SNAPSHOT_PATH` 상수 + `_load_snapshot()` / `_save_snapshot()` 헬퍼 2개 추가
3. `_format_digest()` 서명 확장 (optional 인자 2개)
4. `send_or_queue_digest()` / `save_pending_digest()` 서명 확장
5. `main()` 에 change detection + OTIF steps 추가

- [ ] **Step 1: import 추가**

`harness/dispatch/wave_recommender.py` 상단 import 블록(기존 import 아래)에 추가:

```python
from harness.dispatch.change_detector import ChangeReport, detect
from harness.dispatch.otif_estimator import OtifResult, estimate_all, otif_summary_by_wave
```

- [ ] **Step 2: snapshot 헬퍼 추가**

`DRY_RUN = ...` 상수 아래에 추가:

```python
SNAPSHOT_PATH = os.environ.get("SNAPSHOT_PATH", "")


def _load_snapshot() -> dict:
    if not SNAPSHOT_PATH or not os.path.exists(SNAPSHOT_PATH):
        return {}
    with open(SNAPSHOT_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_snapshot(snapshot: dict) -> None:
    if not SNAPSHOT_PATH:
        return
    import pathlib
    pathlib.Path(SNAPSHOT_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False)
```

- [ ] **Step 3: `_format_digest()` 서명 확장**

기존 `def _format_digest(plans, diff, today_iso):` 를 다음으로 교체:

```python
def _format_digest(
    plans: dict[str, WavePlan],
    diff: list[dict],
    today_iso: str,
    change_report: "ChangeReport | None" = None,
    otif_summary: "dict | None" = None,
) -> str:
    util = compute_utilization(plans)
    lines = [f"*Wave 추천 엔진 다이제스트 — {today_iso}*"]

    # 변경 섹션 (변경이 있을 때만)
    if change_report and (change_report.added or change_report.removed or change_report.critical_modified):
        parts = []
        if change_report.added:
            parts.append(f"🆕 신규 {len(change_report.added)}건")
        if change_report.removed:
            parts.append(f"🚫 완료/취소 {len(change_report.removed)}건")
        if change_report.critical_modified:
            parts.append(f"⚠️ 변경 {len(change_report.critical_modified)}건")
        lines.append("  " + " | ".join(parts))

    # Wave 요약 + OTIF overlay
    for wid in ("W1", "W2", "W3"):
        plan = plans[wid]
        u = util.get(wid, 0.0)
        line = f"  {wid}: {plan.count}건 / {plan.total_cbm:.2f} CBM ({u:.0%})"
        if otif_summary and wid in otif_summary:
            s = otif_summary[wid]
            line += f" — 납기 {s['on_time']}/{s['total']}건 ✅"
            if s["at_risk"]:
                line += f" / {s['at_risk']}건 ⚠️"
        lines.append(line)

    for wid in ("spillover_고고엑스", "spillover_로젠", "수동"):
        cnt = plans[wid].count
        if cnt:
            lines.append(f"  {wid}: {cnt}건")
    lines.append(f"  총 추천: {len(diff)}건")
    return "\n".join(lines)
```

- [ ] **Step 4: `save_pending_digest()` / `send_or_queue_digest()` 서명 확장**

기존 두 함수를 다음으로 교체:

```python
def save_pending_digest(
    plans: dict[str, WavePlan],
    diff: list[dict],
    today_iso: str,
    change_report=None,
    otif_summary=None,
) -> None:
    import pathlib
    pathlib.Path(PENDING_DIGEST_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(PENDING_DIGEST_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {"date": today_iso,
             "text": _format_digest(plans, diff, today_iso, change_report, otif_summary)},
            f,
        )


def send_or_queue_digest(
    plans: dict[str, WavePlan],
    diff: list[dict],
    today_iso: str,
    change_report=None,
    otif_summary=None,
) -> None:
    now = datetime.now()
    if is_quiet_hour(now):
        save_pending_digest(plans, diff, today_iso, change_report, otif_summary)
        print(f"[INFO] quiet hours — digest queued for next cycle")
        return

    import pathlib
    pending = pathlib.Path(PENDING_DIGEST_PATH)
    if pending.exists():
        with open(pending, encoding="utf-8") as f:
            old = json.load(f)
        _slack_post(old.get("text", ""))
        pending.unlink()

    _slack_post(_format_digest(plans, diff, today_iso, change_report, otif_summary))
```

- [ ] **Step 5: `main()` 에 Change Detection + OTIF steps 추가**

기존 `main()` 함수를 다음으로 교체:

```python
def main() -> None:
    today = datetime.now()
    today_iso = today.isoformat()[:10]
    now_iso = today.isoformat()

    print(f"[wave_recommender] {today_iso} {'DRY_RUN' if DRY_RUN else 'LIVE'}")

    # Step 1: 스냅샷 로드
    snapshot = _load_snapshot()
    print(f"  snapshot loaded: {len(snapshot)} records")

    # Load partner autonomy map
    partners = load_partners()
    partner_autonomy = {
        p.get("배송파트너", ""): p.get("autonomy_level", "unknown")
        for p in partners
        if p.get("배송파트너")
    }

    # Stage 0: fetch auto targets
    raw_records = fetch_auto_targets(today_iso)
    print(f"  auto_targets fetched: {len(raw_records)}")

    # Step 2: Change Detection
    change_report, new_snapshot = detect(snapshot, raw_records)
    print(f"  changes: +{len(change_report.added)} ~{len(change_report.critical_modified)} -{len(change_report.removed)}")

    # Stage A: slot + region classification
    shipments: list[Shipment] = []
    for rec in raw_records:
        s = _build_shipment(rec)
        if s:
            shipments.append(s)

    print(f"  shipments built: {len(shipments)}")

    # Stage B+C+D: wave assignment
    plans = assign_waves(shipments, partner_autonomy, today_iso)

    # Summary
    util = compute_utilization(plans)
    for wid in ("W1", "W2", "W3"):
        plan = plans[wid]
        print(f"  {wid}: {plan.count}건 / {plan.total_cbm:.2f} CBM ({util.get(wid, 0):.0%})")
    for wid in ("spillover_고고엑스", "spillover_로젠", "locked-in", "수동"):
        cnt = plans[wid].count
        if cnt:
            print(f"  {wid}: {cnt}건")

    automation_count = sum(plans[w].count for w in ("W1", "W2", "W3"))
    total_count = len(shipments)
    print(f"  automation: {automation_count}/{total_count} ({automation_count/total_count:.0%})" if total_count else "  no shipments")

    # Stage: PATCH + Slack
    shipment_map = {s.id: s for s in shipments}
    diff = patch_airtable(plans, shipment_map, now_iso)

    # Step 3: 가정 OTIF 추정
    otif_results = estimate_all(raw_records)
    otif_summary = otif_summary_by_wave(otif_results, plans)

    # Step 4: Slack 다이제스트 (변경 또는 wave 변동 시)
    has_changes = (
        change_report.added
        or change_report.removed
        or change_report.critical_modified
    )
    if diff or has_changes:
        send_or_queue_digest(plans, diff, today_iso, change_report, otif_summary)
    else:
        print("  no changes to report")

    # Step 5: 스냅샷 저장
    _save_snapshot(new_snapshot)
    print(f"  snapshot saved: {len(new_snapshot)} records")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: import 오류 없는지 확인**

```bash
python -c "from harness.dispatch.wave_recommender import main; print('OK')"
```

Expected: `OK`

- [ ] **Step 7: 전체 pytest 통과 확인**

```bash
python -m pytest tests/dispatch/ -q
```

Expected: `160 passed` (신규 테스트 없음, 기존 회귀 확인)

- [ ] **Step 8: DRY_RUN 연기 확인**

```bash
DRY_RUN=true python -m harness.dispatch.wave_recommender
```

Expected: 출력에 `[wave_recommender] ... DRY_RUN`, `snapshot loaded: 0 records` 포함. 오류 없음.

- [ ] **Step 9: 커밋**

```bash
git add harness/dispatch/wave_recommender.py
git commit -m "feat(dispatch): wave_recommender orchestration — change detection + OTIF 통합"
```

---

## Task 5: GitHub Actions artifact 스텝 추가

**Files:**
- Modify: `.github/workflows/wave_recommender.yml`

- [ ] **Step 1: workflow 파일 수정**

`.github/workflows/wave_recommender.yml`의 `jobs.run.steps` 에서 `actions/checkout@v4` 다음에 artifact 다운로드 스텝을 추가하고, 마지막에 업로드 스텝을 추가한다.

기존:
```yaml
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run wave recommender
        run: python -m harness.dispatch.wave_recommender
        env:
          AIRTABLE_PAT: ${{ secrets.AIRTABLE_PAT }}
          SLACK_BOT_TOKEN: ${{ secrets.SLACK_BOT_TOKEN }}
          SLACK_DM_USER_ID: ${{ secrets.SLACK_DM_USER_ID }}
          DRY_RUN: ${{ github.event.inputs.dry_run || 'false' }}
```

교체:
```yaml
    steps:
      - uses: actions/checkout@v4

      - name: Download snapshot
        uses: actions/download-artifact@v4
        with:
          name: dispatch-snapshot
          path: /tmp/snapshot
        continue-on-error: true  # 첫 실행 시 artifact 없어도 OK

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run wave recommender
        run: python -m harness.dispatch.wave_recommender
        env:
          AIRTABLE_PAT: ${{ secrets.AIRTABLE_PAT }}
          SLACK_BOT_TOKEN: ${{ secrets.SLACK_BOT_TOKEN }}
          SLACK_DM_USER_ID: ${{ secrets.SLACK_DM_USER_ID }}
          DRY_RUN: ${{ github.event.inputs.dry_run || 'false' }}
          SNAPSHOT_PATH: /tmp/snapshot/dispatch_snapshot.json

      - name: Upload snapshot
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: dispatch-snapshot
          path: /tmp/snapshot/dispatch_snapshot.json
          retention-days: 90
          overwrite: true
```

- [ ] **Step 2: YAML lint 확인**

```bash
python -c "
import yaml
with open('.github/workflows/wave_recommender.yml') as f:
    data = yaml.safe_load(f)
steps = data['jobs']['run']['steps']
names = [s.get('name', s.get('uses', '?')) for s in steps]
print('Steps:', names)
assert any('Download snapshot' in n for n in names), 'Download step missing'
assert any('Upload snapshot' in n for n in names), 'Upload step missing'
assert any('SNAPSHOT_PATH' in str(s) for s in steps), 'SNAPSHOT_PATH env missing'
print('OK')
"
```

Expected: `OK`

- [ ] **Step 3: 커밋**

```bash
git add .github/workflows/wave_recommender.yml
git commit -m "ci: wave_recommender workflow — GitHub Actions artifact 스냅샷 (90일 TTL)"
```

---

## Task 6: Validation Contract 스크립트 + feature_list 갱신

**Files:**
- Create: `scripts/verification/verify_subspec4_contract.py`
- Modify: `.claude/feature_list.json`
- Modify: `~/.claude/plans/lane-strategy-v3-phase-status.md`

- [ ] **Step 1: Contract 검증 스크립트 작성**

```python
# scripts/verification/verify_subspec4_contract.py
"""Sub-Spec 4 Validation Contract C1~C5 자동 검증.

C1~C5: 단위 테스트로 검증 (pytest).
사용법: python scripts/verification/verify_subspec4_contract.py
"""
from __future__ import annotations

import subprocess
import sys


def run_contract(label: str, cmd: list[str]) -> bool:
    result = subprocess.run(cmd, capture_output=True, text=True)
    passed = result.returncode == 0
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}  {label}")
    if not passed:
        print(result.stdout[-500:])
        print(result.stderr[-200:])
    return passed


def main() -> int:
    print("Sub-Spec 4 Validation Contract")
    print("=" * 40)
    results = [
        run_contract(
            "C1: 신규 TO 감지 (change_detector added)",
            ["python", "-m", "pytest", "tests/dispatch/test_change_detector.py::TestAdded", "-q"],
        ),
        run_contract(
            "C2: 취소/Critical 변경 감지 (change_detector modified/removed)",
            ["python", "-m", "pytest", "tests/dispatch/test_change_detector.py::TestRemovedAndModified", "-q"],
        ),
        run_contract(
            "C3: add_logen_days 일요일 skip",
            ["python", "-m", "pytest", "tests/dispatch/test_logen_days.py", "-q"],
        ),
        run_contract(
            "C4: OTIF 4케이스 (퀵/택배/NULL납기/POD확인완료)",
            ["python", "-m", "pytest", "tests/dispatch/test_otif_estimator.py::TestOtifCases", "-q"],
        ),
        run_contract(
            "C5: JSONL append-only (2회 호출 → 2줄)",
            ["python", "-m", "pytest", "tests/dispatch/test_otif_estimator.py::TestJsonlAppend", "-q"],
        ),
    ]
    passed = sum(results)
    total = len(results)
    print("=" * 40)
    print(f"Contract: {passed}/{total} PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Contract 스크립트 실행**

```bash
python scripts/verification/verify_subspec4_contract.py
```

Expected:
```
Sub-Spec 4 Validation Contract
========================================
✅ PASS  C1: 신규 TO 감지 (change_detector added)
✅ PASS  C2: 취소/Critical 변경 감지 (change_detector modified/removed)
✅ PASS  C3: add_logen_days 일요일 skip
✅ PASS  C4: OTIF 4케이스 (퀵/택배/NULL납기/POD확인완료)
✅ PASS  C5: JSONL append-only (2회 호출 → 2줄)
========================================
Contract: 5/5 PASS
```

- [ ] **Step 3: feature_list.json 갱신**

`.claude/feature_list.json` 에서 Sub-Spec 4 관련 항목 status를 `"done"` 으로 변경하고, 아래 항목을 `"done"` 항목 섹션에 추가:

```json
{
  "id": "SCM-LANE-SUBSPEC-4",
  "title": "Sub-Spec 4 Change Detection + 가정 OTIF",
  "status": "done",
  "completed_at": "2026-MM-DD"
}
```

- [ ] **Step 4: master tracker 갱신**

`~/.claude/plans/lane-strategy-v3-phase-status.md` 에서:

```markdown
| P4 | Sub-Spec 4 Change Detection + 가정 OTIF | 🔄 IN_PROGRESS | lane-strategy-v3-p4-handoff.md | — |
```

→

```markdown
| P4 | Sub-Spec 4 Change Detection + 가정 OTIF | ✅ DONE | lane-strategy-v3-p4-handoff.md | YYYY-MM-DD |
| P4.5 | Sub-Spec 4 implementation (Task 0~6) | ⏸ READY_TO_START | lane-strategy-v3-p4.5-handoff.md | — |
```

- [ ] **Step 5: 최종 pytest 전체 통과 확인**

```bash
python -m pytest tests/dispatch/ -q
```

Expected: `160 passed` (또는 그 이상, 0 failures)

- [ ] **Step 6: 최종 커밋**

```bash
git add scripts/verification/verify_subspec4_contract.py .claude/feature_list.json
git commit -m "chain(v3): P4 Sub-Spec 4 Change Detection + 가정 OTIF brainstorm + plan 마감"
```

---

## 완료 기준 요약

| 항목 | 기준 |
|---|---|
| pytest | 160+ PASS, 0 FAIL |
| Contract | 5/5 PASS (`verify_subspec4_contract.py`) |
| Import 오류 | `python -c "from harness.dispatch.wave_recommender import main"` → OK |
| YAML lint | `wave_recommender.yml` artifact 스텝 2개 존재 확인 |
| 파일 수 | 신규 5개, 수정 3개 |
| Airtable 변경 | 0건 |
