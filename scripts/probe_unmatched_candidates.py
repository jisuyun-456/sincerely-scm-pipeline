"""Probe2: For unmatched lines, find best fuzzy candidates in product master."""
from __future__ import annotations
import os, re, sys, time
from datetime import date, timedelta
from collections import Counter
import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TMS_BASE_ID = "app4x70a8mOrIKsMf"
TBL_SHIP = "tbllg1JoHclGYer7m"
TBL_PROD = "tblBNh6oGDlTKGrdQ"
TF_DATE  = "fldQvmEwwzvQW95h9"
TF_ITEM  = "fldgSupj5XLjJXYQo"
TF_TOTAL_CBM  = "fldJ9DHjwoRyeUEqE"
TF_BOX_PARSED = "fldTjLDmw5sNGszeD"
TF_BOX_MANUAL = "fldRjMaXa5TdSsGDL"
PF_NAME = "fldx01uKEnCd0J0nP"
PF_CBM  = "fldCeJ0RqSUGlfEw4"
PF_KIT  = "fld6W5ImO7UeBVMPI"

_BOX_RE = re.compile(r"(극소|소|중대|중|대|특대|S280|S360|M350|M480|L510|L560)\s*(\d+)")


def _h(pat): return {"Authorization": f"Bearer {pat}"}


def fetch(base, table, fields, formula=None):
    pat = os.environ["AIRTABLE_PAT"]
    out, off = [], None
    while True:
        p = {"fields[]": fields, "pageSize": 100, "returnFieldsByFieldId": "true"}
        if off: p["offset"] = off
        if formula: p["filterByFormula"] = formula
        r = requests.get(f"https://api.airtable.com/v0/{base}/{table}",
                         headers=_h(pat), params=p, timeout=30)
        r.raise_for_status()
        d = r.json()
        out.extend(d.get("records", []))
        off = d.get("offset")
        if not off: break
        time.sleep(0.2)
    return out


def char_overlap(a, b):
    """Bigram overlap ratio (Sorensen-Dice)."""
    if not a or not b: return 0.0
    A = {a[i:i+2] for i in range(len(a)-1)}
    B = {b[i:i+2] for i in range(len(b)-1)}
    if not A or not B: return 0.0
    return 2 * len(A & B) / (len(A) + len(B))


def main():
    print("[probe2] fetching products...")
    prods = fetch(TMS_BASE_ID, TBL_PROD, [PF_NAME, PF_CBM, PF_KIT])
    product_cbm = []
    for r in prods:
        c = r["fields"]
        name = (c.get(PF_NAME) or "").strip()
        cbm = c.get(PF_CBM) or c.get(PF_KIT) or None
        if name and cbm:
            try: product_cbm.append((name, re.sub(r"\s+", "", name), float(cbm)))
            except (ValueError, TypeError): pass
    print(f"  {len(product_cbm)} products loaded\n")

    mon = date.today() - timedelta(days=date.today().weekday()) + timedelta(days=7)
    fri = mon + timedelta(days=4)
    formula = (f"AND(IS_AFTER({{출하확정일}},'{(mon-timedelta(days=1)).isoformat()}'),"
               f"IS_BEFORE({{출하확정일}},'{(fri+timedelta(days=1)).isoformat()}'))")
    ships = fetch(TMS_BASE_ID, TBL_SHIP,
                  [TF_DATE, TF_ITEM, TF_BOX_PARSED, TF_BOX_MANUAL, TF_TOTAL_CBM],
                  formula)

    failed_lines = []
    for rec in ships:
        f = rec["fields"]
        if f.get(TF_TOTAL_CBM): continue
        box = f.get(TF_BOX_PARSED) or f.get(TF_BOX_MANUAL) or ""
        if isinstance(box, list): box = ", ".join(str(x) for x in box)
        if box.strip() and _BOX_RE.search(box.strip()): continue

        item = f.get(TF_ITEM) or ""
        if not item.strip(): continue

        for line in item.strip().splitlines():
            line = line.strip()
            if not line: continue
            norm = re.sub(r"\s+", "", line)
            if any(pn in norm for _, pn, _ in product_cbm):
                continue
            failed_lines.append(line)

    print(f"=== {len(failed_lines)} unique failure lines ===\n")
    for line in failed_lines[:30]:
        norm_line = re.sub(r"\s+", "", line)
        # strip trailing qty for fuzzy match
        norm_noqty = re.sub(r"\d+$", "", norm_line)
        # strip common size suffixes
        norm_clean = re.sub(r"(XL|2XL|XXL|키트|세트)$", "", norm_noqty)
        scored = [(char_overlap(norm_clean, pn), nm, cbm)
                  for nm, pn, cbm in product_cbm]
        scored.sort(reverse=True)
        print(f"LINE: '{line}'  (norm_clean='{norm_clean}')")
        for score, name, cbm in scored[:3]:
            print(f"  {score:.2f}  {name}  cbm/u={cbm}")
        print()


if __name__ == "__main__":
    sys.exit(main() or 0)
