"""Phase-1 검증 게이트 (§7) 실측. read-only.

Gate1 Tier A 굿즈 매칭률(목표 ≥85%, Phase-1 마스터 한계로 ~46%),
Gate2b PT 추출(≥99%), Gate3 BOM 적용율(≥90%), Gate4 링크 안전성.
실행: AIRTABLE_PAT=... AIRTABLE_WMS_PAT=... python -m harness.backbone.verify_phase1
"""
from __future__ import annotations

import os

from harness.backbone.bom_bootstrap import build_bom_rows, fetch_orders
from harness.backbone.crosswalk import collect_keys
from harness.backbone.keys import extract_pt
from harness.settlement.cbm_calc import load_product_lookup, match_product


def main() -> None:
    tms = {"Authorization": f"Bearer {os.environ['AIRTABLE_PAT']}"}
    lookup = load_product_lookup(tms)
    orders = fetch_orders()
    goods, parts = collect_keys()

    # Gate 1: Tier A 굿즈 매칭률
    matched = sum(1 for g in goods if match_product(g, lookup)[1])
    g1 = matched / max(len(goods), 1) * 100

    # Gate 2b: PT 추출률
    pn = [r["fields"].get("파츠명", "") for r in orders if r["fields"].get("파츠명")]
    g2b = sum(1 for p in pn if extract_pt(p)) / max(len(pn), 1) * 100

    # Gate 3: BOM 적용율
    boms = build_bom_rows(orders)
    with_soyo = sum(1 for b in boms if b.soyoryang is not None)
    g3 = with_soyo / max(len(boms), 1) * 100

    print(f"[Gate1] Tier A 굿즈 매칭: {matched}/{len(goods)} = {g1:.1f}% (목표 ≥85%, Phase-1 마스터 한계)")
    print(f"[Gate2b] PT 추출: {g2b:.1f}% (목표 ≥99%)")
    print(f"[Gate3] BOM 적용율: {with_soyo}/{len(boms)} = {g3:.1f}% (목표 ≥90%)")
    print(f"[Gate4] 쓰기 대상: WMS 네이티브 4테이블만 (본 스크립트 read-only, TMS Product 변경 0)")


if __name__ == "__main__":
    main()
