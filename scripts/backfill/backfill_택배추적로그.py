"""
택배추적로그 주간 백필
- 조건: 출하확정일이 대상 주간이고, 운송장번호 있으나 택배추적로그 없음
- 동작: 택배사/운송장번호 기반 초기 추적로그 레코드 생성
"""
import os
import time
from datetime import date, timezone, datetime

import requests

BASE_ID   = "app4x70a8mOrIKsMf"
TBL_SHIP  = "tbllg1JoHclGYer7m"
TBL_TRACK = "tblonyqcHGa5V5zbj"

FLD_TRACK_SHIP   = "fldmxi2cX7Ozl54Tj"  # Shipment (link in 택배추적로그)
FLD_TRACK_ID     = "fldNEjERsz8qEJDnw"  # 추적ID (text)
FLD_TRACK_CARRIER = "fldDDhjUKPZVgrYH0" # 택배사 (singleSelect)
FLD_TRACK_WAYBILL = "fldvzKlwRSlkNCRiA" # 운송장번호 (text)
FLD_TRACK_STATUS  = "flduWediJYFSaZlbh" # 추적상태 (singleSelect)
FLD_TRACK_TIME    = "fldnxRdyJOkMqRbL6" # 추적일시 (dateTime)

FLD_SHP_WAYBILL  = "fldv4U6Gx4d8BWPTb"  # 운송장번호 (in Shipment, multilineText)
FLD_SHP_TRACK    = "fldHGqWyi0aqwNve7"  # 택배추적로그 (link in Shipment)


def _detect_carrier(waybill: str) -> str:
    """운송장 번호 패턴으로 택배사 추정"""
    w = waybill.strip()
    if len(w) == 10 and w.isdigit():
        return "CJ대한통운"
    if len(w) == 12 and w.isdigit():
        return "한진택배"
    if len(w) == 11 and w.startswith("6"):
        return "로젠택배"
    if len(w) == 13 and w.startswith("4"):
        return "우체국택배"
    return ""


def run(headers, start: date, end: date, dry_run: bool) -> dict:
    url_shp   = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_SHIP}"
    url_track = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_TRACK}"

    formula = (
        f'AND('
        f'  {{출하확정일}} >= "{start.isoformat()}",'
        f'  {{출하확정일}} <= "{end.isoformat()}",'
        f'  {{운송장번호}} != "",'
        f'  {{택배추적로그}} = BLANK()'
        f')'
    )
    params = {
        "filterByFormula": formula,
        "fields[]": ["SC id", "출하확정일", FLD_SHP_WAYBILL],
        "pageSize": 100,
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

    print(f"  택배추적로그 백필 대상: {len(all_shp)}건")

    created = 0
    for i in range(0, len(all_shp), 10):
        batch = all_shp[i:i+10]
        records = []
        for rec in batch:
            f = rec["cellValuesByFieldId"]
            sc_id   = f.get("SC id", rec["id"])
            waybill = (f.get(FLD_SHP_WAYBILL) or "").strip()
            shp_date = f.get("출하확정일", "")
            carrier = _detect_carrier(waybill)
            event_time = f"{shp_date}T09:00:00.000Z" if shp_date else datetime.now(timezone.utc).isoformat()

            fields = {
                FLD_TRACK_SHIP:    [{"id": rec["id"]}],
                FLD_TRACK_ID:      f"TRK-{sc_id}-01",
                FLD_TRACK_WAYBILL: waybill,
                FLD_TRACK_TIME:    event_time,
            }
            if carrier:
                fields[FLD_TRACK_CARRIER] = carrier
            records.append({"fields": fields})

        if dry_run:
            for rec in batch:
                sc_id = rec["cellValuesByFieldId"].get("SC id", rec["id"])
                w = (rec["cellValuesByFieldId"].get(FLD_SHP_WAYBILL) or "").strip()
                print(f"  [DRY] 택배추적로그 생성 예정: {sc_id} / {w}")
        else:
            resp = requests.post(
                url_track,
                headers=headers,
                json={"records": records},
            )
            resp.raise_for_status()
            time.sleep(0.3)
        created += len(batch)

    return {"created": created}
