"""Probe: next_week shipments — show TF_ITEM + matching result per line.

목적: match_cbm_from_product()가 어떤 라인에서 실패하는지 시각화.
실행: AIRTABLE_PAT=... python scripts/probe_next_week_match.py
"""
from __future__ import annotations
import os, re, sys, time
from datetime import date, timedelta
from collections import Counter
import requests

# Force UTF-8 on stdout (Windows CP949 default kills emoji/unicode)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TMS_BASE_ID = "app4x70a8mOrIKsMf"
TBL_SHIP = "tbllg1JoHclGYer7m"
TBL_PROD = "tblBNh6oGDlTKGrdQ"

# Shipment fields
TF_DATE  = "fldQvmEwwzvQW95h9"
TF_ITEM  = "fldgSupj5XLjJXYQo"
TF_BOX_PARSED = "fldTjLDmw5sNGszeD"
TF_BOX_MANUAL = "fldRjMaXa5TdSsGDL"
TF_TOTAL_CBM  = "fldJ9DHjwoRyeUEqE"

# Product fields
PF_NAME = "fldx01uKEnCd0J0nP"
PF_CBM  = "fldCeJ0RqSUGlfEw4"
PF_KIT  = "fld6W5ImO7UeBVMPI"

_BOX_RE = re.compile(r"(극소|소|중대|중|대|특대|S280|S360|M350|M480|L510|L560)\s*(\d+)")


def _headers(pat):
    return {"Authorization": f"Bearer {pat}", "Content-Type": "application/json"}


def fetch_all(base, table, fields, formula=None):
    pat = os.environ["AIRTABLE_PAT"]
    out, offset = [], None
    while True:
        params = {"fields[]": fields, "pageSize": 100, "returnFieldsByFieldId": "true"}
        if offset: params["offset"] = offset
        if formula: params["filterByFormula"] = formula
        r = requests.get(f"https://api.airtable.com/v0/{base}/{table}",
                         headers=_headers(pat), params=params, timeout=30)
        r.raise_for_status()
        d = r.json()
        out.extend(d.get("records", []))
        offset = d.get("offset")
        if not offset: break
        time.sleep(0.2)
    return out


def next_week_range():
    today = date.today()
    mon = today - timedelta(days=today.weekday()) + timedelta(days=7)
    fri = mon + timedelta(days=4)
    return mon, fri


def match_current(item_str, product_cbm):
    """현재 로직 — generate_scm_report.py와 동일."""
    total, matched = 0.0, False
    log_lines = []
    for line in item_str.strip().splitlines():
        line = line.strip()
        if not line: continue
        norm = re.sub(r"\s+", "", line)
        nums = re.findall(r"\d+", norm)
        hit = None
        for prod_norm, cpb in product_cbm:
            if prod_norm in norm:
                qty = int(nums[-1]) if nums else 1
                add = cpb * qty
                total += add
                matched = True
                hit = (prod_norm, cpb, qty, add)
                break
        log_lines.append((line, hit))
    return round(total, 4), log_lines


def main():
    print("[probe] fetching products...")
    prods = fetch_all(TMS_BASE_ID, TBL_PROD, [PF_NAME, PF_CBM, PF_KIT])
    product_cbm = []
    for r in prods:
        c = r["fields"]
        name = (c.get(PF_NAME) or "").strip()
        cbm = c.get(PF_CBM) or c.get(PF_KIT) or None
        if name and cbm:
            try: product_cbm.append((re.sub(r"\s+", "", name), float(cbm)))
            except (ValueError, TypeError): pass
    product_cbm.sort(key=lambda x: -len(x[0]))
    print(f"[probe] {len(product_cbm)} products with CBM loaded")

    mon, fri = next_week_range()
    print(f"[probe] next_week range: {mon} ~ {fri}")
    formula = f"AND(IS_AFTER({{출하확정일}},'{(mon-timedelta(days=1)).isoformat()}'),IS_BEFORE({{출하확정일}},'{(fri+timedelta(days=1)).isoformat()}'))"
    ships = fetch_all(TMS_BASE_ID, TBL_SHIP,
                      [TF_DATE, TF_ITEM, TF_BOX_PARSED, TF_BOX_MANUAL, TF_TOTAL_CBM],
                      formula)
    print(f"[probe] next_week shipments: {len(ships)}\n")

    n_manual = n_box = n_match = n_unmatched = 0
    total_est = 0.0
    unmatched_lines = Counter()

    for rec in ships:
        f = rec["fields"]
        d = f.get(TF_DATE, "")
        man = f.get(TF_TOTAL_CBM)
        box = f.get(TF_BOX_PARSED) or f.get(TF_BOX_MANUAL) or ""
        if isinstance(box, list): box = ", ".join(str(x) for x in box)
        box = box.strip()
        item = f.get(TF_ITEM) or ""

        if man and man > 0:
            n_manual += 1
            total_est += float(man)
            continue
        if box and _BOX_RE.search(box):
            n_box += 1
            continue

        # → product matching path
        est, log = match_current(item, product_cbm)
        if est > 0:
            n_match += 1
            total_est += est
        else:
            n_unmatched += 1

        print(f"--- {d} | manual={man} box='{box}' | est={est}")
        if not item.strip():
            print(f"    [EMPTY ITEM FIELD]")
            unmatched_lines["[EMPTY]"] += 1
        for line, hit in log:
            if hit:
                p, cpb, q, add = hit
                print(f"    [MATCH] '{line}' → '{p}' x{q} @ {cpb} = {add:.4f}")
            else:
                print(f"    [FAIL ] '{line}'")
                unmatched_lines[line[:80]] += 1
        print()

    print("=" * 60)
    print(f"manual={n_manual}, box_parse={n_box}, product_match={n_match}, unmatched={n_unmatched}")
    print(f"total est CBM = {total_est:.3f} m³")
    print(f"\nTOP 15 unmatched lines:")
    for ln, c in unmatched_lines.most_common(15):
        print(f"  {c:3d}× {ln}")


if __name__ == "__main__":
    sys.exit(main() or 0)
