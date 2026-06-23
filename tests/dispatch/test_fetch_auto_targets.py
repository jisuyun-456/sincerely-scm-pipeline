"""fetch_auto_targets 회귀 테스트 (2026-06-22 status-value 버그).

과거 버그: 발송상태_TMS 제외값이 실제 옵션('출하 완료'·'진행 취소')과 불일치 →
필터 무효화 → 전체 이력 스캔 + 종료건 재배차. 본 테스트는 (1) formula 가 실제 종료상태를
제외하고, (2) 서버사이드 날짜창을 포함하며, (3) Python-side window 필터가 동작함을 고정.
"""
from harness.dispatch import wave_recommender as wr


def _make_capture(records):
    """_get 대체: 호출 params(formula 포함) 캡처 + canned records 반환."""
    captured = {}

    def fake_get(url, params):
        captured["url"] = url
        captured["params"] = params
        return {"records": records, "offset": None}

    return fake_get, captured


def test_formula_excludes_real_terminal_statuses(monkeypatch):
    fake_get, captured = _make_capture([])
    monkeypatch.setattr(wr, "_get", fake_get)

    wr.fetch_auto_targets("2026-06-29", rolling_days=2)
    formula = captured["params"]["filterByFormula"]

    # 실제 Airtable 옵션 제외
    assert "'출하 완료'" in formula
    assert "'진행 취소'" in formula
    # 존재하지 않던 과거 값은 사라져야 함 (regression guard)
    assert "발송완료" not in formula
    assert "배달완료" not in formula
    assert "반품" not in formula


def test_formula_has_serverside_date_window(monkeypatch):
    fake_get, captured = _make_capture([])
    monkeypatch.setattr(wr, "_get", fake_get)

    wr.fetch_auto_targets("2026-06-29", rolling_days=2)
    formula = captured["params"]["filterByFormula"]

    # 전체 이력 스캔 방지: 날짜창이 서버사이드로 들어가야 함
    assert "IS_AFTER" in formula
    assert "IS_BEFORE" in formula
    assert wr.FLD_SHIP_DATE in formula


def test_python_window_filter_keeps_only_in_window(monkeypatch):
    # window: 2026-06-29 ~ rolling 2 영업일(=07-01). 경계 밖은 Python-side 에서 제거.
    records = [
        {"id": "in1", "fields": {wr.FLD_SHIP_DATE: "2026-06-29"}},
        {"id": "in2", "fields": {wr.FLD_SHIP_DATE: "2026-06-30"}},
        {"id": "past", "fields": {wr.FLD_SHIP_DATE: "2026-06-20"}},
        {"id": "future", "fields": {wr.FLD_SHIP_DATE: "2026-08-01"}},
        {"id": "nodate", "fields": {}},
    ]
    fake_get, _ = _make_capture(records)
    monkeypatch.setattr(wr, "_get", fake_get)

    out = wr.fetch_auto_targets("2026-06-29", rolling_days=2)
    ids = {r["id"] for r in out}
    assert "in1" in ids and "in2" in ids
    assert "past" not in ids
    assert "future" not in ids
    assert "nodate" not in ids
