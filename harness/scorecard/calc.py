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


# ── Airtable fetch helpers ──────────────────────────────────────────────────

def _airtable_headers() -> dict:
    pat = os.environ.get("AIRTABLE_PAT") or os.environ.get("AIRTABLE_API_KEY")
    if not pat:
        raise EnvironmentError("AIRTABLE_PAT 환경변수 필요")
    return {"Authorization": f"Bearer {pat}"}


def _fetch_all(url: str, headers: dict, params: dict | None = None) -> list[dict]:
    """페이지네이션 처리해 전체 레코드 반환."""
    records: list[dict] = []
    offset = None
    while True:
        p = dict(params or {})
        if offset:
            p["offset"] = offset
        resp = requests.get(url, headers=headers, params=p, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return records


def fetch_partners(headers: dict) -> list[dict]:
    """배송파트너 전원 조회 (name, max_daily_orders, autonomy_level)."""
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_PARTNER}"
    return _fetch_all(url, headers, {
        "fields[]": [FLD_P_NAME, FLD_P_MAX_DAILY, FLD_P_AUTONOMY],
    })


def fetch_prev_month_shipments(headers: dict, year: int, month: int) -> list[dict]:
    """전월 출하확정일 기준 Shipment 조회."""
    import calendar as _cal
    _, last_day = _cal.monthrange(year, month)
    formula = (
        f"AND("
        f"IS_AFTER({{출하확정일}}, '{datetime.date(year, month, 1) - datetime.timedelta(days=1)}'),"
        f"IS_BEFORE({{출하확정일}}, '{datetime.date(year, month, last_day) + datetime.timedelta(days=1)}')"
        f")"
    )
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_SHIP}"
    return _fetch_all(url, headers, {
        "filterByFormula": formula,
        "fields[]": [
            FLD_SHIP_DATE, FLD_EST_CBM, FLD_WAVE_REC,
            FLD_TRANSPORT_COST, FLD_PARTNER_LINK, FLD_STATUS,
        ],
    })


def fetch_otif_all(headers: dict) -> list[dict]:
    """OTIF 테이블 전체 조회 (Shipment 링크 + On_Time 필드만)."""
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_OTIF}"
    return _fetch_all(url, headers, {
        "fields[]": [FLD_OTIF_SHIP, FLD_ON_TIME],
    })


def fetch_prev_month_claims(headers: dict, year: int, month: int) -> list[dict]:
    """전월 발생일 기준 배송클레임 조회."""
    import calendar as _cal
    _, last_day = _cal.monthrange(year, month)
    formula = (
        f"AND("
        f"IS_AFTER({{발생일}}, '{datetime.date(year, month, 1) - datetime.timedelta(days=1)}'),"
        f"IS_BEFORE({{발생일}}, '{datetime.date(year, month, last_day) + datetime.timedelta(days=1)}')"
        f")"
    )
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_CLAIM}"
    return _fetch_all(url, headers, {
        "filterByFormula": formula,
        "fields[]": [FLD_CLAIM_DATE, FLD_CLAIM_PARTNER],
    })


def fetch_rate_card(headers: dict) -> dict[str, float]:
    """운임단가 테이블 → {partner_record_id: target_rate(₩/CBM)}.

    target_rate = 기본운임 / ((CBM_최소+CBM_최대)/2) + CBM당_추가운임.
    동일 파트너 여러 행 존재 시 마지막 유효 단가 사용.
    """
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_RATE}"
    rows = _fetch_all(url, headers, {
        "fields[]": [FLD_RATE_PARTNER, FLD_RATE_BASE, FLD_RATE_PER_CBM,
                     FLD_RATE_CBM_MIN, FLD_RATE_CBM_MAX],
    })
    rate_map: dict[str, float] = {}
    for row in rows:
        f = row.get("fields", {})
        partner_ids: list[str] = f.get(FLD_RATE_PARTNER, [])
        base = float(f.get(FLD_RATE_BASE) or 0)
        per_cbm = float(f.get(FLD_RATE_PER_CBM) or 0)
        cbm_min = float(f.get(FLD_RATE_CBM_MIN) or 1)
        cbm_max = float(f.get(FLD_RATE_CBM_MAX) or 1)
        mid_cbm = (cbm_min + cbm_max) / 2 if cbm_max > 0 else 1
        target = (base / mid_cbm) + per_cbm if mid_cbm > 0 else per_cbm
        for pid in partner_ids:
            rate_map[pid] = target
    return rate_map


