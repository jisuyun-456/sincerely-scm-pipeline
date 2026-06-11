"""capacity_snapshot 테스트 (P4) — 윈도우/커버리지/트랙분리/append idempotency."""
from datetime import date

from harness.backbone.capacity_snapshot import build_outbound_forward

TODAY = date(2026, 6, 11)


def _ship(d, cbm):
    return {"ship_date": d, "cbm_valid": cbm}


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
