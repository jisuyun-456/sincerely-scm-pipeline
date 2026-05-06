#!/usr/bin/env python3
"""
Shipment 구간유형 자동 분류 백필
- 대상: 구간유형 BLANK + 출하확정일 최근 30일
- 분류 기준: 수령인(주소) 키워드 매칭
- 옵션: --apply 없으면 DRY-RUN (분포만 출력, PATCH 없음)

W17 보고서 명시 로직:
  ① 접두어 제거 ^\([^)]+\)\s*
  ② METRO_CITY (서울 25구 + 인천 8구 + 경기 시/군)
  ③ METRO_BIG (광역시 5)
  ④ DOSEO_SANGAN (제주/울릉/백령/흑산/홍도)
  ⑤ RURAL_CITY (지방 시·군)
"""
import os
import re
import sys
import time
import argparse
from collections import Counter
from datetime import date, timedelta

import requests

PAT = os.environ.get("AIRTABLE_PAT")
if not PAT:
    sys.exit("ERROR: AIRTABLE_PAT 환경변수 필요")

BASE_ID  = "app4x70a8mOrIKsMf"
SHIP_TBL = "tbllg1JoHclGYer7m"
HDRS_R   = {"Authorization": f"Bearer {PAT}"}
HDRS_W   = {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}
SHIP_URL = f"https://api.airtable.com/v0/{BASE_ID}/{SHIP_TBL}"

# 필드 IDs
F_ZONE = "fldp6haTDFzzF5C74"  # 구간유형 (singleSelect)
F_ADDR = "fldyJHUh9gN44Ggnh"  # 수령인(주소) (rollup)
F_DATE = "fldQvmEwwzvQW95h9"  # 출하확정일

# ── 분류 키워드 ────────────────────────────────────────────────
SEOUL_GU = [
    "종로구","중구","용산구","성동구","광진구","동대문구","중랑구","성북구","강북구",
    "도봉구","노원구","은평구","서대문구","마포구","양천구","강서구","구로구","금천구",
    "영등포구","동작구","관악구","서초구","강남구","송파구","강동구",
]
INCHEON_GU = ["미추홀구","연수구","남동구","부평구","계양구","서구","중구","동구","강화군","옹진군"]
GYEONGGI_CITY = [
    "수원","성남","의정부","안양","부천","광명","평택","동두천","안산","고양","과천","구리",
    "남양주","오산","시흥","군포","의왕","하남","용인","파주","이천","안성","김포","화성",
    "광주시","양주","포천","여주","연천","가평","양평",
]
METRO_BIG = ["부산","대구","대전","광주광역시","광주 서구","광주 북구","광주 동구","광주 남구","광주 광산구","울산"]
DOSEO_SANGAN = ["제주","서귀포","울릉","백령","흑산","홍도","연평","대청"]
RURAL_CITY = [
    "춘천","원주","강릉","동해","속초","삼척","태백","정선","영월","평창","홍천","횡성","철원","화천","양구","인제","고성",
    "청주","충주","제천","천안","아산","보령","서산","논산","계룡","당진",
    "전주","군산","익산","정읍","남원","김제",
    "목포","여수","순천","광양","나주",
    "포항","경주","김천","안동","구미","영주","영천","상주","문경","경산",
    "창원","진주","통영","사천","김해","밀양","거제","양산",
]

# 서울 구는 단독 사용 시 모호하므로 "서울" 또는 "특별시" 동반 매칭 또는 키워드 + "구"
SEOUL_KEYWORDS = ["서울", "특별시"]
INCHEON_KEYWORDS = ["인천"]


def normalize(addr: str) -> str:
    if not addr:
        return ""
    if isinstance(addr, list):
        addr = " ".join(str(a) for a in addr if a)
    addr = str(addr)
    # 접두어 (창고) 등 제거
    addr = re.sub(r"^\([^)]+\)\s*", "", addr)
    return addr.strip()


