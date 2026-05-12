"""
박종성 기사님 운임 교차검증 스크립트
목적: 기존 Airtable 운송비용 데이터 + 추정 거리 역산 → km당 단가 + 기본운임 확정

실행: py harness/settlement/crossvalidation.py
의존: requests (pip install requests)  — Airtable 조회용
거리 계산: 한국 행정구역 좌표 하드코딩 → haversine (API 불필요, 즉시 실행)
"""

import os
import re
import json
import time
import math
import statistics
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ─── Config ─────────────────────────────────────────────────────────────────
AIRTABLE_PAT = os.environ.get("AIRTABLE_PAT", "")
TMS_BASE = "app4x70a8mOrIKsMf"
SHIPMENT_TABLE = "tbllg1JoHclGYer7m"
DRIVER_REC = "recXCfwVTqaoeQ9SS"  # 신시어리 박종성

CACHE_PATH = Path(__file__).parent / "state" / "crossval_cache.json"

# Known origin coords
ORIGINS = {
    "에이원지식산업센터": {"lat": 37.5477, "lng": 127.0446},
    "다영기획": {"lat": 37.4360, "lng": 127.1436},
}

# ─── Korean district coordinate table ────────────────────────────────────────
# Covers Seoul 구, Gyeonggi 시/군, major cities
# Source: approximate centroid coordinates per administrative district
KR_COORDS: dict[str, tuple[float, float]] = {
    # Seoul 구
    "강남구": (37.5172, 127.0473), "강동구": (37.5301, 127.1237),
    "강북구": (37.6396, 127.0256), "강서구": (37.5510, 126.8496),
    "관악구": (37.4784, 126.9516), "광진구": (37.5384, 127.0823),
    "구로구": (37.4954, 126.8874), "금천구": (37.4569, 126.8955),
    "노원구": (37.6542, 127.0568), "도봉구": (37.6688, 127.0471),
    "동대문구": (37.5744, 127.0398), "동작구": (37.5124, 126.9393),
    "마포구": (37.5663, 126.9014), "서대문구": (37.5791, 126.9368),
    "서초구": (37.4837, 127.0324), "성동구": (37.5635, 127.0369),
    "성북구": (37.5894, 127.0167), "송파구": (37.5145, 127.1059),
    "양천구": (37.5169, 126.8664), "영등포구": (37.5264, 126.8962),
    "용산구": (37.5311, 126.9810), "은평구": (37.6026, 126.9291),
    "종로구": (37.5726, 126.9793), "중구": (37.5641, 126.9978),
    "중랑구": (37.6063, 127.0927),
    # Incheon
    "인천중구": (37.4739, 126.5987), "인천서구": (37.5451, 126.6759),
    "인천남동구": (37.4492, 126.7312), "인천연수구": (37.4104, 126.6779),
    "인천부평구": (37.5074, 126.7218), "인천강화군": (37.7472, 126.4877),
    "인천계양구": (37.5374, 126.7381),
    # Gyeonggi major cities/counties
    "성남시": (37.4200, 127.1268), "분당구": (37.3808, 127.1178),
    "수원시": (37.2636, 127.0286), "수원": (37.2636, 127.0286),
    "화성시": (37.1995, 126.8319),
    "평택시": (37.0073, 127.0712), "오산시": (37.1520, 127.0773),
    "용인시": (37.2411, 127.1775), "안양시": (37.3943, 126.9568),
    "군포시": (37.3616, 126.9352), "의왕시": (37.3449, 126.9683),
    "과천시": (37.4297, 126.9878), "광명시": (37.4784, 126.8647),
    "시흥시": (37.3800, 126.8031), "안산시": (37.3219, 126.8309),
    "부천시": (37.5034, 126.7660), "김포시": (37.6146, 126.7162),
    "고양시": (37.6564, 126.8350), "파주시": (37.7600, 126.7798),
    "의정부시": (37.7382, 127.0337), "양주시": (37.7851, 127.0457),
    "남양주시": (37.6359, 127.2164), "구리시": (37.5943, 127.1296),
    "하남시": (37.5393, 127.2147),
    # 경기도 광주 — '광주'만 있으면 광주광역시(전남)로 오인식되므로 긴 패턴 우선 등록
    "경기도 광주": (37.4295, 127.2561), "경기 광주": (37.4295, 127.2561),
    "광주시": (37.4295, 127.2561),
    "이천시": (37.2719, 127.4348), "여주시": (37.2982, 127.6373),
    "가평군": (37.8315, 127.5109), "양평군": (37.4916, 127.4878),
    "연천군": (38.0965, 127.0743), "동두천시": (37.9038, 127.0606),
    "포천시": (37.8946, 127.2001), "안성시": (37.0079, 127.2798),
    # 충청권
    "대전": (36.3504, 127.3845), "청주시": (36.6424, 127.4890),
    "충주시": (36.9910, 127.9259), "천안시": (36.8065, 127.1524),
    "아산시": (36.7898, 127.0022), "공주시": (36.4465, 127.1190),
    "논산시": (36.1868, 127.0985), "서산시": (36.7847, 126.4503),
    "당진시": (36.8925, 126.6297), "홍성군": (36.6010, 126.6611),
    "보령시": (36.3333, 126.6127),
    "세종시": (36.4801, 127.2889),
    # 전라권
    "전주시": (35.8242, 127.1479), "군산시": (35.9677, 126.7368),
    "익산시": (35.9483, 126.9574), "정읍시": (35.5699, 126.8561),
    "남원시": (35.4163, 127.3903), "김제시": (35.8037, 126.8802),
    "순천시": (34.9506, 127.4872), "여수시": (34.7604, 127.6622),
    "목포시": (34.8118, 126.3922), "광양시": (34.9404, 127.6965),
    "나주시": (35.0159, 126.7103),
    # 광주광역시 — 경기도 광주와 구분
    "광주": (35.1595, 126.8526),
    # 경상권
    "대구": (35.8714, 128.6014),
    "경산시": (35.8250, 128.7408), "구미시": (36.1196, 128.3444),
    "경주시": (35.8562, 129.2247), "안동시": (36.5684, 128.7295),
    "영천시": (35.9734, 128.9378), "상주시": (36.4107, 128.1591),
    "부산": (35.1796, 129.0756), "울산": (35.5384, 129.3114),
    "창원시": (35.2280, 128.6812), "진주시": (35.1799, 128.1076),
    "김해시": (35.2280, 128.8890), "거제시": (34.8800, 128.6211),
    "통영시": (34.8544, 128.4333), "사천시": (35.0030, 128.0643),
    "밀양시": (35.5036, 128.7460), "양산시": (35.3350, 129.0337),
    "포항시": (36.0190, 129.3435),
    # 강원권
    "춘천시": (37.8813, 127.7298), "원주시": (37.3422, 127.9202),
    "강릉시": (37.7519, 128.8761), "동해시": (37.5244, 129.1142),
    "속초시": (38.2070, 128.5918), "태백시": (37.1641, 128.9855),
    "삼척시": (37.4498, 129.1659), "홍천군": (37.6935, 127.8886),
    "횡성군": (37.4914, 127.9845), "양양군": (38.0758, 128.6188),
    "고성군": (38.3806, 128.4677), "인제군": (38.1706, 128.1706),
    "평창군": (37.3706, 128.3901), "정선군": (37.3793, 128.6602),
    "영월군": (37.1836, 128.4618), "화천군": (38.1059, 127.7082),
    "철원군": (38.1463, 127.3138), "양구군": (38.1109, 127.9894),
}

