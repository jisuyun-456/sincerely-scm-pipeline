"""
mh_backfill_to_ibsa.py
────────────────────────────────────────────────────────────────────────────────
입하검수입고 베이스 (app6DGHCPI3Yh3IFS) sync_movement 테이블에
CBM-driven 표준 M/H 6개 필드를 채워넣는 백필 스크립트.

대상 필드 (docs/airtable_schemas/ibsa_mh_fields.md 참조):
  - CBM                 fldTHmNEPNhcIX5AQ   m³
  - MH_입하_표준        fld5ZybpbcpEaDkEt   분 (WERC 통합 — 하차+수량확인+서류매칭+staging)
  - MH_검수_표준        fldue4gsBUJIEbGTP   분
  - MH_입고_표준        fldy6Z6durcP0CWFx   분
  - MH_합계_표준        fldmhIVSe5lSkfZhn   분
  - MH_상수버전         fld1UjVS3uM7ii7Cy   text

정의 (2026-05-20):
  입하 = WERC 글로벌 표준 15 CBM/MH (4.0 min/CBM × 1.15 PFD)
       = receiving 활동 전체 (트럭→도크 unloading + qty 확인 + invoice 매칭 + staging)
       → 별도 하차 라인 없음 (double-counting 방지)

Idempotency:
  - MH_상수버전 == 현재 VERSION 인 record는 skip (재계산 없음)
  - --full 로 강제 재계산

사용법:
  python scripts/mh_backfill_to_ibsa.py                       # dry-run, 신규/미버전 record만
  python scripts/mh_backfill_to_ibsa.py --execute              # 실제 PATCH
  python scripts/mh_backfill_to_ibsa.py --execute --full       # 전체 재계산
  python scripts/mh_backfill_to_ibsa.py --since 2026-04-18 --execute
  python scripts/mh_backfill_to_ibsa.py --limit 10            # 10건만 테스트

환경변수:
  AIRTABLE_IBSA_PAT  — 입하검수입고 베이스 PAT (data.records:read/write 필요)
  AIRTABLE_WMS_PAT   — WMS 베이스 PAT (sync_parts fallback 용)
"""

import argparse
import math
import os
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

# ── Constants (mh_calculator.py 와 동기 유지) ────────────────────────────────
VERSION = "v2026-05-cal3"      # 본 버전 식별자 — calibration 갱신 시 bump

PFD_ALLOWANCE = 1.15
RECEIVING_MIN_PER_CBM = 4.0
RECEIVING_MIN_THICKNESS_MM = 3.0
RECEIVING_FLOOR_STD_MIN = 0.5   # 30초 floor (PFD 전 표준) — mh_calculator.py 동기
RECEIVING_CAP_STD_MIN   = 5.0   # 최대 5분 cap (PFD 전 표준) — mh_calculator.py 동기
PUTAWAY_BASE_MIN = 3.0
PUTAWAY_MAX_MIN = 5.0
PUTAWAY_PER_CBM_MIN = 7.0
QC_MIN_PER_PROJECT = 2.5

# ── Airtable ─────────────────────────────────────────────────────────────────
IBSA_BASE = "app6DGHCPI3Yh3IFS"
IBSA_TABLE = "tblhzYiltSBm6vxBz"  # sync_movement

WMS_BASE = "appLui4ZR5HWcQRri"
WMS_SYNC_PARTS = "tblzJh0V4hdo4Xbvx"
WMS_SP_FLD_CODE = "fld8gjySjm4XkCpMc"
WMS_SP_FLD_SPEC = "fldRseOMNseg15D6R"

# Field IDs (sync_movement)
F = {
    "movement_id":     "fldhcO7JFJlVpvnbY",
    "이동목적":         "fldru408fCLHn9v3k",
    "제품_규격":        "fldRhOJuPnE7ZRk6L",
    "입하수량":         "fldXj3bp2ioe8awCd",
    "입하완료처리시간": "fld5pwd5dVYqW4Bdl",
    "입하예정물품":     "fldEMORus5VTtQRVX",
    "입하일자":         "fldcCmgZNTKUWpL9J",
    "project_name":    "fld8Prbt0HqtRSIWP",
    # backfill targets
    "CBM":             "fldTHmNEPNhcIX5AQ",
    "MH_입하":         "fld5ZybpbcpEaDkEt",
    "MH_검수":         "fldue4gsBUJIEbGTP",
    "MH_입고":         "fldy6Z6durcP0CWFx",
    "MH_합계":         "fldmhIVSe5lSkfZhn",
    "MH_상수버전":     "fld1UjVS3uM7ii7Cy",
}

IBSA_PAT = os.environ.get("AIRTABLE_IBSA_PAT", "")
WMS_PAT = os.environ.get("AIRTABLE_WMS_PAT") or os.environ.get("AIRTABLE_PAT", "")


