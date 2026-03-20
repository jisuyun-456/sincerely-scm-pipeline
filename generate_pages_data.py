"""
Sincerely WMS -- Generate pages_data.json for GitHub Pages dashboard
REPORT_MODE=weekly_review  → 지난주 월~금 실적 (매주 월요일)
REPORT_MODE=weekly_forecast → 지난주 기반 이번주 예측 (매주 월요일)
REPORT_MODE=monthly         → 지난달 전체 실적 (매월 1일)
"""

import os, sys, json, time, math, re
from datetime import date, datetime, timedelta
from collections import defaultdict

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests

# ── Env ──────────────────────────────────────────────────────────────────────
AIRTABLE_API_KEY_WMS = os.environ.get("AIRTABLE_API_KEY_WMS") or os.environ.get("AIRTABLE_PAT", "")
AIRTABLE_API_KEY_TMS = os.environ.get("AIRTABLE_API_KEY_TMS") or AIRTABLE_API_KEY_WMS
WMS_BASE_ID          = os.environ.get("AIRTABLE_BASE_WMS_ID") or os.environ.get("AIRTABLE_BASE_ID", "appLui4ZR5HWcQRri")
TMS_BASE_ID          = os.environ.get("AIRTABLE_BASE_TMS_ID") or "app4x70a8mOrIKsMf"
REPORT_MODE          = os.environ.get("REPORT_MODE", "weekly_review")  # weekly_review | weekly_forecast | monthly

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
F_ITEM_NAME  = "fldws6Ohz68i3GBPR"   # 입고물품 (primary)
F_ITEM_ALT   = "fldwZKCYZ4IFOigRp"   # 이동물품 (fallback)

F_MAT_NAME   = "fld7Pfip5zbBTaTdR"
F_MAT_PHYS   = "fld5XQQv2P9YJZP6n"
F_MAT_SYS    = "fldAFkM4HtGJsitOk"
F_MAT_AVAIL  = "fldZ5qLZKp0yy28So"
F_MAT_LOC    = "fldsDSdkogmJ0qsVC"
F_MAT_CHECK  = "flddQhs9cuA6G8xmq"

