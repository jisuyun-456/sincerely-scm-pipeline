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


def week_range(monday: date) -> tuple[date, date]:
    return monday, monday + timedelta(days=6)


def assert_week_in_window(monday: date, max_days_past: int = 60) -> None:
    today = today_kst()
    delta = (today - monday).days
    if delta < 0:
        raise ConfigError(
            f"Week starting {monday} is in the future "
            f"(today KST: {today})"
        )
    if delta > max_days_past:
        raise ConfigError(
            f"Week starting {monday} is {delta} days ago "
            f"(max allowed: {max_days_past})"
        )
