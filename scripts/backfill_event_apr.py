"""
배송이벤트 백필: 2026년 4월 1-10일 Shipment → 배송이벤트(배송완료) 레코드 생성
"""
import requests
import time
import os
from collections import Counter

PAT = os.environ.get("AIRTABLE_PAT", "patU9ew1rwbJbEpOn.d5c7c1bb42c3ad69edd2701ee0424ddcb04c4d261a0ed422f8e5edaf1fa20edc")
BASE_ID = "app4x70a8mOrIKsMf"
SHIPMENT_TABLE = "tbllg1JoHclGYer7m"
EVENT_TABLE = "tblQyuAW30yf21WEf"
HEADERS = {
    "Authorization": f"Bearer {PAT}",
    "Content-Type": "application/json"
}


def fetch_shipments():
    """출하확정일 4/1~4/10, 출하완료, 배송이벤트 미연결 Shipment 조회"""
    all_records = []
    formula = (
        'AND('
        '  IS_AFTER({출하확정일}, "2026-03-31"),'
        '  IS_BEFORE({출하확정일}, "2026-04-11"),'
        '  {발송상태_TMS} = "출하 완료",'
        '  {배송이벤트} = BLANK()'
        ')'
    )
    params = {
        "filterByFormula": formula,
        "fields[]": ["SC id", "출하확정일"],
        "pageSize": 100,
        "sort[0][field]": "출하확정일",
        "sort[0][direction]": "asc"
    }
    url = f"https://api.airtable.com/v0/{BASE_ID}/{SHIPMENT_TABLE}"
    offset = None

    while True:
        if offset:
            params["offset"] = offset
        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()
        records = data.get("records", [])
        all_records.extend(records)
        print(f"  Fetched {len(records)} (total: {len(all_records)})")
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)

    return all_records


def create_events(shipments):
    """배송완료 이벤트 배치 생성"""
    url = f"https://api.airtable.com/v0/{BASE_ID}/{EVENT_TABLE}"
    created = 0
    failed = 0
    date_counter = Counter()

    for i in range(0, len(shipments), 10):
        batch = shipments[i:i+10]
        records = []

        for shp in batch:
            fields = shp["fields"]
            rec_id = shp["id"]
            confirm_date = fields.get("출하확정일", "")

            date_key = confirm_date.replace("-", "") if confirm_date else "00000000"
            date_counter[date_key] += 1
            evt_id = f"EVT-{date_key}-{date_counter[date_key]:03d}"

            record = {
                "fields": {
                    "fld1gqsJsUYlxir5p": evt_id,           # 이벤트ID
                    "fldIAAYK8bfiVl5iv": [rec_id],          # Shipment link
                    "fldbBqodeAJhAQATW": "배송완료",         # 이벤트유형
                }
            }
            if confirm_date:
                record["fields"]["fld9IsE0lC5p1Pf1a"] = f"{confirm_date}T09:00:00.000+09:00"

            records.append(record)

        resp = requests.post(url, headers=HEADERS, json={"records": records})
        if resp.status_code == 200:
            created += len(batch)
            print(f"  Created {created}/{len(shipments)}")
        else:
            failed += len(batch)
            err = resp.text[:200] if resp.text else "unknown"
            print(f"  FAILED batch {i//10+1}: {resp.status_code} - {err}")

        time.sleep(0.25)

    return created, failed


def main():
    print("=" * 60)
    print("배송이벤트 백필: 2026년 4월 1-10일 → 배송완료 이벤트")
    print("=" * 60)

    print("\n[1/2] Shipment 조회...")
    shipments = fetch_shipments()
    print(f"  대상: {len(shipments)}건")

    if not shipments:
        print("  대상 없음.")
        return

    monthly = Counter()
    for s in shipments:
        d = s["fields"].get("출하확정일", "")
        monthly[d if d else "unknown"] += 1
    for m in sorted(monthly):
        print(f"    {m}: {monthly[m]}건")

    print(f"\n[2/2] 배치 생성 ({len(shipments)}건)...")
    created, failed = create_events(shipments)

    print(f"\n{'=' * 60}")
    print(f"완료: 생성 {created}건 / 실패 {failed}건")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
