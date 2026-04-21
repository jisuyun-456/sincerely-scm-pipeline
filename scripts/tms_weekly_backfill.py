"""
tms_weekly_backfill.py
────────────────────────────────────────────────────────────────────────────
TMS 주간 백필 통합 실행기.
매주 월/화요일 전주(Mon~Sun) 누락 레코드를 자동 보충.

사용법:
  python scripts/tms_weekly_backfill.py --dry-run            # 미리보기 (쓰기 없음)
  python scripts/tms_weekly_backfill.py                      # 전체 실행 (전주 기준)
  python scripts/tms_weekly_backfill.py --mode otif          # OTIF만
  python scripts/tms_weekly_backfill.py --mode dispatch,otif # 복수 선택
  python scripts/tms_weekly_backfill.py --start 2026-04-14 --end 2026-04-20  # 날짜 지정

백필 항목:
  dispatch  배차 일지   — Shipment에 내부기사 배정됐으나 배차일지 미생성
  otif      OTIF       — 출하완료인데 OTIF 레코드 없음
  event     배송이벤트  — Shipment에 이벤트 없음 (배송접수 초기 이벤트 생성)
  tracking  택배추적로그 — 운송장 있는데 추적로그 없음
"""
import argparse
import logging
import os
import sys
from datetime import date, timedelta

from dotenv import load_dotenv

load_dotenv()

# 백필 모듈 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backfill"))
from backfill_배차일지 import run as run_dispatch
from backfill_otif import run as run_otif
from backfill_배송이벤트 import run as run_event
from backfill_택배추적로그 import run as run_tracking

PAT = os.environ.get(
    "AIRTABLE_PAT",
    "patU9ew1rwbJbEpOn.d5c7c1bb42c3ad69edd2701ee0424ddcb04c4d261a0ed422f8e5edaf1fa20edc",
)
HEADERS = {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}

MODES = {
    "dispatch": ("배차 일지", run_dispatch),
    "otif":     ("OTIF",     run_otif),
    "event":    ("배송이벤트", run_event),
    "tracking": ("택배추적로그", run_tracking),
}


def last_week_range() -> tuple[date, date]:
    """직전 월~일 (오늘 기준 직전 주)"""
    today = date.today()
    last_monday = today - timedelta(days=today.weekday() + 7)
    last_sunday = last_monday + timedelta(days=6)
    return last_monday, last_sunday


def main():
    parser = argparse.ArgumentParser(description="TMS 주간 백필")
    parser.add_argument(
        "--mode", default="all",
        help="실행 항목 (all / dispatch,otif,event,tracking 중 선택, 콤마 구분)"
    )
    parser.add_argument("--start", help="시작일 YYYY-MM-DD (기본: 전주 월요일)")
    parser.add_argument("--end",   help="종료일 YYYY-MM-DD (기본: 전주 일요일)")
    parser.add_argument("--dry-run", action="store_true", help="쓰기 없이 미리보기만")
    args = parser.parse_args()

    # 날짜 설정
    if args.start and args.end:
        start = date.fromisoformat(args.start)
        end   = date.fromisoformat(args.end)
    else:
        start, end = last_week_range()

    # 실행 모드 파싱
    if args.mode == "all":
        selected = list(MODES.keys())
    else:
        selected = [m.strip() for m in args.mode.split(",") if m.strip() in MODES]

    print(f"{'[DRY RUN] ' if args.dry_run else ''}TMS 주간 백필 시작")
    print(f"  대상 주간: {start} ~ {end}")
    print(f"  실행 항목: {', '.join(selected)}\n")

    summary = {}
    for mode in selected:
        label, run_fn = MODES[mode]
        print(f"▶ {label} 백필...")
        try:
            result = run_fn(HEADERS, start, end, dry_run=args.dry_run)
            summary[label] = result
            print(f"  완료: {result}")
        except Exception as e:
            summary[label] = {"error": str(e)}
            print(f"  오류: {e}")
        print()

    # 결과 요약
    print("=" * 50)
    print("백필 요약")
    print("=" * 50)
    for label, result in summary.items():
        if "error" in result:
            print(f"  {label}: ❌ {result['error']}")
        else:
            created = result.get("created", 0)
            msg = result.get("message", "")
            suffix = f" ({msg})" if msg else ""
            status = "✅" if not args.dry_run else "👀 DRY"
            print(f"  {label}: {status} {created}건 처리{suffix}")

    # 로그 저장
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"backfill_{date.today().isoformat()}.log")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n[{date.today()}] {start}~{end} {'DRY' if args.dry_run else 'RUN'}\n")
        for label, result in summary.items():
            f.write(f"  {label}: {result}\n")
    print(f"\n[로그 저장] {log_path}")


if __name__ == "__main__":
    main()
