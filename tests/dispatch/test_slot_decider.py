"""Tests for harness.dispatch.slot_decider (Contract C2)."""
from __future__ import annotations

import pytest

from harness.dispatch.slot_decider import (
    PARCEL_METHODS,
    QUICK_METHODS,
    TimeWindow,
    decide_slot,
    map_window_to_slot,
    normalize_receipt_category,
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


class TestKoreanTimeParsing:
    """#6 (2026-06-22) — 한글 시간표현 파싱: '시'·'에서…사이'·오전/오후 보정."""

    @pytest.mark.parametrize('text,start,end', [
        ('오후 1시~3시', 13.0, 15.0),    # 명시적 오후
        ('오전 9시~11시', 9.0, 11.0),
        ('2시~4시', 14.0, 16.0),         # 무표기 1~7시 → 배송관행상 오후
        ('10시에서 12시사이', 10.0, 12.0),  # 한글 구분자, 10>7 → 보정 없음
        ('1시부터 5시', 13.0, 17.0),
    ])
    def test_korean_range(self, text, start, end):
        w = parse_time_window(text)
        assert w is not None and not w.is_split
        assert w.start_h == start and w.end_h == end

    @pytest.mark.parametrize('text,start,end', [
        ('오후 3시', 14.0, 16.0),
        ('오전 11시', 10.0, 12.0),
    ])
    def test_single_hour_with_ampm(self, text, start, end):
        w = parse_time_window(text)
        assert w is not None
        assert w.start_h == start and w.end_h == end

    def test_evening_keyword_wins_over_single_hour(self):
        # '저녁 6시'는 18시로 (단일 '시' 파싱이 야간 키워드를 가로채면 안 됨)
        assert parse_time_window('저녁 6시 이후') == TimeWindow(18, 22)

    def test_decide_slot_korean_afternoon(self):
        assert decide_slot('퀵(수도권)', '오후 1시~3시') == ('오후 1 (오후 2시 - 4시)', 0.9)
        assert decide_slot('퀵(수도권)', '2시~4시') == ('오후 1 (오후 2시 - 4시)', 0.9)


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


class TestNormalizeReceiptCategory:
    """'수령 시간' singleSelect(CX 선택) → 배송슬롯 canonical 값 정규화."""

    @pytest.mark.parametrize('raw,expected', [
        ('오전', '오전'),
        ('야간', '야간'),
        ('오후 1 ( 2시-4시 )', '오후 1 (오후 2시 - 4시)'),
        ('오후1', '오후 1 (오후 2시 - 4시)'),
        ('오후 2 ( 4시-6시 )', '오후 2 (오후 4시 - 6시)'),
        ('오후2', '오후 2 (오후 4시 - 6시)'),
        ('오후', '오후'),
    ])
    def test_recognized_values(self, raw, expected):
        assert normalize_receipt_category(raw) == expected

    @pytest.mark.parametrize('raw', [
        None, '', '무관',
        '09~11:30/ 13:00~17:30',  # CX가 select 대신 자유 텍스트를 직접 타이핑한 케이스
    ])
    def test_unrecognized_or_blank_returns_none(self, raw):
        assert normalize_receipt_category(raw) is None


class TestMapWindowToSlotAmbiguous:
    """Boundary-straddling window (2h<=span<6h, 어느 버킷에도 안 맞음) → 무관 대신 확인 플래그."""

    @pytest.mark.parametrize('w', [
        TimeWindow(14.0, 17.0),   # 오후1(13-16)/오후2(16-18) 경계 걸침
        TimeWindow(10.0, 14.0),   # 오전(~12)/오후1(13~) 경계 걸침
    ])
    def test_straddling_window_flags_for_review(self, w):
        assert map_window_to_slot(w) == '특정시간 (희망수령시간 확인) '


class TestDecideSlotWithReceiptCategory:
    """수령시간(카테고리) 우선순위 반영 — 2026-08-19 라이브 데이터 불일치 10건 재현."""

    def test_category_specific_wins_over_wide_split_text(self):
        # rec8CUTlMLvGnBDf4 패턴: 텍스트가 오전/오후 걸쳐 split 되지만 카테고리가 명확
        assert decide_slot(
            '퀵(수도권)', '09:00 ~ 11:00 / 13:00 ~ 16:00', '오전',
        ) == ('오전', 0.95)

    def test_broad_pm_category_with_straddling_text_flags_for_review(self):
        # recCMF6bJlLat1VzO 패턴
        assert decide_slot(
            '퀵(수도권)', '오후 14시 ~ 17시 사이', '오후',
        ) == ('특정시간 (희망수령시간 확인) ', 0.9)

    def test_specific_pm1_category_wins_over_straddling_text(self):
        # recCsaq1VaKJ7a0mu 패턴: 카테고리가 이미 오후1 인데 텍스트가 애매
        assert decide_slot(
            '퀵(수도권)', '오후 2시~5시 사이', '오후 1 ( 2시-4시 )',
        ) == ('오후 1 (오후 2시 - 4시)', 0.95)

    def test_category_specific_wins_over_full_day_text(self):
        # recLb6L5x3eKkT6HS 패턴
        assert decide_slot('퀵(수도권)', '09:00 ~ 17:00', '오전') == ('오전', 0.95)

    def test_parcel_still_always_무관_regardless_of_category(self):
        # recN0OUiKBB53KIQu 패턴 — 택배는 카테고리 무시하고 항상 무관
        assert decide_slot('택배(일반)', None, '오후') == ('무관', 1.0)

    def test_specific_pm2_category_wins_over_wide_text(self):
        # recT6HrZnGchPqDI7 패턴
        assert decide_slot(
            '퀵(지방)', '09:00~18:00', '오후 2 ( 4시-6시 )',
        ) == ('오후 2 (오후 4시 - 6시)', 0.95)

    def test_category_specific_with_no_text_still_wins_over_method_default(self):
        # recUNZ51lMAFlgcl9 / recuYjqaalSqoWfwb 패턴
        assert decide_slot('퀵(수도권)', None, '오전') == ('오전', 0.95)

    def test_unrecognized_freetyped_category_falls_back_to_text_parse(self):
        # recYLp1VfikJ27l13 패턴 — CX가 select 대신 자유 텍스트 직접 입력
        raw = '09~11:30/ 13:00~17:30'
        assert decide_slot('퀵(수도권)', raw, raw) == ('무관', 0.7)

    def test_broad_pm_category_no_text_at_all_flags_for_review(self):
        assert decide_slot('퀵(수도권)', None, '오후') == ('특정시간 (희망수령시간 확인) ', 0.5)

    def test_two_arg_call_unaffected_backward_compat(self):
        # scripts/analysis/{wave_backfill_analysis,wave_debug}.py 는 여전히 2-arg 호출
        assert decide_slot('퀵(수도권)', None) == ('오전', 0.8)
        assert decide_slot('퀵(수도권)', '14:00~16:00') == ('오후 1 (오후 2시 - 4시)', 0.9)
