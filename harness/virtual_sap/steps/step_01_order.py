"""Step 01 — Create Sales Orders.

Generates ctx["orders_count"] sales orders with random customers,
materials, and quantities. Inserts into:
  sap.sales_order, sap.sales_order_item, sap.sales_order_status_event
"""
from __future__ import annotations

import random
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TypedDict

from .. import supabase_client as db
from ..id_gen import next_id
from ..config import get_config

logger = logging.getLogger(__name__)

CUSTOMERS = ["C-0001", "C-0002", "C-0003"]
MATERIALS = [
    "MAT-0001", "MAT-0002", "MAT-0003", "MAT-0004", "MAT-0005",
    "MAT-0006", "MAT-0007", "MAT-0008", "MAT-0009", "MAT-0010",
]
PRICES = {
    "MAT-0001": 4500,  "MAT-0002": 12000, "MAT-0003": 35000,
    "MAT-0004": 22000, "MAT-0005": 6500,  "MAT-0006": 18000,
    "MAT-0007": 55000, "MAT-0008": 15000, "MAT-0009": 2200,
    "MAT-0010": 9500,
}
PLANT_ID = "P001"


class SimContext(TypedDict):
    sim_run_id: str
    now_date: str   # YYYY-MM-DD
    dry_run: bool
    orders_count: int


@dataclass
class StepResult:
    step_name: str
    status: str           # "ok" | "failed" | "skipped"
    docs_created: int
    issues: list[str] = field(default_factory=list)


def run(sim_run_id: str, ctx: SimContext) -> StepResult:
    dry_run = get_config().dry_run
    now_date = date.fromisoformat(ctx["now_date"])
    orders_count = ctx.get("orders_count", 2)
    issues: list[str] = []
    docs_created = 0

    # Reproducible seed derived from sim_run_id hash + date
    seed = hash(sim_run_id + ctx["now_date"]) & 0x7FFFFFFF
    rng = random.Random(seed)

    try:
        for _ in range(orders_count):
            so_id = next_id("SO", now_date, dry_run=dry_run)
            customer_id = rng.choice(CUSTOMERS)
            n_items = rng.randint(1, 3)
            chosen_materials = rng.sample(MATERIALS, k=n_items)
            requested_delivery = now_date + timedelta(days=rng.randint(3, 14))

            # Build line items
            items = []
            total_value = 0.0
            for item_no, mat_id in enumerate(chosen_materials, start=1):
                qty = float(rng.randint(10, 200))
                price = float(PRICES[mat_id])
                total_value += qty * price
                items.append({
                    "so_id": so_id,
                    "item_no": item_no,
                    "material_id": mat_id,
                    "ordered_qty": qty,
                    "confirmed_qty": None,
                    "uom": "EA",
                    "net_price": price,
                })

            # Insert SO header
            db.insert("sales_order", {
                "so_id": so_id,
                "customer_id": customer_id,
                "order_date": now_date.isoformat(),
                "requested_delivery_date": requested_delivery.isoformat(),
                "plant_id": PLANT_ID,
                "status": "open",
                "total_value": round(total_value, 2),
                "sim_run_id": sim_run_id,
            }, dry_run=dry_run)

            # Insert SO items
            db.insert("sales_order_item", items, dry_run=dry_run)

            # Insert status event
            db.insert("sales_order_status_event", {
                "so_id": so_id,
                "from_status": None,
                "to_status": "open",
                "sim_run_id": sim_run_id,
            }, dry_run=dry_run)

            docs_created += 1
            logger.info("Created SO %s for customer %s (%d items, ₩%.0f)",
                        so_id, customer_id, n_items, total_value)

    except Exception as exc:
        issues.append(f"step_01_order failed: {exc}")
        logger.exception("step_01_order error")
        return StepResult("step_01_order", "failed", docs_created, issues)

    return StepResult("step_01_order", "ok", docs_created, issues)
