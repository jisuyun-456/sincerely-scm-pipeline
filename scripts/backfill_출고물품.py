"""
backfill_출고물품.py
────────────────────────────────────────────────────────────────────────────
Barcode 베이스 이동리스트 테이블에서 출고물품이 비어있는 레코드를 채운다.

방식:
  1. 이동리스트 전체를 읽어 {PT코드: 품목명} 매핑 구축 (기존 채워진 레코드 활용)
  2. 빈 출고물품 + 파츠코드 있는 레코드에 매핑값 기록
  3. 매핑에 없는 PT코드는 --dry-run 시 목록 출력 → 수동 입력 안내

사용법:
  python scripts/backfill_출고물품.py --dry-run    # 미리보기 (Airtable 수정 없음)
  python scripts/backfill_출고물품.py              # 실제 업데이트
"""

import argparse, os, sys, time
from collections import defaultdict

import requests
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

BASE_ID   = "app4LvuNIDiqTmhnv"
TABLE     = "tblnxU0PlegXT7bYj"   # 이동리스트
API_URL   = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE}"
PAT       = os.getenv("AIRTABLE_WMS_PAT") or os.getenv("AIRTABLE_PAT", "")
HEADERS   = {"Authorization": f"Bearer {PAT}"}

F_MOV  = "movement_id"
F_PT   = "파츠코드"
F_OUT  = "출고물품"
F_TYPE = "출고자재_자재구분"


# ────────────────────────────────────────────────────────────────────────────
def fetch_all() -> list:
    records, offset = [], None
    while True:
        params = {"fields[]": [F_MOV, F_PT, F_OUT, F_TYPE], "pageSize": 100}
        if offset:
            params["offset"] = offset
        r = requests.get(API_URL, headers=HEADERS, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records


def patch_records(updates: list[dict]):
    """updates: [{"id": recXXX, "fields": {"출고물품": "..."}}]"""
    for i in range(0, len(updates), 10):
        batch = updates[i:i+10]
        payload = {"records": [{"id": u["id"], "fields": u["fields"]} for u in batch]}
        r = requests.patch(API_URL, headers=HEADERS, json=payload, timeout=30)
        r.raise_for_status()
        time.sleep(0.2)


# ────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="이동리스트 출고물품 백필")
    parser.add_argument("--dry-run", action="store_true", help="미리보기만 (수정 없음)")
    args = parser.parse_args()

    if not PAT:
        print("[ERROR] AIRTABLE_WMS_PAT 환경변수가 설정되지 않았습니다.")
        sys.exit(1)

    print("▶ 이동리스트 전체 조회 중…")
    records = fetch_all()
    print(f"  총 {len(records)}건")

    # 1. PT코드 → 품목명 매핑 구축
    pt_map: dict[str, str] = {}
    for r in records:
        f = r.get("fields", {})
        pt   = (f.get(F_PT) or "").strip()
        name = (f.get(F_OUT) or "").strip()
        if pt and name:
            # 가장 최근 값 우선 (나중에 덮어쓰기)
            pt_map[pt] = name

    print(f"  PT → 품목명 매핑: {len(pt_map)}개 구축")

    # 2. 빈 레코드 식별
    to_fill, no_mapping = [], []
    for r in records:
        f   = r.get("fields", {})
        pt  = (f.get(F_PT) or "").strip()
        out = (f.get(F_OUT) or "").strip()
        if out:                        # 이미 채워짐 → skip
            continue
        if not pt:                     # PT코드도 없음 → skip
            continue
        if pt in pt_map:
            to_fill.append({"id": r["id"], "fields": {F_OUT: pt_map[pt]},
                            "_pt": pt, "_name": pt_map[pt],
                            "_mov": f.get(F_MOV,""), "_type": f.get(F_TYPE,"")})
        else:
            no_mapping.append({"rec_id": r["id"], "pt": pt,
                               "mov": f.get(F_MOV,""), "type": f.get(F_TYPE,"")})

    # 3. 결과 출력
    print(f"\n{'='*60}")
    print(f"채울 수 있음: {len(to_fill)}건  |  매핑 없음: {len(no_mapping)}건")
    print(f"{'='*60}")

    if to_fill:
        print(f"\n✅ 채울 수 있는 {len(to_fill)}건 (샘플 15건):")
        for u in to_fill[:15]:
            print(f"  {u['_mov'][:12]:<12} | {u['_pt']:<8} → {u['_name']}")

    if no_mapping:
        print(f"\n⚠️  매핑 없는 {len(no_mapping)}건 (수동 입력 필요):")
        # PT코드별 그룹핑
        pt_groups: dict[str, list] = defaultdict(list)
        for u in no_mapping:
            pt_groups[u["pt"]].append(u["mov"])
        for pt, movs in sorted(pt_groups.items()):
            print(f"  {pt:<10} ({len(movs)}건) — {', '.join(movs[:3])}{'...' if len(movs)>3 else ''}")

    if args.dry_run:
        print("\n[dry-run] Airtable 업데이트 건너뜀")
        return

    if not to_fill:
        print("\n채울 레코드 없음 — 완료")
        return

    print(f"\n▶ {len(to_fill)}건 업데이트 중…")
    patch_records(to_fill)
    print(f"✅ 완료 — {len(to_fill)}건 출고물품 채움")
    if no_mapping:
        print(f"   ⚠️  {len(no_mapping)}건은 매핑 없어 미처리 → Airtable에서 수동 입력 필요")


if __name__ == "__main__":
    main()
