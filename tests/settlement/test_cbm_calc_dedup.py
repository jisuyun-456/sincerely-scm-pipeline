"""Task 1.1 — 중복 견적코드 결정론 해소 (_resolve_dup). formula CBM>0 우선 → 큰 qty_per_box → rec_id 사전순."""
from harness.settlement.cbm_calc import _resolve_dup


def test_prefers_formula_cbm_over_zero():
    a = {"rec_id": "r1", "code": "DUP", "cbm_per_box": 0.0, "qty_per_box": 1, "name": "a", "box_type": ""}
    b = {"rec_id": "r2", "code": "DUP", "cbm_per_box": 0.02, "qty_per_box": 5, "name": "b", "box_type": ""}
    assert _resolve_dup(a, b)["rec_id"] == "r2"
    assert _resolve_dup(b, a)["rec_id"] == "r2"  # 순서 무관 (결정론)


def test_tiebreak_larger_qty_per_box():
    a = {"rec_id": "r1", "code": "DUP", "cbm_per_box": 0.02, "qty_per_box": 5, "name": "a", "box_type": ""}
    b = {"rec_id": "r2", "code": "DUP", "cbm_per_box": 0.02, "qty_per_box": 19, "name": "b", "box_type": ""}
    assert _resolve_dup(a, b)["rec_id"] == "r2"
    assert _resolve_dup(b, a)["rec_id"] == "r2"


def test_tiebreak_rec_id_lexicographic():
    a = {"rec_id": "rA", "code": "DUP", "cbm_per_box": 0.02, "qty_per_box": 5, "name": "a", "box_type": ""}
    b = {"rec_id": "rB", "code": "DUP", "cbm_per_box": 0.02, "qty_per_box": 5, "name": "b", "box_type": ""}
    assert _resolve_dup(a, b)["rec_id"] == "rA"
    assert _resolve_dup(b, a)["rec_id"] == "rA"