# Field IDs
F_SC_ID = "fldBUwhBlhOMsJZdv"
F_DATE = "fldQvmEwwzvQW95h9"
F_FARE = "fldRT95SC88KSBATT"
F_UNLOAD = "fldxmAZrBGqS7sQoL"
F_ORIGIN_ADDR = "fldb24I9EQ2KPXv6S"
F_DEST_ADDR = "fldyJHUh9gN44Ggnh"
F_BOX_TEXT = "fldTjLDmw5sNGszeD"
F_PARTNER = "fldM2u6RwLRrO7ymW"

# ─── Airtable fetch ──────────────────────────────────────────────────────────

def fetch_shipments() -> list[dict]:
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{SHIPMENT_TABLE}"
    headers = {"Authorization": f"Bearer {AIRTABLE_PAT}"}
    records = []
    cursor = None
    while True:
        params = {
            "filterByFormula": "AND(IS_AFTER({출하확정일},'2024-12-31'),{운송비용}>0)",
            "returnFieldsByFieldId": "true",
            "fields[]": [F_SC_ID, F_DATE, F_FARE, F_UNLOAD,
                         F_ORIGIN_ADDR, F_DEST_ADDR, F_BOX_TEXT, F_PARTNER],
            "pageSize": 100,
        }
        if cursor:
            params["offset"] = cursor
        r = requests.get(url, headers=headers, params=params, timeout=30)
        if not r.ok:
            print(f"  Airtable error {r.status_code}: {r.text[:200]}")
            break
        data = r.json()
        records.extend(data.get("records", []))
        print(f"  fetched {len(records)} records...", end="\r")
        cursor = data.get("offset")
        if not cursor:
            break
        time.sleep(0.2)
    print()
    return records


