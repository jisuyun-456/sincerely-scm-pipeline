# ================================================================
# 기사님별 배송 라우팅 거리 계산
# ================================================================
# [구조]
# 1. fetch_routing_records()  - 배송슬롯 + 수령인주소 + 희망시간 조회
# 2. build_route_order()      - 오전/오후/무관 그룹 분리 + 희망시간 정렬
# 3. geocode_kakao()          - 주소 -> 좌표 변환 (카카오 로컬 API)
# 4. route_distance_kakao()   - 경유지 포함 총 거리 계산 (카카오 모빌리티)
# 5. calc_driver_routing()    - 기사님별 일간/주간 km 집계
#
# [GitHub Secrets]
# KAKAO_REST_API_KEY  : 카카오 REST API 키
# ================================================================

import os
import re
import time
import requests
from collections import defaultdict
from datetime import date, timedelta

# ----------------------------------------------------------------
# 설정값
# ----------------------------------------------------------------
KAKAO_API_KEY = os.environ.get("KAKAO_REST_API_KEY", "")

# 출발지 (에이원지식산업센터)
ORIGIN_ADDRESS = "서울시 성동구 성수동1가 13-209 에이원지식산업센터"
ORIGIN_COORDS  = None  # 최초 1회 geocode 후 캐시

# 다영기획 (협력사 출발지) - 박종성 기사님 출하장소가 다영기획일 때 출발지 변경
DAYOUNG_ADDRESS = "경기도 성남시 중원구 둔촌대로 555"
DAYOUNG_ORIGIN_COORDS = None  # 최초 1회 geocode 후 캐시

# 다영기획 출발지 적용 기사님
DAYOUNG_DRIVER = "신시어리 (박종성)"

# 왕복 포함 여부 (True: 에이원 복귀 거리 포함)
INCLUDE_RETURN_TRIP = False

# 슬롯 분류
SLOT_MORNING   = "오전"
SLOT_AFTERNOON = "오후"
SLOT_FLEXIBLE  = "무관"

# 기사님 목록
SINCERELY_DRIVERS = [
    "신시어리 (이장훈)",
    "신시어리 (조희선)",
    "신시어리 (박종성)",
]

# Field ID 상수
F_DATE        = "fldQvmEwwzvQW95h9"
F_PARTNER     = "fldHZ7yMT3KEu2gSj"
F_SLOT        = "fldcSrlxCngYQHtSV"
F_ADDRESS     = "fldyJHUh9gN44Ggnh"
F_WISH_TIME   = "fldFweNu3dASPv93N"
F_STATUS      = "fldOhibgxg6LIpRTi"
F_TOTAL_CBM   = "fldJ9DHjwoRyeUEqE"
F_DEPARTURE   = "fldGZyp4KJNCSWWUr"


# ----------------------------------------------------------------
# 1. 카카오 API 유틸
# ----------------------------------------------------------------
def _kakao_headers() -> dict:
    return {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}


def geocode_kakao(address: str) -> tuple[float, float] | None:
    """주소 -> (위도, 경도) 변환"""
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
            d = docs[0]
            return float(d["y"]), float(d["x"])  # (lat, lng)
    except Exception as e:
        print(f"  [geocode 실패] {address[:30]}... : {e}")
    return None


def route_distance_kakao(coords: list[tuple[float, float]]) -> float:
    """
    경유지 포함 총 주행거리 계산 (카카오 모빌리티 다중경유 API)
    coords: [(lat, lng), ...] - 출발지 포함, 순서대로
    반환: 총 거리 (km), 실패시 직선거리 fallback
    """
    if len(coords) < 2 or not KAKAO_API_KEY:
        return 0.0

    origin    = coords[0]
    dest      = coords[-1]
    waypoints = coords[1:-1]

    try:
        params = {
            "origin":       f"{origin[1]},{origin[0]}",
            "destination":  f"{dest[1]},{dest[0]}",
            "priority":     "RECOMMEND",
            "car_fuel":     "GASOLINE",
            "car_hipass":   "false",
            "alternatives": "false",
            "road_details": "false",
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
        data = resp.json()
        routes = data.get("routes", [])
        if routes and routes[0].get("result_code") == 0:
            return round(routes[0]["summary"]["distance"] / 1000, 2)
    except Exception as e:
        print(f"  [route API 실패] {e} -> 직선거리 fallback 사용")

    return _haversine_total(coords)


def _haversine(lat1, lng1, lat2, lng2) -> float:
    import math
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1))
         * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return round(R * 2 * math.asin(math.sqrt(a)), 2)


