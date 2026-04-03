"""
Shipment 구간유형 백필: 수령인(주소) 기반 자동 분류
- 수도권: 서울, 경기, 인천
- 지방(광역시): 부산, 대구, 광주, 대전, 울산, 세종
- 도서산간: 제주, 울릉
- 지방(기타): 나머지 시/도
"""
import requests, time, json
from collections import Counter

PAT = "patU9ew1rwbJbEpOn.d5c7c1bb42c3ad69edd2701ee0424ddcb04c4d261a0ed422f8e5edaf1fa20edc"
BASE_ID = "app4x70a8mOrIKsMf"
SHIPMENT_TABLE = "tbllg1JoHclGYer7m"
HEADERS = {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}

ZONE_FIELD_ID = "fldp6haTDFzzF5C74"
ADDRESS_FIELD_ID = "fldyJHUh9gN44Ggnh"  # 수령인(주소) rollup

# 분류 규칙
METRO = ["서울", "경기", "인천"]
METRO_METRO = ["서울특별시", "서울시", "경기도", "경기", "인천광역시", "인천시", "인천"]
REGIONAL_CITY = ["부산", "대구", "광주", "대전", "울산", "세종"]
ISLAND = ["제주", "울릉"]
RURAL = ["강원", "충북", "충남", "충청북", "충청남", "전북", "전남", "전라북", "전라남",
         "경북", "경남", "경상북", "경상남"]


def classify_address(addr):
    """주소 문자열 → 구간유형 반환"""
    if not addr or addr.strip() in ("", "방문수령", "-", ".", "미정"):
        return None

    addr = addr.strip()

    # 도서산간 체크 (우선)
    for kw in ISLAND:
        if kw in addr[:10]:
            return "도서산간"

    # 수도권 체크
    for kw in METRO:
        if addr.startswith(kw) or kw in addr[:6]:
            return "수도권"

    # 지방(광역시) 체크
    for kw in REGIONAL_CITY:
        if kw in addr[:6]:
            return "지방(광역시)"

    # 지방(기타) 체크
    for kw in RURAL:
        if kw in addr[:8]:
            return "지방(기타)"

    # 판별 불가 → None
    return None


def fetch_all_shipments():
    """주소 있고 구간유형 미입력 Shipment 조회"""
    all_records = []
    params = {
        "filterByFormula": 'AND({수령인(주소)} != "", {구간유형} = BLANK())',
        "fields[]": ["SC id", "수령인(주소)"],
        "pageSize": 100
    }
    url = f"https://api.airtable.com/v0/{BASE_ID}/{SHIPMENT_TABLE}"
    offset = None

    while True:
        if offset:
            params["offset"] = offset
        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()
        records = data.get("records", [])
        all_records.extend(records)
        print(f"  Fetched {len(records)} (total: {len(all_records)})")
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)

    return all_records


def update_zones(updates):
    """구간유형 배치 업데이트"""
    url = f"https://api.airtable.com/v0/{BASE_ID}/{SHIPMENT_TABLE}"
    updated = 0
    failed = 0

    for i in range(0, len(updates), 10):
        batch = updates[i:i+10]
        records = [{"id": rec_id, "fields": {ZONE_FIELD_ID: zone}} for rec_id, zone in batch]

        resp = requests.patch(url, headers=HEADERS, json={"records": records})
        if resp.status_code == 200:
            updated += len(batch)
            if updated % 100 == 0 or updated == len(updates):
                print(f"  Updated {updated}/{len(updates)}")
        else:
            failed += len(batch)
            print(f"  FAILED batch {i//10+1}: {resp.status_code} - {resp.text[:200]}")

        time.sleep(0.25)

    return updated, failed


def main():
    print("=" * 60)
    print("Shipment 구간유형 자동 분류 (주소 기반)")
    print("=" * 60)

    print("\n[1/3] Shipment 조회...")
    shipments = fetch_all_shipments()
    print(f"  대상: {len(shipments)}건")

    if not shipments:
        print("  대상 없음.")
        return

    print("\n[2/3] 주소 분석...")
    zone_counts = Counter()
    updates = []
    unclassified = []

    for rec in shipments:
        fields = rec["fields"]
        # rollup 필드는 값이 문자열 또는 리스트일 수 있음
        addr_raw = fields.get("수령인(주소)", "")
        if isinstance(addr_raw, list):
            addr = addr_raw[0] if addr_raw else ""
        else:
            addr = str(addr_raw)

        zone = classify_address(addr)
        if zone:
            updates.append((rec["id"], zone))
            zone_counts[zone] += 1
        else:
            unclassified.append((rec["id"], str(addr)[:30] if addr else "EMPTY"))
            zone_counts["판별불가"] += 1

    print("  분류 결과:")
    for z in ["수도권", "지방(광역시)", "지방(기타)", "도서산간", "판별불가"]:
        print(f"    {z}: {zone_counts.get(z, 0)}건")

    if unclassified and len(unclassified) <= 20:
        print(f"\n  판별불가 샘플:")
        for _, addr in unclassified[:10]:
            print(f"    \"{addr}\"")

    print(f"\n[3/3] 구간유형 업데이트 ({len(updates)}건)...")
    updated, failed = update_zones(updates)

    print(f"\n{'=' * 60}")
    print(f"완료: 업데이트 {updated}건 / 실패 {failed}건 / 판별불가 {zone_counts.get('판별불가', 0)}건")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
