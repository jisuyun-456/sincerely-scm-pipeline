"""Slack DM notifier — sends failure alerts to a configured user."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def notify_failure(error_msg: str, sim_run_id: str) -> None:
    """Send a Slack DM on engine failure. No-ops if SLACK_BOT_TOKEN is not set."""
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    user_id = os.environ.get("SLACK_DM_USER_ID", "")

    if not token:
        logger.debug("SLACK_BOT_TOKEN not set — skipping failure notification")
        return

    if not user_id:
        logger.warning("SLACK_BOT_TOKEN set but SLACK_DM_USER_ID missing — cannot send DM")
        return

    try:
        import urllib.request
        import json

        text = f":red_circle: *Virtual SAP Engine Failure*\n`run_id`: {sim_run_id}\n```{error_msg[:500]}```"
        payload = json.dumps({"channel": user_id, "text": text}).encode()

        req = urllib.request.Request(
            "https://slack.com/api/chat.postMessage",
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
            if not body.get("ok"):
                logger.warning("Slack DM failed: %s", body.get("error", "unknown"))
            else:
                logger.info("Failure notification sent to Slack user %s", user_id)

    except Exception as exc:
        logger.warning("Failed to send Slack notification: %s", exc)
