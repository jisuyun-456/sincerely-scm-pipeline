from __future__ import annotations

import os
from typing import Any

import requests

from harness._core.logger import StructuredLogger

_log = StructuredLogger("supabase_sink")


class SupabaseSink:
    """Fire-and-forget INSERT into public.ops_event via Supabase REST API.

    Never raises — harness jobs must never fail because of telemetry.
    """

    def __init__(self, url: str, key: str) -> None:
        self._endpoint = f"{url.rstrip('/')}/rest/v1/ops_event"
        self._headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }

    @classmethod
    def from_env(cls) -> "SupabaseSink | None":
        """Returns None silently if SUPABASE_URL/SUPABASE_SERVICE_KEY not set."""
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            return None
        return cls(url, key)

    def log_event(
        self,
        *,
        source: str,
        agent_id: str,
        domain: str = "",
        session_id: str = "",
        week: str = "",
        status: str,
        duration_ms: int | None = None,
        summary: str = "",
        meta: dict[str, Any] | None = None,
    ) -> None:
        row: dict[str, Any] = {
            "source": source,
            "agent_id": agent_id,
            "status": status,
        }
        if domain:
            row["domain"] = domain
        if session_id:
            row["session_id"] = session_id
        if week:
            row["week"] = week
        if duration_ms is not None:
            row["duration_ms"] = duration_ms
        if summary:
            row["summary"] = summary[:500]
        if meta:
            row["meta"] = meta

        try:
            resp = requests.post(
                self._endpoint,
                json=row,
                headers=self._headers,
                timeout=5,
            )
            if resp.status_code >= 400:
                _log.warning(
                    "ops_event insert failed",
                    status=resp.status_code,
                    body=resp.text[:200],
                )
        except Exception as exc:
            _log.warning("ops_event insert error", error=str(exc))
