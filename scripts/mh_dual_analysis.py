"""
mh_dual_analysis.py
────────────────────────────────────────────────────────────────────────────────
IBSA sync_movement에서 두 가지 M/H 산출 방식을 병렬 계산 후 주차별로 비교.

Method A (CBM-driven):
  - 입하: min(CAP, max(FLOOR, CBM×4.0)) × 1.15
  - 입고: (3.0 + min(2.0, CBM×7.0)) × 1.15
  - 검수: 2.5 × 1.15 × distinct_project 수 (주차 합산)

Method B (Cycle Time):
  - 입하: Method A와 동일 (시작 타임스탬프 없음)
  - 검수: 시안검수완료시간 − 입하완료처리시간 (분, 유효: 0 < x < 180)
  - 입고: 입고수량입력시간 − 입하완료처리시간 (분, 병렬 시작, 유효: 0 < x < 180)
  - 유효 타임스탬프 없으면 standard fallback 사용

공정 흐름:
  입하완료처리시간 ─┬─→ 시안검수완료시간  (검수 interval)
                    └─→ 입고수량입력시간  (입고 interval, 병렬)

사용법:
  python scripts/mh_dual_analysis.py                        # 전체 (2026-01-01~)
  python scripts/mh_dual_analysis.py --since 2026-03-01
  python scripts/mh_dual_analysis.py --limit 20             # 20건 테스트
  python scripts/mh_dual_analysis.py --dry-run              # 파일 미생성

환경변수:
  AIRTABLE_IBSA_PAT  — IBSA 베이스 PAT
  AIRTABLE_WMS_PAT   — WMS sync_parts lookup PAT
"""

import argparse
import datetime
import math
import os
import re
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

# ── 상수 (mh_calculator.py / mh_backfill_to_ibsa.py 동기) ──────────────────────
VERSION = "v2026-05-cal3"

PFD_ALLOWANCE = 1.15
RECEIVING_MIN_PER_CBM = 4.0
RECEIVING_MIN_THICKNESS_MM = 3.0
RECEIVING_FLOOR_STD_MIN = 0.5   # 30초 floor (PFD 전 표준)
RECEIVING_CAP_STD_MIN   = 5.0   # 최대 5분 cap (PFD 전 표준)
PUTAWAY_BASE_MIN = 3.0
PUTAWAY_MAX_MIN = 5.0
PUTAWAY_PER_CBM_MIN = 7.0
QC_STD_PER_PROJECT = 2.5

CYCLE_MAX_MIN = 180.0   # 인터벌 이상치 필터: 180분 초과는 유휴 오염으로 제외

# ── Airtable 설정 ──────────────────────────────────────────────────────────────
IBSA_BASE  = "app6DGHCPI3Yh3IFS"
IBSA_TABLE = "tblhzYiltSBm6vxBz"  # sync_movement

WMS_BASE       = "appLui4ZR5HWcQRri"
WMS_SYNC_PARTS = "tblzJh0V4hdo4Xbvx"
WMS_SP_CODE    = "fld8gjySjm4XkCpMc"
WMS_SP_SPEC    = "fldRseOMNseg15D6R"

# Field IDs — IBSA sync_movement
F = {
    "이동목적":         "fldru408fCLHn9v3k",
    "입하일자":         "fldcCmgZNTKUWpL9J",
    "CBM":             "fldTHmNEPNhcIX5AQ",
    "입하수량":         "fldXj3bp2ioe8awCd",
    "제품_규격":        "fldRhOJuPnE7ZRk6L",
    "입하예정물품":     "fldEMORus5VTtQRVX",
    "project_name":    "fld8Prbt0HqtRSIWP",
    "입하완료처리시간": "fld5pwd5dVYqW4Bdl",
    "시안검수완료시간": "fldPxJvu4iIFcxp7w",
    "입고수량입력시간": "fldnvnZVsuUPgv1Mn",
}

IBSA_PAT = os.environ.get("AIRTABLE_IBSA_PAT", "")
WMS_PAT  = os.environ.get("AIRTABLE_WMS_PAT") or os.environ.get("AIRTABLE_PAT", "")


# ── CBM 헬퍼 ──────────────────────────────────────────────────────────────────
def parse_dims_mm(raw):
    if not raw:
        return None
    cleaned = re.split(r"펼침", str(raw))[0]
    cleaned = re.sub(r"mm", "", cleaned, flags=re.IGNORECASE)
    nums = [float(n) for n in re.findall(r"[\d.]+", cleaned) if float(n) > 0]
    if len(nums) >= 3:
        return (nums[0], nums[1], nums[2])
    if len(nums) == 2:
        return (nums[0], nums[1], RECEIVING_MIN_THICKNESS_MM)
    return None


