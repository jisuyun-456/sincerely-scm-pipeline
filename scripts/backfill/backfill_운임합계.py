"""
배차일지 운임합계 백필
- 조건: 대상 주간 Shipment의 운송비용+상하차비용 합계를 날짜×기사 단위로 집계
- 동작: 매칭되는 배차일지 레코드의 운임합계 필드를 PATCH
- 안전장치: 기존값 != 0이면 --force 없이 skip (수동 입력 보호)
- Verifier: PATCH 후 GET으로 값 재확인 → 불일치 시 mismatch 누적
"""
import time
from collections import defaultdict
from datetime import date

import requests

BASE_ID      = "app4x70a8mOrIKsMf"
TBL_SHIPMENT = "tbllg1JoHclGYer7m"
TBL_DISPATCH = "tbl0YCjOC7rYtyXHV"

INTERNAL_DRIVERS = {
    "recPkgE4o3cs0krnR",
    "recyVExCkk2Lty0E9",
    "recXCfwVTqaoeQ9SS",
}

F_DATE    = "fldQvmEwwzvQW95h9"
F_PARTNER = "fldM2u6RwLRrO7ymW"
F_FARE    = "fldRT95SC88KSBATT"
F_UNLOAD  = "fldxmAZrBGqS7sQoL"

FLD_DISP_DATE     = "fldZh2mZDIPQXfOcO"
FLD_DISP_PARTNER  = "fldIQqaoj2CYlCSFH"
FLD_DISP_FARE_SUM = "fldoT3HlVBWmxJBLs"


def _fetch_shipments(headers, start: date, end: date) -> list[dict]:
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_SHIPMENT}"
    end_excl = (end + __import__("datetime").timedelta(days=1)).isoformat()
    formula = (
        f'AND({{출하확정일}}>="{start.isoformat()}",'
        f'{{출하확정일}}<"{end_excl}",'
        f'NOT({{배송파트너}}=""))'
    )
    params = {
        "filterByFormula": formula,
        "fields[]": [F_DATE, F_PARTNER, F_FARE, F_UNLOAD],
        "pageSize": 100,
        "returnFieldsByFieldId": "true",
    }
    recs, offset = [], None
    while True:
        if offset:
            params["offset"] = offset
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        recs.extend(data["records"])
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return recs


def _fetch_dispatch(headers, start: date, end: date) -> list[dict]:
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_DISPATCH}"
    formula = (
        f'AND({{날짜}}>="{start.isoformat()}",'
        f'{{날짜}}<="{end.isoformat()}")'
    )
    params = {
        "filterByFormula": formula,
        "fields[]": [FLD_DISP_DATE, FLD_DISP_PARTNER, FLD_DISP_FARE_SUM],
        "pageSize": 100,
        "returnFieldsByFieldId": "true",
    }
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json().get("records", [])


def run(headers, start: date, end: date, dry_run: bool, force: bool = False) -> dict:
    shp_recs = _fetch_shipments(headers, start, end)

    # Group Shipment fares by (date, driver_id)
    fare_by_key: defaultdict[tuple, int] = defaultdict(int)
    for rec in shp_recs:
        f = rec["fields"]
        d = (f.get(F_DATE) or "")[:10]
        partners = f.get(F_PARTNER) or []
        for p in partners:
            pid = p["id"] if isinstance(p, dict) else p
            if pid in INTERNAL_DRIVERS:
                fare = int(f.get(F_FARE) or 0) + int(f.get(F_UNLOAD) or 0)
                fare_by_key[(d, pid)] += fare

    if not fare_by_key:
        return {"created": 0, "skipped": 0, "mismatch": [], "message": "대상 없음"}

    # Fetch 배차일지 and match
    disp_recs = _fetch_dispatch(headers, start, end)

    url_disp = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_DISPATCH}"
    updated, skipped, mismatch = 0, 0, []

    for rec in disp_recs:
        f = rec["fields"]
        d = (f.get(FLD_DISP_DATE) or "")[:10]
        partners = f.get(FLD_DISP_PARTNER) or []
        if not partners:
            continue
        pid = partners[0]["id"] if isinstance(partners[0], dict) else partners[0]
        key = (d, pid)
        calc = fare_by_key.get(key, 0)
        if calc == 0:
            skipped += 1
            continue

        current = int(f.get(FLD_DISP_FARE_SUM) or 0)
        if current != 0 and not force:
            skipped += 1
            continue

        if dry_run:
            print(f"  [DRY] {d} × {pid[:8]}: {current:,} → {calc:,}")
            updated += 1
            continue

        r = requests.patch(
            f"{url_disp}/{rec['id']}",
            headers={**headers, "Content-Type": "application/json"},
            json={"fields": {FLD_DISP_FARE_SUM: calc}},
            timeout=15,
        )
        r.raise_for_status()
        time.sleep(0.25)

        # Verifier: re-read and confirm
        verify = requests.get(
            f"{url_disp}/{rec['id']}",
            headers=headers,
            params={"fields[]": [FLD_DISP_FARE_SUM], "returnFieldsByFieldId": "true"},
            timeout=15,
        )
        verify.raise_for_status()
        written = int(verify.json()["fields"].get(FLD_DISP_FARE_SUM) or 0)
        if written != calc:
            mismatch.append({"id": rec["id"], "expected": calc, "got": written})
        updated += 1

    return {"created": updated, "skipped": skipped, "mismatch": mismatch}
