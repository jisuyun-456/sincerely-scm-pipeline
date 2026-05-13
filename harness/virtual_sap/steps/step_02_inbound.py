"""Step 02 — Goods Receipt + AQL Inspection (입하 + 검수).

For each open PO not yet processed in this sim_run_id:
  - Create GR document
  - Run AQL inspection (95% pass rate)
  - Post mat_document movement 101 (pass) or 551 (scrap fail)
  - Log qi_inspection record

Inserts into:
  sap.gr_document, sap.qi_inspection, sap.mat_document, sap.mat_document_item

PO table is immutable — we skip POs that already have a GR in this run.
"""
from __future__ import annotations

import random
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import TypedDict

from .. import supabase_client as db
from ..id_gen import next_id
from ..config import get_config

logger = logging.getLogger(__name__)

PLANT_ID = "P001"
AQL_PASS_RATE = 0.95


class SimContext(TypedDict):
    sim_run_id: str
    now_date: str
    dry_run: bool
    orders_count: int


@dataclass
class StepResult:
    step_name: str
    status: str
    docs_created: int
    issues: list[str] = field(default_factory=list)


def run(sim_run_id: str, ctx: SimContext) -> StepResult:
    dry_run = get_config().dry_run
    now_date = date.fromisoformat(ctx["now_date"])
    issues: list[str] = []
    docs_created = 0

    seed = hash(sim_run_id + ctx["now_date"] + "inbound") & 0x7FFFFFFF
    rng = random.Random(seed)

    try:
        # Find open POs
        open_pos = db.select("purchase_order", {"status": "open"})
        if not open_pos:
            logger.info("step_02_inbound: no open POs found, skipping")
            return StepResult("step_02_inbound", "skipped", 0, issues)

        # Find POs already processed in this sim_run_id (GR already exists)
        processed_gr = db.select("gr_document", {"sim_run_id": sim_run_id}, columns="po_id")
        already_processed = {row["po_id"] for row in processed_gr}

        for po in open_pos:
            po_id = po["po_id"]
            if po_id in already_processed:
                logger.debug("PO %s already has GR in this run, skipping", po_id)
                continue

            # Fetch PO items
            po_items = db.select("purchase_order_item", {"po_id": po_id})
            if not po_items:
                issues.append(f"PO {po_id} has no items")
                continue

            gr_id = next_id("GR", now_date, dry_run=dry_run)

            # Insert GR header
            db.insert("gr_document", {
                "gr_id": gr_id,
                "po_id": po_id,
                "posting_date": now_date.isoformat(),
                "vendor_id": po["vendor_id"],
                "plant_id": PLANT_ID,
                "sloc_id": "WH01",
                "total_items": len(po_items),
                "sim_run_id": sim_run_id,
            }, dry_run=dry_run)

            for po_item in po_items:
                mat_id = po_item["material_id"]
                ordered_qty = float(po_item["ordered_qty"])
                received_qty = ordered_qty  # assume full receipt

                # AQL inspection
                aql_sample = max(1, int(received_qty * 0.1))
                passed = rng.random() < AQL_PASS_RATE
                accepted_qty = received_qty if passed else 0.0
                rejected_qty = 0.0 if passed else received_qty
                disposition = "release" if passed else "scrap"

                db.insert("qi_inspection", {
                    "gr_id": gr_id,
                    "material_id": mat_id,
                    "inspected_qty": received_qty,
                    "aql_sample_size": aql_sample,
                    "aql_accepted_qty": accepted_qty,
                    "aql_rejected_qty": rejected_qty,
                    "disposition": disposition,
                    "inspector_note": f"sim_run={sim_run_id}",
                    "sim_run_id": sim_run_id,
                }, dry_run=dry_run)

                # Post material document
                movement_type = "101" if passed else "551"
                sloc_id = "WH01" if passed else "QC01"
                qty_signed = received_qty if passed else -rejected_qty
                std_price = float(po_item.get("net_price", 0))

                mat_doc_number = next_id("MAT", now_date, dry_run=dry_run)
                mat_doc_rows = db.insert("mat_document", {
                    "doc_number": mat_doc_number,
                    "posting_date": now_date.isoformat(),
                    "movement_type": movement_type,
                    "is_reversal": False,
                    "source_doc_type": "PO",
                    "source_doc_id": po_id,
                    "sim_run_id": sim_run_id,
                }, dry_run=dry_run)

                mat_doc_id = mat_doc_rows[0].get("mat_doc_id") or mat_doc_rows[0].get("id")
                db.insert("mat_document_item", {
                    "mat_doc_id": mat_doc_id,
                    "item_no": 1,
                    "material_id": mat_id,
                    "plant_id": PLANT_ID,
                    "sloc_id": sloc_id,
                    "qty_signed": qty_signed,
                    "uom": po_item.get("uom", "EA"),
                    "value_local": round(abs(qty_signed) * std_price, 2),
                }, dry_run=dry_run)

                docs_created += 1
                logger.info("GR %s | PO %s | mat %s | mvt %s | qty %.0f | aql=%s",
                            gr_id, po_id, mat_id, movement_type, abs(qty_signed), disposition)

    except Exception as exc:
        issues.append(f"step_02_inbound failed: {exc}")
        logger.exception("step_02_inbound error")
        return StepResult("step_02_inbound", "failed", docs_created, issues)

    return StepResult("step_02_inbound", "ok", docs_created, issues)
