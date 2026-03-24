"""
Sincerely SCM 통합 리포트 생성기
======================================================
REPORT_MODE=weekly_review   매주 월요일 - WMS 지난주 실적 + TMS 출하 주간
REPORT_MODE=weekly_forecast 매주 월요일 - WMS 기반 이번주 예측
REPORT_MODE=monthly         매월 1일   - WMS + TMS 월간 실적

생성 파일:
  pages_data.json               -> dashboard.html (4탭 통합)
  docs/weekly.html              -> 주간 TMS 전용 리포트 (JSON 주입)
  docs/monthly.html             -> 월간 TMS 전용 리포트 (JSON 주입)

환경변수:
  AIRTABLE_API_KEY_WMS   WMS Airtable PAT
  AIRTABLE_API_KEY_TMS   TMS Airtable PAT
  AIRTABLE_BASE_WMS_ID   WMS base ID
  AIRTABLE_BASE_TMS_ID   TMS base ID (기본: app4x70a8mOrIKsMf)
  KAKAO_REST_API_KEY     카카오 REST API 키 (라우팅 km, 없으면 스킵)
  REPORT_MODE            리포트 모드
  SKIP_DELAY             1이면 랜덤 지연 없음
"""

import os, json, re, time, random, math, sys, pathlib
from datetime import datetime, timedelta, date
from collections import defaultdict

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests

# ================================================================
# 환경변수
# ================================================================
WMS_KEY     = os.environ.get("AIRTABLE_API_KEY_WMS") or os.environ.get("AIRTABLE_PAT", "")
TMS_KEY     = os.environ.get("AIRTABLE_API_KEY_TMS") or WMS_KEY
WMS_BASE_ID = os.environ.get("AIRTABLE_BASE_WMS_ID") or os.environ.get("AIRTABLE_BASE_ID", "appLui4ZR5HWcQRri")
TMS_BASE_ID = os.environ.get("AIRTABLE_BASE_TMS_ID", "app4x70a8mOrIKsMf")
REPORT_MODE = os.environ.get("REPORT_MODE", "weekly_review")
KAKAO_KEY   = os.environ.get("KAKAO_REST_API_KEY", "")

# ================================================================
# WMS Field IDs
# ================================================================
TABLE_MOVEMENT = "tblwq7Kj5Y9nVjlOw"
TABLE_MATERIAL = "tblaRpZstW10EwDlo"

F_PURPOSE   = "fldFRNxG1pNooEOC7"
F_IN_QTY    = "fldV8kVokQqMIsif0"
F_IN_DATE   = "flduN8khmYwdn7uVD"
F_IN_STATUS = "fld4Yq9LYX46zC5m5"
F_STOCK_QTY = "fldlJt3RPY6E8JB4G"
F_QC_QTY    = "fldnrqmT56niE7O21"
F_DEFECT_S  = "fld3lQvblfrqTl4O8"
F_DEFECT_F  = "fldsTXzxUeerw4qw2"
F_QC_RES    = "fldKrjj58HnHKT4SJ"
F_CANCEL    = "fldwgaM8OnKubM8oE"
F_ITEM_NAME     = "fldws6Ohz68i3GBPR"
F_ITEM_ALT      = "fldwZKCYZ4IFOigRp"
F_NOT_RECV_HIST = "fldjZYoxIe1GI4DGa"
F_SHIP_FROM     = "fldz7ZLrZw7inalHz"
F_ISSUE_CAT     = "fldudxogG53VjQmvX"   # 이슈카테고리 (multipleSelects)
F_QC_ISSUE_FLAG = "fld9eE4YZZWTDsfUC"   # 품질 이슈 리포팅 (checkbox)
F_OPS_ISSUE_FLAG= "fldVJnnvOYW2vR4ur"   # 운영이슈 (checkbox)
F_QTY_ISSUE_FLAG= "fld6XIcRIu6HTePBL"   # 수량이슈공유 (checkbox)
F_MAT_NAME  = "fld7Pfip5zbBTaTdR"
F_MAT_PHYS  = "fld5XQQv2P9YJZP6n"
F_MAT_SYS   = "fldAFkM4HtGJsitOk"
F_MAT_AVAIL = "fldZ5qLZKp0yy28So"
F_MAT_LOC   = "fldsDSdkogmJ0qsVC"
F_MAT_CHECK = "flddQhs9cuA6G8xmq"

MOVEMENT_FIELDS = [F_PURPOSE,F_IN_QTY,F_IN_DATE,F_IN_STATUS,F_STOCK_QTY,
                   F_QC_QTY,F_DEFECT_S,F_DEFECT_F,F_QC_RES,F_CANCEL,
                   F_ITEM_NAME,F_ITEM_ALT,F_NOT_RECV_HIST,F_SHIP_FROM,
                   F_ISSUE_CAT,F_QC_ISSUE_FLAG,F_OPS_ISSUE_FLAG,F_QTY_ISSUE_FLAG]
MATERIAL_FIELDS = [F_MAT_NAME,F_MAT_PHYS,F_MAT_SYS,F_MAT_AVAIL,F_MAT_LOC,F_MAT_CHECK]

# ================================================================
# TMS Field IDs
# ================================================================
TMS_TABLE_SHIPMENT = "tbllg1JoHclGYer7m"
TMS_TABLE_BOX      = "tbltwH7bHk41rTzhM"
TMS_TABLE_PRODUCT  = "tblBNh6oGDlTKGrdQ"

TF_DATE        = "fldQvmEwwzvQW95h9"
TF_ITEM        = "fldgSupj5XLjJXYQo"
TF_BOX_PARSED  = "fldTjLDmw5sNGszeD"
TF_BOX_MANUAL  = "fldRjMaXa5TdSsGDL"
TF_TOTAL_CBM   = "fldJ9DHjwoRyeUEqE"
TF_STATUS      = "fldOhibgxg6LIpRTi"
TF_ITEM_DETAIL = "fldXXnGOXkm90snKn"
TF_REVENUE     = "fldOFuvqBT0iXItcT"
TF_COST        = "fldRT95SC88KSBATT"
TF_PARTNER     = "fldHZ7yMT3KEu2gSj"
TF_DEPARTURE   = "fldGZyp4KJNCSWWUr"
TF_SLOT        = "fldcSrlxCngYQHtSV"
TF_ADDRESS     = "fldyJHUh9gN44Ggnh"
TF_WISH_TIME   = "fldFweNu3dASPv93N"

TMS_SHIP_FIELDS = [TF_DATE,TF_ITEM,TF_BOX_PARSED,TF_BOX_MANUAL,TF_TOTAL_CBM,
                   TF_STATUS,TF_ITEM_DETAIL,TF_REVENUE,TF_COST,TF_PARTNER,TF_DEPARTURE,
                   TF_ADDRESS,TF_SLOT,TF_WISH_TIME]  # 버그픽스: 라우팅 주소/슬롯 필드 추가
TMS_BOX_FIELDS  = ["fldELrd8bBVjQCHnp","fldgvlGjLb4FTlQ0v","fldjFaXiYzeJ2Zt7M"]
TMS_PROD_FIELDS = ["fldx01uKEnCd0J0nP","fldN1JrkxIr5m6pXz","fld6W5ImO7UeBVMPI"]

BOX_CBM = {
    "극소":0.0098,"S280":0.0098,"소":0.0117,"S360":0.0117,
    "중":0.0201,"M350":0.0201,"중대":0.0492,"M480":0.0492,
    "대":0.1066,"L510":0.1066,"특대":0.1663,"L560":0.1663,
}
BOX_SIZE_ORDER = ["극소","소","중","중대","대","특대"]

