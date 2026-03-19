"""
Sincerely WMS -- Generate pages_data.json for GitHub Pages dashboard
REPORT_MODE=weekly_review  → 지난주 월~금 실적 (매주 월요일)
REPORT_MODE=weekly_forecast → 지난주 기반 이번주 예측 (매주 월요일)
REPORT_MODE=monthly         → 지난달 전체 실적 (매월 1일)
"""

import os, sys, json, time
from datetime import date, datetime, timedelta
from collections import defaultdict

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests

# ── Env ──────────────────────────────────────────────────────────────────────
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY_WMS") or os.environ.get("AIRTABLE_PAT", "")
WMS_BASE_ID      = os.environ.get("AIRTABLE_BASE_WMS_ID") or os.environ.get("AIRTABLE_BASE_ID", "appLui4ZR5HWcQRri")
REPORT_MODE      = os.environ.get("REPORT_MODE", "weekly_review")  # weekly_review | weekly_forecast | monthly

# ── Airtable Table / Field IDs ───────────────────────────────────────────────
TABLE_MOVEMENT = "tblwq7Kj5Y9nVjlOw"
TABLE_MATERIAL = "tblaRpZstW10EwDlo"

F_PURPOSE    = "fldFRNxG1pNooEOC7"
F_IN_QTY     = "fldV8kVokQqMIsif0"
F_IN_DATE    = "flduN8khmYwdn7uVD"
F_IN_STATUS  = "fld4Yq9LYX46zC5m5"
F_STOCK_QTY  = "fldlJt3RPY6E8JB4G"
F_QC_QTY     = "fldnrqmT56niE7O21"
F_DEFECT_S   = "fld3lQvblfrqTl4O8"
F_DEFECT_F   = "fldsTXzxUeerw4qw2"
F_QC_RES     = "fldKrjj58HnHKT4SJ"
F_CANCEL     = "fldwgaM8OnKubM8oE"

F_MAT_NAME   = "fld7Pfip5zbBTaTdR"
F_MAT_PHYS   = "fld5XQQv2P9YJZP6n"
F_MAT_SYS    = "fldAFkM4HtGJsitOk"
F_MAT_AVAIL  = "fldZ5qLZKp0yy28So"
F_MAT_LOC    = "fldsDSdkogmJ0qsVC"
F_MAT_CHECK  = "flddQhs9cuA6G8xmq"

MOVEMENT_FIELDS = [
    F_PURPOSE, F_IN_QTY, F_IN_DATE, F_IN_STATUS, F_STOCK_QTY,
    F_QC_QTY, F_DEFECT_S, F_DEFECT_F, F_QC_RES, F_CANCEL
]
MATERIAL_FIELDS = [
    F_MAT_NAME, F_MAT_PHYS, F_MAT_SYS, F_MAT_AVAIL, F_MAT_LOC, F_MAT_CHECK
]

# ── 날짜 헬퍼 ────────────────────────────────────────────────────────────────
def last_week_range():
    """지난주 월요일 ~ 금요일"""
    today = date.today()
    last_monday = today - timedelta(days=today.weekday() + 7)
    last_friday = last_monday + timedelta(days=4)
    return last_monday, last_friday

def this_week_range():
    """이번주 월요일 ~ 금요일"""
    today = date.today()
    this_monday = today - timedelta(days=today.weekday())
    this_friday = this_monday + timedelta(days=4)
    return this_monday, this_friday

def prev_month_range():
    """지난달 1일 ~ 말일"""
    today = date.today()
    first_this = today.replace(day=1)
    last_prev  = first_this - timedelta(days=1)
    return last_prev.replace(day=1), last_prev

def get_period_range():
    if REPORT_MODE == "monthly":
        return prev_month_range()
    else:
        # weekly_review / weekly_forecast 모두 지난주 데이터 기반
        return last_week_range()

def week_label_for(monday: date) -> str:
    w = monday.isocalendar()[1]
    return f"W{w:02d} ({monday.strftime('%m/%d')}~)"

