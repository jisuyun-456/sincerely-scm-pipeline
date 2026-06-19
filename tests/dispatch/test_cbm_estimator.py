"""Tests for harness.dispatch.cbm_estimator.

Covers C2 (parse accuracy) and C3·C4 sanity via inline cases derived from
the 30-shipment baseline + parse_v2 verification (see
_AutoResearch/SCM/outputs/cbm-preflight-sample30.md).

Golden 100 fixture (plan Task 6 Step 1+2) deferred — requires manual user
labeling. The inline cases below lock in the verified parser behavior.
"""
from __future__ import annotations

import pytest

from harness.dispatch.cbm_estimator import (
    build_kit_cbm_lookup,
    estimate_shipment_cbm,
    estimate_shipment_cbm_deterministic,
    parse_product_lines_v2,
)


# ──────────────────────── estimate_shipment_cbm_deterministic ────────────────

_DET_LOOKUP = {
    "sbat": {"rec_id": "r", "name": "심볼", "code": "SBAT",
             "box_type": "", "qty_per_box": 19, "cbm_per_box": 0.0201},
}


class TestEstimateDeterministic:
    def test_single_shipment_deterministic(self):
        # 1출하 프로젝트, order=SBAT×38 → ceil(38/19)*0.0201 = 2*0.0201 = 0.0402
        r = estimate_shipment_cbm_deterministic(
            "PNA1", {"PNA1": [("SBAT", 38)]}, _DET_LOOKUP, {"PNA1": 1})
        assert abs(r["estimated_cbm"] - 0.0402) < 1e-6
        assert r["confidence"] == 1.0
        assert r["mode"] == "deterministic"
        assert r["matched"] == ["SBAT"] and r["unmatched"] == []

    def test_multi_shipment_partial_skip(self):
        r = estimate_shipment_cbm_deterministic(
            "PNA2", {"PNA2": [("SBAT", 38)]}, _DET_LOOKUP, {"PNA2": 3})
        assert r["mode"] == "partial_skip"
        assert r["confidence"] == 0.0
        assert r["estimated_cbm"] == 0.0

    def test_missing_code_reports_unmatched(self):
        r = estimate_shipment_cbm_deterministic(
            "PNA3", {"PNA3": [("NOPE", 10)]}, _DET_LOOKUP, {"PNA3": 1})
        assert "NOPE" in r["unmatched"]
        assert r["confidence"] == 0.0

    def test_no_order_lines(self):
        r = estimate_shipment_cbm_deterministic(
            "PNA4", {}, _DET_LOOKUP, {"PNA4": 1})
        assert r["mode"] == "no_order"
        assert r["estimated_cbm"] == 0.0

    def test_partial_match_confidence_0_7(self):
        # 한 코드 매칭, 한 코드 누락 → conf 0.7
        r = estimate_shipment_cbm_deterministic(
            "PNA5", {"PNA5": [("SBAT", 19), ("NOPE", 5)]}, _DET_LOOKUP, {"PNA5": 1})
        assert r["confidence"] == 0.7
        assert r["matched"] == ["SBAT"] and r["unmatched"] == ["NOPE"]
        assert abs(r["estimated_cbm"] - 0.0201) < 1e-6  # ceil(19/19)*0.0201


# ──────────────────────────── kit-CBM 폴백 (P2b) ─────────────────────────────

_BOM_FIELDS = [
    {"프로젝트코드": "PNA100_x", "모품목_굿즈명": "키트A", "소품목_PT": "PT1111", "소요량_개당": 2},
    {"프로젝트코드": "PNA100_x", "모품목_굿즈명": "키트A", "소품목_PT": "PT2222", "소요량_개당": 1},
    {"프로젝트코드": "PNA100_x", "모품목_굿즈명": "불완전", "소품목_PT": "PT3333", "소요량_개당": 1},
    {"프로젝트코드": "PNA100_x", "모품목_굿즈명": "소요량없음", "소품목_PT": "PT1111", "소요량_개당": None},
]
_ITEM_MASTER = {
    "PT1111": (0.001, "TMS_Product"),
    "PT2222": (0.002, "박스유도"),
    # PT3333: CBM 없음 → '불완전' 그룹 제외
}
_NAME2CODE = {"키트A": "KIT-A", "불완전": "X-1", "소요량없음": "X-2"}


