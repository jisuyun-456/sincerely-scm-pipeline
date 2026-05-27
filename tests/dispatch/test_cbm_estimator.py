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
    estimate_shipment_cbm,
    parse_product_lines_v2,
)


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
