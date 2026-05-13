from __future__ import annotations
import os
import pathlib

VALID_DOMAINS = {"tms_settlement", "tms_email", "tms_courier", "tms_sc_merge"}

_STATE_SUFFIX = pathlib.Path("settlement") / "state"


class LocalProdWriteForbidden(RuntimeError):
    pass


def assert_domain(domain: str) -> None:
    if domain not in VALID_DOMAINS:
        raise ValueError(
            f"Unknown domain {domain!r}. Valid: {sorted(VALID_DOMAINS)}"
        )


def assert_state_path(path: pathlib.Path) -> None:
    """Refuse writes that land outside the gitignored state/ tree.

    Also blocks any write when a prod PAT is detected outside CI — prevents
    accidental live writes from local dev environments.
    """
    harness_root = pathlib.Path(__file__).resolve().parents[1]  # harness/
    state_root = harness_root / _STATE_SUFFIX
    try:
        path.resolve().relative_to(state_root)
    except ValueError:
        raise ValueError(
            f"State writes must be inside {state_root}; got {path}"
        )
    if not os.environ.get("CI") and os.environ.get("AIRTABLE_PAT_PROD"):
        raise LocalProdWriteForbidden(
            "Prod PAT (AIRTABLE_PAT_PROD) detected outside CI. "
            "Use a test PAT for local runs."
        )
