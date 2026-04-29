#!/usr/bin/env python3
"""
택배추적로그 백필 수정
1단계: TRK-rec* 패턴 잘못된 레코드 수정 (PATCH)
  - Shipment의 출하확정일/배송파트너 조회 → TRK-YYYYMMDD-NNN ID 재생성
  - 추적상태 = "배송완료" 설정
  - 추적일시 = {출하확정일}T09:00:00.000+09:00 교정
  - 택배사 = 배송파트너에서 자동 매핑
2단계: 누락 Shipment 택배추적로그 신규 생성
  - 발송상태_TMS="출하 완료", 택배추적로그=BLANK(), 출하확정일 2026-01-01 이후
  - 배송방식에 "택배" 포함된 건만 대상
"""
import os, time, re
from collections import defaultdict
import requests

PAT      = os.environ.get("AIRTABLE_PAT") or "patU9ew1rwbJbEpOn.d5c7c1bb42c3ad69edd2701ee0424ddcb04c4d261a0ed422f8e5edaf1fa20edc"
BASE_ID  = "app4x70a8mOrIKsMf"
SHIP_TBL = "tbllg1JoHclGYer7m"
TRK_TBL  = "tblonyqcHGa5V5zbj"
HDRS     = {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}
META_URL = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables"
TRK_URL  = f"https://api.airtable.com/v0/{BASE_ID}/{TRK_TBL}"
SHIP_URL = f"https://api.airtable.com/v0/{BASE_ID}/{SHIP_TBL}"

BAD_RE   = re.compile(r"^TRK-rec")
VALID_RE = re.compile(r"^TRK-(\d{8})-(\d+)$")

# 배송파트너 → 택배사 매핑
CARRIER_MAP = {
    "로젠": "로젠택배",
    "로지비": "로지비택배",
    "CJ":   "CJ대한통운",
    "한진": "한진택배",
    "우체국": "우체국택배",
}


def map_carrier(partner_str: str) -> str:
    """배송파트너 문자열 → 택배사 singleSelect 값"""
    if not partner_str:
        return ""
    for key, val in CARRIER_MAP.items():
        if key in partner_str:
            return val
    # "택배" 포함이면 파트너명 그대로 반환
    if "택배" in partner_str:
        return partner_str.strip()
    return ""


# ── 필드 ID 자동 발견 ─────────────────────────────────────────────────

def discover_fields():
    """Metadata API로 택배추적로그 + Shipment 필드 ID 매핑 반환"""
    r = requests.get(META_URL, headers=HDRS)
    r.raise_for_status()
    tables = r.json().get("tables", [])

    trk_fields  = {}
    ship_fields = {}
    for tbl in tables:
        fmap = {f["name"]: f["id"] for f in tbl.get("fields", [])}
        if tbl["id"] == TRK_TBL:
            trk_fields = fmap
        elif tbl["id"] == SHIP_TBL:
            ship_fields = fmap

    return trk_fields, ship_fields


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

def fetch_all_tracking(f_trk_id, f_ship_link):
    return paginate(TRK_URL, {
        "returnFieldsByFieldId": "true",
        "fields[]": [f_trk_id, f_ship_link],
        "pageSize": 100,
    })


def fetch_shipments_by_rec_ids(rec_ids, f_date, f_partner, f_delivery_type):
    result = {}
    field_ids = [f for f in [f_date, f_partner, f_delivery_type] if f]  # 빈 ID 제거
    for i in range(0, len(rec_ids), 50):
        chunk = rec_ids[i:i+50]
        formula = "OR(" + ",".join(f"RECORD_ID()='{r}'" for r in chunk) + ")"
        recs = paginate(SHIP_URL, {
            "filterByFormula": formula,
            "returnFieldsByFieldId": "true",
            "fields[]": field_ids,
            "pageSize": 100,
        })
        for rec in recs:
            flds = rec["fields"]
            result[rec["id"]] = {
                "date":    flds.get(f_date, ""),
                "partner": flds.get(f_partner, ""),
                "dtype":   flds.get(f_delivery_type, "") if f_delivery_type else "",
            }
        time.sleep(0.2)
    return result


