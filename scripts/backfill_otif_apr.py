"""
OTIF 백필: 2026년 4월 1-10일 Shipment → OTIF 레코드 생성
- 조건: 출하확정일 4/1~4/10, 발송상태_TMS=출하완료, OTIF 링크 없음
- 생성 필드: Shipment 링크만 (나머지는 formula/lookup 자동)
"""
import requests
import time
import os

PAT = os.environ.get("AIRTABLE_PAT", "patU9ew1rwbJbEpOn.d5c7c1bb42c3ad69edd2701ee0424ddcb04c4d261a0ed422f8e5edaf1fa20edc")
BASE_ID = "app4x70a8mOrIKsMf"
SHIPMENT_TABLE = "tbllg1JoHclGYer7m"
OTIF_TABLE = "tbl4WfEuGLDlqCTQH"
HEADERS = {
    "Authorization": f"Bearer {PAT}",
    "Content-Type": "application/json"
}


def fetch_shipments():
    """출하확정일 4/1~4/10, 출하완료, OTIF 미연결 Shipment 조회"""
    all_records = []
    formula = (
        'AND('
        '  IS_AFTER({출하확정일}, "2026-03-31"),'
        '  IS_BEFORE({출하확정일}, "2026-04-11"),'
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
        time.sleep(0.2)

    return all_records


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
        resp = requests.post(url, headers=HEADERS, json={"records": records})
        if resp.status_code == 200:
            created += len(batch)
            print(f"  Created {created}/{len(shipment_ids)} OTIF records")
        else:
            failed += len(batch)
            print(f"  FAILED batch {i//10 + 1}: {resp.status_code} - {resp.text[:200]}")
        time.sleep(0.25)

    return created, failed


def main():
    print("=" * 60)
    print("OTIF 백필: 2026년 4월 1-10일")
    print("=" * 60)

    print("\n[1/2] Shipment 조회 중...")
    shipments = fetch_shipments()
    print(f"\n  총 {len(shipments)}건 대상")

    if not shipments:
        print("  대상 없음. 종료.")
        return

    for rec in shipments:
        f = rec["fields"]
        print(f"    {f.get('SC id', '?')} | {f.get('출하확정일', '?')}")

    shipment_ids = [rec["id"] for rec in shipments]
    print(f"\n[2/2] OTIF 레코드 생성 중... ({len(shipment_ids)}건)")
    created, failed = create_otif_batch(shipment_ids)

    print(f"\n{'=' * 60}")
    print(f"완료: 생성 {created}건 / 실패 {failed}건")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
