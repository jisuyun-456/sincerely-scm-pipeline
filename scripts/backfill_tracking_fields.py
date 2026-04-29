#!/usr/bin/env python3
"""
택배추적로그 — 택배사 & 운송장번호 백필
: 택배사 또는 운송장번호가 비어 있는 TRK 레코드 대상
  - 연결된 Shipment에서 운송장번호 / 배송파트너명 조회
  - 운송장번호: Shipment.운송장번호 → 없으면 셀포트 운송장번호 폴백
  - 택배사: 배송파트너명에서 CARRIER_MAP으로 자동 매핑
"""
import os, time
from collections import defaultdict
import requests

PAT      = os.environ.get("AIRTABLE_PAT") or "patU9ew1rwbJbEpOn.d5c7c1bb42c3ad69edd2701ee0424ddcb04c4d261a0ed422f8e5edaf1fa20edc"
BASE_ID  = "app4x70a8mOrIKsMf"
SHIP_TBL = "tbllg1JoHclGYer7m"
TRK_TBL  = "tblonyqcHGa5V5zbj"
HDRS     = {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}
TRK_URL  = f"https://api.airtable.com/v0/{BASE_ID}/{TRK_TBL}"
SHIP_URL = f"https://api.airtable.com/v0/{BASE_ID}/{SHIP_TBL}"

# ── 택배추적로그 필드 IDs ─────────────────────────────────────────────
F_TRK_SHIP    = "fldmxi2cX7Ozl54Tj"  # Shipment (linked)
F_TRK_CARRIER = "fldDDhjUKPZVgrYH0"  # 택배사 (singleSelect)
F_TRK_NUM     = "fldvzKlwRSlkNCRiA"  # 운송장번호 (text)

# ── Shipment 필드 IDs ─────────────────────────────────────────────────
F_SHIP_NUM      = "fldv4U6Gx4d8BWPTb"  # 운송장번호 (multilineText)
F_SHIP_NUM_CP   = "fldfu9BtKxoRDTvBq"  # 셀포트 운송장번호 (singleLineText, 폴백)
F_SHIP_PARTNER  = "fldHZ7yMT3KEu2gSj"  # 배송파트너 (from 배송파트너) lookup

# 배송파트너명 → 택배사 singleSelect 매핑
# 정확한 Airtable singleSelect 옵션 값 사용
CARRIER_MAP = {
    "로젠":   "로젠택배",
    "CJ":     "CJ대한통운",
    "한진":   "한진택배",
    "우체국": "우체국",
    "롯데":   "롯데택배",
    "로지비": "기타",
}


def carrier_from_partner(partner_val) -> str:
    """배송파트너 lookup 값(str or list) → 택배사 문자열
    매핑 불가 + '택배' 포함이면 '기타' 반환
    """
    if isinstance(partner_val, list):
        text = " ".join(str(v) for v in partner_val)
    else:
        text = str(partner_val or "")
    for key, val in CARRIER_MAP.items():
        if key in text:
            return val
    # 매핑 없지만 택배사인 경우 → 기타
    if "택배" in text:
        return "기타"
    return ""


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


def patch_batch(updates):
    ok = 0
    for i in range(0, len(updates), 10):
        batch = updates[i:i+10]
        r = requests.patch(TRK_URL, headers=HDRS, json={"records": batch})
        if r.status_code == 200:
            ok += len(batch)
        else:
            print(f"  !! PATCH fail: {r.status_code}")
            print(r.text[:300].encode("utf-8", errors="replace").decode("utf-8", errors="replace"))
        time.sleep(0.25)
    return ok


# ── 조회 함수 ─────────────────────────────────────────────────────────

def fetch_incomplete_trk():
    """택배사 또는 운송장번호가 비어 있는 TRK 레코드 조회"""
    formula = 'OR({택배사}=BLANK(), {운송장번호}=BLANK())'
    return paginate(TRK_URL, {
        "filterByFormula": formula,
        "returnFieldsByFieldId": "true",
        "fields[]": [F_TRK_SHIP, F_TRK_CARRIER, F_TRK_NUM],
        "pageSize": 100,
    })


