from __future__ import annotations
import pathlib

from harness._core._guard import assert_domain, assert_state_path

# Anchored to this file — never Path.cwd()
_HARNESS_ROOT = pathlib.Path(__file__).resolve().parents[1]  # harness/
_STATE_ROOT = _HARNESS_ROOT / "settlement" / "state"


def state_dir(domain: str) -> pathlib.Path:
    assert_domain(domain)
    path = _STATE_ROOT / domain
    path.mkdir(parents=True, exist_ok=True)
    assert_state_path(path)
    return path
