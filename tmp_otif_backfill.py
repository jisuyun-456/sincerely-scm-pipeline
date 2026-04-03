"""
OTIF 백필 스크립트: 2026년 1-2월 Shipment → OTIF 레코드 생성
- 조건: 출하확정일 1/1~2/28, 발송상태_TMS=출하완료, OTIF 링크 없음
- 생성 필드: Shipment 링크만 (나머지는 formula/lookup 자동)
"""
import requests
import time
import json

PAT = "patU9ew1rwbJbEpOn.d5c7c1bb42c3ad69edd2701ee0424ddcb04c4d261a0ed422f8e5edaf1fa20edc"
BASE_ID = "app4x70a8mOrIKsMf"
SHIPMENT_TABLE = "tbllg1JoHclGYer7m"
OTIF_TABLE = "tbl4WfEuGLDlqCTQH"
HEADERS = {
    "Authorization": f"Bearer {PAT}",
    "Content-Type": "application/json"
}

# Step 1: Fetch all Shipment records (Jan-Feb 2026, 출하완료, no OTIF)
def fetch_shipments():
    """출하확정일 1-2월, 출하완료, OTIF 미연결 Shipment 조회"""
    all_records = []
    formula = (
        'AND('
        '  IS_AFTER({출하확정일}, "2025-12-31"),'
        '  IS_BEFORE({출하확정일}, "2026-03-01"),'
        '  {발송상태_TMS} = "출하 완료",'
        '  {OTIF} = BLANK()'
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
        print(f"  Fetched {len(records)} records (total: {len(all_records)})")

        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)  # rate limit

    return all_records


# Step 2: Create OTIF records in batches of 10
def create_otif_batch(shipment_ids):
    """Shipment record ID 목록 → OTIF 레코드 배치 생성"""
    url = f"https://api.airtable.com/v0/{BASE_ID}/{OTIF_TABLE}"
    created = 0
    failed = 0

    for i in range(0, len(shipment_ids), 10):
        batch = shipment_ids[i:i+10]
        records = []
        for rec_id in batch:
            records.append({
                "fields": {
                    "fldGwqw0LSIoa824Z": [rec_id]  # Shipment link
                }
            })

        payload = {"records": records}
        resp = requests.post(url, headers=HEADERS, json=payload)

        if resp.status_code == 200:
            created += len(batch)
            print(f"  Created {created}/{len(shipment_ids)} OTIF records")
        else:
            failed += len(batch)
            print(f"  FAILED batch {i//10 + 1}: {resp.status_code} - {resp.text[:200]}")

        time.sleep(0.25)  # rate limit (5 req/sec)

    return created, failed


def main():
    print("=" * 60)
    print("OTIF 백필: 2026년 1-2월 Shipment → OTIF 레코드 생성")
    print("=" * 60)

    # Step 1: Fetch
    print("\n[1/2] Shipment 조회 중...")
    shipments = fetch_shipments()
    print(f"\n  총 {len(shipments)}건 대상")

    if not shipments:
        print("  대상 없음. 종료.")
        return

    # 월별 집계
    monthly = {}
    for rec in shipments:
        date = rec["fields"].get("출하확정일", "unknown")
        if date and len(date) >= 7:
            month = date[:7]
        else:
            month = "unknown"
        monthly[month] = monthly.get(month, 0) + 1

    print("\n  월별 분포:")
    for m in sorted(monthly.keys()):
        print(f"    {m}: {monthly[m]}건")

    # Step 2: Create
    shipment_ids = [rec["id"] for rec in shipments]
    print(f"\n[2/2] OTIF 레코드 생성 중... ({len(shipment_ids)}건)")
    created, failed = create_otif_batch(shipment_ids)

    print(f"\n{'=' * 60}")
    print(f"완료: 생성 {created}건 / 실패 {failed}건")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
