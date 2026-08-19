"""NEEDS_REVIEW_SLOT('특정시간 확인') → '수동' 라우팅 회귀 테스트 (2026-08-19).

decide_slot() 이 애매한 시간대에 대해 이 플래그를 반환하도록 확장하면서,
어떤 기사의 preferred_slots 에도 없는 이 슬롯값이 wave_assigner 의 Stage B
필터를 통과하지 못해 candidates=[] 로 spillover 로 새어나가는 버그가 발견됨
(사람 확인 전 자동배차 금지라는 플래그 취지 위반). NULL slot 과 동일하게
Stage B 진입 전에 '수동'으로 분리해야 한다.
"""
from __future__ import annotations

from harness.dispatch.slot_decider import NEEDS_REVIEW_SLOT
from harness.dispatch.wave_assigner import Shipment, assign_waves


def test_needs_review_slot_routes_to_manual_not_spillover():
    ships = [Shipment('R1', 'PNA-A', NEEDS_REVIEW_SLOT, 'tier1_seoul', 1.0,
                      slot_confidence=0.9, cbm_confidence=1.0)]
    plans = assign_waves(ships, {}, '2026-08-19', use_sa=False)
    assert [s.id for s in plans['수동'].shipments] == ['R1']
    for wid in ('W1', 'W2', 'W3', 'spillover_고고엑스', 'spillover_로젠'):
        assert 'R1' not in [s.id for s in plans[wid].shipments]
