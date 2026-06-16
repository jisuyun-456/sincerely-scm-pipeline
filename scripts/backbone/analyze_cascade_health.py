"""캐스케이드 리포트 CBM·BOM 정합성 분석 (read-only).

사용: python scripts/backbone/analyze_cascade_health.py <report.json>
산출: 완결/부분/끊김 분포 + 스테이지별 차단 사유 빈도 + S3/S5 CBM 갭 + S2 BOM 갭.
"""
import json
import re
import sys
from collections import Counter


def load(path):
    return json.load(open(path, encoding="utf-8"))


def stage_of(reason: str) -> str:
    m = re.match(r"\s*(S\d)", reason)
    return m.group(1) if m else "기타"


def analyze(rep: dict) -> dict:
    units = rep["units"]
    n = len(units)
    by_status = Counter(u["status"] for u in units)

    # 스테이지별 차단 사유 (단위 단위 — 한 단위가 복수 사유 가질 수 있음)
    stage_units = Counter()          # 스테이지가 한 번이라도 언급된 단위 수
    reason_freq = Counter()          # 정규화 사유 문자열 빈도
    s3_uncovered_pts = Counter()     # S3 미산출 PT 빈도
    s5_modes = Counter()             # S5 미산출 mode 분포
    s5_unmatched = Counter()         # S5 미산출 견적코드 빈도
    s2_bom_missing = 0

    for u in units:
        seen_stage = set()
        for r in u["reasons"]:
            st = stage_of(r)
            if st not in seen_stage:
                stage_units[st] += 1
                seen_stage.add(st)
            # 정규화: 가변 토큰 제거
            norm = re.sub(r":.*$", "", r).strip()
            reason_freq[norm] += 1
            if r.startswith("S3 part CBM 미산출 PT"):
                for pt in re.findall(r"PT\d{3,6}", r):
                    s3_uncovered_pts[pt] += 1
            if r.startswith("S2 BOM 행 없음"):
                s2_bom_missing += 1
            if "S5 출하CBM 미산출" in r:
                mm = re.search(r"mode=(\w+)", r)
                s5_modes[mm.group(1) if mm else "?"] += 1
                for code in re.findall(r"'([A-Z0-9]{2,6})'", r):
                    s5_unmatched[code] += 1
    return {
        "n": n, "by_status": by_status, "stage_units": stage_units,
        "reason_freq": reason_freq, "s3_uncovered_pts": s3_uncovered_pts,
        "s5_modes": s5_modes, "s5_unmatched": s5_unmatched,
        "s2_bom_missing": s2_bom_missing,
    }


def pct(a, b):
    return f"{a/b*100:.1f}%" if b else "—"


def main():
    path = sys.argv[1]
    rep = load(path)
    a = analyze(rep)
    n = a["n"]
    print(f"=== 캐스케이드 정합성 분석 — {path}")
    print(f"run_id={rep.get('run_id')} window={rep.get('window_days')}d  단위={n}")
    print()
    print("[완결률]")
    for st in ("완결", "부분", "끊김"):
        c = a["by_status"].get(st, 0)
        print(f"  {st}: {c:>4} ({pct(c, n)})")
    print()
    print("[스테이지별 차단 단위 수 (영향 큰 순)]")
    for st, c in a["stage_units"].most_common():
        print(f"  {st}: {c:>4} 단위 ({pct(c, n)})")
    print()
    print("[차단 사유 빈도 top 12]")
    for r, c in a["reason_freq"].most_common(12):
        print(f"  {c:>4}  {r}")
    print()
    print(f"[S3 입하 part CBM 미산출 — 고유 PT {len(a['s3_uncovered_pts'])}종, top 15]")
    for pt, c in a["s3_uncovered_pts"].most_common(15):
        print(f"  {c:>4}회  {pt}")
    print()
    print("[S5 출하 CBM 미산출 mode 분포]")
    for m, c in a["s5_modes"].most_common():
        print(f"  {c:>4}  mode={m}")
    print(f"[S5 미산출 견적코드 top 15 (고유 {len(a['s5_unmatched'])}종)]")
    for code, c in a["s5_unmatched"].most_common(15):
        print(f"  {c:>4}회  {code}")
    print()
    print(f"[S2 BOM 행 없음] {a['s2_bom_missing']} 단위 ({pct(a['s2_bom_missing'], n)})")


if __name__ == "__main__":
    main()
