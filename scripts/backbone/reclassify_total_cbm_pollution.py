"""P0 ruling: Total_CBM>0(기계추정 오염) → estimated_cbm 이관 + Total_CBM blank.

사용자 확정: 중량 미측정·부피만, 실측 수동입력 없음 → 일괄 재분류 안전.
- estimated_cbm = 기존 Total_CBM (legacy 추정 보존)
- estimation_confidence = 0.3 (legacy machine estimate)
- estimation_updated_at = 실행 시각(ISO)
- Total_CBM = null (실측 전용 레인으로 비움)
값 무손실(estimated_cbm로 이동). P1 replay가 결정론으로 estimated_cbm 정제.

Usage:
  python scripts/backbone/reclassify_total_cbm_pollution.py            # dry-run
  python scripts/backbone/reclassify_total_cbm_pollution.py --write    # 실행
"""
import argparse
import os
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

load_dotenv()
TP = os.environ["AIRTABLE_PAT"]
TMS = "app4x70a8mOrIKsMf"
SHIP = "tbllg1JoHclGYer7m"
URL = f"https://api.airtable.com/v0/{TMS}/{SHIP}"
H = {"Authorization": f"Bearer {TP}", "Content-Type": "application/json"}
LEGACY_CONF = 0.3


def n(x):
    try:
        return float(str(x).replace(",", "") or 0)
    except (ValueError, TypeError):
        return 0.0


def fetch_polluted():
    out, off = [], None
    while True:
        p = {"pageSize": 100, "fields[]": ["Total_CBM", "estimated_cbm"]}
        if off:
            p["offset"] = off
        r = requests.get(URL, headers=H, params=p, timeout=60)
        r.raise_for_status()
        d = r.json()
        for rec in d.get("records", []):
            if n(rec["fields"].get("Total_CBM")) > 0:
                out.append(rec)
        off = d.get("offset")
        if not off:
            break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    recs = fetch_polluted()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    print(f"Total_CBM>0 대상: {len(recs)}건")
    # 이미 estimated_cbm 있는 행은 덮어쓰지 않음(idempotent)
    todo = [r for r in recs if n(r["fields"].get("estimated_cbm")) <= 0]
    print(f"  이관 대상(estimated_cbm 비어있음): {len(todo)}건 / skip {len(recs)-len(todo)}건")

    if not args.write:
        for r in todo[:5]:
            print(f"  [DRY] {r['id']}  Total_CBM {r['fields']['Total_CBM']} → estimated_cbm + Total_CBM=null")
        print("\n[DRY-RUN] --write 로 실행")
        return

    patched = errors = 0
    for i in range(0, len(todo), 10):
        batch = [{
            "id": r["id"],
            "fields": {
                "estimated_cbm": round(n(r["fields"]["Total_CBM"]), 4),
                "estimation_confidence": LEGACY_CONF,
                "estimation_updated_at": ts,
                "Total_CBM": None,
            },
        } for r in todo[i:i + 10]]
        for attempt in range(3):
            resp = requests.patch(URL, headers=H, json={"records": batch}, timeout=30)
            time.sleep(0.25)
            if resp.ok:
                patched += len(batch)
                break
            if attempt == 2:
                print(f"  ERROR {resp.status_code}: {resp.text[:120]}")
                errors += len(batch)
        if patched % 200 == 0 and patched:
            print(f"  진행 {patched}/{len(todo)}")
    print(f"\n결과: patched={patched} errors={errors}")


if __name__ == "__main__":
    main()
