"""Phase F — 클레임 접수 에이전트.

Trigger: shipment.pod_status='exception' 이고 아직 claim 이벤트가 없는 건.
Action:  sim_claim 테이블에 클레임 레코드 INSERT + Slack 알림.
"""
from __future__ import annotations

import logging
import os
import sys
import json
import urllib.request
from datetime import datetime, timezone

if __name__ == "__main__" and __package__ is None:
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
    __package__ = "harness.virtual_sap.agents"

from .. import supabase_client as db
from ..config import get_config

logger = logging.getLogger(__name__)

AGENT_NAME = "클레임접수"


def _slack_notify(text: str) -> None:
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    user = os.environ.get("SLACK_DM_USER_ID", "")
    if not token or not user:
        return
    body = json.dumps({"channel": user, "text": text}).encode()
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
        if not result.get("ok"):
            logger.warning("Slack error: %s", result.get("error"))
    except Exception as exc:
        logger.warning("Slack notify failed: %s", exc)


def run() -> int:
    cfg = get_config()
    dry_run = cfg.dry_run

    # Shipments with delivery exception
    exceptions = db.select(
        "shipment",
        {"pod_status": "exception"},
        columns="ship_id, carrier_id, actual_delivery",
    )
    if not exceptions:
        logger.info("%s: no exception shipments", AGENT_NAME)
        return 0

    prior = db.select("sim_agent_event", {"agent_name": AGENT_NAME}, columns="target_id")
    already_done = {r["target_id"] for r in prior if r.get("target_id")}

    pending = [s for s in exceptions if s["ship_id"] not in already_done]
    if not pending:
        logger.info("%s: all exceptions already claimed", AGENT_NAME)
        return 0

    processed = 0
    slack_lines: list[str] = []

    for ship in pending:
        ship_id = ship["ship_id"]
        carrier_id = ship.get("carrier_id", "—")

        # Insert claim record
        db.insert("sim_claim", {
            "ship_id": ship_id,
            "reason": "pod_exception",
            "status": "open",
        }, dry_run=dry_run)

        msg = f"SH {ship_id} | carrier {carrier_id} | pod_status=exception → 클레임 접수 완료"
        logger.warning("%s: %s", AGENT_NAME, msg)
        db.insert("sim_agent_event", {
            "agent_name": AGENT_NAME,
            "target_id": ship_id,
            "status": "ok",
            "message": msg,
            "sim_run_id": None,
        }, dry_run=dry_run)
        slack_lines.append(f"📋 SH {ship_id} | carrier {carrier_id} | 클레임 #open")
        processed += 1

    if slack_lines:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        _slack_notify(
            f"📋 *클레임 접수 에이전트* ({ts})\n"
            + "\n".join(slack_lines)
            + f"\n총 {processed}건 — CS팀 확인 필요"
        )

    logger.info("%s: %d claim(s) opened", AGENT_NAME, processed)
    return processed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    count = run()
    print(f"{AGENT_NAME}: {count} claim(s) opened")
    sys.exit(0)
