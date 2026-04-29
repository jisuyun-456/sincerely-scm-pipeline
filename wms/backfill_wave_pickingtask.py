"""
WMS_Wave + WMS_PickingTask Backfill
-------------------------------------
Creates WMS_Wave and WMS_PickingTask records from logistics_release
records where 발송 상태 = "출하 완료".

Field format of 출고 품목 및 수량:
  "제품명 수량"   e.g. "올웨이즈양우산 490+2"
  "제품명 수량"   e.g. "스펙트럼컬러펜 300+2\n쇼핑백 300+1"
  PT codes are NOT present; Korean product names are used.
  Quantity is the main number before the '+' (additional qty is bonus, ignored).

Usage:
  python backfill_wave_pickingtask.py --dry-run   # inspect field values only
  python backfill_wave_pickingtask.py              # live run

Env: AIRTABLE_PAT (required)
"""

import sys, os, re, time, argparse
from collections import defaultdict
from datetime import datetime
import requests

sys.stdout.reconfigure(encoding="utf-8")

# ── Config ───────────────────────────────────────────────────────────────────
PAT      = os.environ["AIRTABLE_PAT"]
BASE_ID  = "appLui4ZR5HWcQRri"
HEADERS  = {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}
API_BASE = "https://api.airtable.com/v0"

# ── Table IDs ────────────────────────────────────────────────────────────────
TBL_LR   = "tbler5LBLxh8lcEPv"   # logistics_release
TBL_MAT  = "tblaRpZstW10EwDlo"   # material(parts-stock)
TBL_WAVE = "tblZucobzQu3CFCrR"   # WMS_Wave
TBL_TASK = "tblJpQcCJfIyB9Xf5"   # WMS_PickingTask

# ── logistics_release field IDs ───────────────────────────────────────────────
F_LR_STATUS = "fldqASGdE4wr2zOxG"   # 발송 상태 (singleSelect: "출하 완료")
F_LR_DATE   = "fldd30xmwJZgneRmT"   # 출고 요청일 (date)
F_LR_ITEMS  = "flddjsAgwAYNtwOnI"   # 출고 품목 및 수량 (multilineText)
F_LR_NAME   = "fldV4FMACOiYCv088"   # 프로젝트명 (multilineText)

# ── WMS_Wave field IDs ────────────────────────────────────────────────────────
F_WAV_ID    = "fldqOrsNaAqA0ttVb"
F_WAV_DATE  = "fldmTk2tlepvAzu42"
F_WAV_STAT  = "fldCwSRWdBEMvJEpk"   # singleSelect: PLANNED/IN_PROGRESS/COMPLETED/CANCELLED
F_WAV_OCNT  = "fldAF5vlawqBc4Yf8"   # Order_Count (number)
F_WAV_LINES = "fldldYw6tmfxu70hk"   # Total_Lines (number)
F_WAV_DONE  = "fldPTz5QyVWFDZmJp"   # Completed_Lines (number)
F_WAV_REF   = "fldUyvsHfOLYaXm4J"   # Order_Ref (singleLineText)
F_WAV_RATE  = "fldMb9S6CnjfZTQo5"   # Completion_Rate (number)

# ── WMS_PickingTask field IDs ─────────────────────────────────────────────────
F_TSK_ID    = "fld7oUeh7JTfBPutp"
F_TSK_WAVE  = "fldYkQ0W3lMEPEDEs"   # Wave_Link (multipleRecordLinks)
F_TSK_MAT   = "fld3udgtMClXamgt1"   # Material (multipleRecordLinks)
F_TSK_LOC   = "fldZkfusqTJ7J7Dy6"   # From_Location (multipleRecordLinks)
F_TSK_RQTY  = "fldu9uAidbUMwVtYe"   # Required_Qty (number)
F_TSK_PQTY  = "fldOnjDaEYQHbTVFb"   # Picked_Qty (number)
F_TSK_STAT  = "fldkpOdJUUY4HUUXA"   # Status: PENDING/IN_PROGRESS/COMPLETED/SHORT
F_TSK_METH  = "fldnK5MEcV1VU2IkA"   # Pick_Method: FIFO/FEFO

# ── material field IDs ────────────────────────────────────────────────────────
F_MAT_CODE  = "fldclYkWLmwrTzuF6"   # 파츠 코드 (PT코드)