MOVEMENT_FIELDS = [
    F_PURPOSE, F_IN_QTY, F_IN_DATE, F_IN_STATUS, F_STOCK_QTY,
    F_QC_QTY, F_DEFECT_S, F_DEFECT_F, F_QC_RES, F_CANCEL,
    F_ITEM_NAME, F_ITEM_ALT,
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
    return {"Authorization": f"Bearer {AIRTABLE_API_KEY_WMS}", "Content-Type": "application/json"}

def _tms_headers():
    return {"Authorization": f"Bearer {AIRTABLE_API_KEY_TMS}", "Content-Type": "application/json"}

def _get_with_retry(url, field_params, params, max_retry=3, headers=None):
    h = headers or _headers()
    for attempt in range(max_retry):
        try:
            resp = requests.get(f"{url}?{field_params}", headers=h, params=params, timeout=60)
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

# ── TMS Table / Field IDs ────────────────────────────────────────────────────
TMS_TABLE_SHIPMENT = "tbllg1JoHclGYer7m"
TMS_TABLE_BOX      = "tbltwH7bHk41rTzhM"

TF_DATE        = "fldQvmEwwzvQW95h9"  # 출하확정일
TF_ITEM        = "fldgSupj5XLjJXYQo"  # 최종 출하 품목
TF_BOX_PARSED  = "fldTjLDmw5sNGszeD"  # 최종 외박스 수량 값 (formula)
TF_BOX_MANUAL  = "fldRjMaXa5TdSsGDL"  # 외박스 수량 직접입력
TF_TOTAL_CBM   = "fldJ9DHjwoRyeUEqE"  # Total_CBM
TF_STATUS      = "fldOhibgxg6LIpRTi"  # 발송상태_TMS
TF_ITEM_DETAIL = "fldXXnGOXkm90snKn"  # 최종 출고 품목 및 수량
TF_BOX_CODE    = "fldELrd8bBVjQCHnp"  # Box Code
TF_BOX_NAME    = "fldgvlGjLb4FTlQ0v"  # 박스명
TF_BOX_CBM     = "fldjFaXiYzeJ2Zt7M"  # cbm
TF_PARTNER     = "fldHZ7yMT3KEu2gSj"  # 배송파트너

TMS_SHIP_FIELDS = [TF_DATE, TF_ITEM, TF_BOX_PARSED, TF_BOX_MANUAL, TF_TOTAL_CBM, TF_STATUS, TF_ITEM_DETAIL, TF_PARTNER]
TMS_BOX_FIELDS  = [TF_BOX_CODE, TF_BOX_NAME, TF_BOX_CBM]

# Product table
TMS_TABLE_PRODUCT = "tblBNh6oGDlTKGrdQ"
TF_PROD_NAME    = "fldx01uKEnCd0J0nP"   # Name
TF_PROD_BOX     = "fldqGM1lw2TUpZdKW"   # 박스명칭 (singleSelect)
TF_PROD_PER_BOX = "fldENIdfxbVn8YnPI"   # 박스당 제품수
TF_PROD_CBM     = "fldSBWylTZwGf1aEh"   # 박스 당 CBM (formula)

# Box dims
TF_BOX_W = "fld7qcdN496Gv4ul6"  # 가로
TF_BOX_D = "fldUX1YyqJL0TvTwl"  # 세로
TF_BOX_H = "fldIj302AgTAYMLbk"  # 높이
TMS_BOX_DIM_FIELDS = [TF_BOX_CODE, TF_BOX_NAME, TF_BOX_CBM, TF_BOX_W, TF_BOX_D, TF_BOX_H]

BOX_CBM = {
    "극소": 0.0098, "S280": 0.0098,
    "소":   0.0117, "S360": 0.0117,
    "중":   0.0201, "M350": 0.0201,
    "중대": 0.0492, "M480": 0.0492,
    "대":   0.1066, "L510": 0.1066,
    "특대": 0.1663, "L560": 0.1663,
}
BOX_SIZE_ORDER = ["극소", "소", "중", "중대", "대", "특대"]

PRODUCT_CBM = {
    "스펙트럼컬러펜":                    ("중",   300, 0.0201),
    "올블랙펜":                          ("중",   130, 0.0201),
    "슈가케인펜":                        ("중",   100, 0.0201),
    "플레인USB":                         ("중",   100, 0.0201),
    "브랜디드피규어키링":                ("중",   100, 0.0201),
    "홈카페코스터":                      ("중",   275, 0.0201),
    "밸류메모큐브(M)":                   ("중",    33, 0.0201),
    "레더스킨다이어리(표준)":            ("중대",  50, 0.0492),
    "슬로건다이어리(표준)":              ("중대",  50, 0.0492),
    "트리플컬러펜∣JETSTREAM":           ("중대", 413, 0.0492),
    "라이트샤오미펜":                    ("중대", 333, 0.0492),
    "커넥트6in1케이블키트":              ("중대", 150, 0.0492),
    "홀리데이네임택":                    ("중대", 200, 0.0492),
    "리멤버타투스티커":                  ("중대", 500, 0.0492),
    "버티컬무선충전패드":                ("중대", 100, 0.0492),
    "밸류무선충전마우스패드":            ("중대",  20, 0.0492),
    "브랜드스트랩단우산":                ("중대",  50, 0.0492),
    "유니크디퓨저":                      ("중대",  40, 0.0492),
    "오토매틱와인오프너":                ("중대",  19, 0.0492),
    "리마커블칫솔살균기":                ("중대", 100, 0.0492),
    "킵세이프마그넷배터리Max":           ("중대",  50, 0.0492),
    "킵세이프마그넷배터리Slim":          ("중대",  75, 0.0492),
    "더블업트래블파우치(Large)":         ("대",    50, 0.1066),
    "로고스트랩파우치(단품)":            ("대",   100, 0.1066),
    "포시즌블랭킷(무릎담요)":           ("대",    50, 0.1066),
    "미니멀스텐머그":                    ("대",    43, 0.1066),
    "미스트워터보틀":                    ("대",    47, 0.1066),
    "미르(MiiR)텀블러":                 ("대",    50, 0.1066),
    "메시지캐리어파우치":                ("대",    49, 0.1066),
    "올웨이즈양우산":                    ("중대",  80, 0.0492),
    "스탠리데일리텀블러":                ("대",    30, 0.1066),
    "핸디링미니선풍기":                  ("중대", 100, 0.0492),
    "스타트씨드키트":                    ("중대",  50, 0.0492),
    "톤앤톤쿨러백(단품)":               ("특대",  25, 0.1663),
    "브랜디드타월":                      ("대",    50, 0.1066),
    "Solid스탠다드G형박스(L사이즈)키트": ("대",    18, 0.1066),
    "Solid스탠다드G형박스(M사이즈)키트": ("대",    20, 0.1066),
    "브릭메모&캘린더스탠드2.0":         ("중대",  50, 0.0492),
}

_BOX_RE = re.compile(r"(극소|소|중대|중|대|특대|S280|S360|M350|M480|L510|L560)\s*(\d+)")


# ── TMS Airtable 조회 ─────────────────────────────────────────────────────────
def fetch_box_cbm_live() -> dict:
    url = f"https://api.airtable.com/v0/{TMS_BASE_ID}/{TMS_TABLE_BOX}"
    field_params = "&".join(f"fields[]={fid}" for fid in TMS_BOX_FIELDS)
    all_records, offset = [], None
    while True:
        params = {"pageSize": "100", "returnFieldsByFieldId": "true"}
        if offset:
            params["offset"] = offset
        resp = _get_with_retry(url, field_params, params, headers=_tms_headers())
        resp.raise_for_status()
        data = resp.json()
        all_records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.22)
    live = {}
    for rec in all_records:
        c = rec.get("cellValuesByFieldId") or rec.get("fields", {})
        for key in (c.get(TF_BOX_CODE), c.get(TF_BOX_NAME)):
            if key:
                live[str(key)] = c.get(TF_BOX_CBM) or 0
    return live


