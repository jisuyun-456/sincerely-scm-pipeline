"""Flow verifier — checks end-to-end order-to-delivery flow completeness."""
from __future__ import annotations

import logging

from .. import supabase_client as db
from .base import DimScore, Issue, Severity, VerifierResult

logger = logging.getLogger(__name__)


def verify(sim_run_id: str) -> VerifierResult:
    """Run end-to-end flow completeness checks for the given sim_run_id."""
    issues: list[Issue] = []
    dim_scores: list[DimScore] = []

    # ── Fetch data ────────────────────────────────────────────────────────────
    sales_orders = db.select("sales_order", {"sim_run_id": sim_run_id})
    outbound_deliveries = db.select("outbound_delivery", {"sim_run_id": sim_run_id})
    fi_docs = db.select("fi_document", {"sim_run_id": sim_run_id})

    so_ids = {so["so_id"] for so in sales_orders}
    deliveries_by_so: dict[str, list[dict]] = {}
    for od in outbound_deliveries:
        deliveries_by_so.setdefault(od.get("so_id", ""), []).append(od)

    # Index: goods_issue mat_doc_id → fi_document exists
    fi_mat_doc_ids = {d.get("source_mat_doc_id") for d in fi_docs if d.get("source_mat_doc_id")}

    # SO items for qty check
    so_items = db.select("sales_order_item", {"so_id": list(so_ids)}) if so_ids else []
    ordered_qty_by_so_mat: dict[tuple, float] = {}
    for item in so_items:
        key = (item.get("so_id"), item.get("material_id"))
        ordered_qty_by_so_mat[key] = float(item.get("ordered_qty") or 0)

    # ── D3 Coverage: every sales_order has at least one outbound_delivery ─────
    d3_issues: list[Issue] = []
    for so in sales_orders:
        so_id = so["so_id"]
        if not deliveries_by_so.get(so_id):
            d3_issues.append(Issue(
                dim="D3", severity=Severity.ERROR,
                entity_type="sales_order", entity_id=so_id,
                msg="no outbound_delivery found for this sales_order",
            ))

    # D3: every outbound_delivery with goods_issue_status='posted' has goods_issue_mat_doc_id
    for od in outbound_deliveries:
        od_id = od.get("delivery_id", "?")
        if od.get("goods_issue_status") == "posted":
            if not od.get("goods_issue_mat_doc_id"):
                d3_issues.append(Issue(
                    dim="D3", severity=Severity.ERROR,
                    entity_type="outbound_delivery", entity_id=od_id,
                    msg="goods_issue_status='posted' but goods_issue_mat_doc_id is null",
                ))
            else:
                # D3: every goods_issue mat_doc has a corresponding fi_document
                gi_mat_doc_id = od["goods_issue_mat_doc_id"]
                if gi_mat_doc_id not in fi_mat_doc_ids:
                    d3_issues.append(Issue(
                        dim="D3", severity=Severity.ERROR,
                        entity_type="outbound_delivery", entity_id=od_id,
                        msg=f"goods_issue mat_doc {gi_mat_doc_id} has no fi_document",
                    ))

    issues.extend(d3_issues)
    dim_scores.append(DimScore("D3", passed=len(d3_issues) == 0, issue_count=len(d3_issues)))

    # ── D5 BizRule: delivery qty <= sales_order ordered_qty ───────────────────
    d5_issues: list[Issue] = []
    # Fetch delivery items for quantity check
    delivery_ids = {od.get("delivery_id") for od in outbound_deliveries if od.get("delivery_id")}
    delivery_items = db.select("outbound_delivery_item", {"delivery_id": list(delivery_ids)}) if delivery_ids else []

    # Sum delivery qty per (so_id, material_id)
    delivered_qty_by_so_mat: dict[tuple, float] = {}
    for di in delivery_items:
        so_id = di.get("so_id")
        mat_id = di.get("material_id")
        key = (so_id, mat_id)
        delivered_qty_by_so_mat[key] = delivered_qty_by_so_mat.get(key, 0.0) + float(di.get("delivery_qty") or 0)

    for (so_id, mat_id), delivered_qty in delivered_qty_by_so_mat.items():
        ordered_qty = ordered_qty_by_so_mat.get((so_id, mat_id))
        if ordered_qty is not None and delivered_qty > ordered_qty:
            d5_issues.append(Issue(
                dim="D5", severity=Severity.ERROR,
                entity_type="outbound_delivery_item",
                entity_id=f"{so_id}/{mat_id}",
                msg=f"delivery_qty={delivered_qty} > ordered_qty={ordered_qty}",
            ))

    issues.extend(d5_issues)
    dim_scores.append(DimScore("D5", passed=len(d5_issues) == 0, issue_count=len(d5_issues)))

    overall = all(d.passed for d in dim_scores)
    logger.info("flow_verifier: run=%s passed=%s issues=%d", sim_run_id, overall, len(issues))
    return VerifierResult(passed=overall, dim_scores=dim_scores, issues=issues)
