"""CBM 마스터: TMS Product 정규화 + 미등록 굿즈 탐지 + 박스치수→CBM 유도.

dry-run 실측: 1500 order 굿즈 413종 중 ~186종이 382품목 마스터 미등록.
박스규격(LxWxH mm) + 박스당 제품수로 개당 CBM을 유도해 ItemMaster 확장.
"""
from __future__ import annotations

import re

from harness.backbone.keys import normalize_goods
from harness.settlement.cbm_calc import match_product

_DIM_RE = re.compile(r"^\s*(\d+)\s*[*xX×]\s*(\d+)\s*[*xX×]\s*(\d+)\s*$")


def cbm_from_box_dims(box_size: str, qty_per_box: int) -> float | None:
    """'480*380*270'(mm) + 박스당수량 → 개당 CBM(m³). 파싱 실패 시 None."""
    m = _DIM_RE.match(box_size or "")
    if not m or not qty_per_box or qty_per_box <= 0:
        return None
    l, w, h = (int(x) for x in m.groups())
    box_cbm = (l / 1000) * (w / 1000) * (h / 1000)
    return round(box_cbm / qty_per_box, 6)


def find_unmatched_goods(goods_names: set[str], product_lookup: dict) -> list[str]:
    """매칭(정확/유사/정규화) 모두 실패한 굿즈명 = 마스터 확장 대상."""
    out: list[str] = []
    for gn in sorted(goods_names):
        _, e, _ = match_product(gn, product_lookup)
        if e is None:
            _, e, _ = match_product(normalize_goods(gn), product_lookup)
        if e is None:
            out.append(gn)
    return out


import os


def report_unmatched() -> list[str]:
    from harness.settlement.cbm_calc import load_product_lookup
    from harness.backbone.crosswalk import collect_keys
    lookup = load_product_lookup({"Authorization": f"Bearer {os.environ['AIRTABLE_PAT']}"})
    goods, _ = collect_keys()
    miss = find_unmatched_goods(goods, lookup)
    print(f"미등록 굿즈: {len(miss)}/{len(goods)} ({len(miss)/max(len(goods),1)*100:.1f}%)")
    for g in miss[:30]:
        print("   -", g)
    return miss


if __name__ == "__main__":
    report_unmatched()