VEHICLE_CBM = {
    "신시어리 (이장훈)": 5.4,
    "신시어리 (조희선)": 7.6,
    "신시어리 (박종성)": 9.5,
}
A1_WAREHOUSE_CBM = 44.4
WD_KR = ["월","화","수","목","금","토","일"]
_BOX_RE = re.compile(r"(극소|소|중대|중|대|특대|S280|S360|M350|M480|L510|L560)\s*(\d+)")

PARTNER_GROUP = {
    "신시어리 (이장훈)":"신시어리 기사님 (이장훈)",
    "신시어리 (박종성)":"신시어리 기사님 (박종성)",
    "신시어리 (조희선)":"신시어리 기사님 (조희선)",
    "신시어리 (로젠)":"로젠 택배",
    "고객":"고객 직접수령",
}

SINCERELY_DRIVERS = list(VEHICLE_CBM.keys())

# ================================================================
# 날짜 유틸
# ================================================================
def last_week_range():
    today = date.today()
    mon = today - timedelta(days=today.weekday()+7)
    return mon, mon+timedelta(days=4)

def this_week_range():
    today = date.today()
    mon = today - timedelta(days=today.weekday())
    return mon, mon+timedelta(days=4)

def next_week_range():
    mon, _ = this_week_range()
    nmon = mon+timedelta(weeks=1)
    return nmon, nmon+timedelta(days=4)

def prev_week_range(offset=1):
    mon, _ = this_week_range()
    pmon = mon - timedelta(weeks=offset)
    return pmon, pmon+timedelta(days=4)

def prev_month_range():
    today = date.today()
    first = today.replace(day=1)
    last  = first - timedelta(days=1)
    return last.replace(day=1), last

def week_label_for(d):
    return f"W{d.isocalendar()[1]} ({d.month}/{d.day}~)"

def week_number_of_month(d):
    return (d.day-1)//7+1

def get_period_range():
    if REPORT_MODE == "monthly":
        return prev_month_range()
    else:
        return last_week_range()

# ================================================================
# Airtable HTTP 헬퍼
# ================================================================
def _wms_headers():
    return {"Authorization": f"Bearer {WMS_KEY}"}

def _tms_headers():
    return {"Authorization": f"Bearer {TMS_KEY}"}

def _get_with_retry(url, field_params, params, headers, max_retries=3):
    for attempt in range(max_retries):
        try:
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            full_url = f"{url}?{field_params}&{qs}" if field_params else f"{url}?{qs}"
            resp = requests.get(full_url, headers=headers, timeout=30)
            if resp.status_code == 429:
                time.sleep(30)
                continue
            return resp
        except Exception:
            if attempt < max_retries-1:
                time.sleep(2**attempt)
    raise RuntimeError(f"fetch 실패: {url}")

def _fetch_all(url, field_params, extra_params, headers):
    all_recs, offset = [], None
    while True:
        params = {"pageSize":"100","returnFieldsByFieldId":"true", **extra_params}
        if offset:
            params["offset"] = offset
        resp = _get_with_retry(url, field_params, params, headers)
        resp.raise_for_status()
        d = resp.json()
        all_recs.extend(d.get("records",[]))
        offset = d.get("offset")
        if not offset:
            break
        time.sleep(0.22)
    return all_recs

def _c(rec):
    return rec.get("cellValuesByFieldId") or rec.get("fields",{})

# ================================================================
# WMS Airtable 조회
# ================================================================
def fetch_movement(start, end):
    url = f"https://api.airtable.com/v0/{WMS_BASE_ID}/{TABLE_MOVEMENT}"
    fp  = "&".join(f"fields[]={f}" for f in MOVEMENT_FIELDS)
    formula = (f"AND(IS_AFTER({{{F_IN_DATE}}},DATEADD('{start.isoformat()}',-1,'days')),"
               f"IS_BEFORE({{{F_IN_DATE}}},DATEADD('{end.isoformat()}',1,'days')))")
    return _fetch_all(url, fp, {"filterByFormula":formula}, _wms_headers())

def fetch_material():
    url = f"https://api.airtable.com/v0/{WMS_BASE_ID}/{TABLE_MATERIAL}"
    fp  = "&".join(f"fields[]={f}" for f in MATERIAL_FIELDS)
    return _fetch_all(url, fp, {}, _wms_headers())

# ================================================================
# TMS Airtable 조회
# ================================================================
def fetch_shipments_tms(start, end):
    url = f"https://api.airtable.com/v0/{TMS_BASE_ID}/{TMS_TABLE_SHIPMENT}"
    fp  = "&".join(f"fields[]={f}" for f in TMS_SHIP_FIELDS)
    formula = (f"AND(IS_AFTER({{{TF_DATE}}},DATEADD('{start.isoformat()}',-1,'days')),"
               f"IS_BEFORE({{{TF_DATE}}},DATEADD('{end.isoformat()}',1,'days')))")
    return _fetch_all(url, fp, {"filterByFormula":formula}, _tms_headers())

def fetch_box_cbm_live():
    url = f"https://api.airtable.com/v0/{TMS_BASE_ID}/{TMS_TABLE_BOX}"
    fp  = "&".join(f"fields[]={f}" for f in TMS_BOX_FIELDS)
    recs = _fetch_all(url, fp, {}, _tms_headers())
    live = {}
    for rec in recs:
        c = _c(rec)
        for key in (c.get("fldELrd8bBVjQCHnp"), c.get("fldgvlGjLb4FTlQ0v")):
            if key: live[key] = c.get("fldjFaXiYzeJ2Zt7M") or 0
    return live

def fetch_product_cbm():
    url = f"https://api.airtable.com/v0/{TMS_BASE_ID}/{TMS_TABLE_PRODUCT}"
    fp  = "&".join(f"fields[]={f}" for f in TMS_PROD_FIELDS)
    recs = _fetch_all(url, fp, {}, _tms_headers())
    result = []
    for rec in recs:
        c    = _c(rec)
        name = (c.get("fldx01uKEnCd0J0nP") or "").strip()
        cbm  = c.get("fldN1JrkxIr5m6pXz") or c.get("fld6W5ImO7UeBVMPI") or None
        if name and cbm:
            try: result.append((re.sub(r"\s+","",name), float(cbm)))
            except (ValueError,TypeError): pass
    result.sort(key=lambda x:-len(x[0]))
    print(f"  Product CBM: {len(result)}개")
    return result

# ================================================================
# CBM 파싱
# ================================================================
def parse_box_cbm(box_str, live):
    ref = {**BOX_CBM, **live}
    total, by_type = 0.0, {}
    for m in _BOX_RE.finditer(box_str):
        btype, cnt = m.group(1), int(m.group(2))
        total += ref.get(btype,0)*cnt
        norm = next((k for k in BOX_CBM if k==btype), btype)
        by_type[norm] = by_type.get(norm,0)+cnt
    return round(total,4), by_type

def match_cbm_from_product(item_str, product_cbm):
    total, matched = 0.0, False
    for line in item_str.strip().splitlines():
        line=line.strip()
        if not line: continue
        norm=re.sub(r"\s+","",line)
        nums=re.findall(r"\d+",norm)
        for prod_norm,cpb in product_cbm:
            if prod_norm in norm:
                total+=cpb*(int(nums[-1]) if nums else 1)
                matched=True; break
    return round(total,4) if matched else 0.0

