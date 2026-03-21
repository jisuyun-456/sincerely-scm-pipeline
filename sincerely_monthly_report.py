"""
Sincerely SCM 월간 출하 리포트
─────────────────────────────────────────────
매월 1일 09:00 KST GitHub Actions 자동 실행
결과는 GitHub Pages (JSON 아카이브)로 조회

포함 지표:
  [CBM]     월 총 CBM / 주차별 CBM 추이
  [배차]    월 총 배차 건수 / 배송파트너별 배송 비율
  [손익]    월 물류매출 / 운송비용 / 물류 손익
  [품목]    월 출하 품목 Top 10
  [기사님]  기사님별 월간 처리 CBM / 배송 거리 km

환경변수:
  AIRTABLE_API_KEY_TMS   Airtable PAT
  AIRTABLE_BASE_TMS_ID   TMS base (app4x70a8mOrIKsMf)
  KAKAO_REST_API_KEY     카카오 REST API 키 (라우팅 km 계산)
"""

import os
import json
import re
import time
import random
from datetime import datetime, timedelta, date
from collections import defaultdict

import pyairtable

# ── 환경변수 ──────────────────────────────────────────
API_KEY = os.environ["AIRTABLE_API_KEY_TMS"]
BASE_ID = os.environ.get("AIRTABLE_BASE_TMS_ID", "app4x70a8mOrIKsMf")

# ── Table ID ──────────────────────────────────────────
TABLE_SHIPMENT = "tbllg1JoHclGYer7m"
TABLE_BOX      = "tbltwH7bHk41rTzhM"
TABLE_PRODUCT  = "tblBNh6oGDlTKGrdQ"

# ── Field ID ──────────────────────────────────────────
F_DATE       = "fldQvmEwwzvQW95h9"   # 출하확정일
F_ITEM       = "fldgSupj5XLjJXYQo"   # 최종 출하 품목
F_BOX_PARSED = "fldTjLDmw5sNGszeD"   # 최종 외박스 수량 값
F_BOX_MANUAL = "fldRjMaXa5TdSsGDL"   # 외박스 수량 직접입력
F_TOTAL_CBM  = "fldJ9DHjwoRyeUEqE"   # Total_CBM
F_STATUS     = "fldOhibgxg6LIpRTi"   # 발송상태_TMS
F_REVENUE    = "fldOFuvqBT0iXItcT"   # 물류매출
F_COST       = "fldRT95SC88KSBATT"   # 운송비용
F_PARTNER    = "fldHZ7yMT3KEu2gSj"   # 배송파트너

# ── 박스 CBM fallback ─────────────────────────────────
BOX_CBM = {
    "극소": 0.0098, "S280": 0.0098,
    "소":   0.0117, "S360": 0.0117,
    "중":   0.0201, "M350": 0.0201,
    "중대": 0.0492, "M480": 0.0492,
    "대":   0.1066, "L510": 0.1066,
    "특대": 0.1663, "L560": 0.1663,
}

# ── 파트너 그룹 정규화 ────────────────────────────────
PARTNER_GROUP = {
    "신시어리 (이장훈)":  "신시어리 기사님 (이장훈)",
    "신시어리 (박종성)":  "신시어리 기사님 (박종성)",
    "신시어리 (조희선)":  "신시어리 기사님 (조희선)",
    "신시어리 (로젠)":    "로젠 택배",
    "고객":               "고객 직접수령",
}

# ── 기사님 차량 CBM 용량 ───────────────────────────────
VEHICLE_CBM = {
    "신시어리 (이장훈)": 5.4,   # 스타리아 카고
    "신시어리 (조희선)": 7.6,   # 1톤 트럭
    "신시어리 (박종성)": 9.5,   # 1.4톤 트럭
}
A1_WAREHOUSE_CBM = 44.4   # 에이원센터 총 창고 CBM

_BOX_RE = re.compile(
    r"(극소|소|중대|중|대|특대|S280|S360|M350|M480|L510|L560)\s*(\d+)"
)


