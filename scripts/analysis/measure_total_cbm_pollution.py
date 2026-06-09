"""Total_CBM>0 Shipment를 결정론 재계산과 비교 — 오염(기계추정) 추정치 측정. READ-ONLY (쓰기 0).

판정:
  - 결정론 일치(±5%)  = 측정값이거나 추정이 정확 → 신뢰 가능
  - 결정론 불일치       = 기계추정 오염 의심
  - 코드/CBM 없음       = 판정 불가(blank project/code 또는 Product CBM 부재)

Usage: python scripts/analysis/measure_total_cbm_pollution.py
"""
import collections
import math
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "harness" / "settlement"))
from cbm_calc import load_product_lookup  # noqa: E402

load_dotenv()
TP = os.environ["AIRTABLE_PAT"]
WP = os.environ["AIRTABLE_WMS_PAT"]
TMS = "app4x70a8mOrIKsMf"
WMS = "appLui4ZR5HWcQRri"
SHIP = "tbllg1JoHclGYer7m"
ORDER = "tblJslWg8sYEdCkXw"
PNA = re.compile(r"PNA\d+")


def fetch(base, tid, pat, fields):
    out, off = [], None
    while True:
        p = {"pageSize": 100, "fields[]": fields}
        if off:
            p["offset"] = off
        r = requests.get(
            f"https://api.airtable.com/v0/{base}/{tid}",
            headers={"Authorization": f"Bearer {pat}"}, params=p, timeout=60,
        )
        r.raise_for_status()
        d = r.json()
        out += d["records"]
        off = d.get("offset")
        if not off:
            break
    return out


def n(x):
    try:
        return float(str(x).replace(",", "") or 0)
    except (ValueError, TypeError):
        return 0.0


def main():
    print("Product 룩업 로딩...", flush=True)
    lk = load_product_lookup({"Authorization": f"Bearer {TP}"})
    print("order 로딩...", flush=True)
    orders = fetch(WMS, ORDER, WP, ["project_code", "굿즈코드 (from sync_itemdb)", "주문수량"])
    opg = collections.defaultdict(collections.Counter)
    for r in orders:
        f = r["fields"]
        m = PNA.search(str(f.get("project_code") or ""))
        code = f.get("굿즈코드 (from sync_itemdb)")
        if isinstance(code, list):
            code = code[0] if code else ""
        if m and code:
            opg[m.group(0)][str(code).upper()] += n(f.get("주문수량"))
    print("shipment 로딩...", flush=True)
    ships = fetch(TMS, SHIP, TP, ["project code", "Total_CBM"])
    have = [r for r in ships if n(r["fields"].get("Total_CBM")) > 0]

    match = mismatch = nocode = 0
    for r in have:
        f = r["fields"]
        m = PNA.search(str(f.get("project code") or ""))
        ok = bool(m and m.group(0) in opg)
        det = 0.0
        if ok:
            for code, q in opg[m.group(0)].items():
                e = lk.get(code.lower())
                if e and e["cbm_per_box"] > 0 and q > 0:
                    det += math.ceil(q / e["qty_per_box"]) * e["cbm_per_box"]
        tot = n(f.get("Total_CBM"))
        if not ok or det <= 0:
            nocode += 1
        elif abs(det - tot) / max(tot, 1e-9) <= 0.05:
            match += 1
        else:
            mismatch += 1

    print(f"\n=== Total_CBM>0 Shipment: {len(have)}건 ===")
    print(f"  결정론 일치(±5%, 신뢰 가능)    : {match} ({match/len(have)*100:.1f}%)")
    print(f"  결정론 불일치(기계추정 오염 의심): {mismatch} ({mismatch/len(have)*100:.1f}%)")
    print(f"  코드/CBM 없음(판정 불가)        : {nocode} ({nocode/len(have)*100:.1f}%)")
    print("\n→ ruling: 불일치 행 Total_CBM blank(되돌림) vs estimated_cbm 재분류 vs 수용")


if __name__ == "__main__":
    main()