def get_cbm_tms(f, live, product_cbm=None):
    """
    CBM 우선순위: Total_CBM(수동) > 박스파싱 > 0 (unmatched)
    
    버그 수정: product_match 제거.
    이유: 품목문자열의 수량(qty)은 개수(EA)이지 박스 수가 아님.
    cbm_per_box × qty(개수)로 계산하면 수량이 클 때 CBM이 수십~수백배 뻥튀기됨.
    예) 브릭메모 1000개 × 0.05m³/박스 = 50m³ (실제는 ~1m³)
    product_cbm은 top_items 표시용 item_agg에서만 사용.
    """
    v = f.get(TF_TOTAL_CBM)
    if v and v>0: return float(v), "manual"
    box = f.get(TF_BOX_PARSED) or f.get(TF_BOX_MANUAL) or ""
    if isinstance(box,list): box=", ".join(str(x) for x in box)
    box=box.strip()
    if box and _BOX_RE.search(box):
        cv, _ = parse_box_cbm(box, live)
        return cv, "box_parse"
    return 0.0, "unmatched"

# ================================================================
# WMS 분석 함수
# ================================================================
def _sel(val):
    if isinstance(val, dict): return val.get("name","")
    return str(val) if val else ""

def analyze_inbound(records):
    total_cnt=total_in_qty=total_stock_qty=completed=unconfirmed=0
    by_date=defaultdict(lambda:{"cnt":0,"in_qty":0})
    by_week=defaultdict(lambda:{"cnt":0,"in_qty":0})
    by_purpose=defaultdict(lambda:{"cnt":0,"qty":0})
    not_recv=defaultdict(int)
    for r in records:
        c=_c(r)
        in_qty=c.get(F_IN_QTY) or 0
        stock_qty=c.get(F_STOCK_QTY) or 0
        date_val=c.get(F_IN_DATE,"")
        stat=_sel(c.get(F_IN_STATUS,{}))
        purpose=_sel(c.get(F_PURPOSE,{})) or "미분류"
        total_in_qty+=in_qty; total_stock_qty+=stock_qty; total_cnt+=1
        if stat=="입하완료": completed+=1
        elif not stat: unconfirmed+=1
        if c.get(F_NOT_RECV_HIST):
            not_recv[c.get(F_SHIP_FROM) or "미상"]+=1
        if date_val:
            by_date[date_val]["cnt"]+=1
            by_date[date_val]["in_qty"]+=in_qty
            try:
                d=datetime.strptime(date_val,"%Y-%m-%d")
                wk=f"{d.year}-W{d.isocalendar()[1]:02d}"
                by_week[wk]["cnt"]+=1; by_week[wk]["in_qty"]+=in_qty
            except Exception: pass
        by_purpose[purpose]["cnt"]+=1; by_purpose[purpose]["qty"]+=in_qty
    comp_rate=round(completed/total_cnt*100,1) if total_cnt else 0
    return {
        "summary":{"total_cnt":total_cnt,"total_in_qty":total_in_qty,"total_stock_qty":total_stock_qty,
                   "completed":completed,"unconfirmed":unconfirmed,"completion_rate":comp_rate},
        "by_date":dict(sorted(by_date.items())),
        "by_week":dict(sorted(by_week.items())),
        "by_purpose":dict(by_purpose),
        "not_recv_by_partner":dict(sorted(not_recv.items(),key=lambda x:-x[1])),
    }

def analyze_qc(records):
    """
    검수 로직 반영:
    - 검수 건수 = 전체 입하건수 (표본 검수 방식이므로 모든 건에 대해 검수 진행)
    - 검수 수량 = 전체 입하수량의 7.5% (5~10% 표본 검수 비율 중간값)
    - 불량 수량/불량률은 실제 QC 기록에서 집계
    - 이슈카테고리 집계 (수량이슈/품질이슈/운영이슈)
    """
    total_cnt = len(records)  # 전체 입하건수 = 검수 건수
    total_in_qty = sum((_c(r).get(F_IN_QTY) or 0) for r in records)
    sample_rate = 0.075        # 5~10% 표본 검수 중간값 7.5%
    total_qc_qty = int(total_in_qty * sample_rate)

    total_defect = 0
    actual_qc_cnt = 0
    by_week = defaultdict(lambda:{"cnt":0,"qc_qty":0,"defect":0,"defect_rate":0.0})
    defect_by_item = defaultdict(lambda:{"qc_qty":0,"defect":0})
    result_dist = defaultdict(int)

    # 이슈카테고리 집계
    issue_cnt = 0
    issue_cat_counts = defaultdict(int)

    for r in records:
        c = _c(r)
        in_qty = c.get(F_IN_QTY) or 0
        qc_qty = c.get(F_QC_QTY) or 0
        defect_s = c.get(F_DEFECT_S) or 0
        defect_f = c.get(F_DEFECT_F) or 0
        defect = defect_s + defect_f
        total_defect += defect
        if qc_qty > 0:
            actual_qc_cnt += 1
        qc_res = _sel(c.get(F_QC_RES, {})) or "수량 정상"
        result_dist[qc_res] += 1

        # 이슈카테고리
        cats = c.get(F_ISSUE_CAT) or []
        if cats:
            issue_cnt += 1
            for cat in cats:
                cat_name = _sel(cat) if isinstance(cat, dict) else str(cat)
                if cat_name:
                    issue_cat_counts[cat_name] += 1

        date_val = c.get(F_IN_DATE, "")
        if date_val:
            try:
                d = datetime.strptime(date_val, "%Y-%m-%d")
                wk = f"W{d.isocalendar()[1]}"
                by_week[wk]["cnt"] += 1
                by_week[wk]["qc_qty"] += int(in_qty * sample_rate)
                by_week[wk]["defect"] += defect
            except Exception: pass
        item_name = _sel(c.get(F_ITEM_NAME)) or _sel(c.get(F_ITEM_ALT)) or ""
        if item_name and defect > 0:
            defect_by_item[item_name]["qc_qty"] += max(qc_qty, int(in_qty * sample_rate))
            defect_by_item[item_name]["defect"] += defect

    for wk in by_week:
        q = by_week[wk]["qc_qty"]
        d = by_week[wk]["defect"]
        by_week[wk]["defect_rate"] = round(d / q * 100, 2) if q else 0.0

    defect_rate = round(total_defect / total_qc_qty * 100, 2) if total_qc_qty else 0.0
    defect_items = sorted(
        [{"name": k, "qc_qty": v["qc_qty"], "defect": v["defect"],
          "defect_rate": round(v["defect"] / v["qc_qty"] * 100, 2) if v["qc_qty"] else 0}
         for k, v in defect_by_item.items()], key=lambda x: -x["defect_rate"])[:10]

    return {
        "summary": {
            "qc_cnt": total_cnt,           # 검수 건수 = 전체 입하건수
            "total_qc_qty": total_qc_qty,  # 검수 수량 = 입하수량 × 7.5%
            "sample_rate": sample_rate,
            "actual_qc_cnt": actual_qc_cnt, # 실제 QC 기록 건수
            "total_defect": total_defect,
            "defect_rate": defect_rate,
            "target_met": defect_rate <= 1.0,
        },
        "by_week": dict(sorted(by_week.items())),
        "result_dist": dict(result_dist),
        "defect_by_item": defect_items,
        "issue_summary": {
            "total_cnt": total_cnt,
            "issue_cnt": issue_cnt,
            "cat_counts": dict(issue_cat_counts),
        },
    }

