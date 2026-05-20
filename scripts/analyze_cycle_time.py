"""
analyze_cycle_time.py
────────────────────────────────────────────────────────────────────────────────
IBSA sync_movement 의 타임스탬프 인터벌 분석.

목적: cycle timestamp 데이터가 CBM 기반 M/H 표준 보정에 유효한 지표인지 평가.

출력: outputs/cycle_time_analysis_2026-05.md
"""

import math
import os
import sys
import time
from datetime import datetime, timezone

import requests

# ── .env 로드 ─────────────────────────────────────────────────────────────────
if os.path.exists(".env"):
    with open(".env") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

sys.stdout.reconfigure(encoding="utf-8")

# ── Airtable ──────────────────────────────────────────────────────────────────
IBSA_PAT = os.environ.get("AIRTABLE_IBSA_PAT", "")
IBSA_BASE = "app6DGHCPI3Yh3IFS"
IBSA_TABLE = "tblhzYiltSBm6vxBz"

FLD_입하완료 = "fld5pwd5dVYqW4Bdl"
FLD_검수완료 = "fldPxJvu4iIFcxp7w"
FLD_입고수량 = "fldnvnZVsuUPgv1Mn"
FLD_입고좌표 = "fldKK37djY8g5CFaA"
FLD_CBM     = "fldTHmNEPNhcIX5AQ"
FLD_입하수량 = "fldXj3bp2ioe8awCd"   # 입하 piece count (CBM vs pcs 비교용)

# ── 표준 상수 (mh_backfill_to_ibsa.py 와 동기) ────────────────────────────────
PFD = 1.15
QC_STD = 2.5 * PFD          # 검수 표준: 2.875 분
PUTAWAY_BASE = 3.0 * PFD    # 입고 최소: 3.45 분
PUTAWAY_MAX  = 5.0 * PFD    # 입고 최대: 5.75 분 (PUTAWAY_MAX_MIN=5.0)


# ── 통계 유틸 ─────────────────────────────────────────────────────────────────
def percentile(data, p):
    if not data:
        return float("nan")
    s = sorted(data)
    idx = (len(s) - 1) * p / 100
    lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def mean(data):
    return sum(data) / len(data) if data else float("nan")


def pearson_r(xs, ys):
    n = len(xs)
    if n < 2:
        return float("nan")
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return float("nan")
    return num / (dx * dy)


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def diff_min(a, b):
    """b - a in minutes. Returns None if either is None."""
    if a is None or b is None:
        return None
    return (b - a).total_seconds() / 60


# ── 데이터 fetch ──────────────────────────────────────────────────────────────
def fetch_all():
    if not IBSA_PAT:
        print("ERROR: AIRTABLE_IBSA_PAT 미설정", file=sys.stderr)
        sys.exit(2)

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {IBSA_PAT}"})

    records, offset = [], None
    while True:
        params = {
            "pageSize": 100,
            "returnFieldsByFieldId": "true",
            "fields[]": [FLD_입하완료, FLD_검수완료, FLD_입고수량, FLD_입고좌표, FLD_CBM, FLD_입하수량],
        }
        if offset:
            params["offset"] = offset
        resp = session.get(
            f"https://api.airtable.com/v0/{IBSA_BASE}/{IBSA_TABLE}",
            params=params, timeout=90,
        )
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records


