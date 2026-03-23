"""
delivery_routing.py
────────────────────────────────────────────
신시어리 기사님별 배송 경로 km 집계
Kakao Mobility Direction API 기반

환경변수:
  KAKAO_REST_API_KEY    카카오 REST API 키
  AIRTABLE_API_KEY      Airtable PAT  (weekly 실행 시)
  AIRTABLE_API_KEY_TMS  Airtable PAT  (monthly 실행 시, fallback)
  AIRTABLE_BASE_ID / AIRTABLE_BASE_TMS_ID   TMS base ID
"""

import os
import re
import time
import math
import requests
import pyairtable
from collections import defaultdict
from datetime import date, timedelta

# ── 환경변수 ──────────────────────────────────────────
KAKAO_API_KEY = os.environ.get("KAKAO_REST_API_KEY", "")
# 주간/월간 리포트 모두 지원 (env 이름 다름)
_AT_API_KEY   = (
    os.environ.get("AIRTABLE_API_KEY") or
    os.environ.get("AIRTABLE_API_KEY_TMS") or ""
)
_AT_BASE_ID   = (
    os.environ.get("AIRTABLE_BASE_ID") or
    os.environ.get("AIRTABLE_BASE_TMS_ID") or
    "app4x70a8mOrIKsMf"
)
TABLE_SHIPMENT = "tbllg1JoHclGYer7m"

# ── 상수 ──────────────────────────────────────────────
SINCERELY_DRIVERS = [
    "신시어리 (이장훈)",
    "신시어리 (조희선)",
    "신시어리 (박종성)",
]

# 출발지 주소
ORIGIN_ADDRESS  = "서울시 성동구 성수동1가 13-209 에이원지식산업센터"
DAYOUNG_ADDRESS = "경기도 성남시 중원구 둔촌대로 555 선일 테크노피아"

# 박종성 기사님의 출발지를 다영기획으로 변경할 때 사용
DAYOUNG_DRIVER = "신시어리 (박종성)"

# 왕복 거리 포함 여부
INCLUDE_RETURN_TRIP = False

# 슬롯 분류
SLOT_MORNING   = "오전"
SLOT_AFTERNOON = "오후"
SLOT_FLEXIBLE  = "무관"

# 좌표 캐시 (모듈 레벨)
_ORIGIN_COORDS:  tuple | None = None
_DAYOUNG_COORDS: tuple | None = None
_geocode_cache:  dict = {}

# Field ID 상수
F_DATE      = "fldQvmEwwzvQW95h9"
F_PARTNER   = "fldHZ7yMT3KEu2gSj"
F_SLOT      = "fldcSrlxCngYQHtSV"
F_ADDRESS   = "fldyJHUh9gN44Ggnh"
F_WISH_TIME = "fldFweNu3dASPv93N"
F_STATUS    = "fldOhibgxg6LIpRTi"
F_TOTAL_CBM = "fldJ9DHjwoRyeUEqE"
F_DEPARTURE = "fldGZyp4KJNCSWWUr"

_TIME_RE = re.compile(r"(\d{1,2})[:\s시](\d{0,2})")


# ── 카카오 API 헬퍼 ────────────────────────────────────

def _kakao_headers() -> dict:
    return {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}


def geocode_kakao(address: str) -> tuple[float, float] | None:
    """주소 → (위도 lat, 경도 lng). 실패 시 None."""
    if not address or not KAKAO_API_KEY:
        return None
    try:
        resp = requests.get(
            "https://dapi.kakao.com/v2/local/search/address.json",
            headers=_kakao_headers(),
            params={"query": address.strip(), "analyze_type": "similar"},
            timeout=5,
        )
        resp.raise_for_status()
        docs = resp.json().get("documents", [])
        if docs:
            return float(docs[0]["y"]), float(docs[0]["x"])  # (lat, lng)

        # fallback: 키워드 검색
        resp2 = requests.get(
            "https://dapi.kakao.com/v2/local/search/keyword.json",
            headers=_kakao_headers(),
            params={"query": address.strip(), "size": 1},
            timeout=5,
        )
        resp2.raise_for_status()
        docs2 = resp2.json().get("documents", [])
        if docs2:
            return float(docs2[0]["y"]), float(docs2[0]["x"])

    except Exception as e:
        print(f"  [geocode 실패] {address[:40]} — {e}")
    return None


