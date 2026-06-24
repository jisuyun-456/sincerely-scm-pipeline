"""B3 입하 14d 사전계획 섹션 (capacity_series 표면화) 테스트 — P2."""
import json

from scripts.wms_weekly_runner import _b3_from_snapshot, _build_b3_inbound_section

_SNAP = {
    "snapshot_date": "2026-06-18", "horizon_days": 14,
    "tracks": {"inbound": {
        "scheduled_by_date": {"2026-06-19": 18.2272, "2026-06-24": 35.5607},
        "scheduled_total_cbm": 56.6904, "n_rows_window": 317, "coverage_pct": 16.4,
        "staging": {"에이원센터": {"max_cbm": 57.6, "peak_date": "2026-06-24",
                                "peak_day_cbm": 35.5607, "peak_day_pct": 61.7}},
        "mes_forecast": {"by_horizon": {"7": 11.18, "14": 11.61},
                         "n_joined": 31, "n_total": 338},
    }},
}


def test_b3_from_snapshot_renders_inbound():
    md = _b3_from_snapshot(_SNAP)
    assert "B3 입하 14d 사전계획" in md
    assert "56.6904 m³" in md and "16.4%" in md
    assert "2026-06-24" in md and "35.5607" in md
    assert "에이원센터" in md and "61.7%" in md
    assert "7d 11.18m³" in md and "14d 11.61m³" in md


def test_build_b3_inbound_section_missing_file(tmp_path):
    md = _build_b3_inbound_section(tmp_path / "nope.json")
    assert "capacity_series.json 없음" in md


def test_build_b3_inbound_section_reads_latest(tmp_path):
    p = tmp_path / "capacity_series.json"
    p.write_text(json.dumps([
        {"snapshot_date": "2026-06-10", "horizon_days": 14,
         "tracks": {"inbound": {"scheduled_total_cbm": 1.0}}},
        _SNAP,
    ]), encoding="utf-8")
    md = _build_b3_inbound_section(p)
    assert "2026-06-18" in md and "56.6904 m³" in md   # 최신 스냅샷 사용
