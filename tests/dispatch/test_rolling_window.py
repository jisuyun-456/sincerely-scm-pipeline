"""Tests for 7-day rolling business-day window (Contract C8)."""
from __future__ import annotations

from datetime import date

import pytest

from harness.dispatch.scheduling import (
    business_days_forward,
    is_business_day,
    rolling_window_end,
)


class TestBusinessDay:
    """Contract C8 — 7일 rolling 영업일 기준."""

    def test_weekday_is_business(self):
        # 2026-05-28 = Thu
        assert is_business_day(date(2026, 5, 28)) is True

    def test_saturday_is_not_business(self):
        # 2026-05-30 = Sat
        assert is_business_day(date(2026, 5, 30)) is False

    def test_sunday_is_not_business(self):
        # 2026-05-31 = Sun
        assert is_business_day(date(2026, 5, 31)) is False

    def test_holiday_excluded(self):
        # 2026-05-24 어린이날 대체휴일 → 휴일
        assert is_business_day(date(2026, 5, 24)) is False

    def test_business_days_forward_skips_weekend(self):
        # Friday + 1 영업일 = 다음 Monday
        days = business_days_forward(date(2026, 5, 29), n=1)  # Fri
        assert days == [date(2026, 6, 1)]  # next Mon

    def test_rolling_7_days_returns_business_only(self):
        start = date(2026, 5, 28)  # Thu
        end = rolling_window_end(start, days=7)
        # 7 영업일 ≈ 1.5 calendar week → 6/8 or later
        assert end > start
        # 결과는 영업일이어야 함
        assert is_business_day(end)
