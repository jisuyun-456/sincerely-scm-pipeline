# -*- coding: utf-8 -*-
"""
weekly_report_data.py
────────────────────────────────────────────────────────────────────────────────
물류파트 주간 리포트(크림+클레이 디자인) 전용 데이터 계산기.

리포트의 *고유 KPI 정의*를 그대로 재현한다 (기존 dashboard 생성기와 정의가 다름):
  - 입고 건수 247 (movement 생성일자 기준, 입하완료/미확인)
  - QC 불합격률 0.40% (movement 이슈카테고리 '품질이슈' 직접)
  - 자재 피킹수 328 (이동목적 조립/생산투입 ∩ project PNA ∩ 출고자재 에이원, 취소 제외)
  - 출고 54 · 주간 Total_CBM (TMS Shipment)
  - 미입하 10 (movement, 입하예상일/실제입하일/생성일자 W31 union)
  - Dock-to-Stock (IBSA), 공급사납기(WMS), FPY·AQL·검수시간(IBSA)
  - 출하단가(Shipment 물류비), 오더 사이클타임(order)
  - 차트: 일별 입고 / 일별 출고 CBM / 입고목적별 / CBM채널별 / 배송방식별 / 기사별 이용률
  - 다음주 볼륨 예측 (Shipment 요일패턴, 건수+CBM)

출력: 리포트 템플릿(@@token@@)에 주입할 flat dict + 차트용 구조.

env: AIRTABLE_WMS_PAT(또는 AIRTABLE_API_KEY_WMS) · AIRTABLE_PAT(또는 _TMS) · AIRTABLE_IBSA_PAT
"""
import os, requests, statistics
from datetime import datetime, date, timedelta
from collections import Counter, defaultdict

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ── PAT (CI secret 명과 로컬 .env 명 모두 지원) ──────────────────────────────
PAT_WMS  = os.environ.get("AIRTABLE_WMS_PAT")  or os.environ.get("AIRTABLE_API_KEY_WMS", "")
PAT_TMS  = os.environ.get("AIRTABLE_PAT")      or os.environ.get("AIRTABLE_API_KEY_TMS", "")
PAT_IBSA = os.environ.get("AIRTABLE_IBSA_PAT", "")

BASE_WMS="appLui4ZR5HWcQRri"; BASE_TMS="app4x70a8mOrIKsMf"; BASE_IBSA="app6DGHCPI3Yh3IFS"
TBL_MOV="tblwq7Kj5Y9nVjlOw"; TBL_ORDER="tblJslWg8sYEdCkXw"
TBL_SHIP="tbllg1JoHclGYer7m"; TBL_SYNC="tblhzYiltSBm6vxBz"

# movement 필드 ID
F_MOV_PURPOSE="fldFRNxG1pNooEOC7"; F_MOV_CREATED="fldDXUAF4JOORLJ2v"
F_MOV_EXP="fldlpGxylH72YPs7V"; F_MOV_ACT="flduN8khmYwdn7uVD"
F_MOV_NOARR="fldjZYoxIe1GI4DGa"; F_MOV_SUPPLIER="fldqGAjPo0SHxx2qW"; F_MOV_ISSUE="fldudxogG53VjQmvX"
# order
F_ORD_START="fldgXFrvBimnCcZjC"; F_ORD_SHIP="fldNeMqU5r8sYGGT1"
# shipment
F_SHP_DATE="fldQvmEwwzvQW95h9"; F_SHP_CBM="fldRQxI4HOWydlwEh"

WAREHOUSE_CBM = 44.4  # 창고 유효용적 기준 (report 고정)
DTS_TARGET_MIN = 480

def _h(pat): return {"Authorization": f"Bearer {pat}"}

def fetch(base, tbl, pat, fields=None, formula=None, byid=False, cap=12000):
    recs, off = [], None
    while True:
        p=[("pageSize","100")]
        if byid: p.append(("returnFieldsByFieldId","true"))
        if formula: p.append(("filterByFormula",formula))
        if fields:
            for f in fields: p.append(("fields[]", f))
        if off: p.append(("offset", off))
        r=requests.get(f"https://api.airtable.com/v0/{base}/{tbl}", headers=_h(pat), params=p, timeout=30)
        r.raise_for_status(); d=r.json(); recs+=d.get("records",[]); off=d.get("offset")
        if not off or len(recs)>=cap: break
    return recs

def week_bounds(week_id):
    y,w = week_id.split("-W")
    mon = date.fromisocalendar(int(y), int(w), 1)
    return mon, mon+timedelta(days=4)

def _median(xs):
    return statistics.median(xs) if xs else None


# ─────────────────────────────────────────────────────────────────────────────
def compute(week_id):
    """주어진 ISO week(예 '2026-W31')의 리포트 데이터 dict 반환."""
    mon, fri = week_bounds(week_id)
    s, e = mon.isoformat(), fri.isoformat()
    d = {"week_id": week_id, "week_range": f"{mon.strftime('%m-%d')} ~ {fri.strftime('%m-%d')}"}

    # ══ 입고 건수 (movement 생성일자 W31) ══
    mov = fetch(BASE_WMS, TBL_MOV, PAT_WMS, byid=True,
                fields=[F_MOV_PURPOSE, F_MOV_CREATED, F_MOV_ISSUE, F_MOV_EXP, F_MOV_ACT, F_MOV_NOARR, F_MOV_SUPPLIER],
                formula=f"AND(IS_AFTER({{생성일자}}, '{(mon-timedelta(days=1)).isoformat()}'), IS_BEFORE({{생성일자}}, '{(fri+timedelta(days=1)).isoformat()}'))")
    d["ingo_count"] = len(mov)

    # 입고 목적별 구성 (건수)
    purpose = Counter()
    for r in mov:
        p = r["fields"].get(F_MOV_PURPOSE)
        if p: purpose[p]+=1
    d["inbound_by_purpose"] = purpose.most_common()

    # QC 불합격률 (이슈카테고리 '품질이슈')
    qcat = Counter()
    for r in mov:
        for c in (r["fields"].get(F_MOV_ISSUE) or []):
            qcat[c]+=1
    q_total = len(mov)
    q_quality = qcat.get("품질이슈", 0)
    d["qc_fail_rate"] = round(q_quality/q_total*100, 2) if q_total else 0.0
    d["qc_issue_breakdown"] = dict(qcat)

    return d, mov


if __name__ == "__main__":
    import json, sys
    wk = sys.argv[1] if len(sys.argv)>1 else "2026-W31"
    data, _mov = compute(wk)
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
