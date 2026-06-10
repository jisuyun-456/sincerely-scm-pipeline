"""storage — 보관 트랙 occupied CBM 분자 집계 (P3' T3, pure logic).

occupied = Σ(Current_Stock × part CBM), Warehouse별 그룹.
분모(WMS_Location.Max_CBM)는 사용자 실측 도착 시 주입 — 본 모듈은 분자만.
"""
from __future__ import annotations

import re

_PT_KEY_RE = re.compile(r"^PT\d{3,6}$")

# 집계 대상 (spec §6 보관: STORAGE 존 가용 재고만)
ZONE_TYPE_INCLUDE = "STORAGE"
STOCK_TYPE_INCLUDE = "UNRESTRICTED"


def parse_pt_from_ledger_key(key: str) -> str | None:
    """'PT0510|BW01-ST-A01|UNRESTRICTED' → 'PT0510'. PT 아닌 키는 None."""
    head = (key or "").split("|")[0].strip()
    return head if _PT_KEY_RE.match(head) else None


def aggregate_occupied(
    ledger_rows: list[dict],
    part_cbm_by_pt: dict[str, float],
) -> dict:
    """InventoryLedger 행 → Warehouse별 occupied CBM.

    ledger_rows: {pt, stock, warehouse, zone_type, stock_type}
    Returns: by_warehouse / total_occupied_cbm / pt_coverage_pct / uncovered_pts
             / n_rows_filtered
    """
    by_wh: dict[str, dict] = {}
    covered_pts: set[str] = set()
    uncovered_pts: set[str] = set()
    n_filtered = 0

    for row in ledger_rows:
        if row.get("zone_type") != ZONE_TYPE_INCLUDE:
            continue
        if row.get("stock_type") != STOCK_TYPE_INCLUDE:
            continue
        n_filtered += 1
        pt = row["pt"]
        stock = float(row.get("stock") or 0)
        wh = row.get("warehouse") or "미지정"
        entry = by_wh.setdefault(wh, {"occupied_cbm": 0.0, "n_rows": 0,
                                      "pt_covered": 0, "pt_uncovered": 0,
                                      "stock_uncovered": 0.0})
        entry["n_rows"] += 1
        cbm = part_cbm_by_pt.get(pt, 0.0)
        if cbm > 0:
            entry["occupied_cbm"] += stock * cbm
            if pt not in covered_pts:
                entry["pt_covered"] += 1
            covered_pts.add(pt)
        else:
            entry["stock_uncovered"] += stock
            if pt not in uncovered_pts:
                entry["pt_uncovered"] += 1
            uncovered_pts.add(pt)

    total = sum(e["occupied_cbm"] for e in by_wh.values())
    n_pts = len(covered_pts) + len(uncovered_pts)
    coverage = round(len(covered_pts) / n_pts * 100, 1) if n_pts else 0.0
    return {
        "by_warehouse": by_wh,
        "total_occupied_cbm": round(total, 4),
        "pt_coverage_pct": coverage,
        "uncovered_pts": sorted(uncovered_pts),
        "n_rows_filtered": n_filtered,
    }
