"""Step 08 — Month-end Period Close.

Runs only on the 1st of the month. Closes the prior period:
  1. Check if prior period already closed — skip if so.
  2. Post a placeholder REVAL FI document (Dr/Cr 5610 ₩1 each).
  3. Update sap.period_close prior_period → 'closed'.
  4. Ensure current period row exists with status='open'.

Updates (non-ledger): sap.period_close
Inserts into: sap.fi_document, sap.fi_document_line, sap.period_close
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


def _period_str(year: int, month: int) -> str:
    return f"{year}{month:02d}"


def _prior_period(now: date) -> str:
    if now.month == 1:
        return _period_str(now.year - 1, 12)
    return _period_str(now.year, now.month - 1)


def run(sim_run_id: str, ctx: SimContext) -> StepResult:
    dry_run = get_config().dry_run
    now_date = date.fromisoformat(ctx["now_date"])
    issues: list[str] = []
    docs_created = 0

    if now_date.day != 1:
        logger.info("step_08_period_close: not 1st of month (%s), skipping", now_date)
        return StepResult("step_08_period_close", "skipped", 0, issues)

    prior_period = _prior_period(now_date)
    current_period = now_date.strftime("%Y%m")

    try:
        closed_rows = db.select(
            "period_close",
            {"period": prior_period, "status": "closed"},
            columns="period",
            limit=1,
        )
        if closed_rows:
            logger.info("step_08_period_close: period %s already closed", prior_period)
            return StepResult("step_08_period_close", "skipped", 0, issues)

        fi_id = next_id("FI", now_date, dry_run=dry_run)
        db.insert("fi_document", {
            "fi_doc_id": fi_id,
            "doc_type": "REVAL",
            "posting_date": now_date.isoformat(),
            "period": prior_period,
            "source_mat_doc_id": None,
            "description": f"period_close placeholder reval | sim_run={sim_run_id}",
            "sim_run_id": sim_run_id,
        }, dry_run=dry_run)

        db.insert("fi_document_line", [
            {
                "fi_doc_id": fi_id,
                "line_no": 1,
                "gl_code": GL_MAP["inventory_adj"],
                "debit_credit": "D",
                "amount_local": 1.0,
            },
            {
                "fi_doc_id": fi_id,
                "line_no": 2,
                "gl_code": GL_MAP["inventory_adj"],
                "debit_credit": "C",
                "amount_local": 1.0,
            },
        ], dry_run=dry_run)
        docs_created += 1

        prior_rows = db.select("period_close", {"period": prior_period}, columns="period", limit=1)
        if prior_rows:
            db.update(
                "period_close",
                match={"period": prior_period},
                updates={"status": "closed", "closed_at": now_date.isoformat()},
                dry_run=dry_run,
            )
        else:
            db.insert("period_close", {
                "period": prior_period,
                "status": "closed",
                "closed_at": now_date.isoformat(),
            }, dry_run=dry_run)

        current_rows = db.select(
            "period_close", {"period": current_period}, columns="period", limit=1
        )
        if not current_rows:
            db.insert("period_close", {
                "period": current_period,
                "status": "open",
                "closed_at": None,
            }, dry_run=dry_run)

        logger.info("Period %s closed; period %s opened | REVAL %s",
                    prior_period, current_period, fi_id)

    except Exception as exc:
        issues.append(f"step_08_period_close failed: {exc}")
        logger.exception("step_08_period_close error")
        return StepResult("step_08_period_close", "failed", docs_created, issues)

    return StepResult("step_08_period_close", "ok", docs_created, issues)
