"""Ledger verifier — checks immutable ledger integrity (reversals, orphans, dates)."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from .. import supabase_client as db
from .base import DimScore, Issue, Severity, VerifierResult

logger = logging.getLogger(__name__)

_MAX_DATE_AGE_DAYS = 365


def verify(sim_run_id: str) -> VerifierResult:
    """Run ledger integrity checks for the given sim_run_id."""
    issues: list[Issue] = []
    dim_scores: list[DimScore] = []

    today = date.today()
    oldest_allowed = today - timedelta(days=_MAX_DATE_AGE_DAYS)

    # Fetch mat_documents and fi_documents for this run
    mat_docs = db.select("mat_document", {"sim_run_id": sim_run_id})
    fi_docs = db.select("fi_document", {"sim_run_id": sim_run_id})
    mat_doc_ids = {d["mat_doc_id"] for d in mat_docs}
    fi_doc_ids = {d["fi_doc_id"] for d in fi_docs}

    # Fetch ALL mat_document_items for orphan check
    all_items: list[dict] = []
    if mat_doc_ids:
        all_items = db.select("mat_document_item", {"mat_doc_id": list(mat_doc_ids)})

    # ── D1 Scope: posting_date within last 365 days, not in the future ────────
    d1_issues: list[Issue] = []
    for doc in mat_docs:
        raw_date = (doc.get("posting_date") or "")[:10]
        if not raw_date:
            continue
        try:
            posting = date.fromisoformat(raw_date)
        except ValueError:
            d1_issues.append(Issue(
                dim="D1", severity=Severity.ERROR,
                entity_type="mat_document", entity_id=doc["mat_doc_id"],
                msg=f"invalid posting_date format: '{raw_date}'",
            ))
            continue
        if posting > today:
            d1_issues.append(Issue(
                dim="D1", severity=Severity.WARN,
                entity_type="mat_document", entity_id=doc["mat_doc_id"],
                msg=f"posting_date {posting} is in the future",
            ))
        elif posting < oldest_allowed:
            d1_issues.append(Issue(
                dim="D1", severity=Severity.WARN,
                entity_type="mat_document", entity_id=doc["mat_doc_id"],
                msg=f"posting_date {posting} is older than {_MAX_DATE_AGE_DAYS} days",
            ))

    issues.extend(d1_issues)
    dim_scores.append(DimScore("D1", passed=len(d1_issues) == 0, issue_count=len(d1_issues)))

    # ── D2 Integrity: no orphan mat_document_items ────────────────────────────
    d2_issues: list[Issue] = []
    for item in all_items:
        if item.get("mat_doc_id") not in mat_doc_ids:
            d2_issues.append(Issue(
                dim="D2", severity=Severity.ERROR,
                entity_type="mat_document_item", entity_id=str(item.get("item_id", "?")),
                msg=f"orphan item: mat_doc_id {item.get('mat_doc_id')} not in mat_document",
            ))

    issues.extend(d2_issues)
    dim_scores.append(DimScore("D2", passed=len(d2_issues) == 0, issue_count=len(d2_issues)))

    # ── D5 BizRule: reversal pointers are valid ───────────────────────────────
    d5_issues: list[Issue] = []

    # mat_document reversals
    for doc in mat_docs:
        if doc.get("is_reversal"):
            reverses_id = doc.get("reverses_doc_id")
            if not reverses_id:
                d5_issues.append(Issue(
                    dim="D5", severity=Severity.ERROR,
                    entity_type="mat_document", entity_id=doc["mat_doc_id"],
                    msg="is_reversal=True but reverses_doc_id is null",
                ))
            else:
                # Look up the target across all mat_documents (not just this run)
                target = db.select("mat_document", {"mat_doc_id": reverses_id}, limit=1)
                if not target:
                    d5_issues.append(Issue(
                        dim="D5", severity=Severity.ERROR,
                        entity_type="mat_document", entity_id=doc["mat_doc_id"],
                        msg=f"reverses_doc_id {reverses_id} does not exist in mat_document",
                    ))

    # fi_document reversals
    for doc in fi_docs:
        if doc.get("is_reversal"):
            reverses_id = doc.get("reverses_fi_doc_id")
            if not reverses_id:
                d5_issues.append(Issue(
                    dim="D5", severity=Severity.ERROR,
                    entity_type="fi_document", entity_id=doc["fi_doc_id"],
                    msg="is_reversal=True but reverses_fi_doc_id is null",
                ))
            else:
                target = db.select("fi_document", {"fi_doc_id": reverses_id}, limit=1)
                if not target:
                    d5_issues.append(Issue(
                        dim="D5", severity=Severity.ERROR,
                        entity_type="fi_document", entity_id=doc["fi_doc_id"],
                        msg=f"reverses_fi_doc_id {reverses_id} does not exist in fi_document",
                    ))

    issues.extend(d5_issues)
    dim_scores.append(DimScore("D5", passed=len(d5_issues) == 0, issue_count=len(d5_issues)))

    overall = all(d.passed for d in dim_scores)
    logger.info("ledger_verifier: run=%s passed=%s issues=%d", sim_run_id, overall, len(issues))
    return VerifierResult(passed=overall, dim_scores=dim_scores, issues=issues)
