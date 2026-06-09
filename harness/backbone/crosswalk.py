"""Crosswalk 2-tier 빌드.

Tier A 굿즈: 굿즈명 → TMS Product(견적코드/CBM) name-match (match_product).
Tier B 파츠: PT#### 자기동일(WMS=MES). normalize_goods 재시도 포함.
"""
from __future__ import annotations

from harness.backbone.keys import normalize_goods
from harness.settlement.cbm_calc import match_product


def build_crosswalk(goods_names: set[str], part_codes: set[str],
                    product_lookup: dict) -> list[dict]:
    rows: list[dict] = []
    # Tier A: 굿즈 → 견적코드
    for gn in sorted(goods_names):
        key, entry, score = match_product(gn, product_lookup)
        if entry is None:  # 정규화 재시도
            key, entry, score = match_product(normalize_goods(gn), product_lookup)
        rows.append({
            "표준키": gn, "키유형": "굿즈",
            "TMS_견적코드": entry["code"] if entry else "",
            "WMS_아이템코드": "", "MES_파츠코드": "",
            "매칭방식": ("정확" if score >= 1.0 else "유사") if entry else "수기",
            "매칭신뢰도": round(score, 2),
            "검증상태": "확정" if score >= 1.0 else ("미검증" if entry else "보류"),
        })
    # Tier B: 파츠 자기동일
    for pt in sorted(part_codes):
        rows.append({
            "표준키": pt, "키유형": "파츠",
            "TMS_견적코드": "", "WMS_아이템코드": pt, "MES_파츠코드": pt,
            "매칭방식": "정확", "매칭신뢰도": 1.0, "검증상태": "확정",
        })
    return rows


import os

WMS_BASE = "appLui4ZR5HWcQRri"


def _crosswalk_table_id() -> str:
    from harness.backbone.create_tables import existing_tables
    return existing_tables()["WMS_KeyCrosswalk"]["id"]


def collect_keys() -> tuple[set[str], set[str]]:
    """order에서 굿즈명·PT#### 수집."""
    from harness.backbone.bom_bootstrap import fetch_orders
    from harness.backbone.keys import parse_goods, extract_pt, is_service
    goods: set[str] = set()
    parts: set[str] = set()
    for rec in fetch_orders():
        f = rec["fields"]
        gn, _ = parse_goods(f.get("굿즈 주문 수량 (자동)", ""))
        if gn and not is_service(gn):
            goods.add(gn)
        pt = extract_pt(f.get("파츠명", ""))
        if pt:
            parts.add(pt)
    return goods, parts


def main() -> None:
    import sys
    from harness.settlement.cbm_calc import load_product_lookup
    from harness._core.airtable import AirtableClient
    dry = "--write" not in sys.argv
    lookup = load_product_lookup({"Authorization": f"Bearer {os.environ['AIRTABLE_PAT']}"})
    goods, parts = collect_keys()
    rows = build_crosswalk(goods, parts, lookup)
    matched = sum(1 for r in rows if r["키유형"] == "굿즈" and r["TMS_견적코드"])
    n_goods = sum(1 for r in rows if r["키유형"] == "굿즈")
    print(f"Crosswalk: 굿즈 {n_goods}(매칭 {matched}={matched/max(n_goods,1)*100:.1f}%) 파츠 {len(parts)}")
    if not dry:
        tbl = _crosswalk_table_id()
        client = AirtableClient.get_or_create(WMS_BASE, tbl, os.environ["AIRTABLE_WMS_PAT"])
        client.create_records([{"fields": r} for r in rows])
        print(f"WROTE {len(rows)}")


if __name__ == "__main__":
    main()
