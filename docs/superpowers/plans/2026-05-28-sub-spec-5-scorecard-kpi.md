# Sub-Spec 5 Scorecard + KPI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 9개 carrier 대상 월간 4축 Scorecard + KPI 3종을 자동 산출해 Slack DM 상세형으로 발송하는 파이프라인 구축.

**Architecture:** `calc.py`(순수 점수 함수 + Airtable 조회) + `kpi_tracker.py`(KPI 계산 + JSONL 히스토리) → `run_monthly.py`(오케스트레이터 + Slack 포맷) → GitHub Actions 월간 cron. 점수 함수는 순수 함수로 분리해 Airtable mock 없이 단위 테스트 가능.

**Tech Stack:** Python 3.11+, requests, python-dotenv, pytest, GitHub Actions. Airtable REST API (TMS base `app4x70a8mOrIKsMf`). `harness/_core/notifier.py` Slack 발송.

**Design doc:** `docs/superpowers/specs/2026-05-28-sub-spec-5-scorecard-kpi-design.md`

---

## File Map

| 파일 | 역할 |
|---|---|
| `harness/scorecard/__init__.py` | CarrierScore·MonthlySnapshot 데이터클래스 |
| `harness/scorecard/calc.py` | 순수 점수 함수 + Airtable fetch helpers + 전체 집계 |
| `harness/scorecard/kpi_tracker.py` | KPI 3종 계산 + JSONL 히스토리 read/write |
| `scripts/scorecard/run_monthly.py` | 오케스트레이터 + Slack DM 포맷터 |
| `scripts/scorecard/scorecard_history.jsonl` | 월간 스냅샷 누적 (INSERT ONLY, 첫 실행 시 auto-create) |
| `tests/scorecard/__init__.py` | (빈 파일) |
| `tests/scorecard/test_calc.py` | score_* 순수 함수 단위 테스트 |
| `tests/scorecard/test_kpi_tracker.py` | KPI 계산 + JSONL 2-run 시나리오 |
| `.github/workflows/scorecard.yml` | 매월 1일 00:01 KST cron |

**Airtable Table IDs (TMS base):**
- Shipment: `tbllg1JoHclGYer7m`
- 배송파트너: `tblI4ZXrte7WyhXyd`
- OTIF: `tbl4WfEuGLDlqCTQH`
- 배송클레임: `tblIZ9kco1QDpUz0u`
- 운임단가: `tblQA1ev9fjbowUoP`

---

## Task 0: Pre-flight

**Files:** (no new files)

- [ ] **Step 1: Create directories**

```bash
mkdir -p harness/scorecard tests/scorecard scripts/scorecard
```

- [ ] **Step 2: Confirm existing patterns compile**

