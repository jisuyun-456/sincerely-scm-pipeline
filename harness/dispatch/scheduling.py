"""Scheduling utilities for Sub-Spec 3 (quiet hours + business-day rolling window).

Contracts:
- C6: Slack 다이제스트 quiet hours 22:00~07:00 KST → 발송 0건
- C8: 7일 rolling 영업일 기준 (주말·법정공휴일 제외)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable

# KR 법정공휴일 2026 (간소화 — 운영 중 직접 갱신)
KR_HOLIDAYS_2026 = frozenset({
    '2026-01-01', '2026-01-26', '2026-02-16', '2026-02-17', '2026-02-18',
    '2026-03-01', '2026-05-05', '2026-05-24', '2026-06-06',
    '2026-08-15', '2026-09-25', '2026-09-26', '2026-09-27',
    '2026-10-03', '2026-10-09', '2026-12-25',
})


def is_quiet_hour(dt: datetime) -> bool:
    """22:00 ~ 06:59 KST → True (Slack 발송 금지)."""
    h = dt.hour
    return h >= 22 or h < 7


def is_business_day(d: date, holidays: Iterable[str] = KR_HOLIDAYS_2026) -> bool:
    if d.weekday() >= 5:  # Sat=5, Sun=6
        return False
    return d.isoformat() not in set(holidays)


def business_days_forward(start: date, n: int,
                          holidays: Iterable[str] = KR_HOLIDAYS_2026) -> list[date]:
    """start부터 영업일 n개 list (start 포함하지 않음). C8 7일 rolling 계산용."""
    out: list[date] = []
    cur = start
    while len(out) < n:
        cur += timedelta(days=1)
        if is_business_day(cur, holidays):
            out.append(cur)
    return out


def rolling_window_end(today: date, days: int = 7,
                      holidays: Iterable[str] = KR_HOLIDAYS_2026) -> date:
    """today 기준 영업일 n일 후 (마지막 영업일)."""
    return business_days_forward(today, days, holidays)[-1]
