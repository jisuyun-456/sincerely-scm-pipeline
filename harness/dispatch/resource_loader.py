"""배송파트너 테이블 SSOT loader.

기존 배송파트너 테이블(tblI4ZXrte7WyhXyd)에서 contract_type 기반으로
자체 기사(load_drivers) / 외주 파트너(load_partners)를 분리 반환.

Source: _AutoResearch/SCM/outputs/2026-05-27-driver-lane-consolidation-strategy.md §1
"""
from __future__ import annotations
import os
from typing import Any
import requests

BASE_ID = "app4x70a8mOrIKsMf"
TABLE_ID = "tblI4ZXrte7WyhXyd"

INTERNAL_CONTRACTS = {"계약직", "개인사업자"}
EXTERNAL_CONTRACTS = {"외주_3PL", "외주_carrier", "고객직접"}


def _fetch_records(table_id: str = TABLE_ID) -> list[dict[str, Any]]:
    """Airtable에서 배송파트너 record들을 모두 가져옴."""
    pat = os.environ.get("AIRTABLE_PAT")
    if not pat:
        raise RuntimeError("AIRTABLE_PAT 환경변수 필요")
    headers = {"Authorization": f"Bearer {pat}", "Content-Type": "application/json"}
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}"
    params: dict[str, Any] = {"pageSize": 100}
    out: list[dict[str, Any]] = []
    offset = None
    while True:
        if offset:
            params["offset"] = offset
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        out.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return out


def _contract_type(rec: dict[str, Any]) -> str:
    return rec.get("fields", {}).get("contract_type", "")


def _flat(rec: dict[str, Any]) -> dict[str, Any]:
    """record_id를 fields에 합쳐서 flat dict로 반환."""
    flat = dict(rec.get("fields", {}))
    flat["_record_id"] = rec.get("id")
    return flat


def load_drivers() -> list[dict[str, Any]]:
    """자체 기사 (contract_type ∈ {계약직, 개인사업자})만 반환."""
    records = _fetch_records()
    return [_flat(r) for r in records if _contract_type(r) in INTERNAL_CONTRACTS]


def load_partners() -> list[dict[str, Any]]:
    """외주 파트너 (contract_type ∈ {외주_3PL, 외주_carrier, 고객직접})만 반환."""
    records = _fetch_records()
    return [_flat(r) for r in records if _contract_type(r) in EXTERNAL_CONTRACTS]
