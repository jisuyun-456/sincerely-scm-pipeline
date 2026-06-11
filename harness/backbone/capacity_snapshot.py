"""capacity_snapshot — 3트랙(출고/보관/입하) event-boundary 집계 (P4, pure logic).

각 트랙은 자기 event boundary 1곳에서만 카운트 (spec §9-6 lifecycle 4중 카운트 방지):
출고=shipment.출하확정일 / 보관=InventoryLedger point-in-time / 입하=movement.입하예상일.
트랙 간 합산 필드는 만들지 않는다 — "1주문 트랙간 중복 0" gate를 스키마로 충족.
MES 납기일 forecast는 입하 트랙 내 별도 컴포넌트 (scheduled와 합산 금지).
모든 집계에 커버리지% 동반 (no silent under-count).
"""
from __future__ import annotations

from datetime import date, timedelta

HORIZON_DAYS = 14   # 사용자 CP 2026-06-11. 윈도우 = today..today+14 양끝 포함
                    # (15 캘린더일 — MES forecast의 days<=h 의미론과 정렬)

EVENT_BOUNDARIES = {
    "outbound": "shipment.출하확정일",
    "storage": "inventory_ledger.point_in_time",
    "inbound": "movement.입하예상일",
}


def _parse_date(raw) -> date | None:
    try:
        return date.fromisoformat(str(raw or "")[:10])
    except ValueError:
        return None


def build_outbound_forward(
    shipment_rows: list[dict], today: date, horizon_days: int = HORIZON_DAYS,
) -> dict:
    """[{ship_date, cbm_valid}] → 윈도우(today..today+h) forward curve.

    coverage_pct 분모 = 윈도우 내 shipment 전체 (CBM 0 행 포함 — no silent under-count).
    """
    end = today + timedelta(days=horizon_days)
    by_date: dict[str, float] = {}
    n_window = n_with_cbm = 0
    for row in shipment_rows:
        d = _parse_date(row.get("ship_date"))
        if d is None or not (today <= d <= end):
            continue
        n_window += 1
        cbm = float(row.get("cbm_valid") or 0)
        if cbm > 0:
            n_with_cbm += 1
            key = d.isoformat()
            by_date[key] = round(by_date.get(key, 0.0) + cbm, 4)
    return {
        "forward_by_date": dict(sorted(by_date.items())),
        "forward_total_cbm": round(sum(by_date.values()), 4),
        "n_shipments_window": n_window,
        "n_with_cbm": n_with_cbm,
        "coverage_pct": round(n_with_cbm / n_window * 100, 1) if n_window else 0.0,
    }


def normalize_center(raw) -> str:
    """movement 이동물품 3번째 토큰('에이원지식산업센터' 등) → Location.Warehouse 키."""
    s = str(raw or "")
    if "에이원" in s:
        return "에이원센터"
    if "베스트원" in s:
        return "베스트원"
    return "기타"


def build_inbound_scheduled(
    records: list[dict], today: date, horizon_days: int = HORIZON_DAYS,
) -> dict:
    """fetch_inbound_cbm records → 윈도우 입하 예정 by_date/by_center.

    records: [{exp_date, cbm, spec_src, center}]. coverage_pct 분모 = 윈도우 행 전체,
    분자 = 규격 해소 + CBM>0 산출 성공 (qty=0 등 미산출 행은 covered 아님 — review fix).
    """
    end = today + timedelta(days=horizon_days)
    by_date: dict[str, float] = {}
    by_center: dict[str, dict] = {}
    n_window = n_matched = 0
    for r in records:
        d = _parse_date(r.get("exp_date"))
        if d is None or not (today <= d <= end):
            continue
        n_window += 1
        cbm = float(r.get("cbm") or 0)
        if r.get("spec_src", "none") != "none" and cbm > 0:
            n_matched += 1
        if cbm <= 0:
            continue
        key = d.isoformat()
        by_date[key] = round(by_date.get(key, 0.0) + cbm, 4)
        ce = by_center.setdefault(normalize_center(r.get("center")),
                                  {"total_cbm": 0.0, "by_date": {}})
        ce["total_cbm"] = round(ce["total_cbm"] + cbm, 4)
        ce["by_date"][key] = round(ce["by_date"].get(key, 0.0) + cbm, 4)
    return {
        "scheduled_by_date": dict(sorted(by_date.items())),
        "scheduled_total_cbm": round(sum(by_date.values()), 4),
        "n_rows_window": n_window,
        "coverage_pct": round(n_matched / n_window * 100, 1) if n_window else 0.0,
        "by_center": by_center,
    }


