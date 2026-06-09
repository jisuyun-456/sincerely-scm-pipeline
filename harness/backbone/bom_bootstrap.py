"""WMS order를 굿즈로 그룹핑해 WMS_BOM 행을 생성.

핵심: 같은 '굿즈주문수량' 그룹의 파츠(PT####)들이 그 굿즈의 구성품.
소요량 = 주문수량 / 굿즈수량. (dry-run 실측 적용가능 93.1%)
"""
from __future__ import annotations

from dataclasses import dataclass

from harness.backbone.keys import (
    extract_pt, parse_goods, is_service, compute_soyoryang,
)


@dataclass
class BomRow:
    bom_id: str
    project_code: str
    goods_name: str
    goods_qty: int
    part_code: str
    order_qty: float
    soyoryang: float | None
    confidence: float
    source: str = "order그룹핑"


def _first(v):
    return v[0] if isinstance(v, list) and v else ("" if isinstance(v, list) else v)


def build_bom_rows(order_records: list[dict]) -> list[BomRow]:
    rows: list[BomRow] = []
    for rec in order_records:
        f = rec.get("fields", {})
        pc = str(_first(f.get("project_code")) or "").strip()
        goods_name, goods_qty = parse_goods(f.get("굿즈 주문 수량 (자동)", ""))
        part = extract_pt(f.get("파츠명", ""))
        if not pc or not goods_name or is_service(goods_name) or not part:
            continue
        oqty = f.get("주문수량", 0) or 0
        soyo = compute_soyoryang(oqty, goods_qty)
        rows.append(BomRow(
            bom_id=f"{pc}_{goods_name}_{part}",
            project_code=pc,
            goods_name=goods_name,
            goods_qty=goods_qty,
            part_code=part,
            order_qty=float(oqty) if isinstance(oqty, (int, float)) else 0.0,
            soyoryang=soyo,
            confidence=1.0 if soyo is not None else 0.3,
        ))
    return rows
