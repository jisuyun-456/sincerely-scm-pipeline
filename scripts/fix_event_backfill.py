#!/usr/bin/env python3
"""
배송이벤트 백필 수정
1단계: EVT-rec* 패턴 잘못된 레코드 수정 (PATCH)
  - Shipment의 출하확정일 조회 → EVT-YYYYMMDD-NNN ID 재생성
  - 이벤트유형 = "배송완료" 설정
  - 이벤트일시 = {출하확정일}T09:00:00.000+09:00 설정
2단계: 누락 Shipment 배송이벤트 신규 생성
  - 발송상태_TMS="출하 완료", 배송이벤트=BLANK(), 출하확정일 2026-01-01 이후
"""
import os, time, re
from collections import defaultdict
import requests

PAT     = os.environ.get("AIRTABLE_PAT") or "patU9ew1rwbJbEpOn.d5c7c1bb42c3ad69edd2701ee0424ddcb04c4d261a0ed422f8e5edaf1fa20edc"
BASE_ID = "app4x70a8mOrIKsMf"
SHIP_TBL = "tbllg1JoHclGYer7m"
EVT_TBL  = "tblQyuAW30yf21WEf"
HDRS     = {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}

# 배송이벤트 필드 IDs (기존 스크립트 확인)
F_EVT_ID   = "fld1gqsJsUYlxir5p"  # 이벤트ID
F_EVT_SHIP = "fldIAAYK8bfiVl5iv"  # Shipment (linked)
F_EVT_TYPE = "fldbBqodeAJhAQATW"  # 이벤트유형
F_EVT_DATE = "fld9IsE0lC5p1Pf1a"  # 이벤트일시

BAD_RE   = re.compile(r"^EVT-rec")
VALID_RE = re.compile(r"^EVT-(\d{8})-(\d+)$")

EVT_URL  = f"https://api.airtable.com/v0/{BASE_ID}/{EVT_TBL}"
SHIP_URL = f"https://api.airtable.com/v0/{BASE_ID}/{SHIP_TBL}"


# ── 유틸 ─────────────────────────────────────────────────────────────

def paginate(url, params):
    records, offset = [], None
    while True:
        p = {**params, **({"offset": offset} if offset else {})}
        r = requests.get(url, headers=HDRS, params=p)
        r.raise_for_status()
        data = r.json()
        records += data.get("records", [])
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records


def patch_batch(url, updates):
    ok = 0
    for i in range(0, len(updates), 10):
        batch = updates[i:i+10]
        r = requests.patch(url, headers=HDRS, json={"records": batch})
        if r.status_code == 200:
            ok += len(batch)
        else:
            print(f"  !! PATCH 실패: {r.status_code} – {r.text[:200]}")
        time.sleep(0.25)
    return ok


def post_batch(url, records):
    ok = 0
    for i in range(0, len(records), 10):
        batch = records[i:i+10]
        r = requests.post(url, headers=HDRS, json={"records": batch})
        if r.status_code == 200:
            ok += len(batch)
        else:
            print(f"  !! POST 실패: {r.status_code} – {r.text[:200]}")
        time.sleep(0.25)
    return ok


# ── 데이터 조회 ───────────────────────────────────────────────────────

def fetch_all_events():
    return paginate(EVT_URL, {
        "returnFieldsByFieldId": "true",
        "fields[]": [F_EVT_ID, F_EVT_SHIP],
        "pageSize": 100,
    })


def fetch_shipments_by_rec_ids(rec_ids):
    """record ID 리스트로 Shipment 출하확정일 조회"""
    result = {}
    for i in range(0, len(rec_ids), 50):
        chunk = rec_ids[i:i+50]
        formula = "OR(" + ",".join(f"RECORD_ID()='{r}'" for r in chunk) + ")"
        recs = paginate(SHIP_URL, {
            "filterByFormula": formula,
            "fields[]": ["출하확정일"],
            "pageSize": 100,
        })
        for rec in recs:
            result[rec["id"]] = rec["fields"].get("출하확정일", "")
        time.sleep(0.2)
    return result


def fetch_missing_shipments():
    """배송이벤트 없는 완료 Shipment (2026-01-01 이후)"""
    formula = (
        'AND('
        '  {발송상태_TMS}="출하 완료",'
        '  IS_AFTER({출하확정일},"2025-12-31"),'
        '  {배송이벤트}=BLANK()'
        ')'
    )
    return paginate(SHIP_URL, {
        "filterByFormula": formula,
        "fields[]": ["SC id", "출하확정일"],
        "sort[0][field]": "출하확정일",
        "sort[0][direction]": "asc",
        "pageSize": 100,
    })