class TestBuildKitCbmLookup:
    def test_complete_kit_only(self):
        kit = build_kit_cbm_lookup(_BOM_FIELDS, _ITEM_MASTER, _NAME2CODE)
        assert set(kit) == {("PNA100", "KIT-A")}
        cbm, conf = kit[("PNA100", "KIT-A")]
        assert abs(cbm - (2 * 0.001 + 1 * 0.002)) < 1e-9
        # min(1.0, 0.9) * 0.9 = 0.81 → 상한 0.8
        assert conf == 0.8

    def test_confidence_below_cap(self):
        bom = [{"프로젝트코드": "PNA200", "모품목_굿즈명": "g", "소품목_PT": "PT1", "소요량_개당": 1}]
        kit = build_kit_cbm_lookup(bom, {"PT1": (0.005, "수기")}, {"g": "G-1"})
        assert kit[("PNA200", "G-1")][1] == 0.63  # 0.7 * 0.9

    def test_unknown_goods_code_skipped(self):
        bom = [{"프로젝트코드": "PNA300", "모품목_굿즈명": "미등록굿즈", "소품목_PT": "PT1", "소요량_개당": 1}]
        assert build_kit_cbm_lookup(bom, {"PT1": (0.005, "TMS_Product")}, {}) == {}

    def test_part_cbm_backfill_sources_conf(self):
        # P3' part_cbm 백필 출처 — 치수파싱 0.55·QC버킷 0.40이 kit conf에 반영
        bom = [{"프로젝트코드": "PNA400", "모품목_굿즈명": "g", "소품목_PT": "PT1", "소요량_개당": 1}]
        kit = build_kit_cbm_lookup(bom, {"PT1": (0.005, "치수파싱")}, {"g": "G-1"})
        assert kit[("PNA400", "G-1")][1] == 0.5   # 0.55 * 0.9
        kit = build_kit_cbm_lookup(bom, {"PT1": (0.005, "QC버킷")}, {"g": "G-1"})
        assert kit[("PNA400", "G-1")][1] == 0.36  # 0.40 * 0.9


_DET_KIT_LOOKUP = {("PNA100", "KIT-A"): (0.004, 0.8)}


class TestDeterministicKitFallback:
    def test_kit_fallback_applied_when_product_missing(self):
        res = estimate_shipment_cbm_deterministic(
            "PNA100", {"PNA100": [("KIT-A", 10)]}, {}, {"PNA100": 1},
            kit_lookup=_DET_KIT_LOOKUP)
        assert res["estimated_cbm"] == 0.04   # 10 * 0.004 (박스 패킹 없음)
        assert res["confidence"] == 0.8
        assert res["kit_used"] == ["KIT-A"]

    def test_product_direct_wins_over_kit(self):
        lookup = {"kit-a": {"rec_id": "r", "name": "키트A", "code": "KIT-A",
                            "box_type": "", "qty_per_box": 10, "cbm_per_box": 0.05}}
        res = estimate_shipment_cbm_deterministic(
            "PNA100", {"PNA100": [("KIT-A", 10)]}, lookup, {"PNA100": 1},
            kit_lookup=_DET_KIT_LOOKUP)
        assert res["estimated_cbm"] == 0.05   # 이중계상 가드: direct 우선
        assert res["kit_used"] == [] and res["confidence"] == 1.0

    def test_backward_compat_without_kit_lookup(self):
        res = estimate_shipment_cbm_deterministic(
            "PNA100", {"PNA100": [("KIT-A", 10)]}, {}, {"PNA100": 1})
        assert res["estimated_cbm"] == 0.0 and res["unmatched"] == ["KIT-A"]


# ───────────────────── 비물리 서비스라인 제외 (confidence 보정) ─────────────────────

