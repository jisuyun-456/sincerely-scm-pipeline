"""
Sincerely SCM 주간 출하 리포트 v2
----------------------------------------------
매주 월요일 09:00~09:30 KST GitHub Actions 실행
결과: report_{날짜}.json 저장 -> GitHub Pages 자동 반영

포함 지표:
  [CBM]    총 CBM / 일별 CBM / 박스 타입별 구성비
  [물동량]  건수 / 건당 평균 CBM / 요일별 집중도
  [품질]   외박스 수량 미기재율 / 당일 등록 비율 / 리드타임
  [손익]   물류매출 / 운송비용 / CBM당 물류비 / 주간 트렌드
  [기사님] 차량 CBM 달성율 + 배송 거리 km (이전주 기준)
  [창고]   에이원센터 창고 가동율

환경변수:
  AIRTABLE_API_KEY      Airtable PAT
  AIRTABLE_BASE_ID      TMS base (app4x70a8mOrIKsMf)
  KAKAO_REST_API_KEY    카카오 REST API 키 (라우팅 km 계산용)
"""

import os
import json
import re
import time
import random
from datetime import datetime, timedelta, date
from collections import defaultdict

import pyairtable

API_KEY = os.environ["AIRTABLE_API_KEY"]
BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "app4x70a8mOrIKsMf")

TABLE_SHIPMENT = "tbllg1JoHclGYer7m"
TABLE_BOX      = "tbltwH7bHk41rTzhM"
TABLE_PRODUCT  = "tblBNh6oGDlTKGrdQ"

F_DATE        = "fldQvmEwwzvQW95h9"
F_ITEM        = "fldgSupj5XLjJXYQo"
F_BOX_PARSED  = "fldTjLDmw5sNGszeD"
F_BOX_MANUAL  = "fldRjMaXa5TdSsGDL"
F_TOTAL_CBM   = "fldJ9DHjwoRyeUEqE"
F_STATUS      = "fldOhibgxg6LIpRTi"
F_ITEM_DETAIL = "fldXXnGOXkm90snKn"
F_REVENUE     = "fldOFuvqBT0iXItcT"
F_COST        = "fldRT95SC88KSBATT"
F_PARTNER     = "fldHZ7yMT3KEu2gSj"

BOX_CBM = {
    "극소": 0.0098, "S280": 0.0098,
    "소":   0.0117, "S360": 0.0117,
    "중":   0.0201, "M350": 0.0201,
    "중대": 0.0492, "M480": 0.0492,
    "대":   0.1066, "L510": 0.1066,
    "특대": 0.1663, "L560": 0.1663,
}
BOX_SIZE_ORDER = ["극소", "소", "중", "중대", "대", "특대"]

VEHICLE_CBM = {
    "신시어리 (이장훈)": 5.4,
    "신시어리 (조희선)": 7.6,
    "신시어리 (박종성)": 9.5,
}
A1_WAREHOUSE_CBM = 44.4
WD_KR = ["월", "화", "수", "목", "금", "토", "일"]

_BOX_RE = re.compile(
    r"(극소|소|중대|중|대|특대|S280|S360|M350|M480|L510|L560)\s*(\d+)"
)


def week_range(offset: int = 0):
    today = date.today()
    mon = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
    return mon, mon + timedelta(days=4)


def fetch_shipments(start: date, end: date) -> list[dict]:
    api   = pyairtable.Api(API_KEY)
    table = api.table(BASE_ID, TABLE_SHIPMENT)
    formula = (
        f"AND("
        f"IS_AFTER({{출하확정일}}, DATEADD('{start.isoformat()}', -1, 'days')), "
        f"IS_BEFORE({{출하확정일}}, DATEADD('{end.isoformat()}',  1, 'days'))"
        f")"
    )
    return table.all(formula=formula)


