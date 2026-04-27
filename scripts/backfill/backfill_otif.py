"""
OTIF 주간 백필
- 조건: 출하확정일이 대상 주간이고, 발송상태_TMS=출하완료, OTIF 링크 없음
- 동작: Shipment별 OTIF 레코드 1:1 생성
"""
import os
import time
from datetime import date

import requests

BASE_ID     = "app4x70a8mOrIKsMf"
TBL_SHIP    = "tbllg1JoHclGYer7m"
TBL_OTIF    = "tbl4WfEuGLDlqCTQH"

FLD_SHIP_OTIF    = "fldQEpW6QI8Qg3nDn"  # OTIF (link in Shipment)
FLD_OTIF_SHIP    = "fldGwqw0LSIoa824Z"  # Shipment (link in OTIF)


def run(headers, start: date, end: date, dry_run: bool) -> dict:
    url_shp  = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_SHIP}"
    url_otif = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_OTIF}"

    formula = (
        f'AND('
        f'  {{출하확정일}} >= "{start.isoformat()}",'
        f'  {{출하확정일}} <= "{end.isoformat()}",'
        f'  {{발송상태_TMS}} = "출하 완료",'
        f'  {{OTIF}} = BLANK()'
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

    print(f"  OTIF 백필 대상: {len(all_shp)}건")

    created = 0
    # 10건씩 배치 생성
    for i in range(0, len(all_shp), 10):
        batch = all_shp[i:i+10]
        records = [
            {"fields": {FLD_OTIF_SHIP: [rec["id"]]}}
            for rec in batch
        ]
        if dry_run:
            for rec in batch:
                sc_id = rec["fields"].get("SC id", rec["id"])
                print(f"  [DRY] OTIF 생성 예정: {sc_id}")
        else:
            resp = requests.post(
                url_otif,
                headers=headers,
                json={"records": records},
            )
            resp.raise_for_status()
            time.sleep(0.3)
        created += len(batch)

    return {"created": created}
