"""
sync_box_count.py
────────────────────────────────────────────────────────────────────────────
WMS 입고박스수량 → Barcode 베이스 이동리스트 라벨 박스수량 동기화

우선순위:
  1순위: WMS Movement 테이블 '입고박스수량' (입하팀 기입값) — movement_id 매칭
  Fallback: Barcode 외박스(BC) 레코드의 '라벨 박스수량' 합산

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

# Barcode 베이스 (피킹리스트 소스)
BC_BASE      = "app4LvuNIDiqTmhnv"
TBL_IL       = "tblnxU0PlegXT7bYj"   # 이동리스트
TBL_BC       = "tbl0K3QP5PCd06Cxv"   # 바코드(외박스)

# WMS 베이스 (입하팀 기입값 소스)
WMS_BASE     = "appLui4ZR5HWcQRri"
TBL_MOVEMENT = "tblwq7Kj5Y9nVjlOw"

BC_PAT   = (os.getenv("AIRTABLE_API_KEY")
            or os.getenv("AIRTABLE_WMS_PAT")
            or os.getenv("AIRTABLE_PAT", ""))
WMS_PAT  = (os.getenv("AIRTABLE_WMS_PAT")
            or os.getenv("AIRTABLE_PAT", ""))
BC_HDRS  = {"Authorization": f"Bearer {BC_PAT}",  "Content-Type": "application/json"}
WMS_HDRS = {"Authorization": f"Bearer {WMS_PAT}", "Content-Type": "application/json"}


# ────────────────────────────────────────────────────────────────────────────
# 유틸
# ────────────────────────────────────────────────────────────────────────────
def get_all(base: str, table: str, headers: dict, params: dict) -> list:
    url = f"https://api.airtable.com/v0/{base}/{table}"
    records, offset = [], None
    while True:
        p = dict(params)
        if offset:
            p["offset"] = offset
        r = requests.get(url, headers=headers, params=p, timeout=30)
        r.raise_for_status()
        data = r.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records


def patch_bc(updates: list[dict]):
    """Barcode 이동리스트 PATCH, 10건씩"""
    url = f"https://api.airtable.com/v0/{BC_BASE}/{TBL_IL}"
    for i in range(0, len(updates), 10):
        batch = updates[i:i+10]
        r = requests.patch(url, headers=BC_HDRS,
                           json={"records": batch}, timeout=30)
        r.raise_for_status()
        print(f"  PATCH {len(batch)}건 완료")
        time.sleep(0.22)


# ────────────────────────────────────────────────────────────────────────────
# 메인
# ────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="이동리스트 라벨 박스수량 동기화")
    parser.add_argument("--dry-run", action="store_true", help="미리보기만")
    parser.add_argument("--project", help="프로젝트 코드 필터 (예: PNA38579)")
    args = parser.parse_args()

    if not BC_PAT:
        print("❌ AIRTABLE_API_KEY 환경변수 없음"); sys.exit(1)

    # ── 1) Barcode 베이스 이동리스트 조회 ──────────────────────────────────
    print("▶ Barcode 이동리스트 조회…")
    il_params = {"pageSize": 100}
    if args.project:
        il_params["filterByFormula"] = f"FIND('{args.project}', {{project}})"
    il_recs = get_all(BC_BASE, TBL_IL, BC_HDRS, il_params)
    print(f"  {len(il_recs)}건")

    # movement_id → IL record 매핑
    mov_to_il_id: dict[str, str] = {}
    for r in il_recs:
        mid = (r.get("fields", {}).get("movement_id") or "").strip()
        if mid:
            mov_to_il_id[mid] = r["id"]

    # ── 2) WMS Movement: 입고박스수량 기입 레코드 조회 ─────────────────────
    print("▶ WMS Movement 입고박스수량 조회…")
    base_formula = "{입고박스수량} != ''"
    if args.project:
        wms_formula = f"AND({base_formula}, FIND('{args.project}', {{이동물품}}))"
    else:
        wms_formula = base_formula
    try:
        wms_recs = get_all(WMS_BASE, TBL_MOVEMENT, WMS_HDRS, {
            "fields[]": ["movement_id", "입고박스수량"],
            "filterByFormula": wms_formula,
            "pageSize": 100,
        })
    except Exception as e:
        print(f"  WMS 조회 실패 ({e}) — BC fallback만 사용")
        wms_recs = []
    print(f"  WMS 입고박스 기입: {len(wms_recs)}건")

    # movement_id → WMS 입고박스수량
    wms_box: dict[str, int] = {}
    for r in wms_recs:
        f   = r.get("fields", {})
        mid = (f.get("movement_id") or "").strip()
        val = f.get("입고박스수량") or ""
        if mid and val:
            try:
                wms_box[mid] = int(str(val).strip())
            except ValueError:
                pass

    # ── 3) Fallback: Barcode 외박스 BC 합산 ───────────────────────────────
    print("▶ Barcode 외박스 조회 (fallback용)…")
    bc_recs = get_all(BC_BASE, TBL_BC, BC_HDRS, {"pageSize": 100})
    print(f"  {len(bc_recs)}건")

    il_bc_box: dict[str, int] = {}
    il_id_set = {r["id"] for r in il_recs}
    for bc in bc_recs:
        bf     = bc.get("fields", {})
        il_ids = bf.get("이동리스트") or []
        bc_box = int(bf.get("라벨 박스수량") or 1)
        for il_id in (il_ids if isinstance(il_ids, list) else []):
            if il_id in il_id_set:
                il_bc_box[il_id] = il_bc_box.get(il_id, 0) + bc_box

    # ── 4) 최종 박스수 결정 ────────────────────────────────────────────────
    updates = []
    for r in il_recs:
        rec_id  = r["id"]
        f       = r.get("fields", {})
        cur_val = int(f.get("라벨 박스수량") or 0)
        mid     = (f.get("movement_id") or "").strip().rstrip(";").strip()
        pt      = (f.get("파츠코드") or "").strip().rstrip(";").strip()

        if mid and mid in wms_box:
            new_val = wms_box[mid]
            source  = "WMS"
        elif rec_id in il_bc_box:
            new_val = il_bc_box[rec_id]
            source  = "BC "
        else:
            continue

        if new_val and new_val != cur_val:
            updates.append({
                "id":      rec_id,
                "fields":  {"라벨 박스수량": new_val},
                "_pt":     pt,
                "_old":    cur_val,
                "_new":    new_val,
                "_source": source,
            })

    print(f"\n변경 대상: {len(updates)}건")
    for u in updates:
        print(f"  [{u['_source']}] {u.get('_pt','?'):12}  {u['_old']} → {u['_new']}")

    if args.dry_run:
        print("\n(dry-run — 실제 업데이트 없음)"); return

    if not updates:
        print("업데이트 없음"); return

    api_updates = [{"id": u["id"], "fields": u["fields"]} for u in updates]
    print("\n▶ Airtable 업데이트 중…")
    patch_bc(api_updates)
    print("✅ 동기화 완료")


if __name__ == "__main__":
    main()
