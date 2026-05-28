"""Tests for wave_locked override handling (Contract C7)."""
from __future__ import annotations

import pytest

from harness.dispatch.wave_assigner import Shipment, assign_waves


class TestOverride:
    """Contract C7 — wave_locked=True 처리 (다음 cycle skip)."""

    def test_locked_shipment_goes_to_manual_not_wave(self):
        ships = [Shipment('LK1', 'PNA-A', '오전', 'tier1_seoul', 1.0, wave_locked=True)]
        plans = assign_waves(ships, {}, '2026-05-28', use_sa=False)
        assert [s.id for s in plans['수동'].shipments] == ['LK1']
        for wid in ('W1', 'W2', 'W3'):
            assert 'LK1' not in [s.id for s in plans[wid].shipments]

    def test_unlocked_shipment_assigned_normally(self):
        ships = [Shipment('UN1', 'PNA-A', '오전', 'tier1_seoul', 1.0, wave_locked=False)]
        plans = assign_waves(ships, {}, '2026-05-28', use_sa=False)
        placed = sum([[s.id for s in plans[wid].shipments] for wid in ('W1','W2','W3')], [])
        assert 'UN1' in placed

    def test_mixed_lock_and_unlocked(self):
        ships = [
            Shipment('A', 'PNA-X', '오전', 'tier1_seoul', 1.0, wave_locked=True),
            Shipment('B', 'PNA-X', '오전', 'tier1_seoul', 1.0, wave_locked=False),
        ]
        plans = assign_waves(ships, {}, '2026-05-28', use_sa=False)
        assert 'A' in [s.id for s in plans['수동'].shipments]
        placed = sum([[s.id for s in plans[wid].shipments] for wid in ('W1','W2','W3')], [])
        assert 'B' in placed

    def test_override_input_idempotent(self):
        ships = [Shipment('IDEM', 'PNA-A', '오전', 'tier1_seoul', 1.0, wave_locked=True)]
        p1 = assign_waves(ships, {}, '2026-05-28', use_sa=False)
        p2 = assign_waves(ships, {}, '2026-05-28', use_sa=False)
        assert [s.id for s in p1['수동'].shipments] == [s.id for s in p2['수동'].shipments]
        assert ships[0].wave_locked is True  # 원본 상태 보존

    def test_lockin_partner_does_not_set_wave_locked_on_input(self):
        # locked-in 파트너 처리 시 input Shipment.wave_locked는 변하지 않음
        ships = [Shipment('LP', 'PNA-A', '오전', 'tier1_seoul', 1.0,
                         assigned_partner='LP_PTN', wave_locked=False)]
        assign_waves(ships, {'LP_PTN': 'locked-in'}, '2026-05-28', use_sa=False)
        assert ships[0].wave_locked is False
