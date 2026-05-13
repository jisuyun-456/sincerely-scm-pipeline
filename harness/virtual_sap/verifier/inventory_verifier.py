"""Inventory verifier — checks mat_document and inventory_snapshot integrity."""
from __future__ import annotations

import logging

from .. import supabase_client as db
from .base import DimScore, Issue, Severity, VerifierResult

logger = logging.getLogger(__name__)

# Movement types and their expected item sign:
#   positive movements: qty > 0 (stock in)
#   negative movements: qty < 0 (stock out)
_POSITIVE_MOVEMENTS = {"101", "122"}   # GR, return GR
_NEGATIVE_MOVEMENTS = {"601", "261", "551"}  # GI delivery, production, scrap
_ADJ_MOVEMENTS = {"701"}               # adjustment — sign depends on direction
_TRANSFER_MOVEMENT = "311"             # must have one +, one - item pair


def verify(sim_run_id: str) -> VerifierResult:
    """Run all inventory dimension checks for the given sim_run_id."""
    issues: list[Issue] = []
    dim_scores: list[DimScore] = []

    # Fetch mat_documents for this run
    mat_docs = db.select("mat_document", {"sim_run_id": sim_run_id})
    mat_doc_ids = {d["mat_doc_id"] for d in mat_docs}

    # Fetch all items for these documents (filter client-side to avoid N+1)
    all_items: list[dict] = []
    if mat_doc_ids:
        all_items = db.select("mat_document_item", filters={"mat_doc_id": list(mat_doc_ids)})

    # ── D1 Scope: all items have valid material_id and plant_id ───────────────
    d1_issues: list[Issue] = []
    for item in all_items:
        if not item.get("material_id"):
            d1_issues.append(Issue(
                dim="D1", severity=Severity.ERROR,
                entity_type="mat_document_item", entity_id=str(item.get("item_id", "?")),
                msg="material_id is null",
            ))
        if not item.get("plant_id"):
            d1_issues.append(Issue(
                dim="D1", severity=Severity.ERROR,
                entity_type="mat_document_item", entity_id=str(item.get("item_id", "?")),
                msg="plant_id is null",
            ))
    issues.extend(d1_issues)
    dim_scores.append(DimScore("D1", passed=len(d1_issues) == 0, issue_count=len(d1_issues)))

    # ── D2 Integrity: no orphan mat_document_items ────────────────────────────
    d2_issues: list[Issue] = []
    for item in all_items:
        item_doc_id = item.get("mat_doc_id")
        if item_doc_id not in mat_doc_ids:
            d2_issues.append(Issue(
                dim="D2", severity=Severity.ERROR,
                entity_type="mat_document_item", entity_id=str(item.get("item_id", "?")),
                msg=f"orphan: mat_doc_id {item_doc_id} not found in mat_document",
            ))
    issues.extend(d2_issues)
    dim_scores.append(DimScore("D2", passed=len(d2_issues) == 0, issue_count=len(d2_issues)))

    # ── D4 Outlier: negative qty_on_hand in inventory_snapshot ───────────────
    d4_issues: list[Issue] = []
    snapshots = db.select("inventory_snapshot", limit=500)
    for snap in snapshots:
        qty = snap.get("qty_on_hand")
        if qty is not None and qty < 0:
            d4_issues.append(Issue(
                dim="D4", severity=Severity.ERROR,
                entity_type="inventory_snapshot",
                entity_id=f"{snap.get('material_id','?')}@{snap.get('plant_id','?')}",
                msg=f"negative qty_on_hand={qty}",
            ))
    issues.extend(d4_issues)
    dim_scores.append(DimScore("D4", passed=len(d4_issues) == 0, issue_count=len(d4_issues)))

    # ── D5 BizRule: movement sign and 311 pair validation ────────────────────
    d5_issues: list[Issue] = []
    items_by_doc: dict[str, list[dict]] = {}
    for item in all_items:
        items_by_doc.setdefault(item["mat_doc_id"], []).append(item)

    for doc in mat_docs:
        doc_id = doc["mat_doc_id"]
        mvt = str(doc.get("movement_type", ""))
        doc_items = items_by_doc.get(doc_id, [])

        if mvt == _TRANSFER_MOVEMENT:
            # 311: must have exactly one positive and one negative item
            signs = [1 if (i.get("qty") or 0) > 0 else -1 for i in doc_items]
            pos_count = signs.count(1)
            neg_count = signs.count(-1)
            if pos_count != 1 or neg_count != 1:
                d5_issues.append(Issue(
                    dim="D5", severity=Severity.ERROR,
                    entity_type="mat_document", entity_id=doc_id,
                    msg=f"movement 311 must have 1 positive + 1 negative item; got +{pos_count}/-{neg_count}",
                ))
        elif mvt in _POSITIVE_MOVEMENTS:
            for item in doc_items:
                if (item.get("qty_signed") or 0) <= 0:
                    d5_issues.append(Issue(
                        dim="D5", severity=Severity.WARN,
                        entity_type="mat_document_item", entity_id=str(item.get("item_id", "?")),
                        msg=f"movement {mvt} item has non-positive qty={item.get('qty')}",
                    ))
        elif mvt in _NEGATIVE_MOVEMENTS:
            for item in doc_items:
                if (item.get("qty_signed") or 0) >= 0:
                    d5_issues.append(Issue(
                        dim="D5", severity=Severity.WARN,
                        entity_type="mat_document_item", entity_id=str(item.get("item_id", "?")),
                        msg=f"movement {mvt} item has non-negative qty={item.get('qty')}",
                    ))

    issues.extend(d5_issues)
    dim_scores.append(DimScore("D5", passed=len(d5_issues) == 0, issue_count=len(d5_issues)))

    overall = all(d.passed for d in dim_scores)
    logger.info("inventory_verifier: run=%s passed=%s issues=%d", sim_run_id, overall, len(issues))
    return VerifierResult(passed=overall, dim_scores=dim_scores, issues=issues)