# ── Airtable 조회 ────────────────────────────────────────────────────────────
def _headers():
    return {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}

def _get_with_retry(url, field_params, params, max_retry=3):
    for attempt in range(max_retry):
        try:
            resp = requests.get(f"{url}?{field_params}", headers=_headers(), params=params, timeout=60)
            if resp.status_code == 429:
                time.sleep(30)
                continue
            return resp
        except requests.exceptions.ReadTimeout:
            wait = 10 * (attempt + 1)
            print(f"[generate] timeout, {wait}초 후 재시도 ({attempt+1}/{max_retry})")
            time.sleep(wait)
    raise RuntimeError("Airtable API 요청 최대 재시도 초과")

def fetch_movement(start: date, end: date) -> list:
    url = f"https://api.airtable.com/v0/{WMS_BASE_ID}/{TABLE_MOVEMENT}"
    formula = (
        f"AND("
        f"IS_AFTER({{{F_IN_DATE}}}, DATEADD('{start.isoformat()}', -1, 'days')), "
        f"IS_BEFORE({{{F_IN_DATE}}}, DATEADD('{end.isoformat()}', 1, 'days'))"
        f")"
    )
    field_params = "&".join(f"fields[]={fid}" for fid in MOVEMENT_FIELDS)
    all_records, offset = [], None
    while True:
        params = {"filterByFormula": formula, "pageSize": "100", "returnFieldsByFieldId": "true"}
        if offset:
            params["offset"] = offset
        resp = _get_with_retry(url, field_params, params)
        resp.raise_for_status()
        data = resp.json()
        all_records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.22)
    return all_records

def fetch_material() -> list:
    url = f"https://api.airtable.com/v0/{WMS_BASE_ID}/{TABLE_MATERIAL}"
    field_params = "&".join(f"fields[]={fid}" for fid in MATERIAL_FIELDS)
    all_records, offset = [], None
    while True:
        params = {"pageSize": "100", "returnFieldsByFieldId": "true"}
        if offset:
            params["offset"] = offset
        resp = _get_with_retry(url, field_params, params)
        resp.raise_for_status()
        data = resp.json()
        all_records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.22)
    return all_records

# ── 분석 함수 ────────────────────────────────────────────────────────────────
def _sel(val):
    if isinstance(val, dict):
        return val.get("name", "")
    return str(val) if val else ""

def analyze_inbound(records):
    total_cnt = len(records)
    total_in_qty = total_stock_qty = completed = unconfirmed = 0
    by_date    = defaultdict(lambda: {"cnt": 0, "in_qty": 0})
    by_week    = defaultdict(lambda: {"cnt": 0, "in_qty": 0})
    by_purpose = defaultdict(lambda: {"cnt": 0, "qty": 0})

    for r in records:
        c = r.get("cellValuesByFieldId", {})
        in_qty    = c.get(F_IN_QTY) or 0
        stock_qty = c.get(F_STOCK_QTY) or 0
        date_val  = c.get(F_IN_DATE, "")
        stat      = _sel(c.get(F_IN_STATUS, {}))
        purpose   = _sel(c.get(F_PURPOSE, {})) or "미분류"

        total_in_qty    += in_qty
        total_stock_qty += stock_qty
        if stat == "입하완료":
            completed += 1
        elif not stat:
            unconfirmed += 1

        if date_val:
            by_date[date_val]["cnt"]    += 1
            by_date[date_val]["in_qty"] += in_qty
            try:
                d = datetime.strptime(date_val, "%Y-%m-%d")
                wk = f"{d.year}-W{d.isocalendar()[1]:02d}"
            except Exception:
                wk = "기타"
            by_week[wk]["cnt"]    += 1
            by_week[wk]["in_qty"] += in_qty

        by_purpose[purpose]["cnt"] += 1
        by_purpose[purpose]["qty"] += in_qty

    return {
        "summary": {
            "total_cnt":       total_cnt,
            "total_in_qty":    total_in_qty,
            "total_stock_qty": total_stock_qty,
            "completed":       completed,
            "unconfirmed":     unconfirmed,
            "completion_rate": round(completed / total_cnt * 100, 1) if total_cnt else 0,
        },
        "by_date":    dict(sorted(by_date.items())),
        "by_week":    dict(sorted(by_week.items())),
        "by_purpose": dict(sorted(by_purpose.items(), key=lambda x: -x[1]["cnt"])),
    }

