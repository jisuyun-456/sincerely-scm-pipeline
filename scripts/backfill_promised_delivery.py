"""
backfill_promised_delivery.py
──────────────────────────────────────────────────────────────────────────────
약속납기일 = 출하확정일 + SLA 목표배송일수

TMS Airtable의 Shipment 레코드에서
proxy(약속납기일 = 출하확정일)인 건을 찾아 실측값으로 업데이트.

SLA 기준: 배송SLA 테이블 (구간유형 + 배송방식 → 목표배송일수)

사용법:
  # 전체 Shipment 백필 (최초 1회)
  python scripts/backfill_promised_delivery.py --mode all

  # 지난 7일 신규 Shipment만 (주 1회, 매주 월요일)
  python scripts/backfill_promised_delivery.py --mode weekly

  # dry-run (실제 업데이트 없이 결과 미리보기)
  python scripts/backfill_promised_delivery.py --mode all --dry-run

환경변수:
  AIRTABLE_PAT  (또는 .env 파일)
"""

import argparse
import os
import sys
import time
from datetime import date, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()

# ── 상수 ──────────────────────────────────────────────────────────────────────
BASE_ID = "app4x70a8mOrIKsMf"
TBL_SHIPMENT = "tbllg1JoHclGYer7m"
TBL_SLA = "tblbPC6z0AsbvcVxJ"

# Shipment 필드 ID
FLD_CONFIRMED_DATE = "fldQvmEwwzvQW95h9"   # 출하확정일 (date)
FLD_PROMISED_DATE = "fldyYIfBhhu7sEX1P"   # 약속납기일 (date) ← 업데이트 대상
FLD_DELIVERY_TYPE = "fldp6haTDFzzF5C74"   # 구간유형 (singleSelect)
FLD_DELIVERY_METHOD = "flduzH5tS7orqGG3o" # 배송 방식 (rollup → list)

# 배송SLA 필드 ID
FLD_SLA_ZONE = "fldOcAzLmHw3gb6Gr"        # 구간유형 (singleSelect)
FLD_SLA_METHOD = "fldpm7IsG1gZrvsfG"      # 배송방식 (singleSelect)
FLD_SLA_LEAD_DAYS = "fldlZ0INaM3CNidcD"   # 목표배송일수 (number)

AIRTABLE_PAT = os.environ.get("AIRTABLE_PAT", "")
HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_PAT}",
    "Content-Type": "application/json",
}
BATCH_SIZE = 10  # Airtable PATCH 최대 10건


# ── Airtable API ───────────────────────────────────────────────────────────────
def get_records(table_id: str, fields: list[str], offset: str | None = None) -> dict:
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}"
    params: dict = {"fields[]": fields, "pageSize": 100, "returnFieldsByFieldId": "true"}
    if offset:
        params["offset"] = offset
    resp = requests.get(url, headers=HEADERS, params=params)
    resp.raise_for_status()
    return resp.json()


def patch_records(table_id: str, updates: list[dict]) -> dict:
    """updates = [{"id": "recXXX", "fields": {...}}, ...]"""
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}"
    resp = requests.patch(url, headers=HEADERS, json={"records": updates})
    resp.raise_for_status()
    return resp.json()


# ── SLA 룩업 테이블 빌드 ────────────────────────────────────────────────────────
def build_sla_lookup() -> dict[tuple[str, str], int]:
    """{ (구간유형, 배송방식): 목표배송일수 }"""
    lookup: dict[tuple[str, str], int] = {}
    offset = None
    while True:
        data = get_records(
            TBL_SLA,
            [FLD_SLA_ZONE, FLD_SLA_METHOD, FLD_SLA_LEAD_DAYS],
            offset,
        )
        for rec in data.get("records", []):
            f = rec.get("fields", {})
            zone = f.get(FLD_SLA_ZONE) or ""   # singleSelect → plain string
            method = f.get(FLD_SLA_METHOD) or ""
            lead = f.get(FLD_SLA_LEAD_DAYS)
            if zone and method and lead is not None:
                lookup[(zone, method)] = int(lead)
        offset = data.get("offset")
        if not offset:
            break
    print(f"[SLA] {len(lookup)}개 룩업 로드 완료")
    for k, v in sorted(lookup.items()):
        print(f"  {k[0]} + {k[1]} → {v}일")
    return lookup


# ── Shipment 로드 ──────────────────────────────────────────────────────────────
def load_shipments(mode: str, since: str | None = None) -> list[dict]:
    """
    mode='all'    : 약속납기일 == 출하확정일 인 모든 레코드
    mode='weekly' : 최근 7일 출하확정일 기준 레코드
    since         : 이 날짜(YYYY-MM-DD) 이후 출하확정일 건만 처리 (기본 2026-01-01)
    """
    records = []
    offset = None
    cutoff = (date.today() - timedelta(days=7)).isoformat() if mode == "weekly" else None
    since_date = since or "2026-01-01"  # 26년 이전은 TMS 운영 전 데이터 — 제외

    while True:
        data = get_records(
            TBL_SHIPMENT,
            [FLD_CONFIRMED_DATE, FLD_PROMISED_DATE, FLD_DELIVERY_TYPE, FLD_DELIVERY_METHOD],
            offset,
        )
        for rec in data.get("records", []):
            f = rec.get("fields", {})
            confirmed = f.get(FLD_CONFIRMED_DATE)
            promised = f.get(FLD_PROMISED_DATE)
            if not confirmed:
                continue  # 출하확정일 없으면 스킵

            # since 필터: 26년 이전 데이터 제외
            if confirmed < since_date:
                continue

            # weekly 모드: 최근 7일만
            if cutoff and confirmed < cutoff:
                continue

            # proxy 조건: 약속납기일이 없거나 출하확정일과 같은 날
            if promised is None or promised == confirmed:
                records.append(rec)

        offset = data.get("offset")
        if not offset:
            break

    return records


