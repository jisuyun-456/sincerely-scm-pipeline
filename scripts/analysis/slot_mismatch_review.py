"""배송슬롯 ↔ 수령시간 불일치 1회성 리뷰 리스트 (2026-08-19).

decide_slot() 의 개선된 우선순위 로직(수령시간 카테고리 반영, Task 1-2)으로
재계산한 값과 현재 배송슬롯을 비교해 다른 건만 CSV 로 출력. 읽기 전용 —
PATCH 없음. wave_recommender.py 의 cron 파이프라인은 미변경(운영자 보호
가드 유지, Q1 결정) — 여기서 나온 리스트는 사람이 Airtable 에서 직접
검토/수정한다.

Usage: AIRTABLE_PAT=... python scripts/analysis/slot_mismatch_review.py [rolling_days]
"""
from __future__ import annotations

import csv
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from harness.dispatch.slot_decider import decide_slot
from harness.dispatch.wave_recommender import (
    FLD_HOPE_TIME,
    FLD_METHOD,
    FLD_RECEIPT_CATEGORY,
    FLD_SLOT,
    FLD_WAVE_LOCKED,
    _first,
    fetch_auto_targets,
)

KST = timezone(timedelta(hours=9))
OUT_DIR = "_AutoResearch/SCM/outputs"


def main() -> None:
    if not os.environ.get("AIRTABLE_PAT"):
        sys.exit("ERROR: AIRTABLE_PAT not set")

    rolling_days = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    today_iso = datetime.now(KST).isoformat()[:10]

    print(f"[slot_mismatch_review] {today_iso} + {rolling_days}일 조회 중...")
    records = fetch_auto_targets(today_iso, rolling_days=rolling_days)
    print(f"  조회: {len(records)}건")

    rows = []
    for rec in records:
        f = rec.get("fields", {})
        if bool(f.get(FLD_WAVE_LOCKED)):
            continue
        current_slot = _first(f.get(FLD_SLOT))
        if not current_slot:
            continue  # 빈 값은 다음 cron 이 정상적으로 채움 — 리뷰 대상 아님
        method = _first(f.get(FLD_METHOD)) or ""
        hope_time = _first(f.get(FLD_HOPE_TIME)) or ""
        receipt_category = _first(f.get(FLD_RECEIPT_CATEGORY)) or ""
        expected, conf = decide_slot(method, hope_time, receipt_category)
        if expected and expected != current_slot:
            rows.append({
                "record_id": rec.get("id", ""),
                "배송방식": method,
                "수령시간_카테고리": receipt_category,
                "고객희망수령시간": hope_time,
                "현재_배송슬롯": current_slot,
                "재계산_배송슬롯": expected,
                "신뢰도": conf,
            })

    print(f"  불일치: {len(rows)}건")

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"slot_mismatch_review_{today_iso}.csv")
    with open(out_path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "record_id", "배송방식", "수령시간_카테고리", "고객희망수령시간",
            "현재_배송슬롯", "재계산_배송슬롯", "신뢰도",
        ])
        writer.writeheader()
        writer.writerows(rows)
    print(f"  저장: {out_path}")


if __name__ == "__main__":
    main()
