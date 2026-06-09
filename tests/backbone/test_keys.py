"""키 추출·정규화 순수 함수 테스트."""
from harness.backbone.keys import (
    extract_pt, parse_goods, normalize_goods, is_service, compute_soyoryang,
    resolve_goods_code,
)


class TestExtractPt:
    def test_from_order_part_name(self):
        assert extract_pt("PT4917-아크릴트로피_추상적산출물") == "PT4917"

    def test_from_movement_concat(self):
        assert extract_pt("PT4911-배경지 || PNA50702_심볼 || 좌표") == "PT4911"

    def test_no_pt(self):
        assert extract_pt("배송 다마스") is None

    def test_empty(self):
        assert extract_pt("") is None


class TestParseGoods:
    def test_name_and_qty(self):
        assert parse_goods("심볼아크릴트로피 125") == ("심볼아크릴트로피", 125)

    def test_comma_qty(self):
        assert parse_goods("시그니처 다이어리 1,200") == ("시그니처 다이어리", 1200)

    def test_no_qty(self):
        assert parse_goods("핸디링미니선풍기") == ("핸디링미니선풍기", 0)


class TestNormalizeGoods:
    def test_strip_bracket_index(self):
        assert normalize_goods("브랜디드피규어[4]") == "브랜디드피규어"

    def test_strip_parens(self):
        assert normalize_goods("클리어리유저블컵(스탠다드)") == "클리어리유저블컵"

    def test_strip_underscore_suffix(self):
        assert normalize_goods("핸디링미니선풍기_화이트") == "핸디링미니선풍기"


class TestIsService:
    def test_delivery(self):
        assert is_service("배송 다마스") is True

    def test_unload(self):
        assert is_service("하차서비스_퀵(다마스)") is True

    def test_real_goods(self):
        assert is_service("심볼아크릴트로피") is False


class TestComputeSoyoryang:
    def test_one_to_one(self):
        assert compute_soyoryang(125, 125) == 1.0

    def test_ratio(self):
        assert compute_soyoryang(250, 125) == 2.0

    def test_zero_goods(self):
        assert compute_soyoryang(125, 0) is None

    def test_bad_input(self):
        assert compute_soyoryang(None, 125) is None


class TestResolveGoodsCode:
    def test_direct_code(self):
        assert resolve_goods_code({"굿즈코드 (from sync_itemdb)": "SSSV"}) == ("SSSV", "direct")

    def test_blank_returns_none(self):
        assert resolve_goods_code({}) == (None, "none")

    def test_strips_and_uppercases(self):
        assert resolve_goods_code({"굿즈코드 (from sync_itemdb)": " sssv "}) == ("SSSV", "direct")

    def test_list_value_unwrapped(self):
        # Airtable lookup 필드는 list로 올 수 있음
        assert resolve_goods_code({"굿즈코드 (from sync_itemdb)": ["SBAT"]}) == ("SBAT", "direct")

    def test_empty_list_returns_none(self):
        assert resolve_goods_code({"굿즈코드 (from sync_itemdb)": []}) == (None, "none")