# ── 배송방식 정규화 맵 (SLA 테이블 키와 매핑) ──────────────────────────────────────
METHOD_NORMALIZE = {
    "택배(분할)": "택배",
    "택배(일반)": "택배",
}


# ── 배송방식 추출 (rollup → 단일값) ──────────────────────────────────────────────
def extract_method(cell_value) -> str:
    """
    배송 방식은 rollup이라 [{"value": "택배"}, ...] 또는 ["택배"] 형태일 수 있음.
    첫 번째 값만 사용. 정규화 맵 적용.
    """
    if not cell_value:
        return ""
    raw = ""
    if isinstance(cell_value, list):
        for item in cell_value:
            if isinstance(item, dict):
                raw = item.get("value", "")
                break
            if isinstance(item, str):
                raw = item
                break
    elif isinstance(cell_value, str):
        raw = cell_value
    return METHOD_NORMALIZE.get(raw, raw)


# ── 메인 백필 로직 ─────────────────────────────────────────────────────────────
def run_backfill(mode: str, dry_run: bool, since: str = "2026-01-01") -> None:
    if not AIRTABLE_PAT:
        print("[ERROR] AIRTABLE_PAT 환경변수가 없습니다. .env 파일을 확인하세요.")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"약속납기일 백필 시작 | mode={mode} | since={since} | dry_run={dry_run}")
    print(f"{'='*60}\n")

    # 1. SLA 룩업 빌드
    sla = build_sla_lookup()

    # 2. Shipment 로드
    print(f"\n[Shipment] {mode} 모드로 대상 레코드 조회 중... (since={since})")
    shipments = load_shipments(mode, since)
    print(f"[Shipment] 대상 {len(shipments)}건 발견\n")

    if not shipments:
        print("업데이트할 레코드가 없습니다.")
        return

    # 3. 업데이트 계산
    updates = []
    skipped = 0
    fallback_days = 2  # SLA 매핑 없을 때 기본값

    for rec in shipments:
        f = rec.get("fields", {})
        confirmed_str = f.get(FLD_CONFIRMED_DATE)  # "2026-03-15"
        zone_obj = f.get(FLD_DELIVERY_TYPE)
        method_raw = f.get(FLD_DELIVERY_METHOD)

        zone = zone_obj if isinstance(zone_obj, str) else ((zone_obj or {}).get("name", "") if isinstance(zone_obj, dict) else "")
        method = extract_method(method_raw)

        if not confirmed_str:
            skipped += 1
            continue

        lead_days = sla.get((zone, method))
        if lead_days is None:
            # fallback: 구간유형만으로 매핑 시도
            for (z, m), d_val in sla.items():
                if z == zone:
                    lead_days = d_val
                    break
            if lead_days is None:
                lead_days = fallback_days
                print(f"  [WARN] SLA 미매핑 ({zone}, {method}) → fallback {fallback_days}일 | rec={rec['id']}")

        confirmed_date = date.fromisoformat(confirmed_str)
        promised_date = confirmed_date + timedelta(days=lead_days)

        updates.append({
            "id": rec["id"],
            "fields": {FLD_PROMISED_DATE: promised_date.isoformat()},
            "_debug": {
                "confirmed": confirmed_str,
                "zone": zone,
                "method": method,
                "lead_days": lead_days,
                "promised": promised_date.isoformat(),
            },
        })

    print(f"계산 완료: {len(updates)}건 업데이트 예정, {skipped}건 스킵\n")

    # dry-run: 미리보기만
    if dry_run:
        print("[DRY-RUN] 실제 업데이트 없이 미리보기만 출력합니다.\n")
        for u in updates[:20]:
            d = u["_debug"]
            print(
                f"  {u['id']} | {d['confirmed']} +{d['lead_days']}일"
                f" ({d['zone']}/{d['method']}) → {d['promised']}"
            )
        if len(updates) > 20:
            print(f"  ... 이하 {len(updates) - 20}건 생략")
        return

    # 4. 실제 PATCH (배치 10건)
    success = 0
    for i in range(0, len(updates), BATCH_SIZE):
        batch = updates[i : i + BATCH_SIZE]
        # _debug 키 제거 후 전송
        clean = [{"id": u["id"], "fields": u["fields"]} for u in batch]
        try:
            patch_records(TBL_SHIPMENT, clean)
            success += len(clean)
            print(f"  [{i + len(clean)}/{len(updates)}] 업데이트 완료")
        except requests.HTTPError as e:
            print(f"  [ERROR] 배치 {i}~{i+BATCH_SIZE} 실패: {e}")
        time.sleep(0.25)  # Airtable rate limit (5 req/s)

    print(f"\n완료: {success}/{len(updates)}건 업데이트")
    print(f"{'='*60}\n")


# ── CLI ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="약속납기일 SLA 기반 백필")
    parser.add_argument(
        "--mode",
        choices=["all", "weekly"],
        default="weekly",
        help="all: 전체 백필 (최초 1회) | weekly: 지난 7일만 (주 1회)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 업데이트 없이 결과만 미리보기",
    )
    parser.add_argument(
        "--since",
        default="2026-01-01",
        help="이 날짜(YYYY-MM-DD) 이후 출하확정일 건만 처리 (기본: 2026-01-01)",
    )
    args = parser.parse_args()
    run_backfill(args.mode, args.dry_run, args.since)
