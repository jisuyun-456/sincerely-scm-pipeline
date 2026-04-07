# ================================================================
# 택배 실제배송일수 최종 교정 (수도권→2, 지방/도서→3)
# ================================================================
# 배송방식 contains "택배" AND 실제배송일수=0 인 레코드를
# 구간유형에 따라 수도권→2, 나머지→3 으로 교정.
# Airtable filterByFormula에서 한글 필드명 사용 (REST API 기본).
# ================================================================

import os
import time
import requests

PAT      = os.environ.get("AIRTABLE_PAT", "")
BASE_ID  = "app4x70a8mOrIKsMf"
TABLE_ID = "tbllg1JoHclGYer7m"
API_BASE = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}"

HEADERS = {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}

FLD_DELIVERY_DAYS = "fld1EJjUSSKKboinl"


def fetch_and_update(zone_formula: str, days: int, label: str) -> int:
    """구간유형별 레코드 조회 후 실제배송일수 업데이트. 처리 건수 반환."""
    formula = (
        'AND({발송상태_TMS}="출하 완료",'
        'FIND("택배",ARRAYJOIN({배송 방식})),'
        + zone_formula + ','
        '{실제배송일수}=0)'
    )

    total = 0
    offset = None
    page = 1
    record_ids = []

    # 전체 조회
    while True:
        params: dict = {"filterByFormula": formula, "fields[]": [FLD_DELIVERY_DAYS], "pageSize": 100}
        if offset:
            params["offset"] = offset
        resp = requests.get(API_BASE, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("records", [])
        record_ids.extend([r["id"] for r in batch])
        print(f"  [{label}] page {page}: {len(batch)}건 (누적 {len(record_ids)}건)", flush=True)
        offset = data.get("offset")
        if not offset:
            break
        page += 1
        time.sleep(0.2)

    if not record_ids:
        print(f"  [{label}] 0건 — 스킵\n", flush=True)
        return 0

    # 배치 업데이트
    print(f"  [{label}] {len(record_ids)}건 → {days}일로 업데이트 중...", flush=True)
    for i in range(0, len(record_ids), 10):
        batch = record_ids[i : i + 10]
        payload = {"records": [{"id": rid, "fields": {FLD_DELIVERY_DAYS: days}} for rid in batch]}
        resp = requests.patch(API_BASE, headers=HEADERS, json=payload)
        resp.raise_for_status()
        done = min(i + 10, len(record_ids))
        if done % 500 == 0 or done == len(record_ids):
            print(f"  [{label}] 업데이트 진행: {done}/{len(record_ids)}건", flush=True)
        time.sleep(0.2)

    print(f"  [{label}] 완료: {len(record_ids)}건\n", flush=True)
    return len(record_ids)


def main() -> None:
    if not PAT:
        raise ValueError("AIRTABLE_PAT 환경변수 미설정")

    print("=" * 60, flush=True)
    print("택배 실제배송일수 최종 교정", flush=True)
    print("=" * 60, flush=True)

    # 수도권 택배 → 2일
    cnt2 = fetch_and_update('{구간유형}="수도권"', 2, "수도권→2일")

    # 지방/도서 택배 → 3일 (수도권이 아닌 경우)
    cnt3 = fetch_and_update('{구간유형}!="수도권"', 3, "지방/도서→3일")

    print(f"총 교정: {cnt2 + cnt3}건 (2일: {cnt2}건, 3일: {cnt3}건)", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    main()
