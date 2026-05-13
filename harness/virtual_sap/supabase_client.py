"""Supabase client wrapper — INSERT-only, dry-run gate, retry."""
from __future__ import annotations

import time
import logging
from typing import Any

from supabase import create_client, Client

from .config import get_config

logger = logging.getLogger(__name__)

_client: Client | None = None


def get_client() -> Client:
    """Return singleton Supabase client (service_role key)."""
    global _client
    if _client is None:
        cfg = get_config()
        _client = create_client(cfg.supabase_url, cfg.supabase_service_key)
    return _client


def reset_client() -> None:
    global _client
    _client = None


def _retry(fn, max_attempts: int = 3, delay: float = 1.0):
    """Simple retry with exponential backoff on 5xx."""
    last_exc = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            msg = str(exc).lower()
            # Don't retry on constraint violations or auth errors
            if any(k in msg for k in ("constraint", "violation", "policy", "rls", "401", "403", "duplicate")):
                raise
            if attempt < max_attempts - 1:
                wait = delay * (2 ** attempt)
                logger.warning("Supabase call failed (attempt %d/%d), retrying in %.1fs: %s",
                               attempt + 1, max_attempts, wait, exc)
                time.sleep(wait)
    raise last_exc  # type: ignore[misc]


def select(table: str, filters: dict[str, Any] | None = None,
           columns: str = "*", limit: int | None = None,
           dry_run: bool | None = None) -> list[dict]:
    """SELECT rows from a sap.* table. Returns [] in dry_run mode."""
    if dry_run is None:
        dry_run = get_config().dry_run
    if dry_run:
        logger.debug("[DRY-RUN] Would SELECT from sap.%s (returning [])", table)
        return []
    client = get_client()

    def _do():
        q = client.schema("sap").table(table).select(columns)
        if filters:
            for col, val in filters.items():
                if isinstance(val, list):
                    q = q.in_(col, val)
                else:
                    q = q.eq(col, val)
        if limit is not None:
            q = q.limit(limit)
        resp = q.execute()
        return resp.data or []

    return _retry(_do)


def insert(table: str, rows: list[dict] | dict, dry_run: bool | None = None) -> list[dict]:
    """INSERT rows into a sap.* table. No-ops in dry_run mode."""
    if dry_run is None:
        dry_run = get_config().dry_run

    if not isinstance(rows, list):
        rows = [rows]

    if dry_run:
        logger.info("[DRY-RUN] Would INSERT %d row(s) into sap.%s", len(rows), table)
        # Return fake rows with generated IDs for downstream logic
        import uuid
        return [{**r, "id": str(uuid.uuid4())} if "id" not in r else r for r in rows]

    client = get_client()

    def _do():
        resp = client.schema("sap").table(table).insert(rows).execute()
        return resp.data or []

    result = _retry(_do)
    logger.debug("Inserted %d row(s) into sap.%s", len(result), table)
    return result


def update(table: str, match: dict[str, Any], updates: dict[str, Any],
           dry_run: bool | None = None) -> list[dict]:
    """UPDATE rows — allowed only for non-ledger tables (status fields, snapshots)."""
    if dry_run is None:
        dry_run = get_config().dry_run

    LEDGER_TABLES = {
        "mat_document", "mat_document_item",
        "fi_document", "fi_document_line",
        "gr_document",
    }
    if table in LEDGER_TABLES:
        raise RuntimeError(
            f"UPDATE forbidden on ledger table sap.{table}. "
            "Post a reversal/correction record instead (Immutable Ledger rule)."
        )

    if dry_run:
        logger.info("[DRY-RUN] Would UPDATE sap.%s where %s set %s", table, match, updates)
        return []

    client = get_client()

    def _do():
        q = client.schema("sap").table(table).update(updates)
        for col, val in match.items():
            q = q.eq(col, val)
        resp = q.execute()
        return resp.data or []

    return _retry(_do)


def rpc(name: str, params: dict | None = None) -> Any:
    """Call a Postgres stored procedure/function."""
    client = get_client()

    def _do():
        resp = client.rpc(name, params or {}).execute()
        return resp.data

    return _retry(_do)
