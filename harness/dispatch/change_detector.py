"""Sub-Spec 4 Change Detection — 직전 스캔 대비 신규/취소/변경 감지.

snapshot 포맷: {record_id: {"출하확정일": str, "배송방식": str, "주소": str,
                             "발송상태": str, "cbm": float}}
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Airtable field IDs (Shipment table)
FLD_SHIP_DATE = "fldQvmEwwzvQW95h9"  # 출하확정일
FLD_METHOD = "flduzH5tS7orqGG3o"     # 배송 방식 (rollup)
FLD_ADDRESS = "fldyJHUh9gN44Ggnh"    # 수령인(주소) (rollup)
FLD_STATUS = "fldOhibgxg6LIpRTi"     # 발송상태_TMS
FLD_EST_CBM = "fldaP8D9AM8CHEZ2o"    # estimated_cbm

CRITICAL_FIELDS = ("출하확정일", "배송방식", "주소")


def _first(val) -> str:
    """multipleLookupValues 또는 plain 값 → 첫 번째 문자열."""
    if isinstance(val, list):
        return str(val[0]) if val else ""
    return str(val) if val is not None else ""


def _normalize(rec: dict) -> dict:
    """Airtable 원시 레코드 → 스냅샷용 normalized dict."""
    f = rec.get("fields", {})
    return {
        "출하확정일": f.get(FLD_SHIP_DATE, ""),
        "배송방식": _first(f.get(FLD_METHOD)),
        "주소": _first(f.get(FLD_ADDRESS)),
        "발송상태": f.get(FLD_STATUS, ""),
        "cbm": float(f.get(FLD_EST_CBM) or 0),
    }


@dataclass
class ChangeReport:
    added: list[str] = field(default_factory=list)             # record IDs
    removed: list[str] = field(default_factory=list)           # record IDs
    critical_modified: list[dict] = field(default_factory=list)  # [{id, field, old, new}]
    minor_modified: list[dict] = field(default_factory=list)     # [{id, field, old, new}]


def detect(
    snapshot: dict[str, dict],
    current: list[dict],
) -> tuple[ChangeReport, dict[str, dict]]:
    """스냅샷 vs 현재 레코드 비교 → (ChangeReport, new_snapshot).

    new_snapshot은 caller가 artifact 또는 파일로 저장.
    """
    report = ChangeReport()
    new_snapshot: dict[str, dict] = {}

    current_map = {rec["id"]: rec for rec in current}

    for rec_id, rec in current_map.items():
        norm = _normalize(rec)
        new_snapshot[rec_id] = norm
        if rec_id not in snapshot:
            report.added.append(rec_id)
        else:
            prev = snapshot[rec_id]
            for field_name in CRITICAL_FIELDS:
                if norm[field_name] != prev.get(field_name, ""):
                    report.critical_modified.append(
                        {"id": rec_id, "field": field_name,
                         "old": prev.get(field_name, ""), "new": norm[field_name]}
                    )
            if norm["cbm"] != prev.get("cbm", 0):
                report.minor_modified.append(
                    {"id": rec_id, "field": "cbm",
                     "old": prev.get("cbm", 0), "new": norm["cbm"]}
                )

    for rec_id in snapshot:
        if rec_id not in current_map:
            report.removed.append(rec_id)

    return report, new_snapshot
