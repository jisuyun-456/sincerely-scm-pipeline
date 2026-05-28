"""Sub-Spec 5 Scorecard — 점수 산출 함수 + Airtable fetch helpers."""
from __future__ import annotations

import calendar
import datetime
import os
from typing import Optional

import requests

TMS_BASE = "app4x70a8mOrIKsMf"
TBL_SHIP = "tbllg1JoHclGYer7m"
TBL_PARTNER = "tblI4ZXrte7WyhXyd"
TBL_OTIF = "tbl4WfEuGLDlqCTQH"
TBL_CLAIM = "tblIZ9kco1QDpUz0u"
TBL_RATE = "tblQA1ev9fjbowUoP"

# Shipment fields
FLD_SHIP_DATE = "fldQvmEwwzvQW95h9"      # 출하확정일
FLD_EST_CBM = "fldaP8D9AM8CHEZ2o"        # estimated_cbm
FLD_WAVE_REC = "fld9hlDfnTS4frfR4"       # wave_recommendation
FLD_TRANSPORT_COST = "fldRT95SC88KSBATT" # 운송비용
FLD_PARTNER_LINK = "fldM2u6RwLRrO7ymW"  # 배송파트너 (link)
FLD_STATUS = "fldOhibgxg6LIpRTi"         # 발송상태_TMS

# 배송파트너 fields
FLD_P_NAME = "fldUCl2kD890FqRkt"         # 배송파트너
FLD_P_MAX_DAILY = "fldEfEZHWQBx2FO7C"   # max_daily_orders
FLD_P_AUTONOMY = "fldxPZYD3OpwLtqdP"    # autonomy_level

# OTIF fields
FLD_OTIF_SHIP = "fldGwqw0LSIoa824Z"      # Shipment (link)
FLD_ON_TIME = "fldoUQOue0umGJ2xk"        # On_Time

# 배송클레임 fields
FLD_CLAIM_DATE = "fldiNGNqgmQH1MFB7"    # 발생일
FLD_CLAIM_PARTNER = "fldm96CqoNw0pS5ut" # 배송파트너 (link)

# 운임단가 fields
FLD_RATE_PARTNER = "fldgc1e6CEmIj6II1"  # 배송파트너 (link)
FLD_RATE_BASE = "fld8UyM9hPOOX6pTU"    # 기본운임
FLD_RATE_PER_CBM = "fldFT8nO6QrXWcJh1" # CBM당_추가운임
FLD_RATE_CBM_MIN = "fld4DQRC3X3JPmRjP"  # CBM_최소
FLD_RATE_CBM_MAX = "fldh6UTE9G3osg2mp"  # CBM_최대
FLD_RATE_VALID_FROM = "fldcN7yDOW91S6YwG"  # 유효시작일
FLD_RATE_VALID_TO = "fldoMTwX2LRHIbaR4"    # 유효종료일

SELF_EMPLOYED_NAMES = {"이장훈", "조희선", "박종성"}
SPILLOVER_WAVES = {"spillover_고고엑스", "spillover_로젠"}
AUTO_WAVES = {"W1", "W2", "W3", "spillover_고고엑스", "spillover_로젠", "locked-in"}

WEIGHTS = {"cost": 0.30, "reliability": 0.35, "capacity": 0.20, "damage": 0.15}


# ── 순수 점수 함수 (unit-testable) ─────────────────────────────────────────

def score_cost(
    total_transport_cost: float,
    total_cbm: float,
    target_rate: Optional[float],
) -> Optional[float]:
    """운임/CBM 실질 단가 vs 운임단가 목표 단가 비교 → 0~100."""
    if target_rate is None:
        return None
    if total_cbm <= 0:
        return None
    actual_rate = total_transport_cost / total_cbm
    return min(100.0, (target_rate / actual_rate) * 100.0)


def score_reliability(on_time_count: int, total_count: int) -> Optional[float]:
    """OTIF On_Time 비율 → 0~100. 레코드 없으면 None."""
    if total_count == 0:
        return None
    return (on_time_count / total_count) * 100.0


def score_capacity(
    shipments: int,
    max_daily: int,
    working_days: int,
    is_self_employed: bool,
    prev_month_count: Optional[int],
) -> float:
    """가동률(자체기사) 또는 처리량 추세(외주) → 0~100."""
    if is_self_employed:
        ceiling = max_daily * working_days
        if ceiling == 0:
            return 50.0
        return min(100.0, (shipments / ceiling) * 100.0)
    else:
        if prev_month_count is None or prev_month_count == 0:
            return 50.0
        return min(100.0, (shipments / prev_month_count) * 50.0)


def score_damage(claim_count: int, shipment_count: int) -> float:
    """클레임 발생률 → 0~100. 0건=100점, 2%=0점."""
    if shipment_count == 0:
        return 100.0
    claim_rate = claim_count / shipment_count
    return max(0.0, 100.0 - claim_rate * 5000.0)


def aggregate_score(
    cost: Optional[float],
    reliability: Optional[float],
    capacity: float,
    damage: float,
) -> float:
    """N/A 축 재정규화 후 가중합."""
    active: dict[str, tuple[Optional[float], float]] = {
        "cost": (cost, WEIGHTS["cost"]),
        "reliability": (reliability, WEIGHTS["reliability"]),
        "capacity": (capacity, WEIGHTS["capacity"]),
        "damage": (damage, WEIGHTS["damage"]),
    }
    total_weight = sum(w for _, (v, w) in active.items() if v is not None)
    if total_weight == 0:
        return 0.0
    weighted_sum = sum(v * w for _, (v, w) in active.items() if v is not None)
    return weighted_sum / total_weight


def working_days_in_month(year: int, month: int) -> int:
    """해당 월의 월~금 영업일 수 (공휴일 미제외)."""
    _, days = calendar.monthrange(year, month)
    return sum(
        1
        for d in range(1, days + 1)
        if datetime.date(year, month, d).weekday() < 5
    )