```bash
cd c:/Users/yjisu/Desktop/SCM_WORK
python -c "from harness.dispatch.otif_estimator import OtifResult; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit pre-flight**

```bash
git add harness/scorecard tests/scorecard scripts/scorecard
git commit -m "chore(scorecard): create Sub-Spec 5 directory structure"
```

---

## Task 1: Dataclasses — `harness/scorecard/__init__.py`

**Files:**
- Create: `harness/scorecard/__init__.py`
- Create: `tests/scorecard/__init__.py`

- [ ] **Step 1: Write `harness/scorecard/__init__.py`**

```python
"""Sub-Spec 5 Scorecard + KPI — 월간 carrier 평가 파이프라인."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CarrierScore:
    carrier_id: str          # Airtable record ID
    carrier_name: str        # 배송파트너.배송파트너 field
    cost: Optional[float]    # 0-100, None = 운임단가 없음(N/A)
    reliability: Optional[float]  # 0-100, None = OTIF 레코드 없음
    capacity: float          # 0-100
    damage: float            # 0-100
    total: float             # weighted aggregate (N/A 축 재정규화)
    shipment_count: int      # 해당 월 처리 건수


@dataclass
class KpiSnapshot:
    K_LC_1: float            # 자체 기사 활용도 (0-1)
    K_LC_2: float            # Wave 자동화 비중 (0-1)
    K_LC_3: float            # 외주 spillover 비용 (₩ 원단위)
    K_LC_1_baseline: Optional[float] = None  # 첫 측정값
    K_LC_3_baseline: Optional[float] = None  # 첫 측정값


@dataclass
class MonthlySnapshot:
    month: str               # "YYYY-MM"
    generated_at: str        # ISO 8601 KST
    carriers: dict[str, dict] = field(default_factory=dict)  # name → score dict
    kpi: dict = field(default_factory=dict)
```

- [ ] **Step 2: Create empty test init**

```bash
type nul > tests/scorecard/__init__.py
```

- [ ] **Step 3: Verify import**

```bash
python -c "from harness.scorecard import CarrierScore, KpiSnapshot; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add harness/scorecard/__init__.py tests/scorecard/__init__.py
git commit -m "feat(scorecard): CarrierScore + KpiSnapshot dataclasses"
```

---

## Task 2: 순수 점수 함수 — TDD (failing tests → implementation)

**Files:**
- Create: `tests/scorecard/test_calc.py`
- Create: `harness/scorecard/calc.py`

- [ ] **Step 1: Write failing tests**

Create `tests/scorecard/test_calc.py`:

```python
"""Unit tests for scorecard score functions — pure functions, no Airtable."""
import pytest
from harness.scorecard.calc import (
    score_cost,
    score_reliability,
    score_capacity,
    score_damage,
    aggregate_score,
    working_days_in_month,
)


# ── score_cost ─────────────────────────────────────────────────────────────

def test_score_cost_on_target():
    """actual == target → 100점."""
    assert score_cost(total_transport_cost=1000.0, total_cbm=10.0, target_rate=100.0) == pytest.approx(100.0)


def test_score_cost_below_target():
    """actual < target (우리가 싸게 쓴 경우) → 100 cap."""
    assert score_cost(1000.0, 10.0, target_rate=200.0) == pytest.approx(100.0)


def test_score_cost_above_target():
    """actual > target (초과 지출) → 비례 감점."""
    # actual_rate=100, target=80 → 80/100*100 = 80
    assert score_cost(1000.0, 10.0, target_rate=80.0) == pytest.approx(80.0)


def test_score_cost_no_target():
    """target_rate None → None (N/A)."""
    assert score_cost(1000.0, 10.0, target_rate=None) is None


def test_score_cost_zero_cbm():
    """CBM 0 → None (분모 0 방어)."""
    assert score_cost(1000.0, 0.0, target_rate=100.0) is None


# ── score_reliability ───────────────────────────────────────────────────────

def test_score_reliability_perfect():
    assert score_reliability(on_time_count=10, total_count=10) == pytest.approx(100.0)


def test_score_reliability_half():
    assert score_reliability(5, 10) == pytest.approx(50.0)


def test_score_reliability_zero_records():
    """레코드 없음 → None (otif_estimator 가정값 사용 신호)."""
    assert score_reliability(0, 0) is None


# ── score_capacity ──────────────────────────────────────────────────────────

def test_score_capacity_self_employed_full():
    """자체 기사: max_daily=3, 20영업일, 실제=60 → 100점."""
    assert score_capacity(shipments=60, max_daily=3, working_days=20,
                          is_self_employed=True, prev_month_count=None) == pytest.approx(100.0)


def test_score_capacity_self_employed_half():
    """자체 기사: max_daily=3, 20영업일, 실제=30 → 50점."""
    assert score_capacity(30, 3, 20, True, None) == pytest.approx(50.0)


def test_score_capacity_external_first_month():
    """외주 첫 달 → 50점 고정."""
    assert score_capacity(10, 0, 20, False, prev_month_count=None) == pytest.approx(50.0)


def test_score_capacity_external_growth():
    """외주: 전월 20건, 이번달 30건 → min(100, 30/20*50) = 75."""
    assert score_capacity(30, 0, 20, False, prev_month_count=20) == pytest.approx(75.0)


def test_score_capacity_external_capped():
    """외주: 전월 10건, 이번달 100건 → min(100, 500) = 100."""
    assert score_capacity(100, 0, 20, False, prev_month_count=10) == pytest.approx(100.0)


# ── score_damage ────────────────────────────────────────────────────────────

def test_score_damage_no_claims():
    assert score_damage(claim_count=0, shipment_count=50) == pytest.approx(100.0)


def test_score_damage_one_percent():
    """1% 클레임 (1/100) → 100 - 0.01*5000 = 50."""
    assert score_damage(1, 100) == pytest.approx(50.0)


def test_score_damage_two_percent():
    """2% 클레임 → 0점 (floor 0)."""
    assert score_damage(2, 100) == pytest.approx(0.0)


def test_score_damage_zero_shipments():
    """출하 0건 → 100점 (클레임 불가 = 완벽)."""
    assert score_damage(0, 0) == pytest.approx(100.0)


# ── aggregate_score ─────────────────────────────────────────────────────────

def test_aggregate_all_axes():
    """4축 모두 있을 때 가중합."""
    # 100*0.30 + 80*0.35 + 60*0.20 + 40*0.15 = 30+28+12+6 = 76
    result = aggregate_score(cost=100.0, reliability=80.0, capacity=60.0, damage=40.0)
    assert result == pytest.approx(76.0)


def test_aggregate_cost_na():
    """Cost N/A → 나머지 3축 재정규화 (0.35+0.20+0.15=0.70)."""
    # reliability=80, capacity=60, damage=40 → (80*0.35+60*0.20+40*0.15)/0.70
    # = (28+12+6)/0.70 = 46/0.70 = 65.714...
    result = aggregate_score(cost=None, reliability=80.0, capacity=60.0, damage=40.0)
    assert result == pytest.approx(46.0 / 0.70, rel=1e-3)


def test_aggregate_both_optional_na():
    """Cost+Reliability 모두 N/A → capacity+damage만 (0.20+0.15=0.35)."""
    # capacity=60, damage=40 → (60*0.20+40*0.15)/0.35 = (12+6)/0.35 = 51.428...
    result = aggregate_score(cost=None, reliability=None, capacity=60.0, damage=40.0)
    assert result == pytest.approx(18.0 / 0.35, rel=1e-3)


# ── working_days_in_month ────────────────────────────────────────────────────

def test_working_days_jan_2026():
    """2026-01: 22영업일."""
    assert working_days_in_month(2026, 1) == 22


def test_working_days_feb_2026():
    """2026-02: 20영업일."""
    assert working_days_in_month(2026, 2) == 20
```

- [ ] **Step 2: Run — verify all fail**

```bash
pytest tests/scorecard/test_calc.py -v 2>&1 | head -30
```

Expected: `ImportError` (calc.py not yet created)

- [ ] **Step 3: Create `harness/scorecard/calc.py` with pure score functions**

```python
"""Sub-Spec 5 Scorecard — 점수 산출 함수 + Airtable fetch helpers."""
from __future__ import annotations

import calendar
import datetime
import os
from typing import Optional

import requests

TMS_BASE = "app4x70a8mOrIKsMf"
TBL_SHIP = "tbllg1JoHclGYer7m"
TBL_PARTNER = "tblI4ZXrte7WyhXyd"
TBL_OTIF = "tbl4WfEuGLDlqCTQH"
TBL_CLAIM = "tblIZ9kco1QDpUz0u"
TBL_RATE = "tblQA1ev9fjbowUoP"

# Shipment fields
FLD_SHIP_DATE = "fldQvmEwwzvQW95h9"      # 출하확정일
FLD_EST_CBM = "fldaP8D9AM8CHEZ2o"        # estimated_cbm
FLD_WAVE_REC = "fld9hlDfnTS4frfR4"       # wave_recommendation
FLD_TRANSPORT_COST = "fldRT95SC88KSBATT" # 운송비용
FLD_PARTNER_LINK = "fldM2u6RwLRrO7ymW"  # 배송파트너 (link)
FLD_STATUS = "fldOhibgxg6LIpRTi"         # 발송상태_TMS

# 배송파트너 fields
FLD_P_NAME = "fldUCl2kD890FqRkt"         # 배송파트너
FLD_P_MAX_DAILY = "fldEfEZHWQBx2FO7C"   # max_daily_orders
FLD_P_AUTONOMY = "fldxPZYD3OpwLtqdP"    # autonomy_level

# OTIF fields
FLD_OTIF_SHIP = "fldGwqw0LSIoa824Z"      # Shipment (link)
FLD_ON_TIME = "fldoUQOue0umGJ2xk"        # On_Time

# 배송클레임 fields
FLD_CLAIM_DATE = "fldiNGNqgmQH1MFB7"    # 발생일
FLD_CLAIM_PARTNER = "fldm96CqoNw0pS5ut" # 배송파트너 (link)

# 운임단가 fields
FLD_RATE_PARTNER = "fldgc1e6CEmIj6II1"  # 배송파트너 (link)
FLD_RATE_BASE = "fld8UyM9hPOOX6pTU"    # 기본운임
FLD_RATE_PER_CBM = "fldFT8nO6QrXWcJh1" # CBM당_추가운임
FLD_RATE_CBM_MIN = "fld4DQRC3X3JPmRjP"  # CBM_최소
FLD_RATE_CBM_MAX = "fldh6UTE9G3osg2mp"  # CBM_최대
FLD_RATE_VALID_FROM = "fldcN7yDOW91S6YwG"  # 유효시작일
FLD_RATE_VALID_TO = "fldoMTwX2LRHIbaR4"    # 유효종료일

SELF_EMPLOYED_NAMES = {"이장훈", "조희선", "박종성"}
SPILLOVER_WAVES = {"spillover_고고엑스", "spillover_로젠"}
AUTO_WAVES = {"W1", "W2", "W3", "spillover_고고엑스", "spillover_로젠", "locked-in"}

WEIGHTS = {"cost": 0.30, "reliability": 0.35, "capacity": 0.20, "damage": 0.15}


# ── 순수 점수 함수 (unit-testable) ─────────────────────────────────────────

def score_cost(
    total_transport_cost: float,
    total_cbm: float,
    target_rate: Optional[float],
) -> Optional[float]:
    """운임/CBM 실질 단가 vs 운임단가 목표 단가 비교 → 0~100."""
    if target_rate is None:
        return None
    if total_cbm <= 0:
        return None
    actual_rate = total_transport_cost / total_cbm
    return min(100.0, (target_rate / actual_rate) * 100.0)


def score_reliability(on_time_count: int, total_count: int) -> Optional[float]:
    """OTIF On_Time 비율 → 0~100. 레코드 없으면 None."""
    if total_count == 0:
        return None
    return (on_time_count / total_count) * 100.0


def score_capacity(
    shipments: int,
    max_daily: int,
    working_days: int,
    is_self_employed: bool,
    prev_month_count: Optional[int],
) -> float:
    """가동률(자체기사) 또는 처리량 추세(외주) → 0~100."""
    if is_self_employed:
        ceiling = max_daily * working_days
        if ceiling == 0:
            return 50.0
        return min(100.0, (shipments / ceiling) * 100.0)
    else:
        if prev_month_count is None or prev_month_count == 0:
            return 50.0
        return min(100.0, (shipments / prev_month_count) * 50.0)


def score_damage(claim_count: int, shipment_count: int) -> float:
    """클레임 발생률 → 0~100. 0건=100점, 2%=0점."""
    if shipment_count == 0:
        return 100.0
    claim_rate = claim_count / shipment_count
    return max(0.0, 100.0 - claim_rate * 5000.0)


def aggregate_score(
    cost: Optional[float],
    reliability: Optional[float],
    capacity: float,
    damage: float,
) -> float:
    """N/A 축 재정규화 후 가중합."""
    active: dict[str, tuple[Optional[float], float]] = {
        "cost": (cost, WEIGHTS["cost"]),
        "reliability": (reliability, WEIGHTS["reliability"]),
        "capacity": (capacity, WEIGHTS["capacity"]),
        "damage": (damage, WEIGHTS["damage"]),
    }
    total_weight = sum(w for _, (v, w) in active.items() if v is not None)
    if total_weight == 0:
        return 0.0
    weighted_sum = sum(v * w for _, (v, w) in active.items() if v is not None)
    return weighted_sum / total_weight


def working_days_in_month(year: int, month: int) -> int:
    """해당 월의 월~금 영업일 수 (공휴일 미제외)."""
    _, days = calendar.monthrange(year, month)
    return sum(
        1
        for d in range(1, days + 1)
        if datetime.date(year, month, d).weekday() < 5
    )
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/scorecard/test_calc.py -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 5: Commit**

```bash
git add harness/scorecard/calc.py tests/scorecard/test_calc.py
git commit -m "feat(scorecard): 4축 순수 점수 함수 + 단위 테스트 (TDD)"
```

---

## Task 3: kpi_tracker.py — KPI 계산 + JSONL 히스토리

**Files:**
- Create: `harness/scorecard/kpi_tracker.py`
- Create: `tests/scorecard/test_kpi_tracker.py`

- [ ] **Step 1: Write failing tests**

Create `tests/scorecard/test_kpi_tracker.py`:

```python
"""Unit tests for kpi_tracker — KPI 계산 + JSONL 2-run 시나리오."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from harness.scorecard.kpi_tracker import (
    calc_kpi,
    load_history,
    append_snapshot,
    compute_deltas,
)


