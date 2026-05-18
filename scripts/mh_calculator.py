"""
mh_calculator.py
────────────────────────────────────────────────────────────────────────────────
글로벌 ELS (Engineered Labor Standards) 기반 WMS+TMS M/H 추정 계산기.

* 0 schema change — Airtable 읽기 전용
* 입하·피킹 즉시 작동 (기존 데이터만)
* 입고·검수는 사용자 입력(거리 매트릭스·표본검수분) 도착 시 활성화

사용법:
  python scripts/mh_calculator.py                  # 직전 30일 기본
  python scripts/mh_calculator.py --since 2026-04-15
  python scripts/mh_calculator.py --dry-run        # API 호출만, 파일 미생성

출처: WERC Annual Benchmark Report, SAP EWM·Manhattan Active WM·Blue Yonder LMS
"""

import argparse
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

# ── Airtable 설정 ──────────────────────────────────────────────────────────────
# WMS
WMS_BASE_ID = "appLui4ZR5HWcQRri"
TBL_MOVEMENT = "tblwq7Kj5Y9nVjlOw"
TBL_PICKING_TASK = "tblJpQcCJfIyB9Xf5"

# TMS
TMS_BASE_ID = "app4x70a8mOrIKsMf"
TBL_SHIPMENT = "tbllg1JoHclGYer7m"

WMS_PAT = os.environ.get("AIRTABLE_WMS_PAT") or os.environ.get("AIRTABLE_PAT", "")
TMS_PAT = os.environ.get("AIRTABLE_PAT") or os.environ.get("AIRTABLE_WMS_PAT", "")

# ── 글로벌 ELS 표준 (분 단위) ─────────────────────────────────────────────────
# 출처: WERC mid-range / SAP EWM·Manhattan·Blue Yonder LMS 기본값
# 자사 측정값이 도출되면 이 블록만 교체하면 됨.
PFD_ALLOWANCE = 1.15  # 15% Personal+Fatigue+Delay

# Receiving (입하) — *spec×qty → CBM* 1차 path (cbm_inbound_check.py 로직 재사용)
# - 이동목적="생산산출" record에서 제품 규격 + 입하수량 → 정확 CBM
# - 규격 없으면 sync_parts 룩업, 그것도 없으면 carton/pcs fallback
RECEIVING_MIN_PER_CBM = 4.0          # 15 CBM/MH 글로벌 표준
RECEIVING_MIN_THICKNESS_MM = 3.0     # 2D dims(스티커 등) 두께 fallback (cbm_inbound_check 정합)
RECEIVING_MIN_PER_CARTON = 0.6       # fallback (cartons-only record)
RECEIVING_FALLBACK_PCS_PER_CARTON = 100

# Putaway (입고) — 사용자 측정 (2026-05-18): 적은 수량/부피 3분 ~ 큰 부피·파렛트·다이어리 류 max 10분
# CBM-linear with cap. CBM 없는 fallback record는 base 3분 적용.
PUTAWAY_BASE_MIN = 3.0
PUTAWAY_MAX_MIN = 10.0
PUTAWAY_PER_CBM_MIN = 7.0   # CBM 1.0에서 max 도달 (3 + 1.0×7 = 10)

# QC (입하검수) — 사용자 측정 (2026-05-18): 프로젝트 1개당 2~3분 (표본검수). 분포 mid = 2.5
QC_MIN_PER_PROJECT = 2.5

# 출고검수 (Outbound QC) — 사용자 측정 (2026-05-18): A3 박스 단위로만, project 1개당 1~3분
# (CBM 높고 2층 파렛트 지게차 내림은 3분, 작은 건 1분) — Iter1.4 mid 2.0분 균일
# 작업 내용: WMS logistics_release 패킹리스트 + 외박스 라벨 + TMS 출하확인서 ↔ 실제 좌표·박스 수량 매칭
OUTBOUND_QC_MIN_PER_PROJECT = 2.0

# 하차 (Unloading) — 사용자 측정 (2026-05-18): 3~8분/프로젝트 (mid 5.5분)
# CBM-weighted: base 3 + min(5, project_cbm × 5.0) cap 8
# mid check: 0.5 m³/project → 3 + 2.5 = 5.5 ✓
UNLOAD_BASE_MIN = 3.0
UNLOAD_MAX_MIN = 8.0
UNLOAD_PER_CBM_MIN = 5.0  # 1 m³/project → max 도달

# 피킹 *임시 deferred* (Iter1.4 사용자 지시) — calc_picking_mh 함수 본체는 유지, 보고서 출력만 제외
# 사용자 자사 batch_size 실측 후 Iter1.6 재활성화 예정
INCLUDE_PICKING = False

