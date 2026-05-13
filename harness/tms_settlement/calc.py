"""
Pure fare calculation functions — no I/O, no Airtable calls.

SettlementItem.fare_gross is the base fare before withholding.
withholding is 0 until T0-1 (tax accountant sign-off) is resolved.
fare_net == fare_gross while WITHHOLDING_RATE == 0.0.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from harness._core.geo import estimate_dest_coord, haversine_km
from harness.tms_settlement.config import (
    DRIVER_NAME,
    DRIVER_PARK,
    F_BOX_QTY,
    F_BOX_QTY_DIRECT,
    F_BOX_TEXT,
    F_DATE,
    F_DEST_ADDR,
    F_FARE,
    F_ITEMS_MFG,
    F_ORIGIN_ADDR,
    F_PARTNER,
    F_PRODUCT_FINAL,
    F_PROJECT_CODE,
    F_REQUEST_NOTE,
    F_SC_ID,
    ORIGINS,
    WITHHOLDING_RATE,
    rates_for,
    round_up_500,
)


@dataclass(kw_only=True, frozen=True)
class SettlementItem:
    rec_id: str
    sc_id: str
    date: str           # YYYY-MM-DD
    driver_id: str      # Airtable record ID (배송파트너 table)
    driver_name: str    # 이장훈 / 조희선 / 박종성
    fare_gross: int     # calculated fare before withholding
    withholding: int    # 원천세 — 0 until T0-1 resolved
    fare_net: int       # fare_gross - withholding
    unload_calc: int    # 상하차비용 (박종성 only)
    fare_existing: int  # current Airtable value (0 if empty)
    note: str
    no_coord: bool = False  # True → NO_COORD: must not PATCH fare


def _str_field(raw: object) -> str:
    if isinstance(raw, list):
        return str(raw[0] or "").strip() if raw else ""
    return str(raw or "").strip()


def _apply_withholding(gross: int) -> tuple[int, int, int]:
    """Return (gross, withholding, net). withholding=0 until T0-1 is resolved."""
    withholding = round(gross * WITHHOLDING_RATE)
    return gross, withholding, gross - withholding


def _parse_unload_fee(box_text: object) -> int:
    """Parse box counts from formula string → 상하차비용, capped at 50,000 KRW."""
    if not box_text:
        return 0
    s = str(box_text)
    try:
        heavy  = int(re.search(r"중대(\d+)", s).group(1)) if re.search(r"중대(\d+)", s) else 0
        large  = int(re.search(r"(?<!중)(?<!특)대(\d+)", s).group(1)) if re.search(r"(?<!중)(?<!특)대(\d+)", s) else 0
        xlarge = int(re.search(r"특대(\d+)", s).group(1)) if re.search(r"특대(\d+)", s) else 0
        return min((heavy // 5) * 5_000 + (large // 3) * 5_000 + (xlarge // 3) * 5_000, 50_000)
    except Exception:
        return 0


def _is_outsource(rec: dict) -> bool:
    """MM 외주임가공 → 다영기획 배송 여부.

    SC id starts with 'MM' + destination contains '다영기획' + request note contains '외주임가공'.
    """
    sc_id = rec["fields"].get(F_SC_ID, "") or ""
    dest  = _str_field(rec["fields"].get(F_DEST_ADDR))
    note  = _str_field(rec["fields"].get(F_REQUEST_NOTE))
    return sc_id.startswith("MM") and "다영기획" in dest and "외주임가공" in note


def _is_pna(rec: dict) -> bool:
    """PNA 프로젝트 고객납품건 — project code contains 'PNA'."""
    code = _str_field(rec["fields"].get(F_PROJECT_CODE))
    return "PNA" in code.upper()


def _make_item(
    rec: dict,
    driver_id: str,
    fare_gross: int,
    unload_calc: int,
    note: str,
    *,
    no_coord: bool = False,
) -> SettlementItem:
    gross, withholding, net = _apply_withholding(fare_gross)
    return SettlementItem(
        rec_id=rec["id"],
        sc_id=_str_field(rec["fields"].get(F_SC_ID)),
        date=rec["fields"].get(F_DATE, ""),
        driver_id=driver_id,
        driver_name=DRIVER_NAME.get(driver_id, driver_id),
        fare_gross=gross,
        withholding=withholding,
        fare_net=net,
        unload_calc=unload_calc,
        fare_existing=rec["fields"].get(F_FARE) or 0,
        note=note,
        no_coord=no_coord,
    )


# ── Driver calc functions ─────────────────────────────────────────────────────

def calc_lee(recs: list[dict], driver_id: str) -> list[SettlementItem]:
    """이장훈: 160,000원/day ÷ 당일 배송건수 (ceiling to 500 KRW)."""
    daily: defaultdict[str, list[dict]] = defaultdict(list)
    for rec in recs:
        daily[rec["fields"].get(F_DATE, "")].append(rec)

    results = []
    for d, day_recs in sorted(daily.items()):
        rates = rates_for(d)
        n = len(day_recs)
        per_ship = round_up_500(rates["lee_daily"] / n)
        for rec in day_recs:
            results.append(_make_item(
                rec, driver_id, per_ship, 0,
                f"{rates['lee_daily']:,}/{n}건",
            ))
    return results


def calc_cho(recs: list[dict], driver_id: str) -> list[SettlementItem]:
    """조희선: (360,000 + max(0, 경기도건수-1)×30,000) / 당일 배송건수."""
    daily: defaultdict[str, list[dict]] = defaultdict(list)
    for rec in recs:
        daily[rec["fields"].get(F_DATE, "")].append(rec)

    results = []
    for d, day_recs in sorted(daily.items()):
        rates = rates_for(d)
        gyeonggi = sum(
            1 for rec in day_recs
            if "경기" in _str_field(rec["fields"].get(F_DEST_ADDR))
        )
        surcharge   = max(0, gyeonggi - 1) * rates["cho_gyeonggi_surcharge"]
        daily_total = rates["cho_base"] + surcharge
        n           = len(day_recs)
        per_ship    = round_up_500(daily_total / n)
        for rec in day_recs:
            results.append(_make_item(
                rec, driver_id, per_ship, 0,
                f"({rates['cho_base']:,}+{surcharge:,}={daily_total:,})/{n}건  경기={gyeonggi}",
            ))
    return results


def calc_park(
    recs: list[dict],
    driver_id: str,
    product_lookup: dict | None = None,
) -> list[SettlementItem]:
    """박종성:
      일반건: haversine × road_factor × park_km + park_base (ceiling 500)
              상하차비: F_BOX_TEXT → PNA fallback → CBM 룩업 fallback
      외주임가공건: outsource_daily / 당일 해당 건수
    """
    outsource = [r for r in recs if _is_outsource(r)]
    normal    = [r for r in recs if not _is_outsource(r)]

    results: list[SettlementItem] = []

    # ── 외주임가공 케이스 ─────────────────────────────────────────────────────
    outsource_by_date: defaultdict[str, list[dict]] = defaultdict(list)
    for rec in outsource:
        outsource_by_date[rec["fields"].get(F_DATE, "")].append(rec)

    for d, day_recs in sorted(outsource_by_date.items()):
        rates    = rates_for(d)
        n        = len(day_recs)
        per_ship = round_up_500(rates["outsource_daily"] / n)
        for rec in day_recs:
            results.append(_make_item(
                rec, driver_id, per_ship, 0,
                f"MM외주임가공{rates['outsource_daily']//1000}k/{n}건",
            ))

    # ── 일반 케이스 ──────────────────────────────────────────────────────────
    for rec in normal:
        d           = rec["fields"].get(F_DATE, "")
        rates       = rates_for(d)
        origin_addr = _str_field(rec["fields"].get(F_ORIGIN_ADDR))
        dest_addr   = _str_field(rec["fields"].get(F_DEST_ADDR))

        # Box text for unload fee (3-level fallback)
        box_text = rec["fields"].get(F_BOX_TEXT, "") or ""
        if not box_text and _is_pna(rec):
            box_text = (
                _str_field(rec["fields"].get(F_BOX_QTY_DIRECT))
                or _str_field(rec["fields"].get(F_BOX_QTY))
                or ""
            )

        cbm_unload = 0
        if not box_text and product_lookup:
            items_text = (
                _str_field(rec["fields"].get(F_ITEMS_MFG))
                or _str_field(rec["fields"].get(F_PRODUCT_FINAL))
            )
            if items_text:
                try:
                    from harness.settlement.cbm_calc import calc_from_products
                    cbm_unload = calc_from_products(items_text, product_lookup)["unload_fee"]
                except Exception:
                    pass

        # Origin coord selection
        if "성남시" in origin_addr or "다영" in origin_addr:
            origin_coord = ORIGINS["다영기획"]
        else:
            origin_coord = ORIGINS["에이원지식산업센터"]

        dest_coord = estimate_dest_coord(dest_addr)

        if dest_coord is None:
            results.append(_make_item(
                rec, driver_id, 0, 0,
                f"NO_COORD: {dest_addr[:40]}",
                no_coord=True,
            ))
            continue

        hav     = haversine_km(origin_coord[0], origin_coord[1], dest_coord[0], dest_coord[1])
        road_km = hav * rates["park_road_factor"]
        fare    = round_up_500(rates["park_base"] + rates["park_km"] * road_km)
        unload  = _parse_unload_fee(box_text) or cbm_unload

        note = f"{road_km:.1f}km ({rates['park_base']}+{rates['park_km']}×{road_km:.1f})"
        existing = rec["fields"].get(F_FARE) or 0
        if existing:
            delta = abs(fare - existing) / existing
            if delta > rates["park_tolerance"]:
                note += f"  [FLAG >{rates['park_tolerance']*100:.0f}%: calc={fare:,} existing={existing:,}]"

        results.append(_make_item(rec, driver_id, fare, unload, note))

    return results
