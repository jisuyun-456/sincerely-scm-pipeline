"""
Sincerely WMS -- Generate pages_data.json for GitHub Pages dashboard
REPORT_MODE=weekly  → 이번달 1일~오늘 (매주 월요일)
REPORT_MODE=monthly → 지난달 전체 (매월 1일)
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
REPORT_MODE      = os.environ.get("REPORT_MODE", "weekly")  # weekly | monthly

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
def get_period_range():
    today = date.today()
    if REPORT_MODE == "monthly":
        # 지난달 1일 ~ 말일
        first_this = today.replace(day=1)
        last_prev  = first_this - timedelta(days=1)
        return last_prev.replace(day=1), last_prev
    else:
        # 이번달 1일 ~ 오늘
        return today.replace(day=1), today

def current_week_label():
    today = date.today()
    w = today.isocalendar()[1]
    mon = today - timedelta(days=today.weekday())
    return f"W{w:02d} ({mon.strftime('%m/%d')}~)"

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
        if resp.status_code == 429:
            time.sleep(30)
            continue
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
    # by_week에 defect_rate 추가
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

# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    start, end = get_period_range()
    week_label = current_week_label()
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

    pages_data = {
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "report_mode": REPORT_MODE,
        "period": {
            "month":       start.strftime("%Y-%m"),
            "month_label": start.strftime("%Y년 %m월") + (" (지난달)" if REPORT_MODE == "monthly" else ""),
            "week_label":  week_label,
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

    out_path = "pages_data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(pages_data, f, ensure_ascii=False, indent=2, default=str)
    print(f"[generate] pages_data.json 생성 완료")
    print(f"  입하완료율: {inb_s['completion_rate']}%  불량률: {qc_s['defect_rate']}%  재고정확도: {mat_s['accuracy']}%")

if __name__ == "__main__":
    if not AIRTABLE_API_KEY:
        print("ERROR: AIRTABLE_API_KEY_WMS 없음", file=sys.stderr)
        sys.exit(1)
    main()
