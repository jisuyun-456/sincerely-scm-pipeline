"""
check_배송요청_미연결.py
────────────────────────────────────────────────────────────────────────────
TMS 배송요청 테이블에서 logistics_PK가 있는데 Shipment 링크가 없는 레코드 조회.

결과를 콘솔 출력 + reports/배송요청_미연결_YYYY-MM-DD.csv 저장.

사용법:
  python scripts/check_배송요청_미연결.py              # TO-prefix, 2026-04-01 이후
  python scripts/check_배송요청_미연결.py --from 2026-03-01  # 시작일 직접 지정
  python scripts/check_배송요청_미연결.py --all         # 전체 (느림)
"""
import argparse
import csv
import os
import time
from datetime import date, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_ID     = "app4x70a8mOrIKsMf"
TABLE_ID    = "tblfIEiPJaEF0DVoM"

FLD_PK      = "fldkA2tfiPumAtaES"   # logistics_PK (text)
FLD_SHIP    = "fld1rfeoDNQKASafk"   # Shipment (link)
FLD_PROJECT = "fldNzb6SwSgAzQ2LR"  # project
FLD_DATE    = "fldeZ1n4Z0P2g6wBG"  # 출고요청일
FLD_ADDR    = "fldsgaWuzPA5ELqst"  # 수령인(주소)
FLD_COMPANY = "fldgk5lOwxe71Alkd"  # 회사명
FLD_PURPOSE = "fldVtovROZNlSc6jn"  # 이동목적
FLD_STATUS  = "fldZzaXhrLk5CIpSe"  # 발송 상태

PAT = os.environ.get(
    "AIRTABLE_PAT",
    "patU9ew1rwbJbEpOn.d5c7c1bb42c3ad69edd2701ee0424ddcb04c4d261a0ed422f8e5edaf1fa20edc",
)
HEADERS = {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}


DEFAULT_FROM = "2026-04-20"  # 4/17(금)까지 처리 완료 → 4/20(월)부터 추적


def fetch_unlinked(from_date=DEFAULT_FROM, all_records=False):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}"

    parts = [
        '{logistics_PK} != ""',
        'FIND("TO", {logistics_PK}) = 1',  # TO-prefix만
        '{Shipment} = BLANK()',
    ]
    if not all_records:
        parts.append(f'{{출고 요청일}} >= "{from_date}"')

    formula = "AND(" + ", ".join(parts) + ")"
    params = {
        "filterByFormula": formula,
        "fields[]": [FLD_PK, FLD_PROJECT, FLD_DATE, FLD_ADDR, FLD_COMPANY, FLD_PURPOSE, FLD_STATUS],
        "sort[0][field]": FLD_DATE,
        "sort[0][direction]": "desc",
        "pageSize": 100,
    }

    results = []
    offset = None
    while True:
        if offset:
            params["offset"] = offset
        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()
        results.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)

    return results


def format_row(rec):
    f = rec.get("cellValuesByFieldId", {})
    purpose = f.get(FLD_PURPOSE, {})
    purpose_name = purpose.get("name", "") if isinstance(purpose, dict) else ""
    return {
        "record_id":    rec["id"],
        "logistics_PK": f.get(FLD_PK, ""),
        "project":      f.get(FLD_PROJECT, ""),
        "출고요청일":   f.get(FLD_DATE, ""),
        "회사명":       f.get(FLD_COMPANY, ""),
        "수령인(주소)": f.get(FLD_ADDR, ""),
        "이동목적":     purpose_name,
        "발송상태":     f.get(FLD_STATUS, ""),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="from_date", default=DEFAULT_FROM,
                        help=f"조회 시작일 YYYY-MM-DD (기본: {DEFAULT_FROM})")
    parser.add_argument("--all", action="store_true", help="전체 조회 (TO-prefix + 날짜 무제한)")
    args = parser.parse_args()

    label = "전체" if args.all else f"{args.from_date} 이후"
    print(f"조회 중... (TO-prefix, {label})")
    records = fetch_unlinked(from_date=args.from_date, all_records=args.all)

    rows = [format_row(r) for r in records]

    # 콘솔 출력
    print(f"\n## 배송요청 → Shipment 미연결 ({len(rows)}건)\n")
    print(f"{'logistics_PK':<16} {'project':<30} {'출고요청일':<12} {'회사명':<20} 수령인(주소)")
    print("-" * 100)
    for r in rows[:50]:
        addr = r["수령인(주소)"][:30] if r["수령인(주소)"] else "-"
        print(f"{r['logistics_PK']:<16} {r['project']:<30} {r['출고요청일']:<12} {r['회사명']:<20} {addr}")
    if len(rows) > 50:
        print(f"  ... 이하 {len(rows)-50}건 더 있음 (CSV 파일 참조)")

    # CSV 저장
    today = date.today().isoformat()
    out_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "reports",
        f"배송요청_미연결_{today}.csv",
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys() if rows else [])
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n[CSV 저장 완료] {out_path}")


if __name__ == "__main__":
    main()
