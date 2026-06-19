"""
mh_phase2_board.py
──────────────────────────────────────────────────────────────────────────────
Phase 2 추적 보드: ⚠️ PT코드 → ✅ 전환 진행도 + 커버리지 갭 진단

사용법:
  python scripts/mh_phase2_board.py
  python scripts/mh_phase2_board.py --top 20
  python scripts/mh_phase2_board.py --dry-run

환경변수:
  AIRTABLE_IBSA_PAT  — IBSA 베이스 PAT
"""

import argparse
import datetime
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

# ── 상수 ────────────────────────────────────────────────────────────────────
SINCE = "2026-03-01"
CYCLE_MAX_MIN = 180.0
TARGET_N      = 30    # ✅ 운영 기준
WARN_N        = 10    # ⚠️ 수집 중 기준
CYCLE_MAX_MIN = 180.0
CYCLE_MIN_MIN = -10.0  # 입고 한정: 입고수량입력이 입하완료 전 기록 패턴 허용

IBSA_BASE  = "app6DGHCPI3Yh3IFS"
IBSA_TABLE = "tblhzYiltSBm6vxBz"

F = {
    "이동목적":         "fldru408fCLHn9v3k",
    "입하일자":         "fldcCmgZNTKUWpL9J",
    "입하수량":         "fldXj3bp2ioe8awCd",
    "입하예정물품":     "fldEMORus5VTtQRVX",
    "입하완료처리시간": "fld5pwd5dVYqW4Bdl",
    "시안검수완료시간": "fldPxJvu4iIFcxp7w",
    "입고수량입력시간": "fldnvnZVsuUPgv1Mn",
}

IBSA_PAT = os.environ.get("AIRTABLE_IBSA_PAT", "")


# ── 헬퍼 ────────────────────────────────────────────────────────────────────
def diff_min(ts_start, ts_end):
    try:
        fmt  = "%Y-%m-%dT%H:%M:%S.%fZ"
        fmt2 = "%Y-%m-%dT%H:%M:%SZ"
        def p(s):
            try:    return datetime.datetime.strptime(s, fmt)
            except: return datetime.datetime.strptime(s, fmt2)
        return (p(ts_end) - p(ts_start)).total_seconds() / 60.0
    except:
        return None


def extract_pt(v):
    if not v:
        return ""
    first = str(v).split("||")[0].strip()
    dash = first.find("-")
    return first[:dash] if dash != -1 else first


def iso_week(date_str):
    try:
        d = datetime.date.fromisoformat(str(date_str)[:10])
        return f"W{d.isocalendar()[1]:02d}"
    except:
        return "W??"


def status(n):
    if n >= TARGET_N: return "✅"
    if n >= WARN_N:   return "⚠️"
    return "❌"


# ── Airtable fetch ───────────────────────────────────────────────────────────
def fetch_records():
    if not IBSA_PAT:
        print("ERROR: AIRTABLE_IBSA_PAT 미설정", file=sys.stderr)
        sys.exit(2)
    formula = "AND({이동목적}='생산산출',IS_AFTER({입하일자},'" + SINCE + "'))"
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {IBSA_PAT}"})
    records, offset = [], None
    while True:
        params = {
            "pageSize": 100,
            "returnFieldsByFieldId": "true",
            "filterByFormula": formula,
            "fields[]": list(F.values()),
        }
        if offset:
            params["offset"] = offset
        resp = session.get(f"https://api.airtable.com/v0/{IBSA_BASE}/{IBSA_TABLE}",
                           params=params, timeout=90)
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records


