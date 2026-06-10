"""P3' Task 4a — movement 이동목적 프로파일 (read-only, CP② 근거 자료).

이동목적별 건수·입하수량/실제입하일/제품규격 보유율·샘플을 출력하고,
입하 증거(실제입하일+입하수량 보유율 기준)가 있는 값을 '외부입하' 후보로 제안.
최종 분류는 사용자 승인(CP②) — 자동 적용 없음.

Usage:
  python scripts/backbone/movement_purpose_profile.py
"""
import os
import sys
from collections import defaultdict
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

load_dotenv()
WP = os.environ["AIRTABLE_WMS_PAT"]
WMS = "appLui4ZR5HWcQRri"
MOV = "tblwq7Kj5Y9nVjlOw"   # movement (read-only ⚡미러)

# 필드 ID (utils/cbm_utils.py와 동일)
F_ITEM = "fldwZKCYZ4IFOigRp"      # 이동물품
F_PURPOSE = "fldFRNxG1pNooEOC7"   # 이동목적
F_IN_QTY = "fldV8kVokQqMIsif0"    # 입하수량
F_ACT_DATE = "flduN8khmYwdn7uVD"  # 실제입하일
F_SPEC = "fldiYU7b6Ogf0zm2D"      # 제품 규격

PROPOSE_THRESHOLD = 0.5   # 실제입하일·입하수량 보유율 동시 ≥50% → 외부입하 후보


def main():
    print("로딩: movement (이동목적·입하필드)...")
    recs, off = [], None
    while True:
        p = {"pageSize": 100,
             "fields[]": [F_ITEM, F_PURPOSE, F_IN_QTY, F_ACT_DATE, F_SPEC],
             "returnFieldsByFieldId": "true"}
        if off:
            p["offset"] = off
        r = requests.get(f"https://api.airtable.com/v0/{WMS}/{MOV}",
                         headers={"Authorization": f"Bearer {WP}"}, params=p, timeout=60)
        r.raise_for_status()
        d = r.json()
        recs += d["records"]
        off = d.get("offset")
        if not off:
            break
    print(f"  movement {len(recs)}행")

    prof = defaultdict(lambda: {"n": 0, "qty": 0, "act": 0, "spec": 0, "samples": []})
    for rec in recs:
        f = rec.get("fields", {})
        purpose = str(f.get(F_PURPOSE) or "(blank)")
        e = prof[purpose]
        e["n"] += 1
        if (f.get(F_IN_QTY) or 0) > 0:
            e["qty"] += 1
        if str(f.get(F_ACT_DATE) or "").strip():
            e["act"] += 1
        if str(f.get(F_SPEC) or "").strip():
            e["spec"] += 1
        if len(e["samples"]) < 2:
            e["samples"].append(str(f.get(F_ITEM) or "")[:50])

    print("\n=== movement 이동목적 프로파일 ===")
    print(f"{'이동목적':<12} {'건수':>7} {'입하수량%':>9} {'실제입하일%':>10} {'제품규격%':>9}")
    candidates = []
    for purpose, e in sorted(prof.items(), key=lambda x: -x[1]["n"]):
        qr, ar, sr = e["qty"] / e["n"], e["act"] / e["n"], e["spec"] / e["n"]
        print(f"{purpose:<14} {e['n']:>7} {qr * 100:>8.1f} {ar * 100:>10.1f} {sr * 100:>9.1f}")
        print(f"               샘플: {' / '.join(e['samples'])}")
        if qr >= PROPOSE_THRESHOLD and ar >= PROPOSE_THRESHOLD and purpose != "(blank)":
            candidates.append(purpose)

    print(f"\n[제안] 외부입하 후보 = {candidates}")
    print("       근거: 실제입하일·입하수량 보유율 동시 ≥50% — 입하 ledger 증거 보유")
    print("       ⚠ 최종 분류는 CP② 사용자 승인 필요 (자동 적용 없음)")


if __name__ == "__main__":
    main()