def fetch_boxes_with_dims() -> dict:
    url = f"https://api.airtable.com/v0/{TMS_BASE_ID}/{TMS_TABLE_BOX}"
    field_params = "&".join(f"fields[]={fid}" for fid in TMS_BOX_DIM_FIELDS)
    all_records, offset = [], None
    while True:
        params = {"pageSize": "100", "returnFieldsByFieldId": "true"}
        if offset:
            params["offset"] = offset
        resp = _get_with_retry(url, field_params, params, headers=_tms_headers())
        resp.raise_for_status()
        d = resp.json()
        all_records.extend(d.get("records", []))
        offset = d.get("offset")
        if not offset:
            break
        time.sleep(0.22)
    boxes = {}
    for rec in all_records:
        c = rec.get("cellValuesByFieldId") or rec.get("fields", {})
        name = c.get(TF_BOX_NAME) or c.get(TF_BOX_CODE) or ""
        if name:
            boxes[str(name)] = {
                "w": c.get(TF_BOX_W), "d": c.get(TF_BOX_D), "h": c.get(TF_BOX_H),
                "cbm": c.get(TF_BOX_CBM) or 0
            }
    return boxes


def fetch_products_tms() -> list:
    url = f"https://api.airtable.com/v0/{TMS_BASE_ID}/{TMS_TABLE_PRODUCT}"
    fields = [TF_PROD_NAME, TF_PROD_BOX, TF_PROD_PER_BOX, TF_PROD_CBM]
    field_params = "&".join(f"fields[]={fid}" for fid in fields)
    all_records, offset = [], None
    while True:
        params = {"pageSize": "100", "returnFieldsByFieldId": "true"}
        if offset:
            params["offset"] = offset
        resp = _get_with_retry(url, field_params, params, headers=_tms_headers())
        resp.raise_for_status()
        d = resp.json()
        all_records.extend(d.get("records", []))
        offset = d.get("offset")
        if not offset:
            break
        time.sleep(0.22)
    result = []
    for rec in all_records:
        c = rec.get("cellValuesByFieldId") or rec.get("fields", {})
        name = c.get(TF_PROD_NAME) or ""
        box_sel = c.get(TF_PROD_BOX)
        box_name = box_sel["name"] if isinstance(box_sel, dict) else (box_sel or "")
        per_box = c.get(TF_PROD_PER_BOX) or 0
        cbm = c.get(TF_PROD_CBM) or 0
        if name and per_box:
            result.append({"name": name, "box_name": box_name, "per_box": per_box, "cbm_per_box": cbm})
    return sorted(result, key=lambda x: x["name"])


