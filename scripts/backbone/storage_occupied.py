"""P3' Task 3 — 보관 occupied CBM 분자 리포트 (report-only, 쓰기 0).

WMS_InventoryLedger.Current_Stock × ItemMaster.CBM_개당_m3 → Warehouse별 occupied.
분모(Max_CBM)는 사용자 실측 도착 시: --max-cbm-seed '{"베스트원": 120, ...}' 로 주입
시 점유율까지 출력. (WMS_Location Max_CBM 필드 신설은 실측 도착 후 1회 — spec §4,
TMS Location.Max_CBM은 다른 물리량이므로 재사용 금지.)

Usage:
  python scripts/backbone/storage_occupied.py
  python scripts/backbone/storage_occupied.py --max-cbm-seed '{"베스트원":120.0}'
"""
import argparse
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.backbone.storage import (  # noqa: E402
    aggregate_occupied,
    parse_pt_from_ledger_key,
)

load_dotenv()
WP = os.environ["AIRTABLE_WMS_PAT"]
WMS = "appLui4ZR5HWcQRri"
ITEM = "tbl5ZGY373D5SCONV"     # WMS_ItemMaster
LEDGER = "tbl4DcXQRHJj921MN"   # WMS_InventoryLedger
LOC = "tblRwUTP5kWnHFt5P"      # WMS_Location


def fetch(tid, fields):
    out, off = [], None
    while True:
        p = {"pageSize": 100, "fields[]": fields}
        if off:
            p["offset"] = off
        r = requests.get(
            f"https://api.airtable.com/v0/{WMS}/{tid}",
            headers={"Authorization": f"Bearer {WP}"}, params=p, timeout=60,
        )
        r.raise_for_status()
        d = r.json()
        out += d["records"]
        off = d.get("offset")
        if not off:
            break
    return out


def main():
    ap = argparse.ArgumentParser(description="보관 occupied CBM 분자 리포트")
    ap.add_argument("--max-cbm-seed", help='Warehouse별 Max_CBM JSON (예: {"베스트원":120.0})')
    args = ap.parse_args()
    seed = json.loads(args.max_cbm_seed) if args.max_cbm_seed else {}

    print("로딩: InventoryLedger / Location / ItemMaster...")
    locs = {r["id"]: r["fields"] for r in fetch(LOC, ["Warehouse", "Zone_Type"])}
    items = fetch(ITEM, ["품목키", "CBM_개당_m3"])
    part_cbm = {r["fields"]["품목키"]: r["fields"]["CBM_개당_m3"]
                for r in items
                if (r["fields"].get("CBM_개당_m3") or 0) > 0
                and parse_pt_from_ledger_key(str(r["fields"].get("품목키", "")))}
    ledger = fetch(LEDGER, ["Ledger_Key", "Current_Stock", "Location", "Stock_Type"])
    print(f"  ledger {len(ledger)}행 / location {len(locs)} / part CBM {len(part_cbm)}PT")

    rows, n_no_pt = [], 0
    for rec in ledger:
        f = rec.get("fields", {})
        pt = parse_pt_from_ledger_key(str(f.get("Ledger_Key", "")))
        if not pt:
            n_no_pt += 1
            continue
        loc_ids = f.get("Location") or []
        loc = locs.get(loc_ids[0], {}) if loc_ids else {}
        rows.append({
            "pt": pt,
            "stock": f.get("Current_Stock") or 0,
            "warehouse": loc.get("Warehouse") or "미지정",
            "zone_type": loc.get("Zone_Type") or "",
            "stock_type": f.get("Stock_Type") or "",
        })

    out = aggregate_occupied(rows, part_cbm)

    print("\n=== 보관 occupied CBM 분자 (STORAGE·UNRESTRICTED) ===")
    print(f"ledger PT행 {len(rows)} (비PT 키 제외 {n_no_pt}) → 필터 후 {out['n_rows_filtered']}행")
    for wh, e in sorted(out["by_warehouse"].items()):
        line = (f"  {wh}: occupied {e['occupied_cbm']:.4f} m³ | {e['n_rows']}행 | "
                f"PT 해소 {e['pt_covered']} / 미해소 {e['pt_uncovered']}"
                f" (미해소 재고 {e['stock_uncovered']:.0f}개)")
        if wh in seed and seed[wh] > 0:
            line += f" | 점유율 {e['occupied_cbm'] / seed[wh] * 100:.1f}% (Max {seed[wh]} m³)"
        print(line)
    print(f"합계 occupied: {out['total_occupied_cbm']:.4f} m³ | "
          f"PT 커버리지 {out['pt_coverage_pct']}%")
    if not seed:
        print("[Max_CBM 미주입 — 점유율 보류] 실측 도착 시 --max-cbm-seed 로 주입")
    if out["uncovered_pts"]:
        print(f"미해소 PT ({len(out['uncovered_pts'])}): "
              + ", ".join(out["uncovered_pts"][:20])
              + (" ..." if len(out["uncovered_pts"]) > 20 else ""))


if __name__ == "__main__":
    main()
