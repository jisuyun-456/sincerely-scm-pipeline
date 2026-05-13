"""FI document verifier — checks fi_document integrity and coverage."""
from __future__ import annotations

import logging

from .. import supabase_client as db
from .base import DimScore, Issue, Severity, VerifierResult

logger = logging.getLogger(__name__)

# Movement types that MUST have a corresponding FI document
_FI_REQUIRED_MOVEMENTS = {"101", "601", "261", "551", "701"}
# 311 (transfer) is excluded — no FI posting for intra-plant stock moves


def verify(sim_run_id: str) -> VerifierResult:
    """Run FI document integrity checks for the given sim_run_id."""
    issues: list[Issue] = []
    dim_scores: list[DimScore] = []

    # Fetch FI documents for this run
    fi_docs = db.select("fi_document", {"sim_run_id": sim_run_id})
    fi_doc_ids = {d["fi_doc_id"] for d in fi_docs}

    # Fetch FI document lines for these docs
    all_lines: list[dict] = []
    if fi_doc_ids:
        all_lines = db.select("fi_document_line", {"fi_doc_id": list(fi_doc_ids)})

    lines_by_doc: dict[str, list[dict]] = {}
    for line in all_lines:
        lines_by_doc.setdefault(line["fi_doc_id"], []).append(line)

    # ── D2 Integrity: every fi_document has at least 2 lines ─────────────────
    d2_issues: list[Issue] = []
    for doc in fi_docs:
        doc_id = doc["fi_doc_id"]
        line_count = len(lines_by_doc.get(doc_id, []))
        if line_count < 2:
            d2_issues.append(Issue(
                dim="D2", severity=Severity.ERROR,
                entity_type="fi_document", entity_id=doc_id,
                msg=f"fi_document has {line_count} line(s); minimum is 2",
            ))

    # D2: every fi_document_line.fi_doc_id resolves
    for line in all_lines:
        if line.get("fi_doc_id") not in fi_doc_ids:
            d2_issues.append(Issue(
                dim="D2", severity=Severity.ERROR,
                entity_type="fi_document_line", entity_id=str(line.get("line_id", "?")),
                msg=f"orphan: fi_doc_id {line.get('fi_doc_id')} not found in fi_document",
            ))

    issues.extend(d2_issues)
    dim_scores.append(DimScore("D2", passed=len(d2_issues) == 0, issue_count=len(d2_issues)))

    # ── D3 Coverage: every relevant mat_document has a matching fi_document ──
    d3_issues: list[Issue] = []
    mat_docs = db.select("mat_document", {"sim_run_id": sim_run_id})
    fi_by_mat_doc = {d.get("source_mat_doc_id"): d["fi_doc_id"] for d in fi_docs
                     if d.get("source_mat_doc_id")}

    for doc in mat_docs:
        mvt = str(doc.get("movement_type", ""))
        if mvt in _FI_REQUIRED_MOVEMENTS:
            mat_doc_id = doc["mat_doc_id"]
            if mat_doc_id not in fi_by_mat_doc:
                d3_issues.append(Issue(
                    dim="D3", severity=Severity.ERROR,
                    entity_type="mat_document", entity_id=mat_doc_id,
                    msg=f"movement {mvt} has no corresponding fi_document",
                ))

    issues.extend(d3_issues)
    dim_scores.append(DimScore("D3", passed=len(d3_issues) == 0, issue_count=len(d3_issues)))

    # ── D5 BizRule: debit sum = credit sum per fi_document ────────────────────
    d5_issues: list[Issue] = []
    for doc in fi_docs:
        doc_id = doc["fi_doc_id"]
        doc_lines = lines_by_doc.get(doc_id, [])
        debit_sum = sum(float(l.get("debit_amount") or 0) for l in doc_lines)
        credit_sum = sum(float(l.get("credit_amount") or 0) for l in doc_lines)
        # Allow small floating-point tolerance
        if abs(debit_sum - credit_sum) > 0.01:
            d5_issues.append(Issue(
                dim="D5", severity=Severity.ERROR,
                entity_type="fi_document", entity_id=doc_id,
                msg=f"debit={debit_sum:.2f} != credit={credit_sum:.2f} (diff={abs(debit_sum - credit_sum):.2f})",
            ))

    issues.extend(d5_issues)
    dim_scores.append(DimScore("D5", passed=len(d5_issues) == 0, issue_count=len(d5_issues)))

    overall = all(d.passed for d in dim_scores)
    logger.info("doc_verifier: run=%s passed=%s issues=%d", sim_run_id, overall, len(issues))
    return VerifierResult(passed=overall, dim_scores=dim_scores, issues=issues)
