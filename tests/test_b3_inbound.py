"""B3 입하 14d 사전계획 섹션 (capacity_series 표면화) 테스트 — P2 + Chain A Slack."""
import json

from scripts.wms_weekly_runner import (
    _b3_from_snapshot,
    _b3_slack_from_snapshot,
    _build_b3_inbound_section,
    b3_slack_summary,
)

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


# ─── B3 Slack 요약 (Chain A) — compact, not full markdown table ──────────

def test_b3_slack_from_snapshot_is_compact():
    s = _b3_slack_from_snapshot(_SNAP)
    assert "B3 입하 14d" in s
    assert "56.6904" in s and "16.4%" in s     # total + coverage
    assert "7d 11.18m³" in s and "14d 11.61m³" in s   # MES horizon
    # 컴팩트: 전체 일자 테이블은 미포함 (Slack 과부하 방지)
    assert "| 입하예상일 |" not in s


def test_b3_slack_summary_none_when_missing(tmp_path):
    assert b3_slack_summary(tmp_path / "nope.json") is None


def test_b3_slack_summary_reads_latest(tmp_path):
    p = tmp_path / "capacity_series.json"
    p.write_text(json.dumps([
        {"snapshot_date": "2026-06-10", "horizon_days": 14,
         "tracks": {"inbound": {"scheduled_total_cbm": 1.0}}},
        _SNAP,
    ]), encoding="utf-8")
    s = b3_slack_summary(p)
    assert s is not None and "56.6904" in s
