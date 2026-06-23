"""Sub-Spec 4 가정 OTIF 추정 — 배송방식별 가정 POD + 납기 준수 예측.

실제 OTIF는 Airtable OTIF 테이블(formula)이 처리. 본 모듈은 미출하 shipment의
예측값만 계산 → JSONL 로그 (P5 Scorecard 집계용).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from harness.dispatch.scheduling import add_logen_days

# Airtable field IDs (Shipment table)
FLD_SHIP_DATE = "fldQvmEwwzvQW95h9"   # 출하확정일
FLD_PROMISE = "fldyYIfBhhu7sEX1P"      # 약속납기일
FLD_METHOD = "flduzH5tS7orqGG3o"       # 배송 방식 (rollup)
FLD_POD = "fldNPH5xLdYevknfZ"          # POD_확인일시

DEFAULT_LOG_PATH = Path("_AutoResearch/SCM/outputs/audit_log/assumed_otif.jsonl")

# 실제 배송방식 값은 접미사가 붙는다('퀵(수도권)'·'택배(일반)'·'신시어리택배' 등).
# 정확일치(set membership)면 100% 측정불가가 되므로 부분문자열(substring)로 매칭. (2026-06-22 fix)
SAME_DAY_KEYS = ("퀵", "자체기사", "바로고")
LOGEN_KEYS = ("택배", "로젠")


def _first(val) -> str:
    if isinstance(val, list):
        return str(val[0]) if val else ""
    return str(val) if val is not None else ""


@dataclass
class OtifResult:
    record_id: str
    on_time: Optional[bool]
    assumed_pod: Optional[date]
    method: str  # "당일" | "로젠+3일" | "측정불가" | "POD확인완료"


def _estimate_one(rec: dict) -> OtifResult:
    record_id = rec["id"]
    f = rec.get("fields", {})

    if f.get(FLD_POD):
        return OtifResult(record_id=record_id, on_time=None,
                          assumed_pod=None, method="POD확인완료")

    ship_date_raw = f.get(FLD_SHIP_DATE, "")
    promise_raw = f.get(FLD_PROMISE, "")
    method_raw = _first(f.get(FLD_METHOD))

    if not ship_date_raw or not promise_raw or not method_raw:
        return OtifResult(record_id=record_id, on_time=None,
                          assumed_pod=None, method="측정불가")

    ship_date = date.fromisoformat(ship_date_raw[:10])
    promise_date = date.fromisoformat(promise_raw[:10])

    if any(k in method_raw for k in SAME_DAY_KEYS):
        assumed_pod = ship_date
        method = "당일"
    elif any(k in method_raw for k in LOGEN_KEYS):
        assumed_pod = add_logen_days(ship_date, 3)
        method = "로젠+3일"
    else:
        return OtifResult(record_id=record_id, on_time=None,
                          assumed_pod=None, method="측정불가")

    return OtifResult(
        record_id=record_id,
        on_time=assumed_pod <= promise_date,
        assumed_pod=assumed_pod,
        method=method,
    )


def estimate_all(
    raw_records: list[dict],
    log_path: Path | None = None,
) -> list[OtifResult]:
    """각 shipment 가정 OTIF 계산 → JSONL append + list 반환."""
    if log_path is None:
        log_path = DEFAULT_LOG_PATH
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    results = [_estimate_one(rec) for rec in raw_records]
    ts = datetime.now().isoformat()

    with open(log_path, "a", encoding="utf-8") as f:
        for r in results:
            entry = {
                "ts": ts,
                "record_id": r.record_id,
                "on_time": r.on_time,
                "assumed_pod": r.assumed_pod.isoformat() if r.assumed_pod else None,
                "method": r.method,
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return results


def otif_summary_by_wave(
    results: list[OtifResult],
    plans: dict,
) -> dict[str, dict]:
    """record_id → wave 역매핑 후 wave별 on_time / at_risk 집계.

    on_time=None (측정불가/POD확인완료)은 집계에서 제외.
    """
    id_to_wave: dict[str, str] = {}
    for wave_id, plan in plans.items():
        for s in plan.shipments:
            id_to_wave[s.id] = wave_id

    summary: dict[str, dict] = {}
    for r in results:
        if r.on_time is None:
            continue
        wave = id_to_wave.get(r.record_id, "수동")
        if wave not in summary:
            summary[wave] = {"total": 0, "on_time": 0, "at_risk": 0}
        summary[wave]["total"] += 1
        if r.on_time:
            summary[wave]["on_time"] += 1
        else:
            summary[wave]["at_risk"] += 1

    return summary
