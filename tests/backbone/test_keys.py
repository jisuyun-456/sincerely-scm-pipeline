"""키 추출·정규화 순수 함수 테스트."""
from harness.backbone.keys import (
    extract_pt, parse_goods, normalize_goods, is_service, compute_soyoryang,
    resolve_goods_code, build_pkg_goods_map, extract_pts, build_mes_crosswalk_rows,
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


class TestResolveGoodsCodePkgFallback:
    PKG = {"PNA50702": "SBAT"}

    def test_direct_wins_over_pkg(self):
        row = {"굿즈코드 (from sync_itemdb)": "SSSV", "project_code": "PNA50702_심볼"}
        assert resolve_goods_code(row, self.PKG) == ("SSSV", "direct")

    def test_blank_falls_back_to_pkg(self):
        assert resolve_goods_code({"project_code": "PNA50702_심볼"}, self.PKG) == ("SBAT", "pkg")

    def test_blank_and_unknown_project_none(self):
        assert resolve_goods_code({"project_code": "PNA99999_없음"}, self.PKG) == (None, "none")

    def test_blank_no_pna_none(self):
        assert resolve_goods_code({"project_code": "기타"}, self.PKG) == (None, "none")

    def test_no_map_backward_compat(self):
        assert resolve_goods_code({}) == (None, "none")


class TestBuildPkgGoodsMap:
    N2C = {"심볼아크릴트로피": "SSSV", "시그니처보조배터리": "SBAT"}

    def test_single_code_project_mapped(self):
        rows = [{"프로젝트 코드 (PK) (from project)": "PNA50702_심볼",
                 "주문 굿즈 리스트 (자동) (from project)": "심볼아크릴트로피 125"}]
        assert build_pkg_goods_map(rows, self.N2C) == {"PNA50702": "SSSV"}

    def test_multi_code_project_excluded(self):
        rows = [{"프로젝트 코드 (PK) (from project)": "PNA1_x",
                 "주문 굿즈 리스트 (자동) (from project)": "심볼아크릴트로피 125, 시그니처보조배터리 30"}]
        assert build_pkg_goods_map(rows, self.N2C) == {}

    def test_service_and_unknown_names_skipped(self):
        rows = [{"프로젝트 코드 (PK) (from project)": "PNA2_y",
                 "주문 굿즈 리스트 (자동) (from project)": "배송 다마스 1, 미지의굿즈 10"}]
        assert build_pkg_goods_map(rows, self.N2C) == {}

    def test_second_source_also_read(self):
        rows = [{"프로젝트 코드 (PK) (from project)": "PNA3_z",
                 "단품 굿즈 품목 및 수량": "심볼아크릴트로피 10"}]
        assert build_pkg_goods_map(rows, self.N2C) == {"PNA3": "SSSV"}

    def test_same_code_multiple_rows_merged(self):
        rows = [{"프로젝트 코드 (PK) (from project)": "PNA4_a",
                 "주문 굿즈 리스트 (자동) (from project)": "심볼아크릴트로피 5"},
                {"프로젝트 코드 (PK) (from project)": "PNA4_a",
                 "주문 굿즈 리스트 (자동) (from project)": "심볼아크릴트로피 5"}]
        assert build_pkg_goods_map(rows, self.N2C) == {"PNA4": "SSSV"}


class TestExtractPts:
    def test_multiple_unique_order_preserved(self):
        assert extract_pts("PT1234 외 PT5678, PT1234 재투입") == ["PT1234", "PT5678"]

    def test_empty_and_none(self):
        assert extract_pts("") == []
        assert extract_pts(None) == []

    def test_short_digits_not_matched(self):
        assert extract_pts("PT99 PT123456") == ["PT123456"]


class TestBuildMesCrosswalkRows:
    def test_part_in_wms(self):
        rows, stats = build_mes_crosswalk_rows(
            {"PT1234"}, {}, set(), {"PT1234"}, set())
        assert rows == [{
            "표준키": "PT1234", "키유형": "파츠", "TMS_견적코드": "",
            "WMS_아이템코드": "PT1234", "MES_파츠코드": "PT1234",
            "매칭방식": "정확", "매칭신뢰도": 1.0, "검증상태": "확정",
            "출처": "mes_crosswalk",
        }]
        assert stats["parts_in_wms"] == 1 and stats["parts_new"] == 1

    def test_part_not_in_wms_unverified(self):
        rows, _ = build_mes_crosswalk_rows({"PT777777"}, {}, set(), set(), set())
        assert rows[0]["WMS_아이템코드"] == "" and rows[0]["검증상태"] == "미검증"
        assert rows[0]["매칭신뢰도"] == 0.5

    def test_existing_key_skipped(self):
        rows, stats = build_mes_crosswalk_rows(
            {"PT1234"}, {"굿즈A": "AB-1"}, {"PT1234", "굿즈A"}, {"PT1234"}, {"ab-1"})
        assert rows == []
        assert stats["parts_already"] == 1 and stats["goods_already"] == 1
        # 해소율은 INSERT 여부와 무관 — 기존 crosswalk 키도 해소로 집계 (재실행 시 rate 안정)
        assert stats["parts_in_wms"] == 1
        assert stats["goods_code_in_tms"] == 1

    def test_goods_code_in_tms(self):
        rows, stats = build_mes_crosswalk_rows(
            set(), {"굿즈A": "ab-1 "}, set(), set(), {"ab-1"})
        assert rows[0]["TMS_견적코드"] == "AB-1"
        assert rows[0]["검증상태"] == "확정" and rows[0]["매칭신뢰도"] == 1.0
        assert stats["goods_code_in_tms"] == 1

    def test_goods_code_not_in_tms_held(self):
        rows, _ = build_mes_crosswalk_rows(set(), {"굿즈B": "ZZ-9"}, set(), set(), set())
        assert rows[0]["검증상태"] == "보류" and rows[0]["매칭방식"] == "수기"

    def test_goods_without_code_skipped(self):
        rows, stats = build_mes_crosswalk_rows(set(), {"굿즈C": ""}, set(), set(), set())
        assert rows == [] and stats["goods_no_code"] == 1
