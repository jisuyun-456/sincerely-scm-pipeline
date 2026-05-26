#!/usr/bin/env python3
"""
문서출력 ↔ 피킹리스트 2 자동 연결

매핑 경로: 문서출력.라벨링작업 → 라벨링작업.피킹리스트 → 문서출력.피킹리스트 2 채우기

Usage:
    python scripts/link_picking_list_2.py --dry-run   # 변경 없이 매핑 결과만 출력
    python scripts/link_picking_list_2.py             # 실제 업데이트
"""
import os, sys, time, argparse
import requests

API_KEY = os.environ.get("AIRTABLE_API_KEY", "")
if not API_KEY:
    raise SystemExit("ERROR: AIRTABLE_API_KEY not set")

BASE_ID = "app4LvuNIDiqTmhnv"
HDRS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# Table IDs
TBL_DOCPRINT  = "tblMQG1PYioIUWdbe"  # 문서출력
TBL_LR        = "tblnxU0PlegXT7bYj"  # 라벨링작업

# Field IDs in 문서출력
F_DOC_LR      = "fldbPHrVcBrUr39R3"  # 라벨링작업 (multipleRecordLinks)
F_DOC_PL2     = "fldnGsmwqfVbCjrS6"  # 피킹리스트 2 (multipleRecordLinks)

# Field IDs in 라벨링작업
F_LR_PL       = "fld0X1hazNGX7TiO9"  # 피킹리스트 (multipleRecordLinks)

URL_DOC = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_DOCPRINT}"
URL_LR  = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_LR}"


def paginate(url, params):
    records, offset = [], None
    while True:
        p = {**params, **({"offset": offset} if offset else {})}
        r = requests.get(url, headers=HDRS, params=p)
        r.raise_for_status()
        data = r.json()
        records += data.get("records", [])
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records


def get_lr_record(rec_id: str, session: requests.Session) -> dict:
    """라벨링작업 레코드 단건 GET (fields[] param not supported on single-record endpoint)"""
    url = f"{URL_LR}/{rec_id}"
    r = session.get(url, headers=HDRS)
    r.raise_for_status()
    return r.json()


def patch_batch(updates: list, dry_run: bool) -> int:
    ok = 0
    for i in range(0, len(updates), 10):
        batch = updates[i:i + 10]
        if dry_run:
            for u in batch:
                pl2 = u["fields"]["피킹리스트 2"]
                print(f"  [DRY] {u['id']} → 피킹리스트 {pl2[0] if pl2 else '?'}")
            ok += len(batch)
        else:
            r = requests.patch(URL_DOC, headers=HDRS, json={"records": batch})
            if r.status_code == 200:
                ok += len(batch)
                print(f"  PATCH ok: {len(batch)}건 (누적 {ok})")
            else:
                print(f"  !! PATCH fail {r.status_code}: {r.text[:200]}")
            time.sleep(0.25)
    return ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("link_picking_list_2.py" + (" [DRY RUN]" if args.dry_run else ""))
    print("=" * 60)

    # ── 1. 문서출력 전체 조회 (필요 필드만)
    print("\n[1] 문서출력 레코드 조회 중...")
    doc_records = paginate(URL_DOC, {
        "returnFieldsByFieldId": "true",
        "fields[]": [F_DOC_LR, F_DOC_PL2],
        "pageSize": 100,
    })
    print(f"    총 {len(doc_records)}건")

    # ── 2. 클라이언트 필터: 피킹리스트 2 없음 AND 라벨링작업 있음
    candidates = []
    skipped_no_lr = 0
    skipped_already_linked = 0
    for rec in doc_records:
        f = rec.get("fields", {})
        has_pl2 = bool(f.get(F_DOC_PL2))
        has_lr  = bool(f.get(F_DOC_LR))
        if has_pl2:
            skipped_already_linked += 1
        elif not has_lr:
            skipped_no_lr += 1
        else:
            candidates.append(rec)

    print(f"    이미 연결됨: {skipped_already_linked}건 skip")
    print(f"    라벨링작업 없음: {skipped_no_lr}건 skip")
    print(f"    연결 대상: {len(candidates)}건")

    if not candidates:
        print("\n연결할 레코드가 없습니다.")
        return

    # ── 3. 필요한 라벨링작업 IDs 수집 (문서출력당 첫 번째만)
    # 가정: 한 문서출력의 모든 라벨링작업은 같은 피킹리스트를 가리킴
    lr_to_fetch = {}  # lr_record_id → 문서출력 record id (representative)
    doc_to_first_lr = {}  # 문서출력 id → 첫 번째 lr id
    for rec in candidates:
        # With returnFieldsByFieldId=true, linked fields return as plain string IDs
        lr_raw = rec["fields"].get(F_DOC_LR, [])
        lr_ids = [lr if isinstance(lr, str) else lr["id"] for lr in lr_raw]
        first_lr = lr_ids[0]
        doc_to_first_lr[rec["id"]] = first_lr
        lr_to_fetch[first_lr] = rec["id"]

    unique_lr_ids = list(lr_to_fetch.keys())
    print(f"\n[2] 라벨링작업 레코드 {len(unique_lr_ids)}건 조회 중...")

    # ── 4. 라벨링작업 단건 GET (RECORD_ID() 필터 금지 정책 준수)
    session = requests.Session()
    lr_pl_map = {}  # lr_id → 피킹리스트 record id
    errors = 0
    for idx, lr_id in enumerate(unique_lr_ids, 1):
        try:
            rec_data = get_lr_record(lr_id, session)
            f = rec_data.get("fields", {})
            # field name key (no returnFieldsByFieldId), value is [{"id":..., "name":...}]
            pl_links = f.get("피킹리스트", [])
            if pl_links:
                first = pl_links[0]
                lr_pl_map[lr_id] = first if isinstance(first, str) else first["id"]
            else:
                lr_pl_map[lr_id] = None
        except Exception as e:
            print(f"  !! GET {lr_id} 실패: {e}")
            lr_pl_map[lr_id] = None
            errors += 1
        if idx % 50 == 0:
            print(f"    {idx}/{len(unique_lr_ids)}...")
        time.sleep(0.05)

    print(f"    완료 (오류: {errors}건)")

    # ── 5. 매핑 빌드
    updates = []
    skipped_no_pl = 0
    for rec in candidates:
        doc_id = rec["id"]
        first_lr = doc_to_first_lr[doc_id]
        pl_id = lr_pl_map.get(first_lr)
        if not pl_id:
            skipped_no_pl += 1
            continue
        updates.append({
            "id": doc_id,
            "fields": {"피킹리스트 2": [pl_id]},
        })

    print(f"\n[3] 업데이트 준비: {len(updates)}건, 피킹리스트 없어 skip: {skipped_no_pl}건")

    # ── 6. Batch PATCH
    print(f"\n[4] {'[DRY RUN] ' if args.dry_run else ''}PATCH 시작...")
    ok = patch_batch(updates, dry_run=args.dry_run)

    print("\n" + "=" * 60)
    print(f"완료: processed={ok}, skipped_no_lr={skipped_no_lr}, "
          f"skipped_already={skipped_already_linked}, skipped_no_pl={skipped_no_pl}, errors={errors}")
    if args.dry_run:
        print("[DRY RUN] 실제 변경 없음. --dry-run 제거 후 재실행하면 적용됩니다.")


if __name__ == "__main__":
    main()