def _staging_occupancy(by_center: dict, staging_max_cbm: dict | None) -> dict:
    """센터별 입하 피크일 CBM vs 입하장 Max_CBM (시드된 센터만)."""
    out = {}
    for wh, mx in (staging_max_cbm or {}).items():
        dates = (by_center.get(wh) or {}).get("by_date") or {}
        if not dates or not mx:
            out[wh] = {"max_cbm": mx, "peak_date": None,
                       "peak_day_cbm": 0.0, "peak_day_pct": 0.0}
            continue
        peak_date, peak = max(dates.items(), key=lambda kv: kv[1])
        out[wh] = {"max_cbm": mx, "peak_date": peak_date,
                   "peak_day_cbm": peak,
                   "peak_day_pct": round(peak / mx * 100, 1)}
    return out


def build_snapshot(
    today: date,
    outbound: dict,
    storage_agg: dict,
    inbound_sched: dict,
    mes_forecast: dict | None,
    storage_max_cbm: dict | None = None,
    staging_max_cbm: dict | None = None,
    horizon_days: int = HORIZON_DAYS,
    generated_at: str | None = None,
) -> dict:
    """3트랙 스냅샷 1건 조립 — 트랙 간 합산 없음, 각 트랙 자기 boundary만.

    storage_agg = storage.aggregate_occupied() 출력 / mes_forecast =
    mes_forecast.build_inbound_forecast() 출력 또는 None(MES PAT 부재).
    *_max_cbm = {Warehouse: m³} — WMS_Location.Max_CBM 시드행만.
    """
    by_wh = {}
    for wh, e in storage_agg["by_warehouse"].items():
        mx = (storage_max_cbm or {}).get(wh)
        by_wh[wh] = {
            "occupied_cbm": round(e["occupied_cbm"], 4),
            "max_cbm": mx,
            "occupancy_pct": round(e["occupied_cbm"] / mx * 100, 1) if mx else None,
        }
    mes_part = None
    if mes_forecast is not None:
        mes_part = {
            "by_horizon": {str(h): v for h, v in mes_forecast["by_horizon"].items()},
            "n_joined": mes_forecast["n_joined"],
            "n_total": mes_forecast["n_total"],
        }
    inbound = {k: v for k, v in inbound_sched.items() if k != "by_center"}
    return {
        "snapshot_date": today.isoformat(),
        "generated_at": generated_at,
        "horizon_days": horizon_days,
        "tracks": {
            "outbound": {"event_boundary": EVENT_BOUNDARIES["outbound"], **outbound},
            "storage": {
                "event_boundary": EVENT_BOUNDARIES["storage"],
                "occupied_total_cbm": storage_agg["total_occupied_cbm"],
                "by_warehouse": by_wh,
                "pt_coverage_pct": storage_agg["pt_coverage_pct"],
            },
            "inbound": {
                "event_boundary": EVENT_BOUNDARIES["inbound"],
                **inbound,
                "staging": _staging_occupancy(inbound_sched.get("by_center", {}),
                                              staging_max_cbm),
                "mes_forecast": mes_part,
            },
        },
    }


def append_series(series: list[dict], snapshot: dict) -> list[dict]:
    """idempotent append — 같은 snapshot_date 항목 교체, 날짜순 정렬."""
    out = [s for s in series if s.get("snapshot_date") != snapshot["snapshot_date"]]
    out.append(snapshot)
    out.sort(key=lambda s: s.get("snapshot_date", ""))
    return out