# ── calc_kpi ────────────────────────────────────────────────────────────────

def _make_shipments(
    w1=5, w2=3, w3=2, spillover_gogox=2, spillover_logen=1,
    locked_in=3, manual=4, total_auto=20
):
    """wave_recommendation 값별 건수를 가진 mock shipment 목록 생성."""
    ships = []
    for wave, count in [
        ("W1", w1), ("W2", w2), ("W3", w3),
        ("spillover_고고엑스", spillover_gogox),
        ("spillover_로젠", spillover_logen),
        ("locked-in", locked_in),
        ("수동", manual),
    ]:
        for _ in range(count):
            ships.append({
                "fields": {
                    "wave_recommendation": wave,
                    "운송비용": 50000.0 if wave in {"spillover_고고엑스", "spillover_로젠"} else 0.0,
                }
            })
    return ships


def test_kpi_k_lc_1():
    """K-LC-1: 자체기사(W1+W2+W3) / 전체 자동대상."""
    ships = _make_shipments(w1=5, w2=3, w3=2, spillover_gogox=2, spillover_logen=1, locked_in=3, manual=4)
    # total auto targets = all with wave_recommendation not None (=20)
    # self-employed = W1+W2+W3 = 10
    kpi = calc_kpi(ships)
    assert kpi["K_LC_1"] == pytest.approx(10 / 20)


def test_kpi_k_lc_2():
    """K-LC-2: 자동화(!=수동) / 전체 자동대상."""
    ships = _make_shipments(w1=5, w2=3, w3=2, spillover_gogox=2, spillover_logen=1, locked_in=3, manual=4)
    # auto = W1+W2+W3+spillover+locked-in = 5+3+2+2+1+3 = 16
    # total = 20
    kpi = calc_kpi(ships)
    assert kpi["K_LC_2"] == pytest.approx(16 / 20)


def test_kpi_k_lc_3():
    """K-LC-3: spillover 운송비용 합계."""
    ships = _make_shipments(spillover_gogox=2, spillover_logen=1)
    # 3건 × 50000 = 150000
    kpi = calc_kpi(ships)
    assert kpi["K_LC_3"] == pytest.approx(150000.0)


