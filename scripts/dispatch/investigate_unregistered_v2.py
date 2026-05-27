"""Sub-Spec 2 backfill investigation v2 — parse 외박스 수량 직접입력 text.

Text format observed: '중대172 / 총 172박스', '중1,중대172,대1 / 총174박스'
Pattern: (극소|중대|특대|대|중)(\\d+) box-type-prefix + count.

For SINGLE-product shipments with SINGLE box-type breakdown:
  qty_per_box   = qty / box_count
  cbm_per_box   = BOX_TYPE_TO_CBM_M3[box_type]  (known from box-type label)

Aggregate per product across shipments → propose Product record specs.
"""
import json
import os
import re
import sys
from collections import defaultdict

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
load_dotenv()

from harness.settlement.cbm_calc import BOX_TYPE_TO_CBM_M3, load_product_lookup, match_product
from harness.dispatch.cbm_estimator import parse_product_lines_v2

PAT = os.environ.get("AIRTABLE_PAT")
HEADERS = {"Authorization": f"Bearer {PAT}"}
TMS_BASE = "app4x70a8mOrIKsMf"
TBL_SHIP = "tbllg1JoHclGYer7m"

FLD = {
    "pre_text": "fldgSupj5XLjJXYQo",
    "post_text": "fldXXnGOXkm90snKn",
    "total_cbm": "fldJ9DHjwoRyeUEqE",
    "box_text": "fldRjMaXa5TdSsGDL",  # 외박스 수량 (직접입력)
    "confirm_date": "fldQvmEwwzvQW95h9",
    "sc_id": "fldBUwhBlhOMsJZdv",
}

# Ordered most-specific first: 중대 must precede 중/대, 특대 must precede 대.
BOX_TOKEN = re.compile(r"(극소|중대|특대|중|대)(\d+)")


def parse_box_text(text: str) -> dict[str, int]:
    """'중대172,대55 / 총227박스' → {'중대': 172, '대': 55}"""
    if not text:
        return {}
    # Remove '/ 총N박스' tail to avoid double-counting
    text = re.sub(r"/.*$", "", text)
    out = {}
    for m in BOX_TOKEN.finditer(text):
        prefix, count = m.group(1), int(m.group(2))
        # Map to canonical box-type names used in BOX_TYPE_TO_CBM_M3
        canonical = {"극소": "극소형", "중대": "중대형", "특대": "특대형",
                     "중": "중형", "대": "대형"}[prefix]
        out[canonical] = out.get(canonical, 0) + count
    return out


def main():
    print("Loading Product lookup...", file=sys.stderr)
    lookup = load_product_lookup(HEADERS)

    print("Fetching shipments (paginated, up to 1000)...", file=sys.stderr)
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_SHIP}"
    records = []
    offset = None
    for _ in range(10):
        params = {
            "returnFieldsByFieldId": "true",
            "fields[]": list(FLD.values()),
            "pageSize": 100,
            "sort[0][field]": FLD["confirm_date"],
            "sort[0][direction]": "desc",
        }
        if offset:
            params["offset"] = offset
        r = requests.get(url, headers=HEADERS, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    print(f"  Fetched {len(records)} shipments", file=sys.stderr)

    evidence = defaultdict(list)
    for rec in records:
        f = rec["fields"]
        post_text = (f.get(FLD["post_text"]) or "").strip()
        pre_text = (f.get(FLD["pre_text"]) or "").strip()
        text = post_text or pre_text
        if not text:
            continue
        lines = parse_product_lines_v2(text)
        if len(lines) != 1:
            continue  # single-product only for clean inference
        name, qty, _extra = lines[0]
        _, entry, score = match_product(name, lookup)
        if entry is not None and score >= 0.4:
            continue  # already registered
        if qty <= 0:
            continue

        box_text = f.get(FLD["box_text"]) or ""
        boxes = parse_box_text(box_text)
        if not boxes:
            continue  # no box info → skip
        try:
            total_cbm = float(f.get(FLD["total_cbm"]) or 0)
        except (TypeError, ValueError):
            total_cbm = 0.0

        evidence[name].append({
            "sc_id": f.get(FLD["sc_id"]),
            "qty": qty,
            "total_cbm": total_cbm,
            "boxes": boxes,
            "total_box_count": sum(boxes.values()),
            "single_box_type": next(iter(boxes)) if len(boxes) == 1 else None,
        })

    # Aggregate per product
    summary = {}
    for name, evs in evidence.items():
        # Prefer single-box-type evidence
        single_type = [e for e in evs if e["single_box_type"]]
        if single_type:
            # Most common box type
            types = [e["single_box_type"] for e in single_type]
            box_type = max(set(types), key=types.count)
            qty_per_box_vals = [e["qty"] / e["total_box_count"]
                                for e in single_type if e["single_box_type"] == box_type]
            avg_qty_per_box = sum(qty_per_box_vals) / len(qty_per_box_vals)
            cbm_per_box = BOX_TYPE_TO_CBM_M3.get(box_type, 0.0)

            # Sanity: predicted CBM vs actual
            cbm_match = []
            for e in single_type:
                if e["total_cbm"] > 0 and e["single_box_type"] == box_type:
                    expected = e["total_box_count"] * cbm_per_box
                    cbm_match.append({
                        "sc_id": e["sc_id"],
                        "expected_cbm": round(expected, 4),
                        "actual_cbm": e["total_cbm"],
                        "match_ratio": round(expected / e["total_cbm"], 3),
                    })

            summary[name] = {
                "n_shipments": len(evs),
                "n_single_box_type": len(single_type),
                "inferred_box_type": box_type,
                "inferred_qty_per_box": int(round(avg_qty_per_box)),
                "cbm_per_box": cbm_per_box,
                "qty_per_box_observations": [round(v, 1) for v in qty_per_box_vals],
                "cbm_validation": cbm_match,
            }
        else:
            # Mixed box types — record but don't recommend
            summary[name] = {
                "n_shipments": len(evs),
                "n_single_box_type": 0,
                "mixed_evidence": [e for e in evs[:3]],
                "recommendation": "manual_review",
            }

    out = {
        "fetched_records": len(records),
        "n_candidates": len(summary),
        "products": dict(sorted(summary.items(),
                                key=lambda kv: -kv[1].get("n_single_box_type", 0))),
    }
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
