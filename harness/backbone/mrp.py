"""MRP 순수 함수 — PT별 부족분 = Σ(소요량_개당×주문수량) − 현재고 (P6 spec §1 S2).

bom_rows 계약은 ledger.build_propagation_row와 동일: {"소품목_PT", "소요량_개당"}.
gross는 발주 단위(정수)로 올림. 음수재고는 부족분을 키운다(즉시 보충 필요).
"""
from __future__ import annotations

import math


def net_requirements(bom_rows: list[dict], order_qty: int,
                     stock_by_pt: dict[str, float]) -> list[dict]:
    gross_by_pt: dict[str, float] = {}
    for b in bom_rows:
        pt = b.get("소품목_PT") or ""
        if not pt:
            continue
        gross_by_pt[pt] = gross_by_pt.get(pt, 0.0) + (b.get("소요량_개당") or 0) * order_qty
    out = []
    for pt in sorted(gross_by_pt):
        gross = math.ceil(round(gross_by_pt[pt], 6))
        stock = stock_by_pt.get(pt, 0)
        out.append({"pt": pt, "gross": gross, "stock": stock,
                    "shortfall": max(0, gross - math.floor(stock))})
    return out