def fetch_ship_data(rec_ids):
    """Shipment 운송장번호 + 배송파트너 배치 조회"""
    result = {}
    for i in range(0, len(rec_ids), 50):
        chunk = rec_ids[i:i+50]
        formula = "OR(" + ",".join(f"RECORD_ID()='{r}'" for r in chunk) + ")"
        recs = paginate(SHIP_URL, {
            "filterByFormula": formula,
            "returnFieldsByFieldId": "true",
            "fields[]": [F_SHIP_NUM, F_SHIP_NUM_CP, F_SHIP_PARTNER],
            "pageSize": 100,
        })
        for rec in recs:
            f = rec["fields"]
            # 운송장번호: 기본 필드 → 셀포트 폴백
            num = str(f.get(F_SHIP_NUM, "") or "").strip()
            if not num:
                num = str(f.get(F_SHIP_NUM_CP, "") or "").strip()
            result[rec["id"]] = {
                "num":     num,
                "carrier": carrier_from_partner(f.get(F_SHIP_PARTNER, "")),
            }
        time.sleep(0.2)
    return result


# ── 메인 ─────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("TRK backfill: 택배사 + 운송장번호")
    print("=" * 60)

    # ── 1. 미완성 TRK 레코드 조회 ───────────────────────────────────
    print("\n[1] 택배사/운송장번호 미입력 TRK 레코드 조회...")
    trks = fetch_incomplete_trk()
    print(f"  대상: {len(trks)}건")
    if not trks:
        print("  모두 완성 — 종료")
        return

    # 부족한 필드 통계
    no_carrier = sum(1 for t in trks if not t["fields"].get(F_TRK_CARRIER))
    no_num     = sum(1 for t in trks if not t["fields"].get(F_TRK_NUM))
    print(f"  택배사 없음: {no_carrier}건  |  운송장번호 없음: {no_num}건")

    # ── 2. Shipment 데이터 조회 ──────────────────────────────────────
    ship_ids = list({
        t["fields"].get(F_TRK_SHIP, [None])[0]
        for t in trks
        if t["fields"].get(F_TRK_SHIP)
    })
    print(f"\n[2] Shipment 조회 ({len(ship_ids)}건)...")
    ship_data = fetch_ship_data(ship_ids)

    # ── 3. PATCH 준비 ────────────────────────────────────────────────
    patches = []
    skipped_no_ship = 0
    stats = defaultdict(int)

    for trk in trks:
        linked = trk["fields"].get(F_TRK_SHIP) or []
        sid    = linked[0] if linked else None
        if not sid or sid not in ship_data:
            skipped_no_ship += 1
            continue

        sd      = ship_data[sid]
        cur_num = str(trk["fields"].get(F_TRK_NUM, "") or "").strip()
        cur_car = str(trk["fields"].get(F_TRK_CARRIER, "") or "").strip()

        fields = {}
        if not cur_num and sd["num"]:
            fields[F_TRK_NUM] = sd["num"]
            stats["운송장번호 채움"] += 1
        if not cur_car and sd["carrier"]:
            fields[F_TRK_CARRIER] = sd["carrier"]
            stats["택배사 채움"] += 1

        if fields:
            patches.append({"id": trk["id"], "fields": fields})

    print(f"\n[3] PATCH 준비:")
    for k, v in stats.items():
        print(f"  {k}: {v}건")
    if skipped_no_ship:
        print(f"  Shipment 링크 없음 (스킵): {skipped_no_ship}건")
    if not patches:
        print("  update target: none")
        return
    print(f"  → 총 업데이트: {len(patches)}건")

    # ── 4. 실행 ─────────────────────────────────────────────────────
    print(f"\n[4] 업데이트 중...")
    ok = patch_batch(patches)
    print(f"  완료: {ok}/{len(patches)}건")

    print(f"\n{'=' * 60}")
    print("완료")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
