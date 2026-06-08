"""특정 날짜 wave 배정 상세 디버그."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.parse
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from harness.dispatch.region_classifier import classify_region
from harness.dispatch.resource_loader import load_partners
from harness.dispatch.slot_decider import decide_slot
from harness.dispatch.wave_assigner import WAVE_IDS, Shipment, WavePlan, assign_waves, DRIVER_LIMITS

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
FLD_SC_ID        = "fldBUwhBlhOMsJZdv"

DEBUG_DATES = {"2026-05-04", "2026-05-26", "2026-06-04", "2026-06-15"}


def _headers():
    pat = os.environ.get("AIRTABLE_PAT", "")
    if not pat:
        sys.exit("ERROR: AIRTABLE_PAT not set")
    return {"Authorization": f"Bearer {pat}", "Content-Type": "application/json"}


def _get(url, params):
    qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    full = f"{url}?{qs}" if qs else url
    req = urllib.request.Request(full, headers=_headers())
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _first(val):
    if isinstance(val, list):
        return val[0] if val else None
    return val


def fetch_dates(dates: set) -> dict[str, list[dict]]:
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
    all_recs, offset = [], None
    while True:
        params = {"pageSize": 100, "filterByFormula": formula, "returnFieldsByFieldId": "true"}
        if offset:
            params["offset"] = offset
        data = _get(url, params)
        all_recs.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break

    result: dict[str, list[dict]] = defaultdict(list)
    for rec in all_recs:
        f = rec.get("fields", {})
        raw = _first(f.get(FLD_SHIP_DATE)) or f.get(FLD_SHIP_DATE) or ""
        ship_date = raw[:10]
        if ship_date in dates:
            result[ship_date].append(rec)
    return result


def build_shipment(rec):
    f = rec.get("fields", {})
    wave_locked = bool(f.get(FLD_WAVE_LOCKED))
    project_code = _first(f.get(FLD_PROJECT_CODE)) or ""
    sc_id   = _first(f.get(FLD_SC_ID)) or rec.get("id", "")
    method  = _first(f.get(FLD_METHOD)) or ""
    hope_time = _first(f.get(FLD_HOPE_TIME)) or ""
    address = _first(f.get(FLD_ADDRESS)) or ""
    partner = _first(f.get(FLD_PARTNER)) or ""
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
    return Shipment(
        id=rec.get("id", ""),
        project_code=project_code,
        slot=slot,
        region=region,
        cbm=cbm,
        cbm_confidence=cbm_conf,
        slot_confidence=slot_conf,
        assigned_partner=partner,
        wave_locked=wave_locked,
    ), sc_id, slot, region, address, wave_locked


def main():
    partners = load_partners()
    partner_autonomy = {
        p.get("배송파트너", ""): p.get("autonomy_level", "unknown")
        for p in partners if p.get("배송파트너")
    }

    print("조회 중...")
    date_recs = fetch_dates(DEBUG_DATES)

    for ship_date in sorted(DEBUG_DATES):
        recs = date_recs.get(ship_date, [])
        print(f"\n{'='*60}")
        print(f"  {ship_date} — {len(recs)}건")
        print(f"{'='*60}")

        shipments = []
        meta = {}  # id → (sc_id, slot, region, address, wave_locked)
        for rec in recs:
            s, sc_id, slot, region, address, wave_locked = build_shipment(rec)
            shipments.append(s)
            meta[s.id] = (sc_id, slot, region, address, wave_locked)

        # 원시 데이터 출력
        print(f"  {'SC_ID':<20} {'slot':<30} {'region':<24} {'cbm':>6} {'locked'}")
        print(f"  {'-'*20} {'-'*30} {'-'*24} {'-'*6} {'-'*6}")
        for s in shipments:
            sc_id, slot, region, address, locked = meta[s.id]
            lock_mark = "LOCKED" if locked else ""
            print(f"  {sc_id:<20} {str(slot):<30} {region:<24} {s.cbm:>6.2f} {lock_mark}")

        # wave 배정 결과
        plans = assign_waves(shipments, partner_autonomy, ship_date)
        print(f"\n  [Wave 배정 결과]")
        for wid in ("W1", "W2", "W3", "spillover_로젠", "spillover_고고엑스", "수동"):
            plan = plans[wid]
            if plan.count == 0:
                continue
            lim = DRIVER_LIMITS.get(wid, {})
            name = lim.get("name", wid)
            max_cbm = lim.get("max_cbm", "-")
            print(f"  {wid}({name}): {plan.count}건 / {plan.total_cbm:.2f}m³  (한도: {max_cbm}m³)")
            for s in plan.shipments:
                sc_id, slot, region, address, _ = meta[s.id]
                print(f"    - {sc_id:<20} slot={str(slot):<28} region={region:<22} cbm={s.cbm:.2f}")

        assigned = sum(plans[w].count for w in ("W1","W2","W3","spillover_로젠","spillover_고고엑스","수동","locked-in"))
        print(f"\n  총 배정: {assigned}/{len(shipments)}")
        unassigned = len(shipments) - assigned
        if unassigned:
            print(f"  ⚠️  미배정: {unassigned}건 (원인 확인 필요)")


if __name__ == "__main__":
    main()
