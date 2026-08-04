"""레버1 (2026-06-22) — 활성 출하만 카운트해 가짜 partial_skip(다차출하) 제거.

과거 '출하 완료'가 신규 1건 프로젝트를 다차로 오판 → CBM 통째 skip → 자동배차 수동화하던
문제를, 종료(비활성) 상태를 카운트에서 제외해 해소한다.
"""
from harness.dispatch.cbm_estimator import count_active_shipments


def _s(pna, status):
    return {"fields": {"project code": pna, "발송상태_TMS": status}}


def test_terminal_statuses_excluded():
    ships = [
        _s("PNA100", "출하 완료"),   # 종료 → 제외
        _s("PNA100", "출하 대기"),   # 활성 → 1
        _s("PNA200", "진행 취소"),   # 종료 → 제외 (카운트 0)
        _s("PNA300", None),          # 상태 미설정 = 활성 → 1
    ]
    cnt = count_active_shipments(ships)
    assert cnt.get("PNA100") == 1   # 과거 완료가 다차로 오판되지 않음 → deterministic 가능
    assert "PNA200" not in cnt
    assert cnt.get("PNA300") == 1


def test_genuine_multi_active_still_counted():
    # 활성 출하가 진짜 2건이면 다차로 유지 (partial_skip 정당)
    ships = [
        _s("PNA400", "출하 대기"),
        _s("PNA400", "출하 대기"),
        _s("PNA400", "출하 완료"),   # 종료분은 제외돼도 활성 2건 → 다차
    ]
    assert count_active_shipments(ships)["PNA400"] == 2


def test_status_as_lookup_list():
    ships = [{"fields": {"project code": "PNA500", "발송상태_TMS": ["출하 완료"]}}]
    assert count_active_shipments(ships) == {}


def test_blank_project_skipped():
    ships = [{"fields": {"project code": "", "발송상태_TMS": "출하 대기"}}]
    assert count_active_shipments(ships) == {}
