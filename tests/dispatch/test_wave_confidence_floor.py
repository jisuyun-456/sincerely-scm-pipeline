"""Task 1.7 — wave 자동배차 신뢰도 floor 0.8.

slot_confidence * cbm_confidence < CONFIDENCE_FLOOR → '수동'(사용자 검토).
이상이면 정상 BFD 배차. 결정론 CBM(conf 1.0) shipment만 자동 점등하도록 보장.
"""
from harness.dispatch.wave_assigner import (
    Shipment, assign_waves_greedy, CONFIDENCE_FLOOR,
)

_AUTONOMY: dict = {}


def _ship(sid, cbm_conf, slot_conf):
    return Shipment(sid, "PNA-A", "오전", "tier1_seoul", 1.0,
                    cbm_confidence=cbm_conf, slot_confidence=slot_conf)


class TestWaveConfidenceFloor:
    def test_floor_value_is_0_8(self):
        assert CONFIDENCE_FLOOR == 0.8

    def test_low_confidence_routes_to_manual(self):
        # 0.7 * 0.8 = 0.56 < 0.8 → 수동
        plans = assign_waves_greedy([_ship("L1", 0.7, 0.8)], _AUTONOMY, "2026-05-28", confidence_floor=CONFIDENCE_FLOOR)
        assert plans["수동"].count == 1
        assert sum(plans[w].count for w in ("W1", "W2", "W3")) == 0

    def test_high_confidence_assigned_to_wave(self):
        # 1.0 * 1.0 = 1.0 ≥ 0.8 → 정상 배차
        plans = assign_waves_greedy([_ship("H1", 1.0, 1.0)], _AUTONOMY, "2026-05-28", confidence_floor=CONFIDENCE_FLOOR)
        assert plans["수동"].count == 0
        assert sum(plans[w].count for w in ("W1", "W2", "W3")) == 1

    def test_exactly_at_floor_is_assigned(self):
        # 1.0 * 0.8 = 0.8, strict < 이므로 통과 → 정상 배차
        plans = assign_waves_greedy([_ship("E1", 1.0, 0.8)], _AUTONOMY, "2026-05-28", confidence_floor=CONFIDENCE_FLOOR)
        assert plans["수동"].count == 0

    def test_floor_off_by_default_low_conf_still_assigned(self):
        # floor 미지정(기본 0.0=off) → 저신뢰여도 정상 배차 (단위테스트·baseline 보존)
        plans = assign_waves_greedy([_ship("D1", 0.7, 0.8)], _AUTONOMY, "2026-05-28")
        assert plans["수동"].count == 0
        assert sum(plans[w].count for w in ("W1", "W2", "W3")) == 1