def spec_to_cbm(spec, qty):
    dims = parse_dims_mm(spec)
    if dims is None or qty <= 0:
        return 0.0
    w, h, d = dims
    return (w / 1000) * (h / 1000) * (d / 1000) * qty


def extract_pt_code(이동물품):
    if not 이동물품:
        return ""
    first = str(이동물품).split("||")[0].strip()
    dash = first.find("-")
    return first[:dash] if dash != -1 else first


def cbm_for_record(fields, sync_parts):
    """레코드에서 CBM 산출. 이미 계산된 CBM 필드 우선, 없으면 규격 파싱."""
    # 이미 저장된 CBM 값 사용
    stored = fields.get(F["CBM"])
    if stored and float(stored) > 0:
        return float(stored)
    # 규격 직접 파싱
    qty  = float(fields.get(F["입하수량"]) or 0)
    spec = (fields.get(F["제품_규격"]) or "").strip()
    if qty > 0 and spec:
        cbm = spec_to_cbm(spec, qty)
        if cbm > 0:
            return cbm
    # sync_parts fallback
    if qty > 0 and sync_parts:
        pt = extract_pt_code(fields.get(F["입하예정물품"]))
        if pt and pt in sync_parts:
            cbm = spec_to_cbm(sync_parts[pt], qty)
            if cbm > 0:
                return cbm
    return 0.0


# ── M/H 계산 헬퍼 ─────────────────────────────────────────────────────────────
def receiving_mh(cbm):
    raw = cbm * RECEIVING_MIN_PER_CBM
    return min(RECEIVING_CAP_STD_MIN, max(RECEIVING_FLOOR_STD_MIN, raw)) * PFD_ALLOWANCE


def putaway_mh(cbm):
    if cbm <= 0:
        return PUTAWAY_BASE_MIN * PFD_ALLOWANCE
    extra = min(PUTAWAY_MAX_MIN - PUTAWAY_BASE_MIN, cbm * PUTAWAY_PER_CBM_MIN)
    return (PUTAWAY_BASE_MIN + extra) * PFD_ALLOWANCE


def diff_min(ts_start, ts_end):
    """ISO 8601 두 타임스탬프 → 분 차이. 실패 시 None."""
    try:
        fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
        fmt2 = "%Y-%m-%dT%H:%M:%SZ"
        def parse(s):
            try:
                return datetime.datetime.strptime(s, fmt)
            except ValueError:
                return datetime.datetime.strptime(s, fmt2)
        a = parse(ts_start)
        b = parse(ts_end)
        delta = (b - a).total_seconds() / 60.0
        return delta
    except Exception:
        return None


def iso_week(date_str):
    """'2026-01-05' → 'W01'"""
    try:
        d = datetime.date.fromisoformat(date_str[:10])
        return f"W{d.isocalendar()[1]:02d}"
    except Exception:
        return "W??"


# ── Airtable fetch ─────────────────────────────────────────────────────────────
def load_sync_parts():
    if not WMS_PAT:
        print("[WARN] AIRTABLE_WMS_PAT 미설정 → sync_parts fallback 비활성", file=sys.stderr)
        return {}
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {WMS_PAT}"})
    lookup, offset = {}, None
    while True:
        params = {"pageSize": 100, "returnFieldsByFieldId": "true",
                  "fields[]": [WMS_SP_CODE, WMS_SP_SPEC]}
        if offset:
            params["offset"] = offset
        resp = session.get(f"https://api.airtable.com/v0/{WMS_BASE}/{WMS_SYNC_PARTS}",
                           params=params, timeout=90)
        resp.raise_for_status()
        data = resp.json()
        for r in data.get("records", []):
            f = r.get("fields", {})
            code = str(f.get(WMS_SP_CODE) or "").strip()
            spec = str(f.get(WMS_SP_SPEC) or "").strip()
            if code:
                lookup[code] = spec
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return lookup