def analyze_qc(records):
    qc_recs = [
        r for r in records
        if (r.get("cellValuesByFieldId", {}).get(F_QC_QTY) or 0) > 0
        or r.get("cellValuesByFieldId", {}).get(F_QC_RES)
    ]
    total_qc = total_defect = 0
    result_dist = defaultdict(int)
    by_week = defaultdict(lambda: {"qc_qty": 0, "defect": 0})

    for r in qc_recs:
        c = r.get("cellValuesByFieldId", {})
        qc_qty   = c.get(F_QC_QTY) or 0
        defect   = (c.get(F_DEFECT_S) or 0) + (c.get(F_DEFECT_F) or 0)
        res      = _sel(c.get(F_QC_RES, {}))
        date_val = c.get(F_IN_DATE, "")

        total_qc     += qc_qty
        total_defect += defect
        if res:
            result_dist[res] += 1
        if date_val:
            try:
                d = datetime.strptime(date_val, "%Y-%m-%d")
                wk = f"W{d.isocalendar()[1]:02d}"
            except Exception:
                wk = "기타"
            by_week[wk]["qc_qty"] += qc_qty
            by_week[wk]["defect"] += defect

    defect_rate = round(total_defect / total_qc * 100, 2) if total_qc else 0.0
    bw = {}
    for wk, v in sorted(by_week.items()):
        dr = round(v["defect"] / v["qc_qty"] * 100, 1) if v["qc_qty"] > 0 else 0.0
        bw[wk] = {**v, "defect_rate": dr}

    return {
        "summary": {
            "qc_cnt":        len(qc_recs),
            "total_qc_qty":  total_qc,
            "total_defect":  total_defect,
            "defect_rate":   defect_rate,
            "target_met":    defect_rate <= 1.0,
        },
        "by_week":    bw,
        "result_dist": dict(result_dist),
    }

def analyze_material(records):
    has_stock = [r for r in records if (r.get("cellValuesByFieldId", {}).get(F_MAT_PHYS) or 0) > 0]
    total = len(has_stock)
    match = neg_avail = check_done = 0
    total_phys = total_avail = 0

    for r in has_stock:
        c = r.get("cellValuesByFieldId", {})
        phys  = c.get(F_MAT_PHYS) or 0
        sys_  = c.get(F_MAT_SYS) or 0
        avail = c.get(F_MAT_AVAIL) or 0
        chk   = _sel(c.get(F_MAT_CHECK, {}))

        total_phys  += phys
        total_avail += avail
        if phys == sys_:
            match += 1
        if avail < 0:
            neg_avail += 1
        if chk:
            check_done += 1

    accuracy = round(match / total * 100, 1) if total else 0.0
    return {
        "summary": {
            "total":        total,
            "accuracy":     accuracy,
            "mismatch":     total - match,
            "neg_avail":    neg_avail,
            "check_done":   check_done,
            "total_phys":   total_phys,
            "total_avail":  total_avail,
            "check_rate":   round(check_done / total * 100, 1) if total else 0.0,
        }
    }

