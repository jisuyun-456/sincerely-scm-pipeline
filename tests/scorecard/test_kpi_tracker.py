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
