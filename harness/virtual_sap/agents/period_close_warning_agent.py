"""Phase F — 기간마감 경고 에이전트.

Trigger: 매월 25일 이후, 당월 period_close 가 아직 'closed'가 아닌 경우 경고.
오늘 날짜 기준으로 동일 period에 이미 이벤트가 있으면 스킵(하루 1회).
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

AGENT_NAME = "기간마감경고"
WARNING_DAY = 25  # fire from this day of month onward


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
    today = datetime.now(timezone.utc)

    if today.day < WARNING_DAY:
        logger.info("%s: day %d < %d, skipping", AGENT_NAME, today.day, WARNING_DAY)
        return 0

    current_period = today.strftime("%Y%m")
    dedup_key = f"{current_period}_{today.strftime('%Y%m%d')}"

    # One warning per day per period
    prior = db.select("sim_agent_event", {"agent_name": AGENT_NAME, "target_id": dedup_key},
                      columns="id", limit=1)
    if prior:
        logger.info("%s: already warned today for period %s", AGENT_NAME, current_period)
        return 0

    # Check period_close status
    period_rows = db.select("period_close", {"period": current_period},
                            columns="period, status", limit=1)

    if period_rows and period_rows[0].get("status") == "closed":
        logger.info("%s: period %s already closed", AGENT_NAME, current_period)
        return 0

    # Count unclosed FI docs in current period
    fi_docs = db.select("fi_document",
                        {"period": current_period, "is_reversal": False},
                        columns="fi_doc_id")
    n_docs = len(fi_docs)

    status = period_rows[0].get("status", "open") if period_rows else "not_created"
    msg = (
        f"기간 {current_period} 마감 미완료 (status={status}) | "
        f"전표 {n_docs}건 | 오늘 마감하지 않으면 익월 이월 처리됩니다"
    )
    logger.warning("%s: %s", AGENT_NAME, msg)

    db.insert("sim_agent_event", {
        "agent_name": AGENT_NAME,
        "target_id": dedup_key,
        "status": "ok",
        "message": msg,
        "sim_run_id": None,
    }, dry_run=dry_run)

    _slack_notify(
        f"⚠️ *기간마감 경고* ({today.strftime('%Y-%m-%d')})\n"
        f"• 기간: {current_period} | 상태: {status}\n"
        f"• 전표 {n_docs}건 미마감\n"
        "• step_08 을 수동 실행하거나 금일 cron 완료를 확인하세요"
    )
    return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    count = run()
    print(f"{AGENT_NAME}: {count} warning(s) issued")
    sys.exit(0)