def test_kpi_no_shipments():
    """출하 0건 — 0 반환."""
    kpi = calc_kpi([])
    assert kpi["K_LC_1"] == 0.0
    assert kpi["K_LC_2"] == 0.0
    assert kpi["K_LC_3"] == 0.0


# ── JSONL 히스토리 ──────────────────────────────────────────────────────────

def test_append_and_load():
    """append → load → 동일 데이터 반환."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = Path(f.name)
    snap = {"month": "2026-05", "kpi": {"K_LC_1": 0.5}}
    append_snapshot(path, snap)
    history = load_history(path)
    assert len(history) == 1
    assert history[0]["month"] == "2026-05"


def test_append_is_insert_only():
    """두 번 append → 2개 row."""
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        path = Path(f.name)
    append_snapshot(path, {"month": "2026-05", "kpi": {}})
    append_snapshot(path, {"month": "2026-06", "kpi": {}})
    assert len(load_history(path)) == 2


# ── compute_deltas ──────────────────────────────────────────────────────────

def test_compute_deltas_first_run():
    """히스토리 없음 → baseline 설정, delta=None."""
    current_kpi = {"K_LC_1": 0.61, "K_LC_2": 0.82, "K_LC_3": 1050000.0}
    result = compute_deltas(current_kpi, history=[])
    assert result["K_LC_1"]["delta"] is None
    assert result["K_LC_1"]["baseline"] == pytest.approx(0.61)
    assert result["K_LC_3"]["baseline"] == pytest.approx(1050000.0)


def test_compute_deltas_second_run():
    """히스토리 1개 → 전월 대비 delta 계산."""
    history = [{"month": "2026-05", "kpi": {
        "K_LC_1": {"value": 0.43, "baseline": 0.43},
        "K_LC_2": {"value": 0.79},
        "K_LC_3": {"value": 1200000.0, "baseline": 1200000.0},
    }}]
    current_kpi = {"K_LC_1": 0.61, "K_LC_2": 0.82, "K_LC_3": 1050000.0}
    result = compute_deltas(current_kpi, history)
    assert result["K_LC_1"]["delta"] == pytest.approx(0.61 - 0.43)
    assert result["K_LC_1"]["baseline"] == pytest.approx(0.43)
    assert result["K_LC_3"]["delta_pct"] == pytest.approx((1050000 - 1200000) / 1200000)
```

- [ ] **Step 2: Run — verify fails**

```bash
pytest tests/scorecard/test_kpi_tracker.py -v 2>&1 | head -10
```

Expected: `ImportError`

- [ ] **Step 3: Create `harness/scorecard/kpi_tracker.py`**

```python
"""Sub-Spec 5 KPI 3종 계산 + JSONL 히스토리 관리."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

SELF_EMPLOYED_WAVES = {"W1", "W2", "W3"}
SPILLOVER_WAVES = {"spillover_고고엑스", "spillover_로젠"}
MANUAL_WAVE = "수동"


def calc_kpi(shipments: list[dict]) -> dict:
    """K-LC-1/2/3 계산.

    shipments: Airtable Shipment 레코드 목록.
      각 레코드 fields에 wave_recommendation, 운송비용 포함.
    """
    total = len(shipments)
    if total == 0:
        return {"K_LC_1": 0.0, "K_LC_2": 0.0, "K_LC_3": 0.0}

    self_employed_count = 0
    auto_count = 0
    spillover_cost = 0.0

    for rec in shipments:
        f = rec.get("fields", {})
        wave = f.get("wave_recommendation") or ""
        cost = float(f.get("운송비용") or 0.0)

        if wave in SELF_EMPLOYED_WAVES:
            self_employed_count += 1
        if wave and wave != MANUAL_WAVE:
            auto_count += 1
        if wave in SPILLOVER_WAVES:
            spillover_cost += cost

    return {
        "K_LC_1": self_employed_count / total,
        "K_LC_2": auto_count / total,
        "K_LC_3": spillover_cost,
    }


