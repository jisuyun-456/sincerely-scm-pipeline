"""Step 04 — Production Goods Issue (생산출고).

For each open SO item whose material is in a production material_group
('가전류' or '주방용품'):
  - Post movement 261 (production consumption) from STG01
  - qty_signed = -ordered_qty (issue = negative)
  - Update SO item confirmed_qty = ordered_qty (non-ledger write, allowed)

Continuous mode: global idempotency (not per-run), time gate SO must be >2h old,
                 STOCK_SHORT (8%) and PROD_DELAY (5%) issue injection.

Inserts into:
  sap.mat_document, sap.mat_document_item
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
PRODUCTION_GROUPS = {"가전류", "주방용품"}
SOURCE_SLOC = "STG01"


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


def _get_material_group(material_id: str) -> str:
    """Return material_group for a material_id, or empty string if not found."""
    rows = db.select("material", {"material_id": material_id}, columns="material_group", limit=1)
    return rows[0].get("material_group", "") if rows else ""


def run(sim_run_id: str, ctx: SimContext) -> StepResult:
    dry_run = get_config().dry_run
    now_date = date.fromisoformat(ctx["now_date"])
    issues: list[str] = []
    docs_created = 0

    seed = hash(sim_run_id + ctx["now_date"]) & 0x7FFFFFFF
    rng = random.Random(seed)

    try:
        if ctx.get("is_continuous"):
            # Global idempotency: all 261 docs ever, not just this run
            existing_prod = db.select(
                "mat_document",
                {"movement_type": "261", "source_doc_type": "SO"},
                columns="source_doc_id",
            )
            already_issued_so_ids = {row["source_doc_id"] for row in existing_prod}

            # Time gate: SO must be > 2h old
            now_utc = datetime.fromisoformat(ctx["now_ts"])
            open_sos_raw = db.select(
                "sales_order", {"status": "open"}, columns="so_id, created_at"
            )
            so_ids = [
                row["so_id"]
                for row in open_sos_raw
                if row["so_id"] not in already_issued_so_ids
                and (
                    now_utc - datetime.fromisoformat(
                        row["created_at"].replace("Z", "+00:00")
                    )
                ) >= timedelta(hours=2)
            ]
        else:
            open_sos = db.select("sales_order", {"status": "open"}, columns="so_id")
            existing_prod = db.select(
                "mat_document",
                {"sim_run_id": sim_run_id, "movement_type": "261"},
                columns="source_doc_id",
            )
            already_issued_so_ids = {row["source_doc_id"] for row in existing_prod}
            so_ids = [
                row["so_id"] for row in open_sos
                if row["so_id"] not in already_issued_so_ids
            ]

        if not so_ids:
            logger.info("step_04_production: no eligible SOs, skipping")
            return StepResult("step_04_production", "skipped", 0, issues)

        for so_id in so_ids:
            # Issue injection before processing
            if maybe_inject(rng, IssueCode.STOCK_SHORT, rate=0.08):
                msg = f"STOCK_SHORT: SO {so_id} — insufficient inventory, production deferred"
                record_issue(db, sim_run_id, "WARN", msg, dry_run, dim="D3")
                issues.append(msg)
                continue

            if maybe_inject(rng, IssueCode.PROD_DELAY, rate=0.05):
                msg = f"PROD_DELAY: SO {so_id} — production line delay, retry next tick"
                record_issue(db, sim_run_id, "WARN", msg, dry_run, dim="D4")
                issues.append(msg)
                continue

            so_items = db.select("sales_order_item", {"so_id": so_id})
            if not so_items:
                continue

            # Filter to production materials only
            prod_items = [
                item for item in so_items
                if _get_material_group(item["material_id"]) in PRODUCTION_GROUPS
            ]
            if not prod_items:
                continue

            # One mat_document per SO (all production items grouped)
            doc_number = next_id("MAT", now_date, dry_run=dry_run)
            mat_doc_rows = db.insert("mat_document", {
                "doc_number": doc_number,
                "posting_date": now_date.isoformat(),
                "movement_type": "261",
                "is_reversal": False,
                "source_doc_type": "SO",
                "source_doc_id": so_id,
                "sim_run_id": sim_run_id,
            }, dry_run=dry_run)

            mat_doc_id = mat_doc_rows[0].get("mat_doc_id") or mat_doc_rows[0].get("id")

            mat_doc_items = []
            for item_no, item in enumerate(prod_items, start=1):
                ordered_qty = float(item["ordered_qty"])
                mat_doc_items.append({
                    "mat_doc_id": mat_doc_id,
                    "item_no": item_no,
                    "material_id": item["material_id"],
                    "plant_id": PLANT_ID,
                    "sloc_id": SOURCE_SLOC,
                    "qty_signed": -ordered_qty,   # issue = negative
                    "uom": item.get("uom", "EA"),
                    "value_local": 0.0,           # cost settled separately in FI step
                })

                # Update SO item confirmed_qty (non-ledger table: allowed)
                db.update(
                    "sales_order_item",
                    match={"so_id": so_id, "item_no": item["item_no"]},
                    updates={"confirmed_qty": ordered_qty},
                    dry_run=dry_run,
                )

            db.insert("mat_document_item", mat_doc_items, dry_run=dry_run)
            docs_created += 1
            logger.info("261 Production GI %s | SO %s | %d item(s)",
                        doc_number, so_id, len(prod_items))

    except Exception as exc:
        issues.append(f"step_04_production failed: {exc}")
        logger.exception("step_04_production error")
        return StepResult("step_04_production", "failed", docs_created, issues)

    return StepResult("step_04_production", "ok", docs_created, issues)
