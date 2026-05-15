"""Step 05 — Outbound Delivery + Goods Issue (601).

For each open SO not yet delivered:
  - Create outbound_delivery + outbound_delivery_items
  - Simulate pick/pack completion
  - Post goods issue movement 601 from WH01
  - Update delivery goods_issue_status='posted'

Continuous mode: global idempotency (not per-run), time gate prod_doc must be >1h old,
                 PACK_DAMAGE (4%) issue injection reducing delivery qty 10%.

Inserts into: sap.outbound_delivery, sap.outbound_delivery_item,
              sap.mat_document, sap.mat_document_item
Updates (non-ledger): sap.outbound_delivery
"""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import TypedDict

from .. import supabase_client as db
from ..id_gen import next_id
from ..config import get_config
from .issue_injector import IssueCode, maybe_inject, record_issue

logger = logging.getLogger(__name__)

PLANT_ID = "P001"
SLOC_ID = "WH01"

MATERIAL_CBM = {
    "MAT-0001": 0.000134, "MAT-0002": 0.002462, "MAT-0003": 0.055402,
    "MAT-0004": 0.002736, "MAT-0005": 0.000985, "MAT-0006": 0.002962,
    "MAT-0007": 0.000985, "MAT-0008": 0.002897, "MAT-0009": 0.008000,
    "MAT-0010": 0.003200,
}


class SimContext(TypedDict):
    sim_run_id: str
    now_date: str
    now_ts: str
    is_continuous: bool
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

    seed = hash(sim_run_id + ctx["now_date"] + "step05") & 0x7FFFFFFF
    rng = random.Random(seed)

    try:
        if ctx.get("is_continuous"):
            # Global idempotency: all deliveries ever, not just this run
            existing_dlvs = db.select("outbound_delivery", {}, columns="so_id")
            already_delivered = {row["so_id"] for row in existing_dlvs}

            # Time gate: production mat_doc(261) must be > 1h old
            now_utc = datetime.fromisoformat(ctx["now_ts"])
            prod_docs = db.select(
                "mat_document",
                {"movement_type": "261", "source_doc_type": "SO"},
                columns="source_doc_id, created_at",
            )
            eligible_so_ids = {
                d["source_doc_id"]
                for d in prod_docs
                if d["source_doc_id"] not in already_delivered
                and (
                    now_utc - datetime.fromisoformat(
                        d["created_at"].replace("Z", "+00:00")
                    )
                ) >= timedelta(hours=1)
            }
            open_sos = [{"so_id": sid} for sid in eligible_so_ids]
        else:
            open_sos = db.select("sales_order", {"status": "open"}, columns="so_id")
            existing_dlvs = db.select(
                "outbound_delivery", {"sim_run_id": sim_run_id}, columns="so_id"
            )
            already_delivered = {row["so_id"] for row in existing_dlvs}
            open_sos = [r for r in open_sos if r["so_id"] not in already_delivered]

        if not open_sos:
            return StepResult("step_05_outbound", "skipped", 0, issues)

        for so_row in open_sos:
            so_id = so_row["so_id"]

            so_items = db.select("sales_order_item", {"so_id": so_id})
            if not so_items:
                issues.append(f"SO {so_id} has no items, skipping")
                continue

            dlv_id = next_id("DLV", now_date, dry_run=dry_run)

            total_cbm = 0.0
            dlv_items = []
            for item_no, item in enumerate(so_items, start=1):
                mat_id = item["material_id"]
                delivery_qty = float(item.get("confirmed_qty") or item["ordered_qty"])
                cbm = MATERIAL_CBM.get(mat_id, 0.0) * delivery_qty
                total_cbm += cbm
                dlv_items.append({
                    "dlv_id": dlv_id,
                    "item_no": item_no,
                    "material_id": mat_id,
                    "delivery_qty": delivery_qty,
                    "uom": item.get("uom", "EA"),
                })

            # Issue injection: PACK_DAMAGE reduces delivery qty 10%
            pack_damaged = False
            if maybe_inject(rng, IssueCode.PACK_DAMAGE, rate=0.04):
                for item in dlv_items:
                    item["delivery_qty"] = round(item["delivery_qty"] * 0.9, 3)
                total_cbm = round(total_cbm * 0.9, 6)
                pack_damaged = True
                msg = f"PACK_DAMAGE: DLV {dlv_id} — packing damage, 10% qty reduction"
                record_issue(db, sim_run_id, "WARN", msg, dry_run, dim="D5")
                issues.append(msg)

            db.insert("outbound_delivery", {
                "dlv_id": dlv_id,
                "so_id": so_id,
                "plant_id": PLANT_ID,
                "picking_status": "completed",
                "packing_status": "completed",
                "goods_issue_status": "pending",
                "total_cbm": round(total_cbm, 6),
                "sim_run_id": sim_run_id,
            }, dry_run=dry_run)

            db.insert("outbound_delivery_item", dlv_items, dry_run=dry_run)

            doc_number = next_id("MAT", now_date, dry_run=dry_run)
            mat_doc_rows = db.insert("mat_document", {
                "doc_number": doc_number,
                "posting_date": now_date.isoformat(),
                "movement_type": "601",
                "is_reversal": False,
                "source_doc_type": "DLV",
                "source_doc_id": dlv_id,
                "sim_run_id": sim_run_id,
            }, dry_run=dry_run)
            mat_doc_id = mat_doc_rows[0].get("mat_doc_id") or mat_doc_rows[0].get("id")

            mat_doc_items = []
            for item_no, item in enumerate(dlv_items, start=1):
                mat_doc_items.append({
                    "mat_doc_id": mat_doc_id,
                    "item_no": item_no,
                    "material_id": item["material_id"],
                    "plant_id": PLANT_ID,
                    "sloc_id": SLOC_ID,
                    "qty_signed": -item["delivery_qty"],
                    "uom": item["uom"],
                    "value_local": 0.0,
                })
            db.insert("mat_document_item", mat_doc_items, dry_run=dry_run)

            db.update(
                "outbound_delivery",
                match={"dlv_id": dlv_id},
                updates={
                    "goods_issue_status": "posted",
                    "goods_issue_mat_doc_id": mat_doc_id,
                    "goods_issue_date": now_date.isoformat(),
                },
                dry_run=dry_run,
            )

            docs_created += 1
            logger.info("601 GI %s | DLV %s | SO %s | CBM %.4f%s",
                        doc_number, dlv_id, so_id, total_cbm,
                        " [PACK_DAMAGE]" if pack_damaged else "")

    except Exception as exc:
        issues.append(f"step_05_outbound failed: {exc}")
        logger.exception("step_05_outbound error")
        return StepResult("step_05_outbound", "failed", docs_created, issues)

    return StepResult("step_05_outbound", "ok", docs_created, issues)
