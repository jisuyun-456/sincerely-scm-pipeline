"""Phase F — AQL 불합격 → 재발주 에이전트.

Trigger: qi_inspection.disposition='block' 이고 아직 quality_reject 이벤트가 없는 건.
Action:  so_reorder_queue 에 INSERT → step_01 이 다음 tick에 SO 재생성.
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

AGENT_NAME = "품질불합격재발주"


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

    # All blocked QI inspections
    blocked = db.select(
        "qi_inspection",
        {"disposition": "block"},
        columns="qi_id, gr_id, material_id, aql_rejected_qty",
    )
    if not blocked:
        logger.info("%s: no blocked QI inspections", AGENT_NAME)
        return 0

    # Already-processed qi_ids
    prior = db.select("sim_agent_event", {"agent_name": AGENT_NAME}, columns="target_id")
    already_done = {r["target_id"] for r in prior if r.get("target_id")}

    pending = [qi for qi in blocked if qi["qi_id"] not in already_done]
    if not pending:
        logger.info("%s: all blocked QI already processed", AGENT_NAME)
        return 0

    # Resolve gr_id → plant_id
    gr_ids = list({qi["gr_id"] for qi in pending})
    gr_rows = db.select("gr_document", filters={"gr_id": gr_ids}, columns="gr_id, plant_id")
    gr_to_plant = {r["gr_id"]: r["plant_id"] for r in gr_rows}

    processed = 0
    slack_lines: list[str] = []

    for qi in pending:
        qi_id = str(qi["qi_id"])
        gr_id = qi["gr_id"]
        material_id = qi["material_id"]
        rejected_qty = float(qi.get("aql_rejected_qty") or 0)
        plant_id = gr_to_plant.get(gr_id, "P001")
        reorder_qty = max(rejected_qty, 1.0)

        # Queue the reorder
        db.insert("so_reorder_queue", {
            "qi_id": qi_id,
            "material_id": material_id,
            "plant_id": plant_id,
            "qty": reorder_qty,
            "reason": "aql_rejected",
            "status": "pending",
        }, dry_run=dry_run)

        msg = (
            f"QI {qi_id[:8]}... | {material_id} | GR {gr_id} | "
            f"불량수량 {rejected_qty:.0f} → 재발주큐 등록 (plant={plant_id})"
        )
        logger.warning("%s: %s", AGENT_NAME, msg)
        db.insert("sim_agent_event", {
            "agent_name": AGENT_NAME,
            "target_id": qi_id,
            "status": "ok",
            "message": msg,
            "sim_run_id": None,
        }, dry_run=dry_run)
        slack_lines.append(f"🚨 {material_id} | 불량 {rejected_qty:.0f}개 → 재발주 예약")
        processed += 1

    if slack_lines:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        _slack_notify(
            f"🚨 *AQL 불합격 재발주 에이전트* ({ts})\n"
            + "\n".join(slack_lines)
            + f"\n총 {processed}건 — 다음 tick에 SO 자동 생성 예정"
        )

    logger.info("%s: %d reorder(s) queued", AGENT_NAME, processed)
    return processed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    count = run()
    print(f"{AGENT_NAME}: {count} reorder(s) queued")
    sys.exit(0)
