"""Tests for SA local search (P3.5 Decision 4 — wave_assigner.refine_with_sa)."""
from __future__ import annotations

import random

import pytest

from harness.dispatch.wave_assigner import (
    DRIVER_LIMITS,
    Shipment,
    _score,
    assign_waves,
    assign_waves_greedy,
    refine_with_sa,
)


def _build_ships(n=30, seed=11):
    rng = random.Random(seed)
    regions = ['tier1_seoul', 'tier2_이장훈_gyeonggi', 'tier3_gyeonggi_etc',
               'tier4_incheon', 'tier5_provincial']
    slots = ['오전', '무관', '오후 1 (오후 2시 - 4시)']
    return [
        Shipment(
            id=f'B{i}',
            project_code=f'PNA-{rng.randint(1, 12)}',
            slot=rng.choices(slots, weights=[0.5, 0.4, 0.1])[0],
            region=rng.choices(regions, weights=[0.45, 0.15, 0.15, 0.10, 0.15])[0],
            cbm=round(rng.uniform(0.3, 3.0), 2),
        ) for i in range(n)
    ]


class TestSAConvergence:
    def test_sa_never_worsens_score(self):
        # SA는 best 추적하므로 결과 score >= greedy score
        ships = _build_ships(50, seed=11)
        g = assign_waves(ships, {}, '2026-05-28', use_sa=False)
        sa = assign_waves(ships, {}, '2026-05-28', use_sa=True, sa_iter=1000, sa_seed=42)
        assert _score(sa) >= _score(g) - 1e-6

    def test_sa_deterministic_with_seed(self):
        ships = _build_ships(50, seed=11)
        a = assign_waves(ships, {}, '2026-05-28', use_sa=True, sa_iter=500, sa_seed=42)
        b = assign_waves(ships, {}, '2026-05-28', use_sa=True, sa_iter=500, sa_seed=42)
        for wid in a:
            assert [s.id for s in a[wid].shipments] == [s.id for s in b[wid].shipments]

    def test_sa_no_capacity_violation(self):
        ships = _build_ships(80, seed=23)
        sa = assign_waves(ships, {}, '2026-05-28', use_sa=True, sa_iter=1500, sa_seed=42)
        for wid in ('W1', 'W2', 'W3'):
            lim = DRIVER_LIMITS[wid]
            assert sa[wid].total_cbm <= lim['max_cbm'] + 1e-6
            assert sa[wid].count <= lim['max_count']

    def test_sa_no_region_violation(self):
        ships = _build_ships(60, seed=7)
        sa = assign_waves(ships, {}, '2026-05-28', use_sa=True, sa_iter=1000, sa_seed=42)
        for wid in ('W1', 'W2', 'W3'):
            lim = DRIVER_LIMITS[wid]
            for s in sa[wid].shipments:
                assert s.region in lim['regions'], f'{wid}:{s.id} region={s.region}'

    def test_sa_w1_only_morning(self):
        ships = _build_ships(60, seed=7)
        sa = assign_waves(ships, {}, '2026-05-28', use_sa=True, sa_iter=1000, sa_seed=42)
        for s in sa['W1'].shipments:
            assert s.slot == '오전'

    def test_sa_preserves_locked_in_wave(self):
        ships = [
            Shipment('L1', 'PNA-A', '오전', 'tier1_seoul', 1.0, assigned_partner='LP'),
            Shipment('N1', 'PNA-B', '오전', 'tier1_seoul', 2.0),
        ]
        sa = assign_waves(ships, {'LP': 'locked-in'}, '2026-05-28', use_sa=True, sa_iter=300, sa_seed=42)
        assert 'L1' in [s.id for s in sa['locked-in'].shipments]

    def test_sa_preserves_manual_wave_for_locked(self):
        ships = [Shipment('LK', 'PNA-A', '오전', 'tier1_seoul', 1.0, wave_locked=True)]
        sa = assign_waves(ships, {}, '2026-05-28', use_sa=True, sa_iter=300, sa_seed=42)
        assert 'LK' in [s.id for s in sa['수동'].shipments]

    def test_sa_zero_iter_equals_greedy(self):
        ships = _build_ships(30, seed=11)
        g = assign_waves(ships, {}, '2026-05-28', use_sa=False)
        sa0 = assign_waves(ships, {}, '2026-05-28', use_sa=True, sa_iter=0, sa_seed=42)
        # sa_iter=0 → SA loop 비실행 → greedy 결과와 동일
        for wid in g:
            assert sorted(s.id for s in g[wid].shipments) == sorted(s.id for s in sa0[wid].shipments)

    def test_sa_empty_input(self):
        sa = assign_waves([], {}, '2026-05-28', use_sa=True, sa_iter=100, sa_seed=42)
        for wid in sa:
            assert sa[wid].count == 0

    def test_sa_seed_variation_changes_path(self):
        # 다른 seed → 다른 결과 가능 (확률적 알고리즘 검증)
        ships = _build_ships(60, seed=23)
        a = assign_waves(ships, {}, '2026-05-28', use_sa=True, sa_iter=2000, sa_seed=1)
        b = assign_waves(ships, {}, '2026-05-28', use_sa=True, sa_iter=2000, sa_seed=999)
        # 두 결과 모두 valid (capacity·region OK) — 동일성 보장 X
        for plans in (a, b):
            for wid in ('W1', 'W2', 'W3'):
                assert plans[wid].total_cbm <= DRIVER_LIMITS[wid]['max_cbm'] + 1e-6
