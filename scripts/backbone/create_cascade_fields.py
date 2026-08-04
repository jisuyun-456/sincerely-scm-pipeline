"""P6b — WMS_PropagationLedger 캐스케이드 필드 7개 신설 (spec §3.1).

P4 seed_max_cbm.py Meta API 패턴 재사용. idempotent — 기존 필드는 skip.
필드 신설 전 order_cascade.py --write 실행 시 unknown field 422 (loud fail, 안전)
— 순서: 본 스크립트 --write → dry-run 1회 → order_cascade.py --write.

Usage:
  python scripts/backbone/create_cascade_fields.py            # dry-run
  python scripts/backbone/create_cascade_fields.py --write
"""
import argparse
import os

import requests
from dotenv import load_dotenv

WMS = "appLui4ZR5HWcQRri"
LEDGER_TBL = "tblkQmontWGSjo8c5"   # WMS_PropagationLedger

# ledger.build_propagation_row 캐스케이드 키와 1:1 (spec §3.1 데이터 계약)
FIELDS = [
    {"name": "부족자재_요약", "type": "multilineText",
     "description": "S2 MRP — PT×부족분(재고/소요) 줄 단위 (P6b 2026-06-12)"},
    {"name": "입하CBM_예상_m3", "type": "number", "options": {"precision": 4},
     "description": "S3 — 부족분 입하 CBM 합 m³ (P6b 2026-06-12)"},
    {"name": "MH_예상_h", "type": "number", "options": {"precision": 2},
     "description": "S3 — 입하+검수+입고 표준 M/H 합 h (P6b 2026-06-12)"},
    {"name": "창고적재_예상", "type": "singleLineText",
     "description": "S4 — staging now%→after% (Max_CBM 대비) (P6b 2026-06-12)"},
    {"name": "wave_프리뷰", "type": "singleLineText",
     "description": "S5 — capacity-feasibility (W1/W2/W3 가능 여부) (P6b 2026-06-12)"},
    {"name": "운임_예상범위", "type": "singleLineText",
     "description": "S6 — 수도권 거리대 요율 범위 (주소 미확정) (P6b 2026-06-12)"},
    {"name": "생산_납기일", "type": "date",
     "options": {"dateFormat": {"name": "iso", "format": "YYYY-MM-DD"}},
     "description": "P3 — MES 최조 납기일 (생산 forward 앵커, 주차 버킷용) (2026-06-18)"},
    {"name": "출고요청일", "type": "date",
     "options": {"dateFormat": {"name": "iso", "format": "YYYY-MM-DD"}},
     "description": "P3 — order 출고 요청일 (출고 forward 앵커, 주차 버킷용) (2026-06-18)"},
    {"name": "cascade_실행ID", "type": "singleLineText",
     "description": "run_id YYYYMMDD-HHMM KST — audit jsonl 조인 키 (P6b 2026-06-12)"},
]


def existing_field_names(headers) -> set[str]:
    r = requests.get(f"https://api.airtable.com/v0/meta/bases/{WMS}/tables",
                     headers=headers, timeout=60)
    r.raise_for_status()
    tbl = next(t for t in r.json()["tables"] if t["id"] == LEDGER_TBL)
    return {f["name"] for f in tbl["fields"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    load_dotenv()
    headers = {"Authorization": f"Bearer {os.environ['AIRTABLE_WMS_PAT']}",
               "Content-Type": "application/json"}
    have = existing_field_names(headers)
    created = 0
    for spec in FIELDS:
        if spec["name"] in have:
            print(f"  = {spec['name']}: 이미 있음 — skip (idempotent)")
            continue
        if not args.write:
            print(f"  [DRY-RUN] {spec['name']} ({spec['type']}) 신설 예정")
            continue
        r = requests.post(
            f"https://api.airtable.com/v0/meta/bases/{WMS}/tables/{LEDGER_TBL}/fields",
            headers=headers, timeout=60, json=spec)
        r.raise_for_status()
        created += 1
        print(f"  ✅ {spec['name']} ({spec['type']}) 신설 완료")
    print(f"\n{'신설 ' + str(created) + '개' if args.write else '[DRY-RUN] write 0'} "
          f"/ 기존 {len(have & {f['name'] for f in FIELDS})}개 / 대상 {len(FIELDS)}개")


if __name__ == "__main__":
    main()
