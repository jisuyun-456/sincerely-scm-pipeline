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


import json
import os
import urllib.parse
import urllib.request

from harness._core.airtable import AirtableClient

WMS_BASE = "appLui4ZR5HWcQRri"
TBL_ORDER = "tblJslWg8sYEdCkXw"


def _wms_hdr() -> dict:
    return {"Authorization": f"Bearer {os.environ['AIRTABLE_WMS_PAT']}"}


def fetch_orders(limit: int = 2000) -> list[dict]:
    fields = ["project_code", "굿즈 주문 수량 (자동)", "주문수량", "파츠명"]
    out: list[dict] = []
    cursor = None
    while len(out) < limit:
        params = [("pageSize", "100")] + [("fields[]", f) for f in fields]
        if cursor:
            params.append(("offset", cursor))
        url = f"https://api.airtable.com/v0/{WMS_BASE}/{TBL_ORDER}?" + urllib.parse.urlencode(params)
        data = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=_wms_hdr())))
        out.extend(data.get("records", []))
        cursor = data.get("offset")
        if not cursor:
            break
    return out[:limit]


def dedupe_rows(rows: list[BomRow]) -> list[BomRow]:
    """BOM_ID 기준 중복 제거(최초 우선)."""
    seen: set[str] = set()
    out: list[BomRow] = []
    for r in rows:
        if r.bom_id in seen:
            continue
        seen.add(r.bom_id)
        out.append(r)
    return out


def _bom_table_id() -> str:
    from harness.backbone.create_tables import existing_tables
    return existing_tables()["WMS_BOM"]["id"]


def write_bom(rows: list[BomRow], dry_run: bool = True) -> int:
    """WMS_BOM에 status=이송으로 INSERT. dry_run이면 건수만 반환."""
    rows = dedupe_rows(rows)
    if dry_run:
        return len(rows)
    pat = os.environ["AIRTABLE_WMS_PAT"]
    tbl = _bom_table_id()
    client = AirtableClient.get_or_create(WMS_BASE, tbl, pat)
    records = [{"fields": {
        "BOM_ID": r.bom_id, "프로젝트코드": r.project_code,
        "모품목_굿즈명": r.goods_name, "소품목_PT": r.part_code,
        "소요량_개당": r.soyoryang, "신뢰도": r.confidence,
        "검증상태": "이송", "출처": r.source,
    }} for r in rows]
    client.create_records(records)
    return len(records)


def main() -> None:
    import sys
    dry = "--write" not in sys.argv
    rows = build_bom_rows(fetch_orders())
    n = write_bom(rows, dry_run=dry)
    print(f"BOM rows: {len(dedupe_rows(rows))} | {'DRY (no write)' if dry else f'WROTE {n}'}")


if __name__ == "__main__":
    main()