# Picking — *batch pick* (바스켓/박스 단위, 자사 운영 패턴)
# 한 task의 qty는 batch 안에 묶여 있어 piece 단위로 빼지 않음 (50/100/150/200 등)
# 시간 = ceil(qty / batch_size) × per_batch  (box 핸들링 1회 ≈ 1.5분: 집기·스캔·배치)
PICK_BATCH_SIZE_DEFAULT = 100      # 자사 평균 (50~200 mid)
PICK_MIN_PER_BATCH = 1.5           # 1 box/batch 핸들링 시간 (분)
PICK_MIN_PER_PIECE_FALLBACK = 0.6  # batch_size 불명·소량 잔여건 fallback

# TMS — Dispatch 0.5~2 min/shipment · Docs 2~5 min (자동화 시 <1)
TMS_DISPATCH_MIN_PER_SHIPMENT = 1.0
TMS_DOCS_MIN_PER_SHIPMENT = 2.0

# ── 이동유형 분류 ─────────────────────────────────────────────────────────────
# WMS의 movement 테이블은 사실상 *입하 ledger* (이동유형 = "본품"/"샘플" 분류).
# 따라서 receiving = "실제입하일 + 입하 qty 보유" 로 판단.
SAMPLE_KIND = "샘플"  # 샘플은 표본검수 영역으로 분리 가능 (현재는 receiving에 포함)


# ── Airtable 헬퍼 ─────────────────────────────────────────────────────────────
def get_records(table_id, fields=None, formula=None, max_records=None,
                sort_field=None, sort_dir="desc", stop_predicate=None,
                base_id=None, pat=None, by_field_id=False):
    """
    Paginated fetch. stop_predicate(record) → True 시 즉시 중단.
    Karpathy: filterByFormula 대신 sort + 클라이언트 필터 (perf memo 준수).
    by_field_id=True 시 fields는 field IDs로 해석, response도 field ID key.
    """
    base_id = base_id or WMS_BASE_ID
    pat = pat or WMS_PAT
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {pat}"})
    records, offset = [], None
    while True:
        params = {"pageSize": 100, "returnFieldsByFieldId": "true" if by_field_id else "false"}
        if fields:
            params["fields[]"] = fields
        if formula:
            params["filterByFormula"] = formula
        if sort_field:
            params["sort[0][field]"] = sort_field
            params["sort[0][direction]"] = sort_dir
        if offset:
            params["offset"] = offset
        if max_records:
            params["maxRecords"] = max_records
        resp = session.get(
            f"https://api.airtable.com/v0/{base_id}/{table_id}",
            params=params, timeout=90,
        )
        resp.raise_for_status()
        data = resp.json()
        page = data.get("records", [])
        records.extend(page)
        # client-side stop: sort된 페이지에서 한 건이라도 predicate 만족 시 중단
        if stop_predicate and page and any(stop_predicate(r) for r in page):
            break
        offset = data.get("offset")
        if not offset or (max_records and len(records) >= max_records):
            break
        time.sleep(0.2)
    return records


# ── 카테고리 분류 ─────────────────────────────────────────────────────────────
# ── 규격→CBM 헬퍼 (cbm_inbound_check.py 로직 재사용) ──────────────────────────
import re as _re

def parse_dims_mm(raw):
    """
    '88x88x163', '248*190*33', '200x300', '55x160mm 펼침...' → (W,H,D) mm.
    cbm_inbound_check.py와 동일. 2D dims는 MIN_THICKNESS_MM fallback.
    """
    if not raw:
        return None
    cleaned = _re.split(r"펼침", str(raw))[0]
    cleaned = _re.sub(r"mm", "", cleaned, flags=_re.IGNORECASE)
    nums = [float(n) for n in _re.findall(r"[\d.]+", cleaned) if float(n) > 0]
    if len(nums) >= 3:
        return (nums[0], nums[1], nums[2])
    if len(nums) == 2:
        return (nums[0], nums[1], RECEIVING_MIN_THICKNESS_MM)
    return None


def spec_to_cbm(spec, qty):
    """규격 문자열 × 수량 → CBM (m³). returns (cbm, parsed_ok)."""
    dims = parse_dims_mm(spec)
    if dims is None or qty <= 0:
        return 0.0, False
    w, h, d = dims
    unit_cbm = (w / 1000) * (h / 1000) * (d / 1000)
    return unit_cbm * qty, True


