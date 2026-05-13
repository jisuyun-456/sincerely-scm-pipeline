"""Step 03 — Inventory Transfers and Adjustments (재고 이전 + 조정).

Per tick:
  - 10% chance: intra-plant 311 transfer WH01 → STG01 for a random material
  - 5% chance: inventory adjustment (movement 701) ±5% qty for a random material

Each triggered event queries the latest inventory snapshot to determine
available qty, then inserts into:
  sap.mat_document, sap.mat_document_item
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
MATERIALS = [
    "MAT-0001", "MAT-0002", "MAT-0003", "MAT-0004", "MAT-0005",
    "MAT-0006", "MAT-0007", "MAT-0008", "MAT-0009", "MAT-0010",
]
TRANSFER_PROB = 0.10
ADJUST_PROB   = 0.05
MIN_TRANSFER_QTY = 10.0


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


def _current_qty(material_id: str, sloc_id: str) -> float:
    """Return most-recent inventory snapshot qty for material+sloc."""
    rows = db.select(
        "inventory_snapshot",
        {"material_id": material_id, "plant_id": PLANT_ID, "sloc_id": sloc_id},
        columns="qty_on_hand, as_of_date",
        limit=1,
    )
    # snapshot rows may have multiple dates; take the latest
    if not rows:
        return 0.0
    rows_sorted = sorted(rows, key=lambda r: r.get("as_of_date", ""), reverse=True)
    return float(rows_sorted[0].get("qty_on_hand", 0))


def _post_mat_doc(
    doc_number: str,
    movement_type: str,
    source_doc_type: str,
    now_date: date,
    sim_run_id: str,
    dry_run: bool,
    items: list[dict],
) -> None:
    mat_doc_rows = db.insert("mat_document", {
        "doc_number": doc_number,
        "posting_date": now_date.isoformat(),
        "movement_type": movement_type,
        "is_reversal": False,
        "source_doc_type": source_doc_type,
        "source_doc_id": None,
        "sim_run_id": sim_run_id,
    }, dry_run=dry_run)

    mat_doc_id = mat_doc_rows[0].get("mat_doc_id") or mat_doc_rows[0].get("id")
    for item in items:
        item["mat_doc_id"] = mat_doc_id
    db.insert("mat_document_item", items, dry_run=dry_run)


def run(sim_run_id: str, ctx: SimContext) -> StepResult:
    dry_run = get_config().dry_run
    now_date = date.fromisoformat(ctx["now_date"])
    issues: list[str] = []
    docs_created = 0

    seed = hash(sim_run_id + ctx["now_date"] + "inventory") & 0x7FFFFFFF
    rng = random.Random(seed)

    try:
        # ── 311 Transfer WH01 → STG01 ──────────────────────────────────
        if rng.random() < TRANSFER_PROB:
            mat_id = rng.choice(MATERIALS)
            available = _current_qty(mat_id, "WH01")
            transfer_qty = round(available * rng.uniform(0.1, 0.3), 3)

            if transfer_qty < MIN_TRANSFER_QTY:
                issues.append(
                    f"311 transfer skipped for {mat_id}: available qty {available:.0f} too low"
                )
            else:
                doc_number = next_id("MAT", now_date, dry_run=dry_run)
                _post_mat_doc(
                    doc_number=doc_number,
                    movement_type="311",
                    source_doc_type="TRANSFER",
                    now_date=now_date,
                    sim_run_id=sim_run_id,
                    dry_run=dry_run,
                    items=[
                        {   # issue from WH01
                            "item_no": 1,
                            "material_id": mat_id,
                            "plant_id": PLANT_ID,
                            "sloc_id": "WH01",
                            "qty_signed": -transfer_qty,
                            "uom": "EA",
                            "value_local": 0.0,
                        },
                        {   # receipt into STG01
                            "item_no": 2,
                            "material_id": mat_id,
                            "plant_id": PLANT_ID,
                            "sloc_id": "STG01",
                            "qty_signed": transfer_qty,
                            "uom": "EA",
                            "value_local": 0.0,
                        },
                    ],
                )
                docs_created += 1
                logger.info("311 Transfer %s | %s | WH01→STG01 | qty %.3f",
                            doc_number, mat_id, transfer_qty)

        # ── 701 Inventory Adjustment ────────────────────────────────────
        if rng.random() < ADJUST_PROB:
            mat_id = rng.choice(MATERIALS)
            sloc_id = rng.choice(["WH01", "STG01"])
            current = _current_qty(mat_id, sloc_id)
            delta_pct = rng.uniform(-0.05, 0.05)
            adj_qty = round(current * delta_pct, 3)

            if adj_qty == 0.0:
                issues.append(f"701 adjustment skipped for {mat_id}: delta is zero")
            else:
                doc_number = next_id("MAT", now_date, dry_run=dry_run)
                _post_mat_doc(
                    doc_number=doc_number,
                    movement_type="701",
                    source_doc_type="ADJ",
                    now_date=now_date,
                    sim_run_id=sim_run_id,
                    dry_run=dry_run,
                    items=[{
                        "item_no": 1,
                        "material_id": mat_id,
                        "plant_id": PLANT_ID,
                        "sloc_id": sloc_id,
                        "qty_signed": adj_qty,
                        "uom": "EA",
                        "value_local": 0.0,
                    }],
                )
                docs_created += 1
                direction = "+" if adj_qty > 0 else ""
                logger.info("701 Adjustment %s | %s | %s | qty %s%.3f",
                            doc_number, mat_id, sloc_id, direction, adj_qty)

    except Exception as exc:
        issues.append(f"step_03_inventory failed: {exc}")
        logger.exception("step_03_inventory error")
        return StepResult("step_03_inventory", "failed", docs_created, issues)

    return StepResult("step_03_inventory", "ok", docs_created, issues)