def _haversine_total(coords: list[tuple[float, float]]) -> float:
    total = 0.0
    for i in range(len(coords) - 1):
        total += _haversine(*coords[i], *coords[i + 1])
    return round(total, 2)


# ----------------------------------------------------------------
# 2. 슬롯 / 시간 파싱
# ----------------------------------------------------------------
_TIME_RE = re.compile(r"(\d{1,2})[:\s시](\d{0,2})")

def _parse_time_minutes(time_str: str | None) -> int:
    if not time_str:
        return 999
    m = _TIME_RE.search(str(time_str))
    if m:
        h = int(m.group(1))
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


def _parse_departure(departure_val) -> str:
    if isinstance(departure_val, list):
        return departure_val[0] if departure_val else ""
    return str(departure_val) if departure_val else ""


def _is_dayoung_departure(departure_str: str) -> bool:
    return "다영기획" in departure_str


def _parse_address(addr_val) -> str:
    if isinstance(addr_val, list):
        return addr_val[0] if addr_val else ""
    return str(addr_val) if addr_val else ""


def _parse_wish_time(wt_val) -> str:
    if isinstance(wt_val, list):
        return wt_val[0] if wt_val else ""
    return str(wt_val) if wt_val else ""


# ----------------------------------------------------------------
# 3. Airtable 라우팅용 레코드 조회
# ----------------------------------------------------------------
def fetch_routing_records(start: date, end: date) -> list[dict]:
    """배송슬롯 + 수령인주소 + 희망시간 + 배송파트너 + 출하장소명 조회"""
    import pyairtable
    from sincerely_weekly_report_v2 import API_KEY, BASE_ID, TABLE_SHIPMENT

    api   = pyairtable.Api(API_KEY)
    table = api.table(BASE_ID, TABLE_SHIPMENT)
    formula = (
        f"AND("
        f"IS_AFTER({{출하확정일}}, DATEADD('{start.isoformat()}', -1, 'days')), "
        f"IS_BEFORE({{출하확정일}}, DATEADD('{end.isoformat()}',  1, 'days'))"
        f")"
    )
    all_recs = table.all(formula=formula)

    result = []
    for rec in all_recs:
        f = rec["fields"]
        partner_raw = f.get("배송파트너 (from 배송파트너)")
        pname = None
        if isinstance(partner_raw, dict):
            for vals in partner_raw.get("valuesByLinkedRecordId", {}).values():
                if vals:
                    pname = vals[0]
                    break
        elif isinstance(partner_raw, list) and partner_raw:
            pname = str(partner_raw[0])

        if pname and pname in SINCERELY_DRIVERS:
            addr = _parse_address(f.get("수령인(주소)") or f.get(F_ADDRESS))
            if addr:
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
    return result


# ----------------------------------------------------------------
# 4. 슬롯별 정렬 + 라우팅 순서 결정
# ----------------------------------------------------------------
def build_route_order(deliveries: list[dict]) -> list[dict]:
    """오전 → 무관 → 오후, 슬롯 내 희망시간 빠른 순"""
    morning   = [d for d in deliveries if d["slot"] == SLOT_MORNING]
    afternoon = [d for d in deliveries if d["slot"] == SLOT_AFTERNOON]
    flexible  = [d for d in deliveries if d["slot"] == SLOT_FLEXIBLE]
    morning.sort(key=lambda d: _parse_time_minutes(d["wish_time"]))
    afternoon.sort(key=lambda d: _parse_time_minutes(d["wish_time"]))
    return morning + flexible + afternoon


# ----------------------------------------------------------------
# 5. 일간 라우팅 거리 계산
# ----------------------------------------------------------------
_geocode_cache: dict[str, tuple[float, float] | None] = {}

def _get_coords(address: str) -> tuple[float, float] | None:
    if address not in _geocode_cache:
        time.sleep(0.05)
        _geocode_cache[address] = geocode_kakao(address)
    return _geocode_cache.get(address)


def calc_daily_route(deliveries: list[dict], origin_coords) -> dict:
    ordered      = build_route_order(deliveries)
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
                "cbm":       d["cbm"],
            })
            coords_chain.append(coords)
        else:
            unresolved += 1
            print(f"  [주소 변환 실패] {d['address'][:40]}")

    if len(coords_chain) < 2:
        return {"total_km": 0, "return_km": 0, "route": route_stops,
                "stops": 0, "unresolved": unresolved}

    if INCLUDE_RETURN_TRIP:
        coords_chain.append(origin_coords)

    total_km = route_distance_kakao(coords_chain)

    for i, stop in enumerate(route_stops):
        stop["leg_km"] = _haversine(*coords_chain[i], *coords_chain[i + 1])

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


