"""P4 — WMS_Location.Max_CBM 필드 신설 + 실측치 시드 (사용자 CP 2026-06-11).

실측(에이원센터 입하장 A1-IB-001):
  1,200×1,200×1,200mm ×12 = 20.736m³ + 800×600×1,200mm ×64 = 36.864m³ → 57.6m³
보관(베스트원 ST) 분모는 미도착 — 도착 시 SEEDS에 추가 후 재실행 (idempotent).
TMS Location.Max_CBM 재사용 금지(다른 물리량) — WMS_Location 네이티브 신설.
WMS_Location은 _WRITE_ALLOWLIST 포함 (master data PATCH — ledger 아님).

Usage:
  python scripts/backbone/seed_max_cbm.py            # dry-run
  python scripts/backbone/seed_max_cbm.py --write
"""
import argparse
import os

import requests
from dotenv import load_dotenv

load_dotenv()
WP = os.environ["AIRTABLE_WMS_PAT"]
WMS = "appLui4ZR5HWcQRri"
LOC = "tblRwUTP5kWnHFt5P"
HEADERS = {"Authorization": f"Bearer {WP}", "Content-Type": "application/json"}

SEEDS = {"A1-IB-001": 57.6}   # Location_ID → m³ (실측 2026-06-11)


def field_exists() -> bool:
    r = requests.get(f"https://api.airtable.com/v0/meta/bases/{WMS}/tables",
                     headers=HEADERS, timeout=60)
    r.raise_for_status()
    tbl = next(t for t in r.json()["tables"] if t["id"] == LOC)
    return any(f["name"] == "Max_CBM" for f in tbl["fields"])


def create_field():
    r = requests.post(
        f"https://api.airtable.com/v0/meta/bases/{WMS}/tables/{LOC}/fields",
        headers=HEADERS, timeout=60,
        json={"name": "Max_CBM", "type": "number",
              "description": "물리 부피 용량 m³ (실측 시드 — P4 2026-06-11)",
              "options": {"precision": 3}},
    )
    r.raise_for_status()
    print("  Max_CBM 필드 신설 완료")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    exists = field_exists()
    print(f"Max_CBM 필드: {'있음' if exists else '없음 (신설 필요)'}")
    if not exists:
        if args.write:
            create_field()
        else:
            print("  [DRY-RUN] --write 시 신설")

    fields = ["Location_ID"] + (["Max_CBM"] if exists else [])
    r = requests.get(f"https://api.airtable.com/v0/{WMS}/{LOC}",
                     headers=HEADERS, timeout=60,
                     params={"pageSize": 100, "fields[]": fields})
    r.raise_for_status()
    locs = {rec["fields"].get("Location_ID"): rec for rec in r.json()["records"]}

    for loc_id, target in SEEDS.items():
        rec = locs.get(loc_id)
        if not rec:
            print(f"  ❌ {loc_id}: Location 행 없음 — skip")
            continue
        cur = rec["fields"].get("Max_CBM")
        if cur == target:
            print(f"  = {loc_id}: 이미 {target}m³ — skip (idempotent)")
            continue
        if not args.write:
            print(f"  [DRY-RUN] {loc_id}: {cur} → {target}m³")
            continue
        pr = requests.patch(f"https://api.airtable.com/v0/{WMS}/{LOC}/{rec['id']}",
                            headers=HEADERS, timeout=60,
                            json={"fields": {"Max_CBM": target}})
        pr.raise_for_status()
        print(f"  ✅ {loc_id}: {cur} → {target}m³ PATCH 완료")


if __name__ == "__main__":
    main()
