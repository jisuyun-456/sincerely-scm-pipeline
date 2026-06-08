"""5/1 ~ 6/19 구간 wave 배정 분석 스크립트.

날짜별 독립 assign_waves 실행 후 콘솔 출력.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.parse
from collections import defaultdict
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from harness.dispatch.region_classifier import classify_region
from harness.dispatch.resource_loader import load_partners
from harness.dispatch.scheduling import rolling_window_end
from harness.dispatch.slot_decider import decide_slot
from harness.dispatch.wave_assigner import WAVE_IDS, Shipment, WavePlan, assign_waves, compute_utilization, DRIVER_LIMITS

BASE_ID = "app4x70a8mOrIKsMf"
SHIPMENT_TABLE = "tbllg1JoHclGYer7m"

FLD_PROJECT_CODE = "fldTs3FzaSdGYEiKX"
FLD_METHOD       = "flduzH5tS7orqGG3o"
FLD_SLOT         = "fldcSrlxCngYQHtSV"
FLD_ADDRESS      = "fldyJHUh9gN44Ggnh"
FLD_HOPE_TIME    = "fldFweNu3dASPv93N"
FLD_PARTNER      = "fldHZ7yMT3KEu2gSj"
FLD_STATUS       = "fldOhibgxg6LIpRTi"
FLD_SHIP_DATE    = "fldQvmEwwzvQW95h9"
FLD_TOTAL_CBM    = "fldJ9DHjwoRyeUEqE"
FLD_EST_CBM      = "fldaP8D9AM8CHEZ2o"
FLD_EST_CONF     = "fldUnFZ2ayjJbMW4I"
FLD_WAVE_LOCKED  = "fldfY2d54mffSHBEA"

SHIPPED_STATUSES = frozenset({"발송완료", "취소", "반품", "회수", "배달완료"})

START_DATE = "2026-05-01"
END_DATE   = "2026-06-19"


def _headers() -> dict:
    pat = os.environ.get("AIRTABLE_PAT", "")
    if not pat:
        sys.exit("ERROR: AIRTABLE_PAT not set")
    return {"Authorization": f"Bearer {pat}", "Content-Type": "application/json"}


def _get(url: str, params: dict) -> dict:
    qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    full = f"{url}?{qs}" if qs else url
    req = urllib.request.Request(full, headers=_headers())
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _first(val):
    if isinstance(val, list):
        return val[0] if val else None
    return val


def fetch_range(start: str, end: str) -> list[dict]:
    formula = (
        "AND("
        f"NOT({{{FLD_PROJECT_CODE}}}=''),"
        f"NOT({{{FLD_STATUS}}}='발송완료'),"
        f"NOT({{{FLD_STATUS}}}='취소'),"
        f"NOT({{{FLD_STATUS}}}='반품'),"
        f"NOT({{{FLD_STATUS}}}='회수'),"
        f"NOT({{{FLD_STATUS}}}='배달완료'),"
        f"{{{FLD_SHIP_DATE}}}!=''"
        ")"
    )
    url = f"https://api.airtable.com/v0/{BASE_ID}/{SHIPMENT_TABLE}"
    records, offset = [], None
    while True:
        params = {"pageSize": 100, "filterByFormula": formula, "returnFieldsByFieldId": "true"}
        if offset:
            params["offset"] = offset
        data = _get(url, params)
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break

    # Python-side date filter
    result = []
    for rec in records:
        f = rec.get("fields", {})
        raw = _first(f.get(FLD_SHIP_DATE)) or f.get(FLD_SHIP_DATE) or ""
        ship_date = raw[:10]
        if start <= ship_date <= end:
            result.append(rec)
    return result


def build_shipment(rec: dict):
    f = rec.get("fields", {})
    if bool(f.get(FLD_WAVE_LOCKED)):
        return None, None
    project_code = _first(f.get(FLD_PROJECT_CODE)) or ""
    method   = _first(f.get(FLD_METHOD)) or ""
    hope_time = _first(f.get(FLD_HOPE_TIME)) or ""
    address  = _first(f.get(FLD_ADDRESS)) or ""
    partner  = _first(f.get(FLD_PARTNER)) or ""
    total_cbm = f.get(FLD_TOTAL_CBM) or 0.0
    est_cbm   = f.get(FLD_EST_CBM) or 0.0
    est_conf  = f.get(FLD_EST_CONF) or 0.0
    if total_cbm and total_cbm > 0:
        cbm, cbm_conf = float(total_cbm), 1.0
    elif est_cbm and est_cbm > 0:
        cbm, cbm_conf = float(est_cbm), float(est_conf) if est_conf else 0.7
    else:
        cbm, cbm_conf = 0.5, 0.3
    slot, slot_conf = decide_slot(method, hope_time)
    region = classify_region(address)
    raw = _first(f.get(FLD_SHIP_DATE)) or f.get(FLD_SHIP_DATE) or ""
    ship_date = raw[:10]
    return Shipment(
        id=rec.get("id", ""),
        project_code=project_code,
        slot=slot,
        region=region,
        cbm=cbm,
        cbm_confidence=cbm_conf,
        slot_confidence=slot_conf,
        assigned_partner=partner,
        wave_locked=False,
    ), ship_date


def main():
    print(f"[wave 분석] {START_DATE} ~ {END_DATE}")
    hdrs = _headers()

    partners = load_partners()
    partner_autonomy = {
        p.get("배송파트너", ""): p.get("autonomy_level", "unknown")
        for p in partners if p.get("배송파트너")
    }

    print("  Airtable 조회 중...")
    records = fetch_range(START_DATE, END_DATE)
    print(f"  총 {len(records)}건 조회")

    # 날짜별 grouping
    date_to_shipments: dict[str, list[Shipment]] = defaultdict(list)
    skipped = 0
    for rec in records:
        s, ship_date = build_shipment(rec)
        if s is None:
            skipped += 1
            continue
        date_to_shipments[ship_date].append(s)

    print(f"  배정 대상: {sum(len(v) for v in date_to_shipments.values())}건 / {len(date_to_shipments)}개 날짜 (wave_locked 제외 {skipped}건)\n")

    # 날짜별 wave 배정
    grand: dict[str, int] = defaultdict(int)
    grand_cbm: dict[str, float] = defaultdict(float)

    header = f"{'날짜':<12} {'W1(이장훈)':<14} {'W2(조희선)':<14} {'W3(박종성)':<14} {'로젠':<6} {'고고엑스':<8} {'수동':<5} {'합계'}"
    print(header)
    print("-" * len(header))

    for ship_date in sorted(date_to_shipments):
        ships = date_to_shipments[ship_date]
        plans = assign_waves(ships, partner_autonomy, ship_date)

        w1 = plans["W1"]
        w2 = plans["W2"]
        w3 = plans["W3"]
        lz = plans["spillover_로젠"]
        gx = plans["spillover_고고엑스"]
        mn = plans["수동"]
        total = sum(plans[w].count for w in WAVE_IDS)

        def fmt(plan, limit_key):
            if plan.count == 0:
                return "-"
            lim = DRIVER_LIMITS.get(limit_key, {})
            max_cbm = lim.get("max_cbm", 0)
            return f"{plan.count}건/{plan.total_cbm:.1f}m³"

        print(
            f"{ship_date:<12} "
            f"{fmt(w1, 'W1'):<14} "
            f"{fmt(w2, 'W2'):<14} "
            f"{fmt(w3, 'W3'):<14} "
            f"{lz.count if lz.count else '-':<6} "
            f"{gx.count if gx.count else '-':<8} "
            f"{mn.count if mn.count else '-':<5} "
            f"{total}건"
        )

        for wid in WAVE_IDS:
            grand[wid] += plans[wid].count
            grand_cbm[wid] += plans[wid].total_cbm

    print("-" * len(header))
    total_all = sum(grand.values())
    auto = grand["W1"] + grand["W2"] + grand["W3"]
    print(
        f"{'합계':<12} "
        f"{grand['W1']}건/{grand_cbm['W1']:.1f}m³    "
        f"{grand['W2']}건/{grand_cbm['W2']:.1f}m³    "
        f"{grand['W3']}건/{grand_cbm['W3']:.1f}m³    "
        f"{grand['spillover_로젠']:<6} "
        f"{grand['spillover_고고엑스']:<8} "
        f"{grand['수동']:<5} "
        f"{total_all}건"
    )
    print(f"\n  자동화율(기사 배정): {auto}/{total_all} ({auto/total_all*100:.0f}%)" if total_all else "")
    print(f"  로젠 spillover: {grand['spillover_로젠']}건 ({grand['spillover_로젠']/total_all*100:.0f}%)" if total_all else "")


if __name__ == "__main__":
    main()