class TestDeterministicServiceExclusion:
    """비물리 서비스라인(SSSV 신시어리서비스·CSPR 고객입고물품)은 matched/unmatched
    confidence 계산에서 제외 — 실물이 전부 매칭이고 잔여 unmatched가 서비스라인뿐이면
    conf 1.0. 서비스라인은 박스/CBM이 없으므로 estimated_cbm에도 미가산."""

    def test_service_line_excluded_yields_full_confidence(self):
        # SBAT(실물) 매칭 + SSSV(서비스) → 서비스 제외 시 conf 1.0 (기존엔 0.7)
        r = estimate_shipment_cbm_deterministic(
            "PNA1", {"PNA1": [("SBAT", 38), ("SSSV", 100)]}, _DET_LOOKUP, {"PNA1": 1},
            service_codes={"SSSV", "CSPR"})
        assert r["confidence"] == 1.0
        assert r["matched"] == ["SBAT"]
        assert "SSSV" not in r["unmatched"]
        assert abs(r["estimated_cbm"] - 0.0402) < 1e-6   # 서비스라인 CBM 미가산

    def test_service_exclusion_case_insensitive(self):
        r = estimate_shipment_cbm_deterministic(
            "PNA1", {"PNA1": [("SBAT", 38), ("sssv", 100)]}, _DET_LOOKUP, {"PNA1": 1},
            service_codes={"SSSV"})
        assert r["confidence"] == 1.0
        assert [c for c in r["unmatched"] if c.upper() == "SSSV"] == []

    def test_real_unmatched_still_caps_confidence(self):
        # 서비스 제외해도 실물 누락(NOPE)이 남으면 conf 0.7 유지 (정직)
        r = estimate_shipment_cbm_deterministic(
            "PNA1", {"PNA1": [("SBAT", 19), ("SSSV", 100), ("NOPE", 5)]},
            _DET_LOOKUP, {"PNA1": 1}, service_codes={"SSSV"})
        assert r["confidence"] == 0.7
        assert r["unmatched"] == ["NOPE"]

    def test_all_service_order_zero(self):
        # 전부 서비스라인 → 물리 CBM 없음 → est 0, conf 0 (안전하게 수동)
        r = estimate_shipment_cbm_deterministic(
            "PNA1", {"PNA1": [("SSSV", 100)]}, _DET_LOOKUP, {"PNA1": 1},
            service_codes={"SSSV"})
        assert r["estimated_cbm"] == 0.0
        assert r["confidence"] == 0.0
        assert r["matched"] == [] and r["unmatched"] == []

    def test_backward_compat_no_service_codes(self):
        # service_codes 미전달 → 기존 동작 유지 (SSSV가 unmatched → conf 0.7)
        r = estimate_shipment_cbm_deterministic(
            "PNA1", {"PNA1": [("SBAT", 38), ("SSSV", 100)]}, _DET_LOOKUP, {"PNA1": 1})
        assert r["confidence"] == 0.7
        assert "SSSV" in r["unmatched"]


# ────────────────────────── parse_product_lines_v2 ──────────────────────────

class TestParseV1Compatibility:
    """C2 regression: parse_v2 must preserve existing parse_v1 patterns."""

    def test_times_pattern(self):
        assert parse_product_lines_v2("굿이너프 비치타월×40") == [("굿이너프 비치타월", 40, 0)]

    def test_trailing_space_qty(self):
        assert parse_product_lines_v2("Solid G형 L 20") == [("Solid G형 L", 20, 0)]

    def test_unit_suffix(self):
        assert parse_product_lines_v2("Solid G형 L 20개") == [("Solid G형 L", 20, 0)]

    def test_comma_split(self):
        result = parse_product_lines_v2("굿이너프 비치타월×40, Solid G형 L 20개")
        assert result == [("굿이너프 비치타월", 40, 0), ("Solid G형 L", 20, 0)]

    def test_empty_input(self):
        assert parse_product_lines_v2("") == []

    def test_no_qty(self):
        assert parse_product_lines_v2("단일 품목명") == [("단일 품목명", 0, 0)]