def fetch_prev_weeks(n: int = 4) -> list[dict]:
    mon, _ = week_range(-n)
    _, fri = week_range(-1)
    return fetch_shipments(mon, fri)


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
        name = (f.get("fldx01uKEnCd0J0nP") or f.get("Name") or "").strip()
        cbm  = f.get("fldN1JrkxIr5m6pXz") or f.get("fld6W5ImO7UeBVMPI") or None
        if name and cbm:
            try:
                result.append((re.sub(r"\s+", "", name), float(cbm)))
            except (ValueError, TypeError):
                pass
    result.sort(key=lambda x: -len(x[0]))
    print(f"  Product CBM 조회 완료: {len(result)}개")
    return result


def parse_box_cbm(box_str: str, live: dict) -> tuple[float, dict]:
    ref   = {**BOX_CBM, **live}
    total = 0.0
    by_type: dict[str, int] = {}
    for m in _BOX_RE.finditer(box_str):
        btype, cnt = m.group(1), int(m.group(2))
        total += ref.get(btype, 0) * cnt
        norm = next((k for k in BOX_CBM if k == btype), btype)
        by_type[norm] = by_type.get(norm, 0) + cnt
    return round(total, 4), by_type


def match_cbm_from_product(
    item_str: str,
    product_cbm: list[tuple[str, float]],
) -> float:
    total = 0.0
    matched = False
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
                matched = True
                break
    return round(total, 4) if matched else 0.0


