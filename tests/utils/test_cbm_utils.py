"""cbm_utils — 입하 subset formula 빌더 테스트 (P3' T4)."""
from utils.cbm_utils import EXTERNAL_INBOUND_PURPOSES, build_inbound_formula


def test_default_purposes_is_approved_set():
    # CP② 승인 (2026-06-10): 생산산출·재고생산·고객물품
    assert EXTERNAL_INBOUND_PURPOSES == {"생산산출", "재고생산", "고객물품"}


def test_single_purpose():
    assert build_inbound_formula({"생산산출"}) == '{이동목적}="생산산출"'


def test_multi_purpose_or_sorted():
    f = build_inbound_formula({"생산산출", "고객물품"})
    assert f == 'OR({이동목적}="고객물품", {이동목적}="생산산출")'


def test_require_actual_date():
    f = build_inbound_formula({"생산산출"}, require_actual_date=True)
    assert f == 'AND({이동목적}="생산산출", {실제입하일}!="")'


def test_fetch_inbound_cbm_records_include_center(monkeypatch):
    # P4: 센터별 staging 점유율 입력 — records에 center 키 동반
    import utils.cbm_utils as cu

    fake = [{"fields": {
        cu.FLD_MOV_ITEM: "PT0001-박스 || PNA1_프로젝트 || 에이원지식산업센터",
        cu.FLD_MOV_IN_QTY: 2,
        cu.FLD_MOV_SPEC: "100*100*100",
        cu.FLD_MOV_EXP_DATE: "2026-06-12",
    }}]
    monkeypatch.setattr(cu, "get_all_records", lambda *a, **k: fake)
    out = cu.fetch_inbound_cbm({})
    assert out["records"][0]["center"] == "에이원지식산업센터"