def fetch_ibsa_records(since=None, limit=None):
    if not IBSA_PAT:
        print("ERROR: AIRTABLE_IBSA_PAT 환경변수 미설정", file=sys.stderr)
        sys.exit(2)

    conditions = ["{이동목적}='생산산출'"]
    if since:
        conditions.append(f"IS_AFTER({{입하일자}},'{since}')")
    formula = "AND(" + ",".join(conditions) + ")" if len(conditions) > 1 else conditions[0]

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {IBSA_PAT}"})
    fetch_fields = list(F.values())

    records, offset = [], None
    while True:
        params = {
            "pageSize": 100,
            "returnFieldsByFieldId": "true",
            "filterByFormula": formula,
            "fields[]": fetch_fields,
        }
        if offset:
            params["offset"] = offset
        resp = session.get(f"https://api.airtable.com/v0/{IBSA_BASE}/{IBSA_TABLE}",
                           params=params, timeout=90)
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        if limit and len(records) >= limit:
            records = records[:limit]
            break
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records


# ── 주차별 집계 ────────────────────────────────────────────────────────────────
def aggregate(records, sync_parts):
    """
    records → weekly_data dict.
    주차별: 건수, CBM합계, Method A MH, Method B MH, 인터벌 목록.
    """
    weekly = defaultdict(lambda: {
        "건수": 0,
        "cbm_sum": 0.0,
        "A_입하": 0.0, "A_입고": 0.0,
        "A_검수_projects": set(),      # distinct project names
        "B_입하": 0.0, "B_검수": 0.0, "B_입고": 0.0,
        "검수_intervals": [],          # valid cycle intervals (min)
        "입고_intervals": [],
        "검수_fallback_count": 0,
        "입고_fallback_count": 0,
        "검수_qty_pairs": [],          # (qty, actual_min) — cycle-time 기반 qty 정규화용
        "입고_qty_pairs": [],
    })

    for rec in records:
        fields = rec.get("fields", {})
        date_str = fields.get(F["입하일자"])
        if not date_str:
            continue
        week = iso_week(str(date_str))
        w = weekly[week]
        w["건수"] += 1

        cbm = cbm_for_record(fields, sync_parts)
        w["cbm_sum"] += cbm

        # ── Method A ──
        w["A_입하"] += receiving_mh(cbm)
        w["A_입고"] += putaway_mh(cbm)
        proj = (fields.get(F["project_name"]) or "").strip()
        if proj:
            w["A_검수_projects"].add(proj)

        # ── Method B (입하 = A와 동일) ──
        w["B_입하"] += receiving_mh(cbm)

        ts_입하 = fields.get(F["입하완료처리시간"])
        ts_검수 = fields.get(F["시안검수완료시간"])
        ts_입고 = fields.get(F["입고수량입력시간"])

        qty = float(fields.get(F["입하수량"]) or 0)

        # 검수 interval
        if ts_입하 and ts_검수:
            d = diff_min(ts_입하, ts_검수)
            if d is not None and 0 < d < CYCLE_MAX_MIN:
                w["검수_intervals"].append(d)
                w["B_검수"] += d
                if qty >= 5:
                    w["검수_qty_pairs"].append((qty, d))
            else:
                w["B_검수"] += QC_STD_PER_PROJECT * PFD_ALLOWANCE
                w["검수_fallback_count"] += 1
        else:
            w["B_검수"] += QC_STD_PER_PROJECT * PFD_ALLOWANCE
            w["검수_fallback_count"] += 1

        # 입고 interval (병렬 — 시작 = 입하완료처리시간)
        if ts_입하 and ts_입고:
            d = diff_min(ts_입하, ts_입고)
            if d is not None and 0 < d < CYCLE_MAX_MIN:
                w["입고_intervals"].append(d)
                w["B_입고"] += d
                if qty >= 5:
                    w["입고_qty_pairs"].append((qty, d))
            else:
                w["B_입고"] += putaway_mh(cbm)
                w["입고_fallback_count"] += 1
        else:
            w["B_입고"] += putaway_mh(cbm)
            w["입고_fallback_count"] += 1

    return weekly


