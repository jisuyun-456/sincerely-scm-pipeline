"""utils.vehicle_util 순수 로직 테스트 (P2 A3 — 차량 적재율 SSOT)."""
from utils.vehicle_util import (
    aggregate_capacity,
    bare_driver,
    capacities_from_shipments,
    capacity_for,
    summarize_util,
)


def test_bare_driver_extracts_paren_token():
    assert bare_driver("신시어리 기사님 (이장훈)") == "이장훈"
    assert bare_driver("신시어리 (이장훈)") == "이장훈"
    assert bare_driver("이장훈") == "이장훈"
    assert bare_driver(None) == ""


def test_capacity_for_exact_then_substring_then_default():
    caps = {"이장훈": 4.5, "조희선": 7.616}
    assert capacity_for("이장훈", caps) == 4.5                      # exact bare
    assert capacity_for("신시어리 (이장훈)", caps) == 4.5           # paren → bare exact
    assert capacity_for("이장훈 기사", caps) == 4.5                 # substring fallback
    assert capacity_for("박종성", caps, default=9.486) == 9.486     # 미존재 → default


def test_aggregate_capacity_takes_max_and_ignores_zero_none():
    pairs = [
        ("신시어리 (이장훈)", 4.5),
        ("신시어리 (이장훈)", 3.0),     # 같은 기사 더 작은 값 — max 유지
        ("신시어리 (박종성)", 0),       # 0 무시
        ("신시어리 (조희선)", None),    # None 무시
        ("신시어리 (조희선)", "7.616"),  # 문자열 숫자 허용
    ]
    out = aggregate_capacity(pairs)
    assert out == {"이장훈": 4.5, "조희선": 7.616}


def test_summarize_util_median_and_flags():
    # loaded=[40,544,100,30] (정렬 30,40,100,544 → median 70), zero=2
    s = summarize_util([0, 0, 40, 544, 100, 30], under=50.0, over=100.0)
    assert s["n"] == 6
    assert s["n_loaded"] == 4
    assert s["n_zero"] == 2
    assert s["n_under"] == 2          # 40, 30 < 50
    assert s["n_over"] == 1           # 544 > 100
    assert s["median"] == 70.0
    # capped=[40,100,100,30] → mean 67.5 (오버부킹 544→100 상한)
    assert s["mean_capped"] == 67.5


def test_summarize_util_empty_is_safe():
    s = summarize_util([])
    assert s["n"] == 0 and s["median"] == 0.0 and s["mean_capped"] == 0.0


def test_capacities_from_shipments_extracts_lookup_records():
    recs = [
        {"fields": {"fldHZ7yMT3KEu2gSj": ["신시어리 (이장훈)"], "fld9ZixilQySf9taF": [4.5]}},
        {"fields": {"fldHZ7yMT3KEu2gSj": ["신시어리 (이장훈)"], "fld9ZixilQySf9taF": [4.5]}},
        {"fields": {"fldHZ7yMT3KEu2gSj": ["신시어리 (박종성)"], "fld9ZixilQySf9taF": [9.486]}},
        {"fields": {}},  # 빈 행 무시
    ]
    assert capacities_from_shipments(recs) == {"이장훈": 4.5, "박종성": 9.486}


def test_capacities_from_shipments_empty_falls_back():
    assert capacities_from_shipments([]) == {"이장훈": 4.5, "조희선": 7.616, "박종성": 9.486}
    assert capacities_from_shipments([], fallback=False) == {}
