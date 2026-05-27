"""배송파트너 테이블의 record들에 운영 정책 정보(9개 신규 필드) 일괄 입력.

대상:
- 자체 기사 3 (이장훈/조희선/박종성) — 운영 정보 + 이장훈 CBM 7.616 → 4.5 정정
- 외주/위탁 16개 record들 — autonomy_level + lock_in_reason + contract_type 분류

재실행 가능 (idempotent): 모든 record는 PATCH 방식 — 같은 값 다시 쓰는 건 무해.

Source: _AutoResearch/SCM/outputs/2026-05-27-driver-lane-consolidation-strategy.md
Run: python scripts/seed/update_배송파트너_정책필드.py [--dry-run]
"""
from __future__ import annotations
import os
import sys
import requests

BASE_ID = "app4x70a8mOrIKsMf"
TABLE_ID = "tblI4ZXrte7WyhXyd"

# 자체 기사 3 — 정책 정보 + CBM 정정
DRIVER_UPDATES = [
    {
        "record_id": "recyVExCkk2Lty0E9",  # 신시어리 (이장훈)
        "fields": {
            "배송파트너_CBM": 4.5,  # 7.616 → 4.5 (스타리아 화물칸 추정 — Open Decision)
            "residence": "서울 성북구",
            "work_hours_start": "09:00",
            "work_hours_end": "13:00",
            "daily_fixed_cost": 160000,
            "max_daily_orders": 3,
            "contract_type": "계약직",
            "wave_pattern": "W1-시간고정",
            "autonomy_level": "internal",
            "lock_in_reason": "none",
        },
    },
    {
        "record_id": "recPkgE4o3cs0krnR",  # 신시어리 (조희선)
        "fields": {
            # CBM 7.616 유지 (정확 값 확인 시 갱신)
            "residence": "서울 양천구",
            "work_hours_start": "09:00",
            "work_hours_end": "18:00",
            "daily_fixed_cost": 360000,
            "max_daily_orders": 6,
            "contract_type": "계약직",
            "wave_pattern": "W2-시간고정",
            "autonomy_level": "internal",
            "lock_in_reason": "none",
        },
    },
    {
        "record_id": "recXCfwVTqaoeQ9SS",  # 신시어리 (박종성)
        "fields": {
            # CBM 9.486 유지
            "residence": "서울 중랑구",
            # work_hours_start/end 비워둠 (유연 24h)
            "daily_fixed_cost": 0,
            "max_daily_orders": 8,
            "contract_type": "개인사업자",
            "wave_pattern": "W3-Trigger기반",
            "autonomy_level": "internal",
            "lock_in_reason": "none",
        },
    },
]

