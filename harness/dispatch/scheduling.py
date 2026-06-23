"""Scheduling utilities for Sub-Spec 3 (quiet hours + business-day rolling window).

Contracts:
- C6: Slack 다이제스트 quiet hours 22:00~07:00 KST → 발송 0건
- C8: 7일 rolling 영업일 기준 (주말·법정공휴일 제외)
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from typing import Iterable

# KR 법정공휴일 (간소화 — 운영 중 직접 갱신). 음력·대체공휴일은 매년 확정 후 갱신 필요.
KR_HOLIDAYS_2026 = frozenset({
    '2026-01-01', '2026-01-26', '2026-02-16', '2026-02-17', '2026-02-18',
    '2026-03-01', '2026-05-05', '2026-05-24', '2026-06-06',
    '2026-08-15', '2026-09-25', '2026-09-26', '2026-09-27',
    '2026-10-03', '2026-10-09', '2026-12-25',
})
# 2027 (음력/대체휴일 근사 — 운영 중 관보 확정값으로 교체)
KR_HOLIDAYS_2027 = frozenset({
    '2027-01-01', '2027-02-06', '2027-02-07', '2027-02-08', '2027-02-09',
    '2027-03-01', '2027-05-05', '2027-05-13', '2027-06-06',
    '2027-08-15', '2027-09-14', '2027-09-15', '2027-09-16',
    '2027-10-03', '2027-10-09', '2027-12-25',
})
KR_HOLIDAYS = KR_HOLIDAYS_2026 | KR_HOLIDAYS_2027
_COVERED_YEARS = frozenset({2026, 2027})
_warned_years: set[int] = set()


def _warn_uncovered_year(d: date) -> None:
    """공휴일 데이터 없는 연도 계산 시 1회 경고 — 휴일이 영업일로 오계산되는 silent bug 방지."""
    y = d.year
    if y not in _COVERED_YEARS and y not in _warned_years:
        _warned_years.add(y)
        print(f"[WARN] scheduling: {y}년 공휴일 데이터 미등록 — 휴일이 영업일로 계산될 수 있음. "
              f"KR_HOLIDAYS_{y} 추가 필요.", file=sys.stderr)


def is_quiet_hour(dt: datetime) -> bool:
    """22:00 ~ 06:59 KST → True (Slack 발송 금지)."""
    h = dt.hour
    return h >= 22 or h < 7


def is_business_day(d: date, holidays: Iterable[str] = KR_HOLIDAYS) -> bool:
    if d.weekday() >= 5:  # Sat=5, Sun=6
        return False
    return d.isoformat() not in set(holidays)


def business_days_forward(start: date, n: int,
                          holidays: Iterable[str] = KR_HOLIDAYS) -> list[date]:
    """start부터 영업일 n개 list (start 포함하지 않음). C8 7일 rolling 계산용."""
    _warn_uncovered_year(start)
    out: list[date] = []
    cur = start
    while len(out) < n:
        cur += timedelta(days=1)
        _warn_uncovered_year(cur)
        if is_business_day(cur, holidays):
            out.append(cur)
    return out


def rolling_window_end(today: date, days: int = 7,
                      holidays: Iterable[str] = KR_HOLIDAYS) -> date:
    """today 기준 영업일 n일 후 (마지막 영업일)."""
    return business_days_forward(today, days, holidays)[-1]


def add_logen_days(start: date, days: int) -> date:
    """출하확정일 + N일 (일요일만 skip). 로젠 SLA 기준 — 월~토 배송."""
    d, remaining = start, days
    while remaining > 0:
        d += timedelta(days=1)
        if d.weekday() != 6:  # 6 = Sunday
            remaining -= 1
    return d
