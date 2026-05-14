"""Shared issue injection utility for continuous simulation mode."""
from __future__ import annotations

import logging
from enum import Enum
from random import Random

logger = logging.getLogger(__name__)


class IssueCode(str, Enum):
    STOCK_SHORT   = "STOCK_SHORT"    # step_04: 재고 부족 → 생산 skip
    PROD_DELAY    = "PROD_DELAY"     # step_04: 생산 지연 → this-tick skip
    PACK_DAMAGE   = "PACK_DAMAGE"    # step_05: 포장 파손 → qty 10% 감소
    DLV_EXCEPTION = "DLV_EXCEPTION"  # step_06: 배송 예외 → pod_status='exception'


def maybe_inject(rng: Random, code: IssueCode, rate: float) -> bool:
    """Return True with probability `rate`. Uses rng for reproducibility."""
    return rng.random() < rate


def record_issue(db, sim_run_id: str, severity: str, message: str, dry_run: bool) -> None:
    """Insert a sim_issue record into the sap schema."""
    logger.warning("SIM_ISSUE [%s] %s", severity, message)
    db.insert("sim_issue", {
        "sim_run_id": sim_run_id,
        "severity": severity,
        "message": message,
    }, dry_run=dry_run)


# ─────────────────────────────────────────────────────
# Phase F — Manual fault injection (for testing agents)
# ─────────────────────────────────────────────────────

def inject_aql_failure(db, gr_id: str, dry_run: bool = False) -> bool:
    """Set qi_inspection.disposition='block' for all items in a GR.

    Simulates an AQL inspection failure → triggers quality_reject_agent on next tick.
    """
    rows = db.select("qi_inspection", {"gr_id": gr_id}, columns="qi_id, disposition")
    if not rows:
        logger.warning("inject_aql_failure: no qi_inspection rows for gr_id=%s", gr_id)
        return False
    for row in rows:
        if row.get("disposition") != "block":
            db.update("qi_inspection", {"qi_id": row["qi_id"]},
                      {"disposition": "block"}, dry_run=dry_run)
    logger.info("inject_aql_failure: %d row(s) set to block for gr_id=%s", len(rows), gr_id)
    return True


def inject_pod_damage(db, ship_id: str, dry_run: bool = False) -> bool:
    """Set shipment.pod_status='exception' to simulate a damaged/short delivery.

    Triggers claim_agent on next tick.
    """
    rows = db.select("shipment", {"ship_id": ship_id}, columns="ship_id, pod_status", limit=1)
    if not rows:
        logger.warning("inject_pod_damage: shipment %s not found", ship_id)
        return False
    db.update("shipment", {"ship_id": ship_id},
              {"pod_status": "exception"}, dry_run=dry_run)
    logger.info("inject_pod_damage: shipment %s → pod_status=exception", ship_id)
    return True
