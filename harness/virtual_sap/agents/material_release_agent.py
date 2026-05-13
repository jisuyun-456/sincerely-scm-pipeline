"""Phase E — 자재출고요청 자동화 에이전트.

Trigger: sap.mat_document 중 movement_type='261'이고
         아직 sim_agent_event(자재출고요청)가 없는 건에 보관처 출고 요청 발송.
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

AGENT_NAME = "자재출고요청"


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
    """Send material release requests for movement_type=261 documents. Returns count processed."""
    cfg = get_config()
    dry_run = cfg.dry_run

    docs = db.select(
        "mat_document",
        {"movement_type": "261"},
        columns="mat_doc_id, source_doc_id, posting_date",
    )
    if not docs:
        logger.info("%s: no movement_type=261 documents found", AGENT_NAME)
        return 0

    prior_events = db.select(
        "sim_agent_event",
        {"agent_name": AGENT_NAME},
        columns="target_id",
    )
    already_done = {row["target_id"] for row in prior_events if row.get("target_id")}

    to_process = [d for d in docs if str(d["mat_doc_id"]) not in already_done]
    if not to_process:
        logger.info("%s: all %d documents already processed", AGENT_NAME, len(docs))
        return 0

    processed = 0
    for doc in to_process:
        mat_doc_id = str(doc["mat_doc_id"])
        source_doc_id = doc.get("source_doc_id", "—")

        items = db.select(
            "mat_document_item",
            {"mat_doc_id": doc["mat_doc_id"]},
            columns="material_id, qty_signed, uom",
        )
        top_items = items[:3]
        if top_items:
            parts = []
            for item in top_items:
                qty = abs(float(item.get("qty_signed", 0)))
                uom = item.get("uom", "EA")
                parts.append(f"{item['material_id']} {qty:.0f}{uom}")
            mat_summary = ", ".join(parts)
        else:
            mat_summary = "—"

        message = f"SO {source_doc_id} | {mat_summary} | 자재보관처 VN-0001 출고 요청 발송"
        logger.info("%s: %s", AGENT_NAME, message)
        _log_agent_event(target_id=mat_doc_id, status="ok", message=message, dry_run=dry_run)
        processed += 1

    logger.info("%s: processed %d document(s)", AGENT_NAME, processed)
    return processed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    count = run()
    print(f"{AGENT_NAME}: {count} release request(s) sent")
    sys.exit(0)
