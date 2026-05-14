"""Phase E — 고객출고알림 자동화 에이전트.

Trigger: outbound_delivery 중 goods_issue_status='posted'이고
         아직 sim_agent_event(고객출고알림)가 없는 건에 출고 안내 발송.
"""
from __future__ import annotations

import logging
import os
import sys

if __name__ == "__main__" and __package__ is None:
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
    __package__ = "harness.virtual_sap.agents"

from .. import supabase_client as db
from ..config import get_config

logger = logging.getLogger(__name__)

AGENT_NAME = "고객출고알림"


def _send_customer_email(to_email: str, customer_name: str, so_id: str, goods_issue_date: str) -> bool:
    import smtplib
    import ssl
    from email.mime.text import MIMEText

    sender = os.environ.get("GMAIL_SENDER")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not sender or not password or not to_email:
        return False
    body = (
        f"안녕하세요, {customer_name}님.\n\n"
        f"{so_id} 주문 건이 {goods_issue_date}에 출고 완료되었습니다.\n"
        "곧 배송될 예정이며 운송장 번호는 별도로 안내드리겠습니다.\n\n"
        "감사합니다.\n신시어리 물류팀 드림"
    )
    try:
        mime = MIMEText(body, "plain", "utf-8")
        mime["Subject"] = f"[신시어리] {so_id} 출고 완료 안내"
        mime["From"] = sender
        mime["To"] = to_email
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as smtp:
            smtp.login(sender, password)
            smtp.send_message(mime)
        logger.info("%s: email sent to %s for SO %s", AGENT_NAME, to_email, so_id)
        return True
    except Exception as exc:
        logger.warning("%s: email failed to %s: %s", AGENT_NAME, to_email, exc)
        return False


def _log_agent_event(target_id: str | None, status: str, message: str,
                     dry_run: bool) -> None:
    db.insert("sim_agent_event", {
        "agent_name": AGENT_NAME,
        "target_id": target_id,
        "status": status,
        "message": message,
        "sim_run_id": None,
    }, dry_run=dry_run)


def run() -> int:
    """Notify customers for GI-posted deliveries. Returns count of notifications sent."""
    cfg = get_config()
    dry_run = cfg.dry_run

    posted = db.select(
        "outbound_delivery",
        {"goods_issue_status": "posted"},
        columns="dlv_id, so_id, goods_issue_date",
    )
    if not posted:
        logger.info("%s: no GI-posted deliveries found", AGENT_NAME)
        return 0

    prior_events = db.select(
        "sim_agent_event",
        {"agent_name": AGENT_NAME},
        columns="target_id",
    )
    already_done = {row["target_id"] for row in prior_events if row.get("target_id")}

    to_process = [d for d in posted if d["dlv_id"] not in already_done]
    if not to_process:
        logger.info("%s: all %d deliveries already notified", AGENT_NAME, len(posted))
        return 0

    processed = 0
    for dlv in to_process:
        dlv_id = dlv["dlv_id"]
        so_id = dlv["so_id"]
        goods_issue_date = dlv.get("goods_issue_date", "—")

        so_rows = db.select(
            "sales_order",
            {"so_id": so_id},
            columns="so_id, customer_id, requested_delivery_date",
            limit=1,
        )
        so = so_rows[0] if so_rows else {}
        customer_id = so.get("customer_id", "")
        rdd = so.get("requested_delivery_date", "—")

        bp_rows = db.select(
            "business_partner",
            {"bp_id": customer_id},
            columns="bp_id, name, contact_email",
            limit=1,
        )
        bp = bp_rows[0] if bp_rows else {}
        customer_name = bp.get("name", customer_id)
        contact_email = bp.get("contact_email", "")

        email_sent = _send_customer_email(contact_email, customer_name, so_id, goods_issue_date)
        email_note = f"이메일 발송{'됨' if email_sent else ' 미설정'}"

        message = (
            f"{customer_name} | SO {so_id} | 출고일 {goods_issue_date} "
            f"| 납기 {rdd} | {email_note}"
        )
        logger.info("%s: %s", AGENT_NAME, message)
        _log_agent_event(target_id=dlv_id, status="ok", message=message, dry_run=dry_run)
        processed += 1

    logger.info("%s: processed %d notification(s)", AGENT_NAME, processed)
    return processed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    count = run()
    print(f"{AGENT_NAME}: {count} notification(s) sent")
    sys.exit(0)