def get_field(rec: dict, fid: str):
    return rec.get("fields", {}).get(fid)


def _str_field(raw) -> str:
    if isinstance(raw, list):
        return str(raw[0] or "").strip() if raw else ""
    return str(raw or "").strip()


# ─── Box parsing ─────────────────────────────────────────────────────────────

def parse_unload_fee(box_text) -> int:
    if not box_text:
        return 0
    s = str(box_text)
    try:
        heavy = int(re.search(r"중대(\d+)", s).group(1)) if re.search(r"중대(\d+)", s) else 0
        large = int(re.search(r"(?<!중)대(\d+)", s).group(1)) if re.search(r"(?<!중)대(\d+)", s) else 0
        xlarge = int(re.search(r"특대(\d+)", s).group(1)) if re.search(r"특대(\d+)", s) else 0
        return min((heavy // 5) * 5000 + (large // 3) * 5000 + (xlarge // 3) * 5000, 50000)
    except Exception:
        return 0


# ─── Distance estimation ──────────────────────────────────────────────────────

def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dφ = math.radians(lat2 - lat1)
    dλ = math.radians(lng2 - lng1)
    a = math.sin(dφ / 2) ** 2 + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def estimate_dest_coord(addr: str):
    """
    Match Korean address string to district coordinates.
    긴 패턴을 우선 매칭해 경기도 광주 vs 광주광역시 등 중복 지명 오인식 방지.
    """
    if not addr:
        return None

    # 긴 패턴 우선 매칭
    for name in sorted(KR_COORDS, key=len, reverse=True):
        if name in addr:
            return KR_COORDS[name]

    # 행정구역 정규식 추출
    m = re.search(r"([가-힣]+(?:구|시|군))", addr)
    if m:
        district = m.group(1)
        if district in KR_COORDS:
            return KR_COORDS[district]

    # 광역시 단어 fallback — 광주는 경기 문맥 없을 때만 전남
    for city in ["인천", "대전", "대구", "부산", "울산", "세종"]:
        if city in addr:
            return KR_COORDS.get(city)
    if "광주" in addr:
        return KR_COORDS["광주"]

    return None


# ─── Linear regression helpers ───────────────────────────────────────────────

def linear_regression(xs: list[float], ys: list[float]):
    """Simple OLS. Returns (slope, intercept, r_squared)."""
    n = len(xs)
    if n < 2:
        return None, None, None
    mx = sum(xs) / n
    my = sum(ys) / n
    ss_xx = sum((x - mx) ** 2 for x in xs)
    ss_xy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = ss_xy / ss_xx if ss_xx else 0
    intercept = my - slope * mx
    y_pred = [slope * x + intercept for x in xs]
    ss_res = sum((y - yp) ** 2 for y, yp in zip(ys, y_pred))
    ss_tot = sum((y - my) ** 2 for y in ys)
    r2 = 1 - ss_res / ss_tot if ss_tot else 0
    return slope, intercept, r2


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not AIRTABLE_PAT:
        print("ERROR: AIRTABLE_PAT not set")
        return

    # 1. Fetch or load cached data
    if CACHE_PATH.exists():
        print(f"Loading cached data from {CACHE_PATH}")
        with open(CACHE_PATH, encoding="utf-8") as f:
            records = json.load(f)
    else:
        print("Fetching Shipments since 2025-01-01 with fare data...")
        all_records = fetch_shipments()
        records = [r for r in all_records if DRIVER_REC in (get_field(r, F_PARTNER) or [])]
        print(f"  Total: {len(all_records)}, 박종성: {len(records)}")
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        print(f"  Cached → {CACHE_PATH}")

    print(f"\n박종성 records: {len(records)}")

    # 2. Process all records
    results = []
    no_dest = no_coord = no_origin = 0

    for rec in records:
        fare = get_field(rec, F_FARE) or 0
        if not fare:
            continue

        sc_id = get_field(rec, F_SC_ID) or ""
        date = get_field(rec, F_DATE) or ""
        unload_recorded = get_field(rec, F_UNLOAD) or 0
        box_text = get_field(rec, F_BOX_TEXT) or ""
        origin_addr = _str_field(get_field(rec, F_ORIGIN_ADDR))
        dest_addr = _str_field(get_field(rec, F_DEST_ADDR))

        if not dest_addr:
            no_dest += 1
            continue

        # Match origin
        origin_info = None
        for name, info in ORIGINS.items():
            if info == ORIGINS["에이원지식산업센터"] and "성동구" in origin_addr:
                origin_info = info; break
            if info == ORIGINS["다영기획"] and ("성남시" in origin_addr or "다영" in origin_addr):
                origin_info = info; break
        if origin_info is None:
            if "성동구" in origin_addr:
                origin_info = ORIGINS["에이원지식산업센터"]
            elif "성남시" in origin_addr or "다영" in origin_addr:
                origin_info = ORIGINS["다영기획"]
            else:
                no_origin += 1
                continue

        dest_coord = estimate_dest_coord(dest_addr)
        if dest_coord is None:
            no_coord += 1
            continue

        dist_km = haversine_km(origin_info["lat"], origin_info["lng"],
                               dest_coord[0], dest_coord[1])
        # Road distance ≈ haversine × 1.35 (empirical Korea correction factor)
        road_km = dist_km * 1.35

        unload_calc = parse_unload_fee(box_text)
        results.append({
            "sc_id": sc_id, "date": date,
            "fare": fare, "unload_recorded": unload_recorded,
            "unload_calc": unload_calc,
            "haversine_km": round(dist_km, 1),
            "road_km": round(road_km, 1),
            "origin": origin_addr[:25],
            "dest": dest_addr[:40],
        })

    print(f"Processed: {len(results)} | skipped no-dest={no_dest} no-coord={no_coord} no-origin={no_origin}\n")

    if len(results) < 5:
        print("Not enough data for analysis.")
        return

    # 3. Analysis
    fares = [r["fare"] for r in results]
    dists = [r["road_km"] for r in results]
    implied = [r["fare"] / r["road_km"] for r in results if r["road_km"] > 0]

    print("=== FARE STATISTICS ===")
    sorted_f = sorted(fares)
    print(f"  Min={min(fares):,.0f}  Max={max(fares):,.0f}  Median={statistics.median(fares):,.0f}  Mean={statistics.mean(fares):,.0f}")

    print("\n=== DISTANCE STATISTICS (road_km = haversine × 1.35) ===")
    print(f"  Min={min(dists):.1f}  Max={max(dists):.1f}  Median={statistics.median(dists):.1f}  Mean={statistics.mean(dists):.1f}")

    print("\n=== FARE ZONES ===")
    buckets = [(0,50000),(50000,80000),(80000,130000),(130000,250000),(250000,9999999)]
    for lo, hi in buckets:
        sub = [r for r in results if lo < r["fare"] <= hi]
        if sub:
            d_avg = statistics.mean(r["road_km"] for r in sub)
            f_avg = statistics.mean(r["fare"] for r in sub)
            r_avg = statistics.mean(r["fare"] / r["road_km"] for r in sub if r["road_km"] > 0)
            lbl = "inf" if hi >= 9999999 else f"{hi//1000:,}K"
            print(f"  {lo//1000:>3}K-{lbl:<5}: {len(sub):3}  avg_dist={d_avg:5.1f}km  avg_fare={f_avg:>7,.0f}  avg_rate={r_avg:.0f}/km")

    # 4. Linear regression: fare = base + km_rate × road_km
    slope, intercept, r2 = linear_regression(dists, fares)
    if slope and r2:
        print(f"\n=== LINEAR REGRESSION: fare = {intercept:,.0f} + {slope:,.0f} × road_km  (R²={r2:.3f}) ===")
        if r2 < 0.5:
            print("  ⚠ Low R² — pricing is NOT purely linear. Consider zone-based model.")

    # 5. Separate Seoul-only vs out-of-Seoul
    seoul_recs = [r for r in results if any(g in r["dest"] for g in ["서울", "구"] if "구" in r["dest"])]
    gyeonggi_recs = [r for r in results if "경기" in r["dest"] or any(
        c in r["dest"] for c in ["성남", "수원", "용인", "화성", "남양주", "이천", "여주", "안산", "고양", "파주"]
    )]
    province_recs = [r for r in results if any(c in r["dest"] for c in ["충", "대전", "대구", "부산", "인천", "울산", "광주", "전", "경남", "경북"])]

    print("\n=== ZONE BREAKDOWN ===")
    for label, subset in [("서울권", seoul_recs), ("경기권", gyeonggi_recs), ("지방", province_recs)]:
        if subset:
            fv = [r["fare"] for r in subset]
            dv = [r["road_km"] for r in subset if r["road_km"] > 0]
            sl, ic, r2v = linear_regression(dv, [r["fare"] for r in subset if r["road_km"] > 0])
            med_f = statistics.median(fv)
            med_d = statistics.median(dv) if dv else 0
            print(f"  {label}: {len(subset)}건  median_fare={med_f:,.0f}  median_dist={med_d:.0f}km", end="")
            if sl and r2v:
                print(f"  → {ic:,.0f} + {sl:,.0f}×km  R²={r2v:.2f}", end="")
            print()

    # 6. Sample detail
    print("\n=== RECENT SAMPLES (latest 15) ===")
    print(f"{'SC ID':<12} {'Date':<11} {'Fare':>8} {'RoadKm':>7}  Dest")
    print("-" * 70)
    for r in sorted(results, key=lambda x: x["date"], reverse=True)[:15]:
        print(f"{r['sc_id']:<12} {r['date']:<11} {r['fare']:>8,.0f} {r['road_km']:>6.1f}km  {r['dest']}")

    # 7. Save report
    summary = {
        "total_analyzed": len(results),
        "fare_median": statistics.median(fares),
        "road_km_median": statistics.median(dists),
        "linear_base": round(intercept) if intercept else None,
        "linear_per_km": round(slope) if slope else None,
        "r_squared": round(r2, 3) if r2 else None,
    }
    report_path = Path(__file__).parent / "state" / "crossval_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "records": results}, f, ensure_ascii=False, indent=2)

    print(f"\n→ Report: {report_path}")
    if slope and intercept and r2:
        print(f"\n★ RESULT: fare ≈ {intercept:,.0f}원 (기본) + {slope:,.0f}원/km  (R²={r2:.3f})")
        print(f"  예시: 20km → {intercept + slope*20:,.0f}원  /  50km → {intercept + slope*50:,.0f}원  /  100km → {intercept + slope*100:,.0f}원")


if __name__ == "__main__":
    main()
