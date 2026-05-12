"""
TMS Product 테이블 박스사이즈 일괄 백필 (one-shot).

문제: 328/337 records have blank '박스사이즈' → formula '박스 당 CBM' returns 0.
해결: 박스명칭 → 표준 박스사이즈 매핑으로 빈 칸만 채움.
      박스사이즈가 이미 있는 9건은 손대지 않음.

Usage:
  py scripts/backfill/backfill_product_box_size.py --dry-run
  py scripts/backfill/backfill_product_box_size.py
"""
import argparse
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# Reuse mapping from cbm_calc
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness" / "settlement"))
from cbm_calc import BOX_TYPE_TO_SIZE_STR  # noqa: E402

load_dotenv()
PAT = os.environ.get("AIRTABLE_PAT", "")
TMS_BASE = "app4x70a8mOrIKsMf"
TBL_PRODUCT = "tblBNh6oGDlTKGrdQ"

FLD_CODE     = "fldtpUf2UVooLcxwd"
FLD_BOX_TYPE = "fldqGM1lw2TUpZdKW"
FLD_BOX_SIZE = "fld1ECU2hhnEurOef"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not PAT:
        print("ERROR: AIRTABLE_PAT not set")
        return

    headers = {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_PRODUCT}"

    to_patch = []
    skip_no_type = 0
    already_set = 0
    cursor = None
    while True:
        params = {
            "returnFieldsByFieldId": "true",
            "fields[]": [FLD_CODE, FLD_BOX_TYPE, FLD_BOX_SIZE],
            "pageSize": 100,
        }
        if cursor:
            params["offset"] = cursor
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        d = r.json()
        for rec in d.get("records", []):
            f = rec["fields"]
            existing_size = str(f.get(FLD_BOX_SIZE) or "").strip()
            box_type = str(f.get(FLD_BOX_TYPE) or "").strip()
            if existing_size:
                already_set += 1
                continue
            if not box_type or box_type not in BOX_TYPE_TO_SIZE_STR:
                skip_no_type += 1
                continue
            target_size = BOX_TYPE_TO_SIZE_STR[box_type]
            to_patch.append({
                "rec_id": rec["id"],
                "code": str(f.get(FLD_CODE) or "").strip(),
                "box_type": box_type,
                "box_size": target_size,
            })
        cursor = d.get("offset")
        if not cursor:
            break
        time.sleep(0.2)

    print(f"  total scanned       : {already_set + skip_no_type + len(to_patch)}")
    print(f"  already has 박스사이즈 : {already_set}")
    print(f"  no 박스명칭 (skip)    : {skip_no_type}")
    print(f"  to backfill         : {len(to_patch)}")

    # Sample preview
    for item in to_patch[:5]:
        print(f"    {item['code']:8s}  {item['box_type']:6s} -> {item['box_size']}")
    if len(to_patch) > 5:
        print(f"    ... +{len(to_patch)-5} more")

    if args.dry_run:
        print("\n[DRY-RUN] No changes written.")
        return

    # Batch PATCH (Airtable allows up to 10 records per request)
    BATCH = 10
    ok = 0
    err = 0
    for i in range(0, len(to_patch), BATCH):
        batch = to_patch[i : i + BATCH]
        body = {
            "records": [
                {"id": item["rec_id"], "fields": {FLD_BOX_SIZE: item["box_size"]}}
                for item in batch
            ],
            "typecast": True,  # auto-create missing singleSelect choices
        }
        r = requests.patch(url, headers=headers, json=body, timeout=30)
        if r.ok:
            ok += len(batch)
        else:
            print(f"  ERROR batch {i}: {r.status_code} {r.text[:200]}")
            err += len(batch)
        time.sleep(0.25)

    print(f"\n결과: patched={ok}  errors={err}")


if __name__ == "__main__":
    main()