def analyze(
    records: list[dict],
    live_cbm: dict,
    week_start: date,
    product_cbm: list[tuple[str, float]] | None = None,
) -> dict:

    by_date     = defaultdict(lambda: {"cbm": 0.0, "count": 0, "boxes": 0, "completed": 0, "pending": 0, "revenue": 0.0, "cost": 0.0})
    box_type_all = defaultdict(int)
    item_agg    = defaultdict(lambda: {"qty": 0, "cbm": 0.0})
    cbm_sources = {"manual": 0, "product_match": 0, "box_parse": 0, "unmatched": 0}
    driver_daily  = defaultdict(lambda: defaultdict(float))
    driver_weekly = defaultdict(float)
    missing_box_qty = same_day_create = 0
    leadtimes: list[float] = []
    total = len(records)

    for rec in records:
        f   = rec["fields"]
        d_s = f.get("출하확정일", "")
        if not d_s:
            continue
        ship_date = date.fromisoformat(d_s)
        bkt = by_date[ship_date]
        bkt["count"] += 1

        status_obj = f.get("발송상태_TMS")
        status = status_obj["name"] if isinstance(status_obj, dict) else (status_obj or "")
        bkt["completed" if "완료" in status else "pending"] += 1
        bkt["revenue"] += f.get("물류매출") or 0
        bkt["cost"]    += f.get("운송비용") or 0

        total_cbm_field = f.get("Total_CBM")
        box_qty = f.get("최종 외박스 수량 값") or f.get("외박스 수량 (직접입력)") or ""
        if isinstance(box_qty, list):
            box_qty = ", ".join(str(x) for x in box_qty)
        box_qty = box_qty.strip()

        cbm_val = 0.0
        btype_counts: dict = {}

        if total_cbm_field and total_cbm_field > 0:
            cbm_val = total_cbm_field
            cbm_sources["manual"] += 1
        else:
            item_str = f.get("최종 출하 품목") or f.get("최종 출고 품목 및 수량") or ""
            if item_str.strip() and product_cbm:
                cbm_val = match_cbm_from_product(item_str, product_cbm)
            if cbm_val > 0:
                cbm_sources["product_match"] += 1
            elif box_qty and _BOX_RE.search(box_qty):
                cbm_val, btype_counts = parse_box_cbm(box_qty, live_cbm)
                for bt, cnt in btype_counts.items():
                    box_type_all[bt] += cnt
                    bkt["boxes"] += cnt
                cbm_sources["box_parse"] += 1
            else:
                cbm_sources["unmatched"] += 1

        bkt["cbm"] = round(bkt["cbm"] + cbm_val, 4)

        pf = f.get("배송파트너 (from 배송파트너)")
        pname = None
        if isinstance(pf, dict):
            for vals in pf.get("valuesByLinkedRecordId", {}).values():
                if vals: pname = vals[0]; break
        elif isinstance(pf, list) and pf:
            pname = str(pf[0])
        elif pf:
            pname = str(pf)
        if pname and pname in VEHICLE_CBM:
            driver_daily[pname][d_s]  = round(driver_daily[pname][d_s] + cbm_val, 4)
            driver_weekly[pname]      = round(driver_weekly[pname] + cbm_val, 4)

        if not box_qty or not _BOX_RE.search(box_qty):
            missing_box_qty += 1
        created_s = rec.get("createdTime", "")
        if created_s:
            created_d = datetime.fromisoformat(created_s.replace("Z", "+00:00")).date()
            if created_d == ship_date:
                same_day_create += 1
            if "완료" in status:
                delta = (ship_date - created_d).days
                if 0 <= delta <= 30:
                    leadtimes.append(float(delta))

        item_str = f.get("최종 출하 품목") or ""
        for line in item_str.strip().splitlines():
            line = line.strip()
            if not line: continue
            nums  = re.findall(r"\d+", line)
            iname = re.sub(r"\s*\d+\s*$", "", line).strip()
            if iname and nums:
                qty = int(nums[-1])
                item_agg[iname]["qty"] += qty
                if product_cbm:
                    for prod_norm, cpb in product_cbm:
                        if prod_norm in re.sub(r"\s+", "", iname):
                            item_agg[iname]["cbm"] += round(cpb * qty, 4)
                            break

    total_cbm  = round(sum(v["cbm"] for v in by_date.values()), 3)
    total_cnt  = sum(v["count"]     for v in by_date.values())
    total_done = sum(v["completed"] for v in by_date.values())
    total_pend = sum(v["pending"]   for v in by_date.values())
    total_rev  = sum(v["revenue"]   for v in by_date.values())
    total_cost = sum(v["cost"]      for v in by_date.values())
    total_boxes = sum(box_type_all.values())

    wd_cbm: dict[int, float] = defaultdict(float)
    for d, v in by_date.items():
        wd_cbm[d.weekday()] += v["cbm"]
    cbm_vals = list(wd_cbm.values())
    avg_wd   = sum(cbm_vals) / len(cbm_vals) if cbm_vals else 0
    variance = round(sum((x - avg_wd) ** 2 for x in cbm_vals) / len(cbm_vals), 2) if cbm_vals else 0

    # 기사님 달성율: 차량CBM x 실배차일수 기준
    driver_weekly_max = {}
    driver_pct = {}
    driver_work_days = {}
    for driver, cap in VEHICLE_CBM.items():
        daily = dict(driver_daily.get(driver, {}))
        work_dates = sorted([d for d, c in daily.items() if c > 0])
        work_cnt   = len(work_dates)
        weekly_max = round(cap * work_cnt, 3)
        weekly_cbm = round(driver_weekly.get(driver, 0.0), 3)
        driver_weekly_max[driver] = weekly_max
        driver_pct[driver]        = round(weekly_cbm / weekly_max * 100, 1) if weekly_max > 0 else 0.0
        driver_work_days[driver]  = {
            "count": work_cnt, "dates": work_dates,
            "labels": [f"{d[5:].replace('-','/')}({WD_KR[date.fromisoformat(d).weekday()]})" for d in work_dates],
        }

    a1_pct = round(total_cbm / A1_WAREHOUSE_CBM * 100, 1)

    return {
        "by_date": {k.isoformat() if isinstance(k, date) else k: v for k, v in by_date.items()},
        "summary": {
            "total_cbm": total_cbm, "total_count": total_cnt,
            "completed": total_done, "pending": total_pend,
            "revenue": total_rev, "cost": total_cost,
            "profit": round(total_rev - total_cost, 0),
            "cbm_per_shipment": round(total_cbm / total_cnt, 3) if total_cnt else 0,
            "cbm_unit_cost": round(total_cost / total_cbm, 0) if total_cbm > 0 else 0,
        },
        "box_type": {
            "counts": dict(box_type_all),
            "pct":    {k: round(v / total_boxes * 100, 1) for k, v in box_type_all.items()} if total_boxes else {},
            "total":  total_boxes,
        },
        "weekday_dist": {"by_wd": dict(wd_cbm), "variance": variance, "max_wd": max(wd_cbm, key=wd_cbm.get) if wd_cbm else None},
        "quality": {
            "total_records": total,
            "missing_box_qty": missing_box_qty,
            "missing_rate":  round(missing_box_qty / total * 100, 1) if total else 0,
            "same_day_create": same_day_create,
            "same_day_rate": round(same_day_create / total * 100, 1) if total else 0,
            "avg_leadtime_days": round(sum(leadtimes) / len(leadtimes), 1) if leadtimes else None,
        },
        "confidence":  round((cbm_sources["manual"] + cbm_sources["box_parse"]) / total * 100, 1) if total else 0,
        "cbm_sources": cbm_sources,
        "top_items": sorted(
            [{"name": k, "qty": v["qty"], "cbm": round(v["cbm"], 3)} for k, v in item_agg.items() if v["cbm"] > 0],
            key=lambda x: -x["cbm"],
        )[:8],
        "driver_daily":       {k: dict(v) for k, v in driver_daily.items()},
        "driver_weekly":      dict(driver_weekly),
        "driver_weekly_max":  driver_weekly_max,
        "driver_pct":         driver_pct,
        "driver_work_days":   driver_work_days,
        "a1_utilization":     {"total_cbm": total_cbm, "capacity": A1_WAREHOUSE_CBM, "pct": a1_pct},
    }


