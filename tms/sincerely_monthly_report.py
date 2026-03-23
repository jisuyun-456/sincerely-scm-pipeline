"""
Sincerely SCM 월간 출하 리포트
----------------------------------------------
매월 1일 09:00 KST GitHub Actions 실행
결과: monthly_report_{YYYY-MM}.json -> GitHub Pages

포함 지표:
  [CBM]    월 총 CBM / 주차별 CBM 추이
  [배차]   월 총 배차 건수 / 배송파트너별 비율
  [손익]   물류매출 / 운송비용 / 물류 손익
  [품목]   월 출하 품목 Top 10
  [라우팅] 기사님별 주간 km + 월간 총 km

환경변수:
  AIRTABLE_API_KEY_TMS   Airtable PAT
  AIRTABLE_BASE_TMS_ID   TMS base (app4x70a8mOrIKsMf)
  KAKAO_REST_API_KEY     카카오 REST API 키
"""

import os, json, re, time, random
from datetime import datetime, timedelta, date
from collections import defaultdict
import pyairtable

API_KEY = os.environ["AIRTABLE_API_KEY_TMS"]
BASE_ID = os.environ.get("AIRTABLE_BASE_TMS_ID", "app4x70a8mOrIKsMf")

TABLE_SHIPMENT = "tbllg1JoHclGYer7m"
TABLE_BOX      = "tbltwH7bHk41rTzhM"
TABLE_PRODUCT  = "tblBNh6oGDlTKGrdQ"

F_DATE     = "fldQvmEwwzvQW95h9"
F_ITEM     = "fldgSupj5XLjJXYQo"
F_TOTAL_CBM= "fldJ9DHjwoRyeUEqE"
F_STATUS   = "fldOhibgxg6LIpRTi"
F_REVENUE  = "fldOFuvqBT0iXItcT"
F_COST     = "fldRT95SC88KSBATT"
F_PARTNER  = "fldHZ7yMT3KEu2gSj"

BOX_CBM = {
    "극소":0.0098,"S280":0.0098,"소":0.0117,"S360":0.0117,
    "중":0.0201,"M350":0.0201,"중대":0.0492,"M480":0.0492,
    "대":0.1066,"L510":0.1066,"특대":0.1663,"L560":0.1663,
}
PARTNER_GROUP = {
    "신시어리 (이장훈)":"신시어리 기사님 (이장훈)",
    "신시어리 (박종성)":"신시어리 기사님 (박종성)",
    "신시어리 (조희선)":"신시어리 기사님 (조희선)",
    "신시어리 (로젠)":"로젠 택배",
    "고객":"고객 직접수령",
}
_BOX_RE = re.compile(r"(극소|소|중대|중|대|특대|S280|S360|M350|M480|L510|L560)\s*(\d+)")


# 날짜 유틸
def prev_month_range() -> tuple[date, date]:
    today = date.today()
    first = today.replace(day=1)
    last  = first - timedelta(days=1)
    return last.replace(day=1), last

def month_label(d: date) -> str:
    return f"{d.year}년 {d.month}월"

def week_number_of_month(d: date) -> int:
    return (d.day - 1) // 7 + 1


# Airtable 조회
def fetch_month_shipments(start: date, end: date) -> list[dict]:
    api = pyairtable.Api(API_KEY)
    tbl = api.table(BASE_ID, TABLE_SHIPMENT)
    formula = (
        f"AND(IS_AFTER({{출하확정일}},DATEADD('{start.isoformat()}',-1,'days')),"
        f"IS_BEFORE({{출하확정일}},DATEADD('{end.isoformat()}',1,'days')))"
    )
    return tbl.all(formula=formula)

def fetch_box_cbm_live() -> dict:
    api = pyairtable.Api(API_KEY)
    tbl = api.table(BASE_ID, TABLE_BOX)
    live = {}
    for rec in tbl.all():
        f = rec["fields"]
        for key in (f.get("Box Code"), f.get("박스")):
            if key: live[key] = f.get("cbm", 0)
    return live

def fetch_product_cbm() -> list[tuple[str, float]]:
    api = pyairtable.Api(API_KEY)
    tbl = api.table(BASE_ID, TABLE_PRODUCT)
    result = []
    for rec in tbl.all():
        f    = rec["fields"]
        name = (f.get("fldx01uKEnCd0J0nP") or f.get("Name") or "").strip()
        cbm  = f.get("fldN1JrkxIr5m6pXz") or f.get("fld6W5ImO7UeBVMPI") or None
        if name and cbm:
            try: result.append((re.sub(r"\s+","",name), float(cbm)))
            except (ValueError,TypeError): pass
    result.sort(key=lambda x:-len(x[0]))
    print(f"  Product CBM: {len(result)}개")
    return result


