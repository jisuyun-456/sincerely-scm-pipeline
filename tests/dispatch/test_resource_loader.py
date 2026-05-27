"""Tests for harness.dispatch.resource_loader."""
from __future__ import annotations
from unittest.mock import patch
from harness.dispatch.resource_loader import load_drivers, load_partners


@patch("harness.dispatch.resource_loader._fetch_records")
def test_load_drivers_returns_internal_only(mock_fetch):
    """load_drivers는 contract_type ∈ {계약직, 개인사업자}만 반환."""
    mock_fetch.return_value = [
        {"id": "rec1", "fields": {"배송파트너": "신시어리 (이장훈)", "contract_type": "계약직", "배송파트너_CBM": 4.5}},
        {"id": "rec2", "fields": {"배송파트너": "신시어리 (조희선)", "contract_type": "계약직", "배송파트너_CBM": 7.616}},
        {"id": "rec3", "fields": {"배송파트너": "신시어리 (박종성)", "contract_type": "개인사업자", "배송파트너_CBM": 9.486}},
        {"id": "rec4", "fields": {"배송파트너": "로젠택배 위탁", "contract_type": "외주_carrier"}},
        {"id": "rec5", "fields": {"배송파트너": "다영기획", "contract_type": "외주_3PL"}},
    ]
    drivers = load_drivers()
    assert len(drivers) == 3
    names = {d["배송파트너"] for d in drivers}
    assert "신시어리 (이장훈)" in names
    assert "신시어리 (조희선)" in names
    assert "신시어리 (박종성)" in names


@patch("harness.dispatch.resource_loader._fetch_records")
def test_load_drivers_skips_outsourced(mock_fetch):
    """외주는 driver가 아님."""
    mock_fetch.return_value = [
        {"id": "rec1", "fields": {"배송파트너": "로젠", "contract_type": "외주_carrier"}},
        {"id": "rec2", "fields": {"배송파트너": "다영기획", "contract_type": "외주_3PL"}},
    ]
    drivers = load_drivers()
    assert len(drivers) == 0


@patch("harness.dispatch.resource_loader._fetch_records")
def test_load_partners_returns_external_only(mock_fetch):
    """load_partners는 contract_type ∈ {외주_3PL, 외주_carrier, 고객직접}만 반환."""
    mock_fetch.return_value = [
        {"id": "rec1", "fields": {"배송파트너": "이장훈", "contract_type": "계약직"}},
        {"id": "rec2", "fields": {"배송파트너": "다영기획", "contract_type": "외주_3PL", "autonomy_level": "partial"}},
        {"id": "rec3", "fields": {"배송파트너": "로젠", "contract_type": "외주_carrier", "autonomy_level": "autonomous"}},
        {"id": "rec4", "fields": {"배송파트너": "고객", "contract_type": "고객직접"}},
    ]
    partners = load_partners()
    assert len(partners) == 3
    types = {p["contract_type"] for p in partners}
    assert types == {"외주_3PL", "외주_carrier", "고객직접"}


@patch("harness.dispatch.resource_loader._fetch_records")
def test_load_partners_extracts_autonomy(mock_fetch):
    """autonomy_level이 partner dict에 포함된다."""
    mock_fetch.return_value = [
        {"id": "rec1", "fields": {"배송파트너": "로젠", "contract_type": "외주_carrier", "autonomy_level": "autonomous"}},
    ]
    partners = load_partners()
    assert len(partners) == 1
    assert partners[0]["autonomy_level"] == "autonomous"
