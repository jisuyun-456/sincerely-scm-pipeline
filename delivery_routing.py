"""
delivery_routing.py
────────────────────────────────────────────
신시어리 기사님별 배송 경로 km 집계
Kakao Mobility Direction API 기반

환경변수:
  KAKAO_REST_API_KEY   카카오 REST API 키
  AIRTABLE_API_KEY     Airtable PAT
  AIRTABLE_BASE_ID     TMS base ID (기본값: app4x70a8mOrIKsMf)
"""

import os
import time
from datetime import date
from collections import defaultdict

import requests
import pyairtable

KAKAO_KEY      = os.environ.get("KAKAO_REST_API_KEY", "")
API_KEY        = os.environ.get("AIRTABLE_API_KEY", "")
BASE_ID        = os.environ.get("AIRTABLE_BASE_ID", "app4x70a8mOrIKsMf")
TABLE_SHIPMENT = "tbllg1JoHclGYer7m"

SINCERELY_DRIVERS = [
    "신시어리 (이장훈)",
    "신시어리 (조희선)",
    "신시어리 (박종성)",
]

DEPOT_ADDRESSES = {
    "에이원센터": "서울시 성동구 성수동 1가 13-209 서울숲 에이원지식산업센터",
    "다영기획":   "경기도 성남시 중원구 둔촌대로 555 선일 테크노피아",
}

_GEOCODE_URL = "https://dapi.kakao.com/v2/local/search/address.json"
_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
_ROUTE_URL   = "https://apis-navi.kakaomobility.com/v1/waypoints/directions"

# 모듈 내 depot 좌표 캐시 (geocode 1회만 수행)
_depot_coords: dict = {}


# ── 내부 헬퍼 ──────────────────────────────────────────

def _kakao_headers() -> dict:
    return {"Authorization": f"KakaoAK {KAKAO_KEY}"}


def _geocode(address: str, cache: dict) -> dict | None:
    """주소 → {"x": float, "y": float}. 실패 시 None."""
    if address in cache:
        return cache[address]

    xy = None
    try:
        # 1차: 주소 검색
        resp = requests.get(
            _GEOCODE_URL,
            headers=_kakao_headers(),
            params={"query": address, "size": 1},
            timeout=5,
        )
        resp.raise_for_status()
        docs = resp.json().get("documents", [])
        if docs:
            xy = {"x": float(docs[0]["x"]), "y": float(docs[0]["y"])}

        # 2차: 키워드 검색 fallback
        if not xy:
            resp2 = requests.get(
                _KEYWORD_URL,
                headers=_kakao_headers(),
                params={"query": address, "size": 1},
                timeout=5,
            )
            resp2.raise_for_status()
            docs2 = resp2.json().get("documents", [])
            if docs2:
                xy = {"x": float(docs2[0]["x"]), "y": float(docs2[0]["y"])}

    except Exception as e:
        print(f"  [geocode 실패] {address[:40]} — {e}")

    if xy is None:
        print(f"  [geocode 없음] {address[:40]}")

    cache[address] = xy
    return xy


def _calc_route_km(
    origin_xy: dict,
    stop_xys: list[dict],
) -> tuple[float, list[float]]:
    """
    depot → stop1 → stop2 → ... 경로 km 계산.
    반환: (total_km, [leg_km, ...])
    실패 시: (0.0, [])
    """
    if not stop_xys or not KAKAO_KEY:
        return 0.0, []

    destination = stop_xys[-1]
    waypoints   = [
        {"name": f"경유{i + 1}", "x": s["x"], "y": s["y"]}
        for i, s in enumerate(stop_xys[:-1])
    ]

    body: dict = {
        "origin":      {"x": origin_xy["x"], "y": origin_xy["y"]},
        "destination": {"x": destination["x"], "y": destination["y"]},
    }
    if waypoints:
        body["waypoints"] = waypoints

    try:
        resp = requests.post(
            _ROUTE_URL,
            headers={**_kakao_headers(), "Content-Type": "application/json"},
            json=body,
            timeout=15,
        )
        resp.raise_for_status()
        data   = resp.json()
        routes = data.get("routes", [])
        if not routes:
            return 0.0, []

        route = routes[0]
        if route.get("result_code", -1) != 0:
            print(
                f"  [route 오류] code={route.get('result_code')} "
                f"msg={route.get('result_msg', '')}"
            )
            return 0.0, []

        sections = route.get("sections", [])
        leg_km   = [round(sec.get("distance", 0) / 1000, 2) for sec in sections]
        return round(sum(leg_km), 2), leg_km

    except Exception as e:
        print(f"  [route API 실패] {e}")
        return 0.0, []


def _parse_partner(field_val) -> str | None:
    """배송파트너 lookup 필드 (dict/list/str) → 파트너명."""
    if not field_val:
        return None
    if isinstance(field_val, dict):
        names = []
        for vals in field_val.get("valuesByLinkedRecordId", {}).values():
            names.extend(vals)
        return names[0] if names else None
    if isinstance(field_val, list):
        return str(field_val[0]) if field_val else None
    return str(field_val)


# ── 공개 함수 ──────────────────────────────────────────

def fetch_routing_records(start: date, end: date) -> list[dict]:
    """해당 기간 신시어리 기사 배송 건만 fetch."""
    api   = pyairtable.Api(API_KEY)
    table = api.table(BASE_ID, TABLE_SHIPMENT)
    formula = (
        f"AND("
        f"IS_AFTER({{출하확정일}}, DATEADD('{start.isoformat()}', -1, 'days')), "
        f"IS_BEFORE({{출하확정일}}, DATEADD('{end.isoformat()}',  1, 'days'))"
        f")"
    )
    all_recs = table.all(formula=formula)

    result = [
        rec for rec in all_recs
        if _parse_partner(rec["fields"].get("배송파트너 (from 배송파트너)"))
        in SINCERELY_DRIVERS
    ]
    print(f"  [routing] fetch: {len(result)}건 (전체 {len(all_recs)}건 중 신시어리)")
    return result


