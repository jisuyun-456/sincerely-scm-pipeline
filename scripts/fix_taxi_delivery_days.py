# ================================================================
# 택배 실제배송일수 보정 스크립트
# ================================================================
# [배경]
#   backfill_actual_delivery_days.py 실행 시 returnFieldsByFieldId 미설정으로
#   배송방식 필드를 인식 못해 택배 레코드를 당일(0)으로 잘못 분류.
#   이 스크립트는 배송방식 contains "택배" AND 실제배송일수=0 인 레코드를
#   구간유형 기준으로 2(수도권) 또는 3(지방/도서)으로 보정.
#
# [대상]
#   발송상태_TMS = "출하 완료"
#   AND 배송방식 contains "택배"
#   AND 실제배송일수 = 0  (잘못 설정된 값)
#
# [환경변수]
#   AIRTABLE_PAT : Airtable Personal Access Token
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

ZONE_2DAY = {"수도권"}


def fetch_taxi_records() -> list[dict]:
    """배송방식='택배' AND 실제배송일수=0 인 레코드 전체 조회."""
    records = []
    offset = None
    page = 1

    # 배송방식에 "택배" 포함 AND 실제배송일수=0 AND 출하완료
    formula = 'AND({발송상태_TMS}="출하 완료",FIND("택배",ARRAYJOIN({배송 방식})),{실제배송일수}=0)'
    fields  = [FLD_DELIVERY_DAYS, FLD_DELIVERY_TYPE, FLD_ZONE]

    while True:
        params: dict = {
            "filterByFormula": formula,
            "fields[]": fields,
            "pageSize": 100,
            "returnFieldsByFieldId": "true",
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


def patch_records(updates: list[dict]) -> None:
    for i in range(0, len(updates), 10):
        batch = updates[i : i + 10]
        payload = {
            "records": [
                {"id": rec["id"], "fields": {FLD_DELIVERY_DAYS: rec["days"]}}
                for rec in batch
            ]
        }
        resp = requests.patch(API_BASE, headers=HEADERS, json=payload)
        resp.raise_for_status()
        time.sleep(0.2)


def main() -> None:
    if not PAT:
        raise ValueError("AIRTABLE_PAT 환경변수가 설정되지 않았습니다.")

    print("=" * 60, flush=True)
    print("택배 실제배송일수 보정 시작", flush=True)
    print("=" * 60, flush=True)

    print("\n[1] 택배(실제배송일수=0) 레코드 조회 중...", flush=True)
    records = fetch_taxi_records()
    print(f"  총 {len(records)}건 조회 완료\n", flush=True)

    if not records:
        print("보정 대상 없음. 이미 올바르게 설정됨.", flush=True)
        return

    updates = []
    cnt = {"2일(수도권)": 0, "3일(지방/도서)": 0, "3일(구간유형없음)": 0}

    for rec in records:
        flds = rec.get("fields", {})
        zone_obj = flds.get(FLD_ZONE)  # {"id": "sel...", "name": "수도권"} 형태
        zone_name = zone_obj.get("name", "") if isinstance(zone_obj, dict) else ""

        if zone_name in ZONE_2DAY:
            days = 2
            cnt["2일(수도권)"] += 1
        else:
            days = 3
            if zone_name:
                cnt["3일(지방/도서)"] += 1
            else:
                cnt["3일(구간유형없음)"] += 1

        updates.append({"id": rec["id"], "days": days})

    print("[2] 분류 결과:", flush=True)
    for label, c in cnt.items():
        print(f"  {label}: {c}건", flush=True)
    print(f"  → 업데이트 예정: {len(updates)}건\n", flush=True)

    print("[3] Airtable 업데이트 중...", flush=True)
    for i in range(0, len(updates), 10):
        patch_records(updates[i : i + 10])
        done = min(i + 10, len(updates))
        if done % 500 == 0 or done == len(updates):
            print(f"  진행: {done}/{len(updates)}건", flush=True)

    print(f"  완료: {len(updates)}건 업데이트\n", flush=True)
    print("=" * 60, flush=True)
    print("보정 완료", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    main()
