from __future__ import annotations
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from harness._core.config import ConfigError

try:
    KST = ZoneInfo("Asia/Seoul")
except ZoneInfoNotFoundError:
    # Windows without tzdata package — Korea never observes DST so UTC+9 is exact
    from datetime import timezone, timedelta as _td
    KST = timezone(_td(hours=9))  # type: ignore[assignment]


def today_kst() -> date:
    return datetime.now(KST).date()


def settlement_target_kst() -> date:
    """Date to settle: today KST, but yesterday if we've crossed midnight (cron delay guard).

    GitHub Actions cron can be delayed by several hours. If the job starts after
    midnight KST (hour < 6), the cron was late — settle for yesterday, not today.
    """
    now_kst = datetime.now(KST)
    if now_kst.hour < 6:
        return (now_kst - timedelta(days=1)).date()
    return now_kst.date()


def week_range(monday: date) -> tuple[date, date]:
    return monday, monday + timedelta(days=6)


def assert_week_in_window(
    monday: date, max_days_past: int = 60, max_days_future: int = 1
) -> None:
    """Raise ConfigError if `monday` is outside the allowed settlement window.

    max_days_future=1 allows pre-settlement runs the day before (기사님 사전안내 용도).
    """
    today = today_kst()
    delta = (today - monday).days
    if delta < -max_days_future:
        raise ConfigError(
            f"Date {monday} is more than {max_days_future} day(s) in the future "
            f"(today KST: {today})"
        )
    if delta > max_days_past:
        raise ConfigError(
            f"Week starting {monday} is {delta} days ago "
            f"(max allowed: {max_days_past})"
        )