def classify(addr: str) -> str | None:
    a = normalize(addr)
    if not a:
        return None

    # 1) 도서산간 우선
    if any(k in a for k in DOSEO_SANGAN):
        return "도서산간"

    # 2) 수도권 (서울/인천/경기)
    if any(k in a for k in SEOUL_KEYWORDS) and any(g in a for g in SEOUL_GU):
        return "수도권"
    if a.startswith("서울"):
        return "수도권"
    if any(k in a for k in INCHEON_KEYWORDS):
        return "수도권"
    if any(k in a for k in GYEONGGI_CITY):
        # 경기 키워드 동반 시 신뢰도↑, 단독도 허용
        return "수도권"

    # 3) 광역시
    if any(k in a for k in METRO_BIG):
        return "지방(광역시)"

    # 4) 지방 일반
    if any(k in a for k in RURAL_CITY):
        return "지방(기타)"

    return None


def fetch_targets(days: int = 30) -> list[dict]:
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    formula = (
        f'AND('
        f'  IS_AFTER({{출하확정일}},"{cutoff}"),'
        f'  {{구간유형}}=BLANK()'
        f')'
    )
    out = []
    params = {
        "filterByFormula": formula,
        "returnFieldsByFieldId": "true",
        "fields[]": [F_ZONE, F_ADDR, F_DATE],
        "pageSize": 100,
    }
    while True:
        r = requests.get(SHIP_URL, headers=HDRS_R, params=params, timeout=60)
        r.raise_for_status()
        data = r.json()
        out.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        params["offset"] = offset
    return out


def patch_batch(records: list[dict]) -> int:
    """records: [{id, fields:{F_ZONE: '수도권'}}, ...]  최대 10개씩"""
    updated = 0
    for i in range(0, len(records), 10):
        chunk = records[i:i + 10]
        body = {"records": chunk, "typecast": False, "returnFieldsByFieldId": True}
        r = requests.patch(SHIP_URL, headers=HDRS_W, json=body, timeout=60)
        if r.status_code != 200:
            print(f"  PATCH FAIL {r.status_code}: {r.text[:200]}")
            continue
        updated += len(chunk)
        time.sleep(0.25)
    return updated


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제 PATCH 적용 (기본: DRY-RUN)")
    ap.add_argument("--days", type=int, default=30, help="최근 N일 (기본 30)")
    args = ap.parse_args()

    print("=" * 70)
    print(f"Shipment 구간유형 자동 분류  ({'APPLY' if args.apply else 'DRY-RUN'}) — 최근 {args.days}일")
    print("=" * 70)

    print("\n[1] 대상 조회 ...", end=" ", flush=True)
    targets = fetch_targets(args.days)
    print(f"{len(targets)}건")

    print("\n[2] 분류 ...")
    classified: list[tuple[dict, str]] = []
    unclassified: list[dict] = []
    dist = Counter()
    for rec in targets:
        addr = rec["fields"].get(F_ADDR, "")
        zone = classify(addr)
        if zone:
            classified.append((rec, zone))
            dist[zone] += 1
        else:
            unclassified.append(rec)
            dist["(미분류)"] += 1

    for k, v in dist.most_common():
        print(f"  {k:<12} {v:>5}건")

    print(f"\n  분류 가능   : {len(classified):>5}건")
    print(f"  미분류 보존 : {len(unclassified):>5}건  (구간유형 BLANK 유지)")

    # 미분류 샘플 5건
    if unclassified:
        print("\n  미분류 샘플 (앞 5건):")
        for rec in unclassified[:5]:
            addr = rec["fields"].get(F_ADDR, "")
            d = rec["fields"].get(F_DATE, "")
            print(f"    {d}  {normalize(addr)[:60]}")

    # 분류 샘플 5건
    if classified:
        print("\n  분류 샘플 (앞 5건):")
        for rec, zone in classified[:5]:
            addr = rec["fields"].get(F_ADDR, "")
            d = rec["fields"].get(F_DATE, "")
            print(f"    {d}  [{zone}]  {normalize(addr)[:60]}")

    if not args.apply:
        print("\n→ DRY-RUN 종료. 적용하려면: --apply 옵션 추가")
        return

    if not classified:
        print("\n→ 적용할 레코드 없음. 종료.")
        return

    print(f"\n[3] PATCH 적용 — {len(classified)}건 ...")
    patch_records = [
        {"id": rec["id"], "fields": {F_ZONE: zone}}
        for rec, zone in classified
    ]
    n = patch_batch(patch_records)
    print(f"  ✅ 업데이트: {n}건")


if __name__ == "__main__":
    main()
