"""
backfill_dispatch_log.py
────────────────────────────────────────────────────────────────────────────
배차 일지 백필 — 2026-04-04 ~ 2026-04-17

배차 일지 테이블에 4/3 이후 레코드가 없어 기사별 운행일 집계가 저평가됨.
이 스크립트는:
  1. Shipment에서 4/4~4/17 내 내부 기사 배정 건을 조회
  2. 날짜×기사 단위로 그룹핑
  3. 배차 일지 레코드 생성 (14일 × 3기사 = 최대 42건)
     - Shipment 있는 날: 날짜 + 배송파트너 + 배정물량 링크
     - Shipment 없는 날: 날짜 + 배송파트너만 (CBM=0)

사용법:
  python scripts/backfill_dispatch_log.py --dry-run   # 미리보기
  python scripts/backfill_dispatch_log.py             # 실제 생성
"""

import argparse
import os
import time
from datetime import date, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()

# ── 상수 ──────────────────────────────────────────────────────────────────────
BASE_ID      = "app4x70a8mOrIKsMf"
TBL_SHIPMENT = "tbllg1JoHclGYer7m"
TBL_DISPATCH = "tbl0YCjOC7rYtyXHV"

START_DATE = date(2026, 4, 4)
END_DATE   = date(2026, 4, 17)

# 내부 기사 배송파트너 Record ID
INTERNAL_DRIVERS = {
    "recPkgE4o3cs0krnR": "신시어리 (조희선)",
    "recyVExCkk2Lty0E9": "신시어리 (이장훈)",
    "recXCfwVTqaoeQ9SS": "신시어리 (박종성)",
}

# Shipment 필드
FLD_SHP_DATE    = "fldQvmEwwzvQW95h9"   # 출하확정일 (date)
FLD_SHP_PARTNER = "fldM2u6RwLRrO7ymW"  # 배송파트너 (link → 배송파트너)

# 배차 일지 필드
FLD_DISP_DATE     = "fldZh2mZDIPQXfOcO"  # 날짜
FLD_DISP_PARTNER  = "fldIQqaoj2CYlCSFH"  # 배송파트너 (link → 배송파트너)
FLD_DISP_SHIPMENTS = "flddCIndicSSe8uhi" # 배정물량_합계 (link → Shipment)

PAT = os.environ.get(
    "AIRTABLE_PAT",
    "patU9ew1rwbJbEpOn.d5c7c1bb42c3ad69edd2701ee0424ddcb04c4d261a0ed422f8e5edaf1fa20edc",
)
HEADERS = {
    "Authorization": f"Bearer {PAT}",
    "Content-Type": "application/json",
}


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────
def get_all_records(table_id: str, fields: list[str], formula: str | None = None) -> list[dict]:
    records, offset = [], None
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}"
    while True:
        params: dict = {"fields[]": fields, "pageSize": 100, "returnFieldsByFieldId": "true"}
        if offset:
            params["offset"] = offset
        if formula:
            params["filterByFormula"] = formula
        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records


def post_records(table_id: str, records: list[dict]) -> int:
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}"
    created = 0
    for i in range(0, len(records), 10):
        batch = records[i:i+10]
        resp = requests.post(url, headers=HEADERS, json={"records": batch})
        resp.raise_for_status()
        created += len(resp.json().get("records", []))
        time.sleep(0.25)
    return created


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main(dry_run: bool) -> None:
    print("=" * 60)
    print(f"배차 일지 백필 | {START_DATE} ~ {END_DATE}")
    print(f"모드: {'DRY-RUN (실제 생성 없음)' if dry_run else '실제 실행'}")
    print("=" * 60)

    # STEP 1: Shipment 조회
    print("\n[STEP 1] Shipment 조회")
    formula = (
        f"AND("
        f"  IS_AFTER({{{FLD_SHP_DATE}}}, '{(START_DATE - timedelta(days=1)).isoformat()}'),"
        f"  NOT(IS_AFTER({{{FLD_SHP_DATE}}}, '{END_DATE.isoformat()}'))"
        f")"
    )
    shipments = get_all_records(TBL_SHIPMENT, [FLD_SHP_DATE, FLD_SHP_PARTNER], formula)
    print(f"  조회된 Shipment: {len(shipments)}건")

    # STEP 2: 날짜×기사 그룹핑
    print("\n[STEP 2] 날짜×기사 그룹핑")
    groups: dict[tuple[str, str], list[str]] = {}
    for shp in shipments:
        f = shp["fields"]
        day = f.get(FLD_SHP_DATE)
        if not day:
            continue
        for pid in (f.get(FLD_SHP_PARTNER) or []):
            pid_id = pid if isinstance(pid, str) else pid.get("id", "")
            if pid_id in INTERNAL_DRIVERS:
                key = (day, pid_id)
                groups.setdefault(key, []).append(shp["id"])

    print(f"  내부 기사 배정 (날짜×기사): {len(groups)}건")
    for (day, did), ids in sorted(groups.items()):
        print(f"    {day} | {INTERNAL_DRIVERS[did]}: Shipment {len(ids)}건")

    # STEP 3: 배차 일지 레코드 구성
    print("\n[STEP 3] 배차 일지 레코드 구성")
    all_days = [
        (START_DATE + timedelta(days=i)).isoformat()
        for i in range((END_DATE - START_DATE).days + 1)
    ]
    to_create: list[dict] = []
    for day in all_days:
        for driver_id, driver_name in INTERNAL_DRIVERS.items():
            shp_ids = groups.get((day, driver_id), [])
            fields: dict = {
                FLD_DISP_DATE:    day,
                FLD_DISP_PARTNER: [driver_id],
            }
            if shp_ids:
                fields[FLD_DISP_SHIPMENTS] = shp_ids
            to_create.append({"fields": fields})
            cbm_hint = f"Shipment {len(shp_ids)}건 연결" if shp_ids else "CBM=0 (빈 날)"
            print(f"  {day} | {driver_name} → {cbm_hint}")

    print(f"\n  생성 예정: {len(to_create)}건")

    if dry_run:
        print("\n[DRY-RUN] 실제 생성 생략. --dry-run 없이 재실행하면 적용됩니다.")
        return

    # STEP 4: 실제 POST
    print("\n[STEP 4] 배차 일지 레코드 생성")
    created = post_records(TBL_DISPATCH, to_create)
    print(f"  완료: {created}건 생성")

    print("\n" + "=" * 60)
    print("백필 완료")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="미리보기만 (실제 생성 없음)")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
