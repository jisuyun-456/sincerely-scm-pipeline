"""Phase E — 운송장기입 자동화 에이전트.

Trigger: sap.shipment 중 pod_status='pending' 또는 'in_transit'이고
         아직 sim_agent_event(운송장기입)가 없는 건에 추적번호 자동 생성.
"""
from __future__ import annotations

import logging
import random
import sys

if __name__ == "__main__" and __package__ is None:
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
    __package__ = "harness.virtual_sap.agents"

from .. import supabase_client as db
from ..config import get_config

logger = logging.getLogger(__name__)

AGENT_NAME = "운송장기입"


def _generate_tracking_no(carrier_id: str) -> str:
    if carrier_id.startswith("CA-0001"):
        return "CJ" + str(random.randint(0, 9_999_999_999)).zfill(10)
    if carrier_id.startswith("CA-0005"):
        return "QK" + str(random.randint(0, 9_999_999)).zfill(7)
    return "LP" + str(random.randint(0, 99_999_999)).zfill(8)


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
    """Assign tracking numbers to pending/in_transit shipments. Returns count processed."""
    cfg = get_config()
    dry_run = cfg.dry_run

    all_ships = db.select(
        "shipment",
        None,
        columns="ship_id, carrier_id, driver_name, pod_status",
    )
    pending = [s for s in all_ships if s.get("pod_status") in ("pending", "in_transit")]
    if not pending:
        logger.info("%s: no pending/in_transit shipments found", AGENT_NAME)
        return 0

    prior_events = db.select(
        "sim_agent_event",
        {"agent_name": AGENT_NAME},
        columns="target_id",
    )
    already_done = {row["target_id"] for row in prior_events if row.get("target_id")}

    to_process = [s for s in pending if s["ship_id"] not in already_done]
    if not to_process:
        logger.info("%s: all %d shipments already processed", AGENT_NAME, len(pending))
        return 0

    processed = 0
    for ship in to_process:
        ship_id = ship["ship_id"]
        carrier_id = ship.get("carrier_id", "")
        tracking_no = _generate_tracking_no(carrier_id)
        message = f"{ship_id} | {tracking_no} | {carrier_id} 운송장 자동기입"
        logger.info("%s: %s", AGENT_NAME, message)
        _log_agent_event(target_id=ship_id, status="ok", message=message, dry_run=dry_run)
        processed += 1

    logger.info("%s: processed %d shipment(s)", AGENT_NAME, processed)
    return processed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    count = run()
    print(f"{AGENT_NAME}: {count} tracking number(s) assigned")
    sys.exit(0)
