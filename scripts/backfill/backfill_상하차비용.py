"""
박종성 상하차비용 + Total_CBM 소급 백필.

대상: 박종성 담당 전체 Shipment (2024-01~현재) 중 상하차비용=0 또는 미입력.
계산 우선순위:
  1. 최종 외박스 수량 값(F_BOX_TEXT) 있으면 → parse_unload_fee (regex 기반)
  2. F_BOX_TEXT 없으면 → 임가공 품목 및 수량(F_ITEMS_MFG) → cbm_calc
  3. F_ITEMS_MFG 없으면 → 최종 출하 품목(F_PRODUCT_FINAL) → cbm_calc (수량 미상 = 1박스)

안전장치: F_UNLOAD > 0 이면 --force 없이 skip.

Usage:
  py scripts/backfill/backfill_상하차비용.py --dry-run
  py scripts/backfill/backfill_상하차비용.py --start 2024-01-01 --end 2026-12-31
  py scripts/backfill/backfill_상하차비용.py --force   # 기존값 덮어쓰기
"""
import argparse
import os
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

# harness/settlement 를 path 에 추가해 cbm_calc import
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "harness" / "settlement"))
from cbm_calc import load_product_lookup, calc_from_products

load_dotenv()
PAT = os.environ.get("AIRTABLE_PAT", "")
TMS_BASE = "app4x70a8mOrIKsMf"
TBL_SHIPMENT = "tbllg1JoHclGYer7m"
DRIVER_PARK = "recXCfwVTqaoeQ9SS"

F_DATE         = "fldQvmEwwzvQW95h9"
F_PARTNER      = "fldM2u6RwLRrO7ymW"
F_UNLOAD       = "fldxmAZrBGqS7sQoL"   # 상하차비용
F_TOTAL_CBM    = "fldJ9DHjwoRyeUEqE"   # Total_CBM
F_BOX_TEXT     = "fldTjLDmw5sNGszeD"   # 최종 외박스 수량 값 (formula)
F_BOX_DIRECT   = "fldRjMaXa5TdSsGDL"   # 외박스 수량 (직접입력)
F_BOX_QTY      = "fldGXhlBwI6toXSJC"   # 외박스 수량 (rollup)
F_ITEMS_MFG    = "fldCnwsVrpkKHt4Hl"   # 임가공 품목 및 수량 (rollup, has qty)
F_PRODUCT_FINAL = "fldgSupj5XLjJXYQo"  # 최종 출하 품목 (formula, name only)
F_SC_ID        = "fldBUwhBlhOMsJZdv"


def _str(raw) -> str:
    if isinstance(raw, list):
        return str(raw[0] or "").strip() if raw else ""
    return str(raw or "").strip()


def parse_unload_fee(box_text: str) -> int:
    if not box_text:
        return 0
    s = str(box_text)
    try:
        heavy  = int(re.search(r"중대(\d+)", s).group(1)) if re.search(r"중대(\d+)", s) else 0
        large  = int(re.search(r"(?<!중)(?<!특)대(\d+)", s).group(1)) if re.search(r"(?<!중)(?<!특)대(\d+)", s) else 0
        xlarge = int(re.search(r"특대(\d+)", s).group(1)) if re.search(r"특대(\d+)", s) else 0
        return min((heavy // 5) * 5000 + (large // 3) * 5000 + (xlarge // 3) * 5000, 50000)
    except Exception:
        return 0


def fetch_park_records(headers: dict, start: str, end: str) -> list[dict]:
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_SHIPMENT}"
    end_excl = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    formula = (
        f"AND({{출하확정일}}>='{start}',{{출하확정일}}<'{end_excl}',"
        f"NOT({{배송파트너}}=''))"
    )
    records: list[dict] = []
    cursor = None
    while True:
        params: dict = {
            "filterByFormula": formula,
            "returnFieldsByFieldId": "true",
            "fields[]": [F_SC_ID, F_DATE, F_PARTNER, F_UNLOAD, F_TOTAL_CBM,
                         F_BOX_TEXT, F_BOX_DIRECT, F_BOX_QTY,
                         F_ITEMS_MFG, F_PRODUCT_FINAL],
            "pageSize": 100,
        }
        if cursor:
            params["offset"] = cursor
        r = requests.get(url, headers=headers, params=params, timeout=30)
        if not r.ok:
            raise RuntimeError(f"Airtable {r.status_code}: {r.text[:200]}")
        data = r.json()
        for rec in data.get("records", []):
            if DRIVER_PARK in (rec["fields"].get(F_PARTNER) or []):
                records.append(rec)
        cursor = data.get("offset")
        if not cursor:
            break
        time.sleep(0.2)
    return records


def patch_record(headers: dict, rec_id: str, unload: int, total_cbm: float, dry_run: bool) -> bool:
    if dry_run:
        return True
    fields: dict = {F_UNLOAD: unload}
    if total_cbm > 0:
        fields[F_TOTAL_CBM] = round(total_cbm, 4)
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_SHIPMENT}/{rec_id}"
    r = requests.patch(
        url, headers=headers, json={"fields": fields}, timeout=15,
    )
    time.sleep(0.25)
    return r.ok


