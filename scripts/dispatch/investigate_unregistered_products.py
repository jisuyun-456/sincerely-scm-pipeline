"""Sub-Spec 2 backfill investigation.

Fetch large Shipment sample → run parse_v2 → for unmatched product names,
aggregate per-product stats from Shipment fields (Total_CBM, 최종 외박스 수량 값)
to infer Product specs (qty_per_box, box type).

Heuristic:
- If shipment has ONLY ONE parsed line (single-product) AND Total_CBM > 0
  AND box_count > 0:
    cbm_per_box  = Total_CBM / box_count
    qty_per_box  = qty / box_count
- Map cbm_per_box back to box type via BOX_TYPE_TO_CBM_M3 reverse lookup.
- Aggregate across multiple shipments for confidence.

Output: JSON report.
"""
import json
import os
import sys
from collections import defaultdict

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
load_dotenv()

from harness.settlement.cbm_calc import (
    BOX_TYPE_TO_CBM_M3,
    load_product_lookup,
    match_product,
)
from harness.dispatch.cbm_estimator import parse_product_lines_v2

PAT = os.environ.get("AIRTABLE_PAT")
if not PAT:
    sys.exit("ERROR: AIRTABLE_PAT not set")

HEADERS = {"Authorization": f"Bearer {PAT}"}

TMS_BASE = "app4x70a8mOrIKsMf"
TBL_SHIP = "tbllg1JoHclGYer7m"
FLD_FINAL_OUT_TEXT = "fldgSupj5XLjJXYQo"  # 최종 출하 품목
FLD_FINAL_POST_TEXT = "fldXXnGOXkm90snKn"  # 최종 출고 품목 및 수량
FLD_TOTAL_CBM = "fldJ9DHjwoRyeUEqE"
FLD_BOX_COUNT_FINAL = "fldTjLDmw5sNGszeD"  # 최종 외박스 수량 값 (formula)
FLD_CONFIRM_DATE = "fldQvmEwwzvQW95h9"
FLD_SC_ID = "fldBUwhBlhOMsJZdv"

# Reverse map: cbm value → box type (for inference)
CBM_TO_BOX_TYPE = {v: k for k, v in BOX_TYPE_TO_CBM_M3.items()}


def _nearest_box_type(cbm_per_box: float) -> tuple[str, float, float]:
    """Return (box_type, official_cbm, abs_diff_ratio)."""
    if cbm_per_box <= 0:
        return ("?", 0.0, 1.0)
    best_type, best_diff = "?", float("inf")
    for box_type, official in BOX_TYPE_TO_CBM_M3.items():
        diff = abs(cbm_per_box - official) / official
        if diff < best_diff:
            best_diff = diff
            best_type = box_type
    return (best_type, BOX_TYPE_TO_CBM_M3[best_type], best_diff)


def main():
    print("Loading Product lookup...", file=sys.stderr)
    lookup = load_product_lookup(HEADERS)

    print("Fetching shipments (paginated)...", file=sys.stderr)
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_SHIP}"
    records = []
    offset = None
    page = 0
    while page < 5:  # up to 500 records
        params = {
            "returnFieldsByFieldId": "true",
            "fields[]": [FLD_FINAL_OUT_TEXT, FLD_FINAL_POST_TEXT,
                         FLD_TOTAL_CBM, FLD_BOX_COUNT_FINAL,
                         FLD_CONFIRM_DATE, FLD_SC_ID],
            "pageSize": 100,
            "sort[0][field]": FLD_CONFIRM_DATE,
            "sort[0][direction]": "desc",
        }
        if offset:
            params["offset"] = offset
        r = requests.get(url, headers=HEADERS, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        page += 1
        if not offset:
            break
    print(f"  Fetched {len(records)} shipments", file=sys.stderr)

    # Per-product evidence
    evidence = defaultdict(list)
    multi_evidence = defaultdict(list)
    for rec in records:
        f = rec["fields"]
        post_text = (f.get(FLD_FINAL_POST_TEXT) or "").strip()
        pre_text = (f.get(FLD_FINAL_OUT_TEXT) or "").strip()
        text = post_text or pre_text
        if not text:
            continue
        lines = parse_product_lines_v2(text)
        try:
            total_cbm = float(f.get(FLD_TOTAL_CBM) or 0)
        except (TypeError, ValueError):
            total_cbm = 0.0
        try:
            box_count = float(f.get(FLD_BOX_COUNT_FINAL) or 0)
        except (TypeError, ValueError):
            box_count = 0.0
        sc_id = f.get(FLD_SC_ID, "")

        # Single-product shipments — highest signal
        if len(lines) == 1:
            name, qty, _extra = lines[0]
            _, entry, score = match_product(name, lookup)
            if entry is None or score < 0.4:
                evidence[name].append({
                    "sc_id": sc_id,
                    "qty": qty,
                    "total_cbm": total_cbm,
                    "box_count": box_count,
                    "qty_per_box": qty / box_count if box_count > 0 and qty > 0 else None,
                    "cbm_per_box": total_cbm / box_count if box_count > 0 and total_cbm > 0 else None,
                })
        else:
            # Multi-product: only record the unmatched names (no inference possible)
            for name, qty, _extra in lines:
                _, entry, score = match_product(name, lookup)
                if entry is None or score < 0.4:
                    multi_evidence[name].append({
                        "sc_id": sc_id,
                        "qty": qty,
                        "n_total_lines": len(lines),
                    })

    # Aggregate
    summary = {}
    for name, evs in evidence.items():
        with_box = [e for e in evs if e["box_count"] > 0]
        with_cbm = [e for e in evs if e["cbm_per_box"] is not None]
        qty_per_boxes = [e["qty_per_box"] for e in with_box if e["qty_per_box"]]
        cbm_per_boxes = [e["cbm_per_box"] for e in with_cbm]
        avg_qty_per_box = sum(qty_per_boxes) / len(qty_per_boxes) if qty_per_boxes else None
        avg_cbm_per_box = sum(cbm_per_boxes) / len(cbm_per_boxes) if cbm_per_boxes else None
        box_type, official_cbm, diff_ratio = _nearest_box_type(avg_cbm_per_box) if avg_cbm_per_box else ("?", 0, 1)
        summary[name] = {
            "n_shipments_single": len(evs),
            "n_with_box_count": len(with_box),
            "n_with_total_cbm": len(with_cbm),
            "avg_qty_per_box": round(avg_qty_per_box, 1) if avg_qty_per_box else None,
            "avg_cbm_per_box": round(avg_cbm_per_box, 4) if avg_cbm_per_box else None,
            "inferred_box_type": box_type,
            "official_cbm_for_type": official_cbm,
            "diff_ratio_vs_official": round(diff_ratio, 3),
            "n_shipments_multi": len(multi_evidence.get(name, [])),
            "samples": evs[:5],
        }

    # Also names that appear ONLY in multi-product shipments
    for name in multi_evidence:
        if name not in summary:
            summary[name] = {
                "n_shipments_single": 0,
                "n_shipments_multi": len(multi_evidence[name]),
                "samples": multi_evidence[name][:5],
            }

    out = {
        "fetched_records": len(records),
        "unique_unmatched_products": len(summary),
        "products": dict(sorted(summary.items(),
                                key=lambda kv: kv[1].get("n_shipments_single", 0)
                                + kv[1].get("n_shipments_multi", 0),
                                reverse=True)),
    }
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
