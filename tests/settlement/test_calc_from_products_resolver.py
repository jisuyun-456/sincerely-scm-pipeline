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
