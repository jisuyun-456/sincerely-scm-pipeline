"""Contract C5 verification — Locked-in records recommender override 0건.

Airtable에서 autonomy_level='locked-in' 파트너가 배정된 Shipment를 조회,
wave_recommendation이 'locked-in' 이외 값으로 설정된 건이 있으면 FAIL.

Usage:
    python scripts/verification/verify_c5_lockin.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

BASE_ID = "app4x70a8mOrIKsMf"
SHIPMENT_TABLE = "tbllg1JoHclGYer7m"
PARTNER_TABLE = "tblI4ZXrte7WyhXyd"

FLD_WAVE_REC = "fld9hlDfnTS4frfR4"
FLD_PARTNER = "fldHZ7yMT3KEu2gSj"   # lookup
FLD_AUTONOMY = "fldxPZYD3OpwLtqdP"  # singleSelect (partner table)
FLD_PARTNER_NAME = "fldUCl2kD890FqRkt"  # singleLineText (partner table)
FLD_PROJECT_CODE = "fldTs3FzaSdGYEiKX"


def _fetch_all(table: str, formula: str) -> list[dict]:
    pat = os.environ.get("AIRTABLE_PAT", "")
    if not pat:
        raise RuntimeError("AIRTABLE_PAT 환경변수 필요")
    headers = {"Authorization": f"Bearer {pat}"}
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table}"
    records: list[dict] = []
    offset = None
    while True:
        params = {"pageSize": 100, "filterByFormula": formula}
        if offset:
            params["offset"] = offset
        qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
        req = urllib.request.Request(f"{url}?{qs}", headers=headers)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return records


def _first(val) -> str:
    if isinstance(val, list):
        return val[0] if val else ""
    return val or ""


def main() -> None:
    # 1. locked-in 파트너명 수집
    locked_partners_records = _fetch_all(PARTNER_TABLE, f"{{{FLD_AUTONOMY}}}='locked-in'")
    locked_partner_names = {
        rec["fields"].get(FLD_PARTNER_NAME, "")
        for rec in locked_partners_records
        if rec["fields"].get(FLD_PARTNER_NAME)
    }
    print(f"Locked-in partners: {locked_partner_names}")

    if not locked_partner_names:
        print("⚠️  locked-in 파트너 없음 → SKIP")
        sys.exit(0)

    # 2. wave_recommendation이 설정된 Shipment에서 locked-in 파트너 배정 건 조회
    formula = f"AND(NOT({{{FLD_WAVE_REC}}}=''),NOT({{{FLD_PROJECT_CODE}}}=''))"
    records = _fetch_all(SHIPMENT_TABLE, formula)
    print(f"Wave-recommended shipments: {len(records)}")

    violations = 0
    for rec in records:
        f = rec.get("fields", {})
        partner = _first(f.get(FLD_PARTNER))
        if partner not in locked_partner_names:
            continue
        wave_rec = _first(f.get(FLD_WAVE_REC))
        if wave_rec != "locked-in":
            print(f"  ❌ VIOLATION: {rec['id']} partner={partner} wave={wave_rec}")
            violations += 1

    print(f"\n[C5 locked-in override 검증]")
    print(f"  locked-in 파트너 배정 건 중 override: {violations}건")
    if violations == 0:
        print("  ✅ PASS — override 0건")
        sys.exit(0)
    else:
        print(f"  ❌ FAIL — {violations}건 override 감지")
        sys.exit(1)


if __name__ == "__main__":
    main()