# ── CBM helpers (mh_calculator.py 와 정합) ───────────────────────────────────
def parse_dims_mm(raw):
    if not raw:
        return None
    cleaned = re.split(r"펼침", str(raw))[0]
    cleaned = re.sub(r"mm", "", cleaned, flags=re.IGNORECASE)
    nums = [float(n) for n in re.findall(r"[\d.]+", cleaned) if float(n) > 0]
    if len(nums) >= 3:
        return (nums[0], nums[1], nums[2])
    if len(nums) == 2:
        return (nums[0], nums[1], RECEIVING_MIN_THICKNESS_MM)
    return None


def spec_to_cbm(spec, qty):
    dims = parse_dims_mm(spec)
    if dims is None or qty <= 0:
        return 0.0
    w, h, d = dims
    return (w / 1000) * (h / 1000) * (d / 1000) * qty


def extract_pt_code(이동물품):
    if not 이동물품:
        return ""
    first = str(이동물품).split("||")[0].strip()
    dash = first.find("-")
    return first[:dash] if dash != -1 else first


def load_sync_parts_lookup():
    """sync_parts → {PT_code: 규격} dict 1회 사전 로드."""
    if not WMS_PAT:
        print("[WARN] AIRTABLE_WMS_PAT 미설정 → sync_parts fallback 비활성", file=sys.stderr)
        return {}
    lookup = {}
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {WMS_PAT}"})
    offset = None
    while True:
        params = {
            "pageSize": 100,
            "returnFieldsByFieldId": "true",
            "fields[]": [WMS_SP_FLD_CODE, WMS_SP_FLD_SPEC],
        }
        if offset:
            params["offset"] = offset
        resp = session.get(f"https://api.airtable.com/v0/{WMS_BASE}/{WMS_SYNC_PARTS}",
                           params=params, timeout=90)
        resp.raise_for_status()
        data = resp.json()
        for r in data.get("records", []):
            f = r.get("fields", {})
            code = str(f.get(WMS_SP_FLD_CODE) or "").strip()
            spec = str(f.get(WMS_SP_FLD_SPEC) or "").strip()
            if code:
                lookup[code] = spec
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return lookup


# ── M/H 계산 ─────────────────────────────────────────────────────────────────
def calc_record_mh(rec_fields, sync_parts_lookup):
    """
    record fields(by_field_id) → {CBM, MH_입하, MH_검수, MH_입고, MH_합계}
    return None 이면 skip 권장 (필수값 부재)
    """
    qty = rec_fields.get(F["입하수량"]) or 0
    spec = (rec_fields.get(F["제품_규격"]) or "").strip()

    cbm = 0.0
    if qty > 0 and spec:
        cbm = spec_to_cbm(spec, qty)

    # fallback: sync_parts 룩업
    if cbm <= 0 and qty > 0:
        pt = extract_pt_code(rec_fields.get(F["입하예정물품"]))
        if pt and pt in sync_parts_lookup:
            cbm = spec_to_cbm(sync_parts_lookup[pt], qty)

    # 표준 M/H 계산 (입하: floor 0.5분 ~ cap 5.0분, PFD 전 표준)
    raw_입하 = cbm * RECEIVING_MIN_PER_CBM
    mh_입하 = min(RECEIVING_CAP_STD_MIN, max(RECEIVING_FLOOR_STD_MIN, raw_입하)) * PFD_ALLOWANCE
    mh_검수 = QC_MIN_PER_PROJECT * PFD_ALLOWANCE
    if cbm > 0:
        extra = min(PUTAWAY_MAX_MIN - PUTAWAY_BASE_MIN, cbm * PUTAWAY_PER_CBM_MIN)
        mh_입고 = (PUTAWAY_BASE_MIN + extra) * PFD_ALLOWANCE
    else:
        mh_입고 = PUTAWAY_BASE_MIN * PFD_ALLOWANCE  # base만

    mh_합계 = mh_입하 + mh_검수 + mh_입고

    return {
        F["CBM"]: round(cbm, 6),
        F["MH_입하"]: round(mh_입하, 2),
        F["MH_검수"]: round(mh_검수, 2),
        F["MH_입고"]: round(mh_입고, 2),
        F["MH_합계"]: round(mh_합계, 2),
        F["MH_상수버전"]: VERSION,
    }


