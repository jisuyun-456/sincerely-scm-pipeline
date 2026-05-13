"""Phase E — 고객출고알림 자동화 에이전트.

Trigger: outbound_delivery 중 goods_issue_status='posted'이고
         아직 sim_agent_event(고객출고알림)가 없는 건에 출고 안내 발송.
"""
from __future__ import annotations

import logging
import sys

if __name__ == "__main__" and __package__ is None:
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
    __package__ = "harness.virtual_sap.agents"

from .. import supabase_client as db
from ..config import get_config

logger = logging.getLogger(__name__)

AGENT_NAME = "고객출고알림"


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
            columns="bp_id, name",
            limit=1,
        )
        customer_name = bp_rows[0].get("name", customer_id) if bp_rows else customer_id

        message = (
            f"{customer_name} | SO {so_id} | 출고일 {goods_issue_date} "
            f"| 납기 {rdd} | 출고 안내 발송"
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
