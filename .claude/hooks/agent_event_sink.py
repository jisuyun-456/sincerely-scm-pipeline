#!/usr/bin/env python3
"""PostToolUse hook — logs Agent tool calls to Supabase public.ops_event.

Reads Claude Code hook JSON payload from stdin.
Fires only when tool_name == "Agent". Silent no-op otherwise.
Uses urllib.request (stdlib) — no venv dependency.
"""
import json
import os
import sys
import urllib.request

DOMAIN_MAP: dict[str, str] = {
    "tms-otif-kpi":         "TMS",
    "tms-shipment":         "TMS",
    "tms-cost-lane":        "TMS",
    "tms-carrier":          "TMS",
    "tms-improvement":      "TMS",
    "wms-inbound":          "WMS",
    "wms-outbound":         "WMS",
    "wms-inventory":        "WMS",
    "wms-master-data":      "WMS",
    "wms-return":           "WMS",
    "meeting-analysis":     "OPS",
    "tax-accounting-expert":"FI",
    "scm-logistics-expert": "SCM",
    "consulting-pm-expert": "PM",
}


def main() -> None:
    raw = sys.stdin.read()
    if not raw.strip():
        return

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return

    if payload.get("tool_name") != "Agent":
        return

    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        return

    ti = payload.get("tool_input") or {}
    agent_id = ti.get("subagent_type") or "general-purpose"

    event = {
        "source":     "hook",
        "agent_id":   agent_id,
        "domain":     DOMAIN_MAP.get(agent_id, ""),
        "session_id": payload.get("session_id", ""),
        "status":     "completed",
        "summary":    (ti.get("description") or "")[:200],
        "meta":       {"model": ti.get("model", "")},
    }

    body = json.dumps(event).encode()
    req = urllib.request.Request(
        f"{url.rstrip('/')}/rest/v1/ops_event",
        data=body,
        headers={
            "apikey":        key,
            "Authorization": f"Bearer {key}",
            "Content-Type":  "application/json",
            "Prefer":        "return=minimal",
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # Never fail the main process


if __name__ == "__main__":
    main()
