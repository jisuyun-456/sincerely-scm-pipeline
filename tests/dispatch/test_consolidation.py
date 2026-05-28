"""Tests for Multi-PNA consolidation + Tier→Wave routing (Contract C3·C4)."""
from __future__ import annotations

import pytest

from harness.dispatch.wave_assigner import (
    DRIVER_LIMITS,
    Shipment,
    TIER_TO_CANDIDATES,
    assign_waves,
    compute_utilization,
)


@pytest.fixture
def empty_autonomy():
    return {}


def _ids(plan):
    return [s.id for s in plan.shipments]


class TestMultiPNAConsolidation:
    """Contract C3 — 같은 (slot, region) 그룹 + PNA cluster 정확 그룹화."""

    def test_same_pna_grouped_in_one_wave(self, empty_autonomy):
        ships = [
            Shipment('A1', 'PNA-X', '오전', 'tier1_seoul', 1.0),
            Shipment('A2', 'PNA-X', '오전', 'tier1_seoul', 1.5),
            Shipment('A3', 'PNA-Y', '오전', 'tier1_seoul', 0.5),
        ]
        plans = assign_waves(ships, empty_autonomy, '2026-05-28', use_sa=False)
        placed = sum([_ids(plans[wid]) for wid in ('W1','W2','W3')], [])
        assert set(placed) == {'A1', 'A2', 'A3'}

    def test_different_region_split(self, empty_autonomy):
        ships = [
            Shipment('S1', 'PNA-A', '오전', 'tier1_seoul', 1.0),
            Shipment('P1', 'PNA-A', '오전', 'tier5_provincial', 1.0),
        ]
        plans = assign_waves(ships, empty_autonomy, '2026-05-28', use_sa=False)
        # 지방은 W3만, 서울은 W1/W2/W3
        assert 'P1' in _ids(plans['W3'])

    def test_null_slot_goes_to_manual(self, empty_autonomy):
        ships = [Shipment('NS1', 'PNA-Q', None, 'tier1_seoul', 1.0)]
        plans = assign_waves(ships, empty_autonomy, '2026-05-28', use_sa=False)
        assert _ids(plans['수동']) == ['NS1']


class TestTierRouting:
    """Contract C3 — Tier별 후보 wave 정확."""

    def test_tier1_all_waves_allowed(self):
        assert TIER_TO_CANDIDATES['tier1_seoul'] == ['W1', 'W2', 'W3']

    def test_tier2_ijanghoon_all_waves(self):
        assert TIER_TO_CANDIDATES['tier2_이장훈_gyeonggi'] == ['W1', 'W2', 'W3']

    def test_tier3_gyeonggi_no_w1(self):
        assert TIER_TO_CANDIDATES['tier3_gyeonggi_etc'] == ['W2', 'W3']

    def test_tier4_incheon_all_waves_decision1(self):
        # P3.5 Decision 1: 인천도 W1·W2·W3 모두 가능
        assert TIER_TO_CANDIDATES['tier4_incheon'] == ['W1', 'W2', 'W3']

    def test_tier5_provincial_w3_only(self):
        assert TIER_TO_CANDIDATES['tier5_provincial'] == ['W3']

    def test_unknown_no_candidates(self):
        assert TIER_TO_CANDIDATES['unknown'] == []


class TestW1SlotFilter:
    def test_w1_accepts_only_morning_slot(self, empty_autonomy):
        # W1은 '오전' 슬롯만. '무관' 슬롯이면 W1 후보에서 제외
        ships = [
            Shipment('M1', 'PNA-A', '무관', 'tier1_seoul', 1.0),
            Shipment('M2', 'PNA-A', '무관', 'tier1_seoul', 1.0),
            Shipment('M3', 'PNA-A', '무관', 'tier1_seoul', 1.0),
        ]
        plans = assign_waves(ships, empty_autonomy, '2026-05-28', use_sa=False)
        assert plans['W1'].count == 0
