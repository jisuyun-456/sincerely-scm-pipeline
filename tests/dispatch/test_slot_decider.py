"""Tests for harness.dispatch.slot_decider (Contract C2)."""
from __future__ import annotations

import pytest

from harness.dispatch.slot_decider import (
    PARCEL_METHODS,
    QUICK_METHODS,
    TimeWindow,
    decide_slot,
    map_window_to_slot,
    parse_time_window,
)


class TestParseTimeWindow:
    @pytest.mark.parametrize('text,start,end', [
        ('09:00~12:00', 9.0, 12.0),
        ('14:00 - 18:00', 14.0, 18.0),
        ('13–17', 13.0, 17.0),
    ])
    def test_hhmm_range(self, text, start, end):
        w = parse_time_window(text)
        assert w is not None
        assert w.start_h == start and w.end_h == end
        assert w.is_split is False

    def test_split_range(self):
        w = parse_time_window('10:00~11:45, 13:00~19:00')
        assert w is not None
        assert w.is_split is True
        assert w.start_h == 10.0 and w.end_h == 19.0

    @pytest.mark.parametrize('text,start,end', [
        ('오전 수령', 9.0, 12.0),
        ('오후에 부탁', 13.0, 18.0),
        ('저녁 6시 이후', 18.0, 22.0),
    ])
    def test_korean_keyword(self, text, start, end):
        w = parse_time_window(text)
        assert w is not None
        assert w.start_h == start and w.end_h == end

    @pytest.mark.parametrize('text', [None, '', '아무때나'])
    def test_no_match(self, text):
        assert parse_time_window(text) is None


class TestMapWindowToSlot:
    @pytest.mark.parametrize('w,expected', [
        (TimeWindow(9.0, 12.0), '오전'),
        (TimeWindow(13.0, 16.0), '오후 1 (오후 2시 - 4시)'),
        (TimeWindow(16.0, 18.0), '오후 2 (오후 4시 - 6시)'),
        (TimeWindow(18.0, 22.0), '야간'),
        (TimeWindow(9.0, 18.0), '무관'),  # span >= 6
        (TimeWindow(10.0, 19.0, is_split=True), '무관'),
        # Airtable 배송슬롯 선택지는 후행 공백 포함 — 불일치 시 PATCH 422 (2026-06-09~10 cron 3연속 실패 원인)
        (TimeWindow(12.0, 13.0), '특정시간 (희망수령시간 확인) '),
    ])
    def test_window_to_slot(self, w, expected):
        assert map_window_to_slot(w) == expected


class TestDecideSlot:
    """Contract C2 — 배송슬롯 자동 결정 ≥80% 정확도."""

    @pytest.mark.parametrize('method', list(PARCEL_METHODS))
    def test_parcel_always_무관(self, method):
        slot, conf = decide_slot(method, '14:00~16:00')  # 시간 있어도 무시
        assert (slot, conf) == ('무관', 1.0)

    @pytest.mark.parametrize('method', list(QUICK_METHODS))
    def test_quick_default_오전(self, method):
        # 시간 NULL → 오전 default (P3.5 Decision 2 옵션 A)
        assert decide_slot(method, None) == ('오전', 0.8)

    def test_quick_with_morning_time(self):
        assert decide_slot('퀵(수도권)', '09:00~11:00') == ('오전', 0.9)

    def test_quick_with_afternoon_time(self):
        assert decide_slot('자체기사', '14:00~16:00') == ('오후 1 (오후 2시 - 4시)', 0.9)

    def test_split_time_lower_confidence(self):
        slot, conf = decide_slot('자체기사', '10:00~11:00, 14:00~17:00')
        assert slot == '무관'
        assert conf == 0.7

    @pytest.mark.parametrize('method', ['고객직접수령', '기타', None])
    def test_unknown_method_returns_none(self, method):
        # → 수동 wave fallback
        assert decide_slot(method, None) == (None, 0.0)

    def test_method_null_but_time_parses(self):
        # method NULL이어도 시간 텍스트가 있으면 slot 결정
        assert decide_slot(None, '09:00~12:00') == ('오전', 0.9)
