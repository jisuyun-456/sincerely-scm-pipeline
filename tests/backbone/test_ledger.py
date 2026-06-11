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


# --- P6a 캐스케이드 per-track optional 인자 (spec §3.1) ---

def test_cascade_tracks_omitted_keeps_row_identical():
    """기존 호출 하위호환 — 신규 인자 미전달 시 행에 신규 키가 없어야 한다
    (P6b 필드 신설 전 INSERT가 unknown field로 실패하지 않도록)."""
    row = build_propagation_row("PNA1", "굿즈", 10, [], None, "")
    for key in ("부족자재_요약", "입하CBM_예상_m3", "MH_예상_h", "창고적재_예상",
                "wave_프리뷰", "운임_예상범위", "cascade_실행ID"):
        assert key not in row


def test_cascade_tracks_included_when_provided():
    bom = [{"소품목_PT": "PT4900", "소요량_개당": 1.0}]
    row = build_propagation_row(
        "PNA50702", "심볼아크릴트로피", 125, bom, 0.02, "SHIP1",
        shortage_summary="PT4900×70(재고 55/소요 125)",
        inbound_cbm_m3=1.4012, mh_hours=2.25,
        storage_projection="staging 83%→97% (입하일 기준)",
        wave_preview="W2 가능 (CBM 2.5/잔여 5.1)",
        fare_range="₩38,000~52,000 (CBM bracket)",
        cascade_run_id="20260611-1030")
    assert row["부족자재_요약"] == "PT4900×70(재고 55/소요 125)"
    assert row["입하CBM_예상_m3"] == 1.4012
    assert row["MH_예상_h"] == 2.25
    assert row["창고적재_예상"] == "staging 83%→97% (입하일 기준)"
    assert row["wave_프리뷰"] == "W2 가능 (CBM 2.5/잔여 5.1)"
    assert row["운임_예상범위"] == "₩38,000~52,000 (CBM bracket)"
    assert row["cascade_실행ID"] == "20260611-1030"
    # 기존 필드 계산은 불변
    assert row["전파상태"] == "완결"
    assert row["추정_CBM_m3"] == 2.5


def test_cascade_status_override():
    """캐스케이드는 트랙 결손 기준으로 상태를 직접 판정해 전달 (spec §3.1:
    완결=S1~S6 전 트랙 / 부분=≥1 트랙 결손 / 끊김=S1 실패)."""
    row = build_propagation_row(
        "PNA1", "굿즈", 10, [{"소품목_PT": "PT1", "소요량_개당": 1.0}], 0.01, "",
        status="부분", cascade_run_id="20260611-1030")
    assert row["전파상태"] == "부분"
