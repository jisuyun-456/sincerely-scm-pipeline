"""Config validation tests."""
import pytest


def _reset(monkeypatch, **overrides):
    from harness.virtual_sap import config as cfg
    cfg.reset_config()
    defaults = {
        "VSAP_SUPABASE_URL": "https://fake.supabase.co",
        "VSAP_SUPABASE_SERVICE_KEY": "fake-key",
        "VSAP_DRY_RUN": "false",
        "VSAP_MODE": "manual",
        "VSAP_ORDERS_PER_TICK": "2",
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        monkeypatch.setenv(k, v)


def test_invalid_mode_raises(monkeypatch):
    _reset(monkeypatch, VSAP_MODE="invalid")
    from harness.virtual_sap.config import get_config
    with pytest.raises((ValueError, RuntimeError)):
        get_config()


def test_dry_run_false_by_default(monkeypatch):
    _reset(monkeypatch)
    monkeypatch.delenv("VSAP_DRY_RUN", raising=False)
    from harness.virtual_sap.config import get_config
    cfg = get_config()
    assert cfg.dry_run is False


def test_dry_run_true_from_env(monkeypatch):
    _reset(monkeypatch, VSAP_DRY_RUN="true")
    from harness.virtual_sap.config import get_config
    cfg = get_config()
    assert cfg.dry_run is True
