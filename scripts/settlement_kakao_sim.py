"""
박종성 기사님 운임 시뮬레이션: Haversine×1.35 vs 카카오 실도로 거리

Usage:
  python scripts/settlement_kakao_sim.py
  python scripts/settlement_kakao_sim.py --date 2026-05-11    # 특정 날짜
  python scripts/settlement_kakao_sim.py --week 2026-05-11    # 주간 (Mon~Sun)
  python scripts/settlement_kakao_sim.py --weeks 8            # 최근 N주

환경변수:
  AIRTABLE_PAT           Airtable REST API 키
  KAKAO_REST_API_KEY     카카오 REST API 키
"""
from __future__ import annotations

import argparse
import math
import os
import re
import time
from datetime import date, timedelta

import requests

# ── 상수 ─────────────────────────────────────────────────────────────────────

TMS_BASE       = "app4x70a8mOrIKsMf"
SHIPMENT_TABLE = "tbllg1JoHclGYer7m"
DRIVER_PARK    = "recXCfwVTqaoeQ9SS"

F_SC_ID     = "fldBUwhBlhOMsJZdv"
F_DATE      = "fldQvmEwwzvQW95h9"
F_PARTNER   = "fldM2u6RwLRrO7ymW"
F_FARE      = "fldRT95SC88KSBATT"
F_DEST_ADDR = "fldyJHUh9gN44Ggnh"
F_ORIGIN_ADDR = "fldb24I9EQ2KPXv6S"

# 에이원지식산업센터 (lng, lat) — 카카오 API는 경도 먼저
AEWON_LNG, AEWON_LAT = 127.0446, 37.5477
DAYOUNG_LNG, DAYOUNG_LAT = 127.1436, 37.4360

# 운임 공식 파라미터
PARK_BASE   = 55_421
PARK_KM     = 831
ROAD_FACTOR = 1.35   # haversine → 도로거리 환산 (현재)


def round_up_500(x: float) -> int:
    return math.ceil(x / 500) * 500


# ── Airtable ─────────────────────────────────────────────────────────────────

def _at_headers(pat: str) -> dict:
    return {"Authorization": f"Bearer {pat}", "Content-Type": "application/json"}


def _str_field(raw: object) -> str:
    if isinstance(raw, list):
        return str(raw[0] or "").strip() if raw else ""
    return str(raw or "").strip()


def fetch_park_records(pat: str, start: str, end: str) -> list[dict]:
    """박종성 기사님 SC 레코드 조회."""
    end_excl = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    formula = (
        f"AND("
        f"{{{F_DATE}}}>='{start}',"
        f"{{{F_DATE}}}<'{end_excl}',"
        f"NOT({{{F_PARTNER}}}='')"
        f")"
    )
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{SHIPMENT_TABLE}"
    params: dict = {
        "filterByFormula": formula,
        "fields[]": [F_SC_ID, F_DATE, F_PARTNER, F_FARE, F_DEST_ADDR, F_ORIGIN_ADDR],
        "returnFieldsByFieldId": "true",
        "pageSize": 100,
    }
    records, offset = [], None
    while True:
        if offset:
            params["offset"] = offset
        resp = requests.get(url, headers=_at_headers(pat), params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        for rec in data.get("records", []):
            partners = rec["fields"].get(F_PARTNER) or []
            if DRIVER_PARK in partners:
                records.append(rec)
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.25)
    return records


# ── Haversine ─────────────────────────────────────────────────────────────────

def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * R * math.asin(math.sqrt(a)), 2)


# ── 카카오 API ────────────────────────────────────────────────────────────────

_geocode_cache: dict[str, dict | None] = {}


def _kakao_headers(key: str) -> dict:
    return {"Authorization": f"KakaoAK {key}"}


def geocode_kakao(address: str, key: str) -> dict | None:
    """주소 → {x: lng, y: lat} 또는 None."""
    if not address:
        return None
    if address in _geocode_cache:
        return _geocode_cache[address]

    xy = None
    for endpoint, param_key in [
        ("https://dapi.kakao.com/v2/local/search/address.json", "query"),
        ("https://dapi.kakao.com/v2/local/search/keyword.json", "query"),
    ]:
        try:
            resp = requests.get(
                endpoint,
                headers=_kakao_headers(key),
                params={param_key: address.strip(), "size": 1},
                timeout=5,
            )
            resp.raise_for_status()
            docs = resp.json().get("documents", [])
            if docs:
                d = docs[0]
                xy = {"x": float(d["x"]), "y": float(d["y"])}
                break
        except Exception as e:
            print(f"  [geocode 실패] {address[:40]}: {e}")
        time.sleep(0.05)

    _geocode_cache[address] = xy
    return xy


