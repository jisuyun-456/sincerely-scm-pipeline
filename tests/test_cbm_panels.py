"""Chain A — 대시보드 forecast 패널 데이터 (A3 적재율 / B3 입하 / 출하 14d) 테스트."""
import json

from utils.cbm_panels import inbound_panel, load_rate_panel, outbound_panel

_SNAP = {
    "snapshot_date": "2026-06-18", "horizon_days": 14,
    "tracks": {
        "inbound": {
            "scheduled_by_date": {"2026-06-19": 18.2272, "2026-06-24": 35.5607},
            "scheduled_total_cbm": 56.6904, "n_rows_window": 317, "coverage_pct": 16.4,
            "mes_forecast": {"by_horizon": {"7": 11.18, "14": 11.61}, "n_joined": 31},
        },
        "outbound": {
            "forward_by_date": {"2026-06-19": 4.0, "2026-06-20": 6.5},
            "forward_total_cbm": 10.5, "n_shipments_window": 22, "coverage_pct": 81.3,
        },
    },
}


class TestLoadRatePanel:
    def test_summarizes_driver_pct(self):
        panel = load_rate_panel({"이장훈": 50.0, "조희선": 120.0, "박종성": 40.0})
        assert panel["per_driver"]["조희선"] == 120.0
        s = panel["summary"]
        assert s["median"] == 50.0
        assert s["n_over"] == 1      # 120 > 100
        assert s["n_under"] == 1     # 40 < 50

    def test_empty_driver_pct(self):
        panel = load_rate_panel({})
        assert panel["per_driver"] == {}
        assert panel["summary"]["n"] == 0


class TestInboundPanel:
    def test_reads_inbound_track(self, tmp_path):
        p = tmp_path / "capacity_series.json"
        p.write_text(json.dumps([_SNAP]), encoding="utf-8")
        panel = inbound_panel(p)
        assert panel["total_cbm"] == 56.6904
        assert panel["coverage_pct"] == 16.4
        assert panel["by_date"]["2026-06-24"] == 35.5607
        assert panel["mes_forecast"]["14"] == 11.61

    def test_none_when_missing(self, tmp_path):
        assert inbound_panel(tmp_path / "nope.json") is None


class TestOutboundPanel:
    def test_reads_outbound_track(self, tmp_path):
        p = tmp_path / "capacity_series.json"
        p.write_text(json.dumps([_SNAP]), encoding="utf-8")
        panel = outbound_panel(p)
        assert panel["total_cbm"] == 10.5
        assert panel["coverage_pct"] == 81.3
        assert panel["by_date"]["2026-06-20"] == 6.5

    def test_none_when_missing(self, tmp_path):
        assert outbound_panel(tmp_path / "nope.json") is None

    def test_uses_latest_snapshot(self, tmp_path):
        p = tmp_path / "capacity_series.json"
        old = {"snapshot_date": "2026-06-10", "horizon_days": 14,
               "tracks": {"outbound": {"forward_total_cbm": 1.0}}}
        p.write_text(json.dumps([old, _SNAP]), encoding="utf-8")
        assert outbound_panel(p)["total_cbm"] == 10.5