class TestParseThousandSeparator:
    """C2: '1,000개' must not split to '000개' fragments."""

    def test_thousand_separator_single(self):
        result = parse_product_lines_v2("굿이너프 비치타월 1,000개")
        assert result == [("굿이너프 비치타월", 1000, 0)]

    def test_thousand_separator_multiple_products(self):
        # SC00028225 baseline failure case
        text = "핸디링미니선풍기 2,500개 페이퍼샤쉐[1] 1,000개"
        result = parse_product_lines_v2(text)
        assert len(result) == 2
        assert result[0] == ("핸디링미니선풍기", 2500, 0)
        assert result[1] == ("페이퍼샤쉐", 1000, 0)


class TestParseExtraPattern:
    """C2: 'N+M' / 'N+여분 M' → (qty=N+M, extra=M)."""

    def test_extra_simple(self):
        assert parse_product_lines_v2("티셔츠 100+2") == [("티셔츠", 102, 2)]

    def test_extra_with_여분_word(self):
        assert parse_product_lines_v2("티셔츠 100+여분 5") == [("티셔츠", 105, 5)]

    def test_extra_ratio_sanity(self):
        """extra > 20% of qty is suspicious — reset to 0."""
        # 100+50 → 50/100 = 50% → reset extra=0, qty stays at 100 (after EXTRA strip)
        result = parse_product_lines_v2("티셔츠 100+50")
        assert result == [("티셔츠", 100, 0)]


class TestParseNoWhitespaceQty:
    """C2: Korean/Latin char immediately followed by digits+개|EA."""

    def test_no_whitespace_korean(self):
        assert parse_product_lines_v2("에코컵(커스텀박스)3000개") == [("에코컵(커스텀박스)", 3000, 0)]


class TestParseMultiProductNoDelimiter:
    """C2: 'product1 qty1 product2 qty2' without explicit delimiter."""

    def test_bare_qty_split(self):
        # SC00028497 baseline case
        text = "메시지 캐리어 파우치 [1] 200 메시지 캐리어 파우치 [2] 200 스펙트럼 컬러펜 400"
        result = parse_product_lines_v2(text)
        assert len(result) == 3
        # [N] notation stripped, all share same product name
        assert result[0] == ("메시지 캐리어 파우치", 200, 0)
        assert result[1] == ("메시지 캐리어 파우치", 200, 0)
        assert result[2] == ("스펙트럼 컬러펜", 400, 0)

    def test_unit_split_after_qty_unit(self):
        text = "굿이너프 비치타월 40개 Solid G형 L 20개"
        result = parse_product_lines_v2(text)
        assert len(result) == 2
        assert result[0] == ("굿이너프 비치타월", 40, 0)
        assert result[1] == ("Solid G형 L", 20, 0)


class TestParseBracketNotation:
    """C2: '[1]', '[2]' index markers stripped from product name."""

    def test_bracket_notation_stripped(self):
        assert parse_product_lines_v2("페이퍼샤쉐[1] 100") == [("페이퍼샤쉐", 100, 0)]

    def test_bracket_with_space(self):
        assert parse_product_lines_v2("페이퍼샤쉐 [1] 100") == [("페이퍼샤쉐", 100, 0)]


class TestParseRegressionCombined:
    """C2: combined patterns from baseline plan §3.4."""

    def test_x_pattern_with_extra_plus_comma_split(self):
        result = parse_product_lines_v2("굿이너프 비치타월×40+여분 5, Solid G형 L 20개")
        assert result[0] == ("굿이너프 비치타월", 45, 5)
        assert result[1] == ("Solid G형 L", 20, 0)


# ────────────────────────── estimate_shipment_cbm ──────────────────────────

LOOKUP_FIXTURE = {
    "굿이너프 비치타월": {
        "rec_id": "recA", "name": "굿이너프 비치타월", "code": "TWLB",
        "box_type": "대형", "qty_per_box": 40, "cbm_per_box": 0.1066,
    },
    "twlb": {
        "rec_id": "recA", "name": "굿이너프 비치타월", "code": "TWLB",
        "box_type": "대형", "qty_per_box": 40, "cbm_per_box": 0.1066,
    },
    "solid g형 l": {
        "rec_id": "recB", "name": "Solid G형 L", "code": "SGL",
        "box_type": "중대형", "qty_per_box": 20, "cbm_per_box": 0.0493,
    },
}


