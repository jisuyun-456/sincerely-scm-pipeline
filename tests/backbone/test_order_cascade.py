"""P6a order-trigger 캐스케이드 코어 테스트 (순수 — IO 없음).

spec: docs/superpowers/specs/2026-06-11-cbm-p6-order-cascade-design.md
커버: S0 수집·dedup·14d 윈도우 / 어댑터(order→estimator 입력) / S2~S6 스테이지 /
부분·끊김 마킹 / S7 idempotency(decide_insert).
"""
from datetime import date, datetime, timezone

import pytest

from harness.backbone.cascade import (
    CascadeContext,
    build_order_lines,
    collect_units,
    decide_insert,
    fare_preview,
    latest_ledger_by_pid,
    mh_for_inbound,
    run_unit,
    select_bom_rows,
    shortage_text,
    stage_inbound,
    staging_projection,
    stock_by_pt,
    wave_preview,
)

_NOW = datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)
_RATES = {"park_base": 55_421, "park_km": 831}


def _order(pc, goods, part, oqty, code=None, created="2026-06-10T00:00:00.000Z"):
    f = {"project_code": pc, "굿즈 주문 수량 (자동)": goods, "파츠명": part,
         "주문수량": oqty}
    if code is not None:
        f["굿즈코드 (from sync_itemdb)"] = code
    return {"id": f"rec{pc}{part}", "createdTime": created, "fields": f}


# ─── S0: collect_units ───────────────────────────────────────────

def test_collect_units_groups_by_pna_goods():
    recs = [
        _order("PNA50702_심볼", "심볼아크릴트로피 125", "PT4900-아크릴", 125),
        _order("PNA50702_심볼", "심볼아크릴트로피 125", "PT4906-받침", 125),
        _order("PNA50703", "키트 50", "PT0100-박스", 100),
    ]
    units = collect_units(recs, _NOW)
    assert len(units) == 2
    u = {(x.pna, x.goods_name): x for x in units}
    sym = u[("PNA50702", "심볼아크릴트로피")]
    assert sym.goods_qty == 125
    assert len(sym.rows) == 2
    assert u[("PNA50703", "키트")].goods_qty == 50


def test_collect_units_window_filters_old_orders():
    recs = [
        _order("PNA1", "굿즈 10", "PT0001-a", 10, created="2026-05-01T00:00:00.000Z"),
        _order("PNA2", "굿즈 10", "PT0002-b", 10, created="2026-06-10T00:00:00.000Z"),
    ]
    units = collect_units(recs, _NOW, window_days=14)
    assert [x.pna for x in units] == ["PNA2"]


def test_collect_units_skips_service_and_blank_pna():
    recs = [
        _order("PNA1", "배송 다마스 1", "PT0001-a", 1),     # 서비스
        _order("", "굿즈 10", "PT0002-b", 10),               # PNA 없음
        _order("PNA3", "", "PT0003-c", 10),                  # 굿즈명 없음
    ]
    assert collect_units(recs, _NOW) == []


def test_collect_units_created_max_is_latest_row():
    recs = [
        _order("PNA1", "굿즈 10", "PT0001-a", 10, created="2026-06-08T00:00:00.000Z"),
        _order("PNA1", "굿즈 10", "PT0002-b", 10, created="2026-06-10T05:00:00.000Z"),
    ]
    units = collect_units(recs, _NOW)
    assert units[0].created_max == "2026-06-10T05:00:00.000Z"


# ─── S0: ledger dedup ────────────────────────────────────────────

def test_latest_ledger_by_pid_picks_max_created():
    rows = [
        {"id": "r1", "createdTime": "2026-06-01T00:00:00.000Z",
         "fields": {"전파ID": "PNA1_굿즈", "전파상태": "부분"}},
        {"id": "r2", "createdTime": "2026-06-09T00:00:00.000Z",
         "fields": {"전파ID": "PNA1_굿즈", "전파상태": "완결"}},
    ]
    latest = latest_ledger_by_pid(rows)
    assert latest["PNA1_굿즈"]["fields"]["전파상태"] == "완결"


# ─── 어댑터 (grill Q2 — silent-unmatched 방지) ───────────────────

