"""Phase B — 출고확인서 자동 생성 에이전트.

Trigger: GI 완료된 outbound_delivery 중 아직 sim_agent_event(출고확인서)가 없는 건 처리.
Logic:
  1. GI posted delivery with no prior agent event → generate confirmation record
  2. Fetch SO header + items for confirmation detail
  3. Insert sim_agent_event(agent_name='출고확인서', target_id=dlv_id, status='ok')
  4. Slack DM summary (optional)
"""
from __future__ import annotations

import logging
import os
import sys
import json
import urllib.request
from datetime import datetime, timezone

# Allow running as `python -m harness.virtual_sap.agents.delivery_confirm_agent`
if __name__ == "__main__" and __package__ is None:
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
    __package__ = "harness.virtual_sap.agents"

from .. import supabase_client as db
from ..config import get_config

logger = logging.getLogger(__name__)

AGENT_NAME = "출고확인서"


def _log_agent_event(target_id: str | None, status: str, message: str,
                     sim_run_id: str | None, dry_run: bool) -> None:
    db.insert("sim_agent_event", {
        "agent_name": AGENT_NAME,
        "target_id": target_id,
        "status": status,
        "message": message,
        "sim_run_id": sim_run_id,
    }, dry_run=dry_run)


def _build_confirmation_text(dlv: dict, so: dict, items: list[dict]) -> str:
    lines = [
        f"[출고확인서] DLV {dlv['dlv_id']} / SO {dlv['so_id']}",
        f"  고객: {so.get('customer_id', '—')} | Plant: {so.get('plant_id', '—')}",
        f"  GI일자: {dlv.get('goods_issue_date', '—')} | CBM: {dlv.get('total_cbm', 0):.4f} m³",
        "  품목:",
    ]
    for item in items:
        lines.append(
            f"    #{item['item_no']} {item['material_id']} "
            f"{item['delivery_qty']} {item.get('uom', 'EA')}"
        )
    return "\n".join(lines)


def _slack_notify(text: str) -> None:
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    user = os.environ.get("SLACK_DM_USER_ID", "")
    if not token or not user:
        return
    body = json.dumps({"channel": user, "text": text}).encode()
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
        if not result.get("ok"):
            logger.warning("Slack error: %s", result.get("error"))
    except Exception as exc:
        logger.warning("Slack notify failed: %s", exc)


def run() -> int:
    """Process unconfirmed deliveries. Returns count of confirmations generated."""
    cfg = get_config()
    dry_run = cfg.dry_run

    # GI-posted deliveries
    posted = db.select(
        "outbound_delivery",
        {"goods_issue_status": "posted"},
        columns="dlv_id, so_id, goods_issue_date, total_cbm",
    )
    if not posted:
        logger.info("%s: no GI-posted deliveries found", AGENT_NAME)
        return 0

    # Already-processed delivery IDs
    prior_events = db.select(
        "sim_agent_event",
        {"agent_name": AGENT_NAME},
        columns="target_id",
    )
    already_done = {row["target_id"] for row in prior_events if row.get("target_id")}

    pending = [d for d in posted if d["dlv_id"] not in already_done]
    if not pending:
        logger.info("%s: all %d GI deliveries already confirmed", AGENT_NAME, len(posted))
        return 0

    processed = 0
    slack_lines: list[str] = []

    for dlv in pending:
        dlv_id = dlv["dlv_id"]
        so_id = dlv["so_id"]

        so_rows = db.select("sales_order", {"so_id": so_id},
                            columns="so_id, customer_id, plant_id, total_value", limit=1)
        so = so_rows[0] if so_rows else {}

        items = db.select("outbound_delivery_item", {"dlv_id": dlv_id},
                          columns="item_no, material_id, delivery_qty, uom")

        confirmation_text = _build_confirmation_text(dlv, so, items)
        logger.info(confirmation_text)

        _log_agent_event(
            target_id=dlv_id,
            status="ok",
            message=f"DLV {dlv_id} (SO {so_id}) 출고확인서 생성 완료 — "
                    f"CBM {dlv.get('total_cbm', 0):.4f} m³, {len(items)}품목",
            sim_run_id=None,
            dry_run=dry_run,
        )
        slack_lines.append(f"✅ DLV {dlv_id} | SO {so_id} | {dlv.get('total_cbm', 0):.4f} m³")
        processed += 1

    if slack_lines:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        _slack_notify(
            f"📦 *출고확인서 에이전트* ({ts})\n"
            + "\n".join(slack_lines)
            + f"\n총 {processed}건 처리"
        )

    logger.info("%s: processed %d confirmation(s)", AGENT_NAME, processed)
    return processed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    count = run()
    print(f"{AGENT_NAME}: {count} confirmation(s) generated")
    sys.exit(0)
