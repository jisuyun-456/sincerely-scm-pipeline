"""Stage A — 배송슬롯 자동 결정 (Sub-Spec 3).

3단계 분기 (P3.5 Decision 2: 옵션 A method-aware default):
1. 배송방식 ∈ PARCEL_METHODS → '무관' (confidence 1.0)
2. 배송방식 ∈ QUICK_METHODS + 희망수령시간 텍스트 → parse_time_window → slot mapping
3. 배송방식 ∈ QUICK_METHODS + 시간 NULL → '오전' default (퀵 historical 50%+)
4. 그 외 (배송방식 NULL, 기타 method) → (None, 0.0) → 호출자가 '수동' wave로 라우팅

Returns (slot_name | None, confidence float 0~1).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple

PARCEL_METHODS = frozenset({'택배(일반)', '택배(제주산간)', '신시어리택배'})
QUICK_METHODS = frozenset({
    '퀵(수도권)', '퀵(지방)', '자체기사',
    '바로고', '고객직접퀵배차', '신시어리퀵',
})

HHMM_RANGE = re.compile(r'(\d{1,2})(?::(\d{2}))?\s*[~\-–]\s*(\d{1,2})(?::(\d{2}))?')


@dataclass(frozen=True)
class TimeWindow:
    start_h: float
    end_h: float
    is_split: bool = False


def parse_time_window(text: Optional[str]) -> Optional[TimeWindow]:
    if not text:
        return None

    matches = HHMM_RANGE.findall(text)
    if matches:
        ranges = []
        for h1, m1, h2, m2 in matches:
            start = int(h1) + (int(m1) / 60 if m1 else 0)
            end = int(h2) + (int(m2) / 60 if m2 else 0)
            ranges.append((start, end))
        if len(ranges) > 1:
            return TimeWindow(min(r[0] for r in ranges), max(r[1] for r in ranges), is_split=True)
        return TimeWindow(ranges[0][0], ranges[0][1])

    if '오전' in text:
        return TimeWindow(9, 12)
    if '오후' in text:
        return TimeWindow(13, 18)
    if any(k in text for k in ('저녁', '퇴근', '밤')):
        return TimeWindow(18, 22)

    return None


def map_window_to_slot(w: TimeWindow) -> str:
    span = w.end_h - w.start_h

    if w.is_split or span >= 6:
        return '무관'
    if w.end_h <= 12:
        return '오전'
    if 13 <= w.start_h and w.end_h <= 16:
        return '오후 1 (오후 2시 - 4시)'
    if 16 <= w.start_h and w.end_h <= 18:
        return '오후 2 (오후 4시 - 6시)'
    if w.start_h >= 18:
        return '야간'
    if span < 2:
        # Airtable Shipment.배송슬롯 선택지가 후행 공백 포함 — 문자열 불일치 시 PATCH 422
        return '특정시간 (희망수령시간 확인) '
    return '무관'


def decide_slot(method: Optional[str], hope_time_text: Optional[str]) -> Tuple[Optional[str], float]:
    """Stage A 메인 entry. (slot, confidence) 반환. (None, 0.0) → '수동' wave."""
    if method in PARCEL_METHODS:
        return '무관', 1.0

    if hope_time_text:
        window = parse_time_window(hope_time_text)
        if window:
            slot = map_window_to_slot(window)
            confidence = 0.7 if window.is_split else 0.9
            return slot, confidence

    if method in QUICK_METHODS:
        return '오전', 0.8

    return None, 0.0
