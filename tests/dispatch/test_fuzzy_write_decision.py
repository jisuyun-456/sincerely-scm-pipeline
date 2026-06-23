"""A-2 (2026-06-22) — per-shipment 퍼지 추정 PATCH 결정.

결정론 실패(다차출하·no_order·unmatched) shipment 의 CBM 공백을 per-shipment 텍스트 추정으로
메우되, confidence 를 자동배차 floor(0.8) 미만으로 cap 해 수동 검토를 유지한다.
"""
from harness.dispatch.cbm_estimator import (
    FUZZY_CONF_CAP, FUZZY_MIN_CONF, fuzzy_write_decision,
)


def _fz(est, conf):
    return {"estimated_cbm": est, "confidence": conf}


def test_full_match_is_capped_below_floor():
    # 완전매칭(conf 1.0)이어도 0.7로 cap → 자동배차 안 됨(수동 유지)
    dec = fuzzy_write_decision(_fz(2.5, 1.0), cur_est=0.0, cur_conf=0.0)
    assert dec == (2.5, FUZZY_CONF_CAP)
    assert dec[1] < 0.8


def test_partial_match_keeps_own_conf():
    dec = fuzzy_write_decision(_fz(1.2, 0.6), cur_est=0.0, cur_conf=0.0)
    assert dec == (1.2, 0.6)


def test_below_min_conf_not_written():
    assert fuzzy_write_decision(_fz(1.0, FUZZY_MIN_CONF - 0.01), 0.0, 0.0) is None


def test_zero_est_not_written():
    assert fuzzy_write_decision(_fz(0.0, 1.0), 0.0, 0.0) is None


def test_idempotent_no_change_skips():
    # 이미 동일 est(2.5)+capped conf(0.7)면 재PATCH 안 함
    assert fuzzy_write_decision(_fz(2.5, 1.0), cur_est=2.5, cur_conf=0.7) is None


def test_value_change_triggers_write():
    dec = fuzzy_write_decision(_fz(3.0, 1.0), cur_est=2.5, cur_conf=0.7)
    assert dec == (3.0, 0.7)
