"""Sub-Spec 2 audit logging.

Two append-only jsonl streams:
- `audit_log/cbm_transitions.jsonl` — Total_CBM transitions (NULL→N or N→M)
- `audit_log/cbm_anomalies.jsonl` — |estimated − actual| / actual > 50% with actual > 0.1
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

AUDIT_DIR = "audit_log"
ANOMALY_DIFF_RATIO_THRESHOLD = 0.5
ANOMALY_MIN_ACTUAL_CBM = 0.1


def _append(filename: str, entry: dict) -> None:
    os.makedirs(AUDIT_DIR, exist_ok=True)
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    with open(os.path.join(AUDIT_DIR, filename), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def log_transition(sc_id: str, prev_total_cbm: float, new_total_cbm: float,
                   estimate_before: float, confidence_after: float) -> None:
    """Total_CBM 전이 시 호출 — re-estimate cycle 진입."""
    _append("cbm_transitions.jsonl", {
        "type": "transition",
        "sc_id": sc_id,
        "prev_total_cbm": prev_total_cbm,
        "new_total_cbm": new_total_cbm,
        "estimate_before": estimate_before,
        "confidence_after": confidence_after,
    })


def log_anomaly(sc_id: str, estimated: float, actual: float,
                matched: list, unmatched: list) -> bool:
    """추정-실측 괴리 50%+ 시 anomaly 기록. Returns True if logged."""
    if actual <= ANOMALY_MIN_ACTUAL_CBM:
        return False
    diff = abs(estimated - actual)
    diff_ratio = diff / actual
    if diff_ratio <= ANOMALY_DIFF_RATIO_THRESHOLD:
        return False
    _append("cbm_anomalies.jsonl", {
        "type": "anomaly",
        "sc_id": sc_id,
        "estimated": estimated,
        "actual": actual,
        "diff": round(diff, 4),
        "diff_ratio": round(diff_ratio, 3),
        "matched": matched,
        "unmatched": unmatched,
    })
    return True