def analyze_material(records):
    total=mismatch=neg_avail=check_done=0
    total_phys=0
    for r in records:
        c=_c(r)
        phys=c.get(F_MAT_PHYS) or 0
        sys_v=c.get(F_MAT_SYS) or 0
        avail=c.get(F_MAT_AVAIL) or 0
        chk=c.get(F_MAT_CHECK) or False
        total+=1; total_phys+=phys
        if phys!=sys_v: mismatch+=1
        if avail<0: neg_avail+=1
        if chk: check_done+=1
    accuracy=round((total-mismatch)/total*100,1) if total else 100.0
    check_rate=round(check_done/total*100,1) if total else 0.0
    return {"summary":{"total":total,"total_phys":total_phys,"mismatch":mismatch,
                       "accuracy":accuracy,"neg_avail":neg_avail,"check_done":check_done,
                       "check_rate":check_rate}}

# ================================================================
# TMS 분석 함수 (주간 / 월간 공용)
# ================================================================
def analyze_tms(records, live_cbm, product_cbm=None):
    by_date     = defaultdict(lambda:{"cnt":0,"cbm":0.0,"completed":0,"pending":0,"revenue":0.0,"cost":0.0})
    box_type_all= defaultdict(int)
    item_agg    = defaultdict(lambda:{"qty":0,"cbm":0.0})
    partner_agg = defaultdict(int)
    partner_cbm_agg = defaultdict(float)
    cbm_sources = {"manual":0,"product_match":0,"box_parse":0,"unmatched":0}
    driver_daily  = defaultdict(lambda:defaultdict(float))
    driver_weekly = defaultdict(float)
    missing_box=same_day=0
    leadtimes=[]
    total_cbm=total_rev=total_cost=0.0
    total_cnt=completed=pending=0

    for rec in records:
        f=_c(rec)
        d_s=f.get(TF_DATE,"")
        if not d_s: continue
        total_cnt+=1
        ship_date=date.fromisoformat(d_s)

        status_obj=f.get(TF_STATUS)
        status=status_obj["name"] if isinstance(status_obj,dict) else (status_obj or "")
        if "완료" in status: completed+=1
        else: pending+=1

        rev=f.get(TF_REVENUE) or 0
        cost=f.get(TF_COST) or 0
        total_rev+=rev; total_cost+=cost

        cbm_val, src = get_cbm_tms(f, live_cbm, product_cbm)
        cbm_sources[src]+=1

        box_qty=f.get(TF_BOX_PARSED) or f.get(TF_BOX_MANUAL) or ""
        if isinstance(box_qty,list): box_qty=", ".join(str(x) for x in box_qty)
        box_qty=box_qty.strip()
        if not box_qty or not _BOX_RE.search(box_qty): missing_box+=1
        if box_qty and _BOX_RE.search(box_qty) and src=="box_parse":
            _, btype_counts = parse_box_cbm(box_qty, live_cbm)
            for bt,cnt in btype_counts.items():
                box_type_all[bt]+=cnt

        total_cbm=round(total_cbm+cbm_val,4)
        bkt=by_date[d_s]
        bkt["cnt"]+=1; bkt["cbm"]=round(bkt["cbm"]+cbm_val,4)
        bkt["revenue"]+=rev; bkt["cost"]+=cost
        if "완료" in status: bkt["completed"]+=1
        else: bkt["pending"]+=1

        # 기사님 집계
        pf=f.get(TF_PARTNER)
        pname=None
        if isinstance(pf,dict):
            for vals in pf.get("valuesByLinkedRecordId",{}).values():
                if vals: pname=vals[0]; break
        elif isinstance(pf,list) and pf: pname=str(pf[0])
        elif pf: pname=str(pf)
        if pname:
            display=PARTNER_GROUP.get(pname,pname)
            partner_agg[display]+=1
            partner_cbm_agg[display]=round(partner_cbm_agg[display]+cbm_val,4)
            if pname in VEHICLE_CBM:
                driver_daily[pname][d_s]=round(driver_daily[pname][d_s]+cbm_val,4)
                driver_weekly[pname]=round(driver_weekly[pname]+cbm_val,4)

        # 품목 집계
        item_str=f.get(TF_ITEM) or ""
        for line in item_str.strip().splitlines():
            line=line.strip()
            if not line: continue
            nums=re.findall(r"\d+",line)
            iname=re.sub(r"\s*\d+\s*$","",line).strip()
            if iname and nums:
                qty=int(nums[-1])
                item_agg[iname]["qty"]+=qty
                if product_cbm:
                    for prod_norm,cpb in product_cbm:
                        if prod_norm in re.sub(r"\s+","",iname):
                            item_agg[iname]["cbm"]+=round(cpb*qty,4); break

        created_s=rec.get("createdTime","")
        if created_s:
            cd=datetime.fromisoformat(created_s.replace("Z","+00:00")).date()
            if cd==ship_date: same_day+=1
            if "완료" in status:
                delta=(ship_date-cd).days
                if 0<=delta<=30: leadtimes.append(float(delta))

    total_boxes=sum(box_type_all.values())
    box_pct={k:round(v/total_boxes*100,1) for k,v in box_type_all.items()} if total_boxes else {}

    top_items=sorted(
        [{"name":k,"qty":v["qty"],"cbm":round(v["cbm"],3)} for k,v in item_agg.items() if v["cbm"]>0],
        key=lambda x:-x["cbm"])[:10]

    # 기사님 달성율 (차량CBM x 실배차일수 기준)
    driver_weekly_max={}; driver_pct={}; driver_work_days={}
    for driver,cap in VEHICLE_CBM.items():
        daily=dict(driver_daily.get(driver,{}))
        work_dates=sorted([d for d,c in daily.items() if c>0])
        work_cnt=len(work_dates)
        weekly_max=round(cap*work_cnt,3)
        weekly_cbm=round(driver_weekly.get(driver,0.0),3)
        driver_weekly_max[driver]=weekly_max
        driver_pct[driver]=round(weekly_cbm/weekly_max*100,1) if weekly_max>0 else 0.0
        driver_work_days[driver]={
            "count":work_cnt,"dates":work_dates,
            "labels":[f"{d[5:].replace('-','/')}({WD_KR[date.fromisoformat(d).weekday()]})" for d in work_dates],
        }

    a1_pct=round(round(total_cbm,3)/A1_WAREHOUSE_CBM*100,1)
    conf=round((cbm_sources["manual"]+cbm_sources["box_parse"])/total_cnt*100,1) if total_cnt else 0

    return {
        "summary":{
            "total_cbm":round(total_cbm,3),"total_count":total_cnt,
            "completed":completed,"pending":pending,
            "revenue":round(total_rev,0),"cost":round(total_cost,0),
            "profit":round(total_rev-total_cost,0),
            "cbm_per_shipment":round(total_cbm/total_cnt,3) if total_cnt else 0,
            "cbm_unit_cost":round(total_cost/total_cbm,0) if total_cbm>0 else 0,
        },
        "by_date":dict(sorted(by_date.items())),
        "box_type":{
            "counts":{k:box_type_all[k] for k in BOX_SIZE_ORDER if k in box_type_all},
            "pct":{k:box_pct[k] for k in BOX_SIZE_ORDER if k in box_pct},
            "total":total_boxes,
        },
        "top_items":top_items,
        "partners":[{"name":k,"cnt":v,"cbm":round(partner_cbm_agg[k],2)} for k,v in sorted(partner_agg.items(),key=lambda x:-x[1])],
        "quality":{
            "total_records":total_cnt,"missing_box_qty":missing_box,
            "missing_rate":round(missing_box/total_cnt*100,1) if total_cnt else 0,
            "same_day_create":same_day,
            "same_day_rate":round(same_day/total_cnt*100,1) if total_cnt else 0,
            "avg_leadtime_days":round(sum(leadtimes)/len(leadtimes),1) if leadtimes else None,
        },
        "confidence":conf,"cbm_sources":cbm_sources,
        "driver_daily":{k:dict(v) for k,v in driver_daily.items()},
        "driver_weekly":dict(driver_weekly),
        "driver_weekly_max":driver_weekly_max,
        "driver_pct":driver_pct,
        "driver_work_days":driver_work_days,
        "a1_utilization":{"total_cbm":round(total_cbm,3),"capacity":A1_WAREHOUSE_CBM,"pct":a1_pct},
    }