# CBM 파싱
def parse_box_cbm(box_str: str, live: dict) -> float:
    ref = {**BOX_CBM, **live}
    total = 0.0
    for m in _BOX_RE.finditer(box_str):
        total += ref.get(m.group(1), 0) * int(m.group(2))
    return round(total, 4)

def match_cbm_from_product(item_str: str, product_cbm: list[tuple[str, float]]) -> float:
    total = 0.0; matched = False
    for line in item_str.strip().splitlines():
        line = line.strip()
        if not line: continue
        norm = re.sub(r"\s+","",line)
        nums = re.findall(r"\d+", norm)
        for prod_norm, cpb in product_cbm:
            if prod_norm in norm:
                total += cpb * (int(nums[-1]) if nums else 1)
                matched = True; break
    return round(total,4) if matched else 0.0

def get_cbm(f: dict, live: dict, product_cbm=None) -> float:
    v = f.get("Total_CBM")
    if v and v > 0: return float(v)
    item = f.get("최종 출하 품목") or ""
    if item.strip() and product_cbm:
        cv = match_cbm_from_product(item, product_cbm)
        if cv > 0: return cv
    box = f.get("최종 외박스 수량 값") or f.get("외박스 수량 (직접입력)") or ""
    if isinstance(box, list): box = ", ".join(str(x) for x in box)
    box = box.strip()
    if box and _BOX_RE.search(box): return parse_box_cbm(box, live)
    return 0.0


# 월간 분석
def analyze_month(records: list[dict], live_cbm: dict, product_cbm=None) -> dict:
    total_cbm = total_count = total_rev = total_cost = 0.0
    weekly_cbm: dict[int,float]  = defaultdict(float)
    weekly_cnt: dict[int,int]    = defaultdict(int)
    weekly_labels: dict[int,str] = {}
    partner_cnt: dict[str,int]   = defaultdict(int)
    partner_cbm: dict[str,float] = defaultdict(float)
    item_agg: dict = defaultdict(lambda: {"qty":0,"cbm":0.0})

    for rec in records:
        f   = rec["fields"]
        d_s = f.get("출하확정일")
        if not d_s: continue
        ship_date = date.fromisoformat(d_s)
        week_no   = week_number_of_month(ship_date)
        cbm_val   = get_cbm(f, live_cbm, product_cbm)

        total_count += 1; total_cbm += cbm_val
        total_rev   += f.get("물류매출") or 0
        total_cost  += f.get("운송비용") or 0
        weekly_cbm[week_no] += cbm_val
        weekly_cnt[week_no] += 1
        if week_no not in weekly_labels:
            mon = ship_date - timedelta(days=ship_date.weekday())
            weekly_labels[week_no] = f"{mon.month}/{mon.day}주"

        pf = f.get("배송파트너 (from 배송파트너)")
        names = []
        if isinstance(pf, dict):
            for vals in pf.get("valuesByLinkedRecordId", {}).values(): names.extend(vals)
        elif isinstance(pf, list): names = [str(p) for p in pf]
        elif pf: names = [str(pf)]
        for raw in names:
            d = PARTNER_GROUP.get(raw, raw)
            partner_cnt[d] += 1; partner_cbm[d] += cbm_val

        item_str = f.get("최종 출하 품목") or ""
        for line in item_str.strip().splitlines():
            line = line.strip()
            if not line: continue
            nums = re.findall(r"\d+", line)
            iname = re.sub(r"\s*\d+\s*$","",line).strip()
            if iname and nums:
                qty = int(nums[-1])
                item_agg[iname]["qty"] += qty
                if product_cbm:
                    for prod_norm, cpb in product_cbm:
                        if prod_norm in re.sub(r"\s+","",iname):
                            item_agg[iname]["cbm"] += round(cpb*qty,4); break

    total_cbm  = round(total_cbm, 2)
    total_rev  = round(total_rev, 0)
    total_cost = round(total_cost, 0)
    cnt = int(total_count)

    return {
        "total_cbm":      total_cbm,
        "total_count":    cnt,
        "total_rev":      total_rev,
        "total_cost":     total_cost,
        "profit":         total_rev - total_cost,
        "cbm_per_ship":   round(total_cbm/cnt,3) if cnt else 0,
        "weekly_cbm":     dict(weekly_cbm),
        "weekly_cnt":     dict(weekly_cnt),
        "weekly_labels":  weekly_labels,
        "partner_cnt":    dict(partner_cnt),
        "partner_pct":    {p: round(c/cnt*100,1) if cnt else 0 for p,c in partner_cnt.items()},
        "partner_cbm":    dict(partner_cbm),
        "top_items":      sorted([(k,v["qty"],round(v["cbm"],3)) for k,v in item_agg.items()], key=lambda x:-x[2])[:10],
    }


