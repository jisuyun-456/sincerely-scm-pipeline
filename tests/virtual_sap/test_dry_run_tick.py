"""Dry-run tick tests — no Supabase connection required."""
import os
import pytest


@pytest.fixture(autouse=True)
def dry_run_env(monkeypatch):
    monkeypatch.setenv("VSAP_SUPABASE_URL", "https://fake.supabase.co")
    monkeypatch.setenv("VSAP_SUPABASE_SERVICE_KEY", "fake-key")
    monkeypatch.setenv("VSAP_DRY_RUN", "true")
    monkeypatch.setenv("VSAP_MODE", "manual")
    monkeypatch.setenv("VSAP_ORDERS_PER_TICK", "2")
    # Reset singletons between tests
    from harness.virtual_sap import supabase_client
    from harness.virtual_sap import config as cfg
    supabase_client.reset_client()
    cfg.reset_config()


def test_full_tick_dry_run():
    from harness.virtual_sap.engine import run_tick
    result = run_tick(mode="manual", orders_count=2)
    assert result["status"] == "ok"
    assert result["docs_created"] >= 1
    # issues may include info-level skipped-transfer messages; no ERROR-level failures expected
    error_issues = [i for i in result.get("issues", []) if "failed" in i.lower()]
    assert error_issues == [], f"Unexpected failures: {error_issues}"


def test_step_order_creates_docs():
    from harness.virtual_sap.steps.step_01_order import run as step_run
    import uuid
    ctx = {
        "sim_run_id": str(uuid.uuid4()),
        "now_date": "2026-05-13",
        "dry_run": True,
        "orders_count": 1,
    }
    result = step_run(ctx["sim_run_id"], ctx)
    assert result.status == "ok"
    assert result.docs_created == 1
