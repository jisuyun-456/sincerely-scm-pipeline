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