# ═══════════════════════════════════════════════════════
# 1. 날짜 유틸
# ═══════════════════════════════════════════════════════
def prev_month_range() -> tuple[date, date]:
    """전월 1일 ~ 말일"""
    today     = date.today()
    first_day = today.replace(day=1)
    last_day  = first_day - timedelta(days=1)
    start     = last_day.replace(day=1)
    return start, last_day


def month_label(d: date) -> str:
    return f"{d.year}년 {d.month}월"


def week_number_of_month(d: date) -> int:
    return (d.day - 1) // 7 + 1


# ═══════════════════════════════════════════════════════
# 2. Airtable 조회
# ═══════════════════════════════════════════════════════
def fetch_month_shipments(start: date, end: date) -> list[dict]:
    api   = pyairtable.Api(API_KEY)
    table = api.table(BASE_ID, TABLE_SHIPMENT)
    formula = (
        f"AND("
        f"IS_AFTER({{출하확정일}}, DATEADD('{start.isoformat()}', -1, 'days')), "
        f"IS_BEFORE({{출하확정일}}, DATEADD('{end.isoformat()}',  1, 'days'))"
        f")"
    )
    return table.all(formula=formula)


def fetch_box_cbm_live() -> dict:
    api   = pyairtable.Api(API_KEY)
    table = api.table(BASE_ID, TABLE_BOX)
    live  = {}
    for rec in table.all():
        f = rec["fields"]
        for key in (f.get("Box Code"), f.get("박스")):
            if key:
                live[key] = f.get("cbm", 0)
    return live


def fetch_product_cbm() -> list[tuple[str, float]]:
    api   = pyairtable.Api(API_KEY)
    table = api.table(BASE_ID, TABLE_PRODUCT)
    result = []
    for rec in table.all():
        f    = rec["fields"]
        name = (
            f.get("fldx01uKEnCd0J0nP") or
            f.get("Name") or
            f.get("품목명") or ""
        ).strip()
        cbm = (
            f.get("fldN1JrkxIr5m6pXz") or
            f.get("fld6W5ImO7UeBVMPI") or
            f.get("박스당 CBM") or None
        )
        if name and cbm:
            try:
                norm = re.sub(r"\s+", "", name)
                result.append((norm, float(cbm)))
            except (ValueError, TypeError):
                pass
    result.sort(key=lambda x: -len(x[0]))
    print(f"  Product CBM 조회 완료: {len(result)}개 품목")
    return result


# ═══════════════════════════════════════════════════════
# 3. CBM 파싱
# ═══════════════════════════════════════════════════════
def parse_box_cbm(box_str: str, live: dict) -> float:
    ref   = {**BOX_CBM, **live}
    total = 0.0
    for m in _BOX_RE.finditer(box_str):
        btype, cnt = m.group(1), int(m.group(2))
        total += ref.get(btype, 0) * cnt
    return round(total, 4)


def match_cbm_from_product(item_str: str, product_cbm: list[tuple[str, float]]) -> float:
    total = 0.0
    matched_any = False
    for line in item_str.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        norm_line = re.sub(r"\s+", "", line)
        nums = re.findall(r"\d+", norm_line)
        for prod_norm, cbm_per_box in product_cbm:
            if prod_norm in norm_line:
                qty = int(nums[-1]) if nums else 1
                total += cbm_per_box * qty
                matched_any = True
                break
    return round(total, 4) if matched_any else 0.0


def get_cbm(f: dict, live: dict,
            product_cbm: list[tuple[str, float]] | None = None) -> float:
    total_cbm_f = f.get("Total_CBM")
    if total_cbm_f and total_cbm_f > 0:
        return total_cbm_f

    box_qty = f.get("최종 외박스 수량 값") or f.get("외박스 수량 (직접입력)") or ""
    if isinstance(box_qty, list):
        box_qty = ", ".join(str(x) for x in box_qty)
    box_qty = box_qty.strip()

    item_str = f.get("최종 출하 품목") or f.get("최종 출고 품목 및 수량") or ""

    if item_str.strip() and product_cbm:
        cv = match_cbm_from_product(item_str, product_cbm)
        if cv > 0:
            return cv

    if box_qty and _BOX_RE.search(box_qty):
        return parse_box_cbm(box_qty, live)

    return 0.0