def fetch_missing_shipments(f_date, f_partner, f_delivery_type):
    """택배 배송, 완료, 추적로그 없음, 2026-01-01 이후"""
    # 배송방식 필터: 필드명 기반 포뮬라 (필드 ID 없어도 이름으로 동작)
    # 배송파트너에 "택배"가 포함된 경우도 포함
    formula = (
        'AND('
        '  {발송상태_TMS}="출하 완료",'
        '  IS_AFTER({출하확정일},"2025-12-31"),'
        '  {택배추적로그}=BLANK(),'
        '  OR(FIND("택배",{배송파트너})>0,FIND("로젠",{배송파트너})>0,'
        '     FIND("로지비",{배송파트너})>0,FIND("CJ",{배송파트너})>0)'
        ')'
    )
    field_ids = [f for f in ["SC id", f_date, f_partner] if f]  # 빈 ID 제거
    return paginate(SHIP_URL, {
        "filterByFormula": formula,
        "returnFieldsByFieldId": "true",
        "fields[]": field_ids,
        "sort[0][field]": "출하확정일",
        "sort[0][direction]": "asc",
        "pageSize": 100,
    })


# ── 메인 ─────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("택배추적로그 백필 수정")
    print("=" * 60)

    # ── 0. 필드 ID 발견 ─────────────────────────────────────────────
    print("\n[0] Metadata API로 필드 ID 발견...")
    trk_fields, ship_fields = discover_fields()

    # 택배추적로그 필드
    f_trk_id    = trk_fields.get("추적ID", "")
    f_ship_link = trk_fields.get("Shipment", "")
    f_carrier   = trk_fields.get("택배사", "")
    f_trk_num   = trk_fields.get("운송장번호", "")
    f_status    = trk_fields.get("추적상태", "")
    f_trk_date  = trk_fields.get("추적일시", "")

    print(f"  택배추적로그 필드:")
    for name, fid in [("추적ID", f_trk_id), ("Shipment", f_ship_link),
                      ("택배사", f_carrier), ("운송장번호", f_trk_num),
                      ("추적상태", f_status), ("추적일시", f_trk_date)]:
        print(f"    {name}: {fid or '(발견 못함)'}")

    if not f_trk_id or not f_ship_link:
        print("  !! 필수 필드 ID 발견 실패. 종료.")
        print(f"  발견된 필드 목록: {list(trk_fields.keys())}")
        return

    # Shipment 필드
    f_date          = ship_fields.get("출하확정일", "")
    f_partner       = ship_fields.get("배송파트너", "")
    f_delivery_type = ship_fields.get("배송방식", "")

    print(f"\n  Shipment 필드:")
    for name, fid in [("출하확정일", f_date), ("배송파트너", f_partner), ("배송방식", f_delivery_type)]:
        print(f"    {name}: {fid or '(발견 못함)'}")

    if not f_date:
        print("  !! Shipment 출하확정일 필드 ID 발견 실패. 종료.")
        return

    # ── 1. 전체 추적로그 조회 & 분류 ───────────────────────────────
    print(f"\n[1] 택배추적로그 전체 조회...")
    all_trks = fetch_all_tracking(f_trk_id, f_ship_link)
    bad   = [t for t in all_trks if BAD_RE.match(t["fields"].get(f_trk_id, ""))]
    valid = [t for t in all_trks if VALID_RE.match(t["fields"].get(f_trk_id, ""))]
    other = len(all_trks) - len(bad) - len(valid)
    print(f"  전체: {len(all_trks)}건  |  유효: {len(valid)}  |  잘못된(TRK-rec*): {len(bad)}  |  기타(숫자ID 등): {other}")

    # 날짜별 최대 시퀀스 카운터
    date_counter = defaultdict(int)
    for t in valid:
        m = VALID_RE.match(t["fields"].get(f_trk_id, ""))
        if m:
            dk, seq = m.group(1), int(m.group(2))
            date_counter[dk] = max(date_counter[dk], seq)

    # ── 2. 잘못된 레코드 수정 (PATCH) ──────────────────────────────
    if bad:
        print(f"\n[2] 잘못된 레코드 수정 ({len(bad)}건)...")

        ship_ids = list({
            t["fields"].get(f_ship_link, [None])[0]
            for t in bad
            if t["fields"].get(f_ship_link)
        })
        print(f"  Shipment 정보 조회 ({len(ship_ids)}건)...")
        ship_info = fetch_shipments_by_rec_ids(ship_ids, f_date, f_partner, f_delivery_type)

        date_groups = defaultdict(list)
        for t in bad:
            linked = t["fields"].get(f_ship_link) or []
            sid    = linked[0] if linked else None
            info   = ship_info.get(sid, {}) if sid else {}
            cdate  = info.get("date", "")
            dk     = cdate.replace("-", "") if cdate else "00000000"
            date_groups[dk].append((t["id"], cdate, info.get("partner", "")))

        patches = []
        for dk in sorted(date_groups):
            for rec_id, cdate, partner in date_groups[dk]:
                date_counter[dk] += 1
                new_id  = f"TRK-{dk}-{date_counter[dk]:03d}"
                carrier = map_carrier(str(partner))

                fields = {f_trk_id: new_id}
                if f_status:
                    fields[f_status] = "배송완료"
                if f_trk_date and cdate:
                    fields[f_trk_date] = f"{cdate}T09:00:00.000+09:00"
                if f_carrier and carrier:
                    fields[f_carrier] = carrier

                patches.append({"id": rec_id, "fields": fields})

        fixed = patch_batch(TRK_URL, patches)
        print(f"  수정 완료: {fixed}/{len(bad)}건")

        for dk in sorted(date_groups):
            cnt = len(date_groups[dk])
            print(f"    {dk[:4]}-{dk[4:6]}-{dk[6:]}: {cnt}건 → TRK-{dk}-{date_counter[dk]-cnt+1:03d}~{date_counter[dk]:03d}")
    else:
        print("\n[2] 잘못된 레코드 없음 – 스킵")

    # ── 3. 누락 Shipment 백필 (POST) ────────────────────────────────
    print(f"\n[3] 누락 택배 Shipment 추적로그 생성...")
    missing = fetch_missing_shipments(f_date, f_partner, f_delivery_type)
    print(f"  누락 대상: {len(missing)}건")

    if missing:
        monthly = defaultdict(int)
        for s in missing:
            d = s["fields"].get(f_date, "")
            monthly[d[:7] if d else "unknown"] += 1
        for m in sorted(monthly):
            print(f"    {m}: {monthly[m]}건")

        new_recs = []
        for shp in missing:
            cdate   = shp["fields"].get(f_date, "")
            partner = shp["fields"].get(f_partner, "")
            carrier = map_carrier(str(partner))
            dk      = cdate.replace("-", "") if cdate else "00000000"
            date_counter[dk] += 1
            trk_id  = f"TRK-{dk}-{date_counter[dk]:03d}"

            fields = {f_trk_id: trk_id, f_ship_link: [shp["id"]]}
            if f_status:
                fields[f_status] = "배송완료"
            if f_trk_date and cdate:
                fields[f_trk_date] = f"{cdate}T09:00:00.000+09:00"
            if f_carrier and carrier:
                fields[f_carrier] = carrier

            new_recs.append({"fields": fields})

        created = post_batch(TRK_URL, new_recs)
        print(f"  생성 완료: {created}/{len(missing)}건")
    else:
        print("  누락 없음")

    print(f"\n{'=' * 60}")
    print("완료")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
