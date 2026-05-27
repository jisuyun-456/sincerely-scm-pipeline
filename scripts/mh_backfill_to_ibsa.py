"""
mh_backfill_to_ibsa.py
────────────────────────────────────────────────────────────────────────────────
입하검수입고 베이스 (app6DGHCPI3Yh3IFS) sync_movement 테이블에
다중 요소 ELS (Multi-Element Engineered Labor Standard) M/H 6개 필드를 채움.

ELS 구성 (Iter 2.2):
  입하  = WERC 통합 (하차 + carton qty vs ASN + 서류매칭 + staging)  [CBM-driven]
  검수  = 시안검수 + 서류매칭·GR입력                                  [건당 고정]
  입고  = 이동+적치+스캔 [CBM-driven]
         + 표본검수      [고정]
         + 수량확인(저울) [qty-driven]

대상 필드 (docs/airtable_schemas/ibsa_mh_fields.md):
  CBM, MH_입하_표준, MH_검수_표준, MH_입고_표준, MH_합계_표준, MH_상수버전

Idempotency:
  MH_상수버전 == VERSION → skip  /  --full → 전체 재계산

사용법:
  python scripts/mh_backfill_to_ibsa.py                  # dry-run
  python scripts/mh_backfill_to_ibsa.py --execute         # PATCH
  python scripts/mh_backfill_to_ibsa.py --execute --full  # 전체 재계산
  python scripts/mh_backfill_to_ibsa.py --since 2026-04-01 --execute
  python scripts/mh_backfill_to_ibsa.py --limit 10        # 테스트

환경변수:
  AIRTABLE_IBSA_PAT  — 입하검수입고 베이스 PAT
  AIRTABLE_WMS_PAT   — WMS 베이스 PAT (sync_parts 룩업용)
"""

import argparse
import os
import re
import sys
import time

import requests
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

# ── Version ───────────────────────────────────────────────────────────────────
VERSION = "v2026-05-iter22"

# ── ELS 상수 (mh_calculator.py 와 동기 유지) ──────────────────────────────────
PFD = 1.15  # Personal + Fatigue + Delay allowance (15%)

# 입하 (Receiving) — WERC 15 CBM/MH 글로벌 표준
# 하차 + carton qty vs ASN + 서류매칭 + staging 일괄 포함
RECV_MIN_PER_CBM  = 4.0   # 분/CBM
RECV_THICKNESS_MM = 3.0   # 2D 규격 두께 fallback (스티커류)
RECV_FLOOR_MIN    = 0.5   # 하한 (PFD 전)
RECV_CAP_MIN      = 5.0   # 상한 (PFD 전)

# 검수 (QC) — 시안검수 + 서류매칭·GR입력, 건당 고정
QC_MIN     = 2.5   # 시안검수
QC_DOC_MIN = 1.5   # 서류매칭 + GR입력 (Iter 2.2)

# 입고 (Putaway) — 좌표확인 + 이동 + 적치 + 스캔
PUTAWAY_BASE_MIN    = 3.0   # 기본 (소형)
PUTAWAY_CAP_MIN     = 5.0   # 최대
PUTAWAY_PER_CBM_MIN = 7.0   # CBM 당 증가 (CBM ≈ 0.286에서 cap 도달)

# 입고 — 표본검수 (10개 샘플 확인)
SAMPLE_QC_MIN = 2.5

# 입고 — 수량확인 (저울)
COUNTING_FLOOR_MIN = 2.0    # 최소 (소형 소량)
COUNTING_CAP_MIN   = 7.0    # 최대 (지류 다량)
COUNTING_PER_QTY   = 100.0  # 100개당 1분, qty 500개에서 cap 도달

# ── Airtable ──────────────────────────────────────────────────────────────────
IBSA_BASE  = "app6DGHCPI3Yh3IFS"
IBSA_TABLE = "tblhzYiltSBm6vxBz"  # sync_movement

WMS_BASE       = "appLui4ZR5HWcQRri"
WMS_SYNC_PARTS = "tblzJh0V4hdo4Xbvx"
WMS_SP_CODE    = "fld8gjySjm4XkCpMc"
WMS_SP_SPEC    = "fldRseOMNseg15D6R"

# Field IDs — sync_movement
F = {
    "movement_id":      "fldhcO7JFJlVpvnbY",
    "이동목적":          "fldru408fCLHn9v3k",
    "제품_규격":         "fldRhOJuPnE7ZRk6L",
    "입하수량":          "fldXj3bp2ioe8awCd",
    "입하완료처리시간":  "fld5pwd5dVYqW4Bdl",
    "입하예정물품":      "fldEMORus5VTtQRVX",
    "입하일자":          "fldcCmgZNTKUWpL9J",
    # backfill targets
    "CBM":              "fldTHmNEPNhcIX5AQ",
    "MH_입하":          "fld5ZybpbcpEaDkEt",
    "MH_검수":          "fldue4gsBUJIEbGTP",
    "MH_입고":          "fldy6Z6durcP0CWFx",
    "MH_합계":          "fldmhIVSe5lSkfZhn",
    "MH_상수버전":      "fld1UjVS3uM7ii7Cy",
}

