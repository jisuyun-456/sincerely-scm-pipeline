"""크로스워크 로더 — git-SSOT 결정론 계층 (spec §4.2·§4.3)."""
import pytest

from harness.backbone.crosswalk_store import (
    CrosswalkConflictError,
    clear_cache,
    crosswalk_key,
    load_crosswalk,
)

HEADER = "표준키,키유형,TMS_견적코드,매칭방식,매칭신뢰도,검증상태,근거\n"


def _write(tmp_path, rows):
    p = tmp_path / "goods_crosswalk.csv"
    p.write_text(HEADER + "".join(rows), encoding="utf-8")
    return str(p)


def test_key_normalizes_variants_to_same_key():
    # '(단품)'·'[2]'·'_재제작' 접미는 normalize_goods가 제거 → 같은 키
    assert crosswalk_key("데일리짐색(단품)") == crosswalk_key("데일리짐색")
    assert crosswalk_key("페이퍼샤쉐[2]") == crosswalk_key("페이퍼샤쉐")


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


def test_conflicting_confirmed_rows_raise(tmp_path):
    # 같은 정규화 키인데 견적코드가 다른 확정 행 2개 → 조용한 last-wins 금지
    path = _write(tmp_path, [
        "데일리짐색(단품),굿즈명,DLYG,정확,1.0,확정,seed\n",
        "데일리짐색(키트),굿즈명,ZZZZ,정확,1.0,확정,seed\n",
    ])
    clear_cache()
    with pytest.raises(CrosswalkConflictError) as exc:
        load_crosswalk(path, _cache=False)
    assert "데일리짐색" in str(exc.value)


def test_same_key_same_code_is_not_conflict(tmp_path):
    # 변형 2개가 같은 코드를 가리키는 것은 정상 (충돌 아님)
    path = _write(tmp_path, [
        "데일리짐색(단품),굿즈명,DLYG,정확,1.0,확정,seed\n",
        "데일리짐색(키트),굿즈명,DLYG,정확,1.0,확정,seed\n",
    ])
    clear_cache()
    assert load_crosswalk(path, _cache=False) == {crosswalk_key("데일리짐색"): "DLYG"}


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
