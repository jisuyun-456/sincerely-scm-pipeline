"""
영업팀 CBM 마스터 데이터를 TMS Product 테이블에 UPSERT.

Usage:
  py harness/settlement/import_product_cbm.py --dry-run   # 미리보기
  py harness/settlement/import_product_cbm.py             # 실제 반영

UPSERT 키: 견적코드(code). 없으면 POST, 있으면 PATCH (변경된 필드만).
"""
import argparse
import os
import time

import requests
from dotenv import load_dotenv

from product_cbm_data import PRODUCTS

load_dotenv()
PAT = os.environ.get("AIRTABLE_PAT", "")
TMS_BASE = "app4x70a8mOrIKsMf"
TBL_PRODUCT = "tblBNh6oGDlTKGrdQ"

FLD_NAME     = "fldx01uKEnCd0J0nP"
FLD_CODE     = "fldtpUf2UVooLcxwd"
FLD_BOX_TYPE = "fldqGM1lw2TUpZdKW"
FLD_QTY      = "fldENIdfxbVn8YnPI"
FLD_CBM      = "fldCeJ0RqSUGlfEw4"


def _load_existing(headers: dict) -> dict[str, dict]:
    """견적코드 → {rec_id, name, box_type, qty_per_box, cbm}"""
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_PRODUCT}"
    existing: dict[str, dict] = {}
    cursor = None
    while True:
        params: dict = {
            "returnFieldsByFieldId": "true",
            "fields[]": [FLD_NAME, FLD_CODE, FLD_BOX_TYPE, FLD_QTY, FLD_CBM],
            "pageSize": 100,
        }
        if cursor:
            params["offset"] = cursor
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        for rec in data.get("records", []):
            f = rec["fields"]
            code = str(f.get(FLD_CODE) or "").strip().upper()
            if code:
                existing[code] = {
                    "rec_id":      rec["id"],
                    "name":        str(f.get(FLD_NAME) or "").strip(),
                    "box_type":    str(f.get(FLD_BOX_TYPE) or "").strip(),
                    "qty_per_box": f.get(FLD_QTY),
                    "cbm":         str(f.get(FLD_CBM) or "").strip(),
                }
        cursor = data.get("offset")
        if not cursor:
            break
        time.sleep(0.2)
    return existing


def _fields_from(product: dict) -> dict:
    return {
        FLD_NAME:     product["name"],
        FLD_CODE:     product["code"].upper(),
        FLD_BOX_TYPE: product["box_type"],
        FLD_QTY:      product["qty_per_box"],
        FLD_CBM:      str(product["cbm"]),
    }


def _changed(product: dict, existing: dict) -> dict:
    """Return only fields that differ from the existing record."""
    new_fields = _fields_from(product)
    delta: dict = {}
    if existing["name"] != product["name"]:
        delta[FLD_NAME] = product["name"]
    if existing["box_type"] != product["box_type"]:
        delta[FLD_BOX_TYPE] = product["box_type"]
    if existing["qty_per_box"] != product["qty_per_box"]:
        delta[FLD_QTY] = product["qty_per_box"]
    if existing["cbm"] != str(product["cbm"]):
        delta[FLD_CBM] = str(product["cbm"])
    _ = new_fields  # used above indirectly
    return delta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not PAT:
        print("ERROR: AIRTABLE_PAT not set")
        return

    headers = {
        "Authorization": f"Bearer {PAT}",
        "Content-Type": "application/json",
    }

    print(f"Loading existing Product records...")
    existing = _load_existing(headers)
    print(f"  기존: {len(existing)}건")
    print(f"  입력 리스트: {len(PRODUCTS)}건\n")

    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_PRODUCT}"
    created = updated = unchanged = errors = 0

    for product in PRODUCTS:
        code = product["code"].upper()
        if code in existing:
            delta = _changed(product, existing[code])
            if not delta:
                unchanged += 1
                continue
            print(f"  UPDATE {code}: {delta}")
            if not args.dry_run:
                rec_id = existing[code]["rec_id"]
                r = requests.patch(
                    f"{url}/{rec_id}",
                    headers=headers,
                    json={"fields": delta},
                    timeout=15,
                )
                if r.ok:
                    updated += 1
                else:
                    print(f"    ERROR {r.status_code}: {r.text[:100]}")
                    errors += 1
                time.sleep(0.25)
            else:
                updated += 1
        else:
            fields = _fields_from(product)
            print(f"  CREATE {code}: {product['name']}")
            if not args.dry_run:
                r = requests.post(
                    url,
                    headers=headers,
                    json={"fields": fields},
                    timeout=15,
                )
                if r.ok:
                    created += 1
                else:
                    print(f"    ERROR {r.status_code}: {r.text[:100]}")
                    errors += 1
                time.sleep(0.25)
            else:
                created += 1

    label = "[DRY-RUN] " if args.dry_run else ""
    print(f"\n{label}결과: created={created}  updated={updated}  unchanged={unchanged}  errors={errors}")


if __name__ == "__main__":
    main()
