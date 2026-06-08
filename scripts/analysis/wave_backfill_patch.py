"""5/1 ~ 6/19 wave 배정 Airtable PATCH 백필.

날짜별 독립 assign_waves → wave_recommendation / wave_confidence /
wave_updated_at / 배송슬롯 PATCH (batch 10).

DRY_RUN=true 로 실행하면 PATCH 없이 예상 결과만 출력.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.parse
from collections import defaultdict
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from harness.dispatch.region_classifier import classify_region
from harness.dispatch.resource_loader import load_partners
from harness.dispatch.slot_decider import decide_slot
from harness.dispatch.wave_assigner import WAVE_IDS, Shipment, WavePlan, assign_waves, compute_utilization

BASE_ID      = "app4x70a8mOrIKsMf"
SHIP_TABLE   = "tbllg1JoHclGYer7m"

FLD_PROJECT  = "fldTs3FzaSdGYEiKX"
FLD_METHOD   = "flduzH5tS7orqGG3o"
FLD_SLOT     = "fldcSrlxCngYQHtSV"
FLD_ADDRESS  = "fldyJHUh9gN44Ggnh"
FLD_HOPE     = "fldFweNu3dASPv93N"
FLD_PARTNER  = "fldHZ7yMT3KEu2gSj"
FLD_STATUS   = "fldOhibgxg6LIpRTi"
FLD_SHIP_DATE= "fldQvmEwwzvQW95h9"
FLD_TOTAL_CBM= "fldJ9DHjwoRyeUEqE"
FLD_EST_CBM  = "fldaP8D9AM8CHEZ2o"
FLD_EST_CONF = "fldUnFZ2ayjJbMW4I"
FLD_LOCKED   = "fldfY2d54mffSHBEA"
FLD_WAVE_REC = "fld9hlDfnTS4frfR4"
FLD_WAVE_CONF= "fldkjKK1Fk1xsXj9Q"
FLD_WAVE_UPD = "fld9YtjtpiOiZHJKu"

START = "2026-05-01"
END   = "2026-06-19"
DRY_RUN = os.environ.get("DRY_RUN", "false").lower() in {"true", "1", "yes"}
KST = timezone(timedelta(hours=9))


def _headers():
    pat = os.environ.get("AIRTABLE_PAT", "")
    if not pat:
        sys.exit("ERROR: AIRTABLE_PAT not set")
    return {"Authorization": f"Bearer {pat}", "Content-Type": "application/json"}


def _get(url, params):
    qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    req = urllib.request.Request(f"{url}?{qs}", headers=_headers())
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _patch_batch(records: list[dict]) -> None:
    if DRY_RUN:
        for r in records:
            print(f"  [DRY] {r['id']} → {r['fields']}")
        return
    url = f"https://api.airtable.com/v0/{BASE_ID}/{SHIP_TABLE}"
    data = json.dumps({"records": records}, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=data, headers=_headers(), method="PATCH")
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()
    time.sleep(0.22)  # Airtable rate limit


def _first(val):
    if isinstance(val, list):
        return val[0] if val else None
    return val


def fetch_all() -> list[dict]:
    formula = (
        "AND("
        f"NOT({{{FLD_PROJECT}}}=''),"
        f"NOT({{{FLD_STATUS}}}='발송완료'),"
        f"NOT({{{FLD_STATUS}}}='취소'),"
        f"NOT({{{FLD_STATUS}}}='반품'),"
        f"NOT({{{FLD_STATUS}}}='회수'),"
        f"NOT({{{FLD_STATUS}}}='배달완료'),"
        f"{{{FLD_SHIP_DATE}}}!=''"
        ")"
    )
    url = f"https://api.airtable.com/v0/{BASE_ID}/{SHIP_TABLE}"
    recs, offset = [], None
    while True:
        params = {"pageSize": 100, "filterByFormula": formula, "returnFieldsByFieldId": "true"}
        if offset:
            params["offset"] = offset
        data = _get(url, params)
        recs.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return [r for r in recs if START <= (_first(r["fields"].get(FLD_SHIP_DATE)) or "")[:10] <= END]


def build(rec: dict):
    f = rec["fields"]
    locked = bool(f.get(FLD_LOCKED))
    project = _first(f.get(FLD_PROJECT)) or ""
    method   = _first(f.get(FLD_METHOD)) or ""
    hope     = _first(f.get(FLD_HOPE)) or ""
    address  = _first(f.get(FLD_ADDRESS)) or ""
    partner  = _first(f.get(FLD_PARTNER)) or ""
    total    = f.get(FLD_TOTAL_CBM) or 0.0
    est      = f.get(FLD_EST_CBM) or 0.0
    conf     = f.get(FLD_EST_CONF) or 0.0
    cbm, cbm_conf = (float(total), 1.0) if total else ((float(est), float(conf) or 0.7) if est else (0.5, 0.3))
    slot, slot_conf = decide_slot(method, hope)
    region = classify_region(address)
    raw_date = _first(f.get(FLD_SHIP_DATE)) or ""
    ship_date = raw_date[:10]
    return Shipment(
        id=rec["id"], project_code=project,
        slot=slot, region=region, cbm=cbm,
        cbm_confidence=cbm_conf, slot_confidence=slot_conf,
        assigned_partner=partner, wave_locked=locked,
    ), ship_date


def main():
    mode = "DRY_RUN" if DRY_RUN else "LIVE"
    print(f"[wave 백필 PATCH] {START} ~ {END}  {mode}")

    partners = load_partners()
    partner_autonomy = {p.get("배송파트너", ""): p.get("autonomy_level", "unknown")
                        for p in partners if p.get("배송파트너")}

    print("  Airtable 조회 중...")
    records = fetch_all()
    print(f"  {len(records)}건 조회")

    # 날짜별 grouping
    date_to = defaultdict(list)   # ship_date → [(Shipment, record_id)]
    for rec in records:
        s, ship_date = build(rec)
        date_to[ship_date].append((s, rec["id"]))

    now_iso = datetime.now(KST).isoformat()

    # 집계
    grand = defaultdict(int)
    total_patch = 0

    print()
    header = f"{'날짜':<12} {'W1':>4} {'W2':>4} {'W3':>4} {'로젠':>5} {'수동':>4} {'합계':>5}"
    print(header)
    print("-" * len(header))

    patch_queue: list[dict] = []

    for ship_date in sorted(date_to):
        pairs = date_to[ship_date]
        shipments = [s for s, _ in pairs]
        id_map = {s.id: rid for s, rid in pairs}

        plans = assign_waves(shipments, partner_autonomy, ship_date)

        # wave → record_id 역매핑
        wave_of: dict[str, str] = {}
        slot_of: dict[str, str | None] = {}
        for wid, plan in plans.items():
            for s in plan.shipments:
                wave_of[s.id] = wid
                slot_of[s.id] = s.slot

        for s, rid in pairs:
            wid = wave_of.get(s.id)
            if wid is None:
                continue  # autonomous — skip
            fields = {
                FLD_WAVE_REC: wid,
                FLD_WAVE_CONF: round(s.slot_confidence * s.cbm_confidence, 2),
                FLD_WAVE_UPD: now_iso,
            }
            if slot_of.get(s.id):
                fields[FLD_SLOT] = slot_of[s.id]
            patch_queue.append({"id": rid, "fields": fields})

        row_counts = {wid: plans[wid].count for wid in WAVE_IDS}
        for wid in WAVE_IDS:
            grand[wid] += row_counts[wid]

        print(
            f"{ship_date:<12} "
            f"{row_counts['W1']:>4} "
            f"{row_counts['W2']:>4} "
            f"{row_counts['W3']:>4} "
            f"{row_counts['spillover_로젠']:>5} "
            f"{row_counts['수동']:>4} "
            f"{sum(row_counts.values()):>5}"
        )

    print("-" * len(header))
    total_all = sum(grand.values())
    auto = grand["W1"] + grand["W2"] + grand["W3"]
    print(
        f"{'합계':<12} "
        f"{grand['W1']:>4} "
        f"{grand['W2']:>4} "
        f"{grand['W3']:>4} "
        f"{grand['spillover_로젠']:>5} "
        f"{grand['수동']:>4} "
        f"{total_all:>5}"
    )
    print(f"\n  자동화율: {auto}/{total_all} ({auto/total_all*100:.0f}%)" if total_all else "")
    print(f"  PATCH 대상: {len(patch_queue)}건")

    # Airtable PATCH (batch 10)
    if not DRY_RUN:
        print(f"\n  Airtable PATCH 시작...")
        for i in range(0, len(patch_queue), 10):
            batch = patch_queue[i:i+10]
            _patch_batch(batch)
            total_patch += len(batch)
            print(f"  {total_patch}/{len(patch_queue)} 완료", end="\r")
        print(f"\n  PATCH 완료: {total_patch}건")
    else:
        print(f"\n  DRY_RUN — 실제 PATCH 없음")


if __name__ == "__main__":
    main()