def route_distance_kakao(coords: list[tuple[float, float]]) -> float:
    """
    경유지 포함 총 주행거리 (카카오 모빌리티 다중경유 API).
    coords: [(lat, lng), ...] 출발지 포함 순서대로
    반환: km, 실패 시 Haversine fallback
    """
    if len(coords) < 2 or not KAKAO_API_KEY:
        return _haversine_total(coords)

    origin = coords[0]
    dest   = coords[-1]
    waypoints = coords[1:-1]

    try:
        params = {
            "origin":      f"{origin[1]},{origin[0]}",
            "destination": f"{dest[1]},{dest[0]}",
            "priority":    "RECOMMEND",
            "car_fuel":    "GASOLINE",
            "car_hipass":  "false",
            "alternatives":"false",
            "road_details":"false",
        }
        for i, wp in enumerate(waypoints[:3], 1):
            params[f"waypoint{i}"] = f"{wp[1]},{wp[0]}"

        resp = requests.get(
            "https://apis-navi.kakaomobility.com/v1/directions",
            headers=_kakao_headers(),
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        routes = resp.json().get("routes", [])
        if routes and routes[0].get("result_code") == 0:
            return round(routes[0]["summary"]["distance"] / 1000, 2)

    except Exception as e:
        print(f"  [route API 실패] {e} → 직선거리 fallback")

    return _haversine_total(coords)


def _haversine(lat1, lng1, lat2, lng2) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat/2)**2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlng/2)**2)
    return round(R * 2 * math.asin(math.sqrt(a)), 2)


def _haversine_total(coords: list[tuple[float, float]]) -> float:
    total = 0.0
    for i in range(len(coords) - 1):
        total += _haversine(*coords[i], *coords[i+1])
    return round(total, 2)


# ── 파싱 헬퍼 ─────────────────────────────────────────

def _parse_time_minutes(time_str: str | None) -> int:
    if not time_str:
        return 999
    m = _TIME_RE.search(str(time_str))
    if m:
        h  = int(m.group(1))
        mn = int(m.group(2)) if m.group(2) else 0
        if "오후" in str(time_str) and h < 12:
            h += 12
        return h * 60 + mn
    return 999


def _parse_slot(slot_val) -> str:
    if isinstance(slot_val, dict):
        return slot_val.get("name", SLOT_FLEXIBLE)
    if isinstance(slot_val, list) and slot_val:
        first = slot_val[0]
        return first.get("name", SLOT_FLEXIBLE) if isinstance(first, dict) else str(first)
    return str(slot_val) if slot_val else SLOT_FLEXIBLE


def _parse_address(addr_val) -> str:
    if isinstance(addr_val, list):
        return addr_val[0] if addr_val else ""
    return str(addr_val) if addr_val else ""


def _parse_departure(dep_val) -> str:
    if isinstance(dep_val, list):
        return dep_val[0] if dep_val else ""
    return str(dep_val) if dep_val else ""


def _parse_wish_time(wt_val) -> str:
    if isinstance(wt_val, list):
        return wt_val[0] if wt_val else ""
    return str(wt_val) if wt_val else ""


def _is_dayoung_departure(departure_str: str) -> bool:
    return "다영기획" in departure_str


def _parse_partner(field_val) -> str | None:
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


# ── geocode with cache ─────────────────────────────────

def _get_coords(address: str) -> tuple[float, float] | None:
    if address not in _geocode_cache:
        time.sleep(0.05)
        _geocode_cache[address] = geocode_kakao(address)
    return _geocode_cache.get(address)


# ── 슬롯별 배송 순서 결정 ──────────────────────────────