# ================================================================
# 기사님별 배송 라우팅 거리 계산
# ================================================================
# 적용 파일: sincerely_weekly_report_v2.py 에 함수 추가
#
# [구조]
# 1. fetch_routing_records()  - 배송슬롯 + 수령인주소 + 희망시간 조회
# 2. group_by_slot()          - 오전/오후/무관 그룹 분리
# 3. sort_by_time()           - 슬롯 내 희망시간 기준 정렬
# 4. geocode_kakao()          - 주소 -> 좌표 변환 (카카오 로컬 API)
# 5. route_distance_kakao()   - 경유지 포함 총 거리 계산 (카카오 모빌리티)
# 6. calc_driver_routing()    - 기사님별 일간/주간 km 집계
#
# [수식]
# 총 거리 = 에이원 -> 1번지 -> 2번지 -> ... -> N번지 (편도)
# 왕복 여부는 설정값으로 조절 (INCLUDE_RETURN_TRIP)
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
F_DATE        = "fldQvmEwwzvQW95h9"   # 출하확정일
F_PARTNER     = "fldHZ7yMT3KEu2gSj"   # 배송파트너 (from 배송파트너)
F_SLOT        = "fldcSrlxCngYQHtSV"   # 배송슬롯 (오전/오후/무관)
F_ADDRESS     = "fldyJHUh9gN44Ggnh"   # 수령인(주소)
F_WISH_TIME   = "fldFweNu3dASPv93N"   # 고객 희망 수령 시간
F_STATUS      = "fldOhibgxg6LIpRTi"   # 발송상태_TMS
F_TOTAL_CBM   = "fldJ9DHjwoRyeUEqE"   # Total_CBM
F_DEPARTURE   = "fldGZyp4KJNCSWWUr"   # 출하장소명 (multipleLookupValues)


# ----------------------------------------------------------------
# 1. 카카오 API 유틸
# ----------------------------------------------------------------
def _kakao_headers() -> dict:
    return {"Authorization": f"KakaoAK {KAKAO_API_KEY}"}


def geocode_kakao(address: str) -> tuple[float, float] | None:
    """
    주소 -> (위도, 경도) 변환
    반환: (lat, lng) 또는 None
    """
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

    origin = coords[0]
    dest   = coords[-1]
    waypoints = coords[1:-1]  # 중간 경유지

    try:
        params = {
            "origin":      f"{origin[1]},{origin[0]}",   # lng,lat
            "destination": f"{dest[1]},{dest[0]}",
            "priority":    "RECOMMEND",
            "car_fuel":    "GASOLINE",
            "car_hipass":  "false",
            "alternatives": "false",
            "road_details": "false",
        }
        # 경유지 최대 3개 (카카오 무료 기준)
        for i, wp in enumerate(waypoints[:3], 1):
            params[f"waypoint{i}"] = f"{wp[1]},{wp[0]}"  # lng,lat

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
            summary = routes[0]["summary"]
            distance_m = summary["distance"]
            return round(distance_m / 1000, 2)  # km

    except Exception as e:
        print(f"  [route API 실패] {e} -> 직선거리 fallback 사용")

    # fallback: 직선거리 합산 (Haversine)
    return _haversine_total(coords)


def _haversine(lat1, lng1, lat2, lng2) -> float:
    """두 좌표 간 직선거리 (km)"""
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
    """
    희망수령시간 문자열 -> 분 단위 정수 (정렬용)
    예: "10:00", "오전 10시", "14시 30분" -> 600, 600, 870
    인식 실패시 999 (가장 마지막으로 배치)
    """
    if not time_str:
        return 999
    m = _TIME_RE.search(str(time_str))
    if m:
        h = int(m.group(1))
        mn = int(m.group(2)) if m.group(2) else 0
        # "오전/오후" 보정
        if "오후" in str(time_str) and h < 12:
            h += 12
        return h * 60 + mn
    return 999


def _parse_slot(slot_val) -> str:
    """singleSelect 값 -> 슬롯 문자열"""
    if isinstance(slot_val, dict):
        return slot_val.get("name", SLOT_FLEXIBLE)
    if isinstance(slot_val, list) and slot_val:
        first = slot_val[0]
        return first.get("name", SLOT_FLEXIBLE) if isinstance(first, dict) else str(first)
    return str(slot_val) if slot_val else SLOT_FLEXIBLE


def _parse_departure(departure_val) -> str:
    """출하장소명 (multipleLookupValues) -> 출하장소 문자열"""
    if isinstance(departure_val, list):
        return departure_val[0] if departure_val else ""
    return str(departure_val) if departure_val else ""


def _is_dayoung_departure(departure_str: str) -> bool:
    """출하장소명에 다영기획 포함 여부"""
    return "다영기획" in departure_str
    if isinstance(addr_val, list):
        return addr_val[0] if addr_val else ""
    return str(addr_val) if addr_val else ""


def _parse_wish_time(wt_val) -> str:
    """rollup -> 희망시간 문자열"""
    if isinstance(wt_val, list):
        return wt_val[0] if wt_val else ""
    return str(wt_val) if wt_val else ""


# ----------------------------------------------------------------
# 3. Airtable에서 라우팅용 레코드 조회
# ----------------------------------------------------------------
def fetch_routing_records(start: date, end: date) -> list[dict]:
    """
    배송슬롯 + 수령인주소 + 희망시간 + 배송파트너 + 출하장소명 조회
    기사님 배송 건만 (신시어리 기사님 3분)
    """
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
                departure = _parse_departure(
                    f.get("출하장소명") or f.get(F_DEPARTURE)
                )
                result.append({
                    "date":       f.get("출하확정일", ""),
                    "partner":    pname,
                    "slot":       _parse_slot(f.get("배송슬롯") or f.get(F_SLOT)),
                    "address":    addr,
                    "wish_time":  _parse_wish_time(
                                    f.get("고객 희망 수령 시간") or
                                    f.get(F_WISH_TIME)
                                  ),
                    "cbm":        f.get(F_TOTAL_CBM) or 0,
                    "departure":  departure,       # 출하장소명 (다영기획 여부 판단용)
                    "is_dayoung": _is_dayoung_departure(departure),
                })
    return result


# ----------------------------------------------------------------
# 4. 슬롯별 정렬 + 라우팅 순서 결정
# ----------------------------------------------------------------
def build_route_order(deliveries: list[dict]) -> list[dict]:
    """
    단일 기사님 + 단일 날짜의 배송 목록을 받아
    슬롯 -> 희망시간 순서로 정렬하여 반환

    순서:
      1) 오전 슬롯 (희망시간 빠른 순)
      2) 무관 슬롯 (오전 마지막에 끼워넣기 - 에이원 근처 기준)
      3) 오후 슬롯 (희망시간 빠른 순)

    무관 배치 전략:
      - 무관 건의 주소를 geocode 후 오전/오후 경로 중
        앞 건 -> 무관 -> 뒷 건 거리가 최소인 위치에 삽입
      - geocode 비용 절감을 위해 오전 마지막에 기본 배치
    """
    morning   = [d for d in deliveries if d["slot"] == SLOT_MORNING]
    afternoon = [d for d in deliveries if d["slot"] == SLOT_AFTERNOON]
    flexible  = [d for d in deliveries if d["slot"] == SLOT_FLEXIBLE]

    # 슬롯 내 희망시간 정렬
    morning.sort(key=lambda d: _parse_time_minutes(d["wish_time"]))
    afternoon.sort(key=lambda d: _parse_time_minutes(d["wish_time"]))

    # 무관은 오전 마지막 + 오후 첫 사이에 배치 (희망시간 없으므로 근접성 기준 간단 배치)
    # 더 정밀한 최적화는 geocode 후 삽입 위치 계산
    ordered = morning + flexible + afternoon
    return ordered