def fetch_shipments_tms(start: date, end: date) -> list:
    url = f"https://api.airtable.com/v0/{TMS_BASE_ID}/{TMS_TABLE_SHIPMENT}"
    formula = (
        f"AND("
        f"IS_AFTER({{{TF_DATE}}}, DATEADD('{start.isoformat()}', -1, 'days')), "
        f"IS_BEFORE({{{TF_DATE}}}, DATEADD('{end.isoformat()}', 1, 'days'))"
        f")"
    )
    field_params = "&".join(f"fields[]={fid}" for fid in TMS_SHIP_FIELDS)
    all_records, offset = [], None
    while True:
        params = {"filterByFormula": formula, "pageSize": "100", "returnFieldsByFieldId": "true"}
        if offset:
            params["offset"] = offset
        resp = _get_with_retry(url, field_params, params, headers=_tms_headers())
        resp.raise_for_status()
        data = resp.json()
        all_records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.22)
    return all_records


def _parse_box_cbm(box_str: str, live: dict):
    ref = {**BOX_CBM, **live}
    total = 0.0
    by_type = {}
    for m in _BOX_RE.finditer(box_str):
        btype, cnt = m.group(1), int(m.group(2))
        total += ref.get(btype, 0) * cnt
        norm = next((k for k in BOX_CBM if k == btype), btype)
        by_type[norm] = by_type.get(norm, 0) + cnt
    return round(total, 4), by_type


def _estimate_cbm_from_items(item_str: str) -> float:
    total = 0.0
    for line in item_str.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        for pname, (_, qpb, cpb) in sorted(PRODUCT_CBM.items(), key=lambda x: -len(x[0])):
            if pname in line:
                nums = re.findall(r"\d+", line.replace(pname, ""))
                if nums:
                    total += math.ceil(int(nums[0]) / qpb) * cpb
                break
    return round(total, 4)