# ── PT별 상세 집계 ────────────────────────────────────────────────────────────
def aggregate_pt_detailed(records):
    """
    PT코드별:
    - valid 검수/입고 건수 (타임스탬프 + qty>=5 + 0<d<180)
    - raw 타임스탬프 건수 (qty·시간 필터 전)
    - 누락·이상치 분해
    - 주차별 valid 건수 (velocity 계산용)
    """
    pt = defaultdict(lambda: {
        "total": 0,
        # 타임스탬프 보유 여부
        "has_ts_검수": 0,
        "has_ts_입고": 0,
        # 유효 cycle-time (qty>=5, 0<d<180)
        "valid_검수": 0,
        "valid_입고": 0,
        # 누락/이상치 분해
        "over180_검수": 0,
        "over180_입고": 0,
        "neg_d_검수": 0,
        "neg_d_입고": 0,
        "no_ts_입하": 0,
        "qty_lt5": 0,   # qty < 5 (rate 계산 제외)
        # 주차별 valid 건수
        "weeks_검수": defaultdict(int),
        "weeks_입고": defaultdict(int),
        # 첫 기록 주차 (velocity 분모 계산용)
        "first_week": None,
        "last_week": None,
    })

    for rec in records:
        fields = rec.get("fields", {})
        pt_code = extract_pt(fields.get(F["입하예정물품"]))
        if not pt_code:
            continue
        s = pt[pt_code]
        s["total"] += 1

        date_str = fields.get(F["입하일자"])
        week = iso_week(date_str) if date_str else "W??"

        ts_입하 = fields.get(F["입하완료처리시간"])
        ts_검수 = fields.get(F["시안검수완료시간"])
        ts_입고 = fields.get(F["입고수량입력시간"])
        qty = float(fields.get(F["입하수량"]) or 0)

        if not ts_입하:
            s["no_ts_입하"] += 1
            continue

        is_qty_ok = qty >= 5
        if not is_qty_ok:
            s["qty_lt5"] += 1

        # 검수
        if ts_검수:
            s["has_ts_검수"] += 1
            d = diff_min(ts_입하, ts_검수)
            if d is None:
                pass
            elif d <= 0:
                s["neg_d_검수"] += 1
            elif d >= CYCLE_MAX_MIN:
                s["over180_검수"] += 1
            elif is_qty_ok:
                s["valid_검수"] += 1
                s["weeks_검수"][week] += 1
                if s["first_week"] is None or week < s["first_week"]:
                    s["first_week"] = week
                if s["last_week"] is None or week > s["last_week"]:
                    s["last_week"] = week

        # 입고: CYCLE_MIN_MIN < d (음수 허용 — 입고수량입력이 입하완료 전 기록 패턴)
        if ts_입고:
            s["has_ts_입고"] += 1
            d = diff_min(ts_입하, ts_입고)
            if d is None:
                pass
            elif d < CYCLE_MIN_MIN:
                s["neg_d_입고"] += 1
            elif d >= CYCLE_MAX_MIN:
                s["over180_입고"] += 1
            elif is_qty_ok:
                s["valid_입고"] += 1
                s["weeks_입고"][week] += 1

    return pt


