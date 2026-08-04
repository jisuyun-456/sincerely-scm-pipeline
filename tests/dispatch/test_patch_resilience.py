"""#3 (2026-06-22) — PATCH 재시도/무크래시 + Slack ok 확인 + snapshot dry-run 안전.
"""
import urllib.error

from harness.dispatch import wave_recommender as wr
from harness.dispatch.wave_assigner import WAVE_IDS, Shipment, WavePlan


class _Resp:
    def __init__(self, body=b"{}"):
        self._b = body

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# ── PATCH 재시도 ──────────────────────────────────────────────────────────────

def test_patch_retries_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr(wr, "DRY_RUN", False)
    monkeypatch.setattr(wr.time, "sleep", lambda *_: None)
    monkeypatch.setattr(wr, "_airtable_headers", lambda: {"Authorization": "Bearer x"})
    calls = {"n": 0}

    def fake(req, timeout=30):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.HTTPError("u", 429, "rate", {}, None)
        return _Resp()

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert wr._patch("http://x", {"records": []}) is True
    assert calls["n"] == 3


def test_patch_422_no_retry_returns_false(monkeypatch):
    monkeypatch.setattr(wr, "DRY_RUN", False)
    monkeypatch.setattr(wr.time, "sleep", lambda *_: None)
    monkeypatch.setattr(wr, "_airtable_headers", lambda: {"Authorization": "Bearer x"})
    calls = {"n": 0}

    def fake(req, timeout=30):
        calls["n"] += 1
        raise urllib.error.HTTPError("u", 422, "bad", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    assert wr._patch("http://x", {"records": []}) is False
    assert calls["n"] == 1   # 422 는 재시도 안 함


def test_patch_airtable_survives_batch_failure(monkeypatch):
    monkeypatch.setattr(wr, "_patch_batch", lambda batch: False)  # 모든 배치 실패
    plans = {w: WavePlan(w) for w in WAVE_IDS}
    plans["W1"].shipments = [Shipment("r1", "P", "오전", "tier1_seoul", 1.0,
                                       slot_confidence=1.0, cbm_confidence=1.0)]
    diff = wr.patch_airtable(plans, {}, "now", {})
    assert len(diff) == 1   # 예외 없이 diff 반환


# ── Slack ok 확인 ─────────────────────────────────────────────────────────────

def test_slack_detects_not_ok(monkeypatch):
    monkeypatch.setattr(wr, "DRY_RUN", False)
    monkeypatch.setenv("SLACK_BOT_TOKEN", "x")
    monkeypatch.setenv("SLACK_DM_USER_ID", "u")
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=10: _Resp(b'{"ok":false,"error":"invalid_auth"}'))
    assert wr._slack_post("hi") is False


def test_slack_ok_true(monkeypatch):
    monkeypatch.setattr(wr, "DRY_RUN", False)
    monkeypatch.setenv("SLACK_BOT_TOKEN", "x")
    monkeypatch.setenv("SLACK_DM_USER_ID", "u")
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda req, timeout=10: _Resp(b'{"ok":true}'))
    assert wr._slack_post("hi") is True


# ── snapshot dry-run 안전 ─────────────────────────────────────────────────────

def test_save_snapshot_noop_in_dry_run(monkeypatch, tmp_path):
    p = tmp_path / "snap.json"
    monkeypatch.setattr(wr, "DRY_RUN", True)
    monkeypatch.setattr(wr, "SNAPSHOT_PATH", str(p))
    wr._save_snapshot({"a": 1})
    assert not p.exists()


def test_save_snapshot_writes_when_live(monkeypatch, tmp_path):
    p = tmp_path / "snap.json"
    monkeypatch.setattr(wr, "DRY_RUN", False)
    monkeypatch.setattr(wr, "SNAPSHOT_PATH", str(p))
    wr._save_snapshot({"a": 1})
    assert p.exists()
