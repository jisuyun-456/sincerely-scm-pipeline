"""
debug_dispatch.py
배차일지 Airtable 필드 실제 타입/값 확인용 진단 스크립트
"""
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_ID = "app4x70a8mOrIKsMf"
TBL_DISPATCH = "tbl0YCjOC7rYtyXHV"

AIRTABLE_PAT = os.environ.get("AIRTABLE_PAT", "")
HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_PAT}",
    "Content-Type": "application/json",
}

def fetch_sample(table_id: str, fields: list[str], max_records: int = 10) -> list:
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}"
    params = {
        "fields[]": fields,
        "maxRecords": max_records,
        "sort[0][field]": "fldZh2mZDIPQXfOcO",  # 날짜 내림차순
        "sort[0][direction]": "desc",
    }
    resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("records", [])


def main():
    print("=== 배차일지 필드 진단 ===\n")

    fields = [
        "fldZh2mZDIPQXfOcO",   # 날짜
        "fldyQAoRZFn6oeQ0E",   # 차량이용률(%)
        "fldVJoKjjzcwpHIHC",   # Total_CBM
        "fldwrsxDL2VFdmUKo",   # 오버부킹
    ]

    records = fetch_sample(TBL_DISPATCH, fields, max_records=10)
    print(f"조회된 레코드 수: {len(records)}\n")

    for i, rec in enumerate(records, 1):
        f = rec["fields"]
        date_val = f.get("fldZh2mZDIPQXfOcO")
        rate_val = f.get("fldyQAoRZFn6oeQ0E")
        cbm_val  = f.get("fldVJoKjjzcwpHIHC")
        over_val = f.get("fldwrsxDL2VFdmUKo")

        print(f"[{i}] 날짜: {date_val}")
        print(f"     차량이용률  : {repr(rate_val):30s} (type: {type(rate_val).__name__})")
        print(f"     Total_CBM   : {repr(cbm_val):30s} (type: {type(cbm_val).__name__})")
        print(f"     오버부킹    : {repr(over_val):30s} (type: {type(over_val).__name__})")
        print()

    # 요약 통계
    print("=== 전체 레코드 오버부킹 분포 분석 ===")
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_DISPATCH}"
    all_records = []
    offset = None
    while True:
        params = {"fields[]": ["fldwrsxDL2VFdmUKo", "fldyQAoRZFn6oeQ0E", "fldVJoKjjzcwpHIHC"]}
        if offset:
            params["offset"] = offset
        resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        all_records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break

    print(f"전체 레코드: {len(all_records)}건")

    # 오버부킹 값 분포
    over_values = {}
    cbm_zero = 0
    rate_over100 = 0

    for rec in all_records:
        f = rec["fields"]
        over_val = f.get("fldwrsxDL2VFdmUKo")
        key = f"{type(over_val).__name__}:{repr(over_val)}"
        over_values[key] = over_values.get(key, 0) + 1

        cbm_val = f.get("fldVJoKjjzcwpHIHC")
        try:
            if cbm_val is None or float(str(cbm_val)) <= 0:
                cbm_zero += 1
        except (ValueError, TypeError):
            cbm_zero += 1

        rate_val = f.get("fldyQAoRZFn6oeQ0E")
        try:
            if rate_val is not None:
                rate_str = str(rate_val).replace("%", "").strip()
                if float(rate_str) > 100:
                    rate_over100 += 1
        except (ValueError, TypeError):
            pass

    print("\n오버부킹 값 분포:")
    for k, v in sorted(over_values.items(), key=lambda x: -x[1]):
        print(f"  {k:50s} → {v}건")

    print(f"\nCBM=0 또는 없음: {cbm_zero}건")
    print(f"이용률 100% 초과: {rate_over100}건")


if __name__ == "__main__":
    main()