# ── 메인 분석 ─────────────────────────────────────────────────────────────────
def main():
    print("fetching IBSA records...")
    records = fetch_all()
    print(f"total records: {len(records)}")

    검수_intervals = []
    입고_intervals = []
    전체_intervals = []
    cbm_for_입고 = []
    cbm_for_전체 = []
    pcs_for_입고 = []   # piece count vs 입고 인터벌 비교용
    pcs_for_전체 = []
    negative_검수 = 0
    negative_입고 = 0
    skipped = 0

    for r in records:
        f = r.get("fields", {})
        t입하 = parse_dt(f.get(FLD_입하완료))
        t검수 = parse_dt(f.get(FLD_검수완료))
        t수량 = parse_dt(f.get(FLD_입고수량))
        t좌표 = parse_dt(f.get(FLD_입고좌표))
        cbm   = f.get(FLD_CBM) or 0.0
        pcs   = f.get(FLD_입하수량) or 0.0

        # 4개 타임스탬프 모두 있어야 분석 대상
        if not all([t입하, t검수, t좌표]):
            skipped += 1
            continue

        d검수 = diff_min(t입하, t검수)
        # 입고: 검수완료 → 좌표입력 (입고 완료 기준)
        d입고 = diff_min(t검수, t좌표)
        d전체 = diff_min(t입하, t좌표)

        if d검수 < 0:
            negative_검수 += 1
        else:
            검수_intervals.append(d검수)

        if d입고 < 0:
            negative_입고 += 1
        else:
            입고_intervals.append(d입고)
            cbm_for_입고.append(cbm)
            pcs_for_입고.append(pcs)

        if d전체 is not None and d전체 >= 0:
            전체_intervals.append(d전체)
            cbm_for_전체.append(cbm)
            pcs_for_전체.append(pcs)

    # ── 통계 ──────────────────────────────────────────────────────────────────
    valid = len(검수_intervals)  # 음수 제외한 검수 건수

    def fmt_dist(data):
        if not data:
            return "데이터 없음"
        return (f"p5={percentile(data,5):.1f}  p25={percentile(data,25):.1f}  "
                f"p50={percentile(data,50):.1f}  p75={percentile(data,75):.1f}  "
                f"p95={percentile(data,95):.1f}  mean={mean(data):.1f}")

    r_cbm_입고 = pearson_r(cbm_for_입고, 입고_intervals)
    r_cbm_전체 = pearson_r(cbm_for_전체, 전체_intervals)
    r_pcs_입고 = pearson_r(pcs_for_입고, 입고_intervals)
    r_pcs_전체 = pearson_r(pcs_for_전체, 전체_intervals)

    # 표준 대비 비율
    ratio_검수 = mean(검수_intervals) / QC_STD if 검수_intervals else float("nan")
    ratio_입고 = mean(입고_intervals) / PUTAWAY_BASE if 입고_intervals else float("nan")

    # ── 리포트 생성 ────────────────────────────────────────────────────────────
    lines = [
        "# IBSA Cycle Time 분석 — M/H 지표 유효성 평가",
        "",
        f"**분석일**: 2026-05-20",
        f"**전체 레코드**: {len(records)}  |  **4-필드 정합**: {valid + negative_검수 + len(입고_intervals) + negative_입고}  |  **타임스탬프 누락 skip**: {skipped}",
        "",
        "---",
        "",
        "## 1. 인터벌 분포 (분 단위)",
        "",
        "### 검수 인터벌 (시안검수완료 − 입하완료처리시간)",
        f"- 유효 건수: {len(검수_intervals)}  (음수/병렬: {negative_검수}건 = {negative_검수/(len(검수_intervals)+negative_검수)*100:.1f}% 제외)" if (len(검수_intervals)+negative_검수) else "- 없음",
        f"- 분포: {fmt_dist(검수_intervals)}",
        f"- 표준 M/H 검수: **{QC_STD:.2f}분** (2.5×1.15)",
        f"- 실측 mean / 표준 = **{ratio_검수:.2f}×**",
        "",
        "### 입고 인터벌 (입고좌표입력 − 시안검수완료시간)",
        f"- 유효 건수: {len(입고_intervals)}  (음수/병렬: {negative_입고}건 제외)",
        f"- 분포: {fmt_dist(입고_intervals)}",
        f"- 표준 M/H 입고: **{PUTAWAY_BASE:.2f}~{PUTAWAY_MAX:.2f}분** (3.45~5.75)",
        f"- 실측 mean / 표준_기본 = **{ratio_입고:.2f}×**",
        "",
        "### 전체 사이클 인터벌 (입고좌표입력 − 입하완료처리시간)",
        f"- 유효 건수: {len(전체_intervals)}",
        f"- 분포: {fmt_dist(전체_intervals)}",
        "",
        "---",
        "",
        "## 2. CBM 상관관계",
        "",
        f"| 인터벌 | 피어슨 r | r² | 해석 |",
        f"|--------|---------|-----|------|",
        f"| 입고 인터벌 vs **CBM** (volume) | {r_cbm_입고:.3f} | {r_cbm_입고**2:.3f} | {'강한 양의 상관' if r_cbm_입고 > 0.6 else '중간 상관' if r_cbm_입고 > 0.3 else '약한/무 상관'} |",
        f"| 입고 인터벌 vs **pcs** (수량)   | {r_pcs_입고:.3f} | {r_pcs_입고**2:.3f} | {'강한 양의 상관' if r_pcs_입고 > 0.6 else '중간 상관' if r_pcs_입고 > 0.3 else '약한/무 상관'} |",
        f"| 전체 사이클 vs **CBM**           | {r_cbm_전체:.3f} | {r_cbm_전체**2:.3f} | {'강한 양의 상관' if r_cbm_전체 > 0.6 else '중간 상관' if r_cbm_전체 > 0.3 else '약한/무 상관'} |",
        f"| 전체 사이클 vs **pcs**           | {r_pcs_전체:.3f} | {r_pcs_전체**2:.3f} | {'강한 양의 상관' if r_pcs_전체 > 0.6 else '중간 상관' if r_pcs_전체 > 0.3 else '약한/무 상관'} |",
        "",
        f"> **CBM vs pcs 승자**: {'CBM' if r_cbm_입고 > r_pcs_입고 else 'pcs(수량)'} (입고 인터벌 기준 r={max(r_cbm_입고, r_pcs_입고):.3f} vs {min(r_cbm_입고, r_pcs_입고):.3f})",
        "",
        "---",
        "",
        "## 3. 결론 — cycle time의 M/H 지표 유효성",
        "",
    ]

    # 동적 결론 생성
    conclusions = []
    if negative_검수 + (len(검수_intervals) or 1) > 0:
        neg_pct = negative_검수 / max(1, len(검수_intervals) + negative_검수) * 100
        if neg_pct > 20:
            conclusions.append(f"- **병렬 처리 비율 {neg_pct:.0f}%**: 입하 완료 전 검수가 시작되는 케이스가 많아 timestamp 순서 보장 안 됨.")

    if ratio_검수 > 5:
        conclusions.append(f"- **검수 인터벌 mean이 표준의 {ratio_검수:.1f}×**: 대기 시간(idle time)이 대부분 — 순수 작업 시간 미분리.")
    elif ratio_검수 < 2:
        conclusions.append(f"- 검수 인터벌이 표준과 유사한 범위 ({ratio_검수:.1f}×) — 대기 없이 즉시 검수 진행되는 현장.")

    if r_cbm_입고 < 0.3:
        conclusions.append(f"- **입고 인터벌 ↔ CBM 상관 낮음 (r={r_cbm_입고:.2f})**: CBM이 클수록 입고 시간이 비례해서 늘지 않음 → CBM 기반 입고 표준의 기울기 가정 검증 필요.")
    elif r_cbm_입고 > 0.6:
        conclusions.append(f"- **입고 인터벌 ↔ CBM 강한 상관 (r={r_cbm_입고:.2f})**: CBM 기반 표준이 실측과 방향 일치 → 상수 보정 인풋으로 활용 가능.")

    if not conclusions:
        conclusions.append("- 데이터 패턴이 중간 범위 — 추가 데이터 누적 후 재평가 권장.")

    # 공통 한계
    conclusions += [
        "",
        "### 공통 한계 (cycle time → M/H 직접 환산 불가한 이유)",
        "1. **idle time 포함**: 입하 완료 후 검수 대기, 검수 완료 후 입고 대기 시간이 인터벌에 포함됨.",
        "2. **다인 투입 미분리**: CBM 큰 건은 2명 이상 투입되나 타임스탬프 1개만 기록 → M/H = 인원×시간 환산 불가.",
        "3. **병렬 가능**: 순서 보장 없음 → 음수 인터벌 발생.",
        "",
        "### 권장 활용 방법",
        "- **M/H 표준 보정**: cycle time 단독으로는 부적합. CBM 기반 표준 유지.",
        "- **Lead Time / 공정 병목 분석**: 인터벌 p95 이상 이상치 → 지연 건 식별에 활용.",
        "- **상관관계 모니터링**: CBM vs 입고인터벌 r이 상승하면 (데이터 누적 후) 재평가 가치 있음.",
    ]

    lines += conclusions
    lines += [
        "",
        "---",
        "",
        f"*생성: `scripts/analyze_cycle_time.py` | 표준 상수: PFD={PFD}, QC={QC_STD:.3f}min, PUTAWAY {PUTAWAY_BASE:.2f}~{PUTAWAY_MAX:.2f}min*",
    ]

    report = "\n".join(lines)

    # 파일 저장
    out_path = "outputs/cycle_time_analysis_2026-05.md"
    os.makedirs("outputs", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)

    print()
    print(report)
    print()
    print(f"=== 저장 완료: {out_path} ===")


if __name__ == "__main__":
    main()
