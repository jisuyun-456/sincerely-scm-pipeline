"""공백 무시 매칭 회귀 테스트 — '스펙트럼컬러펜'(붙임) ↔ '스펙트럼 컬러펜'(띄움).

중복 Product 행 제거 후 fuzzy fill이 떨어진 문제(붙임/띄움 철자 변형이
exact 매칭 대상 역할을 하고 있었음)를 space-insensitive alias로 회복.
"""
from unittest.mock import patch

from harness.settlement.cbm_calc import load_product_lookup, match_product


def test_match_product_space_insensitive():
    """붙임 텍스트가 띄움 Product명(+stripped alias)에 exact 매칭돼야 한다."""
    e = {"rec_id": "recX", "name": "스펙트럼 컬러펜", "code": "SPCP",
         "box_type": "극소형", "qty_per_box": 100, "cbm_per_box": 0.0098}
    lookup = {"스펙트럼 컬러펜": e, "spcp": e, "스펙트럼컬러펜": e}  # load_product_lookup 산출 흉내
    k, ent, score = match_product("스펙트럼컬러펜", lookup)
    assert ent is not None and ent["code"] == "SPCP" and score == 1.0
    # 반대 방향(띄움 쿼리 vs 붙임 alias)도
    k2, ent2, sc2 = match_product("스펙트럼 컬러펜", {"스펙트럼컬러펜": e})
    assert ent2 is not None and sc2 == 1.0


def test_load_product_lookup_adds_stripped_alias():
    """load_product_lookup이 공백제거 alias 키를 추가한다 (실제 name/code는 미덮음)."""
    recs = [{"id": "recX", "fields": {
        "fldx01uKEnCd0J0nP": "스펙트럼 컬러펜", "fldtpUf2UVooLcxwd": "SPCP",
        "fldqGM1lw2TUpZdKW": "극소형", "fldENIdfxbVn8YnPI": 100,
        "fldSBWylTZwGf1aEh": 0.0098}}]

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"records": recs}

    with patch("harness.settlement.cbm_calc.requests.get", return_value=FakeResp()):
        lk = load_product_lookup({"Authorization": "fake"})
    assert "스펙트럼 컬러펜" in lk          # 원본 name 키
    assert "spcp" in lk                     # code 키
    assert "스펙트럼컬러펜" in lk            # stripped alias (신규)
    assert lk["스펙트럼컬러펜"]["code"] == "SPCP"