def calc_all_carriers(
    year: int,
    month: int,
    prev_month_counts: dict[str, int] | None = None,
) -> tuple[list, list[dict]]:
    """전체 carrier 점수 계산. (list[CarrierScore], list[dict] shipments_for_kpi) 반환."""
    from harness.scorecard import CarrierScore

    headers = _airtable_headers()
    partners = fetch_partners(headers)
    shipments = fetch_prev_month_shipments(headers, year, month)
    otif_all = fetch_otif_all(headers)
    claims = fetch_prev_month_claims(headers, year, month)
    rate_card = fetch_rate_card(headers)
    wdays = working_days_in_month(year, month)

    # 인덱스: shipment_id → partner_id
    ship_to_partner: dict[str, str] = {}
    for rec in shipments:
        f = rec.get("fields", {})
        partner_links: list[str] = f.get(FLD_PARTNER_LINK, [])
        if partner_links:
            ship_to_partner[rec["id"]] = partner_links[0]

    # 인덱스: partner_id → On_Time 건수
    partner_otif_total: dict[str, int] = {}
    partner_otif_on_time: dict[str, int] = {}
    for otif in otif_all:
        f = otif.get("fields", {})
        ship_links: list[str] = f.get(FLD_OTIF_SHIP, [])
        on_time = int(f.get(FLD_ON_TIME) or 0)
        for sid in ship_links:
            pid = ship_to_partner.get(sid)
            if pid:
                partner_otif_total[pid] = partner_otif_total.get(pid, 0) + 1
                partner_otif_on_time[pid] = partner_otif_on_time.get(pid, 0) + on_time

    # 인덱스: partner_id → claim 건수
    partner_claims: dict[str, int] = {}
    for claim in claims:
        f = claim.get("fields", {})
        for pid in f.get(FLD_CLAIM_PARTNER, []):
            partner_claims[pid] = partner_claims.get(pid, 0) + 1

    # 인덱스: partner_id → shipment 건수·총운임·총CBM
    partner_ship_count: dict[str, int] = {}
    partner_cost: dict[str, float] = {}
    partner_cbm: dict[str, float] = {}
    for rec in shipments:
        f = rec.get("fields", {})
        plinks: list[str] = f.get(FLD_PARTNER_LINK, [])
        if not plinks:
            continue
        pid = plinks[0]
        partner_ship_count[pid] = partner_ship_count.get(pid, 0) + 1
        try:
            partner_cost[pid] = partner_cost.get(pid, 0.0) + float(f.get(FLD_TRANSPORT_COST) or 0)
        except (ValueError, TypeError):
            partner_cost[pid] = partner_cost.get(pid, 0.0)
        try:
            partner_cbm[pid] = partner_cbm.get(pid, 0.0) + float(f.get(FLD_EST_CBM) or 0)
        except (ValueError, TypeError):
            partner_cbm[pid] = partner_cbm.get(pid, 0.0)

    scores: list[CarrierScore] = []
    for p in partners:
        pid = p["id"]
        f = p.get("fields", {})
        name = f.get(FLD_P_NAME, pid)
        is_self = name in SELF_EMPLOYED_NAMES
        try:
            max_daily = int(f.get(FLD_P_MAX_DAILY) or 0)
        except (ValueError, TypeError):
            max_daily = 0
        ship_count = partner_ship_count.get(pid, 0)

        cost_score = score_cost(
            partner_cost.get(pid, 0.0),
            partner_cbm.get(pid, 0.0),
            rate_card.get(pid),
        )
        rel_score = score_reliability(
            partner_otif_on_time.get(pid, 0),
            partner_otif_total.get(pid, 0),
        )
        cap_score = score_capacity(
            ship_count, max_daily, wdays, is_self,
            (prev_month_counts or {}).get(name),
        )
        dmg_score = score_damage(partner_claims.get(pid, 0), ship_count)
        total = aggregate_score(cost_score, rel_score, cap_score, dmg_score)

        scores.append(CarrierScore(
            carrier_id=pid,
            carrier_name=name,
            cost=cost_score,
            reliability=rel_score,
            capacity=cap_score,
            damage=dmg_score,
            total=total,
            shipment_count=ship_count,
        ))

    return scores, shipments