def load_history(path: Path) -> list[dict]:
    """JSONL → list[dict]. 파일 없으면 []."""
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def append_snapshot(path: Path, snapshot: dict) -> None:
    """월간 스냅샷 1 row append (INSERT ONLY)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")


def compute_deltas(current_kpi: dict, history: list[dict]) -> dict:
    """현재 KPI vs 직전 스냅샷 비교 → delta 포함 result dict.

    첫 실행(history 없음): baseline 설정, delta=None.
    이후 실행: 직전 스냅샷과 비교.
    """
    if not history:
        return {
            "K_LC_1": {
                "value": current_kpi["K_LC_1"],
                "baseline": current_kpi["K_LC_1"],
                "delta": None,
                "target": None,
            },
            "K_LC_2": {
                "value": current_kpi["K_LC_2"],
                "delta": None,
                "target": 0.70,
            },
            "K_LC_3": {
                "value": current_kpi["K_LC_3"],
                "baseline": current_kpi["K_LC_3"],
                "delta_pct": None,
                "target": None,
            },
        }

    prev = history[-1]["kpi"]
    prev_k1 = prev.get("K_LC_1", {})
    prev_k3 = prev.get("K_LC_3", {})

    baseline_k1 = prev_k1.get("baseline", prev_k1.get("value", current_kpi["K_LC_1"]))
    baseline_k3 = prev_k3.get("baseline", prev_k3.get("value", current_kpi["K_LC_3"]))

    prev_k1_val = prev_k1.get("value", 0.0) if isinstance(prev_k1, dict) else float(prev_k1)
    prev_k3_val = prev_k3.get("value", 0.0) if isinstance(prev_k3, dict) else float(prev_k3)

    delta_k3_pct = (
        (current_kpi["K_LC_3"] - prev_k3_val) / prev_k3_val
        if prev_k3_val != 0 else None
    )

    return {
        "K_LC_1": {
            "value": current_kpi["K_LC_1"],
            "baseline": baseline_k1,
            "delta": current_kpi["K_LC_1"] - prev_k1_val,
            "target": baseline_k1 + 0.20 if baseline_k1 is not None else None,
        },
        "K_LC_2": {
            "value": current_kpi["K_LC_2"],
            "delta": current_kpi["K_LC_2"] - (prev.get("K_LC_2", {}).get("value", 0.0)
                                               if isinstance(prev.get("K_LC_2"), dict)
                                               else float(prev.get("K_LC_2", 0.0))),
            "target": 0.70,
        },
        "K_LC_3": {
            "value": current_kpi["K_LC_3"],
            "baseline": baseline_k3,
            "delta_pct": delta_k3_pct,
            "target": baseline_k3 * 0.80 if baseline_k3 else None,
        },
    }
```

- [ ] **Step 4: Run tests — verify pass**

```bash
pytest tests/scorecard/test_kpi_tracker.py -v
```

Expected: 모든 테스트 PASS

- [ ] **Step 5: Run all scorecard tests**

```bash
pytest tests/scorecard/ -v
```

Expected: 전체 PASS

- [ ] **Step 6: Commit**

```bash
git add harness/scorecard/kpi_tracker.py tests/scorecard/test_kpi_tracker.py
git commit -m "feat(scorecard): kpi_tracker KPI 3종 + JSONL 히스토리 (TDD)"
```

---

## Task 4: Airtable fetch helpers — `harness/scorecard/calc.py` 추가

**Files:**
- Modify: `harness/scorecard/calc.py` (fetch 함수 추가)

- [ ] **Step 1: Append Airtable fetch helpers to `harness/scorecard/calc.py`**

Append the following to the end of `harness/scorecard/calc.py`:

```python

# ── Airtable fetch helpers ──────────────────────────────────────────────────

def _airtable_headers() -> dict:
    pat = os.environ.get("AIRTABLE_PAT") or os.environ.get("AIRTABLE_API_KEY")
    if not pat:
        raise EnvironmentError("AIRTABLE_PAT 환경변수 필요")
    return {"Authorization": f"Bearer {pat}"}


def _fetch_all(url: str, headers: dict, params: dict | None = None) -> list[dict]:
    """페이지네이션 처리해 전체 레코드 반환."""
    records: list[dict] = []
    offset = None
    while True:
        p = dict(params or {})
        if offset:
            p["offset"] = offset
        resp = requests.get(url, headers=headers, params=p, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return records


def fetch_partners(headers: dict) -> list[dict]:
    """배송파트너 전원 조회 (name, max_daily_orders, autonomy_level)."""
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_PARTNER}"
    return _fetch_all(url, headers, {
        "fields[]": [FLD_P_NAME, FLD_P_MAX_DAILY, FLD_P_AUTONOMY],
    })


def fetch_prev_month_shipments(headers: dict, year: int, month: int) -> list[dict]:
    """전월 출하확정일 기준 Shipment 조회 (발송상태_TMS 무관 — 출하완료 포함)."""
    import calendar as _cal
    _, last_day = _cal.monthrange(year, month)
    first = datetime.date(year, month, 1).isoformat()
    last = datetime.date(year, month, last_day).isoformat()
    formula = (
        f"AND("
        f"IS_AFTER({{출하확정일}}, '{datetime.date(year, month, 1) - datetime.timedelta(days=1)}'),"
        f"IS_BEFORE({{출하확정일}}, '{datetime.date(year, month, last_day) + datetime.timedelta(days=1)}')"
        f")"
    )
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_SHIP}"
    return _fetch_all(url, headers, {
        "filterByFormula": formula,
        "fields[]": [
            FLD_SHIP_DATE, FLD_EST_CBM, FLD_WAVE_REC,
            FLD_TRANSPORT_COST, FLD_PARTNER_LINK, FLD_STATUS,
        ],
    })


def fetch_otif_all(headers: dict) -> list[dict]:
    """OTIF 테이블 전체 조회 (Shipment 링크 + On_Time 필드만)."""
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_OTIF}"
    return _fetch_all(url, headers, {
        "fields[]": [FLD_OTIF_SHIP, FLD_ON_TIME],
    })


def fetch_prev_month_claims(headers: dict, year: int, month: int) -> list[dict]:
    """전월 발생일 기준 배송클레임 조회."""
    import calendar as _cal
    _, last_day = _cal.monthrange(year, month)
    formula = (
        f"AND("
        f"IS_AFTER({{발생일}}, '{datetime.date(year, month, 1) - datetime.timedelta(days=1)}'),"
        f"IS_BEFORE({{발생일}}, '{datetime.date(year, month, last_day) + datetime.timedelta(days=1)}')"
        f")"
    )
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_CLAIM}"
    return _fetch_all(url, headers, {
        "filterByFormula": formula,
        "fields[]": [FLD_CLAIM_DATE, FLD_CLAIM_PARTNER],
    })


def fetch_rate_card(headers: dict) -> dict[str, float]:
    """운임단가 테이블 → {partner_record_id: target_rate(₩/CBM)}.

    target_rate = 기본운임 / ((CBM_최소+CBM_최대)/2) + CBM당_추가운임.
    동일 파트너 여러 행 존재 시 마지막 유효 단가 사용.
    """
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_RATE}"
    rows = _fetch_all(url, headers, {
        "fields[]": [FLD_RATE_PARTNER, FLD_RATE_BASE, FLD_RATE_PER_CBM,
                     FLD_RATE_CBM_MIN, FLD_RATE_CBM_MAX],
    })
    rate_map: dict[str, float] = {}
    for row in rows:
        f = row.get("fields", {})
        partner_ids: list[str] = f.get(FLD_RATE_PARTNER, [])
        base = float(f.get(FLD_RATE_BASE) or 0)
        per_cbm = float(f.get(FLD_RATE_PER_CBM) or 0)
        cbm_min = float(f.get(FLD_RATE_CBM_MIN) or 1)
        cbm_max = float(f.get(FLD_RATE_CBM_MAX) or 1)
        mid_cbm = (cbm_min + cbm_max) / 2 if cbm_max > 0 else 1
        target = (base / mid_cbm) + per_cbm if mid_cbm > 0 else per_cbm
        for pid in partner_ids:
            rate_map[pid] = target
    return rate_map


def calc_all_carriers(
    year: int,
    month: int,
    prev_month_counts: dict[str, int] | None = None,
) -> tuple[list, list[dict]]:
    """전체 carrier 점수 계산. (list[CarrierScore], list[dict] shipments_for_kpi) 반환."""
    from harness.scorecard import CarrierScore

    headers = _airtable_headers()
    partners = fetch_partners(headers)
    shipments = fetch_prev_month_shipments(headers, year, month)
    otif_all = fetch_otif_all(headers)
    claims = fetch_prev_month_claims(headers, year, month)
    rate_card = fetch_rate_card(headers)
    wdays = working_days_in_month(year, month)

    # 인덱스: shipment_id → partner_id
    ship_to_partner: dict[str, str] = {}
    for rec in shipments:
        f = rec.get("fields", {})
        partner_links: list[str] = f.get(FLD_PARTNER_LINK, [])
        if partner_links:
            ship_to_partner[rec["id"]] = partner_links[0]

    # 인덱스: partner_id → On_Time 건수
    partner_otif_total: dict[str, int] = {}
    partner_otif_on_time: dict[str, int] = {}
    for otif in otif_all:
        f = otif.get("fields", {})
        ship_links: list[str] = f.get(FLD_OTIF_SHIP, [])
        on_time = int(f.get(FLD_ON_TIME) or 0)
        for sid in ship_links:
            pid = ship_to_partner.get(sid)
            if pid:
                partner_otif_total[pid] = partner_otif_total.get(pid, 0) + 1
                partner_otif_on_time[pid] = partner_otif_on_time.get(pid, 0) + on_time

    # 인덱스: partner_id → claim 건수
    partner_claims: dict[str, int] = {}
    for claim in claims:
        f = claim.get("fields", {})
        for pid in f.get(FLD_CLAIM_PARTNER, []):
            partner_claims[pid] = partner_claims.get(pid, 0) + 1

    # 인덱스: partner_id → shipment 건수·총운임·총CBM
    partner_ship_count: dict[str, int] = {}
    partner_cost: dict[str, float] = {}
    partner_cbm: dict[str, float] = {}
    for rec in shipments:
        f = rec.get("fields", {})
        plinks: list[str] = f.get(FLD_PARTNER_LINK, [])
        if not plinks:
            continue
        pid = plinks[0]
        partner_ship_count[pid] = partner_ship_count.get(pid, 0) + 1
        partner_cost[pid] = partner_cost.get(pid, 0.0) + float(f.get(FLD_TRANSPORT_COST) or 0)
        partner_cbm[pid] = partner_cbm.get(pid, 0.0) + float(f.get(FLD_EST_CBM) or 0)

    scores: list[CarrierScore] = []
    for p in partners:
        pid = p["id"]
        f = p.get("fields", {})
        name = f.get(FLD_P_NAME, pid)
        is_self = name in SELF_EMPLOYED_NAMES
        max_daily = int(f.get(FLD_P_MAX_DAILY) or 0)
        ship_count = partner_ship_count.get(pid, 0)

        cost_score = score_cost(
            partner_cost.get(pid, 0.0),
            partner_cbm.get(pid, 0.0),
            rate_card.get(pid),
        )
        rel_score = score_reliability(
            partner_otif_on_time.get(pid, 0),
            partner_otif_total.get(pid, 0),
        )
        cap_score = score_capacity(
            ship_count, max_daily, wdays, is_self,
            (prev_month_counts or {}).get(pid),
        )
        dmg_score = score_damage(partner_claims.get(pid, 0), ship_count)
        total = aggregate_score(cost_score, rel_score, cap_score, dmg_score)

        scores.append(CarrierScore(
            carrier_id=pid,
            carrier_name=name,
            cost=cost_score,
            reliability=rel_score,
            capacity=cap_score,
            damage=dmg_score,
            total=total,
            shipment_count=ship_count,
        ))

    return scores, shipments
```

- [ ] **Step 2: Verify existing tests still pass**

```bash
pytest tests/scorecard/ -v
```

Expected: 전체 PASS (fetch 함수는 Airtable 연결 없이 import만 됨)

- [ ] **Step 3: Commit**

```bash
git add harness/scorecard/calc.py
git commit -m "feat(scorecard): Airtable fetch helpers + calc_all_carriers 통합 집계"
```

---

## Task 5: run_monthly.py — 오케스트레이터 + Slack 포맷터

**Files:**
- Create: `scripts/scorecard/run_monthly.py`

- [ ] **Step 1: Create `scripts/scorecard/run_monthly.py`**

```python
"""Sub-Spec 5 월간 Scorecard 실행 스크립트.