# sync_parts 테이블: PT 코드 → 규격 lookup (cbm_inbound_check field IDs 재사용)
TBL_SYNC_PARTS = "tblzJh0V4hdo4Xbvx"
FLD_SP_CODE = "fld8gjySjm4XkCpMc"   # 파츠 코드
FLD_SP_SPEC = "fldRseOMNseg15D6R"   # 규격


def load_sync_parts_lookup():
    """sync_parts → {PT_code: 규격} 1회 사전 로드. field ID 사용 (이름 변동 면역)."""
    records = get_records(TBL_SYNC_PARTS, fields=[FLD_SP_CODE, FLD_SP_SPEC], by_field_id=True)
    lookup = {}
    for r in records:
        f = r.get("fields", {})
        code = str(f.get(FLD_SP_CODE) or "").strip()
        spec = str(f.get(FLD_SP_SPEC) or "").strip()
        if code:
            lookup[code] = spec
    return lookup


def _extract_pt_code(이동물품):
    """'PT3137-사각스티커 || PNA35889_...' → 'PT3137'."""
    if not 이동물품:
        return ""
    first = str(이동물품).split("||")[0].strip()
    dash = first.find("-")
    return first[:dash] if dash != -1 else first


def _extract_project_code(이동물품):
    """'PT3137-... || PNA35889_어텐션스포츠보틀 || ...' → 'PNA35889'."""
    if not 이동물품:
        return ""
    parts = str(이동물품).split("||")
    if len(parts) < 2:
        return ""
    proj = parts[1].strip()
    under = proj.find("_")
    return proj[:under] if under != -1 else proj


def classify_movement(rec):
    """
    WMS movement은 receiving ledger. 실제입하일 + 입하 qty 보유 → 'receiving'.
    """
    f = rec.get("fields", {})
    if not f.get("실제입하일"):
        return "other"
    if (_to_float(f.get("입하수량")) > 0
            or _to_float(f.get("입하카톤수")) > 0
            or _to_float(f.get("입하파렛트수")) > 0):
        return "receiving"
    return "other"


# ── Receiving M/H ─────────────────────────────────────────────────────────────
def calc_receiving_mh(rec, sync_parts_lookup=None):
    """
    입하 M/H_std. *spec×qty→CBM* 1차 path (cbm_inbound_check 로직 재사용).
    우선순위:
      1. 제품 규격 (record 직접) + 입하수량 → CBM
      2. sync_parts.규격 (이동물품 PT 코드 룩업) + 입하수량 → CBM
      3. 입하카톤수 fallback
      4. 입하수량(pcs)/100 → cartons fallback
    returns (mh_std_minutes, basis, qty_or_cbm)
    """
    f = rec.get("fields", {})
    pcs = _to_float(f.get("입하수량"))
    spec_direct = str(f.get("제품 규격") or "").strip()
    이동물품 = f.get("이동물품")

    # 1차: 제품 규격 직접
    if pcs > 0 and spec_direct:
        cbm, ok = spec_to_cbm(spec_direct, pcs)
        if ok and cbm > 0:
            mh = cbm * RECEIVING_MIN_PER_CBM * PFD_ALLOWANCE
            return mh, "cbm-from-spec", cbm

    # 2차: sync_parts 룩업
    if pcs > 0 and sync_parts_lookup and 이동물품:
        pt_code = _extract_pt_code(이동물품)
        spec_fallback = sync_parts_lookup.get(pt_code, "")
        if spec_fallback:
            cbm, ok = spec_to_cbm(spec_fallback, pcs)
            if ok and cbm > 0:
                mh = cbm * RECEIVING_MIN_PER_CBM * PFD_ALLOWANCE
                return mh, "cbm-from-sync_parts", cbm

    # 3차: 카톤 fallback
    cartons = _to_float(f.get("입하카톤수"))
    if cartons > 0:
        mh = cartons * RECEIVING_MIN_PER_CARTON * PFD_ALLOWANCE
        return mh, "cartons-fallback", cartons

    # 4차: pcs→cartons est fallback
    if pcs > 0:
        eq_cartons = pcs / RECEIVING_FALLBACK_PCS_PER_CARTON
        mh = eq_cartons * RECEIVING_MIN_PER_CARTON * PFD_ALLOWANCE
        return mh, "pcs-fallback", pcs

    return 0.0, "no_data", 0.0


