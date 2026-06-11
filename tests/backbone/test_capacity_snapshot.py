"""capacity_snapshot 테스트 (P4) — 윈도우/커버리지/트랙분리/append idempotency."""
from datetime import date

from harness.backbone.capacity_snapshot import (
    build_inbound_scheduled,
    build_outbound_forward,
    normalize_center,
)

TODAY = date(2026, 6, 11)


def _ship(d, cbm):
    return {"ship_date": d, "cbm_valid": cbm}


def _mov(d, cbm, src="mov", center="에이원지식산업센터"):
    return {"exp_date": d, "cbm": cbm, "spec_src": src, "center": center}


class TestOutboundForward:
    def test_window_includes_today_through_horizon(self):
        rows = [_ship("2026-06-11", 1.0), _ship("2026-06-25", 2.0),
                _ship("2026-06-26", 4.0)]  # +15d → 제외
        out = build_outbound_forward(rows, TODAY, horizon_days=14)
        assert out["forward_by_date"] == {"2026-06-11": 1.0, "2026-06-25": 2.0}
        assert out["forward_total_cbm"] == 3.0
        assert out["n_shipments_window"] == 2

    def test_past_and_blank_dates_excluded(self):
        rows = [_ship("2026-06-10", 1.0), _ship(None, 5.0), _ship("", 5.0)]
        out = build_outbound_forward(rows, TODAY)
        assert out["n_shipments_window"] == 0
        assert out["forward_total_cbm"] == 0.0

    def test_coverage_counts_zero_cbm_rows_in_denominator(self):
        rows = [_ship("2026-06-12", 2.0), _ship("2026-06-12", 0)]
        out = build_outbound_forward(rows, TODAY)
        assert out["n_shipments_window"] == 2
        assert out["n_with_cbm"] == 1
        assert out["coverage_pct"] == 50.0

    def test_same_date_accumulates(self):
        rows = [_ship("2026-06-12", 1.5), _ship("2026-06-12", 2.5)]
        out = build_outbound_forward(rows, TODAY)
        assert out["forward_by_date"] == {"2026-06-12": 4.0}

    def test_empty_input_no_zerodivision(self):
        out = build_outbound_forward([], TODAY)
        assert out["coverage_pct"] == 0.0
        assert out["forward_by_date"] == {}

    def test_datetime_string_truncated_to_date(self):
        out = build_outbound_forward([_ship("2026-06-12T09:00:00.000Z", 1.0)], TODAY)
        assert out["forward_by_date"] == {"2026-06-12": 1.0}


class TestNormalizeCenter:
    def test_a1_variant_maps_to_warehouse_key(self):
        assert normalize_center("에이원지식산업센터") == "에이원센터"

    def test_bestone(self):
        assert normalize_center("베스트원") == "베스트원"

    def test_unknown_or_blank(self):
        assert normalize_center("") == "기타"
        assert normalize_center(None) == "기타"


class TestInboundScheduled:
    def test_window_filter_and_center_grouping(self):
        recs = [_mov("2026-06-12", 1.0), _mov("2026-06-13", 2.0, center="베스트원"),
                _mov("2026-06-26", 9.0)]  # +15d → 제외
        out = build_inbound_scheduled(recs, TODAY, horizon_days=14)
        assert out["scheduled_by_date"] == {"2026-06-12": 1.0, "2026-06-13": 2.0}
        assert out["scheduled_total_cbm"] == 3.0
        assert out["by_center"]["에이원센터"]["total_cbm"] == 1.0
        assert out["by_center"]["베스트원"]["by_date"] == {"2026-06-13": 2.0}

    def test_unmatched_rows_in_coverage_denominator(self):
        recs = [_mov("2026-06-12", 1.0), _mov("2026-06-13", 0.0, src="none")]
        out = build_inbound_scheduled(recs, TODAY)
        assert out["n_rows_window"] == 2
        assert out["coverage_pct"] == 50.0

    def test_dateless_rows_skipped(self):
        out = build_inbound_scheduled([_mov("날짜없음", 1.0)], TODAY)
        assert out["n_rows_window"] == 0

    def test_empty_no_zerodivision(self):
        out = build_inbound_scheduled([], TODAY)
        assert out["coverage_pct"] == 0.0
