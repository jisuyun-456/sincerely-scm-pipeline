"""Probe v2: simulate the NEW match_cbm_from_product on next_week."""
from __future__ import annotations
import os, re, sys, time
from datetime import date, timedelta
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
_VARIANT_TAIL_RE = re.compile(r"(키트|세트|단품|XXL|2XL|XL|[SML])$")


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


def _bigram_dice(a, b):
    if len(a) < 2 or len(b) < 2: return 0.0
    A = {a[i:i+2] for i in range(len(a)-1)}
    B = {b[i:i+2] for i in range(len(b)-1)}
    if not A or not B: return 0.0
    return 2*len(A & B) / (len(A) + len(B))


def _find_product_cbm(line_norm, base, product_cbm, debug=False):
    for pn, cbm in product_cbm:
        if pn and pn in line_norm:
            if debug: print(f"      [A:substr] {pn} → {cbm}")
            return cbm, ("A", pn)
    if base and len(base) >= 3:
        bcands = [(pn, cbm) for pn, cbm in product_cbm if pn and base in pn]
        if bcands:
            avg = sum(c for _, c in bcands) / len(bcands)
            if debug: print(f"      [B:reverse {len(bcands)}] avg={avg:.5f} from {[p for p,_ in bcands[:3]]}")
            return avg, ("B", bcands[0][0])
    if base and len(base) >= 4:
        best_sc = 0.0; best_pn = None
        for pn, _ in product_cbm:
            if len(pn) < 4: continue
            sc = _bigram_dice(base, pn)
            if sc > best_sc: best_sc, best_pn = sc, pn
        if best_sc >= 0.75 and best_pn is not None:
            band = best_sc - 0.05
            cands = [(pn, cbm) for pn, cbm in product_cbm
                     if pn and _bigram_dice(base, pn) >= band]
            if cands:
                avg = sum(c for _, c in cands) / len(cands)
                if debug: print(f"      [C:fuzzy {best_sc:.2f}] avg={avg:.5f} from {[p for p,_ in cands[:3]]}")
                return avg, ("C", best_pn)
    return None, None


def match_v2(item_str, product_cbm, debug=False):
    total, matched = 0.0, False
    for line in item_str.strip().splitlines():
        line = line.strip()
        if not line: continue
        norm = re.sub(r"\s+", "", line)
        nums = re.findall(r"\d+", norm)
        qty  = int(nums[-1]) if nums else 1
        base = re.sub(r"\d+$", "", norm)
        for _ in range(3):
            new = _VARIANT_TAIL_RE.sub("", base)
            if new == base: break
            base = new
        if debug: print(f"    LINE '{line}' qty={qty} base='{base}'")
        cbm, info = _find_product_cbm(norm, base, product_cbm, debug=debug)
        if cbm is not None:
            total += cbm * qty
            matched = True
        elif debug:
            print(f"      [FAIL] no match")
    return round(total, 4) if matched else 0.0


def main():
    print("[v2] fetching products...")
    prods = fetch(TMS_BASE_ID, TBL_PROD, [PF_NAME, PF_CBM, PF_KIT])
    product_cbm = []
    for r in prods:
        c = r["fields"]
        nm = (c.get(PF_NAME) or "").strip()
        cbm = c.get(PF_CBM) or c.get(PF_KIT) or None
        if nm and cbm:
            try: product_cbm.append((re.sub(r"\s+", "", nm), float(cbm)))
            except (ValueError, TypeError): pass
    product_cbm.sort(key=lambda x: -len(x[0]))
    print(f"  {len(product_cbm)} products loaded\n")

    mon = date.today() - timedelta(days=date.today().weekday()) + timedelta(days=7)
    fri = mon + timedelta(days=4)
    formula = (f"AND(IS_AFTER({{출하확정일}},'{(mon-timedelta(days=1)).isoformat()}'),"
               f"IS_BEFORE({{출하확정일}},'{(fri+timedelta(days=1)).isoformat()}'))")
    ships = fetch(TMS_BASE_ID, TBL_SHIP,
                  [TF_DATE, TF_ITEM, TF_BOX_PARSED, TF_BOX_MANUAL, TF_TOTAL_CBM],
                  formula)

    nm = nb = npm = nu = 0
    total = 0.0
    for rec in ships:
        f = rec["fields"]
        man = f.get(TF_TOTAL_CBM)
        if man and man > 0:
            nm += 1; total += float(man); continue
        box = f.get(TF_BOX_PARSED) or f.get(TF_BOX_MANUAL) or ""
        if isinstance(box, list): box = ", ".join(str(x) for x in box)
        if box.strip() and _BOX_RE.search(box.strip()):
            nb += 1; continue
        item = f.get(TF_ITEM) or ""
        if not item.strip():
            nu += 1; continue

        print(f"--- {f.get(TF_DATE)}")
        est = match_v2(item, product_cbm, debug=True)
        print(f"    → est={est:.4f}\n")
        if est > 0:
            npm += 1; total += est
        else:
            nu += 1

    print("=" * 60)
    print(f"manual={nm}, box_parse={nb}, product_match={npm}, unmatched={nu}")
    print(f"TOTAL EST CBM = {total:.3f} m³  (cap=44.4, pct={total/44.4*100:.1f}%)")


if __name__ == "__main__":
    sys.exit(main() or 0)