def build_forecast(inbound, qc, material, this_week_start, this_week_end):
    """지난주 실적 기반 이번주 예측"""
    inb_s = inbound["summary"]
    qc_s  = qc["summary"]
    mat_s = material["summary"]

    # 지난주 영업일 수 (데이터 있는 날 기준, 최소 1)
    active_days = max(len(inbound["by_date"]), 1)

    daily_avg_cnt = inb_s["total_cnt"] / active_days
    daily_avg_qty = inb_s["total_in_qty"] / active_days

    proj_cnt  = round(daily_avg_cnt * 5)
    proj_qty  = round(daily_avg_qty * 5)
    proj_comp = inb_s["completion_rate"]   # 같은 완료율 유지 가정
    proj_def  = qc_s["defect_rate"]        # 같은 불량률 유지 가정

    comp_ok   = proj_comp >= 95.0
    defect_ok = proj_def  <= 1.0
    risk = "LOW" if comp_ok and defect_ok else ("HIGH" if not comp_ok and not defect_ok else "MEDIUM")

    return {
        "this_week_start": this_week_start.isoformat(),
        "this_week_end":   this_week_end.isoformat(),
        "active_days_last_week": active_days,
        "daily_avg_cnt":   round(daily_avg_cnt, 1),
        "daily_avg_qty":   round(daily_avg_qty, 1),
        "projected": {
            "inbound_cnt":       proj_cnt,
            "inbound_qty":       proj_qty,
            "completion_rate":   proj_comp,
            "defect_rate":       proj_def,
            "neg_avail":         mat_s["neg_avail"],
            "accuracy":          mat_s["accuracy"],
        },
        "kpi_assessment": {
            "completion": {"target": 95.0,  "projected": proj_comp, "achievable": comp_ok},
            "defect_rate":{"target":  1.0,  "projected": proj_def,  "achievable": defect_ok},
            "risk_level": risk,
        },
    }

# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    start, end = get_period_range()
    this_w_start, this_w_end = this_week_range()
    last_w_label = week_label_for(start - timedelta(days=start.weekday()))
    this_w_label = week_label_for(this_w_start)

    print(f"[generate] 모드: {REPORT_MODE} | 기간: {start} ~ {end}")

    print("[generate] movement 조회 중...")
    movement_records = fetch_movement(start, end)
    print(f"[generate] movement: {len(movement_records)}건")

    print("[generate] material 조회 중...")
    material_records = fetch_material()
    print(f"[generate] material: {len(material_records)}건")

    inbound  = analyze_inbound(movement_records)
    qc       = analyze_qc(movement_records)
    material = analyze_material(material_records)

    inb_s = inbound["summary"]
    qc_s  = qc["summary"]
    mat_s = material["summary"]

    # 모드별 period label
    if REPORT_MODE == "monthly":
        period_label = start.strftime("%Y년 %m월") + " (지난달)"
        week_lbl = ""
    elif REPORT_MODE == "weekly_forecast":
        period_label = this_w_label + " 예측"
        week_lbl = this_w_label
    else:  # weekly_review
        period_label = last_w_label + " 실적"
        week_lbl = last_w_label

    pages_data = {
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "report_mode": REPORT_MODE,
        "period": {
            "label":       period_label,
            "week_label":  week_lbl,
            "start":       start.isoformat(),
            "end":         end.isoformat(),
        },
        "kpi": {
            "completion_rate": inb_s["completion_rate"],
            "defect_rate":     qc_s["defect_rate"],
            "accuracy":        mat_s["accuracy"],
            "neg_avail_cnt":   mat_s["neg_avail"],
        },
        "inbound":  inbound,
        "qc":       qc,
        "material": material,
    }

    # 예측 모드일 때만 forecast 섹션 추가
    if REPORT_MODE == "weekly_forecast":
        pages_data["forecast"] = build_forecast(inbound, qc, material, this_w_start, this_w_end)

    out_path = "pages_data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(pages_data, f, ensure_ascii=False, indent=2, default=str)
    print(f"[generate] pages_data.json 생성 완료")
    print(f"  입하완료율: {inb_s['completion_rate']}%  불량률: {qc_s['defect_rate']}%  재고정확도: {mat_s['accuracy']}%")
    if REPORT_MODE == "weekly_forecast":
        fc = pages_data["forecast"]
        print(f"  [예측] 이번주 입고 예상: {fc['projected']['inbound_cnt']}건 / 리스크: {fc['kpi_assessment']['risk_level']}")

if __name__ == "__main__":
    if not AIRTABLE_API_KEY:
        print("ERROR: AIRTABLE_PAT 환경변수 없음", file=sys.stderr)
        sys.exit(1)
    main()
