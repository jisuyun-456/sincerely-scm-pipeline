"""SAP-style sequential document number generator.

Uses sap.doc_counter table with optimistic upsert to produce numbers like:
    SO-20260513-0001, GR-20260513-0042, FI-20260513-0007, etc.
"""
from __future__ import annotations

from datetime import date

from . import supabase_client as db


def _next_seq(prefix: str, for_date: date, dry_run: bool) -> int:
    """Atomically increment and return the next sequence for prefix+period."""
    period = for_date.strftime("%Y%m")

    if dry_run:
        # In dry-run, return a fake counter (doesn't touch DB)
        _dry_counters = getattr(_next_seq, "_dry_counters", {})
        key = (prefix, period)
        _dry_counters[key] = _dry_counters.get(key, 0) + 1
        _next_seq._dry_counters = _dry_counters  # type: ignore[attr-defined]
        return _dry_counters[key]

    # Upsert with increment using raw SQL via RPC
    result = db.rpc("vsap_next_seq", {"p_prefix": prefix, "p_period": period})
    return int(result)


def next_id(prefix: str, for_date: date | None = None, dry_run: bool = False) -> str:
    """Return the next document ID for the given prefix.

    Example: next_id("SO", date(2026, 5, 13)) → "SO-20260513-0001"
    """
    if for_date is None:
        for_date = date.today()
    seq = _next_seq(prefix, for_date, dry_run)
    date_str = for_date.strftime("%Y%m%d")
    return f"{prefix}-{date_str}-{seq:04d}"
