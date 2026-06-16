"""Tests for V2 견적코드 reconciliation (alias + size-family resolution)."""
from harness.backbone.product_alias import (
    parse_size,
    resolve_registered_code,
    remap_lines,
)

# Minimal product_lookup mimic: code.lower() → entry with cbm_per_box.
LOOKUP = {
    # registered twins (authoritative)
    "lspo": {"cbm_per_box": 0.1066, "qty_per_box": 100},
    "stnb": {"cbm_per_box": 0.0493, "qty_per_box": 60},
    "wcv": {"cbm_per_box": 0.0098, "qty_per_box": 100},
    "slvr": {"cbm_per_box": 0.1662, "qty_per_box": 20},
    "bctl": {"cbm_per_box": 0.1066, "qty_per_box": 40},
    "cnpg": {"cbm_per_box": 0.0493, "qty_per_box": 100},
    "bmch": {"cbm_per_box": 0.0493, "qty_per_box": 20},
    # size-family SKUs
    "sola": {"cbm_per_box": 0.0493, "qty_per_box": 20},
    "solb": {"cbm_per_box": 0.1066, "qty_per_box": 20},
    "solc": {"cbm_per_box": 0.1662, "qty_per_box": 20},
    "slzb": {"cbm_per_box": 0.0201, "qty_per_box": 35},
    "slzs": {"cbm_per_box": 0.0201, "qty_per_box": 35},
    "vmcm": {"cbm_per_box": 0.0201, "qty_per_box": 48},
    "vmcs": {"cbm_per_box": 0.0201, "qty_per_box": 100},
    "rwcl": {"cbm_per_box": 0.1066, "qty_per_box": 25},
    # a normally-registered code (control)
    "abcd": {"cbm_per_box": 0.02, "qty_per_box": 10},
    # an unpopulated SKU (box/qty blank → cbm 0)
    "slzl": {"cbm_per_box": 0.0, "qty_per_box": 1},
}


def test_parse_size_korean():
    assert parse_size("Solid스탠다드G형박스(M사이즈)") == "M"
    assert parse_size("Solid스탠다드G형박스(L사이즈)키트") == "L"
    assert parse_size("Raw 코튼 파우치(XL사이즈)") == "XL"


def test_parse_size_paren_letter():
    assert parse_size("밸류메모큐브(S)") == "S"
    assert parse_size("밸류메모큐브(M)") == "M"


def test_parse_size_none():
    assert parse_size("로고스트랩 파우치") is None
    assert parse_size("") is None
    assert parse_size(None) is None


def test_alias_exact_twins():
    assert resolve_registered_code("LOPU", "로고스트랩 파우치", LOOKUP) == "LSPO"
    assert resolve_registered_code("STTB", "스탠드-업 칫솔", LOOKUP) == "STNB"
    assert resolve_registered_code("WCCV", "웹캠 커버", LOOKUP) == "WCV"
    assert resolve_registered_code("BMVS", "브릭 메모&캘린더 스탠드 2.0", LOOKUP) == "BMCH"


def test_alias_case_insensitive():
    assert resolve_registered_code("lopu", "로고스트랩 파우치", LOOKUP) == "LSPO"


def test_size_family_parsed():
    assert resolve_registered_code("DRCG", "Solid G형박스(S사이즈)", LOOKUP) == "SOLA"
    assert resolve_registered_code("DRCG", "Solid G형박스(M사이즈)", LOOKUP) == "SOLB"
    assert resolve_registered_code("DRCG", "Solid G형박스(L사이즈)", LOOKUP) == "SOLC"


def test_size_family_default_when_no_size():
    # 굿즈명에 사이즈 없음 → __default__ (SOLB)
    assert resolve_registered_code("DRCG", "Solid 스탠다드 G형박스", LOOKUP) == "SOLB"


def test_size_family_falls_to_default_when_sku_unpopulated():
    # SZBT L → SLZL인데 SLZL은 cbm 0 (미입력) → __default__ SLZB
    assert resolve_registered_code("SZBT", "Simple 슬라이드 지퍼백(L사이즈)", LOOKUP) == "SLZB"


def test_unresolved_returns_original():
    # 등록도 alias도 family도 아님 → 원본 (S5 미산출 보고)
    assert resolve_registered_code("ZZZZ", "알 수 없는 굿즈", LOOKUP) == "ZZZZ"


def test_already_registered_passthrough():
    assert resolve_registered_code("ABCD", "whatever", LOOKUP) == "ABCD"


def test_remap_lines_aggregates_on_collapse():
    # DRCG(no size)→SOLB, 또 다른 DRCG행도 SOLB → 합산
    lines = [("DRCG", 100), ("DRCG", 50), ("ABCD", 10)]
    out = dict(remap_lines(lines, "Solid 스탠다드 G형박스", LOOKUP))
    assert out["SOLB"] == 150
    assert out["ABCD"] == 10


def test_remap_lines_empty():
    assert remap_lines([], "x", LOOKUP) == []