def test_adapter_direct_code_qty_summed():
    recs = [
        _order("PNA1", "굿즈 10", "PT0001-a", 10, code="SBAT"),
        _order("PNA1", "굿즈 10", "PT0002-b", 15, code="SBAT"),
    ]
    units = collect_units(recs, _NOW)
    out = build_order_lines(units[0], pkg_map={})
    assert out["lines"] == [("SBAT", 25.0)]
    assert out["code"] == "SBAT"
    assert out["pts"] == ["PT0001", "PT0002"]


def test_adapter_list_unwrap_and_pkg_fallback():
    recs = [_order("PNA1", "굿즈 10", "PT0001-a", 10, code=["TWLB"])]
    out = build_order_lines(collect_units(recs, _NOW)[0], pkg_map={})
    assert out["lines"] == [("TWLB", 10.0)]

    recs2 = [_order("PNA2_x", "굿즈 10", "PT0001-a", 10)]   # blank code
    out2 = build_order_lines(collect_units(recs2, _NOW)[0], pkg_map={"PNA2": "KITA"})
    assert out2["lines"] == [("KITA", 10.0)]
    assert out2["src_counts"]["pkg"] == 1


def test_adapter_unresolved_returns_empty_lines():
    recs = [_order("PNA9", "굿즈 10", "PT0001-a", 10)]
    out = build_order_lines(collect_units(recs, _NOW)[0], pkg_map={})
    assert out["lines"] == []
    assert out["code"] is None


# ─── S2: 재고·BOM ────────────────────────────────────────────────

_STOCK = [
    {"pt": "PT4900", "stock": 55, "warehouse": "베스트원",
     "zone_type": "STORAGE", "stock_type": "UNRESTRICTED"},
    {"pt": "PT4900", "stock": 100, "warehouse": "에이원센터",
     "zone_type": "INBOUND_STAGING", "stock_type": "UNRESTRICTED"},  # MRP 제외
    {"pt": "PT4906", "stock": 500, "warehouse": "베스트원",
     "zone_type": "STORAGE", "stock_type": "UNRESTRICTED"},
    {"pt": "PT4906", "stock": 30, "warehouse": "베스트원",
     "zone_type": "STORAGE", "stock_type": "QC_HOLD"},               # MRP 제외
]


def test_stock_by_pt_storage_unrestricted_only():
    s = stock_by_pt(_STOCK)
    assert s == {"PT4900": 55.0, "PT4906": 500.0}


_BOM_FIELDS = [
    {"프로젝트코드": "PNA50702", "모품목_굿즈명": "심볼아크릴트로피",
     "소품목_PT": "PT4900", "소요량_개당": 1.0, "검증상태": "검증완료"},
    {"프로젝트코드": "PNA50702", "모품목_굿즈명": "심볼아크릴트로피",
     "소품목_PT": "PT4900", "소요량_개당": 2.0, "검증상태": "이송"},   # 검증완료 우선으로 무시
    {"프로젝트코드": "PNA50702", "모품목_굿즈명": "심볼아크릴트로피",
     "소품목_PT": "PT4906", "소요량_개당": 1.0, "검증상태": "이송"},
    {"프로젝트코드": "PNA99999", "모품목_굿즈명": "다른굿즈",
     "소품목_PT": "PT0001", "소요량_개당": 1.0, "검증상태": "검증완료"},
]


def test_select_bom_rows_verified_first_per_pt():
    rows, n_verified = select_bom_rows("PNA50702", "심볼아크릴트로피", _BOM_FIELDS)
    by_pt = {r["소품목_PT"]: r["소요량_개당"] for r in rows}
    assert by_pt == {"PT4900": 1.0, "PT4906": 1.0}   # PT4900은 검증완료행 채택
    assert n_verified == 1


def test_select_bom_rows_fallback_from_orders():
    recs = [_order("PNA7", "굿즈 50", "PT0700-a", 100)]
    unit = collect_units(recs, _NOW)[0]
    rows, n_verified = select_bom_rows("PNA7", "굿즈", [], unit=unit)
    assert rows == [{"소품목_PT": "PT0700", "소요량_개당": 2.0}]   # 100/50
    assert n_verified == 0


# ─── S3: 입하 CBM·M/H ────────────────────────────────────────────

