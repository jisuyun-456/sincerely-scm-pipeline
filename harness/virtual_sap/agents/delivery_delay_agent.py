"""Phase F — 납품 지연 알림 에이전트.

Trigger: pod_status='delivered' 이고 actual_delivery > requested_delivery_date 인
         shipment 중 아직 delivery_delay 이벤트가 없는 건.
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

AGENT_NAME = "납품지연알림"


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

    # All delivered shipments with an actual_delivery timestamp
    delivered = db.select(
        "shipment",
        {"pod_status": "delivered"},
        columns="ship_id, actual_delivery",
    )
    if not delivered:
        logger.info("%s: no delivered shipments", AGENT_NAME)
        return 0

    # Already-processed ship_ids
    prior = db.select("sim_agent_event", {"agent_name": AGENT_NAME}, columns="target_id")
    already_done = {r["target_id"] for r in prior if r.get("target_id")}

    pending_ships = [s for s in delivered if s["ship_id"] not in already_done and s.get("actual_delivery")]
    if not pending_ships:
        logger.info("%s: no new deliveries to check", AGENT_NAME)
        return 0

    # Resolve ship_id → dlv_id → so_id → requested_delivery_date
    ship_ids = [s["ship_id"] for s in pending_ships]
    links = db.select("shipment_delivery_link", filters={"ship_id": ship_ids}, columns="ship_id, dlv_id")
    ship_to_dlvs: dict[str, list[str]] = {}
    for lnk in links:
        ship_to_dlvs.setdefault(lnk["ship_id"], []).append(lnk["dlv_id"])

    dlv_ids = [d for dlvs in ship_to_dlvs.values() for d in dlvs]
    if not dlv_ids:
        logger.info("%s: no delivery links found", AGENT_NAME)
        return 0

    dlv_rows = db.select("outbound_delivery", filters={"dlv_id": dlv_ids}, columns="dlv_id, so_id")
    dlv_to_so = {r["dlv_id"]: r["so_id"] for r in dlv_rows}

    so_ids = list(set(dlv_to_so.values()))
    so_rows = db.select("sales_order", filters={"so_id": so_ids},
                        columns="so_id, customer_id, requested_delivery_date")
    so_map = {r["so_id"]: r for r in so_rows}

    processed = 0
    slack_lines: list[str] = []

    for ship in pending_ships:
        ship_id = ship["ship_id"]
        actual_delivery_str = ship["actual_delivery"]

        dlv_ids_for_ship = ship_to_dlvs.get(ship_id, [])
        if not dlv_ids_for_ship:
            continue

        # Use first linked delivery's SO
        dlv_id = dlv_ids_for_ship[0]
        so_id = dlv_to_so.get(dlv_id)
        if not so_id:
            continue

        so = so_map.get(so_id, {})
        rdd_str = so.get("requested_delivery_date")
        if not rdd_str:
            continue

        try:
            actual_dt = datetime.fromisoformat(actual_delivery_str.replace("Z", "+00:00"))
            rdd_dt = datetime.fromisoformat(rdd_str + "T23:59:59+00:00")
        except (ValueError, AttributeError):
            continue

        if actual_dt <= rdd_dt:
            continue

        delay_days = (actual_dt.date() - datetime.fromisoformat(rdd_str).date()).days

        msg = (
            f"SH {ship_id} | SO {so_id} | 고객 {so.get('customer_id', '?')} | "
            f"납기 {rdd_str} → 실착 {actual_dt.date()} | {delay_days}일 초과"
        )
        logger.info("%s: %s", AGENT_NAME, msg)
        db.insert("sim_agent_event", {
            "agent_name": AGENT_NAME,
            "target_id": ship_id,
            "status": "ok",
            "message": msg,
            "sim_run_id": None,
        }, dry_run=dry_run)
        slack_lines.append(f"📦 SH {ship_id} | {delay_days}일 지연 | {rdd_str} → {actual_dt.date()}")
        processed += 1

    if slack_lines:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        _slack_notify(
            f"⚠️ *납품 지연 알림* ({ts})\n"
            + "\n".join(slack_lines)
            + f"\n총 {processed}건"
        )

    logger.info("%s: %d delay(s) detected", AGENT_NAME, processed)
    return processed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    count = run()
    print(f"{AGENT_NAME}: {count} delay(s) detected")
    sys.exit(0)
