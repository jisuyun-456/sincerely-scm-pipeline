# -*- coding: utf-8 -*-
"""
weekly_report_data.py
────────────────────────────────────────────────────────────────────────────────
물류파트 주간 리포트(크림+클레이 디자인) 전용 데이터 계산기.  [chain: pages-weekly-report-port P1]

리포트에 나오는 *모든 동적 수치* 를 하나의 함수 compute(week_id) 로 계산 → dict 반환.
이 dict 이 P2 템플릿(@@token@@ / REPORT_DATA)의 데이터 공급원이다.

설계 (P0 확정, master tracker 참조):
  · 검증된 운영 KPI 는 생성기(generate_scm_report) 함수를 *재사용* — 재구현 시 미묘한 불일치 위험(입고 247 vs 1093 사례).
      - 입고(analyze_inbound) / 출고·CBM·기사이용률(analyze_tms) / 다음주 예측(tms_weekly_runner.analyze_iter5_forecast)
  · 리포트 고유 정의 2개는 로컬 구현: QC 불합격률 0.40%, 자재 피킹수 328.
  · 신규 7 KPI 는 로컬 구현(median/avg 등 러너 미노출 값 필요): DTS·공급사납기·FPY·AQL·검수시간·출하단가·오더사이클.
  · 전환 KPI(CBM·M/H 완결성)는 반정적 상수(계산 복잡·느리게 변함, 자동화 out-of-scope).

env: AIRTABLE_WMS_PAT(또는 AIRTABLE_API_KEY_WMS) · AIRTABLE_PAT(또는 _TMS) · AIRTABLE_IBSA_PAT
실행: python pages/weekly_report_data.py 2026-W31
"""
import os
import sys
import statistics
import pathlib
from datetime import datetime, date, timedelta
from collections import Counter, defaultdict

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ── 생성기·러너 재사용 (검증된 로직) ──────────────────────────────────────────
_PAGES_DIR = pathlib.Path(__file__).resolve().parent
_ROOT_DIR = _PAGES_DIR.parent
for _p in (str(_PAGES_DIR), str(_ROOT_DIR), str(_ROOT_DIR / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import generate_scm_report as G          # noqa: E402  (fetch_movement/analyze_inbound/analyze_tms 등)
import tms_weekly_runner as TWR          # noqa: E402  (analyze_iter5_forecast — 다음주 예측)

# ── PAT (CI secret 명과 로컬 .env 명 모두 지원) ──────────────────────────────
PAT_WMS  = os.environ.get("AIRTABLE_WMS_PAT")  or os.environ.get("AIRTABLE_API_KEY_WMS", "")
PAT_TMS  = os.environ.get("AIRTABLE_PAT")      or os.environ.get("AIRTABLE_API_KEY_TMS", "")
PAT_IBSA = os.environ.get("AIRTABLE_IBSA_PAT", "")

# 생성기 전역 키를 명시적으로 세팅 (env 변수명 차이로 잘못된 베이스 접근 방지)
if PAT_WMS:
    G.WMS_KEY = PAT_WMS
if PAT_TMS:
    G.TMS_KEY = PAT_TMS

BASE_WMS = "appLui4ZR5HWcQRri"
BASE_TMS = "app4x70a8mOrIKsMf"
BASE_IBSA = "app6DGHCPI3Yh3IFS"
TBL_MOV = "tblwq7Kj5Y9nVjlOw"
TBL_ORDER = "tblJslWg8sYEdCkXw"
TBL_SHIP = "tbllg1JoHclGYer7m"
TBL_SYNC = "tblhzYiltSBm6vxBz"

# movement 필드 ID
F_MOV_PURPOSE = "fldFRNxG1pNooEOC7"      # 이동목적 singleSelect
F_MOV_CREATED = "fldDXUAF4JOORLJ2v"      # 생성일자 dateTime
F_MOV_ACT = "flduN8khmYwdn7uVD"          # 실제입하일 date
F_MOV_EXP = "fldlpGxylH72YPs7V"          # 입하예상일 date
F_MOV_NOARR = "fldjZYoxIe1GI4DGa"        # 미입하 발생이력 checkbox
F_MOV_SUPPLIER = "fldqGAjPo0SHxx2qW"     # (파트너)발주협력사명
F_MOV_ISSUE = "fldudxogG53VjQmvX"        # 이슈카테고리 multipleSelects
F_MOV_OUTITEM = "fldQevLGnuqIuFRVO"      # 출고자재 singleLineText ('PT코드-품명 || 장소' 형식)
F_MOV_CANCEL = "fldwgaM8OnKubM8oE"       # 취소 여부 singleSelect ['취소']

# order 필드 ID (⚠️ Created time 필드명 백스페이스 변종 → 반드시 field ID + returnFieldsByFieldId)
F_ORD_START = "fldgXFrvBimnCcZjC"        # Created time(구.발주신청일)
F_ORD_SHIP = "fldNeMqU5r8sYGGT1"         # 최종 출고일

# shipment 필드 ID
F_SHP_DATE = "fldQvmEwwzvQW95h9"         # 출하확정일
F_SHP_CBM = "fldRQxI4HOWydlwEh"          # CBM_유효 (formula) — 출하단가 per-CBM 분모
F_SHP_COST = "fldGhFPbJzMToeGg7"         # 물류비(합계) (formula)

# TMS 배차일지 (기사별 차량이용률 median 소스 — 리포트 정의)
TBL_DISPATCH = "tbl0YCjOC7rYtyXHV"
TBL_PARTNER = "tblI4ZXrte7WyhXyd"
F_D_DATE = "fldZh2mZDIPQXfOcO"           # 날짜
F_D_PARTNER = "fldIQqaoj2CYlCSFH"        # 배송파트너 (link)
F_D_UTIL = "fldyQAoRZFn6oeQ0E"           # 차량이용률(%) = Total_CBM/차량한도 (A3 권위)
F_PARTNER_NAME = "fldUCl2kD890FqRkt"     # 배송파트너 이름
CBM_OUTLIER_CAP = 15.0                   # CBM_유효 이상치 상한 (출하단가 per-CBM 왜곡 방지)
CBM_MIN = 0.1                            # 미소 CBM 제외 (per-CBM ratio 폭주 방지)

# TMS OTIF / 배송클레임 (스냅샷 KPI)
TBL_OTIF = "tbl4WfEuGLDlqCTQH"
TBL_CLAIM = "tblIZ9kco1QDpUz0u"
F_OTIF_ONTIME = "fldoUQOue0umGJ2xk"      # On_Time
F_OTIF_INFULL = "fldiFhyU1k9YsnoGh"      # In_Full
F_OTIF_DELAY = "fldZJD4YRYg8Mr6yi"       # 납기차이일
F_CLAIM_DATE = "fldiNGNqgmQH1MFB7"       # 발생일
F_CLAIM_STATUS = "fldevAs6IBB0rN2MY"     # 처리상태

# IBSA sync_movement 필드 ID
F_IBSA_ARRIVE = "fld5pwd5dVYqW4Bdl"      # 입하완료처리시간 dateTime
F_IBSA_QTY_IN = "fldnvnZVsuUPgv1Mn"      # 입고수량입력시간 dateTime
F_IBSA_INSPECT = "fldPxJvu4iIFcxp7w"     # 시안검수완료시간 dateTime
F_IBSA_SAMPLE = "fldQjvDvHea1j9By9"      # 표본검수결과 singleSelect

WAREHOUSE_CBM = 44.4      # 창고 유효용적 기준 (report 고정)
DTS_TARGET_MIN = 480      # Dock-to-Stock 목표 (8h)
PICKING_PURPOSES = {"조립투입", "생산투입"}

# 표본검수결과 판정 집합
FPY_PASS = {"샘플링합격", "전수검수합격"}
SAMPLE_FAIL = {"샘플링불합격"}
UNRESOLVED = {"이슈 발생", "이슈 대응중"}
# FPY/AQL 분모(=실제 검수 판정이 내려진 건). 비검수 상태는 제외.
INSPECT_COUNTED = FPY_PASS | SAMPLE_FAIL | UNRESOLVED | {"이슈 발생 후 해결"}


def _h(pat):
    return {"Authorization": f"Bearer {pat}"}


def fetch(base, tbl, pat, fields=None, formula=None, byid=False, cap=20000):
    """Airtable 페이지네이션 fetch (byid=True → field ID 반환)."""
    recs, off = [], None
    sess = requests.Session()
    while True:
        p = [("pageSize", "100")]
        if byid:
            p.append(("returnFieldsByFieldId", "true"))
        if formula:
            p.append(("filterByFormula", formula))
        if fields:
            for f in fields:
                p.append(("fields[]", f))
        if off:
            p.append(("offset", off))
        r = sess.get(f"https://api.airtable.com/v0/{base}/{tbl}", headers=_h(pat), params=p, timeout=60)
        r.raise_for_status()
        d = r.json()
        recs += d.get("records", [])
        off = d.get("offset")
        if not off or len(recs) >= cap:
            break
    return recs


def week_bounds(week_id):
    y, w = week_id.split("-W")
    mon = date.fromisocalendar(int(y), int(w), 1)
    return mon, mon + timedelta(days=4)


def _median(xs):
    return round(statistics.median(xs), 1) if xs else None


def _mean(xs):
    return round(statistics.mean(xs), 1) if xs else None


def _pct(xs, p):
    if not xs:
        return None
    s = sorted(xs)
    idx = (len(s) - 1) * p / 100
    lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (idx - lo), 1)


def _parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _parse_d(s):
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except (ValueError, AttributeError, TypeError):
        return None


def _sel(v):
    """singleSelect 값 정규화 (dict/str 모두)."""
    if isinstance(v, dict):
        return v.get("name", "")
    return str(v) if v else ""


# ═════════════════════════════════════════════════════════════════════════════
#  개별 KPI 계산
# ═════════════════════════════════════════════════════════════════════════════
def kpi_inbound(mon, fri):
    """입고 건수·완료율·일별·목적별·미입하 (생성기 analyze_inbound 재사용)."""
    mov = G.fetch_movement(mon, fri)          # 실제입하일 window
    inb = G.analyze_inbound(mov)
    s = inb["summary"]

    # 일별 입고 건수 (chart)
    by_date = [{"date": d, "cnt": v["cnt"]} for d, v in inb["by_date"].items()]

    # 입고 목적별 구성 (chart) — 건수 내림차순
    by_purpose = sorted(
        [{"purpose": k, "cnt": v["cnt"], "qty": v["qty"]} for k, v in inb["by_purpose"].items()],
        key=lambda x: -x["cnt"],
    )

    # QC 불합격률 = 이슈카테고리 '품질이슈' 건수 / 전체 (리포트 고유 정의)
    quality = 0
    issue_break = Counter()
    for r in mov:
        cats = G._c(r).get(F_MOV_ISSUE) or []
        names = [_sel(c) for c in cats]
        for n in names:
            if n:
                issue_break[n] += 1
        if "품질이슈" in names:
            quality += 1
    total = s["total_cnt"]
    qc_fail_rate = round(quality / total * 100, 2) if total else 0.0

    return {
        "inbound_count": total,
        "inbound_completed": s["completed"],
        "inbound_unconfirmed": s["unconfirmed"],
        "inbound_completion_rate": s["completion_rate"],
        "inbound_total_qty": s["total_in_qty"],
        "chart_inbound_by_date": by_date,
        "chart_inbound_by_purpose": by_purpose,
        "qc_fail_rate": qc_fail_rate,
        "qc_quality_issue_cnt": quality,
        "qc_issue_breakdown": dict(issue_break),
    }, mov


def kpi_no_arrival(mon, fri):
    """미입하 발생 — 미입하발생이력=TRUE ∩ 입하예상일 W31, 협력사별."""
    formula = (
        f"AND({{미입하 발생이력}}=TRUE(), {{입하예상일}}!='', "
        f"IS_AFTER({{입하예상일}}, '{(mon - timedelta(days=1)).isoformat()}'), "
        f"IS_BEFORE({{입하예상일}}, '{(fri + timedelta(days=1)).isoformat()}'))"
    )
    recs = fetch(BASE_WMS, TBL_MOV, PAT_WMS, byid=True,
                 fields=[F_MOV_NOARR, F_MOV_EXP, F_MOV_ACT, F_MOV_SUPPLIER], formula=formula)
    by_sup = Counter()
    for r in recs:
        sup = (r["fields"].get(F_MOV_SUPPLIER) or "미기재").strip() or "미기재"
        by_sup[sup] += 1
    return {
        "no_arrival_count": len(recs),
        "no_arrival_by_supplier": by_sup.most_common(),
    }


def kpi_material_picking(mon, fri):
    """자재 피킹수 328 = 이동목적∈{조립투입,생산투입} ∩ 출고자재에 '에이원지식산업센터' 또는 'PNA' 포함, 취소 제외.

    출고자재 필드는 'PT코드-품명 || 장소' 형식으로 장소가 에이원지식산업센터/PNA(내부 조립·생산 투입 경로).
    매칭 340(조립320+생산20) 중 취소 12 제외 → 328. (project 필드가 아니라 출고자재 문자열 안에 존재 — 실측 확인)
    """
    formula = (
        f"AND(OR({{이동목적}}='조립투입', {{이동목적}}='생산투입'), "
        f"IS_AFTER({{생성일자}}, '{(mon - timedelta(days=1)).isoformat()}'), "
        f"IS_BEFORE({{생성일자}}, '{(fri + timedelta(days=1)).isoformat()}'))"
    )
    recs = fetch(BASE_WMS, TBL_MOV, PAT_WMS, byid=True,
                 fields=[F_MOV_PURPOSE, F_MOV_OUTITEM, F_MOV_CANCEL], formula=formula)
    matched, cancelled = 0, 0
    by_purpose = Counter()          # 매칭 건수 (취소 포함) — 리포트 '조립 320 · 생산 20'
    for r in recs:
        f = r["fields"]
        outitem = f.get(F_MOV_OUTITEM) or ""
        if "에이원지식산업센터" not in outitem and "PNA" not in outitem:
            continue
        matched += 1
        by_purpose[_sel(f.get(F_MOV_PURPOSE))] += 1
        if _sel(f.get(F_MOV_CANCEL)) == "취소":
            cancelled += 1
    return {
        "material_picking_count": matched - cancelled,
        "material_picking_matched": matched,
        "material_picking_cancelled": cancelled,
        "material_picking_by_purpose": dict(by_purpose),
    }


def _ship_partner(f):
    """shipment 배송파트너 링크 → 이름 (analyze_tms 와 동일 추출)."""
    pf = f.get(G.TF_PARTNER)
    if isinstance(pf, dict):
        for vals in pf.get("valuesByLinkedRecordId", {}).values():
            if vals:
                return vals[0]
    elif isinstance(pf, list) and pf:
        return str(pf[0])
    elif pf:
        return str(pf)
    return None


def kpi_tms(mon, fri):
    """출고 건수·주간 CBM·창고가동율·일별 CBM·CBM채널별·배송방식별.

    CBM 소스 = CBM_유효(formula, fldRQxI4HOWydlwEh). Total_CBM(수동입력)은 과거 소스였으나
    2026-08-25 Airtable 실측 대조에서 미입력 다수로 확인 (예: 8/12 그룹 Total_CBM 합계 0.08
    vs CBM_유효 합계 13.28 — 같은 날 8건 중 4건이 Total_CBM 공란). CBM_유효는 estimated_cbm
    제품매칭 오류로 단일 건이 100배+ 튀는 이상치가 있어(tms_weekly_runner.FORECAST_CBM_OUTLIER_CAP과
    동일 근거) [CBM_MIN, CBM_OUTLIER_CAP] 범위 밖은 합계·채널·방식 breakdown에서 제외.
    (건수 count는 이상치 여부와 무관하게 실제 출하 건 전체를 센다 — 제외되는 건 CBM 금액만.)
    """
    ships = G.fetch_shipments_tms(mon, fri)
    by_date = defaultdict(float)
    ch_cbm = defaultdict(float)
    ch_cnt = defaultdict(int)
    total_cbm = 0.0
    count = 0
    for rec in ships:
        f = G._c(rec)
        d = f.get(G.TF_DATE)
        if not d:
            continue
        count += 1
        cbm_raw = float(f.get(G.TF_CBM_VALID) or 0)
        cbm = cbm_raw if CBM_MIN <= cbm_raw <= CBM_OUTLIER_CAP else 0.0   # 이상치 제외
        total_cbm += cbm
        by_date[d] += cbm
        display = G.PARTNER_GROUP.get(_ship_partner(f), _ship_partner(f)) or "미기재"
        ch_cbm[display] += cbm
        ch_cnt[display] += 1
    total_cbm = round(total_cbm, 2)

    channels = sorted(
        [{"name": k, "cbm": round(ch_cbm[k], 2), "cnt": ch_cnt[k]} for k in ch_cbm],
        key=lambda x: -x["cbm"],
    )

    # 배송방식별 = 파트너 CBM 을 배송수단으로 묶음 (리포트 규칙: 협력사는 파트너명 우선)
    method = defaultdict(float)
    for k, cbm in ch_cbm.items():
        if "로젠" in k or "택배" in k:
            method["택배"] += cbm
        elif "고객" in k:
            method["기타(고객직접)"] += cbm
        else:
            method["퀵(수도권)"] += cbm
    method_chart = [{"method": k, "cbm": round(v, 2)} for k, v in sorted(method.items(), key=lambda x: -x[1])]

    return {
        "outbound_count": count,
        "weekly_cbm": total_cbm,
        "warehouse_util_pct": round(total_cbm / WAREHOUSE_CBM * 100, 1),
        "chart_outbound_cbm_by_date": [{"date": d, "cbm": round(v, 2)} for d, v in sorted(by_date.items())],
        "chart_cbm_by_channel": channels,
        "chart_by_method": method_chart,
    }


def kpi_driver_util(week_id):
    """기사별 차량이용률(%) = 배차일지 차량이용률% median (W31, 리포트 정의)."""
    mon, fri = week_bounds(week_id)
    pc = fetch(BASE_TMS, TBL_PARTNER, PAT_TMS, byid=True, fields=[F_PARTNER_NAME])
    cache = {r["id"]: r["fields"].get(F_PARTNER_NAME, "") for r in pc}
    formula = f"AND({{날짜}}>='{mon.isoformat()}', {{날짜}}<='{fri.isoformat()}')"
    recs = fetch(BASE_TMS, TBL_DISPATCH, PAT_TMS, byid=True,
                 fields=[F_D_DATE, F_D_PARTNER, F_D_UTIL], formula=formula)
    by_driver = defaultdict(list)
    for r in recs:
        f = r["fields"]
        u = f.get(F_D_UTIL)
        pids = f.get(F_D_PARTNER) or []
        if u is None or not pids:
            continue
        nm = cache.get(pids[0], pids[0]).replace("신시어리 ", "").strip("() ")
        by_driver[nm].append(float(u))
    chart = [{"driver": k, "pct": round(statistics.median(v), 1), "days": len(v)}
             for k, v in sorted(by_driver.items(), key=lambda x: -statistics.median(x[1]))]
    return {"chart_driver_util": chart}


def kpi_dock_to_stock(week_id):
    """DTS = IBSA 입하완료처리시간→입고수량입력시간, median/avg, 음수·이상치 제외, 목표≤480."""
    mon, fri = week_bounds(week_id)
    formula = (
        f"AND(IS_AFTER({{입하완료처리시간}}, DATEADD('{mon.isoformat()}', -1, 'days')), "
        f"IS_BEFORE({{입하완료처리시간}}, DATEADD('{fri.isoformat()}', 1, 'days')))"
    )
    recs = fetch(BASE_IBSA, TBL_SYNC, PAT_IBSA, byid=True,
                 fields=[F_IBSA_ARRIVE, F_IBSA_QTY_IN], formula=formula)
    vals, neg = [], 0
    for r in recs:
        f = r["fields"]
        t0, t1 = _parse_dt(f.get(F_IBSA_ARRIVE)), _parse_dt(f.get(F_IBSA_QTY_IN))
        if not t0 or not t1:
            continue
        m = (t1 - t0).total_seconds() / 60
        if m < 0:
            neg += 1
            continue
        if m > 2000:
            continue
        vals.append(m)
    within = sum(1 for m in vals if m <= DTS_TARGET_MIN)
    return {
        "dts_count": len(vals),
        "dts_avg_min": round(statistics.mean(vals)) if vals else None,
        "dts_median_min": round(statistics.median(vals)) if vals else None,
        "dts_within_target": within,
        "dts_target_pct": round(within / len(vals) * 100, 1) if vals else None,
        "dts_excluded_negative": neg,
    }


def kpi_supplier_ontime(week_id):
    """공급사 납기 준수율 = movement 입하예상일 vs 실제입하일 (실제입하일 W31), 정시=실제≤예상."""
    mon, fri = week_bounds(week_id)
    formula = (
        f"AND({{입하예상일}}!='', {{실제입하일}}!='', "
        f"{{실제입하일}}>='{mon.isoformat()}', {{실제입하일}}<='{fri.isoformat()}')"
    )
    recs = fetch(BASE_WMS, TBL_MOV, PAT_WMS, byid=True,
                 fields=[F_MOV_EXP, F_MOV_ACT, F_MOV_SUPPLIER], formula=formula)
    total = ontime = late = 0
    diffs = []
    for r in recs:
        f = r["fields"]
        exp, act = _parse_d(f.get(F_MOV_EXP)), _parse_d(f.get(F_MOV_ACT))
        if not exp or not act:
            continue
        total += 1
        d = (act - exp).days
        diffs.append(d)
        if act <= exp:
            ontime += 1
        else:
            late += 1
    return {
        "supplier_ontime_pct": round(ontime / total * 100, 1) if total else None,
        "supplier_total": total,
        "supplier_ontime": ontime,
        "supplier_late": late,
        "supplier_avg_diff_days": round(statistics.mean(diffs), 1) if diffs else None,
    }


def kpi_inspection_quality(days=90):
    """FPY·AQL·검수 처리시간 — IBSA 표본검수결과 + 입하완료처리시간→시안검수완료시간 (최근 90일)."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    formula = f"IS_AFTER({{입하완료처리시간}}, '{cutoff}')"
    recs = fetch(BASE_IBSA, TBL_SYNC, PAT_IBSA, byid=True,
                 fields=[F_IBSA_SAMPLE, F_IBSA_ARRIVE, F_IBSA_INSPECT], formula=formula)

    # FPY / AQL — 표본검수결과 판정이 내려진 건만 분모
    counted = pass_cnt = unresolved = sample_fail = 0
    for r in recs:
        res = _sel(r["fields"].get(F_IBSA_SAMPLE))
        if res not in INSPECT_COUNTED:
            continue
        counted += 1
        if res in FPY_PASS:
            pass_cnt += 1
        if res in UNRESOLVED:
            unresolved += 1
        if res in SAMPLE_FAIL:
            sample_fail += 1
    fpy = round(pass_cnt / counted * 100, 1) if counted else None
    aql = round((counted - unresolved - sample_fail) / counted * 100, 1) if counted else None

    # 검수 처리시간 = 입하완료처리시간 → 시안검수완료시간, 0<m≤600
    times = []
    for r in recs:
        f = r["fields"]
        t0, t1 = _parse_dt(f.get(F_IBSA_ARRIVE)), _parse_dt(f.get(F_IBSA_INSPECT))
        if not t0 or not t1:
            continue
        m = (t1 - t0).total_seconds() / 60
        if 0 < m <= 600:
            times.append(m)
    return {
        "fpy_pct": fpy,
        "fpy_pass": pass_cnt,
        "fpy_total": counted,
        "aql_pct": aql,
        "aql_unresolved": unresolved,
        "aql_sample_fail": sample_fail,
        "inspect_time_median_min": _median(times),
        "inspect_time_mean_min": _mean(times),
        "inspect_time_p90_min": _pct(times, 90),
        "inspect_time_count": len(times),
    }


def kpi_shipping_unit_cost(days=30):
    """출하 단가 = TMS 물류비(합계) ÷ CBM_유효, median 오더당·CBM당 (최근 30일)."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    # 필드명(공백 변종) 대신 field ID 참조 — 생성기 fetch_shipments_tms 와 동일 패턴(검증됨).
    formula = f"IS_AFTER({{{F_SHP_DATE}}}, '{cutoff}')"
    recs = fetch(BASE_TMS, TBL_SHIP, PAT_TMS, byid=True,
                 fields=[F_SHP_COST, F_SHP_CBM, F_SHP_DATE], formula=formula)
    per_order, per_cbm = [], []
    for r in recs:
        f = r["fields"]
        cost = float(f.get(F_SHP_COST) or 0)
        cbm = float(f.get(F_SHP_CBM) or 0)
        if cost > 0:
            per_order.append(cost)                          # 오더당: 전체 cost>0 (→ median 70,250)
            if CBM_MIN <= cbm <= CBM_OUTLIER_CAP:           # per-CBM: 이상치 CBM 제외 (→ median ~68,443)
                per_cbm.append(cost / cbm)
    return {
        "ship_cost_per_order_median": round(statistics.median(per_order)) if per_order else None,
        "ship_cost_per_cbm_median": round(statistics.median(per_cbm)) if per_cbm else None,
        "ship_cost_count": len(per_order),
        "ship_cost_cbm_count": len(per_cbm),
    }


def kpi_order_cycle(days=90):
    """오더 사이클타임 = order Created time→최종 출고일, median days, 0≤d≤180 (최근 90일)."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    formula = f"AND({{최종 출고일}}!='', IS_AFTER({{최종 출고일}}, '{cutoff}'))"
    recs = fetch(BASE_WMS, TBL_ORDER, PAT_WMS, byid=True,
                 fields=[F_ORD_START, F_ORD_SHIP], formula=formula)
    days_list = []
    for r in recs:
        f = r["fields"]
        start, ship = _parse_d(f.get(F_ORD_START)), _parse_d(f.get(F_ORD_SHIP))
        if not start or not ship:
            continue
        d = (ship - start).days
        if 0 <= d <= 180:
            days_list.append(d)
    return {
        "order_cycle_median_days": round(statistics.median(days_list)) if days_list else None,
        "order_cycle_p25_days": _pct(days_list, 25),
        "order_cycle_p75_days": _pct(days_list, 75),
        "order_cycle_count": len(days_list),
    }


def kpi_otif_claims(days=90):
    """OTIF On-Time·In-Full·약속납기 전환율 (전체 누적) + 배송 클레임 (90일 롤링)."""
    def _truthy(v):
        return bool(v) and v not in (0, "0", "No", "false", False)

    otif = fetch(BASE_TMS, TBL_OTIF, PAT_TMS, byid=True,
                 fields=[F_OTIF_ONTIME, F_OTIF_INFULL, F_OTIF_DELAY])
    n = len(otif)
    on = sum(1 for r in otif if _truthy(r["fields"].get(F_OTIF_ONTIME)))
    full = sum(1 for r in otif if _truthy(r["fields"].get(F_OTIF_INFULL)))
    delays = [r["fields"].get(F_OTIF_DELAY) for r in otif if r["fields"].get(F_OTIF_DELAY) is not None]
    promised = len(delays)

    cutoff = (date.today() - timedelta(days=days)).isoformat()
    claims = fetch(BASE_TMS, TBL_CLAIM, PAT_TMS, byid=True,
                   fields=[F_CLAIM_DATE, F_CLAIM_STATUS],
                   formula=f"IS_AFTER({{{F_CLAIM_DATE}}}, '{cutoff}')")
    open_claims = sum(1 for r in claims if _sel(r["fields"].get(F_CLAIM_STATUS)) not in ("완료", "처리완료", "종결"))
    return {
        "otif_ontime_pct": round(on / n * 100, 1) if n else None,
        "otif_infull_pct": round(full / n * 100, 1) if n else None,
        "otif_total": n,
        "promise_conversion_pct": round(promised / n * 100, 1) if n else None,
        "promise_avg_delay_days": round(statistics.mean([float(x) for x in delays]), 1) if delays else None,
        "claim_count": len(claims),
        "claim_open": open_claims,
    }


def kpi_next_week_forecast():
    """다음주 볼륨 예측 (tms_weekly_runner.analyze_iter5_forecast 재사용, today-relative)."""
    recs = fetch(BASE_TMS, TBL_SHIP, PAT_TMS, byid=True, fields=[F_SHP_DATE, F_SHP_CBM])
    try:
        fc = TWR.analyze_iter5_forecast({"all_shipments": recs})
    except Exception as e:
        return {"forecast_count": None, "forecast_cbm": None, "forecast_error": str(e)}
    return {
        "forecast_count": fc["total_forecast"],
        "forecast_cbm": fc["total_forecast_cbm"],
        "forecast_peak_day": fc["peak_day"],
        "forecast_data_weeks": fc["data_weeks"],
    }


# 전환 KPI (반정적 — 리포트 W32 확정값, 자동화 out-of-scope)
CONVERSION_KPI = {
    "cbm_completeness_pct": 81.2,
    "cbm_complete": 1335,
    "cbm_total": 1645,
    "cbm_pending": 310,
    "cbm_box_only_pct": 90.4,
    "cbm_cbm_only_pct": 84.1,
    "cbm_a1_pct": 89.3,
    "cbm_dayoung_pct": 86.5,
    "cbm_bottleneck_note": "미확정 310건 중 다영기획 156건(50.3%)",
    "mh_inbound_pct": 100.0,
    "mh_inspect_pct": 99.8,
    "mh_putaway_pct": 99.9,
    "mh_full_cycle_pct": 99.7,
    "mh_prepkg_pct": 12.1,
    "mh_prepkg_est_pct": 88.6,
    "mh_timestamp_count": 3808,
}


# ═════════════════════════════════════════════════════════════════════════════
def compute(week_id):
    """리포트 데이터 dict 반환."""
    mon, fri = week_bounds(week_id)
    d = {
        "week_id": week_id,
        "week_range": f"{mon.strftime('%m-%d')} ~ {fri.strftime('%m-%d')}",
        "generated_at": date.today().isoformat(),
    }
    inb, _mov = kpi_inbound(mon, fri)
    d.update(inb)
    d.update(kpi_no_arrival(mon, fri))
    d.update(kpi_material_picking(mon, fri))
    d.update(kpi_tms(mon, fri))
    d.update(kpi_driver_util(week_id))
    d.update(kpi_dock_to_stock(week_id))
    d.update(kpi_supplier_ontime(week_id))
    d.update(kpi_inspection_quality())
    d.update(kpi_shipping_unit_cost())
    d.update(kpi_order_cycle())
    d.update(kpi_otif_claims())
    d.update(kpi_next_week_forecast())
    d["conversion_kpi"] = CONVERSION_KPI
    d["label"] = f'W{week_id.split("-W")[1]} ({d["week_range"].split("~")[0].strip().replace("-", "/")}~)'
    return d


if __name__ == "__main__":
    import json
    wk = sys.argv[1] if len(sys.argv) > 1 else "2026-W31"
    print(json.dumps(compute(wk), ensure_ascii=False, indent=2, default=str))
