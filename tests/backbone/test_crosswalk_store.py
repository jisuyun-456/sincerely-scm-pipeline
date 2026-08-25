"""크로스워크 로더 — git-SSOT 결정론 계층 (spec §4.2·§4.3)."""
import pytest

from harness.backbone.crosswalk_store import (
    CrosswalkConflictError,
    clear_cache,
    crosswalk_key,
    load_crosswalk,
    validate_crosswalk,
)

HEADER = "표준키,키유형,TMS_견적코드,매칭방식,매칭신뢰도,검증상태,근거\n"


def _write(tmp_path, rows):
    p = tmp_path / "goods_crosswalk.csv"
    p.write_text(HEADER + "".join(rows), encoding="utf-8")
    return str(p)


def test_key_preserves_paren_and_bracket_variants():
    # 괄호·[n] 접미는 SKU 구분자다 — normalize_goods처럼 제거하면 안 된다(실측 충돌 27건).
    assert crosswalk_key("데일리짐색(단품)") != crosswalk_key("데일리짐색")
    assert crosswalk_key("페이퍼샤쉐[2]") != crosswalk_key("페이퍼샤쉐")
    # 공백·대소문자는 여전히 정규화된다.
    assert crosswalk_key("Simple 슬라이드지퍼백(M)") == crosswalk_key("simple슬라이드지퍼백(m)")


def test_key_distinguishes_paren_sku_discriminator():
    # 동기 사례: 괄호 하나 차이가 실제로 다른 SKU(다른 박스·CBM)를 가리킨다.
    assert crosswalk_key("Simple슬라이드지퍼백(S)") != crosswalk_key("Simple슬라이드지퍼백(M)")


def test_loads_only_confirmed_goods_rows(tmp_path):
    path = _write(tmp_path, [
        "데일리짐색(단품),굿즈명,DLYG,정확,1.0,확정,seed\n",
        "미검증굿즈,굿즈명,XXXX,유사,0.6,미검증,seed\n",
        "보류굿즈,굿즈명,YYYY,유사,0.3,보류,seed\n",
        "LOPU,코드,LSPO,정확,1.0,확정,alias\n",
    ])
    clear_cache()
    m = load_crosswalk(path, _cache=False)
    assert m == {crosswalk_key("데일리짐색(단품)"): "DLYG"}


def test_missing_file_returns_empty(tmp_path):
    clear_cache()
    assert load_crosswalk(str(tmp_path / "nope.csv"), _cache=False) == {}


def test_conflicting_confirmed_rows_excluded_not_raised(tmp_path):
    # 같은 키인데 견적코드가 다른 확정 행 2개 → load_crosswalk는 raise하지 않고
    # 그 키를 양쪽 다 제외한다(§4.2 2026-08-12 개정). 다른(비충돌) 행은 그대로 남는다.
    # 괄호는 이제 키를 보존하므로(단품)/(키트)는 더 이상 충돌하지 않는다 — 공백 변형으로 같은 키를 만든다.
    path = _write(tmp_path, [
        "데일리짐색(단품),굿즈명,DLYG,정확,1.0,확정,seed\n",
        "데일리 짐색(단품),굿즈명,ZZZZ,정확,1.0,확정,seed\n",
        "정상굿즈,굿즈명,GOOD,정확,1.0,확정,seed\n",
    ])
    clear_cache()
    m = load_crosswalk(path, _cache=False)
    assert crosswalk_key("데일리짐색(단품)") not in m
    assert m == {crosswalk_key("정상굿즈"): "GOOD"}


def test_validate_crosswalk_raises_on_conflict(tmp_path):
    # validate_crosswalk는 같은 입력에 대해 loud 실패한다 — 메시지가 키와 두 코드를 모두 지목
    path = _write(tmp_path, [
        "데일리짐색(단품),굿즈명,DLYG,정확,1.0,확정,seed\n",
        "데일리 짐색(단품),굿즈명,ZZZZ,정확,1.0,확정,seed\n",
    ])
    clear_cache()
    with pytest.raises(CrosswalkConflictError) as exc:
        validate_crosswalk(path)
    msg = str(exc.value)
    assert "데일리짐색" in msg
    assert "DLYG" in msg
    assert "ZZZZ" in msg


def test_validate_crosswalk_returns_empty_list_when_clean(tmp_path):
    path = _write(tmp_path, [
        "데일리짐색(단품),굿즈명,DLYG,정확,1.0,확정,seed\n",
        "정상굿즈,굿즈명,GOOD,정확,1.0,확정,seed\n",
    ])
    clear_cache()
    assert validate_crosswalk(path) == []


def test_same_key_same_code_is_not_conflict(tmp_path):
    # 변형 2개가 같은 코드를 가리키는 것은 정상 (충돌 아님) — 공백 변형으로 같은 키를 만든다
    # (괄호는 이제 보존되므로 (단품)/(키트) 변형은 서로 다른 키다).
    path = _write(tmp_path, [
        "데일리짐색(단품),굿즈명,DLYG,정확,1.0,확정,seed\n",
        "데일리 짐색(단품),굿즈명,DLYG,정확,1.0,확정,seed\n",
    ])
    clear_cache()
    assert load_crosswalk(path, _cache=False) == {crosswalk_key("데일리짐색(단품)"): "DLYG"}


def test_blank_fields_skipped(tmp_path):
    path = _write(tmp_path, [
        ",굿즈명,DLYG,정확,1.0,확정,빈표준키\n",
        "빈코드굿즈,굿즈명,,정확,1.0,확정,빈코드\n",
        "정상굿즈,굿즈명,GOOD,정확,1.0,확정,ok\n",
    ])
    clear_cache()
    assert load_crosswalk(path, _cache=False) == {crosswalk_key("정상굿즈"): "GOOD"}


def test_code_is_uppercased(tmp_path):
    path = _write(tmp_path, ["정상굿즈,굿즈명,dlyg,정확,1.0,확정,ok\n"])
    clear_cache()
    assert load_crosswalk(path, _cache=False) == {crosswalk_key("정상굿즈"): "DLYG"}
