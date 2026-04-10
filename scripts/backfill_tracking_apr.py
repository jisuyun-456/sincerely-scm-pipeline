"""
택배추적로그 백필: 2026년 4월 1-10일 Shipment → 택배추적로그 레코드 생성
- 조건: 출하확정일 4/1~4/10, 출하완료, 운송장번호 있음, 택배추적로그 없음
- 운송장번호가 줄바꿈 구분 다중값 → 각 번호별 1건씩 생성
"""
import requests
import time
import os
import re

PAT = os.environ.get("AIRTABLE_PAT", "patU9ew1rwbJbEpOn.d5c7c1bb42c3ad69edd2701ee0424ddcb04c4d261a0ed422f8e5edaf1fa20edc")
BASE_ID = "app4x70a8mOrIKsMf"
SHIPMENT_TABLE = "tbllg1JoHclGYer7m"
TRACKING_TABLE = "tblonyqcHGa5V5zbj"
HEADERS = {
    "Authorization": f"Bearer {PAT}",
    "Content-Type": "application/json"
}


def fetch_shipments():
    """출하확정일 4/1~4/10, 출하완료, 운송장번호 있음, 택배추적로그 미연결"""
    all_records = []
    formula = (
        'AND('
        '  IS_AFTER({출하확정일}, "2026-03-31"),'
        '  IS_BEFORE({출하확정일}, "2026-04-11"),'
        '  {발송상태_TMS} = "출하 완료",'
        '  {운송장번호} != BLANK(),'
        '  {택배추적로그} = BLANK()'
        ')'
    )
    params = {
        "filterByFormula": formula,
        "fields[]": ["SC id", "출하확정일", "운송장번호"],
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


def parse_waybills(raw_text):
    """줄바꿈/공백 구분 운송장번호 파싱, 숫자만 추출"""
    if not raw_text:
        return []
    parts = re.split(r'[\n\r,\s]+', raw_text.strip().strip('"'))
    return [p.strip().strip('"') for p in parts if p.strip().strip('"').isdigit()]


def create_tracking_batch(tracking_items):
    """택배추적로그 배치 생성"""
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TRACKING_TABLE}"
    created = 0
    failed = 0
    total = len(tracking_items)

    for i in range(0, total, 10):
        batch = tracking_items[i:i+10]
        records = []
        for item in batch:
            record = {
                "fields": {
                    "fldNEjERsz8qEJDnw": item["tracking_id"],       # 추적ID
                    "fldDDhjUKPZVgrYH0": "로젠택배",                  # 택배사
                    "fldvzKlwRSlkNCRiA": item["waybill"],            # 운송장번호
                    "flduWediJYFSaZlbh": "배송완료",                  # 추적상태
                    "fldnxRdyJOkMqRbL6": item["tracking_dt"],        # 추적일시 (UTC)
                    "fldmxi2cX7Ozl54Tj": [item["shipment_id"]],      # Shipment link
                    "fldGM0bpzA89eLrlU": "자동 백필"                  # 비고
                }
            }
            records.append(record)

        resp = requests.post(url, headers=HEADERS, json={"records": records})
        if resp.status_code == 200:
            created += len(batch)
            print(f"  Created {created}/{total}")
        else:
            failed += len(batch)
            err = resp.text[:200] if resp.text else "unknown"
            print(f"  FAILED batch {i//10+1}: {resp.status_code} - {err}")

        time.sleep(0.25)

    return created, failed


def main():
    print("=" * 60)
    print("택배추적로그 백필: 2026년 4월 1-10일")
    print("=" * 60)

    print("\n[1/3] Shipment 조회...")
    shipments = fetch_shipments()
    print(f"  Shipment 대상: {len(shipments)}건")

    if not shipments:
        print("  대상 없음.")
        return

    # Parse waybills and build tracking items
    print("\n[2/3] 운송장번호 파싱...")
    tracking_items = []
    for shp in shipments:
        fields = shp["fields"]
        rec_id = shp["id"]
        sc_id = fields.get("SC id", "?")
        confirm_date = fields.get("출하확정일", "")
        raw_waybills = fields.get("운송장번호", "")

        waybills = parse_waybills(raw_waybills)
        print(f"  {sc_id} | {confirm_date} | 운송장 {len(waybills)}건")

        for wb in waybills:
            tracking_items.append({
                "tracking_id": f"TRK-{wb}",
                "waybill": wb,
                "tracking_dt": f"{confirm_date}T00:00:00.000Z",
                "shipment_id": rec_id,
            })

    print(f"\n  총 추적로그 생성 대상: {len(tracking_items)}건")

    if not tracking_items:
        print("  운송장번호 없음. 종료.")
        return

    print(f"\n[3/3] 배치 생성 ({len(tracking_items)}건)...")
    created, failed = create_tracking_batch(tracking_items)

    print(f"\n{'=' * 60}")
    print(f"완료: 생성 {created}건 / 실패 {failed}건")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
