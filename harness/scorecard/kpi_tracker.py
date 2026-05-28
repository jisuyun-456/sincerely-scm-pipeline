"""Sub-Spec 5 KPI 3종 계산 + JSONL 히스토리 관리."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

SELF_EMPLOYED_WAVES = {"W1", "W2", "W3"}
SPILLOVER_WAVES = {"spillover_고고엑스", "spillover_로젠"}
MANUAL_WAVE = "수동"


def calc_kpi(shipments: list[dict]) -> dict:
    """K-LC-1/2/3 계산.

    shipments: Airtable Shipment 레코드 목록.
      각 레코드 fields에 wave_recommendation, 운송비용 포함.
    """
    total = len(shipments)
    if total == 0:
        return {"K_LC_1": 0.0, "K_LC_2": 0.0, "K_LC_3": 0.0}

    self_employed_count = 0
    auto_count = 0
    spillover_cost = 0.0

    for rec in shipments:
        f = rec.get("fields", {})
        wave = f.get("wave_recommendation") or ""
        cost = float(f.get("운송비용") or 0.0)

        if wave in SELF_EMPLOYED_WAVES:
            self_employed_count += 1
        if wave and wave != MANUAL_WAVE:
            auto_count += 1
        if wave in SPILLOVER_WAVES:
            spillover_cost += cost

    return {
        "K_LC_1": self_employed_count / total,
        "K_LC_2": auto_count / total,
        "K_LC_3": spillover_cost,
    }


def load_history(path: Path) -> list[dict]:
    """JSONL → list[dict]. 파일 없으면 []."""
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def append_snapshot(path: Path, snapshot: dict) -> None:
    """월간 스냅샷 1 row append (INSERT ONLY)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")


def compute_deltas(current_kpi: dict, history: list[dict]) -> dict:
    """현재 KPI vs 직전 스냅샷 비교 → delta 포함 result dict.

    첫 실행(history 없음): baseline 설정, delta=None.
    이후 실행: 직전 스냅샷과 비교.
    """
    if not history:
        return {
            "K_LC_1": {
                "value": current_kpi["K_LC_1"],
                "baseline": current_kpi["K_LC_1"],
                "delta": None,
                "target": None,
            },
            "K_LC_2": {
                "value": current_kpi["K_LC_2"],
                "delta": None,
                "target": 0.70,
            },
            "K_LC_3": {
                "value": current_kpi["K_LC_3"],
                "baseline": current_kpi["K_LC_3"],
                "delta_pct": None,
                "target": None,
            },
        }

    prev = history[-1]["kpi"]
    prev_k1 = prev.get("K_LC_1", {})
    prev_k3 = prev.get("K_LC_3", {})

    baseline_k1 = prev_k1.get("baseline", prev_k1.get("value", current_kpi["K_LC_1"]))
    baseline_k3 = prev_k3.get("baseline", prev_k3.get("value", current_kpi["K_LC_3"]))

    prev_k1_val = prev_k1.get("value", 0.0) if isinstance(prev_k1, dict) else float(prev_k1)
    prev_k3_val = prev_k3.get("value", 0.0) if isinstance(prev_k3, dict) else float(prev_k3)

    delta_k3_pct = (
        (current_kpi["K_LC_3"] - prev_k3_val) / prev_k3_val
        if prev_k3_val != 0 else None
    )

    return {
        "K_LC_1": {
            "value": current_kpi["K_LC_1"],
            "baseline": baseline_k1,
            "delta": current_kpi["K_LC_1"] - prev_k1_val,
            "target": baseline_k1 + 0.20 if baseline_k1 is not None else None,
        },
        "K_LC_2": {
            "value": current_kpi["K_LC_2"],
            "delta": current_kpi["K_LC_2"] - (prev.get("K_LC_2", {}).get("value", 0.0)
                                               if isinstance(prev.get("K_LC_2"), dict)
                                               else float(prev.get("K_LC_2", 0.0))),
            "target": 0.70,
        },
        "K_LC_3": {
            "value": current_kpi["K_LC_3"],
            "baseline": baseline_k3,
            "delta_pct": delta_k3_pct,
            "target": baseline_k3 * 0.80 if baseline_k3 else None,
        },
    }
