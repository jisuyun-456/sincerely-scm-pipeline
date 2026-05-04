#!/usr/bin/env python3
"""
TMS 백필 DRY-RUN — 잔여 건수 카운트 (READ-ONLY, WRITE 절대 없음)

대상 (보관 스크립트와 동일 필터):
  1. TRK: 택배사 OR 운송장번호 비어 있음          (backfill_tracking_fields.py)
  2. EVT: 잘못된 ID 패턴 EVT-rec*                 (fix_event_backfill.py Phase A)
  3. EVT: 누락 (발송완료 + BLANK + 2026-01-01↑)  (fix_event_backfill.py Phase B)
  4. TRK: 잘못된 ID 패턴 TRK-rec*                 (fix_tracking_backfill.py Phase A)
  5. TRK: 누락 (위 + 배송파트너에 택배/로젠/로지비/CJ) (fix_tracking_backfill.py Phase B)
  6. Shipment: 구간유형 blank (최근 30일, 출하확정)
"""
import os
import re
import sys
import requests
from datetime import date, timedelta

PAT = os.environ.get("AIRTABLE_PAT")
if not PAT:
    sys.exit("ERROR: AIRTABLE_PAT 환경변수 필요")

BASE_ID  = "app4x70a8mOrIKsMf"
SHIP_TBL = "tbllg1JoHclGYer7m"
EVT_TBL  = "tblQyuAW30yf21WEf"
TRK_TBL  = "tblonyqcHGa5V5zbj"
HDRS     = {"Authorization": f"Bearer {PAT}"}

SHIP_URL = f"https://api.airtable.com/v0/{BASE_ID}/{SHIP_TBL}"
EVT_URL  = f"https://api.airtable.com/v0/{BASE_ID}/{EVT_TBL}"
TRK_URL  = f"https://api.airtable.com/v0/{BASE_ID}/{TRK_TBL}"

EVT_BAD_RE = re.compile(r"^EVT-rec")
TRK_BAD_RE = re.compile(r"^TRK-rec")


def count_records(url: str, params: dict, scan_pattern_field: str = None, pattern: re.Pattern = None) -> int:
    """페이지네이션으로 전체 레코드 카운트. 패턴이 주어지면 클라이언트 측 매칭 카운트."""
    total = 0
    p = dict(params)
    p.setdefault("pageSize", 100)
    while True:
        r = requests.get(url, headers=HDRS, params=p, timeout=30)
        r.raise_for_status()
        data = r.json()
        recs = data.get("records", [])
        if pattern and scan_pattern_field:
            for rec in recs:
                v = rec.get("fields", {}).get(scan_pattern_field, "")
                if pattern.match(str(v)):
                    total += 1
        else:
            total += len(recs)
        offset = data.get("offset")
        if not offset:
            break
        p["offset"] = offset
    return total


def main() -> None:
    print("=" * 70)
    print("TMS 백필 DRY-RUN — 잔여 건수 카운트 (READ-ONLY)")
    print("=" * 70)

    # ── 1. TRK: 택배사 OR 운송장번호 비어 있음 ────────────────────
    print("\n[1] 택배사 OR 운송장번호 비어 있는 TRK …", end=" ", flush=True)
    n1 = count_records(
        TRK_URL,
        {
            "filterByFormula": 'OR({택배사}=BLANK(), {운송장번호}=BLANK())',
            "fields[]": ["택배사", "운송장번호"],
        },
    )
    print(f"{n1}건")

    # ── 2. EVT-rec* 잘못된 ID 패턴 ────────────────────────────────
    print("[2] EVT-rec* 잘못된 ID 패턴 …", end=" ", flush=True)
    n2 = count_records(
        EVT_URL,
        {
            "filterByFormula": 'LEFT({이벤트ID},7)="EVT-rec"',
            "fields[]": ["이벤트ID"],
        },
    )
    print(f"{n2}건")

    # ── 3. 누락 EVT (발송완료 + BLANK + 2026-01-01 이후) ──────────
    print("[3] 누락 배송이벤트 (발송완료 + BLANK + 2026-01-01↑) …", end=" ", flush=True)
    formula3 = (
        'AND('
        '  {발송상태_TMS}="출하 완료",'
        '  IS_AFTER({출하확정일},"2025-12-31"),'
        '  {배송이벤트}=BLANK()'
        ')'
    )
    n3 = count_records(
        SHIP_URL,
        {"filterByFormula": formula3, "fields[]": ["SC id"]},
    )
    print(f"{n3}건")

    # ── 4. TRK-rec* 잘못된 ID 패턴 ────────────────────────────────
    print("[4] TRK-rec* 잘못된 ID 패턴 …", end=" ", flush=True)
    n4 = count_records(
        TRK_URL,
        {
            "filterByFormula": 'LEFT({추적ID},7)="TRK-rec"',
            "fields[]": ["추적ID"],
        },
    )
    print(f"{n4}건")

    # ── 5. 누락 TRK (택배 계열 배송파트너) ────────────────────────
    print("[5] 누락 택배추적로그 (위 + 배송파트너 택배/로젠/로지비/CJ) …", end=" ", flush=True)
    formula5 = (
        'AND('
        '  {발송상태_TMS}="출하 완료",'
        '  IS_AFTER({출하확정일},"2025-12-31"),'
        '  {택배추적로그}=BLANK(),'
        '  OR(FIND("택배",{배송파트너})>0,FIND("로젠",{배송파트너})>0,'
        '     FIND("로지비",{배송파트너})>0,FIND("CJ",{배송파트너})>0)'
        ')'
    )
    n5 = count_records(
        SHIP_URL,
        {"filterByFormula": formula5, "fields[]": ["SC id"]},
    )
    print(f"{n5}건")

    # ── 6. 구간유형 blank Shipment (최근 30일) ────────────────────
    cutoff = (date.today() - timedelta(days=30)).isoformat()
    print(f"[6] 구간유형 blank Shipment (출하확정 ≥ {cutoff}) …", end=" ", flush=True)
    formula6 = (
        f'AND('
        f'  IS_AFTER({{출하확정일}},"{cutoff}"),'
        f'  OR({{구간유형}}=BLANK(), {{구간유형}}="기타")'
        f')'
    )
    n6 = count_records(
        SHIP_URL,
        {"filterByFormula": formula6, "fields[]": ["SC id", "구간유형"]},
    )
    print(f"{n6}건")

    # ── 요약 ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("요약 — 백필 우선순위")
    print("=" * 70)
    print(f"  [1] TRK 택배사/운송장 비어있음              : {n1:>5}건")
    print(f"  [2] EVT-rec* 잘못된 ID                      : {n2:>5}건")
    print(f"  [3] 누락 배송이벤트                          : {n3:>5}건")
    print(f"  [4] TRK-rec* 잘못된 ID                      : {n4:>5}건")
    print(f"  [5] 누락 택배추적로그                        : {n5:>5}건")
    print(f"  [6] 구간유형 blank/기타 (최근 30일)         : {n6:>5}건")
    print(f"  ── 합계                                      : {n1+n2+n3+n4+n5+n6:>5}건")


if __name__ == "__main__":
    main()