# ── Constants ─────────────────────────────────────────────────────────────────
LOC_BW_OB  = "recBoNW2ElQ3ndsQi"   # BW01-OB-001


# ── Helpers ───────────────────────────────────────────────────────────────────
def _get(table_id, params):
    url = f"{API_BASE}/{BASE_ID}/{table_id}"
    r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def paginate(table_id, params):
    """Fetch all pages for a table query."""
    records = []
    p = dict(params)
    while True:
        data = _get(table_id, p)
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        p["offset"] = offset
        time.sleep(0.25)
    return records


def batch_post(table_id, rows, batch_size=10):
    """POST rows in batches of 10. Returns list of created record IDs."""
    url = f"{API_BASE}/{BASE_ID}/{table_id}"
    created_ids = []
    for i in range(0, len(rows), batch_size):
        chunk = rows[i:i + batch_size]
        payload = {"records": [{"fields": r} for r in chunk]}
        resp = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        if not resp.ok:
            print(f"  ERROR batch {i // batch_size}: {resp.text[:300]}")
        else:
            for rec in resp.json().get("records", []):
                created_ids.append(rec["id"])
        time.sleep(0.25)
    return created_ids


# ── Parser ────────────────────────────────────────────────────────────────────
# Actual field format (confirmed by dry-run):
#   "제품명 수량"          e.g. "올웨이즈양우산 490+2"
#   "제품명 수량+추가"     e.g. "스펙트럼컬러펜 300+2"  (main qty before '+')
#   "잔여분(...)"          → skip (remainder/bonus lines)
#   blank lines           → skip
#
# PT codes do NOT appear in this field. Material links will be empty.
# parse_items returns (item_name, qty) tuples — item_name is the Korean product name.

_RE_PT  = re.compile(r"(PT\d+)", re.IGNORECASE)
# Matches: optional leading text + first integer (the main qty)
_RE_LINE_QTY = re.compile(r"^(.+?)\s+(\d+)(?:\+\d+)?[\s]*$")
_SKIP_PREFIXES = ("잔여분", "잔여 분")


