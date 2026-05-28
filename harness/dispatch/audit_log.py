"""Wave recommender audit log — JSONL append-only.

Events:
- override_detected: 사용자가 assigned_carrier 수동 변경
- low_confidence_recommendation: wave_confidence < 0.7
- consolidation_failed: PNA 그룹 wave 배정 실패 (모든 후보 capacity full)
- locked_in_attempted_override: bug check — recommender가 locked-in 강제 변경 시도
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

LOG_PATH = Path("_AutoResearch/SCM/outputs/audit_log/wave_recommender.jsonl")


def log_event(event_type: str, payload: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {"ts": datetime.now().isoformat(), "event": event_type, **payload}
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
