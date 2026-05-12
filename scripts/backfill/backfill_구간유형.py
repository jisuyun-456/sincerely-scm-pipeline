"""
구간유형 자동분류 백필
- 조건: 구간유형 blank AND 수령인(주소) 있는 Shipment
- 동작: 주소 키워드 기반으로 singleSelect 값 PATCH
- 실제 옵션값 (API 확인 완료): 수도권 / 지방(광역시) / 지방(기타) / 도서산간
- Verifier: PATCH 후 GET으로 값 재확인 → 불일치 시 mismatch 누적
"""
import time
from datetime import date

import requests

BASE_ID      = "app4x70a8mOrIKsMf"
TBL_SHIPMENT = "tbllg1JoHclGYer7m"

F_ZONE      = "fldp6haTDFzzF5C74"
F_DEST_ADDR = "fldyJHUh9gN44Ggnh"


def _classify(addr: str) -> str:
    if not addr:
        return ""
    if any(k in addr for k in ("서울", "경기", "인천")):
        return "수도권"
    if any(k in addr for k in ("부산", "대구", "광주", "대전", "울산", "세종")):
        return "지방(광역시)"
    if any(k in addr for k in ("제주", "울릉")):
        return "도서산간"
    return "지방(기타)"


def _str_field(raw) -> str:
    if isinstance(raw, list):
        return str(raw[0] or "").strip() if raw else ""
    return str(raw or "").strip()


def run(headers, start: date, end: date, dry_run: bool) -> dict:
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_SHIPMENT}"
    # Classify all unclassified Shipments regardless of date range
    params = {
        "filterByFormula": f'AND({{구간유형}}="",NOT({{수령인(주소)}}=""))',
        "fields[]": [F_DEST_ADDR, F_ZONE],
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

    if not recs:
        return {"created": 0, "skipped": 0, "mismatch": [], "message": "대상 없음"}

    print(f"  구간유형 미분류: {len(recs)}건")
    updated, skipped, mismatch = 0, 0, []

    for rec in recs:
        addr = _str_field(rec["fields"].get(F_DEST_ADDR))
        zone = _classify(addr)
        if not zone:
            skipped += 1
            continue

        if dry_run:
            print(f"  [DRY] {rec['id'][:8]}: '{addr[:25]}' → {zone}")
            updated += 1
            continue

        r = requests.patch(
            f"{url}/{rec['id']}",
            headers={**headers, "Content-Type": "application/json"},
            json={"fields": {F_ZONE: zone}},
            timeout=15,
        )
        r.raise_for_status()
        time.sleep(0.25)

        # Verifier
        verify = requests.get(
            f"{url}/{rec['id']}",
            headers=headers,
            params={"fields[]": [F_ZONE], "returnFieldsByFieldId": "true"},
            timeout=15,
        )
        verify.raise_for_status()
        written = verify.json()["fields"].get(F_ZONE, "")
        if written != zone:
            mismatch.append({"id": rec["id"], "expected": zone, "got": written})
        updated += 1

    return {"created": updated, "skipped": skipped, "mismatch": mismatch}
