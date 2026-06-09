"""WMS_ItemMaster 적재.

매칭 굿즈 = TMS Product CBM 정규화(출처=TMS_Product).
미등록 굿즈 = CBM 미확보(출처=미등록) — Phase-2 확장 대상(MES 치수/수기 소싱).
  (order 규격 필드는 sparse·단위 불일치라 CBM 유도 소스로 부적합 — 사용 안 함.)
파츠(PT####) = 부자재 식별.

실행: AIRTABLE_PAT=... AIRTABLE_WMS_PAT=... python -m harness.backbone.item_master_sync [--write]
"""
from __future__ import annotations

import os

from harness._core.airtable import AirtableClient
from harness.backbone.crosswalk import collect_keys
from harness.settlement.cbm_calc import load_product_lookup, match_product

WMS_BASE = "appLui4ZR5HWcQRri"


def build_item_rows() -> list[dict]:
    tms_lookup = load_product_lookup(
        {"Authorization": f"Bearer {os.environ['AIRTABLE_PAT']}"}
    )
    goods, parts = collect_keys()
    rows: list[dict] = []
    for gn in sorted(goods):
        _, e, _ = match_product(gn, tms_lookup)
        if e:
            # cbm_per_box는 박스 단위 CBM. 개당 = 박스CBM / 박스당제품수.
            qpb = max(int(e["qty_per_box"]), 1)
            per_item = round(e["cbm_per_box"] / qpb, 6)
            rows.append({"품목키": gn, "품목명": gn, "품목유형": "완제품",
                         "CBM_개당_m3": per_item,
                         "박스당_제품수": e["qty_per_box"],
                         "박스당_CBM_m3": e["cbm_per_box"], "출처": "TMS_Product"})
        else:
            rows.append({"품목키": gn, "품목명": gn, "품목유형": "완제품",
                         "출처": "미등록"})
    for pt in sorted(parts):
        rows.append({"품목키": pt, "품목명": pt, "품목유형": "부자재", "출처": "수기"})
    return rows


def main() -> None:
    import sys
    rows = build_item_rows()
    matched = sum(1 for r in rows if r.get("출처") == "TMS_Product")
    goods_n = sum(1 for r in rows if r.get("품목유형") == "완제품")
    print(f"ItemMaster rows: {len(rows)} | 굿즈 {goods_n}"
          f"(CBM확보 {matched}={matched/max(goods_n,1)*100:.1f}%) | 파츠 {len(rows)-goods_n}")
    if "--write" in sys.argv:
        from harness.backbone.create_tables import existing_tables
        tbl = existing_tables()["WMS_ItemMaster"]["id"]
        client = AirtableClient.get_or_create(WMS_BASE, tbl, os.environ["AIRTABLE_WMS_PAT"])
        client.create_records([{"fields": r} for r in rows])
        print(f"WROTE {len(rows)}")


if __name__ == "__main__":
    main()
