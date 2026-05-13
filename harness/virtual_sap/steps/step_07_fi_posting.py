"""Step 07 — FI Journal Entry posting.

For each mat_document in this sim_run_id without a fi_document:
  - 101 GR:      Dr Inventory(1410) / Cr GR-IR(2110)
  - 551 Scrap:   Dr Scrap Expense(5510) / Cr Inventory(1410)
  - 261 Prod GI: Dr COGS(5110) / Cr Inventory(1410)
  - 601 Cust GI: TWO entries —
      a) Dr COGS(5110) / Cr Inventory(1410)  [at cost]
      b) Dr AR(1110)   / Cr Revenue(4110)    [at net_price]
  - 701 Adj:     Dr/Cr InvAdj(5610) / Cr/Dr Inventory(1410)  [sign-driven]
  - 311 Transfer: no FI posting

Inserts into: sap.fi_document, sap.fi_document_line
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import TypedDict

from .. import supabase_client as db
from ..id_gen import next_id
from ..config import get_config, GL_MAP

logger = logging.getLogger(__name__)

MATERIAL_PRICES = {
    "MAT-0001": 4500,  "MAT-0002": 12000, "MAT-0003": 35000, "MAT-0004": 22000,
    "MAT-0005": 6500,  "MAT-0006": 18000, "MAT-0007": 55000, "MAT-0008": 15000,
    "MAT-0009": 2200,  "MAT-0010": 9500,
}


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


def _get_net_price_for_601(dlv_id: str) -> dict[str, float]:
    """Return {material_id: net_price} from the SO behind the delivery."""
    dlv_rows = db.select("outbound_delivery", {"dlv_id": dlv_id}, columns="so_id", limit=1)
    if not dlv_rows:
        return {}
    so_id = dlv_rows[0]["so_id"]
    items = db.select("sales_order_item", {"so_id": so_id}, columns="material_id,net_price")
    return {row["material_id"]: float(row["net_price"]) for row in items}


def _make_line(fi_doc_id: str, line_no: int, gl: str, debit: float, credit: float) -> dict:
    return {
        "fi_doc_id": fi_doc_id,
        "line_no": line_no,
        "gl_account": gl,
        "debit_amount": round(debit, 2),
        "credit_amount": round(credit, 2),
    }


def run(sim_run_id: str, ctx: SimContext) -> StepResult:
    dry_run = get_config().dry_run
    now_date = date.fromisoformat(ctx["now_date"])
    period = now_date.strftime("%Y%m")
    issues: list[str] = []
    docs_created = 0

    try:
        mat_docs = db.select(
            "mat_document",
            {"sim_run_id": sim_run_id},
            columns="mat_doc_id,movement_type,source_doc_type,source_doc_id",
        )
        if not mat_docs:
            return StepResult("step_07_fi_posting", "skipped", 0, issues)

        existing_fi = db.select(
            "fi_document", {"sim_run_id": sim_run_id}, columns="source_mat_doc_id"
        )
        already_posted = {row["source_mat_doc_id"] for row in existing_fi}

        for mat_doc in mat_docs:
            mat_doc_id = mat_doc["mat_doc_id"]
            mvt = mat_doc["movement_type"]

            if mat_doc_id in already_posted or mvt == "311":
                continue

            items = db.select("mat_document_item", {"mat_doc_id": mat_doc_id})
            if not items:
                issues.append(f"mat_doc {mat_doc_id} has no items, skipping FI")
                continue

            doc_type = "WE" if mvt == "101" else ("ADJ" if mvt == "701" else "GI")
            fi_id = next_id("FI", now_date, dry_run=dry_run)

            db.insert("fi_document", {
                "fi_doc_id": fi_id,
                "doc_type": doc_type,
                "posting_date": now_date.isoformat(),
                "period": period,
                "source_mat_doc_id": mat_doc_id,
                "sim_run_id": sim_run_id,
            }, dry_run=dry_run)

            net_prices: dict[str, float] = {}
            if mvt == "601":
                net_prices = _get_net_price_for_601(mat_doc["source_doc_id"])

            lines: list[dict] = []
            line_no = 1

            for item in items:
                mat_id = item["material_id"]
                qty = abs(float(item["qty_signed"]))
                cost = float(MATERIAL_PRICES.get(mat_id, 0))
                cost_val = qty * cost

                if mvt == "101":
                    lines.append(_make_line(fi_id, line_no,     GL_MAP["inventory"], cost_val, 0))
                    lines.append(_make_line(fi_id, line_no + 1, GL_MAP["gr_ir"],     0, cost_val))
                    line_no += 2

                elif mvt == "551":
                    lines.append(_make_line(fi_id, line_no,     GL_MAP["scrap_expense"], cost_val, 0))
                    lines.append(_make_line(fi_id, line_no + 1, GL_MAP["inventory"],     0, cost_val))
                    line_no += 2

                elif mvt == "261":
                    lines.append(_make_line(fi_id, line_no,     GL_MAP["cogs"],      cost_val, 0))
                    lines.append(_make_line(fi_id, line_no + 1, GL_MAP["inventory"], 0, cost_val))
                    line_no += 2

                elif mvt == "601":
                    # a) inventory outflow at cost
                    lines.append(_make_line(fi_id, line_no,     GL_MAP["cogs"],      cost_val, 0))
                    lines.append(_make_line(fi_id, line_no + 1, GL_MAP["inventory"], 0, cost_val))
                    line_no += 2
                    # b) revenue recognition at net_price
                    rev_val = qty * float(net_prices.get(mat_id, cost))
                    lines.append(_make_line(fi_id, line_no,     GL_MAP["ar"],      rev_val, 0))
                    lines.append(_make_line(fi_id, line_no + 1, GL_MAP["revenue"], 0, rev_val))
                    line_no += 2

                elif mvt == "701":
                    adj_val = float(item["qty_signed"]) * cost
                    if adj_val >= 0:
                        lines.append(_make_line(fi_id, line_no,     GL_MAP["inventory"],     adj_val, 0))
                        lines.append(_make_line(fi_id, line_no + 1, GL_MAP["inventory_adj"], 0, adj_val))
                    else:
                        adj_abs = abs(adj_val)
                        lines.append(_make_line(fi_id, line_no,     GL_MAP["inventory_adj"], adj_abs, 0))
                        lines.append(_make_line(fi_id, line_no + 1, GL_MAP["inventory"],     0, adj_abs))
                    line_no += 2

            if lines:
                db.insert("fi_document_line", lines, dry_run=dry_run)

            docs_created += 1
            logger.info("FI %s | mvt %s | mat_doc %s | %d lines",
                        fi_id, mvt, mat_doc_id, len(lines))

    except Exception as exc:
        issues.append(f"step_07_fi_posting failed: {exc}")
        logger.exception("step_07_fi_posting error")
        return StepResult("step_07_fi_posting", "failed", docs_created, issues)

    return StepResult("step_07_fi_posting", "ok", docs_created, issues)