def parse_items(text):
    """
    Parse multilineText field and return list of (item_key, qty) tuples.

    item_key: PT코드 if present (e.g. "PT1234"), else stripped product name.
    Lines starting with 잔여분 or blank lines are skipped.
    """
    if not text:
        return []
    items = []
    for raw_line in str(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Skip 잔여분 lines
        if any(line.startswith(p) for p in _SKIP_PREFIXES):
            continue

        # Check for PT code first
        pt_m = _RE_PT.search(line)
        if pt_m:
            pt_code = pt_m.group(1).upper()
            remainder = line[pt_m.end():]
            qm = re.search(r"(\d+)", remainder)
            qty = int(qm.group(1)) if qm else 1
            items.append((pt_code, qty))
            continue

        # No PT code → parse Korean product name + quantity
        m = _RE_LINE_QTY.match(line)
        if m:
            item_name = m.group(1).strip()
            qty = int(m.group(2))
            items.append((item_name, qty))
        else:
            # Try to extract any trailing integer as qty=1 if no number found
            nm = re.search(r"(\d+)", line)
            qty = int(nm.group(1)) if nm else 1
            # Use the full line stripped of trailing numbers as name
            item_name = re.sub(r"\s*\d+.*$", "", line).strip() or line
            if item_name:
                items.append((item_name, qty))
    return items


# ── Step 1: material map ──────────────────────────────────────────────────────
def build_material_map():
    print("Loading material table...")
    recs = paginate(TBL_MAT, {
        "fields[]": [F_MAT_CODE],
        "pageSize": 100,
        "returnFieldsByFieldId": "true",
    })
    pt_map = {}
    for r in recs:
        code = r["fields"].get(F_MAT_CODE, "")
        if code and re.match(r"^PT\d+", str(code), re.IGNORECASE):
            pt_map[str(code).upper()] = r["id"]
    print(f"  {len(pt_map)} materials with PT codes")
    return pt_map


# ── Step 2: fetch existing Wave refs (idempotency) ───────────────────────────
def fetch_existing_wave_refs() -> set:
    """이미 생성된 Wave의 Order_Ref(LR record_id) 집합을 반환."""
    recs = paginate(TBL_WAVE, {
        "returnFieldsByFieldId": "true",
        "fields[]": [F_WAV_REF],
        "pageSize": 100,
    })
    return {r["fields"].get(F_WAV_REF, "") for r in recs if r["fields"].get(F_WAV_REF)}


# ── Step 3: fetch logistics_release 출하완료 ──────────────────────────────────
def fetch_lr_records():
    print("Fetching logistics_release (발송 상태 = 출하 완료)...")
    recs = paginate(TBL_LR, {
        "fields[]": [F_LR_STATUS, F_LR_DATE, F_LR_ITEMS, F_LR_NAME],
        "filterByFormula": f'{{발송 상태}}="출하 완료"',
        "pageSize": 100,
        "returnFieldsByFieldId": "true",
    })
    print(f"  {len(recs)} records found")
    return recs


# ── Dry-run mode ──────────────────────────────────────────────────────────────
def dry_run(lr_records):
    print("\n" + "=" * 60)
    print("DRY-RUN: 출고 품목 및 수량 필드 샘플 출력")
    print("=" * 60)

    total_items = 0
    matched_items = 0
    unmatched_pt = set()

    for i, r in enumerate(lr_records):
        f = r["fields"]
        rec_id   = r["id"]
        proj     = f.get(F_LR_NAME, "(unnamed)")
        req_date = f.get(F_LR_DATE, "(no date)")
        raw_text = f.get(F_LR_ITEMS, "")

        parsed = parse_items(raw_text)
        total_items += len(parsed)

        print(f"\n[{i+1}] {rec_id} | {proj} | {req_date}")
        print(f"  RAW: {repr(raw_text[:200])}")
        if parsed:
            print(f"  PARSED ({len(parsed)} items):")
            for item_key, qty in parsed:
                matched_items += 1
                prefix = "[PT]" if _RE_PT.match(item_key) else "[KO]"
                print(f"    {prefix} {item_key}  qty={qty}")
        else:
            print("  PARSED: (none)")
            if raw_text.strip():
                unmatched_pt.add(raw_text.strip()[:80])

    print("\n" + "=" * 60)
    print(f"Total LR records  : {len(lr_records)}")
    print(f"Total parsed items: {total_items}")
    if unmatched_pt:
        print(f"Samples with no PT: {len(unmatched_pt)}")
        for s in list(unmatched_pt)[:5]:
            print(f"  {repr(s)}")
    print("=" * 60)
    print("DRY-RUN complete. Review output above then run without --dry-run.")


# ── Live mode ──────────────────────────────────────────────────────────────────
def live_run(lr_records, pt_map):
    print("\n" + "=" * 60)
    print("LIVE RUN: Creating Wave + PickingTask records")
    print("=" * 60)

    # ── 멱등성 체크: 이미 처리된 LR record_id 스킵 ────────────────────────────
    print("Checking existing Wave records (idempotency)...")
    existing_refs = fetch_existing_wave_refs()
    print(f"  이미 처리된 Wave: {len(existing_refs)}건 (스킵)")

    # Track date-based sequence counters
    wave_seq  = defaultdict(int)   # date_str → next sequence num
    task_seq  = defaultdict(int)

    wave_rows  = []   # fields dicts for batch_post
    task_specs = []   # (wave_row_index, task_fields) — resolved after wave IDs known

    total_tasks       = 0
    matched_pt_items  = 0
    total_pt_items    = 0
    skipped_count     = 0

    for r in lr_records:
        if r["id"] in existing_refs:
            skipped_count += 1
            continue  # 이미 Wave 생성됨 → 스킵
        f       = r["fields"]
        rec_id  = r["id"]
        raw_date = f.get(F_LR_DATE, "")
        # Normalize date string → YYYY-MM-DD
        date_str = str(raw_date)[:10] if raw_date else datetime.now().strftime("%Y-%m-%d")
        date_compact = date_str.replace("-", "")   # YYYYMMDD for IDs

        raw_items = f.get(F_LR_ITEMS, "")
        parsed    = parse_items(raw_items)
        n_lines   = len(parsed)

        # ── Wave ──────────────────────────────────────────────────────────
        wave_seq[date_compact] += 1
        wave_id = f"WAV-{date_compact}-{wave_seq[date_compact]:03d}"

        completion_rate = 100.0 if n_lines > 0 else 0.0

        wave_fields = {
            F_WAV_ID:    wave_id,
            F_WAV_DATE:  date_str,
            F_WAV_STAT:  "COMPLETED",
            F_WAV_OCNT:  1,
            F_WAV_LINES: n_lines,
            F_WAV_DONE:  n_lines,
            F_WAV_REF:   rec_id,
            F_WAV_RATE:  completion_rate,
        }
        wave_idx = len(wave_rows)
        wave_rows.append(wave_fields)

        # ── PickingTask per parsed item ────────────────────────────────────
        for item_key, qty in parsed:
            total_pt_items += 1
            task_seq[date_compact] += 1
            task_id = f"TSK-{date_compact}-{task_seq[date_compact]:03d}"

            # item_key is a PT code if it starts with PT, else Korean product name
            mat_id = pt_map.get(item_key.upper()) if _RE_PT.match(item_key) else None
            if mat_id:
                matched_pt_items += 1

            task_fields = {
                F_TSK_ID:   task_id,
                # F_TSK_WAVE filled after wave creation
                F_TSK_LOC:  [LOC_BW_OB],
                F_TSK_RQTY: qty,
                F_TSK_PQTY: qty,
                F_TSK_STAT: "COMPLETED",
                F_TSK_METH: "FIFO",
            }
            if mat_id:
                task_fields[F_TSK_MAT] = [mat_id]

            task_specs.append((wave_idx, task_fields))
            total_tasks += 1

    print(f"\n  스킵 (이미 처리됨) : {skipped_count}건")
    print(f"  Wave rows prepared  : {len(wave_rows)}")
    print(f"  PickingTask rows    : {total_tasks}")
    if total_pt_items > 0:
        rate = matched_pt_items / total_pt_items * 100
        print(f"  PT match rate       : {matched_pt_items}/{total_pt_items} = {rate:.1f}%")

    # ── 생성할 Wave가 없으면 조기 종료 ────────────────────────────────────────
    if not wave_rows:
        print("\n  신규 생성할 Wave 없음 (모두 이미 처리됨). 종료.")
        return 0, 0, len(lr_records), 0.0

    # ── Batch create Waves ─────────────────────────────────────────────────
    print("\nCreating WMS_Wave records...")
    wave_ids = batch_post(TBL_WAVE, wave_rows)
    print(f"  Created {len(wave_ids)} Wave records")

    if len(wave_ids) != len(wave_rows):
        print(f"  !! Wave 배치 일부 실패: 요청 {len(wave_rows)}건 중 {len(wave_ids)}건만 생성됨")
        print("  PickingTask 생성 중단 (데이터 정합성 보호)")
        raise SystemExit(1)

    # ── Build PickingTask rows with wave links ─────────────────────────────
    task_rows = []
    for wave_idx, tf in task_specs:
        if wave_idx < len(wave_ids):
            tf[F_TSK_WAVE] = [wave_ids[wave_idx]]
        task_rows.append(tf)

    print("\nCreating WMS_PickingTask records...")
    task_ids = batch_post(TBL_TASK, task_rows)
    print(f"  Created {len(task_ids)} PickingTask records")

    match_pct = (matched_pt_items / total_pt_items * 100) if total_pt_items else 0.0

    print("\n" + "=" * 60)
    print("LIVE RUN complete")
    print(f"  Wave        : {len(wave_ids)} created")
    print(f"  PickingTask : {len(task_ids)} created")
    print(f"  PT match    : {matched_pt_items}/{total_pt_items} ({match_pct:.1f}%)")
    print("=" * 60)

    return len(wave_ids), len(task_ids), len(lr_records), match_pct


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="WMS Wave + PickingTask backfill")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print parsed items only; do not write to Airtable")
    args = parser.parse_args()

    if not PAT:
        raise SystemExit("ERROR: AIRTABLE_PAT env var not set")

    print("=" * 60)
    print("WMS Wave + PickingTask Backfill")
    print(f"Date  : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Mode  : {'DRY-RUN' if args.dry_run else 'LIVE'}")
    print("=" * 60)

    lr_records = fetch_lr_records()

    if not lr_records:
        print("No 출하 완료 records found. Nothing to do.")
        return

    if args.dry_run:
        dry_run(lr_records)
        return

    pt_map = build_material_map()
    n_waves, n_tasks, n_lr, match_pct = live_run(lr_records, pt_map)

    print(f"\nSUMMARY")
    print(f"  출하완료 대상  : {n_lr}건")
    print(f"  Wave 생성      : {n_waves}건")
    print(f"  PickingTask    : {n_tasks}건")
    print(f"  파서 매칭률    : {match_pct:.1f}%")


if __name__ == "__main__":
    main()