# ── Picking M/H ───────────────────────────────────────────────────────────────
def calc_picking_mh(rec):
    """
    피킹 M/H_std. *batch pick* 패턴: 자사는 piece가 박스/바스켓에 묶여 있어
    qty가 50~200이어도 핸들링 1~2회로 끝남.
    수식: time = ceil(qty / batch_size) × per_batch (× PFD)
    잔여 1~9개 fallback 시 per-piece 적용 (안전망).
    """
    import math
    f = rec.get("fields", {})
    picked = _to_float(f.get("Picked_Qty"))
    required = _to_float(f.get("Required_Qty"))
    qty = picked if picked > 0 else required
    if qty <= 0:
        return 0.0, "no_qty", 0.0

    batches = math.ceil(qty / PICK_BATCH_SIZE_DEFAULT)
    mh = batches * PICK_MIN_PER_BATCH * PFD_ALLOWANCE
    return mh, f"batch×{batches}", qty


# ── Putaway M/H — 사용자 측정 기반 (3~10 min, CBM-linear cap) ──────────────────
def calc_putaway_mh(rec, cbm=0.0):
    """
    입고 M/H. 사용자 표명: 적은 수량/부피 3분 ~ 큰 부피·파렛트·다이어리 류 max 10분.
    수식: base 3 + min(7, cbm × 7), CBM 1.0+에서 max 도달. cbm 없으면 base만.
    """
    if cbm <= 0:
        return PUTAWAY_BASE_MIN * PFD_ALLOWANCE
    extra = min(PUTAWAY_MAX_MIN - PUTAWAY_BASE_MIN, cbm * PUTAWAY_PER_CBM_MIN)
    return (PUTAWAY_BASE_MIN + extra) * PFD_ALLOWANCE


# ── TMS Shipment M/H ──────────────────────────────────────────────────────────
def calc_tms_shipment_mh(rec):
    """
    TMS shipment 1건 = dispatch + docs M/H_std.
    returns (mh_std_minutes, basis, mode).
    """
    f = rec.get("fields", {})
    mode_raw = f.get("배송 유형") or f.get("배송방식") or "-"
    if isinstance(mode_raw, list):
        mode = "/".join(str(x) for x in mode_raw)
    else:
        mode = str(mode_raw)
    mh = (TMS_DISPATCH_MIN_PER_SHIPMENT + TMS_DOCS_MIN_PER_SHIPMENT) * PFD_ALLOWANCE
    return mh, "shipment", mode


# ── QC M/H — 사용자 측정 기반 (프로젝트당 2~3 min, mid 2.5) ────────────────────
def calc_qc_mh_per_project():
    """입하검수: 프로젝트 1개당 표본검수 M/H. caller가 distinct projects 갯수와 곱함."""
    return QC_MIN_PER_PROJECT * PFD_ALLOWANCE


# ── Outbound QC M/H — 사용자 측정 기반 (project당 1~3 min, mid 2.0) ─────────────
def calc_outbound_qc_mh_per_project():
    """출고검수: project 1개당 A3 박스 단위 매칭 M/H. caller가 distinct outbound projects 갯수와 곱함."""
    return OUTBOUND_QC_MIN_PER_PROJECT * PFD_ALLOWANCE


# ── Unloading M/H — 사용자 측정 기반 (3~8 min/project, CBM-weighted) ──────────
def calc_unloading_mh_for_project(project_cbm: float = 0.0) -> float:
    """하차 M/H. 사용자 측정: 3~8분/프로젝트 (mid 5.5min), CBM-weighted."""
    extra = min(UNLOAD_MAX_MIN - UNLOAD_BASE_MIN, project_cbm * UNLOAD_PER_CBM_MIN)
    return (UNLOAD_BASE_MIN + extra) * PFD_ALLOWANCE


