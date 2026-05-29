"""Tests for Slack 다이제스트 quiet hours (Contract C6)."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from harness.dispatch.scheduling import is_quiet_hour

_KST = ZoneInfo("Asia/Seoul")


class TestQuietHours:
    """Contract C6 — 22:00 ~ 07:00 KST 발송 금지."""

    @pytest.mark.parametrize('hour', [22, 23, 0, 1, 6])
    def test_quiet_hours_block(self, hour):
        dt = datetime(2026, 5, 28, hour, 0, 0)
        assert is_quiet_hour(dt) is True

    @pytest.mark.parametrize('hour', [7, 8, 14, 17, 21])
    def test_business_hours_pass(self, hour):
        dt = datetime(2026, 5, 28, hour, 0, 0)
        assert is_quiet_hour(dt) is False

    def test_boundary_07_00_pass(self):
        # 07:00 정각은 발송 OK (>= 7)
        assert is_quiet_hour(datetime(2026, 5, 28, 7, 0, 0)) is False

    def test_boundary_21_59_pass(self):
        assert is_quiet_hour(datetime(2026, 5, 28, 21, 59, 59)) is False

    def test_boundary_22_00_block(self):
        assert is_quiet_hour(datetime(2026, 5, 28, 22, 0, 0)) is True


class TestQuietHoursTimezone:
    """러너=UTC 회귀 — UTC 인스턴트를 KST로 변환한 뒤 판정해야 정확.

    버그: GitHub Actions 러너의 datetime.now()는 UTC라, 09:00 KST(=00:00 UTC)
    cron 런이 quiet(h<7)로 오인되어 Slack 다이제스트가 큐잉/소실되었음.
    """

    @pytest.mark.parametrize(
        'utc_hour, expected_quiet',
        [
            (0, False),   # 00:00 UTC = 09:00 KST → 발송 OK
            (5, False),   # 05:00 UTC = 14:00 KST → 발송 OK
            (8, False),   # 08:00 UTC = 17:00 KST → 발송 OK
            (13, True),   # 13:00 UTC = 22:00 KST → quiet
            (21, True),   # 21:00 UTC = 06:00 KST → quiet
            (22, False),  # 22:00 UTC = 07:00 KST → 발송 OK (경계)
        ],
    )
    def test_utc_instant_evaluated_in_kst(self, utc_hour, expected_quiet):
        utc_dt = datetime(2026, 5, 28, utc_hour, 0, 0, tzinfo=timezone.utc)
        kst_dt = utc_dt.astimezone(_KST)
        assert is_quiet_hour(kst_dt) is expected_quiet