Usage:
  python scripts/scorecard/run_monthly.py [--dry-run] [--month YYYY-MM]

--dry-run: Airtable 조회 후 Slack 발송 없이 메시지만 출력.
--month: 대상 월 지정 (기본: 직전 달).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
load_dotenv()

from harness.scorecard import CarrierScore
from harness.scorecard.calc import calc_all_carriers
from harness.scorecard.kpi_tracker import calc_kpi, load_history, append_snapshot, compute_deltas

KST = timezone(timedelta(hours=9))
HISTORY_PATH_DEFAULT = "scripts/scorecard/scorecard_history.jsonl"
WARN_THRESHOLD = 70.0


def _fmt_optional(val: float | None, fmt: str = ".1f") -> str:
    return f"{val:{fmt}}" if val is not None else "N/A"


def format_slack_message(
    scores: list[CarrierScore],
    kpi_deltas: dict,
    month_str: str,
) -> str:
    """상세형 B Slack DM 메시지 조립."""
    kst_now = datetime.now(KST).strftime("%Y-%m-%dT%H:%M KST")
    lines: list[str] = [
        f"📊 [{month_str}] Carrier Scorecard",
        f"대상 {len(scores)}개사 · 산출: {kst_now}",
        "",
    ]

    sorted_scores = sorted(scores, key=lambda s: s.total, reverse=True)
    warn: list[CarrierScore] = []

    for cs in sorted_scores:
        lines.append(f"── {cs.carrier_name} ({cs.total:.1f}/100) ──")
        lines.append(f"Cost        30% × {_fmt_optional(cs.cost)}pt = {_fmt_optional((cs.cost or 0)*0.30)}")
        lines.append(f"Reliability 35% × {_fmt_optional(cs.reliability)}pt = {_fmt_optional((cs.reliability or 0)*0.35)}")
        lines.append(f"Capacity    20% × {cs.capacity:.1f}pt = {cs.capacity*0.20:.1f}")
        lines.append(f"Damage      15% × {cs.damage:.1f}pt = {cs.damage*0.15:.1f}")
        lines.append(f"처리건수: {cs.shipment_count}건")
        lines.append("")
        if cs.total < WARN_THRESHOLD:
            warn.append(cs)

    if warn:
        lines.append("⚠️ 주의 (70점 미만)")
        for cs in warn:
            lines.append(f"  {cs.carrier_name} {cs.total:.1f}")
        lines.append("")

    lines.append("─" * 40)
    lines.append("KPI 상세 (전월 비교)")

    k1 = kpi_deltas["K_LC_1"]
    k2 = kpi_deltas["K_LC_2"]
    k3 = kpi_deltas["K_LC_3"]

    def _arrow(delta) -> str:
        if delta is None:
            return "← 첫 측정 (baseline)"
        return "↑" if delta > 0 else ("↓" if delta < 0 else "→")

    k1_pct = f"{k1['value']*100:.1f}%"
    k1_delta_str = f"({k1['delta']*100:+.1f}%p)" if k1["delta"] is not None else ""
    k1_target = f"[목표: {(k1['target'] or 0)*100:.1f}%]" if k1.get("target") else ""
    lines.append(f"K-LC-1 자체기사 활용도  {k1_pct} {k1_delta_str} {_arrow(k1['delta'])}  {k1_target}")

    k2_pct = f"{k2['value']*100:.1f}%"
    k2_delta_str = f"({k2['delta']*100:+.1f}%p)" if k2.get("delta") is not None else ""
    k2_ok = "✅" if k2["value"] >= 0.70 else "❌"
    lines.append(f"K-LC-2 Wave 자동화 비중 {k2_pct} {k2_delta_str} {k2_ok}  [목표: 70%]")

    k3_val = f"₩{k3['value']:,.0f}"
    k3_delta_str = f"({k3['delta_pct']*100:+.1f}%)" if k3.get("delta_pct") is not None else ""
    k3_target = f"[목표: ₩{k3['target']:,.0f}]" if k3.get("target") else ""
    lines.append(f"K-LC-3 Spillover 비용   {k3_val} {k3_delta_str}  {k3_target}")

    return "\n".join(lines)