IBSA_PAT = os.environ.get("AIRTABLE_IBSA_PAT", "")
WMS_PAT  = os.environ.get("AIRTABLE_WMS_PAT") or os.environ.get("AIRTABLE_PAT", "")


# ── CBM 계산 헬퍼 ─────────────────────────────────────────────────────────────
def _parse_dims_mm(raw) -> tuple | None:
    """'88x88x163', '248*190*33', '200x300mm 펼침...' → (W, H, D) mm."""
    if not raw:
        return None
    cleaned = re.split(r"펼침", str(raw))[0]
    cleaned = re.sub(r"mm", "", cleaned, flags=re.IGNORECASE)
    nums = [float(n) for n in re.findall(r"[\d.]+", cleaned) if float(n) > 0]
    if len(nums) >= 3:
        return nums[0], nums[1], nums[2]
    if len(nums) == 2:
        return nums[0], nums[1], RECV_THICKNESS_MM
    return None


def _spec_to_cbm(spec: str, qty: int) -> float:
    dims = _parse_dims_mm(spec)
    if dims is None or qty <= 0:
        return 0.0
    w, h, d = dims
    return (w / 1000) * (h / 1000) * (d / 1000) * qty


def _pt_code(이동물품) -> str:
    """'PT3137-스티커 || PNA...' → 'PT3137'."""
    if not 이동물품:
        return ""
    first = str(이동물품).split("||")[0].strip()
    dash = first.find("-")
    return first[:dash] if dash != -1 else first


def load_sync_parts_lookup() -> dict:
    """sync_parts → {PT_code: 규격} 1회 로드."""
    if not WMS_PAT:
        print("[WARN] AIRTABLE_WMS_PAT 미설정 → sync_parts fallback 비활성", file=sys.stderr)
        return {}
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {WMS_PAT}"})
    lookup, offset = {}, None
    while True:
        params = {"pageSize": 100, "returnFieldsByFieldId": "true",
                  "fields[]": [WMS_SP_CODE, WMS_SP_SPEC]}
        if offset:
            params["offset"] = offset
        resp = session.get(f"https://api.airtable.com/v0/{WMS_BASE}/{WMS_SYNC_PARTS}",
                           params=params, timeout=90)
        resp.raise_for_status()
        data = resp.json()
        for r in data.get("records", []):
            flds = r.get("fields", {})
            code = str(flds.get(WMS_SP_CODE) or "").strip()
            spec = str(flds.get(WMS_SP_SPEC) or "").strip()
            if code:
                lookup[code] = spec
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return lookup


def resolve_cbm(fields: dict, lookup: dict) -> tuple[float, int]:
    """fields → (cbm, qty). 우선순위: 제품규격 > sync_parts > 0."""
    qty = int(fields.get(F["입하수량"]) or 0)
    spec = (fields.get(F["제품_규격"]) or "").strip()
    cbm = _spec_to_cbm(spec, qty) if qty > 0 and spec else 0.0
    if cbm <= 0 and qty > 0:
        pt = _pt_code(fields.get(F["입하예정물품"]))
        if pt and pt in lookup:
            cbm = _spec_to_cbm(lookup[pt], qty)
    return cbm, qty


# ── ELS M/H 계산 ──────────────────────────────────────────────────────────────
def calc_receiving(cbm: float) -> float:
    """입하 M/H — WERC 통합 (하차+qty확인+서류+staging), CBM-driven."""
    raw = cbm * RECV_MIN_PER_CBM
    return min(RECV_CAP_MIN, max(RECV_FLOOR_MIN, raw)) * PFD


def calc_qc() -> float:
    """검수 M/H — 시안검수 + 서류매칭·GR입력, 건당 고정. (2.5+1.5)×1.15=4.60분"""
    return (QC_MIN + QC_DOC_MIN) * PFD


def calc_putaway(cbm: float, qty: int) -> float:
    """입고 M/H — 이동+적치+스캔(CBM) + 표본검수(고정) + 수량확인(qty)."""
    extra    = min(PUTAWAY_CAP_MIN - PUTAWAY_BASE_MIN, cbm * PUTAWAY_PER_CBM_MIN) if cbm > 0 else 0.0
    movement = (PUTAWAY_BASE_MIN + extra) * PFD
    sample   = SAMPLE_QC_MIN
    counting = max(COUNTING_FLOOR_MIN, min(COUNTING_CAP_MIN, COUNTING_FLOOR_MIN + qty / COUNTING_PER_QTY))
    return movement + sample + counting


