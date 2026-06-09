"""CBM 마스터 정규화·유도 테스트."""
from harness.backbone.cbm_master import cbm_from_box_dims, find_unmatched_goods


def test_cbm_from_box_dims_basic():
    # 480*380*270 mm = 0.04925 m³, 박스당 19개 → 개당 ≈ 0.002592
    assert abs(cbm_from_box_dims("480*380*270", 19) - 0.002592) < 1e-4


def test_cbm_from_box_dims_bad():
    assert cbm_from_box_dims("", 10) is None
    assert cbm_from_box_dims("480x380", 10) is None  # 3축 아님


def test_find_unmatched_goods():
    lookup = {"심볼아크릴트로피": {"rec_id": "r1", "name": "심볼아크릴트로피",
                                 "code": "SBAT", "box_type": "", "qty_per_box": 1,
                                 "cbm_per_box": 0.02}}
    goods = {"심볼아크릴트로피", "없는제품"}
    assert find_unmatched_goods(goods, lookup) == ["없는제품"]