def test_mh_for_inbound_pinned_constants():
    # scripts/mh_backfill_to_ibsa.py v2026-05-iter22 동일 상수 검증
    # cbm=1.0, qty=100: recv 4.0×1.15=4.6 + qc 4.0×1.15=4.6
    # + putaway (3+2)×1.15=5.75 + sample 2.5 + counting 3.0 = 20.45min
    assert mh_for_inbound(1.0, 100) == pytest.approx(20.45 / 60, abs=0.005)


def test_stage_inbound_cbm_mh_and_uncovered():
    reqs = [
        {"pt": "PT4900", "gross": 125, "stock": 55, "shortfall": 70},
        {"pt": "PT4906", "gross": 125, "stock": 500, "shortfall": 0},   # 부족 없음 — 제외
        {"pt": "PT0009", "gross": 10, "stock": 0, "shortfall": 10},     # CBM 미산출
    ]
    out = stage_inbound(reqs, {"PT4900": 0.02, "PT4906": 0.001})
    assert out["inbound_cbm"] == pytest.approx(1.4, abs=1e-6)   # 70×0.02
    assert out["uncovered"] == ["PT0009"]
    assert out["mh_hours"] > 0


def test_shortage_text_format():
    reqs = [{"pt": "PT4900", "gross": 125, "stock": 55, "shortfall": 70},
            {"pt": "PT4906", "gross": 125, "stock": 500, "shortfall": 0}]
    assert shortage_text(reqs) == "PT4900×70(재고 55/소요 125)"


# ─── S4: 창고 투영 ───────────────────────────────────────────────

def test_staging_projection_now_to_after():
    txt, ok = staging_projection(_STOCK, {"PT4900": 0.02}, inbound_cbm=1.4,
                                 max_staging_cbm=57.6)
    # staging now = 100×0.02 = 2.0 → 3.5% / after 3.4 → 5.9%
    assert ok
    assert txt == "staging 3.5%→5.9% (Max 57.6m³)"


def test_staging_projection_without_max_is_partial():
    txt, ok = staging_projection(_STOCK, {}, inbound_cbm=1.0, max_staging_cbm=None)
    assert not ok
    assert "Max_CBM 미실측" in txt


# ─── S5/S6: 프리뷰 ───────────────────────────────────────────────

def test_wave_preview_feasible_tiers():
    txt, ok = wave_preview(2.4)
    assert ok and txt.startswith("W1/W2/W3 가능")
    txt2, ok2 = wave_preview(5.0)    # > W1 4.5
    assert ok2 and txt2.startswith("W2/W3 가능")
    txt3, ok3 = wave_preview(10.0)   # > W3 9.486
    assert not ok3 and "용량 초과" in txt3
    txt4, ok4 = wave_preview(0.0)
    assert not ok4 and "미산출" in txt4


def test_fare_preview_band():
    txt, ok = fare_preview(2.4, _RATES)
    # round_up_500(55421+831×10)=64000 / round_up_500(55421+831×60)=105500
    assert ok
    assert txt == "₩64,000~₩105,500 (주소 미확정·수도권 거리대)"
    txt2, ok2 = fare_preview(0.0, _RATES)
    assert not ok2 and "미산출" in txt2


# ─── S7: idempotency ─────────────────────────────────────────────

def test_decide_insert_new_changed_unchanged():
    row = {"전파ID": "PNA1_굿즈", "전파상태": "완결", "고객주문수량": 10,
           "추정_CBM_m3": 0.28140000001, "부족자재_요약": "PT1×5(재고 5/소요 10)"}
    assert decide_insert(row, None) == "new"
    prior = {"전파ID": "PNA1_굿즈", "전파상태": "완결", "고객주문수량": 10,
             "추정_CBM_m3": 0.2814, "부족자재_요약": "PT1×5(재고 5/소요 10)"}
    assert decide_insert(row, prior) == "unchanged"   # float tol 1e-4
    prior2 = dict(prior, 전파상태="부분")
    assert decide_insert(row, prior2) == "changed"