# ----------------------------------------------------------------
# 5. 기사님별 일간 라우팅 거리 계산
# ----------------------------------------------------------------
_geocode_cache: dict[str, tuple[float, float] | None] = {}

def _get_coords(address: str) -> tuple[float, float] | None:
    """geocode with cache"""
    if address not in _geocode_cache:
        time.sleep(0.05)  # API rate limit 방지
        _geocode_cache[address] = geocode_kakao(address)
    return _geocode_cache.get(address)


def calc_daily_route(deliveries: list[dict], origin_coords) -> dict:
    """
    단일 기사님 + 단일 날짜 라우팅 거리 계산

    반환:
    {
        "total_km":    float,    # 총 주행거리
        "return_km":   float,    # 복귀 거리 (옵션)
        "route":       [         # 경유 순서
            {"address": str, "slot": str, "wish_time": str,
             "coords": (lat, lng), "leg_km": float}
        ],
        "stops":       int,      # 배송 건수
        "unresolved":  int,      # 주소 변환 실패 건수
    }
    """
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
                "cbm":       d["cbm"],
            })
            coords_chain.append(coords)
        else:
            unresolved += 1
            print(f"  [주소 변환 실패] {d['address'][:40]}")

    if len(coords_chain) < 2:
        return {"total_km": 0, "return_km": 0, "route": route_stops,
                "stops": 0, "unresolved": unresolved}

    # 복귀 포함 여부
    if INCLUDE_RETURN_TRIP:
        coords_chain.append(origin_coords)

    # 경유지 포함 총 거리 계산
    total_km = route_distance_kakao(coords_chain)

    # 구간별 거리 계산 (표시용)
    for i, stop in enumerate(route_stops):
        prev = coords_chain[i]
        curr = coords_chain[i + 1]
        stop["leg_km"] = _haversine(*prev, *curr)  # 직선거리 표시용

    return_km = 0.0
    if not INCLUDE_RETURN_TRIP and route_stops:
        last = route_stops[-1]["coords"]
        return_km = _haversine(*last, *origin_coords)

    return {
        "total_km":   total_km,
        "return_km":  return_km,
        "route":      route_stops,
        "stops":      len(route_stops),
        "unresolved": unresolved,
    }


# ----------------------------------------------------------------
# 6. 전체 집계 (일간 / 주간 / 월간)
# ----------------------------------------------------------------
def calc_driver_routing(records: list[dict]) -> dict:
    """
    fetch_routing_records() 결과를 받아
    기사님별 일간 / 주간 km 집계

    [출발지 로직]
    - 기본: 에이원지식산업센터 (서울 성동구 성수동1가 13-209)
    - 박종성 기사님 + 해당 날 배송 건 중 1건이라도 출하장소=다영기획이면
      -> 해당 날 출발지를 다영기획 (경기도 성남시 중원구 둔촌대로 555) 으로 변경
      -> 같은 날 에이원 출발 건도 있을 경우 다영기획 출발 후 에이원 경유 처리

    반환:
    {
        "driver_daily_routes": {
            "신시어리 (이장훈)": {
                "2026-03-09": {
                    "total_km": 45.2, "return_km": 8.1, "stops": 3,
                    "route": [...], "unresolved": 0,
                    "origin_label": "에이원",
                }, ...
            }, ...
        },
        "driver_weekly_km":    {"신시어리 (이장훈)": 198.4, ...},
        "origin_coords":       (lat, lng),
        "dayoung_coords":      (lat, lng),
    }
    """
    global ORIGIN_COORDS, DAYOUNG_ORIGIN_COORDS

    # 에이원 좌표 캐시
    if ORIGIN_COORDS is None:
        ORIGIN_COORDS = geocode_kakao(ORIGIN_ADDRESS)
        if ORIGIN_COORDS:
            print(f"  [출발지] 에이원 {ORIGIN_COORDS}")
        else:
            print("  [경고] 에이원 좌표 변환 실패 - fallback 사용")
            ORIGIN_COORDS = (37.5443, 127.0557)

    # 다영기획 좌표 캐시
    if DAYOUNG_ORIGIN_COORDS is None:
        DAYOUNG_ORIGIN_COORDS = geocode_kakao(DAYOUNG_ADDRESS)
        if DAYOUNG_ORIGIN_COORDS:
            print(f"  [출발지] 다영기획 {DAYOUNG_ORIGIN_COORDS}")
        else:
            print("  [경고] 다영기획 좌표 변환 실패 - 에이원 좌표로 대체")
            DAYOUNG_ORIGIN_COORDS = ORIGIN_COORDS

    # 기사님별 날짜별 그룹핑
    grouped: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for rec in records:
        grouped[rec["partner"]][rec["date"]].append(rec)

    driver_daily_routes: dict[str, dict] = {}
    driver_weekly_km:    dict[str, float] = {}

    for driver in SINCERELY_DRIVERS:
        driver_daily_routes[driver] = {}
        driver_weekly_km[driver]    = 0.0

        daily_data = grouped.get(driver, {})
        for day_str in sorted(daily_data.keys()):
            deliveries = daily_data[day_str]

            # 박종성 기사님 + 다영기획 출발 조건 판단
            # 해당 날 배송 건 중 1건이라도 is_dayoung=True 이면 다영기획 출발
            is_dayoung_day = (
                driver == DAYOUNG_DRIVER
                and any(d.get("is_dayoung") for d in deliveries)
            )
            origin         = DAYOUNG_ORIGIN_COORDS if is_dayoung_day else ORIGIN_COORDS
            origin_label   = "다영기획" if is_dayoung_day else "에이원"

            print(
                f"  [{driver.replace('신시어리 ', '')}] "
                f"{day_str} - {len(deliveries)}건 "
                f"출발지: {origin_label}"
            )

            result = calc_daily_route(deliveries, origin)
            result["origin_label"] = origin_label
            result["is_dayoung"]   = is_dayoung_day

            driver_daily_routes[driver][day_str] = result
            driver_weekly_km[driver] = round(
                driver_weekly_km[driver] + result["total_km"], 2
            )

            print(
                f"    -> 총 {result['total_km']}km "
                f"({result['stops']}건 / 미해결 {result['unresolved']}건)"
            )

    return {
        "driver_daily_routes": driver_daily_routes,
        "driver_weekly_km":    driver_weekly_km,
        "origin_coords":       ORIGIN_COORDS,
        "dayoung_coords":      DAYOUNG_ORIGIN_COORDS,
    }


# ----------------------------------------------------------------
# 7. analyze() 반환값에 라우팅 결과 합산하는 래퍼
# ----------------------------------------------------------------
def enrich_with_routing(analysis_result: dict,
                        routing_result: dict) -> dict:
    """
    analyze() 반환 dict에 라우팅 결과를 추가

    추가 키:
      driver_daily_routes  - 기사님별 일간 경로 상세
      driver_weekly_km     - 기사님별 주간 총 km
    """
    analysis_result["driver_daily_routes"] = routing_result["driver_daily_routes"]
    analysis_result["driver_weekly_km"]    = routing_result["driver_weekly_km"]
    return analysis_result


