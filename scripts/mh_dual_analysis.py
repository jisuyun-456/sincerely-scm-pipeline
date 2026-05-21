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

        # 검수 interval
        if ts_입하 and ts_검수:
            d = diff_min(ts_입하, ts_검수)
            if d is not None and 0 < d < CYCLE_MAX_MIN:
                w["검수_intervals"].append(d)
                w["B_검수"] += d
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
            else:
                w["B_입고"] += putaway_mh(cbm)
                w["입고_fallback_count"] += 1
        else:
            w["B_입고"] += putaway_mh(cbm)
            w["입고_fallback_count"] += 1

    return weekly


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

    # 주차별 테이블
    lines.append("## 주차별 집계")
    lines.append("")
    header = ("| 주차 | 건수 | CBM합계 "
              "| A_입하 | A_검수 | A_입고 | **A_합계** "
              "| B_입하 | B_검수 | B_입고 | **B_합계** "
              "| 검수p50 | 입고p50 "
              "| 검수커버리지 | 입고커버리지 |")
    sep    = ("|------|------|---------|"
              "--------|--------|--------|-----------|"
              "--------|--------|--------|-----------|"
              "---------|---------|"
              "------------|------------|")
    lines.append(header)
    lines.append(sep)

    for wk in weeks:
        w = weekly[wk]
        n    = w["건수"]
        cbm  = w["cbm_sum"]

        a_recv = w["A_입하"]
        a_qc   = len(w["A_검수_projects"]) * QC_STD_PER_PROJECT * PFD_ALLOWANCE
        a_put  = w["A_입고"]
        a_tot  = a_recv + a_qc + a_put

        b_recv = w["B_입하"]
        b_qc   = w["B_검수"]
        b_put  = w["B_입고"]
        b_tot  = b_recv + b_qc + b_put

        qc_intervals = w["검수_intervals"]
        pa_intervals = w["입고_intervals"]
        qc_p50 = f"{statistics.median(qc_intervals):.1f}" if qc_intervals else "—"
        pa_p50 = f"{statistics.median(pa_intervals):.1f}" if pa_intervals else "—"

        qc_cov = len(qc_intervals) / n * 100 if n else 0
        pa_cov = len(pa_intervals) / n * 100 if n else 0

        lines.append(
            f"| {wk} | {n} | {cbm:.1f} "
            f"| {a_recv/60:.2f} | {a_qc/60:.2f} | {a_put/60:.2f} | **{a_tot/60:.2f}** "
            f"| {b_recv/60:.2f} | {b_qc/60:.2f} | {b_put/60:.2f} | **{b_tot/60:.2f}** "
            f"| {qc_p50} | {pa_p50} "
            f"| {qc_cov:.0f}% | {pa_cov:.0f}% |"
        )

        # 누적
        tot["건수"]   += n
        tot["cbm_sum"] += cbm
        tot["A_입하"] += a_recv; tot["A_검수"] += a_qc; tot["A_입고"] += a_put
        tot["B_입하"] += b_recv; tot["B_검수"] += b_qc; tot["B_입고"] += b_put
        tot["검수_intervals"].extend(qc_intervals)
        tot["입고_intervals"].extend(pa_intervals)

    # 합계 행
    a_tot_all = tot["A_입하"] + tot["A_검수"] + tot["A_입고"]
    b_tot_all = tot["B_입하"] + tot["B_검수"] + tot["B_입고"]
    qc_p50_all = f"{statistics.median(tot['검수_intervals']):.1f}" if tot["검수_intervals"] else "—"
    pa_p50_all = f"{statistics.median(tot['입고_intervals']):.1f}" if tot["입고_intervals"] else "—"
    tot_n = tot["건수"]
    qc_cov_all = len(tot["검수_intervals"]) / tot_n * 100 if tot_n else 0
    pa_cov_all = len(tot["입고_intervals"]) / tot_n * 100 if tot_n else 0
    lines.append(
        f"| **합계** | **{tot_n}** | **{tot['cbm_sum']:.1f}** "
        f"| **{tot['A_입하']/60:.1f}** | **{tot['A_검수']/60:.1f}** | **{tot['A_입고']/60:.1f}** | **{a_tot_all/60:.1f}** "
        f"| **{tot['B_입하']/60:.1f}** | **{tot['B_검수']/60:.1f}** | **{tot['B_입고']/60:.1f}** | **{b_tot_all/60:.1f}** "
        f"| {qc_p50_all} | {pa_p50_all} "
        f"| {qc_cov_all:.0f}% | {pa_cov_all:.0f}% |"
    )

    lines.append("")
    lines.append("> MH 단위는 **시간(h)**. 검수·입고 커버리지 = 유효 타임스탬프 보유 레코드 비율.")
    lines.append("")

    # 요약 섹션
    diff_pct = (b_tot_all - a_tot_all) / a_tot_all * 100 if a_tot_all else 0
    lines.append("## 방식별 요약 비교")
    lines.append("")
    lines.append("| 구분 | Method A (CBM-driven) | Method B (Cycle Time) | 차이 |")
    lines.append("|------|----------------------|----------------------|------|")
    lines.append(f"| 입하 MH | {tot['A_입하']/60:.1f}h | {tot['B_입하']/60:.1f}h | 동일 (CBM) |")
    lines.append(f"| 검수 MH | {tot['A_검수']/60:.1f}h | {tot['B_검수']/60:.1f}h | {(tot['B_검수']-tot['A_검수'])/60:+.1f}h |")
    lines.append(f"| 입고 MH | {tot['A_입고']/60:.1f}h | {tot['B_입고']/60:.1f}h | {(tot['B_입고']-tot['A_입고'])/60:+.1f}h |")
    lines.append(f"| **합계** | **{a_tot_all/60:.1f}h** | **{b_tot_all/60:.1f}h** | **{diff_pct:+.1f}%** |")
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

    print("[1/4] sync_parts 로드...")
    sync_parts = load_sync_parts()
    print(f"      loaded {len(sync_parts)} parts")

    print(f"[2/4] IBSA records 조회 (since={args.since})...")
    records = fetch_ibsa_records(since=args.since, limit=args.limit)
    print(f"      {len(records)} records")
    if not records:
        print("데이터 없음 — 종료")
        return

    print("[3/4] 집계 중...")
    weekly = aggregate(records, sync_parts)
    print(f"      {len(weekly)} 주차")

    # 검증 샘플 출력
    print("\n  [preview] 처음 3개 레코드:")
    for r in records[:3]:
        f = r.get("fields", {})
        cbm = cbm_for_record(f, sync_parts)
        ts_in = f.get(F["입하완료처리시간"])
        ts_qc = f.get(F["시안검수완료시간"])
        ts_pa = f.get(F["입고수량입력시간"])
        d_qc = diff_min(ts_in, ts_qc) if ts_in and ts_qc else None
        d_pa = diff_min(ts_in, ts_pa) if ts_in and ts_pa else None
        print(f"    {r['id']}: CBM={cbm:.4f} "
              f"A_recv={receiving_mh(cbm):.2f}분 "
              f"검수Δ={f'{d_qc:.1f}분' if d_qc else '—'} "
              f"입고Δ={f'{d_pa:.1f}분' if d_pa else '—'}")

    print("\n[4/4] 리포트 생성...")
    report = build_report(weekly, args.since)

    if args.dry_run:
        print("\n--- REPORT PREVIEW (dry-run) ---")
        print(report[:3000])
        if len(report) > 3000:
            print(f"... (총 {len(report)}자)")
    else:
        out_path = Path("outputs") / "MH_dual_W01-W21_2026.md"
        out_path.parent.mkdir(exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"  → {out_path} 저장 완료")

    print("\n=== 완료 ===")


if __name__ == "__main__":
    main()
