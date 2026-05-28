"""Tests for Slack 다이제스트 quiet hours (Contract C6)."""
from __future__ import annotations

from datetime import datetime

import pytest

from harness.dispatch.scheduling import is_quiet_hour


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
