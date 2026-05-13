from __future__ import annotations

import math
import os
from datetime import date
from typing import ClassVar

from harness._core.config import ConfigBase

DOMAIN = "tms_settlement"

# ── Airtable identifiers ──────────────────────────────────────────────────────
TMS_BASE = "app4x70a8mOrIKsMf"
SHIPMENT_TABLE = "tbllg1JoHclGYer7m"

# Airtable View pre-filtered to "배송파트너 is not empty".
# Fetch the view ID from Airtable UI: Table → Views panel → copy "viw..." ID.
# Set as env var SETTLEMENT_VIEW_ID, or hard-code below after confirming.
SHIPMENT_VIEW: str | None = None  # TODO: fill in after fetching from Airtable UI

# ── Field IDs (Shipment table) ────────────────────────────────────────────────
F_SC_ID          = "fldBUwhBlhOMsJZdv"
F_DATE           = "fldQvmEwwzvQW95h9"   # 출하확정일
F_PARTNER        = "fldM2u6RwLRrO7ymW"   # 배송파트너 (multipleRecordLinks)
F_FARE           = "fldRT95SC88KSBATT"   # 운송비용
F_UNLOAD         = "fldxmAZrBGqS7sQoL"  # 상하차비용
F_ORIGIN_ADDR    = "fldb24I9EQ2KPXv6S"  # 출고지 주소 (rollup)
F_DEST_ADDR      = "fldyJHUh9gN44Ggnh"  # 수령인(주소) (rollup)
F_BOX_TEXT       = "fldTjLDmw5sNGszeD"  # 최종 외박스 수량 값 (formula)
F_BOX_QTY_DIRECT = "fldRjMaXa5TdSsGDL" # 외박스 수량 (직접입력) — PNA fallback
F_BOX_QTY        = "fldGXhlBwI6toXSJC"  # 외박스 수량 (rollup from 배송요청) — PNA fallback
F_PROJECT_CODE   = "fldTs3FzaSdGYEiKX"  # project code (rollup) — PNA 식별용
F_REQUEST_NOTE   = "fldHQdGWe8jNrNYEM"  # 배송 요청사항 (rollup)
F_ITEMS_MFG      = "fldCnwsVrpkKHt4Hl"  # 임가공 품목 및 수량 (rollup) — CBM 계산용
F_PRODUCT_FINAL  = "fldgSupj5XLjJXYQo"  # 최종 출하 품목 (formula) — CBM fallback

SETTLEMENT_FIELDS: list[str] = [
    F_SC_ID, F_DATE, F_PARTNER, F_FARE, F_UNLOAD,
    F_ORIGIN_ADDR, F_DEST_ADDR, F_BOX_TEXT,
    F_BOX_QTY_DIRECT, F_BOX_QTY, F_PROJECT_CODE,
    F_REQUEST_NOTE, F_ITEMS_MFG, F_PRODUCT_FINAL,
]

# ── Driver record IDs (배송파트너 table) ────────────────────────────────────────
DRIVER_LEE  = "recyVExCkk2Lty0E9"   # 신시어리 이장훈
DRIVER_CHO  = "recPkgE4o3cs0krnR"   # 신시어리 조희선
DRIVER_PARK = "recXCfwVTqaoeQ9SS"   # 신시어리 박종성

KNOWN_DRIVERS: frozenset[str] = frozenset({DRIVER_LEE, DRIVER_CHO, DRIVER_PARK})

DRIVER_NAME: dict[str, str] = {
    DRIVER_LEE:  "이장훈",
    DRIVER_CHO:  "조희선",
    DRIVER_PARK: "박종성",
}

# ── Origin coordinates for 박종성 fare calc ──────────────────────────────────
ORIGINS: dict[str, tuple[float, float]] = {
    "에이원지식산업센터": (37.5477, 127.0446),
    "다영기획":          (37.4360, 127.1436),
}

# ── Fare rate history (date-versioned, newest first) ─────────────────────────
# Invariant: never delete old entries — they are the audit trail.
# To change rates: prepend a new dict with today's date as effective_from.
RATE_HISTORY: list[dict] = [
    {
        "effective_from":        "2026-01-01",
        "lee_daily":              160_000,   # 이장훈 일일 정액
        "cho_base":               360_000,   # 조희선 기본 일일
        "cho_gyeonggi_surcharge":  30_000,   # 경기도 1건 초과당 추가
        "park_base":               55_421,   # 박종성 기본요금
        "park_km":                    831,   # 박종성 km당 요금
        "park_tolerance":            0.30,   # 30% 이상 차이 = FLAG
        "park_road_factor":          1.35,   # haversine → 도로거리 환산 계수
        "outsource_daily":         70_000,   # MM외주임가공 다영기획 일일 고정
    },
]


def rates_for(target_date: str) -> dict:
    """Return the fare rate row effective on `target_date` (YYYY-MM-DD)."""
    d = date.fromisoformat(target_date)
    for row in RATE_HISTORY:
        if d >= date.fromisoformat(row["effective_from"]):
            return row
    raise ValueError(f"No fare rate row covers date {target_date!r}")


def round_up_500(x: float) -> int:
    """Ceiling to nearest 500 KRW."""
    return math.ceil(x / 500) * 500


# ── Verifier thresholds ───────────────────────────────────────────────────────
MAX_BLOCKED_RATIO: float = 0.10  # abort batch if >10% of write-set is blocked

# ── Withholding tax — T0-1 BLOCKER ───────────────────────────────────────────
# 3.3% source withholding applies to individual contractor (기사님) payments.
# DO NOT set to 0.033 until the tax accountant confirms applicability.
# When confirmed: update this value and re-verify calc_* golden tests.
WITHHOLDING_RATE: float = 0.0   # T0-1: pending tax accountant confirmation


class SettlementConfig(ConfigBase):
    REQUIRED_ENV: ClassVar[list[str]] = ["AIRTABLE_PAT"]
    OPTIONAL_ENV: ClassVar[list[str]] = [
        "SLACK_BOT_TOKEN",
        "SLACK_DM_USER_ID",
        "SETTLEMENT_VIEW_ID",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_KEY",
    ]

    @property
    def pat(self) -> str:
        return os.environ["AIRTABLE_PAT"]

    @property
    def view_id(self) -> str | None:
        return os.environ.get("SETTLEMENT_VIEW_ID") or SHIPMENT_VIEW