# ── 메인 ─────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("배송이벤트 백필 수정")
    print("=" * 60)

    # ── 1. 전체 이벤트 조회 & 분류 ─────────────────────────────────
    print("\n[1] 배송이벤트 전체 조회...")
    all_evts = fetch_all_events()
    bad   = [e for e in all_evts if BAD_RE.match(e["fields"].get(F_EVT_ID, ""))]
    valid = [e for e in all_evts if VALID_RE.match(e["fields"].get(F_EVT_ID, ""))]
    other = len(all_evts) - len(bad) - len(valid)
    print(f"  전체: {len(all_evts)}건  |  유효: {len(valid)}  |  잘못된(EVT-rec*): {len(bad)}  |  기타: {other}")

    # 날짜별 최대 시퀀스 카운터 (기존 유효 레코드 기준)
    date_counter = defaultdict(int)
    for e in valid:
        m = VALID_RE.match(e["fields"].get(F_EVT_ID, ""))
        if m:
            dk, seq = m.group(1), int(m.group(2))
            date_counter[dk] = max(date_counter[dk], seq)

    # ── 2. 잘못된 레코드 수정 (PATCH) ──────────────────────────────
    if bad:
        print(f"\n[2] 잘못된 레코드 수정 ({len(bad)}건)...")

        # 연결 Shipment IDs 수집
        ship_ids = list({
            e["fields"].get(F_EVT_SHIP, [None])[0]
            for e in bad
            if e["fields"].get(F_EVT_SHIP)
        })
        print(f"  Shipment 출하확정일 조회 ({len(ship_ids)}건)...")
        ship_dates = fetch_shipments_by_rec_ids(ship_ids)

        # 날짜별로 그룹화 후 ID 재생성
        date_groups = defaultdict(list)
        for e in bad:
            linked = e["fields"].get(F_EVT_SHIP) or []
            sid    = linked[0] if linked else None
            cdate  = ship_dates.get(sid, "") if sid else ""
            dk     = cdate.replace("-", "") if cdate else "00000000"
            date_groups[dk].append((e["id"], cdate))

        patches = []
        for dk in sorted(date_groups):
            for rec_id, cdate in date_groups[dk]:
                date_counter[dk] += 1
                new_id = f"EVT-{dk}-{date_counter[dk]:03d}"
                fields = {
                    F_EVT_ID:   new_id,
                    F_EVT_TYPE: "배송완료",
                }
                if cdate:
                    fields[F_EVT_DATE] = f"{cdate}T09:00:00.000+09:00"
                patches.append({"id": rec_id, "fields": fields})

        fixed = patch_batch(EVT_URL, patches)
        print(f"  수정 완료: {fixed}/{len(bad)}건")

        # 수정 내역 요약
        for dk in sorted(date_groups):
            cnt = len(date_groups[dk])
            print(f"    {dk[:4]}-{dk[4:6]}-{dk[6:]}: {cnt}건 → EVT-{dk}-{date_counter[dk]-cnt+1:03d}~{date_counter[dk]:03d}")
    else:
        print("\n[2] 잘못된 레코드 없음 – 스킵")

    # ── 3. 누락 Shipment 백필 (POST) ────────────────────────────────
    print(f"\n[3] 누락 Shipment 배송이벤트 생성...")
    missing = fetch_missing_shipments()
    print(f"  누락 대상: {len(missing)}건")

    if missing:
        # 월별 분포 출력
        monthly = defaultdict(int)
        for s in missing:
            d = s["fields"].get("출하확정일", "")
            monthly[d[:7] if d else "unknown"] += 1
        for m in sorted(monthly):
            print(f"    {m}: {monthly[m]}건")

        new_recs = []
        for shp in missing:
            cdate = shp["fields"].get("출하확정일", "")
            dk    = cdate.replace("-", "") if cdate else "00000000"
            date_counter[dk] += 1
            evt_id = f"EVT-{dk}-{date_counter[dk]:03d}"

            fields = {
                F_EVT_ID:   evt_id,
                F_EVT_SHIP: [shp["id"]],
                F_EVT_TYPE: "배송완료",
            }
            if cdate:
                fields[F_EVT_DATE] = f"{cdate}T09:00:00.000+09:00"
            new_recs.append({"fields": fields})

        created = post_batch(EVT_URL, new_recs)
        print(f"  생성 완료: {created}/{len(missing)}건")
    else:
        print("  누락 없음")

    print(f"\n{'=' * 60}")
    print("완료")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
