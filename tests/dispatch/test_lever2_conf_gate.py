"""LEVER2 (2026-06-23, opt-in) — CONF_GATE_MODE 'separate' 시 부분매칭 conf0.7 자동 + 용량 마진.

기본 'product' 는 현행 곱 floor(무변경). 'separate' 전환 시 slot/cbm 분리 게이트 +
effective_cbm 인플레이트(과소추정→과적 방지)로 안전하게 자동화율 상승.
"""
import harness.dispatch.wave_assigner as wa
from harness.dispatch.wave_assigner import (
    CONFIDENCE_FLOOR, Shipment, _effective_cbm, assign_waves_greedy,
)

_AUTONOMY: dict = {}


def _ship(sid, cbm=2.0, cbm_conf=0.7, slot_conf=1.0, slot="오전"):
    return Shipment(sid, "PNA-A", slot, "tier1_seoul", cbm,
                    cbm_confidence=cbm_conf, slot_confidence=slot_conf)


class TestConfGate:
    def test_product_mode_conf07_manual(self, monkeypatch):
        monkeypatch.setattr(wa, "CONF_GATE_MODE", "product")
        plans = assign_waves_greedy([_ship("p1")], _AUTONOMY, "2026-06-23",
                                    confidence_floor=CONFIDENCE_FLOOR)
        assert plans["수동"].count == 1
        assert sum(plans[w].count for w in ("W1", "W2", "W3")) == 0

    def test_separate_mode_conf07_auto(self, monkeypatch):
        monkeypatch.setattr(wa, "CONF_GATE_MODE", "separate")
        plans = assign_waves_greedy([_ship("s1")], _AUTONOMY, "2026-06-23",
                                    confidence_floor=CONFIDENCE_FLOOR)
        assert plans["수동"].count == 0
        assert sum(plans[w].count for w in ("W1", "W2", "W3")) == 1

    def test_separate_mode_low_slot_still_manual(self, monkeypatch):
        monkeypatch.setattr(wa, "CONF_GATE_MODE", "separate")
        # slot_conf 0.7 < SLOT_FLOOR 0.8 → 여전히 수동
        plans = assign_waves_greedy([_ship("s2", cbm_conf=1.0, slot_conf=0.7)],
                                    _AUTONOMY, "2026-06-23", confidence_floor=CONFIDENCE_FLOOR)
        assert plans["수동"].count == 1


class TestEffectiveCbm:
    def test_separate_inflates_low_conf(self, monkeypatch):
        monkeypatch.setattr(wa, "CONF_GATE_MODE", "separate")
        # 7.0/0.7 = 10.0, cap 7.0*1.6=11.2 → 10.0
        assert abs(_effective_cbm(_ship("e1", cbm=7.0, cbm_conf=0.7)) - 10.0) < 1e-9

    def test_separate_caps_inflation(self, monkeypatch):
        monkeypatch.setattr(wa, "CONF_GATE_MODE", "separate")
        # 7.0/0.3 = 23.3 → cap 7.0*1.6 = 11.2
        assert abs(_effective_cbm(_ship("e2", cbm=7.0, cbm_conf=0.3)) - 11.2) < 1e-9

    def test_separate_full_conf_unchanged(self, monkeypatch):
        monkeypatch.setattr(wa, "CONF_GATE_MODE", "separate")
        assert _effective_cbm(_ship("e3", cbm=7.0, cbm_conf=1.0)) == 7.0

    def test_product_mode_no_inflation(self, monkeypatch):
        monkeypatch.setattr(wa, "CONF_GATE_MODE", "product")
        assert _effective_cbm(_ship("e4", cbm=7.0, cbm_conf=0.7)) == 7.0
