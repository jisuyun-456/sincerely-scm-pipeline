"""Sub-Spec 2 polling job (Task 7).

KST 09/14/17 cron entry — re-estimates CBM for active shipments and PATCHes
3 Shipment fields (estimated_cbm, estimation_confidence, estimation_updated_at).

Active filter: 출하확정일 BETWEEN today AND today+7 (대상 자동화 7-day rolling).
Total_CBM transition detection via state/cbm_last_snapshot.json.

CLI:
  python scripts/dispatch/run_cbm_polling.py [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
load_dotenv()

from harness.dispatch.audit import log_anomaly, log_transition
from harness.dispatch.cbm_estimator import estimate_shipment_cbm
from harness.dispatch.product_loader import load as load_product_cache

TMS_BASE = "app4x70a8mOrIKsMf"
TBL_SHIP = "tbllg1JoHclGYer7m"

# Read fields
FLD_FINAL_OUT_TEXT = "fldgSupj5XLjJXYQo"  # 최종 출하 품목
FLD_FINAL_POST_TEXT = "fldXXnGOXkm90snKn"  # 최종 출고 품목 및 수량
FLD_TOTAL_CBM = "fldJ9DHjwoRyeUEqE"
FLD_CONFIRM_DATE = "fldQvmEwwzvQW95h9"
FLD_SC_ID = "fldBUwhBlhOMsJZdv"
FLD_PROJECT = "fldZel4trYQwP7EV5"

# Write fields (created in Task 1)
FLD_EST_CBM = "fldaP8D9AM8CHEZ2o"
FLD_EST_CONF = "fldUnFZ2ayjJbMW4I"
FLD_EST_UPDATED_AT = "fld7St3rZilF8WOYs"

SNAPSHOT_PATH = "state/cbm_last_snapshot.json"
BATCH_SIZE = 10  # Airtable batch PATCH limit


def load_snapshot() -> dict:
    if not os.path.exists(SNAPSHOT_PATH):
        return {}
    with open(SNAPSHOT_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_snapshot(snap: dict) -> None:
    os.makedirs(os.path.dirname(SNAPSHOT_PATH), exist_ok=True)
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)


def fetch_active_shipments(headers: dict, days_ahead: int = 7) -> list[dict]:
    """출하확정일 ∈ [today, today+N]."""
    today = datetime.now(timezone(timedelta(hours=9))).date()
    end = today + timedelta(days=days_ahead)
    # Airtable native filter supports IS_AFTER / IS_BEFORE on date fields via filterByFormula
    formula = (
        f"AND("
        f"IS_AFTER({{출하확정일}}, '{(today - timedelta(days=1)).isoformat()}'),"
        f"IS_BEFORE({{출하확정일}}, '{(end + timedelta(days=1)).isoformat()}')"
        f")"
    )
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_SHIP}"
    records: list[dict] = []
    offset = None
    while True:
        params = {
            "filterByFormula": formula,
            "pageSize": 100,
            "fields[]": [FLD_FINAL_OUT_TEXT, FLD_FINAL_POST_TEXT, FLD_TOTAL_CBM,
                         FLD_CONFIRM_DATE, FLD_SC_ID, FLD_PROJECT,
                         FLD_EST_CBM, FLD_EST_CONF],
            "returnFieldsByFieldId": "true",
        }
        if offset:
            params["offset"] = offset
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records


def batch_patch(headers: dict, updates: list[dict], dry_run: bool = False) -> int:
    """10건 batch PATCH. Returns count of patched records."""
    if dry_run:
        return len(updates)
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_SHIP}"
    patched = 0
    for i in range(0, len(updates), BATCH_SIZE):
        chunk = updates[i:i + BATCH_SIZE]
        payload = {"records": chunk, "typecast": False}
        r = requests.patch(url, headers={**headers, "Content-Type": "application/json"},
                           data=json.dumps(payload), timeout=30)
        r.raise_for_status()
        patched += len(chunk)
        time.sleep(0.2)
    return patched


def run(dry_run: bool = False, limit: int | None = None) -> dict:
    pat = os.environ.get("AIRTABLE_PAT")
    if not pat:
        sys.exit("ERROR: AIRTABLE_PAT not set")
    headers = {"Authorization": f"Bearer {pat}"}

    cache = load_product_cache(headers)
    shipments = fetch_active_shipments(headers)
    if limit:
        shipments = shipments[:limit]

    prev_snap = load_snapshot()
    new_snap: dict[str, dict] = {}
    updates: list[dict] = []
    transitions = 0
    anomalies = 0
    n_skipped_no_project = 0

    now_iso = datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds")

    for rec in shipments:
        rid = rec["id"]
        f = rec["fields"]
        # Sub-Spec 2 자동 대상 = project IS NOT NULL (이동목적 filter는 polling 이후 단계 검증)
        project_val = f.get(FLD_PROJECT)
        if not project_val:
            n_skipped_no_project += 1
            new_snap[rid] = {"total_cbm": f.get(FLD_TOTAL_CBM, 0)}
            continue

        # Shape the shipment dict for estimate_shipment_cbm
        shipment_for_estimate = {"fields": {
            "Total_CBM": f.get(FLD_TOTAL_CBM, 0),
            "최종 출고 품목 및 수량": f.get(FLD_FINAL_POST_TEXT, ""),
            "최종 출하 품목": f.get(FLD_FINAL_OUT_TEXT, ""),
        }}
        result = estimate_shipment_cbm(shipment_for_estimate, cache.lookup)

        # Transition detection
        prev_cbm = prev_snap.get(rid, {}).get("total_cbm", 0) or 0
        new_cbm = f.get(FLD_TOTAL_CBM, 0) or 0
        if new_cbm > 0 and prev_cbm != new_cbm:
            estimate_before = prev_snap.get(rid, {}).get("estimated_cbm", 0) or 0
            log_transition(f.get(FLD_SC_ID, rid), prev_cbm, new_cbm,
                           estimate_before, result["confidence"])
            transitions += 1
            # Anomaly check on transition: was the prior estimate wildly off?
            if estimate_before > 0:
                logged = log_anomaly(
                    f.get(FLD_SC_ID, rid),
                    estimated=estimate_before,
                    actual=new_cbm,
                    matched=result["matched"],
                    unmatched=result["unmatched"],
                )
                if logged:
                    anomalies += 1

        # Snapshot new state
        new_snap[rid] = {
            "total_cbm": new_cbm,
            "estimated_cbm": result["estimated_cbm"],
            "confidence": result["confidence"],
            "mode": result["mode"],
        }

        # Skip PATCH if values unchanged from current Airtable state (idempotent)
        cur_est = f.get(FLD_EST_CBM)
        cur_conf = f.get(FLD_EST_CONF)
        if cur_est == result["estimated_cbm"] and cur_conf == result["confidence"]:
            continue

        updates.append({
            "id": rid,
            "fields": {
                FLD_EST_CBM: result["estimated_cbm"],
                FLD_EST_CONF: result["confidence"],
                FLD_EST_UPDATED_AT: now_iso,
            },
        })

    patched = batch_patch(headers, updates, dry_run=dry_run) if updates else 0
    if not dry_run:
        save_snapshot(new_snap)

    return {
        "dry_run": dry_run,
        "n_shipments_fetched": len(shipments),
        "n_skipped_no_project": n_skipped_no_project,
        "n_patched": patched,
        "n_pending_patch": len(updates),
        "transitions_logged": transitions,
        "anomalies_logged": anomalies,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    summary = run(dry_run=args.dry_run, limit=args.limit)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