class TestEstimateBranching:
    """C4 time-branching: 실측 / 임가공_후 / 임가공_전 / no_text."""

    def test_branch_실측_when_total_cbm_present(self):
        ship = {"fields": {"Total_CBM": 5.123}}
        result = estimate_shipment_cbm(ship, LOOKUP_FIXTURE)
        assert result["mode"] == "실측"
        assert result["confidence"] == 1.0
        assert result["estimated_cbm"] == 5.123

    def test_branch_임가공_후_when_post_text_present(self):
        ship = {"fields": {"Total_CBM": 0, "최종 출고 품목 및 수량": "굿이너프 비치타월 40개"}}
        result = estimate_shipment_cbm(ship, LOOKUP_FIXTURE)
        assert result["mode"] == "임가공_후_추정"

    def test_branch_임가공_전_when_only_pre_text(self):
        ship = {"fields": {"Total_CBM": 0, "최종 출하 품목": "굿이너프 비치타월 40개"}}
        result = estimate_shipment_cbm(ship, LOOKUP_FIXTURE)
        assert result["mode"] == "임가공_전_추정"

    def test_no_text_returns_zero_confidence(self):
        ship = {"fields": {"Total_CBM": 0}}
        result = estimate_shipment_cbm(ship, LOOKUP_FIXTURE)
        assert result["mode"] == "no_text"
        assert result["confidence"] == 0.0
        assert result["estimated_cbm"] == 0.0


class TestEstimateCalculation:
    """C3: estimated_cbm computation via n_boxes ceil × cbm_per_box."""

    def test_single_line_exact_box_count(self):
        # 40 / 40 qty_per_box = 1 box × 0.1066 = 0.1066
        ship = {"fields": {"최종 출하 품목": "굿이너프 비치타월 40개"}}
        result = estimate_shipment_cbm(ship, LOOKUP_FIXTURE)
        assert result["estimated_cbm"] == pytest.approx(0.1066, abs=1e-4)
        assert result["confidence"] == 1.0
        assert len(result["matched"]) == 1
        assert result["matched"][0]["n_boxes"] == 1

    def test_single_line_partial_box_ceil(self):
        # 50 / 40 = 1.25 → ceil = 2 boxes × 0.1066 = 0.2132
        ship = {"fields": {"최종 출하 품목": "굿이너프 비치타월 50개"}}
        result = estimate_shipment_cbm(ship, LOOKUP_FIXTURE)
        assert result["estimated_cbm"] == pytest.approx(0.2132, abs=1e-4)

    def test_multi_line_aggregation(self):
        # 40개 ×0.1066 + 20개 ×0.0493 = 0.1559
        ship = {"fields": {"최종 출하 품목": "굿이너프 비치타월 40개, Solid G형 L 20개"}}
        result = estimate_shipment_cbm(ship, LOOKUP_FIXTURE)
        assert result["estimated_cbm"] == pytest.approx(0.1559, abs=1e-4)
        assert result["confidence"] == 1.0
        assert len(result["matched"]) == 2

    def test_unmatched_line_drops_confidence(self):
        ship = {"fields": {"최종 출하 품목": "굿이너프 비치타월 40개, 미등록제품 100개"}}
        result = estimate_shipment_cbm(ship, LOOKUP_FIXTURE)
        # 1 of 2 matched
        assert result["confidence"] == 0.5
        assert "미등록제품" in result["unmatched"]


class TestEstimateEdgeCases:
    def test_invalid_total_cbm_string_defaults_to_zero(self):
        # Robustness: bad input shouldn't crash
        ship = {"fields": {"Total_CBM": "not_a_number",
                           "최종 출하 품목": "굿이너프 비치타월 40개"}}
        result = estimate_shipment_cbm(ship, LOOKUP_FIXTURE)
        assert result["mode"] == "임가공_전_추정"
        assert result["estimated_cbm"] > 0

    def test_fields_dict_directly_accepted(self):
        # Caller may pass fields dict without 'fields' wrapper
        fields = {"Total_CBM": 0, "최종 출하 품목": "굿이너프 비치타월 40개"}
        result = estimate_shipment_cbm(fields, LOOKUP_FIXTURE)
        assert result["estimated_cbm"] > 0