def run(headers: dict, start: date, end: date, dry_run: bool, force: bool = False) -> dict:
    print(f"Product 룩업 로딩 중...")
    lookup = load_product_lookup(headers)
    print(f"  {len(lookup)//2}개 품목 로드 완료 (name+code 각 키 포함)\n")

    start_s = start.isoformat()
    end_s = end.isoformat()
    print(f"박종성 Shipment 조회 중 ({start_s} ~ {end_s})...")
    records = fetch_park_records(headers, start_s, end_s)
    print(f"  {len(records)}건 조회\n")

    updated = skipped = errors = 0
    cbm_source_counts: dict[str, int] = {"box_text": 0, "cbm_calc": 0, "zero": 0}

    for rec in records:
        f = rec["fields"]
        existing_unload = f.get(F_UNLOAD) or 0

        if existing_unload > 0 and not force:
            skipped += 1
            continue

        sc_id = _str(f.get(F_SC_ID))
        box_text = _str(f.get(F_BOX_TEXT))
        total_cbm = 0.0

        if box_text:
            unload = parse_unload_fee(box_text)
            cbm_source_counts["box_text"] += 1
            src = "box_text"
        else:
            items_text = (
                _str(f.get(F_ITEMS_MFG))
                or _str(f.get(F_PRODUCT_FINAL))
            )
            if items_text and lookup:
                result = calc_from_products(items_text, lookup)
                unload = result["unload_fee"]
                total_cbm = result["total_cbm"]
                cbm_source_counts["cbm_calc"] += 1
                src = "cbm_calc"
            else:
                unload = 0
                cbm_source_counts["zero"] += 1
                src = "zero"

        if not dry_run:
            ok = patch_record(headers, rec["id"], unload, total_cbm, dry_run=False)
            if ok:
                updated += 1
            else:
                errors += 1
                print(f"  ERROR patching {sc_id} ({rec['id']})")
        else:
            updated += 1
            date_val = (f.get(F_DATE) or "")[:10]
            print(f"  {sc_id:<13} {date_val}  unload={unload:>6,}  cbm={total_cbm:.3f}  [{src}]")

    print(f"\n{'[DRY-RUN] ' if dry_run else ''}결과: "
          f"updated={updated}  skipped={skipped}  errors={errors}")
    print(f"  소스: box_text={cbm_source_counts['box_text']}  "
          f"cbm_calc={cbm_source_counts['cbm_calc']}  zero={cbm_source_counts['zero']}")
    return {"updated": updated, "skipped": skipped, "errors": errors}


def main():
    parser = argparse.ArgumentParser(description="박종성 상하차비용 + Total_CBM 소급 백필")
    parser.add_argument("--start", default="2024-01-01")
    parser.add_argument("--end",   default=date.today().isoformat())
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force",   action="store_true", help="기존 상하차비용 있어도 덮어쓰기")
    args = parser.parse_args()

    if not PAT:
        print("ERROR: AIRTABLE_PAT not set")
        return

    headers = {
        "Authorization": f"Bearer {PAT}",
        "Content-Type": "application/json",
    }
    run(
        headers,
        start=date.fromisoformat(args.start),
        end=date.fromisoformat(args.end),
        dry_run=args.dry_run,
        force=args.force,
    )


if __name__ == "__main__":
    main()