def build_route_order(deliveries: list[dict]) -> list[dict]:
    """오전 → 무관 → 오후 순서로 정렬, 슬롯 내 희망시간 오름차순."""
    morning   = [d for d in deliveries if d["slot"] == SLOT_MORNING]
    afternoon = [d for d in deliveries if d["slot"] == SLOT_AFTERNOON]
    flexible  = [d for d in deliveries if d["slot"] == SLOT_FLEXIBLE]
    morning.sort(key=lambda d: _parse_time_minutes(d["wish_time"]))
    afternoon.sort(key=lambda d: _parse_time_minutes(d["wish_time"]))
    return morning + flexible + afternoon


# ── 일간 라우팅 거리 계산 ──────────────────────────────

def calc_daily_route(deliveries: list[dict], origin_coords: tuple) -> dict:
    ordered = build_route_order(deliveries)

    route_stops  = []
    unresolved   = 0
    coords_chain = [origin_coords]

    for d in ordered:
        coords = _get_coords(d["address"])
        if coords:
            route_stops.append({
                "address":   d["address"][:40],
                "slot":      d["slot"],
                "wish_time": d["wish_time"],
                "coords":    coords,
                "cbm":       d.get("cbm", 0),
            })
            coords_chain.append(coords)
        else:
            unresolved += 1
            print(f"  [주소 변환 실패] {d['address'][:40]}")

    if len(coords_chain) < 2:
        return {"total_km": 0.0, "return_km": 0.0, "route": route_stops,
                "stops": 0, "unresolved": unresolved}

    if INCLUDE_RETURN_TRIP:
        coords_chain.append(origin_coords)

    total_km = route_distance_kakao(coords_chain)

    for i, stop in enumerate(route_stops):
        stop["leg_km"] = _haversine(*coords_chain[i], *coords_chain[i+1])

    return_km = 0.0
    if not INCLUDE_RETURN_TRIP and route_stops:
        return_km = _haversine(*route_stops[-1]["coords"], *origin_coords)

    return {
        "total_km":   total_km,
        "return_km":  return_km,
        "route":      route_stops,
        "stops":      len(route_stops),
        "unresolved": unresolved,
    }


# ── Airtable 조회 ─────────────────────────────────────

def fetch_routing_records(start: date, end: date) -> list[dict]:
    """해당 기간 신시어리 기사 배송 건 fetch → 전처리된 dict 리스트 반환."""
    api   = pyairtable.Api(_AT_API_KEY)
    table = api.table(_AT_BASE_ID, TABLE_SHIPMENT)
    formula = (
        f"AND("
        f"IS_AFTER({{출하확정일}}, DATEADD('{start.isoformat()}', -1, 'days')), "
        f"IS_BEFORE({{출하확정일}}, DATEADD('{end.isoformat()}',  1, 'days'))"
        f")"
    )
    all_recs = table.all(formula=formula)

    result = []
    for rec in all_recs:
        f      = rec["fields"]
        pname  = _parse_partner(f.get("배송파트너 (from 배송파트너)"))
        if not pname or pname not in SINCERELY_DRIVERS:
            continue
        addr = _parse_address(f.get("수령인(주소)") or f.get(F_ADDRESS))
        if not addr:
            continue
        departure = _parse_departure(f.get("출하장소명") or f.get(F_DEPARTURE))
        result.append({
            "date":       f.get("출하확정일", ""),
            "partner":    pname,
            "slot":       _parse_slot(f.get("배송슬롯") or f.get(F_SLOT)),
            "address":    addr,
            "wish_time":  _parse_wish_time(f.get("고객 희망 수령 시간") or f.get(F_WISH_TIME)),
            "cbm":        f.get(F_TOTAL_CBM) or 0,
            "departure":  departure,
            "is_dayoung": _is_dayoung_departure(departure),
        })

    print(f"  [routing] fetch: {len(result)}건 (전체 {len(all_recs)}건 중 신시어리)")
    return result


# ── 전체 집계 ─────────────────────────────────────────