def _send_slack(message: str) -> bool:
    import requests
    token = os.environ.get("SLACK_BOT_TOKEN")
    channel = os.environ.get("SLACK_DM_USER_ID")
    if not token or not channel:
        print("[WARN] SLACK_BOT_TOKEN / SLACK_DM_USER_ID 미설정 — Slack 발송 스킵", file=sys.stderr)
        return False
    resp = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {token}"},
        json={"channel": channel, "text": message},
        timeout=10,
    )
    data = resp.json()
    if data.get("ok"):
        print("Slack DM 발송 완료")
        return True
    print(f"[ERROR] Slack 발송 실패: {data.get('error')}", file=sys.stderr)
    return False


def _prev_month(ref: datetime) -> tuple[int, int]:
    """ref 기준 직전 달 (year, month) 반환."""
    first = ref.replace(day=1)
    prev = first - timedelta(days=1)
    return prev.year, prev.month


def main(dry_run: bool = False, month_override: str | None = None) -> None:
    now_kst = datetime.now(KST)

    if month_override:
        year, month = int(month_override[:4]), int(month_override[5:7])
    else:
        year, month = _prev_month(now_kst)

    month_str = f"{year:04d}-{month:02d}"
    print(f"[scorecard] 대상 월: {month_str}")

    history_path = __import__("pathlib").Path(HISTORY_PATH_DEFAULT)
    history = load_history(history_path)

    # 이전 달 처리건수 (Capacity 외주 추세용)
    prev_counts: dict[str, int] | None = None
    if history:
        last_snap = history[-1]
        prev_counts = {
            name: data.get("shipment_count", 0)
            for name, data in last_snap.get("carriers", {}).items()
        }

    print("[scorecard] Airtable 조회 중...")
    scores, shipments = calc_all_carriers(year, month, prev_counts)

    kpi_raw = calc_kpi(shipments)
    kpi_deltas = compute_deltas(kpi_raw, history)

    # JSONL 스냅샷 구성
    snapshot = {
        "month": month_str,
        "generated_at": now_kst.isoformat(),
        "carriers": {
            cs.carrier_name: {
                "cost": cs.cost,
                "reliability": cs.reliability,
                "capacity": cs.capacity,
                "damage": cs.damage,
                "total": cs.total,
                "shipment_count": cs.shipment_count,
            }
            for cs in scores
        },
        "kpi": kpi_deltas,
    }

    message = format_slack_message(scores, kpi_deltas, month_str)

    if dry_run:
        print("\n=== DRY RUN — Slack DM 미발송 ===")
        print(message)
        print("=== END ===")
    else:
        append_snapshot(history_path, snapshot)
        _send_slack(message)
        print(f"[scorecard] 스냅샷 저장: {history_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="월간 Scorecard 실행")
    parser.add_argument("--dry-run", action="store_true", help="Slack 발송 없이 메시지만 출력")
    parser.add_argument("--month", help="대상 월 (YYYY-MM). 기본: 직전 달")
    args = parser.parse_args()
    main(dry_run=args.dry_run, month_override=args.month)
```

- [ ] **Step 2: Verify import OK**

```bash
python -c "from scripts.scorecard.run_monthly import format_slack_message; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Dry-run smoke test (Airtable 연결 필요)**

```bash
python scripts/scorecard/run_monthly.py --dry-run --month 2026-05
```

Expected: Airtable PAT 설정 시 carrier 목록 + 포맷된 Slack 메시지 출력. PAT 미설정 시 `EnvironmentError`.

- [ ] **Step 4: Commit**

```bash
git add scripts/scorecard/run_monthly.py
git commit -m "feat(scorecard): run_monthly 오케스트레이터 + Slack 상세형 B 포맷터"
```

---

## Task 6: GitHub Actions — `scorecard.yml`

**Files:**
- Create: `.github/workflows/scorecard.yml`

- [ ] **Step 1: Create `.github/workflows/scorecard.yml`**

```yaml
name: Monthly Scorecard

on:
  schedule:
    # 매월 1일 00:01 UTC = 09:01 KST
    - cron: "1 0 1 * *"
  workflow_dispatch:
    inputs:
      dry_run:
        description: "dry-run (Slack 미발송)"
        required: false
        default: "false"
      month:
        description: "대상 월 YYYY-MM (기본: 직전 달)"
        required: false
        default: ""

jobs:
  scorecard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install requests python-dotenv

      - name: Run scorecard
        env:
          AIRTABLE_PAT: ${{ secrets.AIRTABLE_PAT }}
          SLACK_BOT_TOKEN: ${{ secrets.SLACK_BOT_TOKEN }}
          SLACK_DM_USER_ID: ${{ secrets.SLACK_DM_USER_ID }}
        run: |
          DRY_RUN_FLAG=""
          if [ "${{ github.event.inputs.dry_run }}" = "true" ]; then
            DRY_RUN_FLAG="--dry-run"
          fi
          MONTH_FLAG=""
          if [ -n "${{ github.event.inputs.month }}" ]; then
            MONTH_FLAG="--month ${{ github.event.inputs.month }}"
          fi
          python scripts/scorecard/run_monthly.py $DRY_RUN_FLAG $MONTH_FLAG

      - name: Commit scorecard_history update
        if: github.event.inputs.dry_run != 'true'
        run: |
          git config user.email "github-actions@github.com"
          git config user.name "GitHub Actions"
          git add scripts/scorecard/scorecard_history.jsonl || true
          git diff --cached --quiet || git commit -m "chore(scorecard): monthly snapshot $(date +%Y-%m)"
          git push || true
```

> **Note:** GitHub Actions cron `L` (last day of month)은 지원하지 않음. `1 15 28-31 * *`으로 대체하거나 workflow_dispatch 수동 실행. 아래 수정 버전:

수정:
```yaml
    - cron: "1 0 1 * *"   # 매월 1일 00:01 UTC = 09:01 KST
```

- [ ] **Step 2: Lint 확인**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/scorecard.yml'))" 2>/dev/null && echo "OK"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/scorecard.yml
git commit -m "ci(scorecard): 월간 cron scorecard.yml (매월 28일 UTC=다음날 KST 1일)"
```

---

## Task 7: Validation Contract 검증 + feature_list 업데이트

**Files:**
- Create: `scripts/verification/verify_subspec5_contract.py`
- Modify: `.claude/feature_list.json`

- [ ] **Step 1: Create contract verification script**

Create `scripts/verification/verify_subspec5_contract.py`:

```python
"""Sub-Spec 5 Validation Contract C1~C4 자동 검증."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path


PASS = "✅ PASS"
FAIL = "❌ FAIL"
results = []


def check(label: str, ok: bool, detail: str = "") -> None:
    status = PASS if ok else FAIL
    print(f"{status} {label}" + (f" — {detail}" if detail else ""))
    results.append(ok)


# C1: scorecard.yml 존재 + cron 설정 포함
yml_path = Path(".github/workflows/scorecard.yml")
c1 = yml_path.exists() and "cron" in yml_path.read_text()
check("C1: scorecard.yml cron 설정 존재", c1)

# C2: test_calc.py 모든 테스트 PASS
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/scorecard/test_calc.py", "-q"],
    capture_output=True, text=True
)
c2 = result.returncode == 0
check("C2: 4축 점수 함수 단위 테스트 PASS", c2, result.stdout.strip().split("\n")[-1])

# C3: test_kpi_tracker.py 모든 테스트 PASS
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/scorecard/test_kpi_tracker.py", "-q"],
    capture_output=True, text=True
)
c3 = result.returncode == 0
check("C3: KPI 계산 + JSONL 2-run 시나리오 PASS", c3, result.stdout.strip().split("\n")[-1])

# C4: run_monthly.py --dry-run import 가능 + format_slack_message 실행
try:
    from scripts.scorecard.run_monthly import format_slack_message
    from harness.scorecard import CarrierScore
    from harness.scorecard.kpi_tracker import compute_deltas
    mock_scores = [
        CarrierScore("r1", "이장훈", cost=90.0, reliability=85.0, capacity=80.0, damage=100.0, total=88.0, shipment_count=30),
        CarrierScore("r2", "로젠", cost=None, reliability=70.0, capacity=50.0, damage=95.0, total=65.0, shipment_count=50),
    ]
    mock_kpi = compute_deltas({"K_LC_1": 0.6, "K_LC_2": 0.8, "K_LC_3": 500000.0}, [])
    msg = format_slack_message(mock_scores, mock_kpi, "2026-05")
    c4_ok = "⚠️ 주의" in msg and "K-LC-1" in msg and "K-LC-2" in msg and "K-LC-3" in msg
    check("C4: Slack 포맷 상세형 B (⚠️ 주의 + KPI 3종 포함)", c4_ok)
except Exception as e:
    check("C4: Slack 포맷 상세형 B", False, str(e))

print()
total = sum(results)
print(f"Contract: {total}/{len(results)} PASS")
sys.exit(0 if all(results) else 1)
```

- [ ] **Step 2: Run contract verification**

```bash
python scripts/verification/verify_subspec5_contract.py
```

Expected:
```
✅ PASS C1: scorecard.yml cron 설정 존재
✅ PASS C2: 4축 점수 함수 단위 테스트 PASS — X passed
✅ PASS C3: KPI 계산 + JSONL 2-run 시나리오 PASS — X passed
✅ PASS C4: Slack 포맷 상세형 B (⚠️ 주의 + KPI 3종 포함)

Contract: 4/4 PASS
```

- [ ] **Step 3: feature_list.json 업데이트**

`.claude/feature_list.json`에서:
- `SCM-LANE-SUBSPEC-5` 항목을 찾아 `"status": "done"`으로 변경
- 없으면 다음 항목 추가:

```json
{
  "id": "SCM-LANE-SUBSPEC-5",
  "title": "Sub-Spec 5 Scorecard + KPI — 월간 carrier 평가",
  "status": "done",
  "priority": "done",
  "notes": "4축 Scorecard + K-LC-1~3 + JSONL + Slack DM 상세형. C1~C4 PASS."
}
```

운임 자동입력 파이프라인 항목 추가:

```json
{
  "id": "SCM-FREIGHT-AUTO",
  "title": "운임 자동입력 — Slack 발주알림 → Dropbox PDF → Airtable 운송비용 PATCH",
  "status": "medium",
  "priority": "medium",
  "notes": "Zapier trigger + pdfplumber + PNA→Shipment 매칭. Sub-Spec 5 이후 착수."
}
```

- [ ] **Step 4: 전체 테스트 최종 확인**

```bash
pytest tests/scorecard/ -v
```

Expected: 전체 PASS

- [ ] **Step 5: Final commit**

```bash
git add scripts/verification/verify_subspec5_contract.py .claude/feature_list.json
git commit -m "feat(scorecard): Sub-Spec 5 Contract C1~C4 검증 스크립트 + feature_list 갱신"
```

---

## Validation Contract 통과 기준

| # | 조건 | 달성 방법 |
|---|---|---|
| C1 | `scorecard.yml` cron 존재 | Task 6 |
| C2 | 9개 carrier 4축 점수 계산 (단위 테스트) | Task 2 |
| C3 | KPI 3종 + JSONL 2-run 시나리오 | Task 3 |
| C4 | Slack 상세형 B 포맷 (⚠️ 주의 + KPI) | Task 5 + Task 7 |

**6개월 ROI 리뷰:** 2026-12월 수동 실행 — `python scripts/scorecard/run_monthly.py --dry-run --month 2026-11` 결과와 초기 baseline 비교.