# ── 유틸 ──────────────────────────────────────────────────────────────────────
def _to_float(v):
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def _parse_date(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def iso_week(d):
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


# ── 리포트 생성 ────────────────────────────────────────────────────────────────
def generate_report(receiving_rows, putaway_rows, picking_rows, tms_rows,
                    distinct_projects, distinct_outbound_projects,
                    project_cbm_map,
                    since, until, out_path):
    week = iso_week(until)

    total_recv = sum(r["mh_std"] for r in receiving_rows)
    total_putaway = sum(r["mh_std"] for r in putaway_rows)
    total_pick = sum(r["mh_std"] for r in picking_rows)
    total_tms = sum(r["mh_std"] for r in tms_rows)
    total_qc = len(distinct_projects) * calc_qc_mh_per_project()
    total_outbound_qc = len(distinct_outbound_projects) * calc_outbound_qc_mh_per_project()
    total_unload = sum(
        calc_unloading_mh_for_project(project_cbm_map.get(p, 0.0))
        for p in distinct_projects
    )

    # 피킹은 Iter1.4 사용자 지시로 합계에서 제외 (INCLUDE_PICKING=False)
    pick_in_total = total_pick if INCLUDE_PICKING else 0.0
    total_wms = total_recv + total_putaway + total_qc + total_outbound_qc + total_unload + pick_in_total
    total_all = total_wms + total_tms

    # FTE: 매니저 2명(파트장+파트원) 제외 — 실작업자만 카운트
    # 입하·입고 2 + 자재(피킹) 1 + 검수 1 + 출하 1 = 5명
    productive_fte = 5
    total_fte = 7  # OKR 기준 (KR-1 7명 × 1.5)
    fte_minutes_per_week = productive_fte * 40 * 60
    days = (until - since).days + 1
    weeks_in_window = days / 7.0
    fte_window = fte_minutes_per_week * weeks_in_window
    capacity_pct = (total_all / fte_window * 100) if fte_window else 0

    # 피킹 deferred 표기 (Iter1.4 사용자 지시)
    if INCLUDE_PICKING:
        pick_row = f"| WMS 피킹 | {len(picking_rows)} 건 / {total_pick/60:.1f} MH |"
    else:
        pick_row = "| WMS 피킹 | _deferred — 사용자 batch_size 실측 확인 중_ |"

    lines = [
        f"# WMS+TMS M/H 분석 — {week}  (Global ELS Iter 1.5)",
        "",
        f"**기간**: {since.isoformat()} ~ {until.isoformat()} ({days}일)",
        f"**범위**: WMS 입하·입고·입하검수·출고검수·**하차** + TMS Shipment dispatch+docs — *피킹·외주임가공·프리패키징 deferred*",
        f"**표준 출처**: WERC Annual Benchmark · SAP EWM/Manhattan/Blue Yonder LMS · MOST/MTM-2",
        f"**PFD allowance**: ×{PFD_ALLOWANCE} (15% Personal+Fatigue+Delay)",
        "",
        "## 요약",
        "",
        f"| 항목 | 값 |",
        f"|---|---|",
        f"| WMS 입하 | {len(receiving_rows)} 건 / {total_recv/60:.1f} MH |",
        f"| WMS 입고 (Putaway) | {len(putaway_rows)} 건 / {total_putaway/60:.1f} MH |",
        f"| WMS 하차 (Unloading) | {len(distinct_projects)} 프로젝트 / {total_unload/60:.1f} MH |",
        f"| WMS 입하검수 (표본) | {len(distinct_projects)} 프로젝트 / {total_qc/60:.1f} MH |",
        f"| WMS 출고검수 (A3 박스 매칭) | {len(distinct_outbound_projects)} 프로젝트 / {total_outbound_qc/60:.1f} MH |",
        pick_row,
        f"| **WMS 합계 (피킹 제외)** | **{total_wms/60:.1f} MH** |",
        f"| TMS Shipment | {len(tms_rows)} 건 / {total_tms/60:.1f} MH |",
        f"| **전체 합계** | **{total_all/60:.1f} MH** |",
        f"| FTE 가용 ({productive_fte}명 실작업 × 40h × {weeks_in_window:.1f}주) | {fte_window/60:.0f} MH |",
        f"| 표준 대비 가동률 | {capacity_pct:.1f}% |",
        "",
        f"> FTE 구성: 입하·입고 2 + 자재(피킹) 1 + 검수 1 + 출하 1 = **{productive_fte}명**. ",
        f"> 매니저(파트장+파트원) {total_fte - productive_fte}명은 관리·판단 역할로 capacity 계산에서 제외. ",
        f"> 단 OKR KR-1은 {total_fte}명 기준 ×1.5 처리량 (Sprint 4 정책 그대로).",
        "",
        "> ⚠️ 글로벌 벤치마크 기반 *추정값*. 자사 환경 보정 전엔 *상대 variance*만 신뢰. ",
        "> 자사 실측 M/H 산출 후 상수 1줄 교체로 정확도 ↑.",
        "",
        "## 입하 (Receiving) 상세",
        "",
        f"| 레코드 | basis | qty | M/H_std (min) |",
        f"|---|---|---|---|",
    ]
    for r in sorted(receiving_rows, key=lambda x: -x["mh_std"])[:30]:
        lines.append(f"| {r['id']} | {r['basis']} | {r['qty']:.1f} | {r['mh_std']:.1f} |")
    if len(receiving_rows) > 30:
        lines.append(f"| ... ({len(receiving_rows)-30} more) | | | |")

    # TMS section
    from collections import Counter
    mode_ctr = Counter(r["mode"] for r in tms_rows)
    lines += [
        "",
        "## TMS Shipment (Dispatch + Docs) 상세",
        "",
        f"- Shipment 건수: **{len(tms_rows)}**",
        f"- per-shipment 표준: dispatch {TMS_DISPATCH_MIN_PER_SHIPMENT}분 + docs {TMS_DOCS_MIN_PER_SHIPMENT}분 × PFD {PFD_ALLOWANCE}",
        f"- 합계: **{total_tms/60:.1f} MH** ({total_tms:.0f} 분)",
        "",
        "### 배송유형별 분포 (Top)",
        "",
        "| 배송유형 | 건수 | M/H |",
        "|---|---|---|",
    ]
    per_shipment_mh = (TMS_DISPATCH_MIN_PER_SHIPMENT + TMS_DOCS_MIN_PER_SHIPMENT) * PFD_ALLOWANCE
    for mode, cnt in mode_ctr.most_common(10):
        mode_disp = mode if mode and mode != "-" else "(미분류)"
        lines.append(f"| {mode_disp} | {cnt} | {cnt * per_shipment_mh / 60:.1f} MH |")

    # 입고·검수 상세
    putaway_with_cbm = [r for r in putaway_rows if r["cbm"] > 0]
    putaway_base_only = len(putaway_rows) - len(putaway_with_cbm)
    avg_putaway_min = (total_putaway / len(putaway_rows)) if putaway_rows else 0
    lines += [
        "",
        "## 하차 (Unloading) 상세",
        "",
        f"- 표준: base {UNLOAD_BASE_MIN}분 + min({UNLOAD_MAX_MIN - UNLOAD_BASE_MIN}, project_cbm×{UNLOAD_PER_CBM_MIN}) × PFD (cap {UNLOAD_MAX_MIN}분) — 사용자 측정",
        f"- mid 검증: 0.5 m³/project → {UNLOAD_BASE_MIN} + {0.5*UNLOAD_PER_CBM_MIN:.1f} = {UNLOAD_BASE_MIN + 0.5*UNLOAD_PER_CBM_MIN:.1f}분 ✓",
        f"- 단위: 프로젝트(PNA***) 별 CBM 합산 (기존 receiving records 재사용, 추가 API 호출 0)",
        f"- distinct 프로젝트 수: {len(distinct_projects)} / CBM 보유 프로젝트: {sum(1 for p in distinct_projects if project_cbm_map.get(p, 0) > 0)}",
        f"- 합계 **{total_unload/60:.1f} MH** ({total_unload:.0f} 분)",
        "",
        "## 입고 (Putaway) 상세",
        "",
        f"- 표준: base {PUTAWAY_BASE_MIN}분 + min({PUTAWAY_MAX_MIN - PUTAWAY_BASE_MIN}, CBM×{PUTAWAY_PER_CBM_MIN}) × PFD (cap {PUTAWAY_MAX_MIN}분) — 사용자 측정",
        f"- 처리 건수: {len(putaway_rows)} (CBM 보유 {len(putaway_with_cbm)} / fallback base만 {putaway_base_only})",
        f"- 평균 M/H: **{avg_putaway_min:.2f}분/건** · 합계 **{total_putaway/60:.1f} MH**",
        "",
        "## 입하검수 (QC, 표본) 상세",
        "",
        f"- 표준: 프로젝트 1개당 {QC_MIN_PER_PROJECT}분 (mid of 2~3) × PFD — 사용자 측정",
        f"- distinct 프로젝트 수: {len(distinct_projects)} (movement.이동물품 PNA*** 추출)",
        f"- 합계 **{total_qc/60:.1f} MH** ({total_qc:.0f} 분)",
        "",
        "## 출고검수 (Outbound QC, A3 박스 매칭) 상세",
        "",
        f"- 표준: project 1개당 {OUTBOUND_QC_MIN_PER_PROJECT}분 (mid of 1~3, 자사 측정) × PFD",
        "- 작업: WMS `logistics_release` 패킹리스트 + 외박스 라벨 + TMS 출하확인서 ↔ 실제 좌표·박스 수량 매칭 (전수·표본 아님, 박스 단위)",
        "- 3분 케이스: CBM 높음 + 2층 파렛트 지게차 내림. mid 2분 균일 적용 (CBM-tier 보정은 Iter 후속 후보)",
        f"- distinct outbound project 수: {len(distinct_outbound_projects)} (TMS shipment.project code 추출)",
        f"- 합계 **{total_outbound_qc/60:.1f} MH** ({total_outbound_qc:.0f} 분)",
        "",
        "## Deferred (사용자 입력 대기)",
        "",
        "- **피킹** — 사용자 자사 batch_size 실측(50/100/150/200 mix) 확인 중. 함수 로직(`calc_picking_mh`) 유지, 본 보고서에서만 제외",
        "- **상차** (Loading) — TMS 도메인 영역, WMS M/H 계산 제외",
        "- **외주임가공** (다영기획 prep) — 사용자 연구 결과 수령 후",
        "- **프리패키징** (MES 인쇄 prep) — 사용자 확인 후",
        "",
        "## 글로벌 표준 상수 (script L37~57)",
        "",
        f"- 입하 **CBM 기반**: {RECEIVING_MIN_PER_CBM} min/CBM ({60/RECEIVING_MIN_PER_CBM:.0f} CBM/MH 글로벌) — spec×qty (cbm_inbound_check 로직 재사용)",
        f"- 입하 fallback case: {RECEIVING_MIN_PER_CARTON} min/case · pcs/{RECEIVING_FALLBACK_PCS_PER_CARTON}→case",
        f"- 입고: base {PUTAWAY_BASE_MIN} + min({PUTAWAY_MAX_MIN - PUTAWAY_BASE_MIN}, CBM×{PUTAWAY_PER_CBM_MIN}) min/건 (cap {PUTAWAY_MAX_MIN}) — 사용자 측정",
        f"- 입하검수: {QC_MIN_PER_PROJECT} min/project (표본검수, mid of 2~3) — 사용자 측정",
        f"- 출고검수: {OUTBOUND_QC_MIN_PER_PROJECT} min/project (A3 박스 매칭, mid of 1~3) — 사용자 측정",
        f"- 하차: base {UNLOAD_BASE_MIN} + min({int(UNLOAD_MAX_MIN-UNLOAD_BASE_MIN)}, project_cbm×{UNLOAD_PER_CBM_MIN}) min/project (cap {UNLOAD_MAX_MIN}) — 사용자 측정",
        f"- 피킹 **batch** (현재 *deferred*): {PICK_MIN_PER_BATCH} min/batch (batch size={PICK_BATCH_SIZE_DEFAULT}) — 자사 운영 패턴 (50~200 묶음)",
        f"- TMS shipment: dispatch {TMS_DISPATCH_MIN_PER_SHIPMENT} + docs {TMS_DOCS_MIN_PER_SHIPMENT} min",
        f"- PFD: ×{PFD_ALLOWANCE}",
        "",
    ]

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", help="ISO date (default: 30일 전)")
    parser.add_argument("--until", help="ISO date (default: 오늘)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out-dir", default="outputs",
                        help="report output directory (default: outputs/)")
    args = parser.parse_args()

    if not WMS_PAT:
        sys.exit("ERROR: AIRTABLE_WMS_PAT or AIRTABLE_PAT not set in env")

    until = date.fromisoformat(args.until) if args.until else date.today()
    since = date.fromisoformat(args.since) if args.since else (until - timedelta(days=30))

    print(f"[mh_calculator] period: {since} ~ {until}", flush=True)

    # 0) sync_parts 룩업 1회 사전 로드 (PT 코드 → 규격, fallback용)
    print(f"[mh_calculator] loading sync_parts lookup (PT→규격)...", flush=True)
    sync_parts_lookup = load_sync_parts_lookup()
    print(f"[mh_calculator]   sync_parts lookup: {len(sync_parts_lookup)} entries", flush=True)

    # 1) Receiving: movement 테이블 — 최신순 sort + 클라이언트 필터
    print(f"[mh_calculator] fetching movement records (sorted by 실제입하일 desc)...", flush=True)
    mov_fields = [
        "이동유형", "이동목적", "실제입하일", "입하카톤수", "입하파렛트수", "입하수량",
        "제품 규격", "이동물품", "검수수량", "표본검수수량(미사용중)",
    ]

    def _past_cutoff(rec):
        d = _parse_date(rec.get("fields", {}).get("실제입하일"))
        return d is not None and d < since

    mov_records = get_records(
        TBL_MOVEMENT,
        fields=mov_fields,
        sort_field="실제입하일",
        sort_dir="desc",
        stop_predicate=_past_cutoff,
    )
    print(f"[mh_calculator]   movement fetched: {len(mov_records)} records (pre-filter)", flush=True)

    receiving_rows = []
    putaway_rows = []
    distinct_projects = set()
    project_cbm_map = {}
    basis_ctr = {}
    for rec in mov_records:
        f = rec.get("fields", {})
        d = _parse_date(f.get("실제입하일"))
        if d is None or d < since or d > until:
            continue
        if classify_movement(rec) != "receiving":
            continue
        mh, basis, qty_or_cbm = calc_receiving_mh(rec, sync_parts_lookup=sync_parts_lookup)
        if mh <= 0:
            continue
        basis_ctr[basis] = basis_ctr.get(basis, 0) + 1
        receiving_rows.append({
            "id": rec["id"], "basis": basis, "qty": qty_or_cbm, "mh_std": mh,
        })
        # 입고 M/H: spec→CBM 경로면 cbm 그대로 사용, 그 외엔 base 3분
        cbm = qty_or_cbm if basis.startswith("cbm-from-") else 0.0
        putaway_mh = calc_putaway_mh(rec, cbm=cbm)
        putaway_rows.append({"id": rec["id"], "cbm": cbm, "mh_std": putaway_mh})
        # 프로젝트 추적 (QC + 하차용)
        proj = _extract_project_code(f.get("이동물품"))
        if proj:
            distinct_projects.add(proj)
            if cbm > 0:
                project_cbm_map[proj] = project_cbm_map.get(proj, 0.0) + cbm
    print(f"[mh_calculator]   receiving basis: {basis_ctr}", flush=True)
    print(f"[mh_calculator]   distinct projects in period: {len(distinct_projects)}", flush=True)

    # 2) Picking: WMS_PickingTask 전체 (created time 필터링은 API에서 미제공 — 전체)
    print(f"[mh_calculator] fetching WMS_PickingTask...", flush=True)
    pick_records = get_records(TBL_PICKING_TASK)
    print(f"[mh_calculator]   picking_task: {len(pick_records)} records", flush=True)

    picking_rows = []
    for rec in pick_records:
        # 기간 필터: createdTime ≥ since (Airtable record metadata)
        created = _parse_date(rec.get("createdTime"))
        if created is None or created < since or created > until:
            continue
        mh, basis, qty = calc_picking_mh(rec)
        if mh <= 0:
            continue
        picking_rows.append({
            "id": rec["id"],
            "basis": basis,
            "qty": qty,
            "mh_std": mh,
        })

    # 3) TMS Shipment — 출하확정일 기준, 같은 sort+stop 패턴
    print(f"[mh_calculator] fetching TMS Shipment (sorted by 출하확정일 desc)...", flush=True)
    # project code: rollup (PNA*** string) — 출고검수 distinct project 추출용
    tms_fields = ["출하확정일", "배송 유형", "배송 방식", "project code"]

    def _tms_past_cutoff(rec):
        d = _parse_date(rec.get("fields", {}).get("출하확정일"))
        return d is not None and d < since

    tms_records = get_records(
        TBL_SHIPMENT,
        fields=tms_fields,
        sort_field="출하확정일",
        sort_dir="desc",
        stop_predicate=_tms_past_cutoff,
        base_id=TMS_BASE_ID,
        pat=TMS_PAT,
    )
    print(f"[mh_calculator]   TMS shipment fetched: {len(tms_records)} records (pre-filter)", flush=True)

    tms_rows = []
    distinct_outbound_projects = set()
    for rec in tms_records:
        f = rec.get("fields", {})
        d = _parse_date(f.get("출하확정일"))
        if d is None or d < since or d > until:
            continue
        mh, basis, mode = calc_tms_shipment_mh(rec)
        tms_rows.append({"id": rec["id"], "basis": basis, "mode": mode, "mh_std": mh})
        # 출고검수 distinct project 추출 (rollup이지만 사용자 sample 결과 string으로 옴)
        pc = f.get("project code")
        if isinstance(pc, list):
            for v in pc:
                if v:
                    distinct_outbound_projects.add(str(v).strip())
        elif pc:
            distinct_outbound_projects.add(str(pc).strip())

    print(f"[mh_calculator] receiving={len(receiving_rows)} | picking={len(picking_rows)} | tms={len(tms_rows)} | outbound_projects={len(distinct_outbound_projects)}", flush=True)

    if args.dry_run:
        print(f"[mh_calculator] --dry-run set: skipping file write", flush=True)
        total = sum(r["mh_std"] for r in receiving_rows) + sum(r["mh_std"] for r in tms_rows)
        print(f"[mh_calculator] total M/H_std (recv+tms, excl pick/qc) = {total/60:.1f} MH", flush=True)
        return

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"MH-{iso_week(until)}.md"
    generate_report(receiving_rows, putaway_rows, picking_rows, tms_rows,
                    distinct_projects, distinct_outbound_projects,
                    project_cbm_map,
                    since, until, out_path)
    print(f"[mh_calculator] wrote: {out_path}", flush=True)


if __name__ == "__main__":
    main()
