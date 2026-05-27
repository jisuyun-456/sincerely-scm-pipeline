"""Roster 정정 회귀 테스트 — CA-0004 김민준 제거, 조희선 추가, 이장훈 CBM 4.5."""
from __future__ import annotations
import sys
import types
import pytest

# Stub out supabase so dispatch_advisor can be imported without the package
_supabase_stub = types.ModuleType("supabase")
_supabase_stub.create_client = lambda url, key: None
_supabase_stub.Client = object
sys.modules.setdefault("supabase", _supabase_stub)

from harness.virtual_sap.agents.dispatch_advisor import INHOUSE_DRIVERS  # noqa: E402


def test_inhouse_drivers_count():
    assert len(INHOUSE_DRIVERS) == 3


def test_johee_sun_present():
    names = {d[1] for d in INHOUSE_DRIVERS}
    assert "조희선" in names


def test_kim_min_jun_removed():
    ids = {d[0] for d in INHOUSE_DRIVERS}
    names = {d[1] for d in INHOUSE_DRIVERS}
    assert "CA-0004" not in ids
    assert "김민준" not in names


def test_lee_jang_hoon_cbm_updated():
    """이장훈 max_cbm 7.6 → 4.5 (스타리아 화물칸 추정)."""
    lee = next((d for d in INHOUSE_DRIVERS if d[1] == "이장훈"), None)
    assert lee is not None
    assert lee[2] == 4.5, f"Expected 4.5, got {lee[2]}"


def test_park_jong_sung_preserved():
    names = {d[1] for d in INHOUSE_DRIVERS}
    assert "박종성" in names
