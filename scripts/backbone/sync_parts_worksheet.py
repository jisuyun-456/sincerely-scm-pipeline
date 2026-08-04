"""최신 order_cascade 리포트에서 입하CBM 차단(part CBM 미산출) PT를 빈도순 추출 →
규격 이미 입력된 PT 제외 → 사용자 규격 입력용 CSV(docs/). 읽기 전용 분석.

차단단위수 = 해당 PT가 막은 단위 수(우선순위) / 단독차단수 = 그 PT만 막은 단위(채우면 즉시 완결).

Usage:
  py scripts/backbone/sync_parts_worksheet.py [report.json]
"""
import csv
import json
import re
import sys
from collections import Counter
from glob import glob
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from utils.cbm_utils import load_sync_parts_lookup  # noqa: E402

PT_RE = re.compile(r"PT\d{3,6}")


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if path is None:
        reports = sorted(glob("data/order_cascade/report_*.json"))
        if not reports:
            sys.exit("no order_cascade report found")
        path = Path(reports[-1])
    rep = json.loads(path.read_text(encoding="utf-8"))

    blocked_total: Counter = Counter()
    blocked_solo: Counter = Counter()
    example: dict[str, tuple] = {}
    for u in rep["units"]:
        pts = set()
        for r in u.get("reasons", []):
            if "part CBM 미산출" in r:
                pts.update(PT_RE.findall(r))
        if not pts:
            continue
        row = u.get("row", {})
        for pt in pts:
            blocked_total[pt] += 1
            example.setdefault(pt, (row.get("굿즈명", ""), row.get("프로젝트코드", "")))
        if len(pts) == 1:
            blocked_solo[next(iter(pts))] += 1

    sp = load_sync_parts_lookup()
    have_spec = {pt for pt, spec in sp.items() if str(spec or "").strip()}

    rows = [(pt, blocked_total[pt], blocked_solo.get(pt, 0),
             example[pt][0], example[pt][1])
            for pt in blocked_total if pt not in have_spec]
    rows.sort(key=lambda x: (-x[1], -x[2]))

    out = Path("docs/sync_parts_치수입력_worksheet.csv")
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["PT코드", "차단단위수", "단독차단수", "예시_굿즈명", "예시_PNA",
                    "규격_입력(가로x세로x높이mm)"])
        for pt, tot, solo, g, pna in rows:
            w.writerow([pt, tot, solo, g, pna, ""])

    skipped = sum(1 for p in blocked_total if p in have_spec)
    print(f"report={path.name}  차단 PT distinct={len(blocked_total)}  "
          f"규격이미입력(제외)={skipped}  입력필요={len(rows)}")
    print(f"[saved] {out}\n상위 15 (차단단위수 순):")
    for pt, tot, solo, g, pna in rows[:15]:
        print(f"  {pt:8s} 차단={tot:3d} 단독={solo:3d}  {g[:24]:24s} {pna}")


if __name__ == "__main__":
    main()