def build_trend(prev_records, live_cbm, product_cbm=None) -> list[dict]:
    weekly: dict[date, dict] = defaultdict(lambda: {"cbm": 0.0, "revenue": 0.0, "cost": 0.0, "count": 0})
    for rec in prev_records:
        f   = rec["fields"]
        d_s = f.get("출하확정일")
        if not d_s: continue
        d   = date.fromisoformat(d_s)
        mon = d - timedelta(days=d.weekday())
        w   = weekly[mon]
        w["count"]   += 1
        w["revenue"] += f.get("물류매출") or 0
        w["cost"]    += f.get("운송비용") or 0
        total_cbm_f = f.get("Total_CBM")
        box_qty = f.get("최종 외박스 수량 값") or ""
        if isinstance(box_qty, list):
            box_qty = ", ".join(str(x) for x in box_qty)
        if total_cbm_f and total_cbm_f > 0:
            w["cbm"] += total_cbm_f
        elif f.get("최종 출하 품목") and product_cbm:
            cv = match_cbm_from_product(f["최종 출하 품목"], product_cbm)
            w["cbm"] += cv if cv > 0 else (parse_box_cbm(box_qty, live_cbm)[0] if box_qty and _BOX_RE.search(box_qty) else 0)
        elif box_qty and _BOX_RE.search(box_qty):
            w["cbm"] += parse_box_cbm(box_qty, live_cbm)[0]
    result = []
    for mon in sorted(weekly.keys())[-4:]:
        w = weekly[mon]
        rev, cst = round(w["revenue"]), round(w["cost"])
        result.append({"week": f"{mon.month}/{mon.day}주", "cbm": round(w["cbm"], 2), "revenue": rev, "cost": cst, "profit": rev - cst, "count": w["count"]})
    return result


