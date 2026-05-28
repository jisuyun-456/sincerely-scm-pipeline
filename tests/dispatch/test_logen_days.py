"""Tests for add_logen_days — 로젠 SLA (월~토, 일요일 skip)."""
from __future__ import annotations

from datetime import date

from harness.dispatch.scheduling import add_logen_days


class TestAddLogenDays:
    """Contract C3 — 일요일 skip, 토요일 포함."""

    def test_friday_plus3_is_tuesday(self):
        # 금(05-29) → 토(+1) → 일 skip → 월(+2) → 화(+3)
        assert add_logen_days(date(2026, 5, 29), 3) == date(2026, 6, 2)

    def test_saturday_plus3_is_wednesday(self):
        # 토(05-30) → 일 skip → 월(+1) → 화(+2) → 수(+3)
        assert add_logen_days(date(2026, 5, 30), 3) == date(2026, 6, 3)

    def test_sunday_plus3_is_wednesday(self):
        # 일(05-31) → 월(+1) → 화(+2) → 수(+3)
        assert add_logen_days(date(2026, 5, 31), 3) == date(2026, 6, 3)

    def test_monday_plus3_is_thursday(self):
        # 월(06-01) → 화(+1) → 수(+2) → 목(+3) — 일요일 없음
        assert add_logen_days(date(2026, 6, 1), 3) == date(2026, 6, 4)

    def test_thursday_plus3_skips_sunday(self):
        # 목(06-04) → 금(+1) → 토(+2) → 일 skip → 월(+3)
        assert add_logen_days(date(2026, 6, 4), 3) == date(2026, 6, 8)