def analyze_shipment(records: list, live_cbm: dict) -> dict:
    box_type_all = defaultdict(int)
    item_agg     = defaultdict(lambda: {"qty": 0, "cbm": 0.0})
    by_date      = defaultdict(lambda: {"cnt": 0, "cbm": 0.0})
    partner_agg: dict = defaultdict(int)
    total_cbm = 0.0
    total_cnt = completed = pending = 0

    for rec in records:
        c = rec.get("cellValuesByFieldId") or rec.get("fields", {})
        if not c.get(TF_DATE):
            continue
        total_cnt += 1
        date_val = c.get(TF_DATE, "")

        status_obj = c.get(TF_STATUS)
        status = (status_obj["name"] if isinstance(status_obj, dict) else (status_obj or ""))
        if "완료" in status:
            completed += 1
        else:
            pending += 1

        total_cbm_field = c.get(TF_TOTAL_CBM)
        box_qty = c.get(TF_BOX_PARSED) or c.get(TF_BOX_MANUAL) or ""
        if isinstance(box_qty, list):
            box_qty = ", ".join(str(x) for x in box_qty)
        box_qty = str(box_qty).strip()

        cbm_val = 0.0
        if box_qty and _BOX_RE.search(box_qty):
            parsed_cbm, btype_counts = _parse_box_cbm(box_qty, live_cbm)
            cbm_val = total_cbm_field if (total_cbm_field and total_cbm_field > 0) else parsed_cbm
            for bt, cnt in btype_counts.items():
                box_type_all[bt] += cnt
        elif total_cbm_field and total_cbm_field > 0:
            cbm_val = total_cbm_field
        else:
            item_str = c.get(TF_ITEM) or c.get(TF_ITEM_DETAIL) or ""
            if item_str:
                cbm_val = _estimate_cbm_from_items(str(item_str))

        total_cbm = round(total_cbm + cbm_val, 4)
        if date_val:
            by_date[date_val]["cnt"] += 1
            by_date[date_val]["cbm"] = round(by_date[date_val]["cbm"] + cbm_val, 4)

        # 품목 집계
        item_str = str(c.get(TF_ITEM) or "")
        for line in item_str.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            nums  = re.findall(r"\d+", line)
            iname = re.sub(r"\s*\d+\s*$", "", line).strip()
            if iname and nums:
                qty = int(nums[-1])
                item_agg[iname]["qty"] += qty
                for pname, (_, qpb, cpb) in sorted(PRODUCT_CBM.items(), key=lambda x: -len(x[0])):
                    if pname in iname:
                        item_agg[iname]["cbm"] = round(
                            item_agg[iname]["cbm"] + math.ceil(qty / qpb) * cpb, 4
                        )
                        break

        # 배송파트너 집계
        partner_field = c.get(TF_PARTNER)
        if partner_field and isinstance(partner_field, dict):
            vals = partner_field.get("valuesByLinkedRecordId", {})
            for v_list in vals.values():
                for v in v_list:
                    partner_agg[str(v)] += 1

    total_boxes = sum(box_type_all.values())
    box_pct = {k: round(v / total_boxes * 100, 1) for k, v in box_type_all.items()} if total_boxes else {}
    ordered_counts = {k: box_type_all[k] for k in BOX_SIZE_ORDER if k in box_type_all}
    ordered_pct    = {k: box_pct[k]      for k in BOX_SIZE_ORDER if k in box_pct}

    top_items = sorted(
        [{"name": name, "qty": v["qty"], "cbm": round(v["cbm"], 3)}
         for name, v in item_agg.items() if v["cbm"] > 0],
        key=lambda x: -x["cbm"]
    )[:8]

    return {
        "box_type": {"counts": ordered_counts, "pct": ordered_pct, "total": total_boxes},
        "top_items": top_items,
        "by_date":  dict(sorted(by_date.items())),
        "partners": [
            {"name": k, "cnt": v}
            for k, v in sorted(partner_agg.items(), key=lambda x: -x[1])
        ],
        "summary": {
            "total_cbm":        round(total_cbm, 3),
            "total_count":      total_cnt,
            "completed":        completed,
            "pending":          pending,
            "cbm_per_shipment": round(total_cbm / total_cnt, 3) if total_cnt else 0,
        },
    }


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
        c = r.get("cellValuesByFieldId") or r.get("fields", {})
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
        if (r.get("cellValuesByFieldId") or r.get("fields", {}).get(F_QC_QTY) or 0) > 0
        or r.get("cellValuesByFieldId") or r.get("fields", {}).get(F_QC_RES)
    ]
    total_qc = total_defect = 0
    result_dist = defaultdict(int)
    by_week = defaultdict(lambda: {"qc_qty": 0, "defect": 0})
    item_acc = defaultdict(lambda: {"qc_qty": 0, "defect": 0})

    for r in qc_recs:
        c = r.get("cellValuesByFieldId") or r.get("fields", {})
        if c.get(F_CANCEL):
            continue
        qc_qty   = c.get(F_QC_QTY) or 0
        defect   = (c.get(F_DEFECT_S) or 0) + (c.get(F_DEFECT_F) or 0)
        res      = _sel(c.get(F_QC_RES, {}))
        date_val = c.get(F_IN_DATE, "")
        item_name = (c.get(F_ITEM_NAME) or c.get(F_ITEM_ALT) or "미분류").strip()

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
        if qc_qty > 0 or defect > 0:
            item_acc[item_name]["qc_qty"] += qc_qty
            item_acc[item_name]["defect"] += defect

    defect_rate = round(total_defect / total_qc * 100, 2) if total_qc else 0.0
    bw = {}
    for wk, v in sorted(by_week.items()):
        dr = round(v["defect"] / v["qc_qty"] * 100, 1) if v["qc_qty"] > 0 else 0.0
        bw[wk] = {**v, "defect_rate": dr}

    defect_by_item = sorted(
        [{"name": k, "qc_qty": v["qc_qty"], "defect": v["defect"],
          "defect_rate": round(v["defect"] / v["qc_qty"] * 100, 2) if v["qc_qty"] else 0.0}
         for k, v in item_acc.items() if v["defect"] > 0],
        key=lambda x: x["defect"], reverse=True
    )

    return {
        "summary": {
            "qc_cnt":        len(qc_recs),
            "total_qc_qty":  total_qc,
            "total_defect":  total_defect,
            "defect_rate":   defect_rate,
            "target_met":    defect_rate <= 1.0,
        },
        "by_week":       bw,
        "result_dist":   dict(result_dist),
        "defect_by_item": defect_by_item,
    }

