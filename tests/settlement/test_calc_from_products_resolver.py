"""calc_from_products 공유 리졸버 통합 (D — 정산 CBM을 코드+alias로 통일).

핵심: 이름만으론 Jaccard<0.4로 못 잡는 aliased 굿즈를 name2code(이름→sync_item 코드→
V2 alias→Product)로 정확 해소 → 정산 상하차비 갭 보정. name2code 미전달 시 현행 동작 보존.
"""
from harness.settlement.cbm_calc import calc_from_products


def _lookup():
    e = {"name": "데스크 매트", "code": "DSKS", "box_type": "대형",
         "qty_per_box": 30, "cbm_per_box": 0.1066, "rec_id": "r1"}
    return {"dsks": e, "데스크 매트": e}


def test_name2code_resolves_aliased_good():
    # DSKT(WMS코드) → V2 alias → DSKS(등록). 이름만으론 미매칭이나 name2code로 정확 해소.
    out = calc_from_products("데스크테리어 매트×120", _lookup(),
                             name2code={"데스크테리어 매트": "DSKT"})
    assert out["matched"] and out["matched"][0]["matched_key"] == "DSKS"
    assert out["matched"][0]["method"] == "name2code"
    assert out["unload_fee"] == 5_000          # ceil(120/30)=4박스 대형 → 4//3=1 → 5,000


def test_without_name2code_preserves_current_jaccard_miss():
    # 동일 입력, name2code 없음 → Jaccard 0.33<0.4 → 미매칭 (현행 정산 동작 = 갭).
    out = calc_from_products("데스크테리어 매트×120", _lookup())
    assert out["matched"] == [] and out["unmatched"] == ["데스크테리어 매트"]


def _box_lookup():
    # 무공백 키를 명시적으로 넣는다 — 테스트는 lookup을 손으로 만들므로
    # load_product_lookup의 alias 자동생성이 일어나지 않는다.
    e = {"name": "프라임 폴더블 멀티충전기", "code": "PFMC", "box_type": "대형",
         "qty_per_box": 10, "cbm_per_box": 0.1066, "rec_id": "r2"}
    return {"프라임 폴더블 멀티충전기": e, "pfmc": e, "프라임폴더블멀티충전기": e}


def test_bonus_qty_notation_counts_total():
    # '50+1' = 본 50 + 여분 1 = 51 → ceil(51/10) = 6박스. v1 파서는 수량을 통째로 유실했다.
    out = calc_from_products("프라임폴더블멀티충전기 50+1", _box_lookup())
    assert out["matched"], "보너스 수량 표기가 매칭을 깨뜨리면 안 된다"
    m = out["matched"][0]
    assert m["qty"] == 51
    assert m["extra"] == 1
    assert m["n_boxes"] == 6


def test_bracket_index_stripped_from_name():
    # '[1]' 인덱스 표기가 붙어도 매칭돼야 한다 (v2가 이름에서 제거).
    out = calc_from_products("프라임폴더블멀티충전기[1] 20", _box_lookup())
    assert out["matched"]
    assert out["matched"][0]["qty"] == 20
    assert out["matched"][0]["n_boxes"] == 2


def test_qty_hint_still_applies_when_no_qty_parsed():
    # 수량이 전혀 없는 텍스트에서는 기존 qty_hint 폴백이 그대로 동작해야 한다.
    out = calc_from_products("프라임폴더블멀티충전기", _box_lookup(), qty_hint=30)
    assert out["matched"]
    assert out["matched"][0]["qty"] == 30
    assert out["matched"][0]["n_boxes"] == 3
