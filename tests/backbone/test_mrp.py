"""mrp.net_requirements 순수 함수 테스트 — PT별 부족분 = Σ(소요량×주문수량) − 현재고."""
from harness.backbone.mrp import net_requirements


def test_basic_shortfall():
    bom = [{"소품목_PT": "PT4900", "소요량_개당": 1.0},
           {"소품목_PT": "PT4906", "소요량_개당": 2.0}]
    out = net_requirements(bom, order_qty=100, stock_by_pt={"PT4900": 30, "PT4906": 500})
    by_pt = {r["pt"]: r for r in out}
    assert by_pt["PT4900"] == {"pt": "PT4900", "gross": 100, "stock": 30, "shortfall": 70}
    assert by_pt["PT4906"] == {"pt": "PT4906", "gross": 200, "stock": 500, "shortfall": 0}


def test_missing_stock_treated_as_zero():
    bom = [{"소품목_PT": "PT0001", "소요량_개당": 3.0}]
    out = net_requirements(bom, order_qty=10, stock_by_pt={})
    assert out == [{"pt": "PT0001", "gross": 30, "stock": 0, "shortfall": 30}]


def test_duplicate_pt_rows_aggregate_gross():
    bom = [{"소품목_PT": "PT0002", "소요량_개당": 1.0},
           {"소품목_PT": "PT0002", "소요량_개당": 0.5}]
    out = net_requirements(bom, order_qty=10, stock_by_pt={"PT0002": 5})
    assert out == [{"pt": "PT0002", "gross": 15, "stock": 5, "shortfall": 10}]


def test_none_or_zero_soyoryang_contributes_zero():
    bom = [{"소품목_PT": "PT0003", "소요량_개당": None},
           {"소품목_PT": "PT0003", "소요량_개당": 0}]
    out = net_requirements(bom, order_qty=10, stock_by_pt={})
    assert out == [{"pt": "PT0003", "gross": 0, "stock": 0, "shortfall": 0}]


def test_negative_stock_increases_shortfall():
    # 음수재고 = 즉시 보충 필요. 부족분 = gross − (−stock).
    bom = [{"소품목_PT": "PT0004", "소요량_개당": 1.0}]
    out = net_requirements(bom, order_qty=10, stock_by_pt={"PT0004": -5})
    assert out == [{"pt": "PT0004", "gross": 10, "stock": -5, "shortfall": 15}]


def test_blank_pt_rows_skipped():
    bom = [{"소품목_PT": "", "소요량_개당": 1.0},
           {"소품목_PT": None, "소요량_개당": 1.0},
           {"소품목_PT": "PT0005", "소요량_개당": 1.0}]
    out = net_requirements(bom, order_qty=10, stock_by_pt={})
    assert [r["pt"] for r in out] == ["PT0005"]


def test_output_sorted_by_pt():
    bom = [{"소품목_PT": "PT0009", "소요량_개당": 1.0},
           {"소품목_PT": "PT0001", "소요량_개당": 1.0}]
    out = net_requirements(bom, order_qty=1, stock_by_pt={})
    assert [r["pt"] for r in out] == ["PT0001", "PT0009"]


def test_fractional_gross_rounds_up():
    # 소요량 0.34 × 10 = 3.4 → 발주는 정수 단위, 올림 4
    bom = [{"소품목_PT": "PT0006", "소요량_개당": 0.34}]
    out = net_requirements(bom, order_qty=10, stock_by_pt={})
    assert out == [{"pt": "PT0006", "gross": 4, "stock": 0, "shortfall": 4}]