# ═══════════════════════════════════════════════════════
# 4. 월간 분석
# ═══════════════════════════════════════════════════════
def analyze_month(records: list[dict], live_cbm: dict,
                  product_cbm: list[tuple[str, float]] | None = None) -> dict:
    total_cbm   = 0.0
    total_count = 0
    total_rev   = 0.0
    total_cost  = 0.0

    weekly_cbm: dict[int, float]  = defaultdict(float)
    weekly_cnt: dict[int, int]    = defaultdict(int)
    partner_cnt: dict[str, int]   = defaultdict(int)
    partner_cbm: dict[str, float] = defaultdict(float)
    item_agg: dict = defaultdict(lambda: {"qty": 0, "cbm": 0.0})

    for rec in records:
        f   = rec["fields"]
        d_s = f.get("출하확정일")
        if not d_s:
            continue

        ship_date = date.fromisoformat(d_s)
        week_no   = week_number_of_month(ship_date)
        cbm_val   = get_cbm(f, live_cbm, product_cbm)

        total_count += 1
        total_cbm   += cbm_val
        total_rev   += f.get("물류매출") or 0
        total_cost  += f.get("운송비용") or 0

        weekly_cbm[week_no] += cbm_val
        weekly_cnt[week_no] += 1

        # 배송파트너 파싱 (lookup 필드)
        partner_field = f.get("배송파트너 (from 배송파트너)")
        if partner_field:
            if isinstance(partner_field, dict):
                names = []
                for vals in partner_field.get("valuesByLinkedRecordId", {}).values():
                    names.extend(vals)
            elif isinstance(partner_field, list):
                names = [str(p) for p in partner_field]
            else:
                names = [str(partner_field)]

            for raw_name in names:
                display = PARTNER_GROUP.get(raw_name, raw_name)
                partner_cnt[display] += 1
                partner_cbm[display] += cbm_val

        # 품목 집계
        item_str = f.get("최종 출하 품목") or ""
        for line in item_str.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            nums  = re.findall(r"\d+", line)
            iname = re.sub(r"\s*\d+\s*$", "", line).strip()
            if iname and nums:
                qty = int(nums[-1])
                item_agg[iname]["qty"] += qty
                if product_cbm:
                    norm_line = re.sub(r"\s+", "", iname)
                    for prod_norm, cpb in product_cbm:
                        if prod_norm in norm_line:
                            item_agg[iname]["cbm"] += round(cpb * qty, 4)
                            break

    total_cbm  = round(total_cbm, 2)
    total_rev  = round(total_rev, 0)
    total_cost = round(total_cost, 0)

    partner_pct = {
        p: round(cnt / total_count * 100, 1) if total_count else 0
        for p, cnt in partner_cnt.items()
    }

    top_items = sorted(
        [{"name": k, "qty": v["qty"], "cbm": round(v["cbm"], 3)}
         for k, v in item_agg.items() if v["cbm"] > 0],
        key=lambda x: -x["cbm"],
    )[:10]

    # 기사님별 월간 CBM (raw 파트너명 → 표시명 역매핑으로 partner_cbm 조회)
    driver_cbm = {}
    for raw_key in VEHICLE_CBM:
        display_key = PARTNER_GROUP.get(raw_key, raw_key)
        driver_cbm[raw_key] = round(partner_cbm.get(display_key, 0.0), 2)

    return {
        "total_cbm":    total_cbm,
        "total_count":  total_count,
        "total_rev":    total_rev,
        "total_cost":   total_cost,
        "profit":       total_rev - total_cost,
        "cbm_per_ship": round(total_cbm / total_count, 3) if total_count else 0,
        "weekly_cbm":   dict(weekly_cbm),
        "weekly_cnt":   dict(weekly_cnt),
        "partner_cnt":  dict(partner_cnt),
        "partner_pct":  partner_pct,
        "partner_cbm":  dict(partner_cbm),
        "top_items":    top_items,
        "driver_cbm":   driver_cbm,
    }