# ── PT코드별 cycle-time 집계 ───────────────────────────────────────────────────
def aggregate_by_pt(records):
    """
    PT코드별 검수·입고 cycle-time (qty, actual_min) 쌍 수집.
    qty < 5인 레코드는 제외 (소량 특이값 방지).
    Returns: dict[pt_code] -> {"검수": [(qty, min), ...], "입고": [(qty, min), ...]}
    """
    pt = defaultdict(lambda: {"검수": [], "입고": []})

    for rec in records:
        fields = rec.get("fields", {})
        pt_code = extract_pt_code(fields.get(F["입하예정물품"]))
        if not pt_code:
            continue
        qty = float(fields.get(F["입하수량"]) or 0)
        if qty < 5:
            continue

        ts_입하 = fields.get(F["입하완료처리시간"])
        ts_검수 = fields.get(F["시안검수완료시간"])
        ts_입고 = fields.get(F["입고수량입력시간"])

        if ts_입하 and ts_검수:
            d = diff_min(ts_입하, ts_검수)
            if d is not None and 0 < d < CYCLE_MAX_MIN:
                pt[pt_code]["검수"].append((qty, d))

        if ts_입하 and ts_입고:
            d = diff_min(ts_입하, ts_입고)
            if d is not None and 0 < d < CYCLE_MAX_MIN:
                pt[pt_code]["입고"].append((qty, d))

    return pt


def _rate_p50(pairs):
    """(qty, min) 쌍 목록 → 분/100개 p50. 쌍이 없으면 None."""
    rates = [m / q * 100 for q, m in pairs if q > 0]
    return statistics.median(rates) if rates else None


def _min_p50(pairs):
    """(qty, min) 쌍 목록 → 실측분 p50."""
    mins = [m for _, m in pairs]
    return statistics.median(mins) if mins else None


