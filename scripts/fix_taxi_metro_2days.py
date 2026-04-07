# ================================================================
# 수도권 택배 실제배송일수 3→2 보정 스크립트
# ================================================================
# [배경]
#   fix_taxi_delivery_days.py 에서 구간유형 파싱 버그로
#   수도권 택배도 3일로 설정됨. 이 스크립트는 수도권 택배를 2일로 보정.
#
# [대상]
#   발송상태_TMS = "출하 완료"
#   AND 배송방식 contains "택배"
#   AND 구간유형 = "수도권"
#   AND 실제배송일수 = 3  (잘못 설정된 값, 2여야 함)
# ================================================================

import os
import time
import requests

PAT      = os.environ.get("AIRTABLE_PAT", "")
BASE_ID  = "app4x70a8mOrIKsMf"
TABLE_ID = "tbllg1JoHclGYer7m"
API_BASE = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}"

HEADERS = {
    "Authorization": f"Bearer {PAT}",
    "Content-Type": "application/json",
}

FLD_DELIVERY_DAYS = "fld1EJjUSSKKboinl"
FLD_DELIVERY_TYPE = "flduzH5tS7orqGG3o"
FLD_ZONE          = "fldp6haTDFzzF5C74"
FLD_STATUS        = "fldOhibgxg6LIpRTi"


def fetch_records() -> list[dict]:
    records = []
    offset = None
    page = 1

    # 수도권 + 택배 + 실제배송일수=3 (2여야 하는 것들)
    formula = (
        'AND('
        '{발송상태_TMS}="출하 완료",'
        'FIND("택배",ARRAYJOIN({배송 방식})),'
        '{구간유형}="수도권",'
        '{실제배송일수}=3'
        ')'
    )

    while True:
        params: dict = {
            "filterByFormula": formula,
            "fields[]": [FLD_DELIVERY_DAYS, FLD_DELIVERY_TYPE, FLD_ZONE],
            "pageSize": 100,
        }
        if offset:
            params["offset"] = offset

        resp = requests.get(API_BASE, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()

        batch = data.get("records", [])
        records.extend(batch)
        print(f"  page {page}: {len(batch)}건 수신 (누적 {len(records)}건)", flush=True)

        offset = data.get("offset")
        if not offset:
            break

        page += 1
        time.sleep(0.2)

    return records


def patch_records(record_ids: list[str]) -> None:
    for i in range(0, len(record_ids), 10):
        batch = record_ids[i : i + 10]
        payload = {
            "records": [
                {"id": rid, "fields": {FLD_DELIVERY_DAYS: 2}}
                for rid in batch
            ]
        }
        resp = requests.patch(API_BASE, headers=HEADERS, json=payload)
        resp.raise_for_status()
        time.sleep(0.2)


def main() -> None:
    if not PAT:
        raise ValueError("AIRTABLE_PAT 환경변수가 설정되지 않았습니다.")

    print("=" * 60, flush=True)
    print("수도권 택배 3→2 보정 시작", flush=True)
    print("=" * 60, flush=True)

    print("\n[1] 수도권 택배(실제배송일수=3) 레코드 조회 중...", flush=True)
    records = fetch_records()
    print(f"  총 {len(records)}건 조회 완료\n", flush=True)

    if not records:
        print("보정 대상 없음.", flush=True)
        return

    record_ids = [r["id"] for r in records]

    print(f"[2] {len(record_ids)}건 → 실제배송일수 2로 업데이트 중...", flush=True)
    for i in range(0, len(record_ids), 10):
        patch_records(record_ids[i : i + 10])
        done = min(i + 10, len(record_ids))
        if done % 500 == 0 or done == len(record_ids):
            print(f"  진행: {done}/{len(record_ids)}건", flush=True)

    print(f"\n완료: {len(record_ids)}건 → 2일로 보정\n", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    main()