# ----------------------------------------------------------------
# 8. 리포트 출력 포맷터 (로그 / JSON 아카이브용)
# ----------------------------------------------------------------
def format_routing_log(routing_result: dict) -> str:
    """
    터미널 출력용 라우팅 요약 텍스트
    """
    lines = ["", "=== 기사님 배송 라우팅 요약 ==="]
    for driver in SINCERELY_DRIVERS:
        weekly_km = routing_result["driver_weekly_km"].get(driver, 0)
        lines.append(f"\n{driver.replace('신시어리 ', '')}  주간 {weekly_km}km")
        daily = routing_result["driver_daily_routes"].get(driver, {})
        for day_str, result in sorted(daily.items()):
            d = date.fromisoformat(day_str)
            wd = ["월", "화", "수", "목", "금", "토", "일"][d.weekday()]
            slots = []
            for stop in result["route"]:
                slots.append(f"[{stop['slot']}]{stop['address'][:15]}")
            route_str = " -> ".join(slots) if slots else "(경로 없음)"
            lines.append(
                f"  {day_str[5:]}({wd})  {result['total_km']}km  "
                f"{result['stops']}건  {route_str}"
            )
    return "\n".join(lines)


def routing_to_json(routing_result: dict) -> dict:
    """
    JSON 아카이브용 직렬화 (coords tuple -> list 변환)
    """
    result = {
        "driver_weekly_km": routing_result["driver_weekly_km"],
        "driver_daily_routes": {},
    }
    for driver, daily in routing_result["driver_daily_routes"].items():
        result["driver_daily_routes"][driver] = {}
        for day_str, data in daily.items():
            result["driver_daily_routes"][driver][day_str] = {
                "total_km":   data["total_km"],
                "return_km":  data["return_km"],
                "stops":      data["stops"],
                "unresolved": data["unresolved"],
                "route": [
                    {
                        "address":   s["address"],
                        "slot":      s["slot"],
                        "wish_time": s["wish_time"],
                        "leg_km":    s.get("leg_km", 0),
                        "cbm":       s.get("cbm", 0),
                    }
                    for s in data["route"]
                ],
            }
    return result


# ----------------------------------------------------------------
# main() 에서 호출 예시
# ----------------------------------------------------------------
# 기존 main() 안에 아래 코드 추가:
#
# from delivery_routing import (
#     fetch_routing_records, calc_driver_routing,
#     enrich_with_routing, format_routing_log, routing_to_json
# )
#
# # 이전주 라우팅 계산
# routing_recs  = fetch_routing_records(prev_mon, prev_fri)
# routing_result = calc_driver_routing(routing_recs)
# prev_data = enrich_with_routing(prev_data, routing_result)
# print(format_routing_log(routing_result))
#
# # JSON 아카이브에 추가
# archive["prev_week"]["routing"] = routing_to_json(routing_result)

