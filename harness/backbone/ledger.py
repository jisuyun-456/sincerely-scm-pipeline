"""PropagationLedger v0 — 1 고객주문이 order→자재→포장→CBM→shipment로 흐른 1줄.

INSERT-only 스냅샷. 끊긴 고리(shipment/CBM 없음)는 전파상태로 표시.
"""
from __future__ import annotations


def build_propagation_row(project_code: str, goods_name: str, order_qty: int,
                          bom_rows: list[dict], cbm_per_unit: float | None,
                          shipment_id: str) -> dict:
    mat = [f"{b['소품목_PT']}×{int((b.get('소요량_개당') or 0) * order_qty)}"
           for b in bom_rows]
    cbm = round((cbm_per_unit or 0) * order_qty, 4) if cbm_per_unit else None
    has_chain = bool(shipment_id) and cbm is not None and bool(bom_rows)
    return {
        "전파ID": f"{project_code}_{goods_name}",
        "프로젝트코드": project_code,
        "굿즈명": goods_name,
        "고객주문수량": order_qty,
        "자재소요_요약": ", ".join(mat),
        "포장소요_요약": "",
        "추정_CBM_m3": cbm,
        "shipment_id": shipment_id,
        "전파상태": "완결" if has_chain else ("부분" if (bom_rows or cbm) else "끊김"),
    }


import os


def run_sample(project_code: str = "PNA50702") -> dict:
    """샘플 1 프로젝트의 첫 굿즈를 end-to-end 전파해 1줄 생성·출력."""
    from harness.backbone.bom_bootstrap import build_bom_rows, fetch_orders
    from harness.settlement.cbm_calc import load_product_lookup, match_product

    def _pc(f):
        v = f.get("project_code", "")
        return (v[0] if isinstance(v, list) and v else (v if not isinstance(v, list) else ""))

    orders = [r for r in fetch_orders()
              if str(_pc(r["fields"])).startswith(project_code)]
    boms = build_bom_rows(orders)
    if not boms:
        print(f"{project_code}: BOM 없음")
        return {}
    goods = boms[0].goods_name
    gboms = [{"소품목_PT": b.part_code, "소요량_개당": b.soyoryang}
             for b in boms if b.goods_name == goods]
    oqty = boms[0].goods_qty or int(boms[0].order_qty)
    lookup = load_product_lookup({"Authorization": f"Bearer {os.environ['AIRTABLE_PAT']}"})
    _, e, _ = match_product(goods, lookup)
    cbm_unit = e["cbm_per_box"] / max(int(e["qty_per_box"]), 1) if e else None
    row = build_propagation_row(project_code, goods, oqty, gboms, cbm_unit, "")
    print(row)
    return row


if __name__ == "__main__":
    import sys
    run_sample(sys.argv[1] if len(sys.argv) > 1 else "PNA50702")
