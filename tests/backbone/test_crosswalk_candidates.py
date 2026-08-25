"""후보 생성 — INSERT-only 병합 + 승급 규칙 (spec §6.2·§6.3)."""
from scripts.crosswalk.build_candidates import (
    classify,
    find_ambiguous_names,
    merge_rows,
    read_csv,
    write_csv,
)


def _row(key, code, status="미검증", ktype="굿즈명"):
    return {"표준키": key, "키유형": ktype, "TMS_견적코드": code,
            "매칭방식": "유사", "매칭신뢰도": "0.8", "검증상태": status, "근거": "t"}


def test_classify_exact_is_auto_confirmed():
    # score 1.0 = 정규화 후 exact → 철자변형일 뿐이므로 자동 확정 (D2)
    assert classify(1.0, True) == ("확정", "정확")


def test_classify_fuzzy_needs_human():
    assert classify(0.82, True) == ("미검증", "유사")


def test_classify_low_score_is_pending_spec():
    assert classify(0.42, True) == ("보류", "유사")


def test_classify_unmatched_is_pending_spec():
    assert classify(0.0, False) == ("보류", "수기")


def test_merge_preserves_human_decisions():
    # 사람이 미검증→확정으로 올린 행을 재실행이 되돌리면 안 된다 (§6.3)
    existing = [_row("데일리짐색(단품)", "DLYG", status="확정")]
    candidates = [_row("데일리짐색(단품)", "ZZZZ", status="미검증")]
    merged, added = merge_rows(existing, candidates)
    assert added == 0
    assert len(merged) == 1
    assert merged[0]["검증상태"] == "확정"
    assert merged[0]["TMS_견적코드"] == "DLYG"


def test_merge_appends_only_new_keys():
    existing = [_row("기존굿즈", "AAAA", status="확정")]
    candidates = [_row("기존굿즈", "BBBB"), _row("신규굿즈", "CCCC")]
    merged, added = merge_rows(existing, candidates)
    assert added == 1
    assert {r["표준키"] for r in merged} == {"기존굿즈", "신규굿즈"}


def test_merge_is_idempotent():
    existing = [_row("가", "AAAA", status="확정")]
    cands = [_row("나", "BBBB")]
    once, _ = merge_rows(existing, cands)
    twice, added2 = merge_rows(once, cands)
    assert added2 == 0
    assert once == twice


def test_merge_sorts_deterministically():
    merged, _ = merge_rows([], [_row("나", "B"), _row("가", "A"),
                               _row("코드행", "C", ktype="코드")])
    assert [r["표준키"] for r in merged] == ["가", "나", "코드행"]


def _product_entry(rec_id, name, code):
    return {"rec_id": rec_id, "name": name, "code": code}


def test_find_ambiguous_names_flags_only_the_duplicate_name():
    # 동일 이름("데일리 짐색")이 서로 다른 rec_id·견적코드 2건에 걸림 → 모호.
    # "고유상품"은 rec_id 1건뿐 → 모호 아님.
    lookup = {
        "dlyg": _product_entry("rec1", "데일리 짐색", "DLYG"),
        "데일리 짐색": _product_entry("rec1", "데일리 짐색", "DLYG"),
        "dlyk": _product_entry("rec2", "데일리 짐색", "DLYK"),
        "uniq": _product_entry("rec3", "고유상품", "UNIQ"),
        "고유상품": _product_entry("rec3", "고유상품", "UNIQ"),
    }
    ambiguous = find_ambiguous_names(lookup)
    assert set(ambiguous.keys()) == {"데일리짐색"}
    assert ambiguous["데일리짐색"] == {"DLYG", "DLYK"}


def test_write_csv_preserves_unknown_columns(tmp_path):
    # 사람이 Excel에서 추가한 컬럼(예: 검토자)이 --write 재실행에도 지워지면 안 된다.
    path = str(tmp_path / "out.csv")
    rows = [
        {"표준키": "가", "키유형": "굿즈명", "TMS_견적코드": "A", "매칭방식": "정확",
         "매칭신뢰도": "1.00", "검증상태": "확정", "근거": "t", "검토자": "홍길동"},
    ]
    write_csv(path, rows)
    back = read_csv(path)
    assert back[0]["검토자"] == "홍길동"
    assert back[0]["표준키"] == "가"
