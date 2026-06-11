"""capacity_snapshot — 3트랙(출고/보관/입하) event-boundary 집계 (P4, pure logic).

각 트랙은 자기 event boundary 1곳에서만 카운트 (spec §9-6 lifecycle 4중 카운트 방지):
출고=shipment.출하확정일 / 보관=InventoryLedger point-in-time / 입하=movement.입하예상일.
트랙 간 합산 필드는 만들지 않는다 — "1주문 트랙간 중복 0" gate를 스키마로 충족.
MES 납기일 forecast는 입하 트랙 내 별도 컴포넌트 (scheduled와 합산 금지).
모든 집계에 커버리지% 동반 (no silent under-count).
"""
from __future__ import annotations

from datetime import date, timedelta

HORIZON_DAYS = 14   # 사용자 CP 2026-06-11

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
    분자 = 규격 해소 성공(spec_src != 'none').
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
        if r.get("spec_src", "none") != "none":
            n_matched += 1
        cbm = float(r.get("cbm") or 0)
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