# ----------------------------------------------------------------
# 6. 전체 집계
# ----------------------------------------------------------------
def calc_driver_routing(records: list[dict]) -> dict:
    global ORIGIN_COORDS, DAYOUNG_ORIGIN_COORDS

    if ORIGIN_COORDS is None:
        ORIGIN_COORDS = geocode_kakao(ORIGIN_ADDRESS)
        if ORIGIN_COORDS:
            print(f"  [출발지] 에이원 {ORIGIN_COORDS}")
        else:
            print("  [경고] 에이원 좌표 변환 실패 - fallback 사용")
            ORIGIN_COORDS = (37.5443, 127.0557)

    if DAYOUNG_ORIGIN_COORDS is None:
        DAYOUNG_ORIGIN_COORDS = geocode_kakao(DAYOUNG_ADDRESS)
        if DAYOUNG_ORIGIN_COORDS:
            print(f"  [출발지] 다영기획 {DAYOUNG_ORIGIN_COORDS}")
        else:
            print("  [경고] 다영기획 좌표 변환 실패 - 에이원 좌표로 대체")
            DAYOUNG_ORIGIN_COORDS = ORIGIN_COORDS

    grouped: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for rec in records:
        grouped[rec["partner"]][rec["date"]].append(rec)

    driver_daily_routes: dict[str, dict] = {}
    driver_weekly_km:    dict[str, float] = {}

    for driver in SINCERELY_DRIVERS:
        driver_daily_routes[driver] = {}
        driver_weekly_km[driver]    = 0.0

        for day_str in sorted(grouped.get(driver, {}).keys()):
            deliveries     = grouped[driver][day_str]
            is_dayoung_day = (driver == DAYOUNG_DRIVER
                              and any(d.get("is_dayoung") for d in deliveries))
            origin         = DAYOUNG_ORIGIN_COORDS if is_dayoung_day else ORIGIN_COORDS
            origin_label   = "다영기획" if is_dayoung_day else "에이원"

            print(f"  [{driver.replace('신시어리 ', '')}] {day_str} - {len(deliveries)}건 출발지: {origin_label}")

            result = calc_daily_route(deliveries, origin)
            result["origin_label"] = origin_label
            result["is_dayoung"]   = is_dayoung_day
            driver_daily_routes[driver][day_str] = result
            driver_weekly_km[driver] = round(driver_weekly_km[driver] + result["total_km"], 2)
            print(f"    -> 총 {result['total_km']}km ({result['stops']}건 / 미해결 {result['unresolved']}건)")

    return {
        "driver_daily_routes": driver_daily_routes,
        "driver_weekly_km":    driver_weekly_km,
        "origin_coords":       ORIGIN_COORDS,
        "dayoung_coords":      DAYOUNG_ORIGIN_COORDS,
    }


# ----------------------------------------------------------------
# 7. 유틸 함수
# ----------------------------------------------------------------
def enrich_with_routing(analysis_result: dict, routing_result: dict) -> dict:
    analysis_result["driver_daily_routes"] = routing_result["driver_daily_routes"]
    analysis_result["driver_weekly_km"]    = routing_result["driver_weekly_km"]
    return analysis_result


def format_routing_log(routing_result: dict) -> str:
    lines = ["", "=== 기사님 배송 라우팅 요약 ==="]
    for driver in SINCERELY_DRIVERS:
        weekly_km = routing_result["driver_weekly_km"].get(driver, 0)
        lines.append(f"\n{driver.replace('신시어리 ', '')}  주간 {weekly_km}km")
        for day_str, result in sorted(routing_result["driver_daily_routes"].get(driver, {}).items()):
            d  = date.fromisoformat(day_str)
            wd = ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]
            route_str = " -> ".join(f"[{s['slot']}]{s['address'][:15]}" for s in result["route"]) or "(경로 없음)"
            lines.append(f"  {day_str[5:]}({wd})  {result['total_km']}km  {result['stops']}건  {route_str}")
    return "\n".join(lines)


def routing_to_json(routing_result: dict) -> dict:
    result = {"driver_weekly_km": routing_result["driver_weekly_km"], "driver_daily_routes": {}}
    for driver, daily in routing_result["driver_daily_routes"].items():
        result["driver_daily_routes"][driver] = {}
        for day_str, data in daily.items():
            result["driver_daily_routes"][driver][day_str] = {
                "total_km":   data["total_km"],
                "return_km":  data["return_km"],
                "stops":      data["stops"],
                "unresolved": data["unresolved"],
                "route": [{"address": s["address"], "slot": s["slot"],
                           "wish_time": s["wish_time"], "leg_km": s.get("leg_km", 0),
                           "cbm": s.get("cbm", 0)} for s in data["route"]],
            }
    return result