def test_decide_insert_empty_string_equals_absent():
    """P6b VC-2 실측 — Airtable은 빈 문자열 필드를 응답에서 누락.

    '' 기입 행을 다시 읽으면 키 자체가 없음(None) → ''≠None 비교가
    BOM 없는 14단위를 매 run 재INSERT(영구 churn)시킨 버그 회귀 방지.
    """
    row = {"전파ID": "PNA1_굿즈", "전파상태": "부분", "자재소요_요약": "",
           "추정_CBM_m3": None, "wave_프리뷰": "부분: 출하CBM 미산출"}
    prior = {"전파ID": "PNA1_굿즈", "전파상태": "부분",
             "wave_프리뷰": "부분: 출하CBM 미산출"}   # '' 필드 누락 (Airtable 의미론)
    assert decide_insert(row, prior) == "unchanged"
    # 단, 0 vs 누락은 동일 취급 금지 (수치 0은 실값)
    assert decide_insert(dict(row, 입하CBM_예상_m3=0.0), prior) == "changed"


# ─── run_unit 통합 (부분/끊김 마킹 + 완결 happy path) ────────────

def _ctx(**over):
    base = dict(
        pkg_map={},
        product_lookup={"sbat": {"rec_id": "r", "name": "심볼", "code": "SBAT",
                                 "box_type": "", "qty_per_box": 19,
                                 "cbm_per_box": 0.0201}},
        kit_lookup={},
        shipment_count={},
        bom_fields=_BOM_FIELDS,
        stock_rows=_STOCK,
        part_cbm_by_pt={"PT4900": 0.02, "PT4906": 0.001},
        mes_rows=[],
        name_to_code={},
        product_by_code={},
        max_staging_cbm=57.6,
        rates=_RATES,
        today=date(2026, 6, 11),
    )
    base.update(over)
    return CascadeContext(**base)


def _sym_unit(code="SBAT"):
    recs = [
        _order("PNA50702_심볼", "심볼아크릴트로피 125", "PT4900-아크릴", 125, code=code),
        _order("PNA50702_심볼", "심볼아크릴트로피 125", "PT4906-받침", 125, code=code),
    ]
    return collect_units(recs, _NOW)[0]


def test_run_unit_happy_path_complete():
    out = run_unit(_sym_unit(), None, _ctx(), run_id="20260611-1200")
    row = out["row"]
    assert out["action"] == "new"
    assert row["전파상태"] == "완결"
    assert out["reasons"] == []
    assert row["전파ID"] == "PNA50702_심볼아크릴트로피"
    assert row["부족자재_요약"] == "PT4900×70(재고 55/소요 125)"
    assert row["입하CBM_예상_m3"] == pytest.approx(1.4, abs=1e-6)
    assert row["MH_예상_h"] > 0
    assert row["창고적재_예상"].startswith("staging ")
    assert row["wave_프리뷰"].startswith("W1/W2/W3 가능")
    assert row["운임_예상범위"].startswith("₩")
    assert row["cascade_실행ID"] == "20260611-1200"
    # 출하 CBM: 주문수량 합 250 → ceil(250/19)×0.0201 = 0.2814
    assert row["추정_CBM_m3"] == pytest.approx(0.2814, abs=1e-4)


def test_run_unit_s1_fail_marks_broken():
    out = run_unit(_sym_unit(code=None), None, _ctx(), run_id="20260611-1200")
    assert out["row"]["전파상태"] == "끊김"
    assert any("S1" in r for r in out["reasons"])
    assert out["row"]["cascade_실행ID"] == "20260611-1200"


def test_run_unit_unmatched_code_marks_partial():
    out = run_unit(_sym_unit(code="NOPE"), None, _ctx(), run_id="20260611-1200")
    assert out["row"]["전파상태"] == "부분"
    assert any("S5" in r for r in out["reasons"])
    # S2/S3 트랙은 여전히 산출 (abort 없음)
    assert out["row"]["부족자재_요약"] == "PT4900×70(재고 55/소요 125)"


def test_run_unit_idempotent_unchanged_skip():
    first = run_unit(_sym_unit(), None, _ctx(), run_id="20260611-1000")
    prior = dict(first["row"])
    again = run_unit(_sym_unit(), prior, _ctx(), run_id="20260611-1200")
    assert again["action"] == "unchanged"   # 실행ID 달라도 내용 동일 → INSERT 0
