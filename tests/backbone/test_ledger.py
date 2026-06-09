"""PropagationLedger 행 빌드 테스트 (순수)."""
from harness.backbone.ledger import build_propagation_row


def test_full_chain():
    bom = [{"소품목_PT": "PT4900", "소요량_개당": 1.0},
           {"소품목_PT": "PT4906", "소요량_개당": 1.0}]
    row = build_propagation_row(
        project_code="PNA50702", goods_name="심볼아크릴트로피",
        order_qty=125, bom_rows=bom, cbm_per_unit=0.02,
        shipment_id="SHIP1")
    assert row["고객주문수량"] == 125
    assert row["추정_CBM_m3"] == 2.5  # 125 * 0.02
    assert "PT4900×125" in row["자재소요_요약"]
    assert row["전파상태"] == "완결"
    assert row["shipment_id"] == "SHIP1"


def test_broken_chain_no_shipment():
    row = build_propagation_row("PNA1", "굿즈", 10, [], None, "")
    assert row["전파상태"] == "끊김"
