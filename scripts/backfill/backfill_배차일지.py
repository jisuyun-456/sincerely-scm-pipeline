"""
배차 일지 주간 백필
- 조건: 출하확정일이 대상 주간이고, 내부기사(배송파트너) 배정되어 있으나 배차 일지 미링크
- 동작: 날짜×기사 단위로 배차 일지 레코드 생성 + Shipment 링크
"""
import os
import time
from collections import defaultdict
from datetime import date

import requests

BASE_ID      = "app4x70a8mOrIKsMf"
TBL_SHIPMENT = "tbllg1JoHclGYer7m"
TBL_DISPATCH = "tbl0YCjOC7rYtyXHV"

# 내부기사 배송파트너 record ID
INTERNAL_DRIVERS = {
    "recPkgE4o3cs0krnR": "신시어리 (조희선)",
    "recyVExCkk2Lty0E9": "신시어리 (이장훈)",
    "recXCfwVTqaoeQ9SS": "신시어리 (박종성)",
}

FLD_SHP_DATE     = "fldQvmEwwzvQW95h9"   # 출하확정일
FLD_SHP_PARTNER  = "fldM2u6RwLRrO7ymW"  # 배송파트너 (link)
FLD_SHP_DISPATCH = "fldrRdU0TUQtOiLkg"  # 배차 일지 (link)

FLD_DISP_DATE     = "fldZh2mZDIPQXfOcO"
FLD_DISP_PARTNER  = "fldIQqaoj2CYlCSFH"
FLD_DISP_SHIPMENTS = "flddCIndicSSe8uhi"


def run(headers, start: date, end: date, dry_run: bool) -> dict:
    url_shp = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_SHIPMENT}"
    url_dis = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_DISPATCH}"

    # 1. 대상 Shipment 조회
    formula = (
        f'AND('
        f'  {{출하확정일}} >= "{start.isoformat()}",'
        f'  {{출하확정일}} <= "{end.isoformat()}",'
        f'  {{배차 일지}} = BLANK()'
        f')'
    )
    params = {
        "filterByFormula": formula,
        "fields[]": ["SC id", FLD_SHP_DATE, FLD_SHP_PARTNER, FLD_SHP_DISPATCH],
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

    # 2. 내부기사 배정 건만 필터 + 날짜×기사로 그룹핑
    # REST API: 링크 필드는 record ID 문자열 배열 ["recXXX"] 반환
    groups = defaultdict(list)  # (date_str, driver_rec_id) → [shipment_rec_ids]
    for rec in all_shp:
        f = rec["fields"]
        shp_date = f.get(FLD_SHP_DATE, "")
        partners = f.get(FLD_SHP_PARTNER, [])
        for p in (partners or []):
            rec_id = p["id"] if isinstance(p, dict) else p
            if rec_id in INTERNAL_DRIVERS:
                groups[(shp_date, rec_id)].append(rec["id"])

    if not groups:
        return {"created": 0, "skipped": 0, "message": "대상 없음"}

    print(f"  배차일지 대상 그룹: {len(groups)}개 (날짜×기사)")

    # 3. 기존 배차일지 중복 체크
    existing_keys = set()
    params2 = {
        "filterByFormula": f'AND({{날짜}} >= "{start.isoformat()}", {{날짜}} <= "{end.isoformat()}")',
        "fields[]": [FLD_DISP_DATE, FLD_DISP_PARTNER],
        "pageSize": 100,
        "returnFieldsByFieldId": "true",
    }
    resp2 = requests.get(url_dis, headers=headers, params=params2)
    resp2.raise_for_status()
    for rec in resp2.json().get("records", []):
        f = rec["fields"]
        d = f.get(FLD_DISP_DATE, "")
        partners = f.get(FLD_DISP_PARTNER, []) or []
        for p in partners:
            rec_id = p["id"] if isinstance(p, dict) else p
            existing_keys.add((d, rec_id))

    created, skipped = 0, 0
    for (date_str, driver_id), shp_ids in groups.items():
        if (date_str, driver_id) in existing_keys:
            skipped += 1
            continue
        payload = {
            "fields": {
                FLD_DISP_DATE: date_str,
                FLD_DISP_PARTNER: [{"id": driver_id}],
                FLD_DISP_SHIPMENTS: [{"id": s} for s in shp_ids],
            }
        }
        if dry_run:
            print(f"  [DRY] 생성 예정: {date_str} × {INTERNAL_DRIVERS[driver_id]} ({len(shp_ids)}건)")
        else:
            resp = requests.post(url_dis, headers=headers, json=payload)
            resp.raise_for_status()
            time.sleep(0.2)
        created += 1

    return {"created": created, "skipped": skipped}
