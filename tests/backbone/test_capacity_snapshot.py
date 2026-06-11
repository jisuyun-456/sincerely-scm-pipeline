"""capacity_snapshot 테스트 (P4) — 윈도우/커버리지/트랙분리/append idempotency."""
from datetime import date

from harness.backbone.capacity_snapshot import (
    EVENT_BOUNDARIES,
    append_series,
    build_inbound_scheduled,
    build_outbound_forward,
    build_snapshot,
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


# aggregate_occupied 출력 스키마 그대로 (harness/backbone/storage.py)
STORAGE_AGG = {
    "by_warehouse": {"베스트원": {"occupied_cbm": 306.24, "n_rows": 100,
                                "pt_covered": 135, "pt_uncovered": 166,
                                "stock_uncovered": 5000.0}},
    "total_occupied_cbm": 306.24,
    "pt_coverage_pct": 44.9,
    "uncovered_pts": [],
    "n_rows_filtered": 100,
}


def make_snap(mes=None, storage_max=None, staging_max=None):
    outbound = build_outbound_forward([_ship("2026-06-12", 3.0)], TODAY)
    inbound = build_inbound_scheduled([_mov("2026-06-12", 1.0)], TODAY)
    return build_snapshot(TODAY, outbound, STORAGE_AGG, inbound, mes,
                          storage_max_cbm=storage_max, staging_max_cbm=staging_max,
                          generated_at="2026-06-11T07:30:00+09:00")


class TestSnapshotTrackSeparation:
    """Gate: 1주문 트랙간 중복 0 — 트랙 간 합산 필드 부재 + boundary 태깅."""

    def test_three_tracks_with_event_boundaries(self):
        snap = make_snap()
        assert set(snap["tracks"]) == {"outbound", "storage", "inbound"}
        for t, b in EVENT_BOUNDARIES.items():
            assert snap["tracks"][t]["event_boundary"] == b

    def test_no_cross_track_sum_field(self):
        snap = make_snap()
        # top-level에 트랙 횡단 합산 키 없음 — 각 트랙 숫자는 자기 입력만 반영
        assert not any("cbm" in k.lower() or "total" in k.lower() for k in snap)
        assert snap["tracks"]["outbound"]["forward_total_cbm"] == 3.0
        assert snap["tracks"]["inbound"]["scheduled_total_cbm"] == 1.0
        assert snap["tracks"]["storage"]["occupied_total_cbm"] == 306.24

    def test_mes_kept_separate_from_scheduled(self):
        mes = {"by_horizon": {7: 2.49, 14: 4.83}, "n_joined": 31, "n_total": 100}
        snap = make_snap(mes=mes)
        inb = snap["tracks"]["inbound"]
        assert inb["mes_forecast"]["by_horizon"] == {"7": 2.49, "14": 4.83}
        assert inb["scheduled_total_cbm"] == 1.0   # MES 미합산

    def test_mes_none_when_pat_missing(self):
        assert make_snap(mes=None)["tracks"]["inbound"]["mes_forecast"] is None


class TestOccupancy:
    def test_storage_occupancy_with_max(self):
        snap = make_snap(storage_max={"베스트원": 500.0})
        wh = snap["tracks"]["storage"]["by_warehouse"]["베스트원"]
        assert wh["occupancy_pct"] == 61.2          # 306.24/500

    def test_storage_occupancy_none_without_max(self):
        wh = make_snap()["tracks"]["storage"]["by_warehouse"]["베스트원"]
        assert wh["max_cbm"] is None and wh["occupancy_pct"] is None

    def test_staging_peak_day(self):
        snap = make_snap(staging_max={"에이원센터": 57.6})
        st = snap["tracks"]["inbound"]["staging"]["에이원센터"]
        assert st["max_cbm"] == 57.6
        assert st["peak_day_cbm"] == 1.0
        assert st["peak_day_pct"] == 1.7            # 1.0/57.6

    def test_staging_no_arrivals_zero_not_error(self):
        snap = make_snap(staging_max={"베스트원": 10.0})  # 베스트원 입하 0건
        st = snap["tracks"]["inbound"]["staging"]["베스트원"]
        assert st["peak_day_cbm"] == 0.0 and st["peak_date"] is None


class TestAppendSeries:
    def test_appends_new_date(self):
        out = append_series([], make_snap())
        assert len(out) == 1

    def test_replaces_same_date_idempotent(self):
        s1 = make_snap()
        s2 = make_snap(mes={"by_horizon": {7: 1.0, 14: 2.0},
                            "n_joined": 1, "n_total": 1})
        out = append_series([s1], s2)
        assert len(out) == 1
        assert out[0]["tracks"]["inbound"]["mes_forecast"] is not None

    def test_sorted_by_snapshot_date(self):
        a = dict(make_snap(), snapshot_date="2026-06-12")
        b = dict(make_snap(), snapshot_date="2026-06-10")
        out = append_series([a], b)
        assert [s["snapshot_date"] for s in out] == ["2026-06-10", "2026-06-12"]