# 외주 record 분류 — record ID 기준 (배송파트너 테이블 19개 record 중 자체 3 제외 16개)
PARTNER_UPDATES = [
    # 다영기획 (퀵) — 임가공 협력사, partial (퀵은 박종성 90% 흡수)
    {"record_id": "recPV3KdfisKr9Zs8", "fields": {"contract_type": "외주_3PL", "wave_pattern": "N-A", "autonomy_level": "partial", "lock_in_reason": "imga_gong-mapping"}},
    # 다영기획 (택배)
    {"record_id": "recxh0xUjlwOOkrKJ", "fields": {"contract_type": "외주_3PL", "wave_pattern": "N-A", "autonomy_level": "locked-in", "lock_in_reason": "customer-designated"}},
    # 베스트원 (퀵) — 광주시 재고보관 창고
    {"record_id": "recFyXr7Y1sIjWQ62", "fields": {"contract_type": "외주_3PL", "wave_pattern": "N-A", "autonomy_level": "locked-in", "lock_in_reason": "distance"}},
    # 베스트원 (택배)
    {"record_id": "rec9cMWyTYFJzrNiK", "fields": {"contract_type": "외주_3PL", "wave_pattern": "N-A", "autonomy_level": "locked-in", "lock_in_reason": "distance"}},
    # 로지비 (퀵) — 이천시 풀필먼트
    {"record_id": "rec4e0KsUSiX3dcPT", "fields": {"contract_type": "외주_3PL", "wave_pattern": "N-A", "autonomy_level": "locked-in", "lock_in_reason": "distance"}},
    # 로지비 (택배)
    {"record_id": "rec61pZqGjuYaMwFc", "fields": {"contract_type": "외주_3PL", "wave_pattern": "N-A", "autonomy_level": "locked-in", "lock_in_reason": "distance"}},
    # 신시어리 위탁 — 로젠·고고엑스·항공·물류팀
    {"record_id": "recrbwsFhkb16eMXZ", "fields": {"contract_type": "외주_carrier", "wave_pattern": "N-A", "autonomy_level": "autonomous", "lock_in_reason": "none"}},
    {"record_id": "recSRtnToG5XrcMzZ", "fields": {"contract_type": "외주_carrier", "wave_pattern": "N-A", "autonomy_level": "autonomous", "lock_in_reason": "none"}},
    {"record_id": "recDvqCerTWX6bCin", "fields": {"contract_type": "외주_carrier", "wave_pattern": "N-A", "autonomy_level": "autonomous", "lock_in_reason": "none"}},
    {"record_id": "recdD4leXvLNazDPO", "fields": {"contract_type": "계약직", "wave_pattern": "N-A", "autonomy_level": "internal", "lock_in_reason": "none"}},
    {"record_id": "reclDM1WJuZJTD257", "fields": {"contract_type": "외주_carrier", "wave_pattern": "N-A", "autonomy_level": "autonomous", "lock_in_reason": "none"}},
    # 에스에스아이팩 — 2026-05-27 운영 종료. Status Notes에 [inactive] 표기.
    {"record_id": "recrmvfz58msNDfNN", "fields": {"contract_type": "외주_3PL", "wave_pattern": "N-A", "autonomy_level": "locked-in", "lock_in_reason": "none", "Notes": "2026-05-27 운영 종료. 과거 record 보존용. [inactive]"}},
    {"record_id": "rec7QF1ioERDdogIu", "fields": {"contract_type": "외주_3PL", "wave_pattern": "N-A", "autonomy_level": "locked-in", "lock_in_reason": "none", "Notes": "2026-05-27 운영 종료. 과거 record 보존용. [inactive]"}},
    # 제작협력사 (퀵·택배)
    {"record_id": "recr48f91VOWjYN3Z", "fields": {"contract_type": "외주_3PL", "wave_pattern": "N-A", "autonomy_level": "partial", "lock_in_reason": "imga_gong-mapping"}},
    {"record_id": "recx9DjW1StCQeJRS", "fields": {"contract_type": "외주_3PL", "wave_pattern": "N-A", "autonomy_level": "locked-in", "lock_in_reason": "customer-designated"}},
    # 고객 (직접 수령)
    {"record_id": "recpA2Fv7lESQVNk9", "fields": {"contract_type": "고객직접", "wave_pattern": "N-A", "autonomy_level": "locked-in", "lock_in_reason": "customer-designated"}},
]


def _headers(pat: str) -> dict:
    return {"Authorization": f"Bearer {pat}", "Content-Type": "application/json"}


def update_drivers(dry_run: bool = False) -> int:
    pat = os.environ.get("AIRTABLE_PAT")
    if not pat:
        sys.exit("ERROR: AIRTABLE_PAT 환경변수 필요")

    headers = _headers(pat)
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}"

    if dry_run:
        for upd in DRIVER_UPDATES:
            print(f"  [DRY] {upd['record_id']}: {list(upd['fields'].keys())}")
        return 0

    # PATCH batch (10 records max per request)
    payload = {"records": [{"id": u["record_id"], "fields": u["fields"]} for u in DRIVER_UPDATES]}
    r = requests.patch(url, headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    count = len(r.json().get("records", []))
    print(f"자체 기사 {count} record 갱신 완료")
    return count


def update_partners(dry_run: bool = False) -> int:
    pat = os.environ.get("AIRTABLE_PAT")
    if not pat:
        sys.exit("ERROR: AIRTABLE_PAT 환경변수 필요")

    headers = _headers(pat)
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}"

    if dry_run:
        for upd in PARTNER_UPDATES:
            print(f"  [DRY] {upd['record_id']}: {list(upd['fields'].keys())}")
        return 0

    # PATCH in batches of 10 (Airtable limit)
    total = 0
    for i in range(0, len(PARTNER_UPDATES), 10):
        batch = PARTNER_UPDATES[i:i+10]
        payload = {"records": [{"id": u["record_id"], "fields": u["fields"]} for u in batch]}
        r = requests.patch(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        total += len(r.json().get("records", []))
    print(f"외주/위탁 {total} record 분류 정보 갱신 완료")
    return total


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    driver_count = update_drivers(dry_run=dry)
    partner_count = update_partners(dry_run=dry)
    print(f"drivers: {driver_count}, partners: {partner_count}")