def main():
    if not os.environ.get("SKIP_DELAY"):
        d = random.randint(0, 29 * 60)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {d//60}분 {d%60}초 후 실행")
        time.sleep(d)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 주간 리포트 생성 시작")

    this_mon, this_fri = week_range(0)
    next_mon, next_fri = week_range(1)
    prev_mon, prev_fri = week_range(-1)
    print(f"  이전주: {prev_mon} ~ {prev_fri}")
    print(f"  이번주: {this_mon} ~ {this_fri}")
    print(f"  다음주: {next_mon} ~ {next_fri}")

    live_cbm    = fetch_box_cbm_live()
    product_cbm = fetch_product_cbm()
    this_recs   = fetch_shipments(this_mon, this_fri)
    next_recs   = fetch_shipments(next_mon, next_fri)
    prev_recs   = fetch_shipments(prev_mon, prev_fri)
    trend_recs  = fetch_prev_weeks(4)
    print(f"  이전주 {len(prev_recs)}건 / 이번주 {len(this_recs)}건 / 다음주 {len(next_recs)}건 / 트렌드 {len(trend_recs)}건")

    this_data = analyze(this_recs, live_cbm, this_mon, product_cbm)
    next_data = analyze(next_recs, live_cbm, next_mon, product_cbm)
    prev_data = analyze(prev_recs, live_cbm, prev_mon, product_cbm)
    trend     = build_trend(trend_recs, live_cbm, product_cbm)

    src = this_data["cbm_sources"]
    print(f"  CBM: 수동{src['manual']} + 매칭{src['product_match']} + 파싱{src['box_parse']} / 미산출{src['unmatched']}")

    # -- 이전주 기사님 배송 라우팅 km 계산 --
    # 이전주 리포트에만 포함: 기사님별 일별 km + 주간 총 km
    print("  [라우팅] 이전주 기사님 배송 거리 계산 중...")
    routing_json = {}
    try:
        from delivery_routing import (
            fetch_routing_records, calc_driver_routing,
            routing_to_json, format_routing_log,
        )
        routing_recs   = fetch_routing_records(prev_mon, prev_fri)
        routing_result = calc_driver_routing(routing_recs)
        print(format_routing_log(routing_result))
        routing_json   = routing_to_json(routing_result)
    except Exception as e:
        print(f"  [라우팅 실패] {e}")

    # 로그: CBM 달성율 + km
    for driver, pct in prev_data.get("driver_pct", {}).items():
        wd   = prev_data["driver_work_days"][driver]
        wmax = prev_data["driver_weekly_max"][driver]
        wact = prev_data["driver_weekly"].get(driver, 0)
        km   = routing_json.get("driver_weekly_km", {}).get(driver)
        name = driver.replace("신시어리 ", "")
        print(f"    {name}: CBM {wact:.2f}/{wmax}m3 ({VEHICLE_CBM[driver]}x{wd['count']}일)={pct}%" + (f" / {km}km" if km else ""))

    a1 = prev_data.get("a1_utilization", {})
    if a1:
        print(f"  [에이원] {a1['total_cbm']}m3 / {a1['capacity']}m3 = {a1['pct']}%")

    archive = {
        "generated_at": datetime.now().isoformat(),
        "week_start":   this_mon.isoformat(),
        "this_week": {
            "summary": this_data["summary"],
            "by_date": {k.isoformat() if hasattr(k, "isoformat") else k: v for k, v in this_data["by_date"].items()},
            "box_type": this_data["box_type"], "quality": this_data["quality"],
            "top_items": this_data["top_items"], "cbm_sources": this_data["cbm_sources"],
            "confidence": this_data["confidence"],
        },
        "prev_week": {
            "summary":           prev_data["summary"],
            "week_start":        prev_mon.isoformat(),
            "driver_daily":      prev_data["driver_daily"],
            "driver_weekly":     prev_data["driver_weekly"],
            "driver_weekly_max": prev_data["driver_weekly_max"],
            "driver_pct":        prev_data["driver_pct"],
            "driver_work_days":  prev_data["driver_work_days"],
            "a1_utilization":    prev_data.get("a1_utilization", {}),
            "routing":           routing_json,  # 기사님별 일별/주간 km
        },
        "next_week": {
            "summary": next_data["summary"],
            "by_date": {k.isoformat() if hasattr(k, "isoformat") else k: v for k, v in next_data["by_date"].items()},
        },
        "trend": trend,
    }

    fname = f"report_{this_mon.isoformat()}.json"
    with open(fname, "w", encoding="utf-8") as fp:
        json.dump(archive, fp, ensure_ascii=False, indent=2, default=str)
    print(f"[OK] {fname} 저장 완료")

    # docs/index.html에 JSON 주입
    import pathlib
    _html = pathlib.Path(__file__).parent.parent / "docs" / "index.html"
    if _html.exists():
        _src = _html.read_text(encoding="utf-8")
        _json_str = json.dumps(archive, ensure_ascii=False, default=str)
        _html.write_text(
            _src.replace("const REPORT_DATA = null", f"const REPORT_DATA = {_json_str}"),
            encoding="utf-8"
        )
        print("[OK] docs/index.html JSON 주입 완료")

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 완료")


if __name__ == "__main__":
    main()