def calc_driver_routing(records: list[dict]) -> dict:
    """
    기사×날짜 그룹 → Kakao API로 km 계산.

    반환:
      driver_weekly_km:    {기사명: 주간 총 km}
      driver_daily_routes: {기사명: {날짜: {total_km, stops, depot, route:[...]}}}
    """
    # 기사×날짜 그룹핑
    groups: dict = defaultdict(lambda: defaultdict(list))
    for rec in records:
        f     = rec["fields"]
        d_s   = f.get("출하확정일", "")
        pname = _parse_partner(f.get("배송파트너 (from 배송파트너)"))
        if d_s and pname in SINCERELY_DRIVERS:
            groups[pname][d_s].append(f)

    geocache: dict = {}

    # depot 좌표 사전 geocode
    for depot_name, depot_addr in DEPOT_ADDRESSES.items():
        xy = _geocode(depot_addr, geocache)
        _depot_coords[depot_name] = xy
        status = f"({xy['x']:.4f}, {xy['y']:.4f})" if xy else "실패"
        print(f"  [depot] {depot_name}: {status}")

    driver_weekly_km:    dict = defaultdict(float)
    driver_daily_routes: dict = defaultdict(dict)

    for driver in SINCERELY_DRIVERS:
        daily = groups.get(driver, {})
        for d_str in sorted(daily.keys()):
            recs_day = daily[d_str]

            # depot 결정 (첫 레코드 출하장소 기준)
            depot_key = (recs_day[0].get("출하장소") or "에이원센터").strip()
            if depot_key not in DEPOT_ADDRESSES:
                depot_key = "에이원센터"

            origin_xy = _depot_coords.get(depot_key)
            if not origin_xy:
                print(f"  [건너뜀] {driver} {d_str} — depot 좌표 없음 ({depot_key})")
                driver_daily_routes[driver][d_str] = {
                    "total_km": 0.0, "stops": len(recs_day),
                    "depot": depot_key, "route": [],
                }
                continue

            # 배송지 주소 geocode
            addresses = [
                (f.get("수령인(주소)") or "").strip()
                for f in recs_day
            ]
            addresses = [a for a in addresses if a]

            stop_xys: list[dict]   = []
            valid_addrs: list[str] = []
            for addr in addresses:
                time.sleep(0.05)
                xy = _geocode(addr, geocache)
                if xy:
                    stop_xys.append(xy)
                    valid_addrs.append(addr)
                else:
                    print(f"  [주소 건너뜀] {addr[:35]}")

            if not stop_xys:
                driver_daily_routes[driver][d_str] = {
                    "total_km": 0.0, "stops": 0,
                    "depot": depot_key, "route": [],
                }
                continue

            time.sleep(0.1)
            total_km, leg_kms = _calc_route_km(origin_xy, stop_xys)

            route = [
                {
                    "address": addr,
                    "slot":    i + 1,
                    "leg_km":  leg_kms[i] if i < len(leg_kms) else 0.0,
                }
                for i, addr in enumerate(valid_addrs)
            ]

            driver_daily_routes[driver][d_str] = {
                "total_km": total_km,
                "stops":    len(stop_xys),
                "depot":    depot_key,
                "route":    route,
            }
            driver_weekly_km[driver] = round(
                driver_weekly_km[driver] + total_km, 2
            )
            name = driver.replace("신시어리 ", "")
            print(f"  [routing] {name} {d_str}: {total_km}km / {len(stop_xys)}정류장")

    return {
        "driver_weekly_km":    dict(driver_weekly_km),
        "driver_daily_routes": {k: dict(v) for k, v in driver_daily_routes.items()},
    }


def routing_to_json(result: dict) -> dict:
    """JSON 직렬화 가능 형태로 변환 (float/int 타입 보장)."""
    weekly = {k: round(float(v), 2) for k, v in result.get("driver_weekly_km", {}).items()}
    daily: dict = {}
    for driver, days in result.get("driver_daily_routes", {}).items():
        daily[driver] = {}
        for d_str, info in days.items():
            daily[driver][d_str] = {
                "total_km": round(float(info.get("total_km", 0)), 2),
                "stops":    int(info.get("stops", 0)),
                "depot":    str(info.get("depot", "")),
                "route": [
                    {
                        "address": str(r.get("address", "")),
                        "slot":    int(r.get("slot", 0)),
                        "leg_km":  round(float(r.get("leg_km", 0)), 2),
                    }
                    for r in info.get("route", [])
                ],
            }
    return {
        "driver_weekly_km":    weekly,
        "driver_daily_routes": daily,
    }


def format_routing_log(result: dict) -> str:
    """기사별 주간 km 요약 문자열 반환."""
    lines  = ["  [기사님 배송 거리 요약]"]
    weekly = result.get("driver_weekly_km", {})
    daily  = result.get("driver_daily_routes", {})

    for driver in SINCERELY_DRIVERS:
        name  = driver.replace("신시어리 ", "")
        total = weekly.get(driver, 0.0)
        days  = daily.get(driver, {})
        lines.append(f"    {name}: 주간 총 {total}km ({len(days)}일 배차)")
        for d_str, info in sorted(days.items()):
            lines.append(
                f"      {d_str}: {info['total_km']}km "
                f"/ {info['stops']}정류장 (출발: {info['depot']})"
            )
    return "\n".join(lines)
