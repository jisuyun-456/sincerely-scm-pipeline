"""Tests for capacity constraints (Contract C4)."""
from __future__ import annotations

import pytest

from harness.dispatch.wave_assigner import DRIVER_LIMITS, Shipment, assign_waves


def _build(n, region='tier1_seoul', slot='오전', cbm=1.0, prefix='X'):
    return [Shipment(f'{prefix}{i}', f'PNA-{i}', slot, region, cbm) for i in range(n)]


class TestCapacity:
    """Contract C4 — 자체 기사 capacity 초과 0건."""

    def test_w1_max_cbm(self):
        lim = DRIVER_LIMITS['W1']
        assert lim['max_cbm'] == 4.5
        assert lim['max_count'] == 3

    def test_w2_max_cbm(self):
        lim = DRIVER_LIMITS['W2']
        assert lim['max_cbm'] == 7.616
        assert lim['max_count'] == 6

    def test_w3_max_cbm(self):
        lim = DRIVER_LIMITS['W3']
        assert lim['max_cbm'] == 9.486
        assert lim['max_count'] == 8

    def test_no_wave_exceeds_max_cbm(self):
        # 50건 1 CBM each → 모든 wave capacity 채워야 함 + 초과 0건
        ships = _build(50, region='tier1_seoul', slot='오전', cbm=1.0)
        plans = assign_waves(ships, {}, '2026-05-28', use_sa=False)
        for wid in ('W1', 'W2', 'W3'):
            lim = DRIVER_LIMITS[wid]
            assert plans[wid].total_cbm <= lim['max_cbm'], f'{wid} cbm exceeded'
            assert plans[wid].count <= lim['max_count'], f'{wid} count exceeded'

    def test_no_wave_exceeds_max_count_with_small_cbm(self):
        # 100건 0.1 CBM each → count cap 먼저 도달
        ships = _build(100, region='tier1_seoul', slot='오전', cbm=0.1)
        plans = assign_waves(ships, {}, '2026-05-28', use_sa=False)
        for wid in ('W1', 'W2', 'W3'):
            lim = DRIVER_LIMITS[wid]
            assert plans[wid].count <= lim['max_count']

    def test_oversize_overflow_to_spillover(self):
        # 단일 5.0 CBM (W1 4.5 초과) → W2 또는 W3 또는 spillover
        ships = [Shipment('XL', 'PNA-Z', '오전', 'tier5_provincial', 5.0)]
        plans = assign_waves(ships, {}, '2026-05-28', use_sa=False)
        # 지방 + 5.0 CBM → W3 OK (max 9.486) 또는 spillover
        placed = sum([[s.id for s in plans[wid].shipments] for wid in plans], [])
        assert 'XL' in placed
