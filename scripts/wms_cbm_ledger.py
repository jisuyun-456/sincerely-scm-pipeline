"""
scripts/wms_cbm_ledger.py
─────────────────────────────────────────────────────────────────────────────
WMS 창고 Running Balance 계산기 (M-02).

입하 CBM (WMS movement.생산산출) vs 출하 CBM (TMS shipment.총 CBM) 대비로
현재 재고 부피 + 창고 용적률을 계산한다.

단독 실행:
  python scripts/wms_cbm_ledger.py                  # 올해 YTD 기준
  python scripts/wms_cbm_ledger.py --since 2026-01-01 --until 2026-05-15

wms_weekly_runner.py Iter 9에서 import:
  from wms_cbm_ledger import calc_running_balance
"""

import argparse
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

# utils/ 가 같은 레포 루트 아래에 있으므로 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.cbm_utils import (
    AIRTABLE_PAT,
    fetch_inbound_cbm,
    load_sync_parts_lookup,
)

load_dotenv()

# ── 창고 용량 상수 ────────────────────────────────────────────────────────────
WAREHOUSE_INBOUND_CBM  = 50.0   # TODO: 월요일 실측 후 교체
WAREHOUSE_OUTBOUND_CBM = 44.0   # 출하/보관 창고 용적 (확인값)

# ── TMS 상수 ──────────────────────────────────────────────────────────────────
TMS_BASE      = "app4x70a8mOrIKsMf"
TBL_SHIPMENT  = "tbllg1JoHclGYer7m"
TF_DATE       = "fldQvmEwwzvQW95h9"   # 출하일
TF_TOTAL_CBM  = "fldJ9DHjwoRyeUEqE"   # 총 CBM (formula)

TMS_PAT = os.environ.get("AIRTABLE_TMS_PAT", os.environ.get("AIRTABLE_PAT", ""))


def _tms_headers() -> dict:
    return {
        "Authorization": f"Bearer {TMS_PAT}",
        "Content-Type": "application/json",
    }


# ── TMS 출하 CBM 조회 ─────────────────────────────────────────────────────────
def get_total_outbound_cbm(since: date, until: date | None = None) -> float:
    """
    TMS Shipment.총 CBM 기간 합계.
    since/until: 출하일 범위 (inclusive). until 미지정 시 오늘까지.
    """
    if until is None:
        until = date.today()

    formula = (
        f"AND("
        f"IS_AFTER({{출하일}}, DATEADD('{since.isoformat()}', -1, 'days')), "
        f"IS_BEFORE({{출하일}}, DATEADD('{until.isoformat()}', 1, 'days'))"
        f")"
    )

    records, offset = [], None
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_SHIPMENT}"
    while True:
        params: dict = {
            "fields[]": [TF_DATE, TF_TOTAL_CBM],
            "pageSize": 100,
            "returnFieldsByFieldId": "true",
            "filterByFormula": formula,
        }
        if offset:
            params["offset"] = offset
        resp = requests.get(url, headers=_tms_headers(), params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)

    total = 0.0
    for rec in records:
        f = rec.get("fields", {})
        try:
            cbm = float(f.get(TF_TOTAL_CBM) or 0)
        except (ValueError, TypeError):
            cbm = 0.0
        total += cbm
    return round(total, 4)


def get_weekly_inbound_cbm(week_str: str) -> float:
    """
    주간 입하 CBM 합계. week_str 예: '2026-W21'.
    """
    sp_lookup = load_sync_parts_lookup()
    result = fetch_inbound_cbm(sp_lookup, week_str=week_str)
    return result["total_cbm"]


