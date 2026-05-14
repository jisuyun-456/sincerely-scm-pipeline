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
