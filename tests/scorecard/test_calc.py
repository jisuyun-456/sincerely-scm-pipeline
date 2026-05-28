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
