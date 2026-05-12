"""
Total_CBM 안전 소급 백필.

- 대상: 전체 Shipment 중 Total_CBM = 0 또는 미입력인 건
- 상하차비용(F_UNLOAD)은 절대 수정하지 않음
- 계산: 임가공 품목(F_ITEMS_MFG) → 최종 출하 품목(F_PRODUCT_FINAL) 순으로 cbm_calc 사용

Usage:
  py scripts/backfill/backfill_total_cbm_safe.py --dry-run
  py scripts/backfill/backfill_total_cbm_safe.py
  py scripts/backfill/backfill_total_cbm_safe.py --start 2025-01-01
"""
import argparse
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "harness" / "settlement"))
from cbm_calc import load_product_lookup, calc_from_products

load_dotenv()
PAT = os.environ.get("AIRTABLE_PAT", "")
TMS_BASE = "app4x70a8mOrIKsMf"
TBL_SHIPMENT = "tbllg1JoHclGYer7m"

F_SC_ID        = "fldBUwhBlhOMsJZdv"
F_DATE         = "fldQvmEwwzvQW95h9"
F_TOTAL_CBM    = "fldJ9DHjwoRyeUEqE"
F_ITEMS_MFG    = "fldCnwsVrpkKHt4Hl"
F_PRODUCT_FINAL = "fldgSupj5XLjJXYQo"


def _str(raw) -> str:
    if isinstance(raw, list):
        return str(raw[0] or "").strip() if raw else ""
    return str(raw or "").strip()


def fetch_empty_cbm_records(headers: dict, start: str, end: str) -> list[dict]:
    """Total_CBM = 0 또는 blank 인 Shipment 전체 조회."""
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_SHIPMENT}"
    end_excl = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    formula = f"AND({{출하확정일}}>='{start}',{{출하확정일}}<'{end_excl}')"
    records: list[dict] = []
    cursor = None
    while True:
        params: dict = {
            "filterByFormula": formula,
            "returnFieldsByFieldId": "true",
            "fields[]": [F_SC_ID, F_DATE, F_TOTAL_CBM, F_ITEMS_MFG, F_PRODUCT_FINAL],
            "pageSize": 100,
        }
        if cursor:
            params["offset"] = cursor
        r = requests.get(url, headers=headers, params=params, timeout=30)
        if not r.ok:
            raise RuntimeError(f"Airtable {r.status_code}: {r.text[:200]}")
        data = r.json()
        for rec in data.get("records", []):
            f = rec["fields"]
            try:
                cbm_val = float(f.get(F_TOTAL_CBM) or 0)
            except (ValueError, TypeError):
                cbm_val = 0.0
            if cbm_val <= 0:
                records.append(rec)
        cursor = data.get("offset")
        if not cursor:
            break
        time.sleep(0.2)
    return records


def run(headers: dict, start: str, end: str, dry_run: bool) -> None:
    print("Product 룩업 로딩 중...")
    lookup = load_product_lookup(headers)
    print(f"  {len(lookup) // 2}개 품목 로드 완료\n")

    print(f"Total_CBM 미입력 Shipment 조회 중 ({start} ~ {end})...")
    records = fetch_empty_cbm_records(headers, start, end)
    print(f"  {len(records)}건 대상\n")

    filled = skipped = errors = 0
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_SHIPMENT}"

    for rec in records:
        f = rec["fields"]
        sc_id = _str(f.get(F_SC_ID))
        date_val = (_str(f.get(F_DATE)) or "")[:10]

        items_text = _str(f.get(F_ITEMS_MFG)) or _str(f.get(F_PRODUCT_FINAL))
        if not items_text:
            skipped += 1
            continue

        result = calc_from_products(items_text, lookup)
        total_cbm = result["total_cbm"]

        if total_cbm <= 0:
            skipped += 1
            continue

        if dry_run:
            matched = [m["matched_key"] for m in result["matched"]]
            print(f"  {sc_id:<13} {date_val}  cbm={total_cbm:.4f}  matched={matched}")
            filled += 1
        else:
            r = requests.patch(
                f"{url}/{rec['id']}",
                headers=headers,
                json={"fields": {F_TOTAL_CBM: round(total_cbm, 4)}},
                timeout=15,
            )
            time.sleep(0.25)
            if r.ok:
                filled += 1
            else:
                errors += 1
                print(f"  ERROR {sc_id} ({rec['id']}): {r.status_code} {r.text[:80]}")

    label = "[DRY-RUN] " if dry_run else ""
    print(f"\n{label}결과: filled={filled}  skipped={skipped}  errors={errors}")
    print("(상하차비용은 수정하지 않음)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start",   default="2024-01-01")
    parser.add_argument("--end",     default=date.today().isoformat())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not PAT:
        print("ERROR: AIRTABLE_PAT not set")
        return

    headers = {
        "Authorization": f"Bearer {PAT}",
        "Content-Type": "application/json",
    }
    run(headers, args.start, args.end, args.dry_run)


if __name__ == "__main__":
    main()
