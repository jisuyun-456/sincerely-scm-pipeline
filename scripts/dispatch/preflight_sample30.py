"""Sub-Spec 2 Task 0 Step 3 — Pre-flight sample 30 dry-run.

Loads Product lookup (344 records), fetches 30 most recent Shipments with
text content, runs parse_product_lines + match_product, and reports baseline
line-level match rate + shipment-level confidence distribution.

Output: JSON to stdout. Caller redirects/transforms to markdown report.
"""
import json
import os
import sys

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
load_dotenv()

from harness.settlement.cbm_calc import (
    load_product_lookup,
    match_product,
    parse_product_lines,
)

PAT = os.environ.get("AIRTABLE_PAT")
if not PAT:
    sys.exit("ERROR: AIRTABLE_PAT not set")

HEADERS = {"Authorization": f"Bearer {PAT}"}

TMS_BASE = "app4x70a8mOrIKsMf"
TBL_SHIP = "tbllg1JoHclGYer7m"
FLD_FINAL_OUT_TEXT = "fldgSupj5XLjJXYQo"
FLD_FINAL_POST_TEXT = "fldXXnGOXkm90snKn"
FLD_TOTAL_CBM = "fldJ9DHjwoRyeUEqE"
FLD_CONFIRM_DATE = "fldQvmEwwzvQW95h9"
FLD_SC_ID = "fldBUwhBlhOMsJZdv"


def main():
    print("Loading Product lookup...", file=sys.stderr)
    lookup = load_product_lookup(HEADERS)
    unique = {v["rec_id"]: v for v in lookup.values()}
    zero_cbm = sum(1 for e in unique.values() if e["cbm_per_box"] <= 0)
    print(f"  unique entries: {len(unique)}, lookup keys: {len(lookup)}, "
          f"cbm=0 post-fallback: {zero_cbm}", file=sys.stderr)

    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_SHIP}"
    params = {
        "returnFieldsByFieldId": "true",
        "fields[]": [FLD_FINAL_OUT_TEXT, FLD_FINAL_POST_TEXT,
                     FLD_TOTAL_CBM, FLD_CONFIRM_DATE, FLD_SC_ID],
        "pageSize": 100,
        "sort[0][field]": FLD_CONFIRM_DATE,
        "sort[0][direction]": "desc",
    }
    r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    records = r.json().get("records", [])

    ships = []
    for rec in records:
        f = rec["fields"]
        if not (f.get(FLD_FINAL_OUT_TEXT) or f.get(FLD_FINAL_POST_TEXT)):
            continue
        ships.append(rec)
        if len(ships) >= 30:
            break
    print(f"  Sampled shipments: {len(ships)}", file=sys.stderr)

    total_lines = 0
    matched_lines = 0
    confidences = []
    per_ship = []
    unmatched_all = []
    for rec in ships:
        f = rec["fields"]
        post_text = (f.get(FLD_FINAL_POST_TEXT) or "").strip()
        pre_text = (f.get(FLD_FINAL_OUT_TEXT) or "").strip()
        text = post_text or pre_text
        mode = "임가공_후" if post_text else "임가공_전"
        lines = parse_product_lines(text)
        n_lines = len(lines)
        n_matched = 0
        n_qty_zero = 0
        unmatched = []
        for name, qty in lines:
            if qty == 0:
                n_qty_zero += 1
            _, entry, score = match_product(name, lookup)
            if entry is not None and score >= 0.4:
                n_matched += 1
            else:
                unmatched.append(name)
        total_lines += n_lines
        matched_lines += n_matched
        conf = (n_matched / n_lines) if n_lines > 0 else 0.0
        confidences.append(conf)
        per_ship.append({
            "sc_id": f.get(FLD_SC_ID, ""),
            "mode": mode,
            "total_cbm": f.get(FLD_TOTAL_CBM, 0) or 0,
            "n_lines": n_lines,
            "n_matched": n_matched,
            "n_qty_zero": n_qty_zero,
            "confidence": round(conf, 2),
            "text_preview": text[:80].replace("\n", " ") + ("..." if len(text) > 80 else ""),
            "unmatched": unmatched,
        })
        unmatched_all.extend(unmatched)

    out = {
        "product_lookup": {
            "total_records_table": 344,
            "unique_entries_loaded": len(unique),
            "lookup_keys": len(lookup),
            "cbm_zero_post_fallback": zero_cbm,
            "cbm_zero_ratio": round(zero_cbm / len(unique), 4) if unique else 0,
        },
        "shipment_sample": {
            "n_shipments": len(ships),
            "total_lines": total_lines,
            "matched_lines": matched_lines,
            "line_match_rate": round(matched_lines / total_lines, 4) if total_lines else 0,
            "avg_confidence": round(sum(confidences) / len(confidences), 4) if confidences else 0,
            "shipments_conf_ge_0.7": sum(1 for c in confidences if c >= 0.7),
            "shipments_conf_lt_0.4": sum(1 for c in confidences if c < 0.4),
        },
        "per_ship": per_ship,
        "unmatched_top_unique": sorted(set(unmatched_all))[:50],
    }
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