# ── Phase 2 보드 생성 ─────────────────────────────────────────────────────────
def build_phase2_board(pt_data, top_n=25):
    today = datetime.date.today().isoformat()
    lines = []
    lines.append(f"# WMS M/H Phase 2 추적 보드 — {today}")
    lines.append("")
    lines.append(f"> 기준: {SINCE} ~ {today} | ✅ N≥{TARGET_N} | ⚠️ N {WARN_N}-{TARGET_N-1} | ❌ N<{WARN_N}")
    lines.append(f"> 속도(velocity) = 최근 8주 valid 검수 레코드 / 8")
    lines.append(f"> ETA = 갭(30-N) / velocity (주)")
    lines.append("")

    # ── 현황 요약 ──
    n_ok   = sum(1 for s in pt_data.values() if min(s["valid_검수"], s["valid_입고"]) >= TARGET_N)
    n_warn = sum(1 for s in pt_data.values()
                 if WARN_N <= min(s["valid_검수"], s["valid_입고"]) < TARGET_N)
    n_none = len(pt_data) - n_ok - n_warn
    lines.append("## 현황 요약")
    lines.append(f"- ✅ 운영 가능: **{n_ok}개** (N≥{TARGET_N})")
    lines.append(f"- ⚠️ 수집 중:  **{n_warn}개** (N {WARN_N}-{TARGET_N-1})")
    lines.append(f"- ❌ 데이터 부족: **{n_none}개** (N<{WARN_N})")
    lines.append(f"- 전체 PT코드: {len(pt_data)}개")
    lines.append("")

    # ── Phase 2 타겟 보드 (⚠️만, gap 오름차순) ──
    lines.append("## Phase 2 타겟 보드 (⚠️ → ✅ 전환 로드맵)")
    lines.append("")
    lines.append("| 순위 | PT코드 | 검수N | 입고N | 갭 | 속도(건/주) | ETA(주) | 병목 |")
    lines.append("|------|--------|-------|-------|-----|------------|---------|------|")

    # 최근 8주 집계
    all_weeks = sorted({w for s in pt_data.values() for w in s["weeks_검수"]})
    recent_8 = set(all_weeks[-8:]) if len(all_weeks) >= 8 else set(all_weeks)

    warn_rows = []
    for pt_code, s in pt_data.items():
        qc_n = s["valid_검수"]
        pa_n = s["valid_입고"]
        bottleneck_n = min(qc_n, pa_n)
        if bottleneck_n < WARN_N or bottleneck_n >= TARGET_N:
            continue
        gap = TARGET_N - bottleneck_n
        # velocity: 최근 8주 valid 검수 건수 / 8
        recent_count = sum(cnt for w, cnt in s["weeks_검수"].items() if w in recent_8)
        velocity = recent_count / 8 if recent_count > 0 else 0.01
        eta = gap / velocity if velocity > 0 else 9999

        bottleneck = "입고" if pa_n < qc_n else ("검수" if qc_n < pa_n else "균등")
        warn_rows.append((gap, -recent_count, pt_code, qc_n, pa_n, velocity, eta, bottleneck))

    warn_rows.sort()
    for rank, (gap, _, pt_code, qc_n, pa_n, velocity, eta, bottleneck) in enumerate(warn_rows[:top_n], 1):
        eta_str = f"~{int(eta)}주" if eta < 9000 else "??"
        vel_str = f"{velocity:.1f}"
        lines.append(f"| {rank} | {pt_code} | {qc_n} | {pa_n} | {gap} | {vel_str} | {eta_str} | {bottleneck} |")

    lines.append("")
    lines.append("> 속도 0.01건/주는 최근 8주 실적 없음 (데이터 입력 대기)")
    lines.append("")

    # ── 커버리지 갭 진단 (검수N >> 입고N, 갭 5 이상) ──
    lines.append("## 입고 타임스탬프 커버리지 갭 진단")
    lines.append("")
    lines.append("검수 timestamp는 있으나 입고 timestamp 누락이 큰 PT코드 분석.")
    lines.append("")
    lines.append("| PT코드 | 검수N | 입고N | 갭 | ts_없음 | >180분 | 비율 |")
    lines.append("|--------|-------|-------|-----|---------|--------|------|")

    gap_rows = []
    for pt_code, s in pt_data.items():
        qc_n = s["valid_검수"]
        pa_n = s["valid_입고"]
        gap = qc_n - pa_n
        if gap < 5 or qc_n < WARN_N:
            continue
        # no timestamp: has 검수 but not 입고
        no_ts = s["has_ts_검수"] - s["has_ts_입고"]
        over180 = s["over180_입고"]
        total_lost = gap
        ratio = total_lost / qc_n * 100 if qc_n > 0 else 0
        gap_rows.append((gap, pt_code, qc_n, pa_n, no_ts, over180, ratio))

    gap_rows.sort(reverse=True)
    for gap, pt_code, qc_n, pa_n, no_ts, over180, ratio in gap_rows[:15]:
        lines.append(f"| {pt_code} | {qc_n} | {pa_n} | {gap} | {no_ts} | {over180} | {ratio:.0f}% |")

    lines.append("")
    lines.append("**갭 원인 분류:**")
    lines.append("- `ts_없음`: 입하완료 후 입고수량입력시간 미기록 — 프로세스 미준수")
    lines.append("- `>180분`: 당일 처리 안 되고 다음날 이후 입고 → 타임스탬프 있으나 필터에서 제외")
    lines.append("")

    # ── ✅ 운영 기준 PT코드 현황 ──
    lines.append("## ✅ 운영 기준 달성 PT코드")
    lines.append("")
    lines.append("| PT코드 | 검수N | 입고N | 검수p50(분) | 입고p50(분) |")
    lines.append("|--------|-------|-------|------------|------------|")
    for pt_code, s in pt_data.items():
        if min(s["valid_검수"], s["valid_입고"]) >= TARGET_N:
            lines.append(f"| {pt_code} | {s['valid_검수']} | {s['valid_입고']} | — | — |")
    lines.append("")
    lines.append("> ✅ PT코드는 `mh_dual_analysis.py` 리포트에서 p50 값 확인 가능")

    return "\n".join(lines)


# ── main ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=25, help="Phase 2 타겟 최대 표시 수")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    print("=== mh_phase2_board.py ===")
    print(f"  since:   {SINCE}")
    print(f"  top:     {args.top}")
    print()

    print("[1/3] IBSA records 조회...")
    records = fetch_records()
    print(f"      {len(records)} records")

    print("[2/3] PT별 상세 집계...")
    pt_data = aggregate_pt_detailed(records)
    print(f"      {len(pt_data)} PT코드")

    print("[3/3] Phase 2 보드 생성...")
    report = build_phase2_board(pt_data, top_n=args.top)

    if args.dry_run:
        print("\n--- PREVIEW ---")
        print(report[:3000])
    else:
        today = datetime.date.today().isoformat()
        out = Path("outputs") / f"MH_phase2_board_{today}.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"  → {out}")

    print("\n=== 완료 ===")


if __name__ == "__main__":
    main()