# ── Backfill 메인 ────────────────────────────────────────────────────────────
def fetch_target_records(since=None, full=False, limit=None):
    """
    대상: 이동목적=생산산출 + 입하완료처리시간 채워진 record
    Idempotency: full=False 이면 MH_상수버전 != VERSION 만 가져옴
    """
    if not IBSA_PAT:
        print("ERROR: AIRTABLE_IBSA_PAT 환경변수 미설정", file=sys.stderr)
        sys.exit(2)

    conditions = [
        "{이동목적}='생산산출'",
        "NOT({입하완료처리시간}=BLANK())",
    ]
    if since:
        conditions.append(f"IS_AFTER({{입하일자}},'{since}')")
    if not full:
        conditions.append(f"OR({{MH_상수버전}}=BLANK(),{{MH_상수버전}}!='{VERSION}')")
    formula = "AND(" + ",".join(conditions) + ")"

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {IBSA_PAT}"})

    records, offset = [], None
    while True:
        params = {
            "pageSize": 100,
            "returnFieldsByFieldId": "true",
            "filterByFormula": formula,
            "fields[]": [
                F["movement_id"], F["입하수량"], F["제품_규격"],
                F["입하예정물품"], F["입하일자"], F["MH_상수버전"],
            ],
        }
        if offset:
            params["offset"] = offset
        resp = session.get(
            f"https://api.airtable.com/v0/{IBSA_BASE}/{IBSA_TABLE}",
            params=params, timeout=90,
        )
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        if limit and len(records) >= limit:
            records = records[:limit]
            break
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records


def batch_patch(updates, execute=False):
    """updates: [{"id": recId, "fields": {fldXxx: val, ...}}, ...]
    return: (patched_count, error_count)
    """
    if not updates:
        return 0, 0
    if not execute:
        return 0, 0  # dry-run: nothing to do

    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {IBSA_PAT}",
        "Content-Type": "application/json",
    })
    patched, errors = 0, 0
    for i in range(0, len(updates), 10):
        chunk = updates[i:i + 10]
        body = {"records": chunk, "typecast": False}
        resp = session.patch(
            f"https://api.airtable.com/v0/{IBSA_BASE}/{IBSA_TABLE}",
            json=body, timeout=90,
        )
        if resp.status_code != 200:
            print(f"  PATCH error {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
            errors += len(chunk)
        else:
            patched += len(chunk)
        time.sleep(0.25)
    return patched, errors


def main():
    global VERSION
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true",
                    help="실제 PATCH (기본은 dry-run)")
    ap.add_argument("--full", action="store_true",
                    help="MH_상수버전 무시하고 전체 재계산")
    ap.add_argument("--since", help="입하일자 시작 (YYYY-MM-DD)")
    ap.add_argument("--limit", type=int, help="처리 최대 건수 (테스트용)")
    ap.add_argument("--version", help=f"상수버전 라벨 override (기본 {VERSION})")
    args = ap.parse_args()

    if args.version:
        VERSION = args.version

    print(f"=== mh_backfill_to_ibsa.py ===")
    print(f"  VERSION:    {VERSION}")
    print(f"  dry-run:    {not args.execute}")
    print(f"  full:       {args.full}")
    print(f"  since:      {args.since or '(none)'}")
    print(f"  limit:      {args.limit or '(none)'}")
    print()

    # 1. sync_parts 로드
    print("[1/4] sync_parts lookup 로드...")
    lookup = load_sync_parts_lookup()
    print(f"      loaded {len(lookup)} parts")

    # 2. 대상 record 조회
    print(f"[2/4] 대상 record 조회...")
    records = fetch_target_records(since=args.since, full=args.full, limit=args.limit)
    print(f"      {len(records)} records to process")

    if not records:
        print("처리할 record 없음 — 종료")
        return

    # 3. M/H 계산
    print(f"[3/4] M/H 계산...")
    updates, skipped = [], 0
    for r in records:
        mh = calc_record_mh(r.get("fields", {}), lookup)
        if mh is None:
            skipped += 1
            continue
        updates.append({"id": r["id"], "fields": mh})
    print(f"      computed {len(updates)} / skipped {skipped}")

    # Preview first 3
    print("\n  [preview] first 3 records:")
    for u in updates[:3]:
        print(f"    {u['id']}: CBM={u['fields'][F['CBM']]:.6f} "
              f"입하={u['fields'][F['MH_입하']]:.2f} "
              f"검수={u['fields'][F['MH_검수']]:.2f} "
              f"입고={u['fields'][F['MH_입고']]:.2f} "
              f"합계={u['fields'][F['MH_합계']]:.2f}")

    # 4. Batch PATCH
    print(f"\n[4/4] {'PATCH 실행' if args.execute else 'PATCH dry-run (실행 X)'}")
    patched, errors = batch_patch(updates, execute=args.execute)
    if args.execute:
        print(f"      patched: {patched}  errors: {errors}")
    else:
        print(f"      would patch: {len(updates)}  (--execute 로 실제 실행)")

    print("\n=== 완료 ===")


if __name__ == "__main__":
    main()
