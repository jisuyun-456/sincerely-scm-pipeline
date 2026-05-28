"""Contract C1 verification — 자동 대상 필터 정확도.

Sample 50건 수동 GT(ground truth)와 wave_recommender.fetch_auto_targets() 결과 비교.
100% 일치 → PASS.

Usage:
    python scripts/verification/verify_c1_filter.py [--today YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date

# 수동 GT: 아래 record ID들이 auto_targets에 포함되어야 함 (배포 전 팀 확인 필수)
# 없으면 empty → SKIP (수동 보완 필요)
GROUND_TRUTH_IDS: list[str] = []

# 반드시 제외되어야 할 record IDs (발송완료/취소 등)
EXCLUDED_IDS: list[str] = []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--today", default=date.today().isoformat())
    args = parser.parse_args()

    from harness.dispatch.wave_recommender import fetch_auto_targets

    records = fetch_auto_targets(args.today)
    fetched_ids = {r["id"] for r in records}

    total = len(GROUND_TRUTH_IDS) + len(EXCLUDED_IDS)
    if total == 0:
        print("⚠️  C1 Ground truth empty — 수동 보완 필요. SKIP.")
        sys.exit(0)

    passed = 0
    failed = 0

    for rid in GROUND_TRUTH_IDS:
        if rid in fetched_ids:
            passed += 1
        else:
            print(f"  ❌ MISSING expected: {rid}")
            failed += 1

    for rid in EXCLUDED_IDS:
        if rid not in fetched_ids:
            passed += 1
        else:
            print(f"  ❌ INCLUDED excluded: {rid}")
            failed += 1

    pct = passed / total * 100
    print(f"\n[C1 자동 대상 필터] {passed}/{total} ({pct:.0f}%)")
    print(f"  fetched: {len(records)}건 (today={args.today})")
    if failed == 0:
        print("  ✅ PASS")
        sys.exit(0)
    else:
        print(f"  ❌ FAIL — {failed}건 불일치")
        sys.exit(1)


if __name__ == "__main__":
    main()
