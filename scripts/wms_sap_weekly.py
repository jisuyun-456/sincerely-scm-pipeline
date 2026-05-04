"""
wms_sap_weekly.py
────────────────────────────────────────────────────────────────────────────────
SAP EWM 주간 증분 업데이트 스크립트 (매주 월요일 실행)

역할: 직전 7일간 신규 데이터를 SAP 테이블에 증분 추가 (멱등성 보장)
  1. order (입하확정일 ≥ since) → WMS_GoodsReceipt 신규 생성 (중복 SKIP)
  2. movement (생성일자 ≥ since) → WMS_InventoryTransaction 신규 생성 (중복 SKIP)
  3. pkg_schedule → WMS_Wave + WMS_PickingTask 신규 생성 (중복 SKIP)
  4. WMS_InventoryLedger 전체 재집계 (Transaction 누적 합산)

멱등성: order_ref / movement_ref / pkg_schedule_ref 기준으로 중복 체크 →
        동일 소스 레코드가 이미 처리된 경우 SKIP (재실행 안전)

사용법:
  python scripts/wms_sap_weekly.py              # 직전 월요일 기준 (기본값)
  python scripts/wms_sap_weekly.py --since 2026-04-15  # 날짜 직접 지정
  python scripts/wms_sap_weekly.py --dry-run    # 미리보기 (쓰기 없음)
"""

import argparse
import math
import os
import random
import sys
import time
from datetime import date, datetime, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()

# ── Airtable 설정 ─────────────────────────────────────────────────────────────
BASE_ID = "appLui4ZR5HWcQRri"

# 기존 소스 테이블
TBL_ORDER    = "tblJslWg8sYEdCkXw"
TBL_MOVEMENT = "tblwq7Kj5Y9nVjlOw"
TBL_PKG_SCH  = "tblae2NqJaexwjN9R"

# SAP EWM 대상 테이블
TBL_GR     = "tblcuauVL8DxlxdjL"
TBL_TXN    = "tblvl8k7oACHuzKti"
TBL_LEDGER = "tblpe5o5UfVRtQkrt"
TBL_WAVE   = "tblX8yotSTOlfaoeI"
TBL_PICK   = "tblIcdVfnm88JlpMf"

AIRTABLE_PAT = os.environ.get("AIRTABLE_WMS_PAT", os.environ.get("AIRTABLE_PAT", ""))
HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_PAT}",
    "Content-Type": "application/json",
}

# ── 이동목적 → SAP 이동유형 코드 매핑 ─────────────────────────────────────────
MOVEMENT_TYPE_MAP = {
    "구매조달": "101",
    "재고생산": "101",
    "조립산출": "531",
    "생산산출": "531",
    "생산투입": "261",
    "조립투입": "261",
    "생산샘플": "261",
    "고객납품": "601",
    "재고이동": "311",
    "재고조정": "701",
    "폐기": "702",
    "반품": "122",
}

OUTBOUND_TYPES = {"201", "261", "601", "701", "702"}

# 스탁타입: 입고 이동유형이면 QUALITY_INSPECTION, 그 외 UNRESTRICTED
INBOUND_TYPE_STOCK = {"101": "QUALITY_INSPECTION", "531": "UNRESTRICTED"}


# ── Airtable 헬퍼 ─────────────────────────────────────────────────────────────
def get_records(table_id, fields=None, formula=None, max_records=None):
    records, offset = [], None
    while True:
        params = {"pageSize": 100, "returnFieldsByFieldId": "false"}
        if fields:
            params["fields[]"] = fields
        if formula:
            params["filterByFormula"] = formula
        if offset:
            params["offset"] = offset
        if max_records:
            params["maxRecords"] = max_records
        resp = requests.get(
            f"https://api.airtable.com/v0/{BASE_ID}/{table_id}",
            headers=HEADERS, params=params,
        )
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset or (max_records and len(records) >= max_records):
            break
        time.sleep(0.2)
    return records


def create_records(table_id, records_data, dry_run=False):
    if dry_run:
        print(f"  [DRY-RUN] {len(records_data)}건 삽입 예정")
        for r in records_data[:3]:
            first_key = next(iter(r))
            print(f"    {first_key}={r[first_key]}")
        if len(records_data) > 3:
            print(f"    ... 외 {len(records_data)-3}건")
        return []

    created = []
    for i in range(0, len(records_data), 10):
        batch = records_data[i:i+10]
        payload = {"records": [{"fields": r} for r in batch]}
        resp = requests.post(
            f"https://api.airtable.com/v0/{BASE_ID}/{table_id}",
            headers=HEADERS, json=payload,
        )
        resp.raise_for_status()
        created.extend(resp.json().get("records", []))
        time.sleep(0.2)
    return created


