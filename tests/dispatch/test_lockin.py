"""Tests for partner locked-in handling (Contract C5)."""
from __future__ import annotations

import pytest

from harness.dispatch.wave_assigner import Shipment, assign_waves


class TestLockedIn:
    """Contract C5 — locked-in 9 records recommender override 0건."""

    def test_locked_partner_routed_to_lockin_wave(self):
        ships = [Shipment('L1', 'PNA-A', '오전', 'tier1_seoul', 1.0,
                         assigned_partner='LOCK_PTN')]
        plans = assign_waves(ships, {'LOCK_PTN': 'locked-in'}, '2026-05-28', use_sa=False)
        assert [s.id for s in plans['locked-in'].shipments] == ['L1']
        # W1·W2·W3·spillover에는 들어가면 안 됨
        for wid in ('W1', 'W2', 'W3', 'spillover_고고엑스', 'spillover_로젠'):
            assert 'L1' not in [s.id for s in plans[wid].shipments]

    def test_autonomous_partner_excluded(self):
        ships = [Shipment('A1', 'PNA-A', '오전', 'tier1_seoul', 1.0,
                         assigned_partner='AUTO_PTN')]
        plans = assign_waves(ships, {'AUTO_PTN': 'autonomous'}, '2026-05-28', use_sa=False)
        all_ids = sum([[s.id for s in p.shipments] for p in plans.values()], [])
        assert 'A1' not in all_ids

    def test_locked_in_idempotent_across_calls(self):
        # 입력 Shipment 비변경 확인
        ships = [Shipment('L2', 'PNA-A', '오전', 'tier1_seoul', 1.0,
                         assigned_partner='LOCK_PTN')]
        p1 = assign_waves(ships, {'LOCK_PTN': 'locked-in'}, '2026-05-28', use_sa=False)
        p2 = assign_waves(ships, {'LOCK_PTN': 'locked-in'}, '2026-05-28', use_sa=False)
        assert [s.id for s in p1['locked-in'].shipments] == [s.id for s in p2['locked-in'].shipments]
        assert ships[0].wave_locked is False  # input 비변경

    def test_partial_autonomy_treated_as_normal(self):
        ships = [Shipment('P1', 'PNA-A', '오전', 'tier1_seoul', 1.0,
                         assigned_partner='PART_PTN')]
        plans = assign_waves(ships, {'PART_PTN': 'partial'}, '2026-05-28', use_sa=False)
        # partial은 정상 처리 → W1·W2·W3에 들어감
        placed = sum([[s.id for s in plans[wid].shipments] for wid in ('W1','W2','W3')], [])
        assert 'P1' in placed