def analyze_material(records):
    has_stock = [r for r in records if (r.get("cellValuesByFieldId") or r.get("fields", {}).get(F_MAT_PHYS) or 0) > 0]
    total = len(has_stock)
    match = neg_avail = check_done = 0
    total_phys = total_avail = 0

    for r in has_stock:
        c = r.get("cellValuesByFieldId") or r.get("fields", {})
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

    # 모드별 period label & period_key (히스토리 파일명용)
    if REPORT_MODE == "monthly":
        period_label = start.strftime("%Y년 %m월") + " (지난달)"
        period_key   = start.strftime("%Y-%m") + "_monthly"
        week_lbl = ""
    elif REPORT_MODE == "weekly_forecast":
        period_label = this_w_label + " 예측"
        period_key   = this_w_start.strftime("%Y-W%V") + "_forecast"
        week_lbl = this_w_label
    else:  # weekly_review
        period_label = last_w_label + " 실적"
        period_key   = start.strftime("%Y-W%V") + "_review"
        week_lbl = last_w_label

    print("[generate] TMS 출하 조회 중...")
    try:
        live_cbm     = fetch_box_cbm_live()
        ship_records = fetch_shipments_tms(start, end)
        print(f"[generate] TMS 출하: {len(ship_records)}건")
        shipment = analyze_shipment(ship_records, live_cbm)
    except Exception as e:
        print(f"[generate] TMS 출하 조회 실패 (무시): {e}")
        shipment = None

    print("[generate] TMS Product/Box 조회 중...")
    try:
        boxes_data    = fetch_boxes_with_dims()
        products_data = fetch_products_tms()
        print(f"[generate] Products: {len(products_data)}건  Boxes: {len(boxes_data)}건")
    except Exception as e:
        print(f"[generate] TMS Product/Box 조회 실패 (무시): {e}")
        boxes_data, products_data = {}, []

    pages_data = {
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "report_mode":  REPORT_MODE,
        "period_key":   period_key,
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
    if shipment:
        pages_data["shipment"] = shipment
    pages_data["products"] = products_data
    pages_data["boxes"]    = boxes_data

    # 예측 모드일 때만 forecast 섹션 추가
    if REPORT_MODE == "weekly_forecast":
        pages_data["forecast"] = build_forecast(inbound, qc, material, this_w_start, this_w_end)

    out_path = "pages_data.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(pages_data, f, ensure_ascii=False, indent=2, default=str)
    print(f"[generate] pages_data.json 생성 완료 (period_key: {period_key})")
    print(f"  입하완료율: {inb_s['completion_rate']}%  불량률: {qc_s['defect_rate']}%  재고정확도: {mat_s['accuracy']}%")
    if shipment:
        sh_s = shipment["summary"]
        print(f"  [출하] {sh_s['total_count']}건  총CBM: {sh_s['total_cbm']}m³  완료: {sh_s['completed']}건  대기: {sh_s['pending']}건")
    if REPORT_MODE == "weekly_forecast":
        fc = pages_data["forecast"]
        print(f"  [예측] 이번주 입고 예상: {fc['projected']['inbound_cnt']}건 / 리스크: {fc['kpi_assessment']['risk_level']}")

if __name__ == "__main__":
    if not AIRTABLE_API_KEY_WMS:
        print("ERROR: AIRTABLE_PAT 환경변수 없음", file=sys.stderr)
        sys.exit(1)
    main()