# ================================================================
# 메인
# ================================================================
def main():
    if os.environ.get("SKIP_DELAY","0")!="1":
        d=random.randint(0,29*60)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {d//60}분 {d%60}초 후 실행")
        time.sleep(d)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] SCM 통합 리포트 시작 (모드: {REPORT_MODE})")
    start,end=get_period_range()
    print(f"  기간: {start} ~ {end}")

    # -- WMS 조회/분석 ----------------------------------------
    print("[WMS] 조회 중...")
    movement_records=fetch_movement(start,end)
    material_records=fetch_material()
    print(f"  movement: {len(movement_records)}건  material: {len(material_records)}건")
    inbound =analyze_inbound(movement_records)
    qc      =analyze_qc(movement_records)
    material=analyze_material(material_records)

    inb_s=inbound["summary"]; qc_s=qc["summary"]; mat_s=material["summary"]
    print(f"  입하완료율:{inb_s['completion_rate']}%  불량률:{qc_s['defect_rate']}%  재고정확도:{mat_s['accuracy']}%")

    # -- TMS 조회/분석 ----------------------------------------
    print("[TMS] 조회 중...")
    live_cbm    =fetch_box_cbm_live()
    product_cbm =fetch_product_cbm()
    ship_records=fetch_shipments_tms(start,end)
    print(f"  출하: {len(ship_records)}건")
    tms_data=analyze_tms(ship_records,live_cbm,product_cbm)
    sh_s=tms_data["summary"]
    print(f"  CBM {sh_s['total_cbm']}m3  완료:{sh_s['completed']}건  대기:{sh_s['pending']}건")
    src=tms_data["cbm_sources"]
    print(f"  CBM 산출: 수동{src['manual']} 매칭{src['product_match']} 파싱{src['box_parse']} 미산출{src['unmatched']}")

    # -- 라우팅 km --------------------------------------------
    print("[라우팅] 배송 거리 계산...")
    routing_records=ship_records  # 동일 기간 레코드 재사용
    routing=calc_routing(routing_records)

    # -- 이전주 데이터 (주간 모드) --------------------------
    prev_tms={}; prev_routing={}
    if REPORT_MODE in ("weekly_review","weekly_forecast"):
        prev_mon, prev_fri = prev_week_range(1)
        print(f"[TMS] 이전주 {prev_mon}~{prev_fri} 조회...")
        prev_recs=fetch_shipments_tms(prev_mon,prev_fri)
        prev_tms=analyze_tms(prev_recs,live_cbm,product_cbm)
        prev_routing=calc_routing(prev_recs)
        for driver,pct in prev_tms.get("driver_pct",{}).items():
            wd=prev_tms["driver_work_days"][driver]
            wmax=prev_tms["driver_weekly_max"][driver]
            wact=prev_tms["driver_weekly"].get(driver,0)
            km=prev_routing.get("driver_weekly_km",{}).get(driver)
            name=driver.replace("신시어리","").strip()
            print(f"  [{name}] CBM {wact:.2f}/{wmax}m3 ({VEHICLE_CBM[driver]}x{wd['count']}일)={pct}%" + (f" / {km}km" if km else ""))
        a1=prev_tms.get("a1_utilization",{})
        if a1: print(f"  [에이원] {a1['total_cbm']}m3/{a1['capacity']}m3 = {a1['pct']}%")

    # -- 추세 데이터 (주간 4주) ------------------------------
    trend=[]
    if REPORT_MODE in ("weekly_review","weekly_forecast"):
        trend_start=prev_week_range(4)[0]; _, trend_end=prev_week_range(1)
        print(f"[TMS] 트렌드 {trend_start}~{trend_end} 조회...")
        trend_recs=fetch_shipments_tms(trend_start,trend_end)
        weekly=defaultdict(lambda:{"cbm":0.0,"revenue":0.0,"cost":0.0,"count":0})
        for rec in trend_recs:
            f=_c(rec)
            d_s=f.get(TF_DATE)
            if not d_s: continue
            d=date.fromisoformat(d_s)
            mon=d-timedelta(days=d.weekday())
            w=weekly[mon]
            w["count"]+=1; w["revenue"]+=f.get(TF_REVENUE) or 0; w["cost"]+=f.get(TF_COST) or 0
            cbm_v,_=get_cbm_tms(f,live_cbm,product_cbm)
            w["cbm"]+=cbm_v
        for mon in sorted(weekly.keys())[-4:]:
            w=weekly[mon]; rev=round(w["revenue"]); cst=round(w["cost"])
            trend.append({"week":f"{mon.month}/{mon.day}주","cbm":round(w["cbm"],2),
                          "revenue":rev,"cost":cst,"profit":rev-cst,"count":w["count"]})

    # -- 다음주 (주간 모드) ----------------------------------
    next_tms={}
    if REPORT_MODE in ("weekly_review","weekly_forecast"):
        nmon,nfri=next_week_range()
        next_recs=fetch_shipments_tms(nmon,nfri)
        next_tms=analyze_tms(next_recs,live_cbm,product_cbm)

    # ================================================================
    # pages_data.json (dashboard.html용 - WMS+TMS 통합)
    # ================================================================
    if REPORT_MODE=="monthly":
        period_label=start.strftime("%Y년 %m월")+" (지난달)"
        period_key=start.strftime("%Y-%m")+"_monthly"
        week_lbl=""
    elif REPORT_MODE=="weekly_forecast":
        this_mon,_=this_week_range()
        period_label=week_label_for(this_mon)+" 예측"
        period_key=this_mon.strftime("%Y-W%V")+"_forecast"
        week_lbl=week_label_for(this_mon)
    else:
        last_mon,_=last_week_range()
        period_label=week_label_for(last_mon)+" 실적"
        period_key=last_mon.strftime("%Y-W%V")+"_review"
        week_lbl=week_label_for(last_mon)

    pages_data={
        "generated_at":datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "report_mode":REPORT_MODE,"period_key":period_key,
        "period":{"label":period_label,"week_label":week_lbl,
                  "start":start.isoformat(),"end":end.isoformat()},
        "kpi":{"completion_rate":inb_s["completion_rate"],"defect_rate":qc_s["defect_rate"],
               "accuracy":mat_s["accuracy"],"neg_avail_cnt":mat_s["neg_avail"]},
        "inbound":inbound,"qc":qc,"material":material,
        "shipment":tms_data,
        # weekly 섹션: 출하 탭에서 이전주/다음주/트렌드/품질/기사님 등 상세 표시용
        "weekly": {
            "this_week": {
                "summary":    tms_data["summary"],
                "by_date":    tms_data["by_date"],
                "box_type":   tms_data["box_type"],
                "top_items":  tms_data["top_items"],
                "quality":    tms_data["quality"],
                "cbm_sources":tms_data["cbm_sources"],
                "confidence": tms_data["confidence"],
            },
            "prev_week": {
                "summary":           prev_tms.get("summary",{}),
                "week_start":        prev_week_range(1)[0].isoformat() if REPORT_MODE!="monthly" else "",
                "driver_daily":      prev_tms.get("driver_daily",{}),
                "driver_weekly":     prev_tms.get("driver_weekly",{}),
                "driver_weekly_max": prev_tms.get("driver_weekly_max",{}),
                "driver_pct":        prev_tms.get("driver_pct",{}),
                "driver_work_days":  prev_tms.get("driver_work_days",{}),
                "a1_utilization":    prev_tms.get("a1_utilization",{}),
                "routing":           prev_routing,
            },
            "next_week": {
                "summary": next_tms.get("summary",{}),
                "by_date": next_tms.get("by_date",{}),
            },
            "trend": trend,
        },
    }
    with open("pages_data.json","w",encoding="utf-8") as fp:
        json.dump(pages_data,fp,ensure_ascii=False,indent=2,default=str)
    print("[OK] pages_data.json 저장 완료")

    # ================================================================
    # 주간 전용 리포트 (weekly.html 주입)
    # ================================================================
    if REPORT_MODE in ("weekly_review","weekly_forecast"):
        this_mon,_=this_week_range()
        weekly_archive={
            "generated_at":datetime.now().isoformat(),
            "week_start":this_mon.isoformat(),
            "this_week":{
                "summary":tms_data["summary"],
                "by_date":tms_data["by_date"],
                "box_type":tms_data["box_type"],
                "quality":tms_data["quality"],
                "top_items":tms_data["top_items"],
                "cbm_sources":tms_data["cbm_sources"],
                "confidence":tms_data["confidence"],
            },
            "prev_week":{
                "summary":prev_tms.get("summary",{}),
                "week_start":prev_week_range(1)[0].isoformat(),
                "driver_daily":prev_tms.get("driver_daily",{}),
                "driver_weekly":prev_tms.get("driver_weekly",{}),
                "driver_weekly_max":prev_tms.get("driver_weekly_max",{}),
                "driver_pct":prev_tms.get("driver_pct",{}),
                "driver_work_days":prev_tms.get("driver_work_days",{}),
                "a1_utilization":prev_tms.get("a1_utilization",{}),
                "routing":prev_routing,
            },
            "next_week":{
                "summary":next_tms.get("summary",{}),
                "by_date":next_tms.get("by_date",{}),
            },
            "trend":trend,
        }
        fname=f"report_{this_mon.isoformat()}.json"
        with open(fname,"w",encoding="utf-8") as fp:
            json.dump(weekly_archive,fp,ensure_ascii=False,indent=2,default=str)
        print(f"[OK] {fname} 저장")
        # docs/weekly.html에 주입
        inject_html("docs/weekly.html", weekly_archive, "const REPORT_DATA = null")

    # ================================================================
    # 월간 전용 리포트 (monthly.html 주입)
    # ================================================================
    if REPORT_MODE=="monthly":
        weekly_km_breakdown=_calc_weekly_km_breakdown(routing)
        monthly_archive={
            "generated_at":datetime.now().isoformat(),
            "month":start.isoformat(),"month_label":f"{start.year}년 {start.month}월",
            "total_cbm":sh_s["total_cbm"],"total_count":sh_s["total_count"],
            "total_rev":sh_s["revenue"],"total_cost":sh_s["cost"],
            "profit":sh_s["profit"],"cbm_per_ship":sh_s["cbm_per_shipment"],
            "weekly_cbm":{},  # 월간 주차별 (아래서 채움)
            "weekly_cnt":{},
            "weekly_labels":{},
            "partner_cnt":{p["name"]:p["cnt"] for p in tms_data["partners"]},
            "partner_pct":{p["name"]:round(p["cnt"]/sh_s["total_count"]*100,1) if sh_s["total_count"] else 0
                           for p in tms_data["partners"]},
            "partner_cbm":{p["name"]:p["cbm"] for p in tms_data["partners"]},
            "top_items":[(i["name"],i["qty"],i["cbm"]) for i in tms_data["top_items"]],
            "routing":{
                "driver_monthly_km":routing.get("driver_weekly_km",{}),
                "driver_weekly_km_breakdown":weekly_km_breakdown,
                "driver_daily_routes":routing.get("driver_daily_routes",{}),
            },
        }
        # 주차별 CBM 집계
        for d_str,v in tms_data["by_date"].items():
            try:
                d=date.fromisoformat(d_str)
                wno=(d.day-1)//7+1
                mon=d-timedelta(days=d.weekday())
                if wno not in monthly_archive["weekly_cbm"]:
                    monthly_archive["weekly_cbm"][wno]=0.0
                    monthly_archive["weekly_cnt"][wno]=0
                    monthly_archive["weekly_labels"][wno]=f"{mon.month}/{mon.day}주"
                monthly_archive["weekly_cbm"][wno]=round(monthly_archive["weekly_cbm"][wno]+v["cbm"],4)
                monthly_archive["weekly_cnt"][wno]+=v["cnt"]
            except Exception: pass

        fname=f"monthly_report_{start.strftime('%Y-%m')}.json"
        with open(fname,"w",encoding="utf-8") as fp:
            json.dump(monthly_archive,fp,ensure_ascii=False,indent=2,default=str)
        print(f"[OK] {fname} 저장")
        inject_html("docs/monthly.html", monthly_archive, "const MONTHLY_DATA = null")

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 완료")

if __name__=="__main__":
    if not WMS_KEY:
        print("ERROR: AIRTABLE_API_KEY_WMS 없음",file=sys.stderr); sys.exit(1)
    main()