def road_km_kakao(origin_lng: float, origin_lat: float,
                   dest_lng: float, dest_lat: float, key: str) -> float | None:
    """카카오 길찾기 API → 실도로 거리(km). 실패 시 None."""
    try:
        params = {
            "origin":      f"{origin_lng},{origin_lat}",
            "destination": f"{dest_lng},{dest_lat}",
            "priority":    "RECOMMEND",
            "car_fuel":    "GASOLINE",
            "car_hipass":  "false",
            "alternatives": "false",
            "road_details": "false",
        }
        resp = requests.get(
            "https://apis-navi.kakaomobility.com/v1/directions",
            headers=_kakao_headers(key),
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        routes = data.get("routes", [])
        if routes and routes[0].get("result_code", -1) == 0:
            return round(routes[0]["summary"]["distance"] / 1000, 2)
        # API result_code != 0
        rc = routes[0].get("result_code", "?") if routes else "no routes"
        print(f"  [카카오 길찾기 result_code={rc}]")
    except Exception as e:
        print(f"  [카카오 길찾기 실패] {e}")
    return None


# ── 주소 → 출발지 결정 ────────────────────────────────────────────────────────

def _origin_xy(origin_addr: str) -> tuple[float, float]:
    if "성남시" in origin_addr or "다영" in origin_addr:
        return DAYOUNG_LNG, DAYOUNG_LAT
    return AEWON_LNG, AEWON_LAT


# ── 시뮬레이션 메인 ────────────────────────────────────────────────────────────

def simulate(records: list[dict], kakao_key: str) -> list[dict]:
    rows = []
    for i, rec in enumerate(records, 1):
        f = rec["fields"]
        sc_id       = _str_field(f.get(F_SC_ID))
        d           = f.get(F_DATE, "")
        dest_addr   = _str_field(f.get(F_DEST_ADDR))
        origin_addr = _str_field(f.get(F_ORIGIN_ADDR))
        fare_manual = f.get(F_FARE) or 0

        print(f"[{i:02d}/{len(records)}] {sc_id}  {d}  {dest_addr[:40]}")

        origin_lng, origin_lat = _origin_xy(origin_addr)

        # ── (A) Haversine × 1.35 ─────────────────────────────────────────────
        dest_xy = geocode_kakao(dest_addr, kakao_key)   # 카카오 좌표 (지오코딩은 공통)
        if dest_xy:
            dest_lat_v, dest_lng_v = dest_xy["y"], dest_xy["x"]
            hav = haversine_km(origin_lat, origin_lng, dest_lat_v, dest_lng_v)
        else:
            # 카카오 지오코딩 실패 → 좌표 없음
            hav = None

        hav_road    = round(hav * ROAD_FACTOR, 2) if hav is not None else None
        fare_hav    = round_up_500(PARK_BASE + PARK_KM * hav_road) if hav_road is not None else None

        # ── (B) 카카오 실도로 거리 ─────────────────────────────────────────────
        kakao_km = None
        if dest_xy:
            time.sleep(0.15)  # rate limit
            kakao_km = road_km_kakao(origin_lng, origin_lat,
                                     dest_xy["x"], dest_xy["y"], kakao_key)

        fare_kakao = round_up_500(PARK_BASE + PARK_KM * kakao_km) if kakao_km is not None else None

        rows.append({
            "sc_id":       sc_id,
            "date":        d,
            "dest":        dest_addr[:35],
            "fare_manual": fare_manual,
            "hav_km":      hav_road,
            "fare_hav":    fare_hav,
            "kakao_km":    kakao_km,
            "fare_kakao":  fare_kakao,
        })

        # 결과 요약
        parts = []
        if hav_road:
            parts.append(f"haversine×1.35={hav_road:.1f}km → ₩{fare_hav:,}")
        if kakao_km:
            parts.append(f"kakao={kakao_km:.1f}km → ₩{fare_kakao:,}")
        if fare_manual:
            parts.append(f"manual=₩{fare_manual:,}")
        print("  " + " | ".join(parts))

    return rows


def _diff_pct(a, b) -> str:
    if a is None or b is None or b == 0:
        return "  N/A"
    return f"{(a - b) / b * 100:+.1f}%"


def print_report(rows: list[dict]) -> None:
    print("\n" + "=" * 110)
    print(f"{'SC ID':<14} {'날짜':<12} {'목적지':<36} {'수동':>9} {'Hav×1.35km':>11} {'Hav운임':>9} {'Kakao km':>9} {'Kakao운임':>10} {'Hav-수동':>9} {'Kakao-수동':>10}")
    print("-" * 110)

    hav_diffs, kakao_diffs = [], []
    for r in rows:
        fm = r["fare_manual"]
        fh = r["fare_hav"]
        fk = r["fare_kakao"]

        hav_d   = _diff_pct(fh, fm) if fm else "  N/A"
        kakao_d = _diff_pct(fk, fm) if fm else "  N/A"

        print(
            f"{r['sc_id']:<14} {r['date']:<12} {r['dest']:<36} "
            f"{fm:>9,} "
            f"{(r['hav_km'] or 0):>11.1f} "
            f"{(fh or 0):>9,} "
            f"{(r['kakao_km'] or 0):>9.1f} "
            f"{(fk or 0):>10,} "
            f"{hav_d:>9} {kakao_d:>10}"
        )
        if fm and fh:
            hav_diffs.append((fh - fm) / fm * 100)
        if fm and fk:
            kakao_diffs.append((fk - fm) / fm * 100)

    print("=" * 110)

    # 통계 요약
    def stats(diffs: list[float], label: str) -> None:
        if not diffs:
            print(f"  {label}: 데이터 없음")
            return
        avg = sum(diffs) / len(diffs)
        rms = math.sqrt(sum(d ** 2 for d in diffs) / len(diffs))
        mn, mx = min(diffs), max(diffs)
        print(f"  {label:20s}  avg={avg:+.1f}%  RMSE={rms:.1f}%  min={mn:+.1f}%  max={mx:+.1f}%  N={len(diffs)}")

    print("\n[정확도 요약 vs 수동 운임]")
    stats(hav_diffs,   "Haversine×1.35  ")
    stats(kakao_diffs, "카카오 실도로    ")

    # 개선 여부
    if hav_diffs and kakao_diffs:
        hav_rms   = math.sqrt(sum(d ** 2 for d in hav_diffs)   / len(hav_diffs))
        kakao_rms = math.sqrt(sum(d ** 2 for d in kakao_diffs) / len(kakao_diffs))
        improvement = (hav_rms - kakao_rms) / hav_rms * 100
        print(f"\n  카카오 전환 시 RMSE {improvement:+.1f}% {'개선' if improvement > 0 else '악화'}")

    # km 비교
    km_pairs = [(r["hav_km"], r["kakao_km"]) for r in rows if r["hav_km"] and r["kakao_km"]]
    if km_pairs:
        ratios = [k / h for h, k in km_pairs]
        avg_ratio = sum(ratios) / len(ratios)
        print(f"\n  카카오 실도로 / Haversine×1.35 평균 비율: {avg_ratio:.3f}x  (1.0 = 동일)")


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="박종성 운임 시뮬레이션: Haversine vs 카카오")
    grp = p.add_mutually_exclusive_group()
    grp.add_argument("--date",  help="특정 날짜 YYYY-MM-DD")
    grp.add_argument("--week",  help="주 시작일 YYYY-MM-DD (월요일)")
    grp.add_argument("--weeks", type=int, help="최근 N주")
    grp.add_argument("--since", help="시작일 YYYY-MM-DD (현재까지, 예: 2024-01-01)")
    return p.parse_args()


