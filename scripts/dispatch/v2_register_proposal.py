"""V2 registration proposal — infer Product specs for the 12 unregistered real
견적코드 surfaced by the cascade S5 step (출하CBM 미산출).

Authoritative gap list = S5 `unmatched=[CODE]` aggregated from
data/order_cascade/report_20260612-2353.json. Of 19 codes, 5 are service/
placeholder (filtered) and 2~3 are 재제작 edge cases; the 12 below are real
products needing TMS Product registration.

For each target the script scans historical Shipment records, isolates
SINGLE-product shipments whose parsed product name matches the target, reads the
외박스 수량 직접입력 box-type breakdown, and infers:
    box_type     = most common single-box-type label
    qty_per_box  = mean(qty / total_box_count)
    cbm_per_box  = BOX_TYPE_TO_CBM_M3[box_type]
CBM validation compares total_box_count * cbm_per_box against Total_CBM.

Output: per-code proposal JSON for human review BEFORE any write.
NO writes — read-only.
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
load_dotenv()

from harness.settlement.cbm_calc import BOX_TYPE_TO_CBM_M3, BOX_TYPE_TO_SIZE_STR
from harness.dispatch.cbm_estimator import parse_product_lines_v2

PAT = os.environ.get("AIRTABLE_PAT")
HEADERS = {"Authorization": f"Bearer {PAT}"}
TMS_BASE = "app4x70a8mOrIKsMf"
TBL_SHIP = "tbllg1JoHclGYer7m"

FLD = {
    "pre_text": "fldgSupj5XLjJXYQo",   # 최종 출하 품목
    "post_text": "fldXXnGOXkm90snKn",  # 최종 출고 품목 및 수량
    "total_cbm": "fldJ9DHjwoRyeUEqE",
    "box_text": "fldRjMaXa5TdSsGDL",   # 외박스 수량 (직접입력)
    "confirm_date": "fldQvmEwwzvQW95h9",
    "sc_id": "fldBUwhBlhOMsJZdv",
}

# 12 real products: 견적코드 -> canonical 굿즈명 (from cascade S5 unmatched goods).
TARGETS = {
    "DRCG": "Solid 스탠다드 G형박스",
    "STTB": "스탠드-업 칫솔",
    "LOPU": "로고스트랩 파우치",
    "BCTW": "굿이너프 비치타월",
    "OFMP": "오피스 마우스패드",
    "TWKF": "Lite 스트랩 박스",
    "BSPK": "비스포크",
    "SZBT": "Simple 슬라이드 지퍼백",
    "UMUG": "컴포트 스텐머그",
    "SLVB": "Quality 슬리브박스",
    "VMCB": "밸류 메모큐브",
    "BMVS": "브릭 메모&캘린더 스탠드 2.0",
    # 광역 윈도우(May~Jun) 신규 발견 실품목 4종
    "RCPC": "Raw 코튼 파우치",
    "DSKT": "데스크테리어 매트",
    "CNPB": "컬러풀노트패드(블랙)",
    "WCCV": "웹캠 커버",
}

BOX_TOKEN = re.compile(r"(극소|중대|특대|중|대)(\d+)")
_CANON = {"극소": "극소형", "중대": "중대형", "특대": "특대형", "중": "중형", "대": "대형"}


def parse_box_text(text: str) -> dict:
    if not text:
        return {}
    text = re.sub(r"/.*$", "", text)  # drop '/ 총N박스' tail
    out = {}
    for m in BOX_TOKEN.finditer(text):
        out[_CANON[m.group(1)]] = out.get(_CANON[m.group(1)], 0) + int(m.group(2))
    return out


def norm(s: str) -> str:
    """Normalize for matching: drop [n] suffix, '키트', whitespace; lowercase."""
    s = re.sub(r"\[\d+\]", "", s)
    s = s.replace("키트", "")
    s = re.sub(r"\s+", "", s)
    return s.lower()


def name_matches(parsed: str, target: str) -> bool:
    a, b = norm(parsed), norm(target)
    if not a or not b:
        return False
    return b in a or a in b


def fetch_shipments(max_pages: int) -> list:
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_SHIP}"
    records, offset = [], None
    for _ in range(max_pages):
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
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-pages", type=int, default=15)
    args = ap.parse_args()
    if not PAT:
        sys.exit("ERROR: AIRTABLE_PAT not set")

    print(f"Fetching shipments (up to {args.max_pages*100})...", file=sys.stderr)
    records = fetch_shipments(args.max_pages)
    print(f"  Fetched {len(records)} shipments", file=sys.stderr)

    # code -> list of evidence dicts
    single_ev = defaultdict(list)   # single-product shipments (clean)
    multi_ev = defaultdict(list)    # multi-product (weak — no box attribution)

    for rec in records:
        f = rec["fields"]
        text = (f.get(FLD["post_text"]) or f.get(FLD["pre_text"]) or "").strip()
        if not text:
            continue
        lines = parse_product_lines_v2(text)
        if not lines:
            continue
        sc_id = f.get(FLD["sc_id"])
        try:
            total_cbm = float(f.get(FLD["total_cbm"]) or 0)
        except (TypeError, ValueError):
            total_cbm = 0.0
        boxes = parse_box_text(f.get(FLD["box_text"]) or "")

        single = len(lines) == 1
        for name, qty, _extra in lines:
            for code, target in TARGETS.items():
                if not name_matches(name, target):
                    continue
                if single:
                    single_ev[code].append({
                        "sc_id": sc_id, "parsed_name": name, "qty": qty,
                        "total_cbm": total_cbm, "boxes": boxes,
                        "total_box_count": sum(boxes.values()),
                        "single_box_type": next(iter(boxes)) if len(boxes) == 1 else None,
                    })
                else:
                    multi_ev[code].append({
                        "sc_id": sc_id, "parsed_name": name, "qty": qty,
                        "n_lines": len(lines),
                    })

    proposals = {}
    for code, target in TARGETS.items():
        evs = single_ev.get(code, [])
        single_typed = [e for e in evs if e["single_box_type"] and e["qty"] > 0
                        and e["total_box_count"] > 0]
        prop = {
            "견적코드": code,
            "굿즈명": target,
            "n_single_product_shipments": len(evs),
            "n_clean_box_evidence": len(single_typed),
            "n_multi_product_shipments": len(multi_ev.get(code, [])),
        }
        if single_typed:
            types = [e["single_box_type"] for e in single_typed]
            box_type = max(set(types), key=types.count)
            typed = [e for e in single_typed if e["single_box_type"] == box_type]
            qpb_vals = [e["qty"] / e["total_box_count"] for e in typed]
            avg_qpb = sum(qpb_vals) / len(qpb_vals)
            cbm_per_box = BOX_TYPE_TO_CBM_M3.get(box_type, 0.0)
            cbm_val = []
            for e in typed:
                if e["total_cbm"] > 0:
                    expected = e["total_box_count"] * cbm_per_box
                    cbm_val.append({
                        "sc_id": e["sc_id"],
                        "expected_cbm": round(expected, 4),
                        "actual_cbm": e["total_cbm"],
                        "match_ratio": round(expected / e["total_cbm"], 3),
                    })
            ratios = [c["match_ratio"] for c in cbm_val]
            prop.update({
                "inferred_box_type": box_type,
                "box_type_votes": {t: types.count(t) for t in set(types)},
                "inferred_qty_per_box": int(round(avg_qpb)),
                "qty_per_box_observations": [round(v, 1) for v in qpb_vals],
                "cbm_per_box": cbm_per_box,
                "box_size_str": BOX_TYPE_TO_SIZE_STR.get(box_type, ""),
                "cbm_validation": cbm_val,
                "cbm_match_median": round(sorted(ratios)[len(ratios) // 2], 3) if ratios else None,
                "matched_names": sorted({e["parsed_name"] for e in typed}),
            })
        else:
            prop["matched_names"] = sorted({e["parsed_name"] for e in evs}) or \
                sorted({e["parsed_name"] for e in multi_ev.get(code, [])})
            prop["recommendation"] = "needs_user_input"
        proposals[code] = prop

    out = {
        "n_targets": len(TARGETS),
        "fetched_shipments": len(records),
        "proposals": proposals,
    }
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
