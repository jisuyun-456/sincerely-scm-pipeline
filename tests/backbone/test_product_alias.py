"""Tests for V2 견적코드 reconciliation (alias + size-family resolution)."""
from harness.backbone.product_alias import (
    parse_size,
    resolve_registered_code,
    remap_lines,
    inject_synthetic,
    resolve_product_entry,
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
    # 데스크테리어 매트 형제 (DSKT alias target — 기본형, 사용자 확정 2026-06-16)
    "dsks": {"cbm_per_box": 0.1066, "qty_per_box": 30},
    "dskw": {"cbm_per_box": 0.1066, "qty_per_box": 25},
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


# ── ② #1: DSKT alias + TWKF synthetic registration (사용자 확정 2026-06-16) ──

def test_alias_dskt_to_dsks():
    # '데스크테리어 매트'(사이즈 무표기) → 기본형 DSKS (대형/30, 0.1066)
    assert resolve_registered_code("DSKT", "데스크테리어 매트", LOOKUP) == "DSKS"


def test_inject_synthetic_adds_twkf():
    lk = {}
    inject_synthetic(lk)
    e = lk["twkf"]
    assert e["code"] == "TWKF"
    assert e["box_type"] == "대형"
    assert e["qty_per_box"] == 12
    assert e["cbm_per_box"] == 0.1066          # 대형 표준 = L510 (510×510×410)
    # 이름 키로도 조회 가능 (estimate match_product 경로)
    assert lk["lite 스트랩 박스"] is e


def test_inject_synthetic_skips_if_already_registered():
    # Product에 TWKF가 이미 있으면(향후 ⑤ 소스정합) 덮어쓰지 않음 — Product 우선
    lk = {"twkf": {"code": "TWKF", "box_type": "특대형",
                   "qty_per_box": 7, "cbm_per_box": 0.1662}}
    inject_synthetic(lk)
    assert lk["twkf"]["qty_per_box"] == 7      # 변경 없음


def test_twkf_resolves_after_injection():
    lk = {}
    inject_synthetic(lk)
    # 주입 후 TWKF는 '등록됨'으로 취급 → 원본 코드 그대로 (estimate가 매칭)
    assert resolve_registered_code("TWKF", "Lite 스트랩 박스", lk) == "TWKF"


def test_twkf_unresolved_before_injection():
    # 주입 전에는 미등록 → 원본 반환 (S5 정직 미산출)
    assert resolve_registered_code("TWKF", "Lite 스트랩 박스", {}) == "TWKF"
    assert "twkf" not in {}


# ── 공유 리졸버 resolve_product_entry (D — 캐스케이드·정산 단일 코드 경로) ──

# name 키까지 포함한 lookup (match_product Jaccard 폴백 테스트용)
NAMED = {}
_omp = {"name": "오피스 마우스패드", "code": "OMPD", "cbm_per_box": 0.0201,
        "qty_per_box": 50, "box_type": "중형", "rec_id": "r1"}
NAMED["ompd"] = _omp
NAMED["오피스 마우스패드"] = _omp


def test_resolve_entry_code_path():
    # 코드 직접 (+alias): DSKT → DSKS
    e, rc, m = resolve_product_entry("데스크테리어 매트", "DSKT", {}, LOOKUP)
    assert rc == "DSKS" and m == "code" and e is LOOKUP["dsks"]


def test_resolve_entry_name2code_alias():
    # 이름 → sync_item 코드(LOPU) → alias → LSPO
    e, rc, m = resolve_product_entry("로고스트랩 파우치", None,
                                     {"로고스트랩 파우치": "LOPU"}, LOOKUP)
    assert rc == "LSPO" and m == "name2code" and e is LOOKUP["lspo"]


def test_resolve_entry_name2code_size_family():
    # normalize_goods가 (M사이즈) 제거 → name2code 키는 베이스명, 사이즈는 원본명에서 파싱
    e, rc, m = resolve_product_entry("Solid G형박스(M사이즈)", None,
                                     {"Solid G형박스": "DRCG"}, LOOKUP)
    assert rc == "SOLB" and m == "name2code"


def test_resolve_entry_synthetic_twkf():
    lk = dict(LOOKUP)
    inject_synthetic(lk)
    e, rc, m = resolve_product_entry("Lite 스트랩 박스", None,
                                     {"Lite 스트랩 박스": "TWKF"}, lk)
    assert rc == "TWKF" and m == "name2code" and e["qty_per_box"] == 12


def test_resolve_entry_jaccard_fallback():
    # name2code 없음 → 현행 Jaccard 폴백 (정산 하위호환)
    e, rc, m = resolve_product_entry("오피스 마우스패드", None, {}, NAMED)
    assert m == "jaccard" and rc == "OMPD" and e is _omp


def test_resolve_entry_unmatched():
    e, rc, m = resolve_product_entry("존재하지않는무언가", None, {}, NAMED)
    assert e is None and rc is None and m == "unmatched"


def _norm_lookup():
    """'데일리 짐색' 룩업 — '데일리짐색(단품)'은 정규화해야 해소된다.

    ⚠️ 무공백 alias 키('데일리짐색')를 **명시적으로** 넣어야 한다. 운영에서는
    load_product_lookup(cbm_calc.py:114-123)이 자동 생성하지만, 테스트는 dict를
    손으로 만들므로 자동 생성이 일어나지 않는다. 없으면 정규화 후에도
    Jaccard가 0.0(토큰 '데일리짐색' vs {'데일리','짐색'})이라 재시도가 실패한다.
    """
    e = {"rec_id": "r9", "name": "데일리 짐색", "code": "DLYG",
         "box_type": "대형", "qty_per_box": 101, "cbm_per_box": 0.1066}
    return {"데일리 짐색": e, "dlyg": e, "데일리짐색": e}


def test_normalize_retry_resolves_paren_suffix():
    # '(단품)' 접미 때문에 직접 Jaccard 실패 → normalize_goods로 괄호 제거 후 해소.
    from harness.backbone.product_alias import resolve_product_entry
    entry, code, method = resolve_product_entry(
        "데일리짐색(단품)", None, None, _norm_lookup())
    assert entry is not None
    assert code == "DLYG"
    assert method == "jaccard_norm"


def test_name2code_already_normalizes_so_no_retry_needed():
    # 회귀 가드: 2단이 name2code.get(normalize_goods(name))이므로 '(단품)'은 이미 해소된다.
    # 4단 재시도가 2단을 중복하지 않음을 고정한다.
    from harness.backbone.product_alias import resolve_product_entry
    entry, code, method = resolve_product_entry(
        "데일리짐색(단품)", None, {"데일리짐색": "DLYG"}, _norm_lookup())
    assert entry is not None
    assert code == "DLYG"
    assert method == "name2code"


def test_normalize_retry_not_used_when_direct_match_works():
    # 직접 매칭이 되면 재시도하지 않는다 — method는 기존 값 그대로.
    from harness.backbone.product_alias import resolve_product_entry
    entry, code, method = resolve_product_entry(
        "데일리 짐색", None, None, _norm_lookup())
    assert entry is not None
    assert method == "jaccard"


def test_normalize_retry_still_unmatched_returns_unmatched():
    # 정규화해도 못 찾으면 기존대로 unmatched.
    from harness.backbone.product_alias import resolve_product_entry
    entry, code, method = resolve_product_entry(
        "존재하지않는물건(단품)", None, None, _norm_lookup())
    assert entry is None
    assert code is None
    assert method == "unmatched"


# ── 1.5단 크로스워크 결정론 계층 (spec §4.1) ──────────────────────────────
def _cw_lookup():
    e = {"rec_id": "rC", "name": "로고스트랩 파우치", "code": "LSPO",
         "box_type": "대형", "qty_per_box": 100, "cbm_per_box": 0.1066}
    other = {"rec_id": "rD", "name": "다른 굿즈", "code": "OTHR",
             "box_type": "중형", "qty_per_box": 50, "cbm_per_box": 0.0201}
    return {"로고스트랩 파우치": e, "lspo": e, "다른 굿즈": other, "othr": other}


def test_crosswalk_stage_resolves_before_name2code(monkeypatch):
    # 크로스워크 확정행이 sync_item(name2code)보다 우선 — 사람 판정 우선
    import harness.backbone.product_alias as pa
    from harness.backbone.crosswalk_store import crosswalk_key
    monkeypatch.setattr(pa, "load_crosswalk",
                        lambda: {crosswalk_key("로고스트랩파우치(단품)"): "LSPO"})
    entry, code, method = pa.resolve_product_entry(
        "로고스트랩파우치(단품)", None, {"로고스트랩파우치": "OTHR"}, _cw_lookup())
    assert code == "LSPO"
    assert method == "crosswalk"


def test_crosswalk_miss_falls_through_to_existing_stages(monkeypatch):
    import harness.backbone.product_alias as pa
    monkeypatch.setattr(pa, "load_crosswalk", lambda: {})
    entry, code, method = pa.resolve_product_entry(
        "로고스트랩 파우치", None, None, _cw_lookup())
    assert entry is not None
    assert method == "jaccard"


def test_crosswalk_pointing_at_cbmless_product_falls_through(monkeypatch):
    # 확정행이 CBM 0 Product를 가리키면 0짜리 entry 반환 금지 → 퍼지로 통과 (spec §4.4)
    import harness.backbone.product_alias as pa
    from harness.backbone.crosswalk_store import crosswalk_key
    lk = {"제로박스": {"rec_id": "rZ", "name": "제로박스", "code": "ZERO",
                    "box_type": "", "qty_per_box": 1, "cbm_per_box": 0.0},
          "zero": {"rec_id": "rZ", "name": "제로박스", "code": "ZERO",
                   "box_type": "", "qty_per_box": 1, "cbm_per_box": 0.0}}
    monkeypatch.setattr(pa, "load_crosswalk",
                        lambda: {crosswalk_key("제로박스"): "ZERO"})
    entry, code, method = pa.resolve_product_entry("제로박스", None, None, lk)
    assert method != "crosswalk"


def test_crosswalk_not_used_when_code_given(monkeypatch):
    # 1단(code 직접)이 1.5단보다 우선
    import harness.backbone.product_alias as pa
    from harness.backbone.crosswalk_store import crosswalk_key
    monkeypatch.setattr(pa, "load_crosswalk",
                        lambda: {crosswalk_key("로고스트랩 파우치"): "OTHR"})
    entry, code, method = pa.resolve_product_entry(
        "로고스트랩 파우치", "LSPO", None, _cw_lookup())
    assert code == "LSPO"
    assert method == "code"
