"""Chain A — 대시보드 forecast 패널 데이터 (A3 적재율 / B3 입하 / 출하 14d).

generate_scm_report.py 가 pages_data['forecast'] 로 노출 → dashboard.html 렌더.
- 적재율(A3): 리포트가 이미 산출한 driver_pct(라이브 차량한도 SSOT) → 함대 median+flags 파생.
- 입하(B3)·출하: committed data/capacity_series.json(capacity_snapshot 일배치) 최신 스냅샷.
  (D1 ship_req 주별 사전계획은 cascade 결과 라이브가 필요 → order_cascade Slack digest 담당.)
"""
from __future__ import annotations

import json
from pathlib import Path

from utils.vehicle_util import summarize_util

ROOT = Path(__file__).resolve().parents[1]
_SERIES = ROOT / "data" / "capacity_series.json"


def load_rate_panel(driver_pct: dict) -> dict:
    """A3 — driver_pct(기사별 주간 적재율%) → 함대 요약(median+under/over) + per-driver."""
    return {
        "per_driver": dict(driver_pct or {}),
        "summary": summarize_util(list((driver_pct or {}).values())),
    }


def _latest_snapshot(series_path: Path | None = None) -> dict | None:
    path = series_path or _SERIES
    if not path.exists():
        return None
    try:
        series = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return series[-1] if series else None


def inbound_panel(series_path: Path | None = None) -> dict | None:
    """B3 — capacity_series inbound 14d 사전계획. 스냅샷 없으면 None."""
    snap = _latest_snapshot(series_path)
    if not snap:
        return None
    inb = (snap.get("tracks") or {}).get("inbound") or {}
    return {
        "snapshot_date": snap.get("snapshot_date"),
        "horizon_days": snap.get("horizon_days"),
        "total_cbm": inb.get("scheduled_total_cbm", 0),
        "coverage_pct": inb.get("coverage_pct", 0),
        "by_date": inb.get("scheduled_by_date", {}),
        "mes_forecast": (inb.get("mes_forecast") or {}).get("by_horizon", {}),
    }


def outbound_panel(series_path: Path | None = None) -> dict | None:
    """출하 14d 사전계획 — capacity_series outbound(출하확정 기준). 스냅샷 없으면 None."""
    snap = _latest_snapshot(series_path)
    if not snap:
        return None
    out = (snap.get("tracks") or {}).get("outbound") or {}
    return {
        "snapshot_date": snap.get("snapshot_date"),
        "horizon_days": snap.get("horizon_days"),
        "total_cbm": out.get("forward_total_cbm", 0),
        "coverage_pct": out.get("coverage_pct", 0),
        "by_date": out.get("forward_by_date", {}),
    }
