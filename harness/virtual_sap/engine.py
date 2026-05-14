"""Virtual SAP Simulation — Engine orchestrator."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from datetime import date

from .config import get_config
from . import supabase_client as db
from .steps import (
    step_01_order,
    step_02_inbound,
    step_03_inventory,
    step_04_production,
    step_05_outbound,
    step_06_delivery,
    step_07_fi_posting,
    step_08_period_close,
)
from .verifier import inventory_verifier, doc_verifier, flow_verifier, ledger_verifier
from .notifier import notify_failure

logger = logging.getLogger(__name__)

STEPS = [
    step_01_order,
    step_02_inbound,
    step_03_inventory,
    step_04_production,
    step_05_outbound,
    step_06_delivery,
    step_07_fi_posting,
    step_08_period_close,
]


def run_tick(mode: str = "manual", orders_count: int = 2) -> dict:
    """Execute one simulation tick. Returns summary dict."""
    cfg = get_config()
    now_date = date.today().isoformat()
    sim_run_id = str(uuid.uuid4())

    # Create sim_run record — DB constraint only allows manual/daily/backfill
    db_mode = "manual" if mode == "continuous" else mode
    run_row = db.insert("sim_run", {
        "id": sim_run_id,
        "mode": db_mode,
        "status": "running",
        "git_sha": _get_git_sha(),
    }, dry_run=cfg.dry_run)

    actual_run_id = run_row[0].get("id", sim_run_id) if run_row else sim_run_id

    ctx = {
        "sim_run_id": actual_run_id,
        "now_date": now_date,
        "now_ts": datetime.now(timezone.utc).isoformat(),
        "is_continuous": (mode == "continuous"),
        "dry_run": cfg.dry_run,
        "orders_count": orders_count,
    }

    total_docs = 0
    all_issues: list = []

    try:
        for step_module in STEPS:
            step_name = step_module.__name__.split(".")[-1]
            logger.info("Running step: %s", step_name)

            # Log step start
            step_log_id = str(uuid.uuid4())
            db.insert("sim_step_log", {
                "step_id": step_log_id,
                "sim_run_id": actual_run_id,
                "step_name": step_name,
                "status": "running",
            }, dry_run=cfg.dry_run)

            result = step_module.run(actual_run_id, ctx)
            total_docs += result.docs_created
            all_issues.extend(result.issues)

            # Update step log to finished
            db.update("sim_step_log", {"step_id": step_log_id}, {
                "status": result.status,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "docs_created_count": result.docs_created,
                "verifier_result_json": {"issues": result.issues},
            }, dry_run=cfg.dry_run)

        # Run global verifiers
        # continuous mode: skip flow_verifier (SOs created this tick won't have
        # deliveries until future ticks — E2E completeness check is meaningless)
        is_continuous = ctx.get("is_continuous", False)
        logger.info("Running verifiers...")
        v_results = _run_verifiers(actual_run_id, skip_flow=is_continuous)
        # continuous: verifier issues are warnings, not fatal
        v_passed = True if is_continuous else all(v.passed for v in v_results)

        # Finalize sim_run
        final_status = "ok" if v_passed else "failed"
        db.update("sim_run", {"id": actual_run_id}, {
            "status": final_status,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "docs_created": total_docs,
            "summary_json": {"verifiers_passed": v_passed, "issues": all_issues[:20]},
        }, dry_run=cfg.dry_run)

        logger.info("Tick complete: status=%s, docs=%d", final_status, total_docs)
        return {"status": final_status, "docs_created": total_docs, "issues": all_issues}

    except Exception as exc:
        logger.exception("Tick failed")
        db.update("sim_run", {"id": actual_run_id}, {
            "status": "failed",
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "summary_json": {"error": str(exc)},
        }, dry_run=cfg.dry_run)
        notify_failure(str(exc), actual_run_id)
        raise


def _run_verifiers(sim_run_id: str, skip_flow: bool = False):
    verifiers = [inventory_verifier, doc_verifier, ledger_verifier]
    if not skip_flow:
        verifiers.append(flow_verifier)
    results = []
    for verifier_module in verifiers:
        try:
            r = verifier_module.verify(sim_run_id)
            results.append(r)
        except Exception as exc:
            logger.error("Verifier %s failed: %s", verifier_module.__name__, exc)
    return results


def _get_git_sha() -> str:
    import subprocess
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"
