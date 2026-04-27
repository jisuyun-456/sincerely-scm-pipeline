"""
배송이벤트 주간 백필
- 조건: 출하확정일이 대상 주간이고, 배송이벤트 레코드 없음
- 동작: 이벤트유형=배송접수 초기 이벤트 생성
"""
import os
import time
from datetime import date, datetime, timezone

import requests

BASE_ID   = "app4x70a8mOrIKsMf"
TBL_SHIP  = "tbllg1JoHclGYer7m"
TBL_EVENT = "tblQyuAW30yf21WEf"

FLD_EVENT_SHIP  = "fldIAAYK8bfiVl5iv"   # Shipment (link in 배송이벤트)
FLD_EVENT_TYPE  = "fldbBqodeAJhAQATW"   # 이벤트유형 (singleSelect)
FLD_EVENT_TIME  = "fld9IsE0lC5p1Pf1a"  # 이벤트일시 (dateTime)
FLD_EVENT_ID    = "fld1gqsJsUYlxir5p"  # 이벤트ID (text)

# 배송이벤트 이벤트유형 choice IDs (조회 결과 기반 — 변경 시 get_table_schema로 재확인)
EVT_SHIPMENT_CREATED = "배송접수"  # choice 이름으로 직접 입력 (REST API)


def _get_event_type_id(headers):
    """이벤트유형 singleSelect choice ID 조회 (배송접수)"""
    url = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables"
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    for tbl in resp.json().get("tables", []):
        if tbl["id"] == TBL_EVENT:
            for fld in tbl["fields"]:
                if fld["id"] == FLD_EVENT_TYPE:
                    for choice in fld.get("options", {}).get("choices", []):
                        if "배송접수" in choice["name"]:
                            return choice["id"]
    return None


def run(headers, start: date, end: date, dry_run: bool) -> dict:
    url_shp   = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_SHIP}"
    url_event = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_EVENT}"

    formula = (
        f'AND('
        f'  {{출하확정일}} >= "{start.isoformat()}",'
        f'  {{출하확정일}} <= "{end.isoformat()}",'
        f'  {{배송이벤트}} = BLANK()'
        f')'
    )
    params = {
        "filterByFormula": formula,
        "fields[]": ["SC id", "출하확정일"],
        "pageSize": 100,
        "returnFieldsByFieldId": "true",
    }
    all_shp = []
    offset = None
    while True:
        if offset:
            params["offset"] = offset
        resp = requests.get(url_shp, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        all_shp.extend(data["records"])
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)

    if not all_shp:
        return {"created": 0, "message": "대상 없음"}

    print(f"  배송이벤트 백필 대상: {len(all_shp)}건")

    # 이벤트유형 choice ID 조회
    evt_type_id = _get_event_type_id(headers)

    created = 0
    for i in range(0, len(all_shp), 10):
        batch = all_shp[i:i+10]
        records = []
        for rec in batch:
            sc_id = rec["fields"].get("SC id", rec["id"])
            shp_date = rec["fields"].get("출하확정일", "")
            event_time = f"{shp_date}T09:00:00.000Z" if shp_date else datetime.now(timezone.utc).isoformat()
            fields = {
                FLD_EVENT_SHIP: [rec["id"]],
                FLD_EVENT_TIME: event_time,
                FLD_EVENT_ID:   f"EVT-{sc_id}-01",
            }
            if evt_type_id:
                fields[FLD_EVENT_TYPE] = evt_type_id
            records.append({"fields": fields})

        if dry_run:
            for rec in batch:
                sc_id = rec["fields"].get("SC id", rec["id"])
                print(f"  [DRY] 배송이벤트 생성 예정: {sc_id}")
        else:
            resp = requests.post(
                url_event,
                headers=headers,
                json={"records": records},
            )
            resp.raise_for_status()
            time.sleep(0.3)
        created += len(batch)

    return {"created": created}