# ═══════════════════════════════════════════════════════
# 5. 라우팅 주간 km 분해
# ═══════════════════════════════════════════════════════
def _calc_weekly_km_breakdown(
    driver_daily_routes: dict,
    month_start: date,
    month_end:   date,
) -> dict:
    """
    driver_daily_routes[기사][날짜]["total_km"] 을
    월요일 기준 주간 단위로 묶어 합산.

    반환 예:
    {
        "신시어리 (이장훈)": {"3/2주": 45.2, "3/9주": 52.1, ...},
        ...
    }
    """
    result = {}
    for driver, daily in driver_daily_routes.items():
        weekly: dict = defaultdict(float)
        for day_str, route_data in daily.items():
            try:
                d   = date.fromisoformat(day_str)
                mon = d - timedelta(days=d.weekday())
                wk_label = f"{mon.month}/{mon.day}주"
                km = route_data.get("total_km", 0)
                weekly[wk_label] = round(weekly[wk_label] + km, 2)
            except Exception:
                pass
        result[driver] = dict(sorted(weekly.items()))
    return result


# ═══════════════════════════════════════════════════════
# 6. 메인
# ═══════════════════════════════════════════════════════
def main():
    skip = os.environ.get("SKIP_DELAY", "0")
    if skip != "1":
        delay = random.randint(0, 29 * 60)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {delay//60}분 {delay%60}초 후 실행")
        time.sleep(delay)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 월간 리포트 생성 시작")

    start, end = prev_month_range()
    print(f"  대상 기간: {start} ~ {end}  ({month_label(start)})")

    live_cbm    = fetch_box_cbm_live()
    product_cbm = fetch_product_cbm()
    records     = fetch_month_shipments(start, end)
    print(f"  조회 건수: {len(records)}건")

    data = analyze_month(records, live_cbm, product_cbm)

    # 월간 기사님 배송 라우팅 km 계산
    print("  [라우팅] 월간 기사님 배송 거리 계산 중...")
    routing_monthly: dict = {}

    try:
        from delivery_routing import (
            fetch_routing_records,
            calc_driver_routing,
            routing_to_json,
            format_routing_log,
            SINCERELY_DRIVERS,
        )

        routing_recs   = fetch_routing_records(start, end)
        routing_result = calc_driver_routing(routing_recs)
        print(format_routing_log(routing_result))

        weekly_km_by_driver = _calc_weekly_km_breakdown(
            routing_result["driver_daily_routes"], start, end
        )

        routing_monthly = {
            "driver_monthly_km":          routing_result["driver_weekly_km"],
            "driver_weekly_km_breakdown": weekly_km_by_driver,
            "driver_daily_routes":        routing_to_json(routing_result)["driver_daily_routes"],
        }

        print("\n  [기사님별 월간 총 km]")
        for driver in SINCERELY_DRIVERS:
            monthly_km = routing_result["driver_weekly_km"].get(driver, 0)
            weekly_bk  = weekly_km_by_driver.get(driver, {})
            name = driver.replace("신시어리 ", "")
            print(f"    {name}: 월간 {monthly_km}km")
            for wk_label, km in weekly_bk.items():
                print(f"      {wk_label}: {km}km")

    except Exception as e:
        print(f"  [라우팅 실패] {e} — 라우팅 데이터 없이 계속 진행")

    fname = f"monthly_report_{start.strftime('%Y-%m')}.json"
    with open(fname, "w", encoding="utf-8") as fp:
        json.dump(
            {
                "generated_at": datetime.now().isoformat(),
                "month":        start.isoformat(),
                "month_label":  month_label(start),
                **data,
                "routing": routing_monthly,
            },
            fp, ensure_ascii=False, indent=2, default=str,
        )
    print(f"[OK] {fname} 저장 완료")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 완료")


if __name__ == "__main__":
    main()