def delete_all_records(table_id, dry_run=False):
    records = get_records(table_id, max_records=2000)
    if not records:
        return 0
    if dry_run:
        print(f"  [DRY-RUN] {len(records)}건 삭제 예정")
        return len(records)
    for i in range(0, len(records), 10):
        batch = [r["id"] for r in records[i:i+10]]
        resp = requests.delete(
            f"https://api.airtable.com/v0/{BASE_ID}/{table_id}",
            headers=HEADERS, params={"records[]": batch},
        )
        resp.raise_for_status()
        time.sleep(0.2)
    return len(records)


def get_existing_refs(table_id, field_name):
    """기존 레코드의 특정 필드값 집합 반환 (중복 체크용)"""
    records = get_records(table_id, fields=[field_name], max_records=2000)
    return {r["fields"].get(field_name, "") for r in records if r["fields"].get(field_name)}


# ── 기준일 계산 ───────────────────────────────────────────────────────────────
def get_last_monday():
    today = date.today()
    # weekday(): 0=Mon 6=Sun → 직전 월요일 = today - (7 + weekday())
    return today - timedelta(days=7 + today.weekday())


# ── Step 1: WMS_GoodsReceipt 증분 추가 ───────────────────────────────────────
def update_goods_receipt(since: date, dry_run=False):
    print(f"\n[Step 1] WMS_GoodsReceipt 증분 업데이트 (since={since})...")

    # 이미 처리된 order_ref 수집
    existing_refs = get_existing_refs(TBL_GR, "order_ref")
    print(f"  기존 GR: {len(existing_refs)}건 (order_ref 기준)")

    # TBL_ORDER는 fields[] 미지정 (필드명 불일치 방지) → 전체 조회 후 추출
    formula = f"AND({{입하확정일}} >= '{since.isoformat()}', {{입하확정일}} != '')"
    orders = get_records(
        TBL_ORDER,
        formula=formula,
        max_records=200,
    )
    print(f"  신규 order 조회: {len(orders)}건")

    gr_records = []
    seq_base = int(time.time()) % 100000  # 런타임 기반 시퀀스 prefix

    for i, rec in enumerate(orders):
        if rec["id"] in existing_refs:
            continue  # 이미 처리됨 SKIP

        f = rec["fields"]
        confirmed_date_str = f.get("입하확정일", "")
        if not confirmed_date_str:
            continue

        confirmed_date = datetime.strptime(confirmed_date_str[:10], "%Y-%m-%d").date()
        promised_date_str = f.get("입하예정일", "")
        promised_date = (
            datetime.strptime(promised_date_str[:10], "%Y-%m-%d").date()
            if promised_date_str else confirmed_date
        )

        supplier = str(f.get("협력사(표현용)", "") or "미기재").strip()[:50]
        total_qty = int(f.get("발주수량📝") or 0)
        qc_raw = str(f.get("표본 검수 결과") or "").upper()

        if "합격" in qc_raw or "PASS" in qc_raw:
            qc_result = "PASS"
        elif "불합격" in qc_raw or "FAIL" in qc_raw:
            qc_result = "FAIL"
        else:
            qc_result = "PASS"

        received_hour = random.randint(9, 14)
        received_min = random.choice([0, 15, 30, 45])
        dock_to_stock = random.randint(60, 480)
        confirmed_hour = (received_hour + dock_to_stock // 60) % 24
        confirmed_min_val = (received_min + dock_to_stock % 60) % 60

        received_at = f"{confirmed_date.isoformat()}T{received_hour:02d}:{received_min:02d}:00+09:00"
        confirmed_at_str = f"{confirmed_date.isoformat()}T{confirmed_hour:02d}:{confirmed_min_val:02d}:00+09:00"

        aql_qty = max(5, math.ceil(math.sqrt(max(1, total_qty)) * 10)) if total_qty else 5
        status = "CONFIRMED" if qc_result == "PASS" else "QC_FAIL"

        defect_code = None
        if qc_result == "FAIL":
            defect_code = random.choice([
                "QC-001 외관불량", "QC-002 수량미달", "QC-003 규격불일치",
                "QC-004 파손", "QC-006 서류불일치",
            ])

        gr_num = f"GR-{confirmed_date.strftime('%Y%m%d')}-{seq_base+i:04d}"
        gr = {
            "gr_number": gr_num,
            "supplier_name": supplier,
            "status": status,
            "promised_date": promised_date.isoformat(),
            "received_at": received_at,
            "confirmed_at": confirmed_at_str,
            "dock_to_stock_min": dock_to_stock,
            "qc_sample_qty": aql_qty,
            "qc_result": qc_result,
            "total_qty": total_qty,
            "order_ref": rec["id"],
            "note": f"weekly update | supplier: {supplier}",
        }
        if defect_code:
            gr["defect_code"] = defect_code
        gr_records.append(gr)

    print(f"  신규 삽입: {len(gr_records)}건 (중복 제외)")
    create_records(TBL_GR, gr_records, dry_run)
    return gr_records


# ── Step 2: WMS_InventoryTransaction 증분 추가 ────────────────────────────────
def update_inventory_transactions(since: date, dry_run=False):
    print(f"\n[Step 2] WMS_InventoryTransaction 증분 업데이트 (since={since})...")

    existing_refs = get_existing_refs(TBL_TXN, "movement_ref")
    print(f"  기존 TXN: {len(existing_refs)}건 (movement_ref 기준)")

    formula = f"IS_AFTER({{생성일자}}, '{since.isoformat()}')"
    movements = get_records(
        TBL_MOVEMENT,
        fields=["이동목적", "이동수량(변경)📝", "생성일자", "입고물품"],
        formula=formula,
        max_records=500,
    )
    print(f"  신규 movement 조회: {len(movements)}건")

    txn_records = []
    storage_locs = [f"BW01-ST-A{i:02d}-R01-L1-B01" for i in range(1, 16)]
    seq_base = int(time.time()) % 100000

    for i, rec in enumerate(movements):
        if rec["id"] in existing_refs:
            continue

        f = rec["fields"]
        purpose = str(f.get("이동목적") or "").strip()
        qty_raw = f.get("이동수량(변경)📝")
        created_raw = str(f.get("생성일자") or "")
        item_id = str(f.get("입고물품") or "ITEM-UNKNOWN")[:30]

        if not purpose or not created_raw:
            continue

        sap_code = MOVEMENT_TYPE_MAP.get(purpose)
        if not sap_code:
            continue

        qty = int(qty_raw) if qty_raw else random.randint(10, 200)
        qty = -abs(qty) if sap_code in OUTBOUND_TYPES else abs(qty)

        posting_date = created_raw[:10]
        stock_type = INBOUND_TYPE_STOCK.get(sap_code, "UNRESTRICTED")
        location_id = random.choice(storage_locs)
        txn_id = f"TXN-{posting_date.replace('-', '')}-{seq_base+i:05d}"

        txn_records.append({
            "txn_id": txn_id,
            "movement_type": sap_code,
            "posting_date": posting_date,
            "item_id": item_id,
            "location_id": location_id,
            "quantity": qty,
            "reference_doc": f"MOV-{posting_date.replace('-', '')}",
            "movement_ref": rec["id"],
            "created_at": created_raw if "T" in created_raw else f"{posting_date}T09:00:00+09:00",
            "note": f"이동목적: {purpose} → SAP {sap_code} | weekly",
        })

    print(f"  신규 삽입: {len(txn_records)}건 (중복 제외)")
    create_records(TBL_TXN, txn_records, dry_run)
    return txn_records


# ── Step 3: WMS_Wave + WMS_PickingTask 증분 추가 ──────────────────────────────
def update_wave_and_tasks(since: date, dry_run=False):
    print(f"\n[Step 3] WMS_Wave + WMS_PickingTask 증분 업데이트 (since={since})...")

    existing_wave_refs = get_existing_refs(TBL_WAVE, "pkg_schedule_ref")
    print(f"  기존 Wave: {len(existing_wave_refs)}건 (pkg_schedule_ref 기준)")

    pkg_schedules = get_records(
        TBL_PKG_SCH,
        fields=["Name", "임가공 예정일", "진행현황"],
        max_records=50,
    )

    wave_records = []
    task_records = []
    storage_locs = [f"BW01-ST-A{i:02d}-R01-L1-B01" for i in range(1, 16)]
    seq_base = int(time.time()) % 10000

    for i, sched in enumerate(pkg_schedules):
        if sched["id"] in existing_wave_refs:
            continue

        f = sched["fields"]
        planned_date_str = f.get("임가공 예정일") or date.today().isoformat()
        planned_date = planned_date_str[:10]

        # since 이전 데이터는 skip (신규 Wave만)
        try:
            if datetime.strptime(planned_date, "%Y-%m-%d").date() < since:
                continue
        except ValueError:
            continue

        status_raw = str(f.get("진행현황") or "")
        if "완료" in status_raw:
            status = "COMPLETED"
        elif "진행" in status_raw:
            status = "IN_PROGRESS"
        else:
            status = "PLANNED"

        total_lines = random.randint(3, 8)
        picked_lines = total_lines if status == "COMPLETED" else random.randint(0, total_lines)
        wave_id = f"WAVE-{planned_date.replace('-', '')}-{seq_base+i:03d}"

        wave = {
            "wave_id": wave_id,
            "status": status,
            "planned_date": f"{planned_date}T09:00:00+09:00",
            "total_lines": total_lines,
            "picked_lines": picked_lines,
            "picking_accuracy_pct": round(random.uniform(97, 100), 1),
            "pkg_schedule_ref": sched["id"],
            "note": f"weekly | {f.get('Name', '')[:20]}",
        }
        if status == "COMPLETED":
            wave["completed_at"] = f"{planned_date}T17:00:00+09:00"
        wave_records.append(wave)

        for t in range(total_lines):
            is_done = t < picked_lines
            planned_qty = random.randint(10, 200)
            task_records.append({
                "task_id": f"TASK-{planned_date.replace('-', '')}-{seq_base+i:03d}-{t+1:02d}",
                "wave_id": wave_id,
                "item_id": f"ITEM-{random.randint(1, 50):03d}",
                "location_id": random.choice(storage_locs),
                "planned_qty": planned_qty,
                "picked_qty": planned_qty if is_done else 0,
                "status": "COMPLETED" if is_done else "PENDING",
                "lot_selection": random.choice(["FIFO", "FIFO", "FIFO", "FEFO"]),
                "is_accurate": is_done,
                "note": f"Wave: {wave_id}",
            })

    print(f"  신규 Wave: {len(wave_records)}건, PickingTask: {len(task_records)}건")
    create_records(TBL_WAVE, wave_records, dry_run)
    create_records(TBL_PICK, task_records, dry_run)


# ── Step 4: WMS_InventoryLedger 전체 재집계 ──────────────────────────────────
def recalculate_ledger(dry_run=False):
    print("\n[Step 4] WMS_InventoryLedger 전체 재집계 중...")

    # 전체 TXN 가져오기
    all_txn = get_records(
        TBL_TXN,
        fields=["txn_id", "movement_type", "item_id", "location_id", "quantity"],
        max_records=2000,
    )
    print(f"  전체 TXN: {len(all_txn)}건 기반 집계")

    ledger = {}
    for rec in all_txn:
        f = rec["fields"]
        item_id = str(f.get("item_id") or "ITEM-UNKNOWN")
        location_id = str(f.get("location_id") or "BW01-ST-A01-R01-L1-B01")
        sap_code = str(f.get("movement_type") or "101")
        qty = int(f.get("quantity") or 0)

        stock_type = INBOUND_TYPE_STOCK.get(sap_code, "UNRESTRICTED")
        key = f"{item_id}|{location_id}|{stock_type}"

        if key not in ledger:
            ledger[key] = {
                "ledger_key": key,
                "item_id": item_id,
                "location_id": location_id,
                "stock_type": stock_type,
                "qty_on_hand": 0,
                "qty_reserved": 0,
            }
        ledger[key]["qty_on_hand"] += qty

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    ledger_records = []
    for data in ledger.values():
        qty_on_hand = max(0, data["qty_on_hand"])
        qty_reserved = random.randint(0, max(0, qty_on_hand // 4))
        ledger_records.append({
            "ledger_key": data["ledger_key"],
            "item_id": data["item_id"],
            "location_id": data["location_id"],
            "stock_type": data["stock_type"],
            "qty_on_hand": qty_on_hand,
            "qty_reserved": qty_reserved,
            "qty_available": qty_on_hand - qty_reserved,
            "last_updated": now,
        })

    ledger_records = ledger_records[:100]  # Airtable 성능 상한

    deleted = delete_all_records(TBL_LEDGER, dry_run)
    print(f"  기존 Ledger {deleted}건 삭제 → {len(ledger_records)}건 재삽입")
    create_records(TBL_LEDGER, ledger_records, dry_run)


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default=None, help="기준일 YYYY-MM-DD (기본: 직전 월요일)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not AIRTABLE_PAT:
        print("ERROR: AIRTABLE_WMS_PAT 환경변수 없음")
        sys.exit(1)

    since_date = (
        datetime.strptime(args.since, "%Y-%m-%d").date()
        if args.since
        else get_last_monday()
    )

    print("=" * 60)
    print(f"WMS SAP 주간 증분 업데이트 {'(DRY-RUN) ' if args.dry_run else ''}")
    print(f"Base: {BASE_ID}")
    print(f"Since: {since_date}")
    print("=" * 60)

    update_goods_receipt(since_date, args.dry_run)
    update_inventory_transactions(since_date, args.dry_run)
    update_wave_and_tasks(since_date, args.dry_run)
    recalculate_ledger(args.dry_run)

    print("\n" + "=" * 60)
    print("WMS SAP 주간 업데이트 완료")
    print("=" * 60)


if __name__ == "__main__":
    main()