# ── 리포트 생성 ────────────────────────────────────────────────────────────────
def build_report(weekly, args_since):
    lines = []
    lines.append(f"# WMS M/H 이중 방식 비교 — 2026 W01–W21")
    lines.append(f"")
    lines.append(f"**VERSION**: {VERSION}  ")
    lines.append(f"**기간**: {args_since or '2026-01-01'} ~ 2026-05-21  ")
    lines.append(f"**방식**: Method A (CBM-driven) vs Method B (Cycle Time)  ")
    lines.append(f"")
    lines.append("## 공정 흐름")
    lines.append("```")
    lines.append("입하완료처리시간 ─┬─→ 시안검수완료시간  (검수 interval)")
    lines.append("                  └─→ 입고수량입력시간  (입고 interval, 병렬)")
    lines.append("```")
    lines.append("입하 시작 타임스탬프 없음 → 입하는 양 방식 모두 CBM 공식 (floor 0.5분, cap 5.0분 × PFD).")
    lines.append("")

    # 주차 정렬
    weeks = sorted(weekly.keys())

    # 합계 초기화
    tot = {k: 0.0 for k in ["A_입하","A_검수","A_입고","B_입하","B_검수","B_입고",
                              "건수","cbm_sum"]}
    tot["검수_intervals"] = []
    tot["입고_intervals"] = []
    tot["검수_qty_pairs"] = []
    tot["입고_qty_pairs"] = []

    # 주차별 테이블
    lines.append("## 주차별 집계 (검수·입고: cycle-time 실측 | 입하: CBM-driven)")
    lines.append("")
    header = ("| 주차 | 건수 | CBM합계 "
              "| 입하(CBM) | 검수p50(분) | 검수p50(분/100개) | 입고p50(분) | 입고p50(분/100개) "
              "| 검수커버리지 | 입고커버리지 |")
    sep    = ("|------|------|---------|"
              "-----------|------------|-----------------|------------|-----------------|"
              "------------|------------|")
    lines.append(header)
    lines.append(sep)

    for wk in weeks:
        w = weekly[wk]
        n   = w["건수"]
        cbm = w["cbm_sum"]

        a_recv_h = w["A_입하"] / 60

        qc_intervals = w["검수_intervals"]
        pa_intervals = w["입고_intervals"]
        qc_p50_min  = f"{statistics.median(qc_intervals):.1f}" if qc_intervals else "—"
        pa_p50_min  = f"{statistics.median(pa_intervals):.1f}" if pa_intervals else "—"

        qc_rate = _rate_p50(w["검수_qty_pairs"])
        pa_rate = _rate_p50(w["입고_qty_pairs"])
        qc_p50_rate = f"{qc_rate:.2f}" if qc_rate is not None else "—"
        pa_p50_rate = f"{pa_rate:.2f}" if pa_rate is not None else "—"

        qc_cov = len(qc_intervals) / n * 100 if n else 0
        pa_cov = len(pa_intervals) / n * 100 if n else 0

        lines.append(
            f"| {wk} | {n} | {cbm:.1f} "
            f"| {a_recv_h:.2f}h | {qc_p50_min} | {qc_p50_rate} | {pa_p50_min} | {pa_p50_rate} "
            f"| {qc_cov:.0f}% | {pa_cov:.0f}% |"
        )

        # 누적
        tot["건수"]   += n
        tot["cbm_sum"] += cbm
        tot["A_입하"] += w["A_입하"]
        tot["검수_intervals"].extend(qc_intervals)
        tot["입고_intervals"].extend(pa_intervals)
        tot["검수_qty_pairs"].extend(w["검수_qty_pairs"])
        tot["입고_qty_pairs"].extend(w["입고_qty_pairs"])

    # 합계 행
    tot_n      = tot["건수"]
    qc_p50_all = f"{statistics.median(tot['검수_intervals']):.1f}" if tot["검수_intervals"] else "—"
    pa_p50_all = f"{statistics.median(tot['입고_intervals']):.1f}" if tot["입고_intervals"] else "—"
    qc_rate_all = _rate_p50(tot["검수_qty_pairs"])
    pa_rate_all = _rate_p50(tot["입고_qty_pairs"])
    qc_rate_str = f"{qc_rate_all:.2f}" if qc_rate_all is not None else "—"
    pa_rate_str = f"{pa_rate_all:.2f}" if pa_rate_all is not None else "—"
    qc_cov_all = len(tot["검수_intervals"]) / tot_n * 100 if tot_n else 0
    pa_cov_all = len(tot["입고_intervals"]) / tot_n * 100 if tot_n else 0
    lines.append(
        f"| **합계** | **{tot_n}** | **{tot['cbm_sum']:.1f}** "
        f"| **{tot['A_입하']/60:.1f}h** | **{qc_p50_all}** | **{qc_rate_str}** | **{pa_p50_all}** | **{pa_rate_str}** "
        f"| {qc_cov_all:.0f}% | {pa_cov_all:.0f}% |"
    )

    lines.append("")
    lines.append("> **입하**: CBM-driven 영구 표준 (h). **검수·입고**: cycle-time 실측 — p50(분) / p50(분/100개).")
    lines.append("> 커버리지 = 유효 타임스탬프 보유 레코드 비율. qty < 5 레코드는 rate 산출 제외.")
    lines.append("")

    # 요약 섹션
    lines.append("## 운영 방식 요약")
    lines.append("")
    lines.append("| 공정 | 방식 | 기준값 | 비고 |")
    lines.append("|------|------|--------|------|")
    lines.append(f"| 입하 | CBM-driven (영구) | {RECEIVING_MIN_PER_CBM} min/CBM × PFD | 시작 타임스탬프 없음 |")
    lines.append(f"| 검수 | cycle-time 실측 | p50 {qc_p50_all}분 / {qc_rate_str}분/100개 | PT코드별 모델로 진화 예정 |")
    lines.append(f"| 입고 | cycle-time 실측 | p50 {pa_p50_all}분 / {pa_rate_str}분/100개 | PT코드별 모델로 진화 예정 |")
    lines.append("")
    lines.append("## 상수 (이번 버전)")
    lines.append("```")
    lines.append(f"RECEIVING_MIN_PER_CBM   = {RECEIVING_MIN_PER_CBM}  min/CBM")
    lines.append(f"RECEIVING_FLOOR_STD_MIN = {RECEIVING_FLOOR_STD_MIN}   min (30초, PFD 전)")
    lines.append(f"RECEIVING_CAP_STD_MIN   = {RECEIVING_CAP_STD_MIN}   min (5분, PFD 전) → 실체감 5.75분")
    lines.append(f"PUTAWAY_BASE_MIN        = {PUTAWAY_BASE_MIN}   min")
    lines.append(f"PUTAWAY_MAX_MIN         = {PUTAWAY_MAX_MIN}   min → 실체감 5.75분")
    lines.append(f"QC_STD_PER_PROJECT      = {QC_STD_PER_PROJECT}   min/project")
    lines.append(f"PFD_ALLOWANCE           = {PFD_ALLOWANCE}")
    lines.append(f"CYCLE_MAX_MIN           = {CYCLE_MAX_MIN}   min (이상치 필터)")
    lines.append("```")

    return "\n".join(lines)


