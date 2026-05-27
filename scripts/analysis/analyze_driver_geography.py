"""자체 기사별 실제 배송 지역 분포 분석 (P3 brainstorm 입력)

기간: 2024-01-01 ~ 2026-05-27
대상: 자체 기사 3명 (이장훈 CA-0002 / 박종성 CA-0003 / 조희선 CA-NEW-1)

산출:
- 기사별 historical destination region 분포
- (region, count, %) 출력
"""
import os
import json
import sys
import urllib.parse
import urllib.request
import urllib.error
from collections import Counter, defaultdict

PAT = os.environ.get("AIRTABLE_PAT")
if not PAT and len(sys.argv) > 1:
    PAT = sys.argv[1]
if not PAT:
    raise SystemExit("AIRTABLE_PAT required")

BASE = "app4x70a8mOrIKsMf"
SHIPMENT = "tbllg1JoHclGYer7m"
URL = f"https://api.airtable.com/v0/{BASE}/{SHIPMENT}"

# 배차담당 multipleLookupValues — display name or record ID
FIELDS = ["출하확정일", "배송파트너", "수령인(주소)", "배송 방식"]
DATE_FROM = "2024-01-01"
DATE_TO = "2026-05-27"

# 자체 3 기사 (P1에서 정정 후 carrier_id)
DRIVER_REC_IDS = {
    "recyVExCkk2Lty0E9": "이장훈",
    "recXCfwVTqaoeQ9SS": "박종성",
    "recPkgE4o3cs0krnR": "조희선",
}

def fetch_all():
    records = []
    offset = None
    page = 0
    while True:
        page += 1
        qs = "&".join(f"fields[]={urllib.parse.quote(f)}" for f in FIELDS)
        qs += "&pageSize=100"
        if offset:
            qs += f"&offset={urllib.parse.quote(offset)}"
        req = urllib.request.Request(
            f"{URL}?{qs}",
            headers={"Authorization": f"Bearer {PAT}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            print(f"HTTPError {e.code}: {e.read()[:200].decode()}", file=sys.stderr)
            raise
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if page % 10 == 0:
            print(f"  ... page {page}, cumulative {len(records)}", file=sys.stderr)
        if not offset:
            break
    return records

def in_range(r):
    val = r.get("fields", {}).get("출하확정일")
    if isinstance(val, list):
        val = val[0] if val else None
    return val and DATE_FROM <= str(val)[:10] <= DATE_TO

# 광역시·도 추출
PROVINCES = ["서울", "경기", "인천", "부산", "대구", "광주", "대전", "울산", "세종",
             "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
GYEONGGI_CITIES = ["수원", "용인", "고양", "성남", "부천", "안산", "남양주", "안양", "화성",
                   "평택", "의정부", "시흥", "파주", "광명", "김포", "광주", "군포", "오산",
                   "이천", "양주", "구리", "안성", "포천", "의왕", "하남", "여주", "동두천",
                   "과천", "가평", "연천", "양평"]

def extract_province(addr):
    if not addr:
        return "(NULL)"
    s = str(addr).strip()
    for p in PROVINCES:
        if s.startswith(p) or f" {p}" in s[:30]:
            return p
    return "기타"

def extract_city_in_gyeonggi(addr):
    s = str(addr)
    for city in GYEONGGI_CITIES:
        if city in s:
            return city
    return "(미상)"

if __name__ == "__main__":
    all_records = fetch_all()
    print(f"TOTAL fetched: {len(all_records)}")

    in_window = [r for r in all_records if in_range(r)]
    print(f"In 2024-01-01 ~ 2026-05-27: {len(in_window)}")

    # 자체 기사 분리 (배송파트너 record ID 기준)
    by_driver = defaultdict(list)
    for r in in_window:
        f = r.get("fields", {})
        partner_ids = f.get("배송파트너", [])
        if isinstance(partner_ids, str):
            partner_ids = [partner_ids]
        for pid in partner_ids:
            if pid in DRIVER_REC_IDS:
                name = DRIVER_REC_IDS[pid]
                by_driver[name].append(r)
                break  # only count once even if multiple links

    print(f"\n자체 기사 배송 record 수:")
    for name in DRIVER_REC_IDS.values():
        print(f"  {name}: {len(by_driver[name])}")

    # 기사별 province 분포
    print(f"\n=== 기사별 광역시·도 분포 ===")
    for name in ["이장훈", "조희선", "박종성"]:
        bucket = by_driver.get(name, [])
        if not bucket:
            print(f"\n  ▸ {name}: NO DATA")
            continue
        province_counts = Counter()
        for r in bucket:
            addr = r["fields"].get("수령인(주소)")
            if isinstance(addr, list):
                addr = addr[0] if addr else ""
            province_counts[extract_province(addr)] += 1
        print(f"\n  ▸ {name} (n={len(bucket)})")
        for prov, cnt in province_counts.most_common(15):
            pct = cnt * 100 / len(bucket)
            print(f"    {prov}: {cnt} ({pct:.1f}%)")

    # 이장훈 경기도 cities 세부 (사용자 핵심 결정 포인트)
    print(f"\n=== 이장훈 경기도 city 세부 분포 ===")
    bucket = by_driver.get("이장훈", [])
    gyeonggi_cities = Counter()
    for r in bucket:
        addr = r["fields"].get("수령인(주소)")
        if isinstance(addr, list):
            addr = addr[0] if addr else ""
        if "경기" in str(addr):
            gyeonggi_cities[extract_city_in_gyeonggi(addr)] += 1
    for city, cnt in gyeonggi_cities.most_common(20):
        pct = cnt * 100 / len(bucket) if bucket else 0
        print(f"  {city}: {cnt} ({pct:.1f}%)")

    # 조희선 경기/인천 + 박종성 전국 세부
    for name in ["조희선", "박종성"]:
        print(f"\n=== {name} 광역시·도 외 세부 ===")
        bucket = by_driver.get(name, [])
        gyeonggi_cities = Counter()
        outside_metro = Counter()
        for r in bucket:
            addr = r["fields"].get("수령인(주소)")
            if isinstance(addr, list):
                addr = addr[0] if addr else ""
            s = str(addr)
            if "경기" in s:
                gyeonggi_cities[extract_city_in_gyeonggi(s)] += 1
            else:
                prov = extract_province(s)
                if prov not in ("서울", "(NULL)", "경기"):
                    outside_metro[prov] += 1
        print(f"  경기도 city top 10:")
        for city, cnt in gyeonggi_cities.most_common(10):
            print(f"    {city}: {cnt}")
        if outside_metro:
            print(f"  비수도권 분포:")
            for prov, cnt in outside_metro.most_common(15):
                pct = cnt * 100 / len(bucket) if bucket else 0
                print(f"    {prov}: {cnt} ({pct:.1f}%)")
