"""Phase F — 재고 부족 알림 에이전트.

Trigger: 최신 inventory_snapshot 에서 qty_on_hand < reorder_point 인 자재.
Target_id 는 '{material_id}_{as_of_date}' 로 하루 1회 중복 방지.
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

AGENT_NAME = "재고부족알림"


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
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Latest inventory snapshot (today)
    snapshots = db.select(
        "inventory_snapshot",
        {"as_of_date": today},
        columns="material_id, plant_id, sloc_id, qty_on_hand",
    )
    if not snapshots:
        logger.info("%s: no inventory snapshot for %s", AGENT_NAME, today)
        return 0

    # Material reorder points
    mat_ids = list({s["material_id"] for s in snapshots})
    materials = db.select("material", filters={"material_id": mat_ids},
                          columns="material_id, name, reorder_point")
    reorder_map = {m["material_id"]: m for m in materials}

    # Already alerted today
    prior = db.select("sim_agent_event", {"agent_name": AGENT_NAME}, columns="target_id")
    already_done = {r["target_id"] for r in prior if r.get("target_id")}

    processed = 0
    slack_lines: list[str] = []

    # Aggregate qty by material (sum across slocs)
    qty_by_mat: dict[str, float] = {}
    for snap in snapshots:
        mat_id = snap["material_id"]
        qty_by_mat[mat_id] = qty_by_mat.get(mat_id, 0.0) + float(snap.get("qty_on_hand") or 0)

    for mat_id, total_qty in qty_by_mat.items():
        mat = reorder_map.get(mat_id, {})
        reorder_pt = float(mat.get("reorder_point") or 0)
        if reorder_pt <= 0:
            continue
        if total_qty >= reorder_pt:
            continue

        dedup_key = f"{mat_id}_{today}"
        if dedup_key in already_done:
            continue

        mat_name = mat.get("name", mat_id)
        msg = (
            f"{mat_id} {mat_name} | 현재 {total_qty:.0f} / ROP {reorder_pt:.0f} | "
            f"긴급 발주 필요"
        )
        logger.warning("%s: %s", AGENT_NAME, msg)
        db.insert("sim_agent_event", {
            "agent_name": AGENT_NAME,
            "target_id": dedup_key,
            "status": "ok",
            "message": msg,
            "sim_run_id": None,
        }, dry_run=dry_run)
        slack_lines.append(f"🔴 {mat_id} {mat_name}: {total_qty:.0f}/{reorder_pt:.0f}")
        processed += 1

    if slack_lines:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        _slack_notify(
            f"🔴 *재고 부족 알림* ({ts})\n"
            + "\n".join(slack_lines)
            + f"\n총 {processed}건 — 구매 담당자 확인 필요"
        )

    logger.info("%s: %d low-stock alert(s)", AGENT_NAME, processed)
    return processed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    count = run()
    print(f"{AGENT_NAME}: {count} alert(s)")
    sys.exit(0)
