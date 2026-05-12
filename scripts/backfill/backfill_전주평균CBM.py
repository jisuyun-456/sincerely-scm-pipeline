"""
배차일지 전주평균CBM 백필
- 조건: 대상 주간 배차일지의 linked Shipments에서 '총N박스' 파싱
- 동작: 평균 박스수/건을 전주_평균_CBM 필드에 PATCH
- Verifier: PATCH 후 GET으로 값 재확인 → 불일치 시 mismatch 누적
"""
import re
import time
from datetime import date

import requests

BASE_ID      = "app4x70a8mOrIKsMf"
TBL_SHIPMENT = "tbllg1JoHclGYer7m"
TBL_DISPATCH = "tbl0YCjOC7rYtyXHV"

FLD_DISP_DATE      = "fldZh2mZDIPQXfOcO"
FLD_DISP_SHIPMENTS = "flddCIndicSSe8uhi"  # 배정물량_합계 (link to Shipment)
FLD_DISP_CBM_AVG   = "fldguj0nIYH7hMpXc"  # 전주_평균_CBM

F_BOX_TEXT = "fldTjLDmw5sNGszeD"  # 최종 외박스 수량 값


def _parse_total_boxes(box_text: str) -> int:
    if not box_text:
        return 0
    m = re.search(r"총(\d+)박스", box_text)
    return int(m.group(1)) if m else 0


def _fetch_shipment_boxes(headers, rec_id: str) -> int:
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_SHIPMENT}/{rec_id}"
    r = requests.get(
        url,
        headers=headers,
        params={"fields[]": [F_BOX_TEXT], "returnFieldsByFieldId": "true"},
        timeout=15,
    )
    r.raise_for_status()
    raw = r.json()["fields"].get(F_BOX_TEXT, "")
    return _parse_total_boxes(str(raw or ""))


def run(headers, start: date, end: date, dry_run: bool) -> dict:
    url_disp = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_DISPATCH}"
    formula = (
        f'AND({{날짜}}>="{start.isoformat()}",'
        f'{{날짜}}<="{end.isoformat()}")'
    )
    params = {
        "filterByFormula": formula,
        "fields[]": [FLD_DISP_DATE, FLD_DISP_SHIPMENTS, FLD_DISP_CBM_AVG],
        "pageSize": 100,
        "returnFieldsByFieldId": "true",
    }
    r = requests.get(url_disp, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    disp_recs = r.json().get("records", [])

    if not disp_recs:
        return {"created": 0, "skipped": 0, "mismatch": [], "message": "대상 없음"}

    updated, skipped, mismatch = 0, 0, []

    for rec in disp_recs:
        f = rec["fields"]
        shp_links = f.get(FLD_DISP_SHIPMENTS) or []
        if not shp_links:
            skipped += 1
            continue

        shp_ids = [s["id"] if isinstance(s, dict) else s for s in shp_links]
        box_counts = []
        for sid in shp_ids:
            try:
                n = _fetch_shipment_boxes(headers, sid)
                box_counts.append(n)
                time.sleep(0.15)
            except Exception:
                pass

        if not box_counts:
            skipped += 1
            continue

        avg_cbm = round(sum(box_counts) / len(box_counts), 1)

        if dry_run:
            d = (f.get(FLD_DISP_DATE) or "")[:10]
            print(f"  [DRY] {d}: boxes={box_counts} → avg={avg_cbm}")
            updated += 1
            continue

        r2 = requests.patch(
            f"{url_disp}/{rec['id']}",
            headers={**headers, "Content-Type": "application/json"},
            json={"fields": {FLD_DISP_CBM_AVG: avg_cbm}},
            timeout=15,
        )
        r2.raise_for_status()
        time.sleep(0.25)

        # Verifier
        verify = requests.get(
            f"{url_disp}/{rec['id']}",
            headers=headers,
            params={"fields[]": [FLD_DISP_CBM_AVG], "returnFieldsByFieldId": "true"},
            timeout=15,
        )
        verify.raise_for_status()
        written = verify.json()["fields"].get(FLD_DISP_CBM_AVG)
        if written != avg_cbm:
            mismatch.append({"id": rec["id"], "expected": avg_cbm, "got": written})
        updated += 1

    return {"created": updated, "skipped": skipped, "mismatch": mismatch}