def main() -> None:
    pat       = os.environ.get("AIRTABLE_PAT", "")
    kakao_key = os.environ.get("KAKAO_REST_API_KEY", "")

    if not pat:
        print("ERROR: AIRTABLE_PAT 환경변수 필요")
        return
    if not kakao_key:
        print("ERROR: KAKAO_REST_API_KEY 환경변수 필요")
        return

    args = _parse_args()
    today = date.today()

    if args.date:
        start = end = args.date
    elif args.week:
        s = date.fromisoformat(args.week)
        start, end = s.isoformat(), (s + timedelta(days=6)).isoformat()
    elif args.since:
        start = args.since
        end   = today.isoformat()
    elif args.weeks:
        end   = today.isoformat()
        start = (today - timedelta(weeks=args.weeks)).isoformat()
    else:
        # 기본: 최근 4주
        end   = today.isoformat()
        start = (today - timedelta(weeks=4)).isoformat()

    print(f"\n박종성 운임 시뮬레이션: {start} ~ {end}")
    print(f"카카오 API: {'설정됨' if kakao_key else '없음'}\n")

    print("1. Airtable 레코드 조회 중...")
    records = fetch_park_records(pat, start, end)
    if not records:
        print("  → 해당 기간 박종성 기사님 레코드 없음")
        return
    print(f"  → {len(records)}건 조회 완료\n")

    print("2. 거리/운임 계산 중...\n")
    rows = simulate(records, kakao_key)

    print_report(rows)


if __name__ == "__main__":
    main()
