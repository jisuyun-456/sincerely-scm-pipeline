"""Tests for goods_code_audit pure functions (네트워크 0).

VC-3: 알려진 케이스 분류 (DSKT/TWKF→alias, OFMP→register, DRCG→alias, SSSV→service).
VC-6: normalize_code·annotate_alias·classify 순수함수 검증.
"""
from harness.backbone.keys import is_service
from scripts.backbone.goods_code_audit import (
    annotate_alias,
    classify,
    normalize_code,
)


# ── normalize_code ────────────────────────────────────────────────────────────

def test_normalize_code_list_unwrap():
    assert normalize_code(["ofmp"]) == "OFMP"
    assert normalize_code([]) == ""


def test_normalize_code_scalar_and_blank():
    assert normalize_code(" dskt ") == "DSKT"
    assert normalize_code(None) == ""
    assert normalize_code("") == ""


# ── annotate_alias ────────────────────────────────────────────────────────────

def test_annotate_alias_one_to_one():
    a = annotate_alias("DSKT")
    assert a["kind"] == "1:1" and a["target"] == "DSKS"


def test_annotate_alias_size_family():
    a = annotate_alias("DRCG")
    assert a["kind"] == "size_family" and a["targets"]["__default__"] == "SOLB"


def test_annotate_alias_synthetic():
    a = annotate_alias("TWKF")
    assert a["kind"] == "synthetic" and a["spec"]["qty_per_box"] == 12


def test_annotate_alias_none_for_plain_code():
    assert annotate_alias("OFMP") is None
    assert annotate_alias("ZZZZ") is None


# ── classify (known cases) ────────────────────────────────────────────────────

def _sources():
    return {
        "product": {
            # registered & healthy, but never shipped → stale_unused
            "ABCD": {"name": "통제품", "box_type": "대형", "qty_per_box": 10,
                     "cbm_per_box": 0.1066, "rec_id": "rec1"},
            # registered but box/CBM 미입력 → data_gap
            "GAPC": {"name": "갭품목", "box_type": "", "qty_per_box": 1,
                     "cbm_per_box": 0.0, "rec_id": "rec2"},
            # registered, shipped, name-weak → name_match_weak
            "NMWK": {"name": "정상이름", "box_type": "대형", "qty_per_box": 20,
                     "cbm_per_box": 0.1066, "rec_id": "rec3"},
        },
        "sync": {"OFMP", "DSKT", "TWKF", "DRCG", "NMWK", "ORPH", "SSSV"},
        "ship": {"OFMP": 3, "DSKT": 1, "TWKF": 2, "DRCG": 5, "NMWK": 4, "SSSV": 4},
        "ship_goods": {
            "OFMP": ["오피스 마우스패드"], "DSKT": ["데스크테리어 매트"],
            "TWKF": ["Lite 스트랩 박스"], "DRCG": ["Solid G형박스(M사이즈)"],
            "NMWK": ["전혀 다른 이름"],
            # SSSV: placeholder인데 라인 굿즈명이 service로 안 잡히는 케이스(실데이터)
            "SSSV": ["긴급", "Motion 스탠다드박스"],
        },
        "name_weak": {"NMWK": [{"name": "전혀 다른 이름", "score": 0.0,
                                "matched_code": None}]},
        "csv": None,
    }


def test_classify_register_in_product():
    b = classify(_sources())
    codes = {r["code"] for r in b["register_in_product"]}
    assert "OFMP" in codes                      # plain mismatch → 등록 필요
    assert codes.isdisjoint({"DSKT", "TWKF", "DRCG"})  # aliased는 register 아님
    assert "SSSV" not in codes                  # service 코드는 register 아님


def test_classify_service_code_guard():
    # SSSV는 라인 굿즈명이 service로 안 잡혀도 코드 자체로 service 처리
    b = classify(_sources())
    assert "SSSV" in {r["code"] for r in b["service_codes"]}


def test_classify_alias_papered_over():
    b = classify(_sources())
    by = {r["code"]: r["alias"]["kind"] for r in b["alias_papered_over"]}
    assert by["DSKT"] == "1:1"
    assert by["TWKF"] == "synthetic"
    assert by["DRCG"] == "size_family"


def test_classify_data_gap_and_stale():
    b = classify(_sources())
    assert {r["code"] for r in b["data_gap"]} == {"GAPC"}
    assert "ABCD" in {r["code"] for r in b["stale_unused"]}


def test_classify_name_match_weak():
    b = classify(_sources())
    assert {r["code"] for r in b["name_match_weak"]} == {"NMWK"}


def test_classify_sync_only_unshipped():
    b = classify(_sources())
    assert "ORPH" in {r["code"] for r in b["sync_only_unshipped"]}


def test_classify_drift_vs_master():
    s = _sources()
    s["csv"] = {"NMWK": {"box_type": "특대형", "qty_per_box": 20, "cbm_per_box": 0.1066}}
    b = classify(s)
    drift = {r["code"]: r["diffs"] for r in b["drift_vs_master"]}
    assert "NMWK" in drift and "box_type" in drift["NMWK"]   # 대형 vs 특대형


def test_classify_csv_only_code_registers():
    # 견적서 master에만 있고 Product/sync/출하 어디에도 없는 신규 코드 → register_in_product
    s = _sources()
    s["csv"] = {"NEWQ": {"box_type": "대형", "qty_per_box": 10, "cbm_per_box": 0.1066}}
    b = classify(s)
    reg = {r["code"]: r for r in b["register_in_product"]}
    assert "NEWQ" in reg and reg["NEWQ"].get("source") == "csv_master"


# ── service filter (load_sources가 의존하는 is_service) — SSSV/STCK→service ──

def test_service_names_are_filtered():
    assert is_service("키트포장")          # SSSV류
    assert is_service("키트 포장")          # V5.1 공백 변형
    assert is_service("0428")              # STCK 날짜 placeholder
    assert not is_service("오피스 마우스패드")  # 실물 → 통과