# 주간별 km 집계 헬퍼
def _calc_weekly_km_breakdown(driver_daily_routes: dict) -> dict:
    """
    {기사: {날짜: {total_km,...}}} 을 주간 레이블로 묶어 합산
    반환: {기사: {"3/2주": 45.2, "3/9주": 52.1, ...}}
    """
    result = {}
    for driver, daily in driver_daily_routes.items():
        weekly: dict[str,float] = defaultdict(float)
        for day_str, info in daily.items():
            try:
                d   = date.fromisoformat(day_str)
                mon = d - timedelta(days=d.weekday())
                wk  = f"{mon.month}/{mon.day}주"
                weekly[wk] = round(weekly[wk] + info.get("total_km",0), 2)
            except Exception:
                pass
        result[driver] = dict(sorted(weekly.items()))
    return result


# 메인
def main():
    skip = os.environ.get("SKIP_DELAY","0")
    if skip != "1":
        d = random.randint(0, 29*60)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {d//60}분 {d%60}초 후 실행")
        time.sleep(d)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 월간 리포트 생성 시작")
    start, end = prev_month_range()
    print(f"  대상: {start} ~ {end}  ({month_label(start)})")

    live_cbm    = fetch_box_cbm_live()
    product_cbm = fetch_product_cbm()
    records     = fetch_month_shipments(start, end)
    print(f"  조회 건수: {len(records)}건")

    data = analyze_month(records, live_cbm, product_cbm)

    # -- 월간 기사님 배송 라우팅 km 계산 --
    # 월 전체 기간으로 fetch -> 주간별 km + 월간 총 km
    print("  [라우팅] 월간 기사님 배송 거리 계산 중...")
    routing_monthly = {}
    try:
        from delivery_routing import (
            fetch_routing_records, calc_driver_routing,
            routing_to_json, format_routing_log, SINCERELY_DRIVERS,
        )
        routing_recs   = fetch_routing_records(start, end)
        routing_result = calc_driver_routing(routing_recs)
        routing_json   = routing_to_json(routing_result)
        print(format_routing_log(routing_result))

        weekly_km_breakdown = _calc_weekly_km_breakdown(
            routing_json.get("driver_daily_routes", {})
        )
        routing_monthly = {
            # 월간 총 km (기사님별)
            "driver_monthly_km":          routing_result["driver_weekly_km"],
            # 주간별 km {"기사명": {"3/2주": 45.2, ...}}
            "driver_weekly_km_breakdown": weekly_km_breakdown,
            # 일별 상세 경로
            "driver_daily_routes":        routing_json.get("driver_daily_routes", {}),
        }

        print("\n  [기사님별 월간/주간 km]")
        for driver in SINCERELY_DRIVERS:
            monthly_km = routing_result["driver_weekly_km"].get(driver, 0)
            name = driver.replace("신시어리 ","")
            print(f"    {name}: 월간 총 {monthly_km}km")
            for wk, km in weekly_km_breakdown.get(driver, {}).items():
                print(f"      {wk}: {km}km")

    except Exception as e:
        print(f"  [라우팅 실패] {e}")

    monthly_data = {
        "generated_at": datetime.now().isoformat(),
        "month":        start.isoformat(),
        "month_label":  month_label(start),
        **data,
        # routing.driver_monthly_km[기사명]           = 월간 총 km
        # routing.driver_weekly_km_breakdown[기사명]  = {주차: km}
        # routing.driver_daily_routes[기사명][날짜]    = {total_km, stops, route}
        "routing": routing_monthly,
    }

    fname = f"monthly_report_{start.strftime('%Y-%m')}.json"
    with open(fname, "w", encoding="utf-8") as fp:
        json.dump(monthly_data, fp, ensure_ascii=False, indent=2, default=str)
    print(f"[OK] {fname} 저장 완료")

    # docs/monthly_report.html에 JSON 주입
    import pathlib
    _html = pathlib.Path(__file__).parent.parent / "docs" / "monthly_report.html"
    if _html.exists():
        _src = _html.read_text(encoding="utf-8")
        _json_str = json.dumps(monthly_data, ensure_ascii=False, default=str)
        _html.write_text(
            _src.replace("const MONTHLY_DATA = null", f"const MONTHLY_DATA = {_json_str}"),
            encoding="utf-8"
        )
        print("[OK] docs/monthly_report.html JSON 주입 완료")

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 완료")


if __name__ == "__main__":
    main()