# ── Running Balance 계산 ──────────────────────────────────────────────────────
def calc_running_balance(
    since: date | None = None,
    until: date | None = None,
) -> dict:
    """
    YTD 또는 지정 기간의 입하 vs 출하 CBM 대비로 창고 Running Balance 계산.

    Returns:
      since / until: 집계 기간
      inbound_cbm:   기간 입하 CBM 합계
      outbound_cbm:  기간 출하 CBM 합계
      net_stock_cbm: 현재 재고 CBM (입하 - 출하)
      utilization_pct: net_stock_cbm / WAREHOUSE_OUTBOUND_CBM × 100
      available_cbm: WAREHOUSE_OUTBOUND_CBM - net_stock_cbm
      inbound_headroom_cbm: WAREHOUSE_INBOUND_CBM - net_stock_cbm
      capacity_inbound: WAREHOUSE_INBOUND_CBM
      capacity_outbound: WAREHOUSE_OUTBOUND_CBM
    """
    if since is None:
        since = date(date.today().year, 1, 1)
    if until is None:
        until = date.today()

    sp_lookup = load_sync_parts_lookup()
    inbound_result = fetch_inbound_cbm(sp_lookup, since=since, until=until)
    inbound_cbm  = inbound_result["total_cbm"]
    outbound_cbm = get_total_outbound_cbm(since, until)

    net_stock_cbm    = max(0.0, round(inbound_cbm - outbound_cbm, 4))
    utilization_pct  = round(net_stock_cbm / WAREHOUSE_OUTBOUND_CBM * 100, 1)
    available_cbm    = round(max(0.0, WAREHOUSE_OUTBOUND_CBM - net_stock_cbm), 4)
    inbound_headroom = round(max(0.0, WAREHOUSE_INBOUND_CBM - net_stock_cbm), 4)

    return {
        "since":               since.isoformat(),
        "until":               until.isoformat(),
        "inbound_cbm":         inbound_cbm,
        "outbound_cbm":        outbound_cbm,
        "net_stock_cbm":       net_stock_cbm,
        "utilization_pct":     utilization_pct,
        "available_cbm":       available_cbm,
        "inbound_headroom_cbm": inbound_headroom,
        "capacity_inbound":    WAREHOUSE_INBOUND_CBM,
        "capacity_outbound":   WAREHOUSE_OUTBOUND_CBM,
    }


# ── 단독 실행 ─────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="WMS 창고 Running Balance")
    parser.add_argument("--since", help="시작일 (YYYY-MM-DD), 기본: 올해 1월 1일")
    parser.add_argument("--until", help="종료일 (YYYY-MM-DD), 기본: 오늘")
    args = parser.parse_args()

    since = date.fromisoformat(args.since) if args.since else None
    until = date.fromisoformat(args.until) if args.until else None

    if not AIRTABLE_PAT:
        print("ERROR: AIRTABLE_PAT 환경변수가 없습니다.", file=sys.stderr)
        sys.exit(1)

    print("Running Balance 계산 중...")
    bal = calc_running_balance(since=since, until=until)

    print(f"\n{'='*55}")
    print(f"[창고 Running Balance]  {bal['since']} ~ {bal['until']}")
    print(f"{'='*55}")
    print(f"  YTD 입하 CBM   : {bal['inbound_cbm']:>8.4f} m³")
    print(f"  YTD 출하 CBM   : {bal['outbound_cbm']:>8.4f} m³")
    print(f"  현재 재고 CBM  : {bal['net_stock_cbm']:>8.4f} m³")
    print(f"  창고 용적률    : {bal['utilization_pct']:>7.1f}%  (기준: {WAREHOUSE_OUTBOUND_CBM} m³)")
    print(f"  가용 공간      : {bal['available_cbm']:>8.4f} m³")
    print(f"  입하 여유 공간 : {bal['inbound_headroom_cbm']:>8.4f} m³  (기준: {WAREHOUSE_INBOUND_CBM} m³)")

    util = bal["utilization_pct"]
    if util >= 90:
        print(f"\n  ⚠ 위험: 창고 용적률 {util:.1f}% — 즉시 출하 촉진 필요")
    elif util >= 75:
        print(f"\n  △ 주의: 창고 용적률 {util:.1f}% — 이번 주 입하 모니터링 필요")
    else:
        print(f"\n  ✓ 정상: 창고 용적률 {util:.1f}%")
    print(f"{'='*55}")


if __name__ == "__main__":
    main()