def calc_record_mh(fields: dict, lookup: dict) -> dict:
    """fields(by_field_id) → 백필 대상 6개 필드 dict."""
    cbm, qty   = resolve_cbm(fields, lookup)
    mh_recv    = calc_receiving(cbm)
    mh_qc      = calc_qc()
    mh_putaway = calc_putaway(cbm, qty)
    return {
        F["CBM"]:         round(cbm, 6),
        F["MH_입하"]:     round(mh_recv, 2),
        F["MH_검수"]:     round(mh_qc, 2),
        F["MH_입고"]:     round(mh_putaway, 2),
        F["MH_합계"]:     round(mh_recv + mh_qc + mh_putaway, 2),
        F["MH_상수버전"]: VERSION,
    }


# ── Airtable I/O ──────────────────────────────────────────────────────────────
def fetch_target_records(since=None, full=False, limit=None) -> list:
    """이동목적=생산산출 + 입하완료처리시간 있는 record 조회."""
    if not IBSA_PAT:
        sys.exit("ERROR: AIRTABLE_IBSA_PAT 미설정")

    conditions = [
        f"{{{F['이동목적']}}}='생산산출'",
        f"NOT({{{F['입하완료처리시간']}}}=BLANK())",
    ]
    if since:
        conditions.append(f"IS_AFTER({{{F['입하일자']}}},'{since}')")
    if not full:
        conditions.append(
            f"OR({{{F['MH_상수버전']}}}=BLANK(),{{{F['MH_상수버전']}}}!='{VERSION}')"
        )

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {IBSA_PAT}"})
    records, offset = [], None
    while True:
        params = {
            "pageSize": 100,
            "returnFieldsByFieldId": "true",
            "filterByFormula": "AND(" + ",".join(conditions) + ")",
            "fields[]": [
                F["movement_id"], F["입하수량"], F["제품_규격"],
                F["입하예정물품"], F["입하일자"], F["MH_상수버전"],
            ],
        }
        if offset:
            params["offset"] = offset
        resp = session.get(f"https://api.airtable.com/v0/{IBSA_BASE}/{IBSA_TABLE}",
                           params=params, timeout=90)
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


def batch_patch(updates: list, execute: bool) -> tuple[int, int]:
    """10건씩 PATCH. dry-run 시 (0, 0) 반환."""
    if not updates or not execute:
        return 0, 0
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {IBSA_PAT}",
                             "Content-Type": "application/json"})
    patched, errors = 0, 0
    for i in range(0, len(updates), 10):
        chunk = updates[i:i + 10]
        resp = session.patch(f"https://api.airtable.com/v0/{IBSA_BASE}/{IBSA_TABLE}",
                             json={"records": chunk, "typecast": False}, timeout=90)
        if resp.status_code != 200:
            print(f"  PATCH error {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
            errors += len(chunk)
        else:
            patched += len(chunk)
        time.sleep(0.25)
    return patched, errors


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="실제 PATCH (기본 dry-run)")
    ap.add_argument("--full",    action="store_true", help="전체 재계산 (버전 무시)")
    ap.add_argument("--since",   help="입하일자 시작 YYYY-MM-DD")
    ap.add_argument("--limit",   type=int, help="최대 건수 (테스트용)")
    args = ap.parse_args()

    print("=== mh_backfill_to_ibsa.py ===")
    print(f"  VERSION:    {VERSION}")
    print(f"  dry-run:    {not args.execute}")
    print(f"  full:       {args.full}")
    print(f"  since:      {args.since or '(none)'}")
    print(f"  limit:      {args.limit or '(none)'}")
    print()

    print("[1/4] sync_parts lookup 로드...")
    lookup = load_sync_parts_lookup()
    print(f"      loaded {len(lookup)} parts")

    print("[2/4] 대상 record 조회...")
    records = fetch_target_records(since=args.since, full=args.full, limit=args.limit)
    print(f"      {len(records)} records to process")
    if not records:
        print("처리할 record 없음 — 종료")
        return

    print("[3/4] M/H 계산...")
    updates = [{"id": r["id"], "fields": calc_record_mh(r.get("fields", {}), lookup)}
               for r in records]
    print(f"      computed {len(updates)} / skipped 0")

    print("\n  [preview] first 3 records:")
    for u in updates[:3]:
        flds = u["fields"]
        print(f"    {u['id']}: CBM={flds[F['CBM']]:.6f} "
              f"입하={flds[F['MH_입하']]:.2f} 검수={flds[F['MH_검수']]:.2f} "
              f"입고={flds[F['MH_입고']]:.2f} 합계={flds[F['MH_합계']]:.2f}")

    print(f"\n[4/4] {'PATCH 실행' if args.execute else 'PATCH dry-run (실행 X)'}")
    patched, errors = batch_patch(updates, execute=args.execute)
    if args.execute:
        print(f"      patched: {patched}  errors: {errors}")
    else:
        print(f"      would patch: {len(updates)}  (--execute 로 실제 실행)")

    print("\n=== 완료 ===")


if __name__ == "__main__":
    main()
