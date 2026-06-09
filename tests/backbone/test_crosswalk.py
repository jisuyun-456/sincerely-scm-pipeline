"""Crosswalk 2-tier 빌드 테스트 (순수 변환)."""
from harness.backbone.crosswalk import build_crosswalk


def _lookup():
    # match_product 형식: name.lower() / code.lower() → entry
    e = {"rec_id": "r1", "name": "심볼아크릴트로피", "code": "SBAT",
         "box_type": "중형", "qty_per_box": 6, "cbm_per_box": 0.02}
    return {"심볼아크릴트로피": e, "sbat": e}


def test_tier_a_goods_match():
    rows = build_crosswalk(goods_names={"심볼아크릴트로피"}, part_codes=set(),
                           product_lookup=_lookup())
    a = [r for r in rows if r["키유형"] == "굿즈"][0]
    assert a["TMS_견적코드"] == "SBAT"
    assert a["매칭방식"] == "정확"
    assert a["매칭신뢰도"] == 1.0


def test_tier_a_unmatched_goods():
    rows = build_crosswalk(goods_names={"없는제품XYZ"}, part_codes=set(),
                           product_lookup=_lookup())
    a = [r for r in rows if r["키유형"] == "굿즈"][0]
    assert a["TMS_견적코드"] == ""
    assert a["검증상태"] == "보류"


def test_tier_b_part_identity():
    rows = build_crosswalk(goods_names=set(), part_codes={"PT4900"},
                           product_lookup=_lookup())
    b = [r for r in rows if r["키유형"] == "파츠"][0]
    assert b["표준키"] == "PT4900"
    assert b["WMS_아이템코드"] == "PT4900"