# ── PT코드별 리포트 ────────────────────────────────────────────────────────────
def build_pt_report(pt_data):
    """
    PT코드별 검수·입고 cycle-time 집계 → Markdown 테이블.
    N≥30 ✅ / N 10-29 ⚠️ / N<10 ❌
    관측 수 기준 내림차순 정렬 (검수N + 입고N 합산).
    """
    rows = []
    for pt_code, d in pt_data.items():
        qc_pairs = d["검수"]
        pa_pairs = d["입고"]
        qc_n = len(qc_pairs)
        pa_n = len(pa_pairs)
        if qc_n == 0 and pa_n == 0:
            continue
        rows.append({
            "pt": pt_code,
            "qc_n": qc_n,
            "qc_p50_min":  _min_p50(qc_pairs),
            "qc_p50_rate": _rate_p50(qc_pairs),
            "pa_n": pa_n,
            "pa_p50_min":  _min_p50(pa_pairs),
            "pa_p50_rate": _rate_p50(pa_pairs),
        })

    rows.sort(key=lambda r: r["qc_n"] + r["pa_n"], reverse=True)

    def status(n_qc, n_pa):
        n = min(n_qc, n_pa) if n_qc and n_pa else max(n_qc, n_pa)
        if n >= 30:
            return "✅"
        if n >= 10:
            return "⚠️"
        return "❌"

    def fmt(v, decimals=2):
        return f"{v:.{decimals}f}" if v is not None else "—"

    lines = []
    lines.append("## PT코드별 cycle-time 집계 (검수·입고)")
    lines.append("")
    lines.append("> 입하는 CBM-driven 영구 표준. 검수·입고만 cycle-time 운영 대상.")
    lines.append("> ✅ N≥30 → 운영 기준 즉시 사용 가능 | ⚠️ N 10-29 → 수집 중 | ❌ N<10 → 데이터 부족")
    lines.append("")
    lines.append("| 상태 | PT코드 | 검수N | 검수p50(분) | 검수p50(분/100개) | 입고N | 입고p50(분) | 입고p50(분/100개) |")
    lines.append("|------|--------|-------|------------|-----------------|-------|------------|-----------------|")

    ready_count = 0
    for r in rows:
        st = status(r["qc_n"], r["pa_n"])
        if st == "✅":
            ready_count += 1
        lines.append(
            f"| {st} | {r['pt']} "
            f"| {r['qc_n']} | {fmt(r['qc_p50_min'], 1)} | {fmt(r['qc_p50_rate'])} "
            f"| {r['pa_n']} | {fmt(r['pa_p50_min'], 1)} | {fmt(r['pa_p50_rate'])} |"
        )

    lines.append("")
    lines.append(f"> **운영 기준 사용 가능 PT코드**: {ready_count}개 (N≥30 기준)")
    return "\n".join(lines)


# ── main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2026-01-01", help="조회 시작일 (YYYY-MM-DD)")
    ap.add_argument("--limit", type=int, help="처리 최대 건수 (테스트용)")
    ap.add_argument("--dry-run", action="store_true", help="파일 미생성, 콘솔 출력만")
    args = ap.parse_args()

    print("=== mh_dual_analysis.py ===")
    print(f"  VERSION:  {VERSION}")
    print(f"  since:    {args.since}")
    print(f"  limit:    {args.limit or '(none)'}")
    print(f"  dry-run:  {args.dry_run}")
    print()

    print("[1/5] sync_parts 로드...")
    sync_parts = load_sync_parts()
    print(f"      loaded {len(sync_parts)} parts")

    print(f"[2/5] IBSA records 조회 (since={args.since})...")
    records = fetch_ibsa_records(since=args.since, limit=args.limit)
    print(f"      {len(records)} records")
    if not records:
        print("데이터 없음 — 종료")
        return

    print("[3/5] 주차별 집계...")
    weekly = aggregate(records, sync_parts)
    print(f"      {len(weekly)} 주차")

    print("[4/5] PT코드별 집계...")
    pt_data = aggregate_by_pt(records)
    ready = sum(1 for d in pt_data.values()
                if min(len(d["검수"]), len(d["입고"])) >= 30)
    print(f"      {len(pt_data)} PT코드 / ✅ 운영 가능 {ready}개 (N≥30)")

    print("[5/5] 리포트 생성...")
    today = datetime.date.today().isoformat()
    report = build_report(weekly, args.since) + "\n\n" + build_pt_report(pt_data)

    if args.dry_run:
        print("\n--- REPORT PREVIEW (dry-run) ---")
        print(report[:4000])
        if len(report) > 4000:
            print(f"... (총 {len(report)}자)")
    else:
        out_path = Path("outputs") / f"MH_cycle_time_{today}.md"
        out_path.parent.mkdir(exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"  → {out_path} 저장 완료")

    print("\n=== 완료 ===")


if __name__ == "__main__":
    main()