def calc_driver_routing(records: list[dict]) -> dict:
    """
    fetch_routing_records() 결과를 받아 기사님별 일간/주간 km 집계.
    반환:
      driver_weekly_km:    {기사명: 주간 총 km}
      driver_daily_routes: {기사명: {날짜: {total_km, return_km, stops, route, ...}}}
    """
    global _ORIGIN_COORDS, _DAYOUNG_COORDS

    if _ORIGIN_COORDS is None:
        _ORIGIN_COORDS = geocode_kakao(ORIGIN_ADDRESS) or (37.5443, 127.0557)
        print(f"  [출발지] 에이원 {_ORIGIN_COORDS}")

    if _DAYOUNG_COORDS is None:
        _DAYOUNG_COORDS = geocode_kakao(DAYOUNG_ADDRESS) or _ORIGIN_COORDS
        print(f"  [출발지] 다영기획 {_DAYOUNG_COORDS}")

    grouped: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for rec in records:
        grouped[rec["partner"]][rec["date"]].append(rec)

    driver_daily_routes: dict[str, dict] = {}
    driver_weekly_km:    dict[str, float] = {}

    for driver in SINCERELY_DRIVERS:
        driver_daily_routes[driver] = {}
        driver_weekly_km[driver]    = 0.0

        for day_str in sorted(grouped.get(driver, {}).keys()):
            deliveries = grouped[driver][day_str]
            is_dayoung_day = (
                driver == DAYOUNG_DRIVER
                and any(d.get("is_dayoung") for d in deliveries)
            )
            origin       = _DAYOUNG_COORDS if is_dayoung_day else _ORIGIN_COORDS
            origin_label = "다영기획" if is_dayoung_day else "에이원"

            print(f"  [{driver.replace('신시어리 ','')}] {day_str} - {len(deliveries)}건 출발: {origin_label}")

            result = calc_daily_route(deliveries, origin)
            result["origin_label"] = origin_label
            result["is_dayoung"]   = is_dayoung_day

            driver_daily_routes[driver][day_str] = result
            driver_weekly_km[driver] = round(driver_weekly_km[driver] + result["total_km"], 2)

            print(f"    → {result['total_km']}km ({result['stops']}건 / 미해결 {result['unresolved']}건)")

    return {
        "driver_weekly_km":    driver_weekly_km,
        "driver_daily_routes": driver_daily_routes,
    }


# ── 출력 / 직렬화 ──────────────────────────────────────

def format_routing_log(routing_result: dict) -> str:
    lines = ["", "=== 기사님 배송 라우팅 요약 ==="]
    for driver in SINCERELY_DRIVERS:
        weekly_km = routing_result["driver_weekly_km"].get(driver, 0)
        lines.append(f"\n{driver.replace('신시어리 ','')}  주간 {weekly_km}km")
        daily = routing_result["driver_daily_routes"].get(driver, {})
        for day_str, result in sorted(daily.items()):
            d  = date.fromisoformat(day_str)
            wd = ["월","화","수","목","금","토","일"][d.weekday()]
            stops = " → ".join(
                f"[{s['slot']}]{s['address'][:15]}"
                for s in result.get("route", [])
            ) or "(경로 없음)"
            lines.append(
                f"  {day_str[5:]}({wd})  {result['total_km']}km  "
                f"{result['stops']}건  {stops}"
            )
    return "\n".join(lines)


def routing_to_json(routing_result: dict) -> dict:
    """coords tuple 제거, JSON 직렬화 가능 형태로 변환."""
    result = {
        "driver_weekly_km":    routing_result["driver_weekly_km"],
        "driver_daily_routes": {},
    }
    for driver, daily in routing_result["driver_daily_routes"].items():
        result["driver_daily_routes"][driver] = {}
        for day_str, data in daily.items():
            result["driver_daily_routes"][driver][day_str] = {
                "total_km":    round(float(data.get("total_km", 0)), 2),
                "return_km":   round(float(data.get("return_km", 0)), 2),
                "stops":       int(data.get("stops", 0)),
                "unresolved":  int(data.get("unresolved", 0)),
                "origin_label":str(data.get("origin_label", "")),
                "route": [
                    {
                        "address":   s.get("address", ""),
                        "slot":      s.get("slot", ""),
                        "wish_time": s.get("wish_time", ""),
                        "leg_km":    round(float(s.get("leg_km", 0)), 2),
                        "cbm":       round(float(s.get("cbm", 0)), 4),
                    }
                    for s in data.get("route", [])
                ],
            }
    return result
