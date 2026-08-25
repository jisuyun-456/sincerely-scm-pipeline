"""Contract C2 verification — 배송슬롯 자동 결정 정확도 ≥ 80%.

25-01~26-05-27 7,588건 역사 데이터 기반 측정.
Airtable에서 배송슬롯 필드(기존 사람이 입력한 값)와
slot_decider.decide_slot() 결과를 비교.

Usage:
    python scripts/verification/verify_c2_slot.py [--limit N]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict

BASE_ID = "app4x70a8mOrIKsMf"
SHIPMENT_TABLE = "tbllg1JoHclGYer7m"

FLD_METHOD = "flduzH5tS7orqGG3o"
FLD_HOPE_TIME = "fldFweNu3dASPv93N"
FLD_RECEIPT_CATEGORY = "fldqHPpgLRSIf7Aic"
FLD_SLOT = "fldcSrlxCngYQHtSV"
FLD_PROJECT_CODE = "fldTs3FzaSdGYEiKX"

# 택배계 배송방식 — slot 비교 대상 아님
PARCEL_METHODS = {"택배(일반)", "택배(제주산간)", "신시어리택배"}


def _airtable_get_all(formula: str, limit: int) -> list[dict]:
    pat = os.environ.get("AIRTABLE_PAT", "")
    if not pat:
        raise RuntimeError("AIRTABLE_PAT 환경변수 필요")
    headers = {"Authorization": f"Bearer {pat}"}
    url = f"https://api.airtable.com/v0/{BASE_ID}/{SHIPMENT_TABLE}"
    records: list[dict] = []
    offset = None
    while len(records) < limit:
        params = {"pageSize": min(100, limit - len(records)), "filterByFormula": formula}
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=7588, help="레코드 수 상한")
    args = parser.parse_args()

    from harness.dispatch.slot_decider import decide_slot

    # fetch: 슬롯 값 있고 project code 있는 records
    formula = f"AND(NOT({{{FLD_SLOT}}}=''),NOT({{{FLD_PROJECT_CODE}}}=''))"
    print(f"Fetching up to {args.limit} records…")
    records = _airtable_get_all(formula, args.limit)
    print(f"Fetched {len(records)} records")

    tp = 0
    fp = 0
    per_slot: dict[str, dict] = defaultdict(lambda: {"correct": 0, "total": 0})

    for rec in records:
        f = rec.get("fields", {})
        method = _first(f.get(FLD_METHOD))
        if method in PARCEL_METHODS:
            continue  # 택배는 슬롯 비교 제외
        hope_time = _first(f.get(FLD_HOPE_TIME))
        receipt_category = _first(f.get(FLD_RECEIPT_CATEGORY))
        actual_slot = _first(f.get(FLD_SLOT))
        if not actual_slot:
            continue
        predicted_slot, _ = decide_slot(method, hope_time, receipt_category)
        per_slot[actual_slot]["total"] += 1
        if predicted_slot == actual_slot:
            tp += 1
            per_slot[actual_slot]["correct"] += 1
        else:
            fp += 1

    total_compared = tp + fp
    if total_compared == 0:
        print("⚠️  비교 가능 레코드 없음 (택배 제외 후). 데이터 확인 필요.")
        sys.exit(0)

    accuracy = tp / total_compared * 100
    threshold = 80.0

    print(f"\n[C2 배송슬롯 정확도] {threshold}% 기준선")
    print(f"Total: {total_compared} records (택배 제외)")
    print(f"True positives: {tp}")
    print(f"Mis-classifications: {fp}")
    print(f"Accuracy: {accuracy:.1f}% {'✅ PASS' if accuracy >= threshold else '❌ FAIL'}")
    print()
    print("Per-slot accuracy:")
    for slot, stats in sorted(per_slot.items(), key=lambda x: -x[1]["total"]):
        n = stats["total"]
        c = stats["correct"]
        pct = c / n * 100 if n else 0
        print(f"  {slot}: {pct:.1f}% (n={n})")

    sys.exit(0 if accuracy >= threshold else 1)


if __name__ == "__main__":
    main()
