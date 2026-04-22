"""
sync_box_count.py
────────────────────────────────────────────────────────────────────────────
Barcode 테이블(외박스) → 이동리스트 라벨 박스수량 동기화

각 이동리스트(IL) 레코드에 연결된 외박스(BC) 레코드 수를 계산하여
이동리스트의 '라벨 박스수량' 필드를 PATCH.

사용법:
  python scripts/sync_box_count.py            # 전체 업데이트 (변경된 것만)
  python scripts/sync_box_count.py --dry-run  # 변경 예정 목록만 출력
  python scripts/sync_box_count.py --project PNA38579  # 프로젝트 필터
"""

import argparse, os, sys, time
import requests
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

BC_BASE  = "app4LvuNIDiqTmhnv"
TBL_IL   = "tblnxU0PlegXT7bYj"   # 이동리스트
TBL_BC   = "tbl0K3QP5PCd06Cxv"   # 바코드(외박스)
PAT      = (os.getenv("AIRTABLE_API_KEY")
            or os.getenv("AIRTABLE_WMS_PAT")
            or os.getenv("AIRTABLE_PAT", ""))
HEADERS  = {
    "Authorization":  f"Bearer {PAT}",
    "Content-Type":   "application/json",
}


def airtable_get(table: str, params: dict) -> list:
    url = f"https://api.airtable.com/v0/{BC_BASE}/{table}"
    records, offset = [], None
    while True:
        p = dict(params)
        if offset:
            p["offset"] = offset
        r = requests.get(url, headers=HEADERS, params=p, timeout=30)
        r.raise_for_status()
        data = r.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records


def patch_records(table: str, updates: list[dict]):
    """updates: [{"id": rec_id, "fields": {...}}, ...]  10건씩 PATCH"""
    url = f"https://api.airtable.com/v0/{BC_BASE}/{table}"
    for i in range(0, len(updates), 10):
        batch = updates[i:i+10]
        r = requests.patch(url, headers=HEADERS,
                           json={"records": batch}, timeout=30)
        r.raise_for_status()
        print(f"  PATCH {len(batch)}건 완료")
        time.sleep(0.22)


def main():
    parser = argparse.ArgumentParser(description="이동리스트 라벨 박스수량 동기화")
    parser.add_argument("--dry-run", action="store_true", help="미리보기만")
    parser.add_argument("--project", help="프로젝트 코드 필터 (예: PNA38579)")
    args = parser.parse_args()

    if not PAT:
        print("❌ AIRTABLE_API_KEY 환경변수 없음"); sys.exit(1)

    # ── 이동리스트 전체 조회 ────────────────────────────────────────────────
    print("▶ 이동리스트 조회…")
    il_params = {"pageSize": 100}
    if args.project:
        il_params["filterByFormula"] = f"FIND('{args.project}', {{project}})"
    il_recs = airtable_get(TBL_IL, il_params)
    print(f"  {len(il_recs)}건")

    il_set = {r["id"] for r in il_recs}

    # ── Barcode(외박스) 전체 조회 ───────────────────────────────────────────
    print("▶ Barcode(외박스) 조회…")
    bc_recs = airtable_get(TBL_BC, {"pageSize": 100})
    print(f"  {len(bc_recs)}건")

    # ── IL당 박스수 계산: BC의 라벨 박스수량 합산 ──────────────────────────
    # (BC 레코드 수가 아니라 각 BC의 '라벨 박스수량' 값을 합산)
    il_box_count: dict[str, int] = {}
    for bc in bc_recs:
        bf     = bc.get("fields", {})
        il_ids = bf.get("이동리스트") or []
        bc_box = int(bf.get("라벨 박스수량") or 1)   # BC 한 건당 박스수 (기본 1)
        for il_id in (il_ids if isinstance(il_ids, list) else []):
            if il_id in il_set:
                il_box_count[il_id] = il_box_count.get(il_id, 0) + bc_box

    # ── 변경 대상 필터 ──────────────────────────────────────────────────────
    updates = []
    for rec in il_recs:
        rec_id  = rec["id"]
        cur_val = int(rec.get("fields", {}).get("라벨 박스수량") or 0)
        new_val = il_box_count.get(rec_id, 0)
        if new_val and new_val != cur_val:
            pt = rec.get("fields", {}).get("파츠코드", "")
            updates.append({
                "id":     rec_id,
                "fields": {"라벨 박스수량": new_val},
                "_pt":    pt,
                "_old":   cur_val,
                "_new":   new_val,
            })

    print(f"\n변경 대상: {len(updates)}건")
    for u in updates:
        print(f"  {u.get('_pt','?'):12}  {u['_old']} → {u['_new']}")

    if args.dry_run:
        print("\n(dry-run — 실제 업데이트 없음)"); return

    if not updates:
        print("업데이트 없음"); return

    # _pt, _old, _new 키는 API 전송 전 제거
    api_updates = [{"id": u["id"], "fields": u["fields"]} for u in updates]
    print("\n▶ Airtable 업데이트 중…")
    patch_records(TBL_IL, api_updates)
    print("✅ 동기화 완료")


if __name__ == "__main__":
    main()
