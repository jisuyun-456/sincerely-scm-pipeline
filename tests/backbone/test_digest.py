"""P6b Slack digest 빌더 테스트 (순수 — IO 없음).

spec §3.2: 신규 주문 ≥1건인 tick만 digest (주문 수·부족자재 top·창고 경고).
P6a 학습 1: 부분 216을 노이즈로 만들지 말 것 — top-N 부족자재만.
"""
from harness.backbone.digest import (
    aggregate_shortages,
    build_digest,
    staging_warnings,
)


def _result(action, status="부분", shortage=None, staging=None, pid="PNA1_굿즈"):
    row = {"전파ID": pid, "전파상태": status}
    if shortage is not None:
        row["부족자재_요약"] = shortage
    if staging is not None:
        row["창고적재_예상"] = staging
    return {"row": row, "action": action, "status": status, "reasons": []}


def _totals(new=0, changed=0, unchanged=0, 완결=0, 부분=0, 끊김=0):
    return {"units": new + changed + unchanged, "new": new, "changed": changed,
            "unchanged": unchanged, "완결": 완결, "부분": 부분, "끊김": 끊김}


# ─── aggregate_shortages ─────────────────────────────────────────

def test_aggregate_shortages_parses_and_sums_by_pt():
    results = [
        _result("new", shortage="PT0001×500(재고 200/소요 700)\n"
                                "PT0002×30(재고 0/소요 30)"),
        _result("changed", shortage="PT0001×100(재고 0/소요 100)", pid="PNA2_굿즈"),
    ]
    out = aggregate_shortages(results)
    assert out == [("PT0001", 600.0), ("PT0002", 30.0)]


def test_aggregate_shortages_handles_korean_suffix_pt():
    results = [_result("new", shortage="PT4900-아크릴×40(재고 10/소요 50)")]
    assert aggregate_shortages(results) == [("PT4900-아크릴", 40.0)]


def test_aggregate_shortages_skips_unchanged_and_blank():
    results = [
        _result("unchanged", shortage="PT0001×500(재고 0/소요 500)"),
        _result("new", shortage="부족분 없음"),
        _result("new"),                        # 부족자재_요약 키 없음 (BOM 없음)
    ]
    assert aggregate_shortages(results) == []


# ─── staging_warnings ────────────────────────────────────────────

def test_staging_warnings_flags_over_100pct():
    results = [
        _result("new", staging="staging 12.0%→45.0% (Max 57.6m³)"),
        _result("new", staging="staging 90.0%→130.5% (Max 57.6m³)", pid="PNA2_굿즈"),
        _result("unchanged", staging="staging 50.0%→200.0% (Max 57.6m³)",
                pid="PNA3_굿즈"),   # unchanged는 경고 제외
    ]
    warns = staging_warnings(results)
    assert warns == [("PNA2_굿즈", 130.5)]


def test_staging_warnings_ignores_unmeasured():
    results = [_result("new", staging="부분: Max_CBM 미실측 (입하 +3.2m³)")]
    assert staging_warnings(results) == []


# ─── build_digest ────────────────────────────────────────────────

def test_build_digest_none_when_no_new_units():
    results = [_result("changed", shortage="PT0001×10(재고 0/소요 10)")]
    assert build_digest(results, _totals(changed=1, 부분=1), "20260612-1000", 14) is None


def test_build_digest_contains_counts_topn_and_warning():
    results = [
        _result("new", status="완결", shortage="PT0001×500(재고 0/소요 500)"),
        _result("new", shortage="PT0002×900(재고 0/소요 900)",
                staging="staging 90.0%→130.5% (Max 57.6m³)", pid="PNA2_굿즈"),
    ]
    text = build_digest(results, _totals(new=2, unchanged=3, 완결=1, 부분=1),
                        "20260612-1000", 14, top_n=1)
    assert text is not None
    assert "20260612-1000" in text
    assert "신규 2" in text and "변경 0" in text
    assert "완결 1" in text and "부분 1" in text
    assert "PT0002×900" in text          # top_n=1 — 최대 부족분만
    assert "PT0001" not in text
    assert "PNA2_굿즈" in text and "130.5%" in text


def test_build_digest_no_shortage_no_warning_sections():
    results = [_result("new", status="완결", shortage="부족분 없음")]
    text = build_digest(results, _totals(new=1, 완결=1), "20260612-1000", 14)
    assert text is not None
    assert "부족자재" not in text
    assert "경고" not in text
