"""
wms_sap_backfill.py
────────────────────────────────────────────────────────────────────────────────
SAP EWM 기준 WMS 가상 데이터 백필 스크립트

역할:
  1. WMS_Location       — 베스트원/에이원센터 창고 로케이션 30개 생성 (1회성)
  2. WMS_SupplierSLA    — sync_partner 기반 공급사 SLA 20개 생성 (1회성)
  3. WMS_GoodsReceipt   — order 테이블 기반 최근 90일 입고 문서 50건 생성
  4. WMS_InventoryTransaction — movement 기반 SAP 이동유형 코드 변환 트랜잭션
  5. WMS_InventoryLedger — 트랜잭션 누적 집계로 현재고 원장 계산
  6. WMS_Wave           — pkg_schedule 기반 Wave 10개 생성
  7. WMS_PickingTask    — Wave 당 PickingTask 생성

사용법:
  python scripts/wms_sap_backfill.py              # 전체 실행
  python scripts/wms_sap_backfill.py --step loc   # 로케이션만
  python scripts/wms_sap_backfill.py --step sla   # SLA만
  python scripts/wms_sap_backfill.py --step gr    # GoodsReceipt만
  python scripts/wms_sap_backfill.py --step txn   # InventoryTransaction만
  python scripts/wms_sap_backfill.py --step led   # InventoryLedger만
  python scripts/wms_sap_backfill.py --step wave  # Wave + PickingTask만
  python scripts/wms_sap_backfill.py --dry-run    # 데이터 생성 미리보기 (저장 안 함)
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

# 기존 테이블
TBL_ORDER    = "tblJslWg8sYEdCkXw"
TBL_MOVEMENT = "tblwq7Kj5Y9nVjlOw"
TBL_PARTNER  = "tblXx85u5gNzK7zTf"
TBL_PKG_SCH  = "tblae2NqJaexwjN9R"

# 신규 SAP WMS 테이블
TBL_LOCATION = "tbl2y0m0rLkqp6VRs"
TBL_SLA      = "tblUB6YvY5dLc4XXt"
TBL_GR       = "tblcuauVL8DxlxdjL"
TBL_TXN      = "tblvl8k7oACHuzKti"
TBL_LEDGER   = "tblpe5o5UfVRtQkrt"
TBL_WAVE     = "tblX8yotSTOlfaoeI"
TBL_PICK     = "tblIcdVfnm88JlpMf"

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

# 입고 방향(양수 수량) 이동유형
INBOUND_TYPES = {"101", "531", "311"}
# 출고 방향(음수 수량) 이동유형
OUTBOUND_TYPES = {"201", "261", "601", "701", "702"}


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
            headers=HEADERS, params=params
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
            print(f"    {r}")
        if len(records_data) > 3:
            print(f"    ... 외 {len(records_data)-3}건")
        return []

    created = []
    for i in range(0, len(records_data), 10):
        batch = records_data[i:i+10]
        payload = {"records": [{"fields": r} for r in batch]}
        resp = requests.post(
            f"https://api.airtable.com/v0/{BASE_ID}/{table_id}",
            headers=HEADERS, json=payload
        )
        resp.raise_for_status()
        created.extend(resp.json().get("records", []))
        time.sleep(0.2)
    return created


def clear_table(table_id, dry_run=False):
    """기존 레코드 전체 삭제 (중복 방지)"""
    records = get_records(table_id, max_records=1000)
    if not records:
        return
    if dry_run:
        print(f"  [DRY-RUN] {len(records)}건 삭제 예정")
        return
    for i in range(0, len(records), 10):
        batch = [r["id"] for r in records[i:i+10]]
        params = {"records[]": batch}
        resp = requests.delete(
            f"https://api.airtable.com/v0/{BASE_ID}/{table_id}",
            headers=HEADERS, params=params
        )
        resp.raise_for_status()
        time.sleep(0.2)


# ── Step 1: WMS_Location 생성 ─────────────────────────────────────────────────
def backfill_locations(dry_run=False):
    print("\n[Step 1] WMS_Location 생성 중...")

    locations = []

    # 베스트원 창고
    zones = [
        ("INBOUND_STAGING", "IN", 3),
        ("QC_HOLD", "QC", 2),
        ("STORAGE", "ST", 15),
        ("ASSEMBLY", "AS", 4),
        ("OUTBOUND_STAGING", "OUT", 3),
    ]
    for zone_type, prefix, count in zones:
        for i in range(1, count + 1):
            loc_id = f"BW01-{prefix}-A{i:02d}-R01-L1-B01"
            locations.append({
                "location_id": loc_id,
                "zone_type": zone_type,
                "warehouse": "베스트원",
                "capacity": random.choice([50, 100, 200, 500]),
                "current_qty": 0,
                "is_active": True,
                "note": f"베스트원 {zone_type} 구역",
            })

    # 에이원센터 창고 (STORAGE 3개 추가)
    for i in range(1, 4):
        locations.append({
            "location_id": f"AO01-ST-A{i:02d}-R01-L1-B01",
            "zone_type": "STORAGE",
            "warehouse": "에이원센터",
            "capacity": 300,
            "current_qty": 0,
            "is_active": True,
            "note": "에이원센터 보관 구역",
        })

    clear_table(TBL_LOCATION, dry_run)
    created = create_records(TBL_LOCATION, locations, dry_run)
    print(f"  → {len(locations)}건 생성 완료")
    return locations


# ── Step 2: WMS_SupplierSLA 생성 ─────────────────────────────────────────────
def backfill_supplier_sla(dry_run=False):
    print("\n[Step 2] WMS_SupplierSLA 생성 중...")

    # sync_partner에서 실제 공급사 가져오기
    partners = get_records(TBL_PARTNER, fields=["Name"], max_records=30)
    partner_names = [p["fields"].get("Name", "") for p in partners if p["fields"].get("Name")]

    # 기본 공급사 목록 (sync_partner에서 가져온 것 + 알려진 공급사)
    known_suppliers = [
        ("주식회사 에벤에셀기업", "B", 7, 3),
        ("신명인쇄", "B", 7, 3),
        ("협력사 미기재", "C", 14, 7),
        ("파란마음", "A", 3, 2),
        ("대흥인쇄", "B", 7, 3),
        ("YG페이퍼", "A", 5, 2),
        ("동일포장", "B", 10, 5),
        ("삼성포장재", "B", 7, 3),
        ("한국인쇄", "C", 14, 7),
        ("신우포장", "B", 7, 3),
        ("대한팩키지", "A", 5, 2),
        ("국제인쇄", "B", 7, 4),
        ("서울패키지", "B", 10, 5),
        ("경기포장", "C", 14, 7),
        ("부산인쇄", "B", 7, 3),
        ("인천포장재", "A", 5, 2),
        ("광주인쇄", "B", 10, 5),
        ("대전패키지", "C", 14, 7),
        ("울산포장", "B", 7, 3),
        ("제주인쇄", "D", 21, 10),
    ]

    sla_records = []
    today = date.today().isoformat()

    for supplier_name, grade, std_days, urg_days in known_suppliers[:20]:
        # 등급별 현실적인 납기 준수율
        base_rate = {"A": 95.0, "B": 85.0, "C": 72.0, "D": 60.0}[grade]
        on_time_rate = round(base_rate + random.uniform(-5, 5), 1)

        sla_records.append({
            "supplier_name": supplier_name,
            "sla_grade": grade,
            "standard_days": std_days,
            "urgent_days": urg_days,
            "on_time_rate_pct": max(0, min(100, on_time_rate)),
            "last_reviewed": today,
            "note": f"SAP SLA 기준 등급 {grade} — 표준 {std_days}일 / 긴급 {urg_days}일",
        })

    clear_table(TBL_SLA, dry_run)
    create_records(TBL_SLA, sla_records, dry_run)
    print(f"  → {len(sla_records)}건 생성 완료")
    return sla_records


# ── Step 3: WMS_GoodsReceipt 생성 ─────────────────────────────────────────────
def backfill_goods_receipt(dry_run=False):
    print("\n[Step 3] WMS_GoodsReceipt 생성 중 (order 기반 최근 90일)...")

    # order 테이블에서 입하확정일이 있는 건 조회
    cutoff = (date.today() - timedelta(days=90)).isoformat()
    formula = f"AND({{입하확정일}} >= '{cutoff}', {{입하확정일}} != '')"

    orders = get_records(
        TBL_ORDER,
        fields=["order_id", "협력사(표현용)", "입하예정일", "입하확정일", "발주수량📝", "표본 검수 결과"],
        formula=formula,
        max_records=60,
    )
    print(f"  order 조회: {len(orders)}건")

    gr_records = []
    seq = 1
    today = date.today()

    for rec in orders[:50]:
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
        qc_raw = str(f.get("표본 검수 결과") or "PASS").upper()

        # QC 결과 매핑
        if "합격" in qc_raw or "pass" in qc_raw.lower():
            qc_result = "PASS"
        elif "불합격" in qc_raw or "fail" in qc_raw.lower():
            qc_result = "FAIL"
        else:
            qc_result = "PASS"

        # Dock-to-Stock 시뮬레이션 (당일 입하 기준 랜덤 시간)
        received_hour = random.randint(9, 14)
        received_min = random.choice([0, 15, 30, 45])
        dock_to_stock = random.randint(60, 480)  # 1h~8h
        confirmed_hour = (received_hour + dock_to_stock // 60) % 24
        confirmed_min_val = (received_min + dock_to_stock % 60) % 60

        received_at = f"{confirmed_date.isoformat()}T{received_hour:02d}:{received_min:02d}:00+09:00"
        confirmed_at = f"{confirmed_date.isoformat()}T{confirmed_hour:02d}:{confirmed_min_val:02d}:00+09:00"

        # AQL 샘플 수량 (ISO 2859 기준: ceil(√qty × 10), 최소 5)
        aql_qty = max(5, math.ceil(math.sqrt(max(1, total_qty)) * 10)) if total_qty else 5

        # 상태 결정
        status = "CONFIRMED" if qc_result == "PASS" else "QC_FAIL"

        # 불량코드 (FAIL인 경우만)
        defect_code = None
        if qc_result == "FAIL":
            defect_code = random.choice([
                "QC-001 외관불량", "QC-002 수량미달", "QC-003 규격불일치",
                "QC-004 파손", "QC-006 서류불일치"
            ])

        gr_num = f"GR-{confirmed_date.strftime('%Y%m%d')}-{seq:03d}"

        gr = {
            "gr_number": gr_num,
            "supplier_name": supplier,
            "status": status,
            "promised_date": promised_date.isoformat(),
            "received_at": received_at,
            "confirmed_at": confirmed_at,
            "dock_to_stock_min": dock_to_stock,
            "qc_sample_qty": aql_qty,
            "qc_result": qc_result,
            "total_qty": total_qty,
            "order_ref": rec["id"],
            "note": f"order_id: {f.get('order_id', '')}",
        }
        if defect_code:
            gr["defect_code"] = defect_code

        gr_records.append(gr)
        seq += 1

    clear_table(TBL_GR, dry_run)
    create_records(TBL_GR, gr_records, dry_run)
    print(f"  → {len(gr_records)}건 생성 완료")
    return gr_records


# ── Step 4: WMS_InventoryTransaction 생성 ────────────────────────────────────
def backfill_inventory_transactions(gr_records, dry_run=False):
    print("\n[Step 4] WMS_InventoryTransaction 생성 중 (movement 기반)...")

    # movement 테이블에서 최근 90일 이동 조회
    cutoff = (date.today() - timedelta(days=90)).isoformat()
    formula = f"IS_AFTER({{생성일자}}, '{cutoff}')"

    movements = get_records(
        TBL_MOVEMENT,
        fields=["이동목적", "이동수량(변경)📝", "생성일자", "입고물품"],
        formula=formula,
        max_records=200,
    )
    print(f"  movement 조회: {len(movements)}건")

    txn_records = []
    seq = 1

    # 로케이션 풀 (Storage 구역)
    storage_locs = [f"BW01-ST-A{i:02d}-R01-L1-B01" for i in range(1, 16)]

    for rec in movements[:200]:
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

        qty = int(qty_raw) if qty_raw else random.randint(10, 500)
        # 출고 방향이면 음수
        if sap_code in OUTBOUND_TYPES:
            qty = -abs(qty)
        else:
            qty = abs(qty)

        posting_date = created_raw[:10]
        location_id = random.choice(storage_locs)

        txn_id = f"TXN-{posting_date.replace('-', '')}-{seq:04d}"
        txn_records.append({
            "txn_id": txn_id,
            "movement_type": sap_code,
            "posting_date": posting_date,
            "item_id": item_id[:30],
            "location_id": location_id,
            "quantity": qty,
            "reference_doc": f"MOV-{posting_date.replace('-', '')}",
            "movement_ref": rec["id"],
            "created_at": created_raw if "T" in created_raw else f"{posting_date}T09:00:00+09:00",
            "note": f"이동목적: {purpose} → SAP {sap_code}",
        })
        seq += 1

    # GR 기반 101 트랜잭션 추가
    for gr in gr_records:
        if gr.get("status") == "CONFIRMED":
            posting_date = gr.get("promised_date", date.today().isoformat())
            txn_id = f"TXN-{posting_date.replace('-', '')}-{seq:04d}"
            txn_records.append({
                "txn_id": txn_id,
                "movement_type": "101",
                "posting_date": posting_date,
                "item_id": "ITEM-GR",
                "location_id": "BW01-IN-A01-R01-L1-B01",
                "quantity": gr.get("total_qty", 100),
                "reference_doc": gr.get("gr_number", ""),
                "movement_ref": gr.get("order_ref", ""),
                "created_at": gr.get("received_at", f"{posting_date}T09:00:00+09:00"),
                "note": f"GR 입고: {gr.get('gr_number', '')}",
            })
            seq += 1

    clear_table(TBL_TXN, dry_run)
    create_records(TBL_TXN, txn_records, dry_run)
    print(f"  → {len(txn_records)}건 생성 완료")
    return txn_records


# ── Step 5: WMS_InventoryLedger 생성 ─────────────────────────────────────────
def backfill_inventory_ledger(txn_records, dry_run=False):
    print("\n[Step 5] WMS_InventoryLedger 계산 중...")

    # item_id × location_id 별 누적 수량 계산
    ledger = {}
    for txn in txn_records:
        item_id = txn.get("item_id", "ITEM-UNKNOWN")
        location_id = txn.get("location_id", "BW01-ST-A01-R01-L1-B01")
        qty = int(txn.get("quantity", 0))
        sap_code = str(txn.get("movement_type", "101"))

        # 스탁타입 결정
        if sap_code == "101":
            stock_type = "QUALITY_INSPECTION"  # 입고 시 먼저 QI
        else:
            stock_type = "UNRESTRICTED"

        key = f"{item_id}|{location_id}|{stock_type}"
        if key not in ledger:
            ledger[key] = {
                "ledger_key": key,
                "item_id": item_id,
                "location_id": location_id,
                "stock_type": stock_type,
                "qty_on_hand": 0,
                "qty_reserved": 0,
                "last_txn_id": "",
            }
        ledger[key]["qty_on_hand"] += qty
        ledger[key]["last_txn_id"] = txn.get("txn_id", "")

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    ledger_records = []
    for key, data in ledger.items():
        qty_on_hand = max(0, data["qty_on_hand"])  # 음수 방지
        qty_reserved = random.randint(0, max(0, qty_on_hand // 4))
        ledger_records.append({
            "ledger_key": key,
            "item_id": data["item_id"],
            "location_id": data["location_id"],
            "stock_type": data["stock_type"],
            "qty_on_hand": qty_on_hand,
            "qty_reserved": qty_reserved,
            "qty_available": qty_on_hand - qty_reserved,
            "last_txn_id": data["last_txn_id"],
            "last_updated": now,
        })

    # 상위 100개만 (Airtable 성능 고려)
    ledger_records = ledger_records[:100]

    clear_table(TBL_LEDGER, dry_run)
    create_records(TBL_LEDGER, ledger_records, dry_run)
    print(f"  → {len(ledger_records)}건 생성 완료")
    return ledger_records


# ── Step 6: WMS_Wave + WMS_PickingTask 생성 ───────────────────────────────────
def backfill_wave_and_tasks(dry_run=False):
    print("\n[Step 6] WMS_Wave + WMS_PickingTask 생성 중 (pkg_schedule 기반)...")

    # pkg_schedule에서 최근 30일 건 조회
    cutoff = (date.today() - timedelta(days=30)).isoformat()
    pkg_schedules = get_records(
        TBL_PKG_SCH,
        fields=["Name", "임가공 예정일", "진행현황"],
        max_records=15,
    )
    print(f"  pkg_schedule 조회: {len(pkg_schedules)}건")

    wave_records = []
    task_records = []

    for i, sched in enumerate(pkg_schedules[:10]):
        f = sched["fields"]
        name = str(f.get("Name") or f"PKG-{i+1}")[:30]
        planned_date_str = f.get("임가공 예정일") or date.today().isoformat()
        planned_date = planned_date_str[:10] if planned_date_str else date.today().isoformat()

        status_raw = str(f.get("진행현황") or "")
        if "완료" in status_raw:
            status = "COMPLETED"
        elif "진행" in status_raw:
            status = "IN_PROGRESS"
        else:
            status = "PLANNED"

        total_lines = random.randint(3, 10)
        picked_lines = total_lines if status == "COMPLETED" else random.randint(0, total_lines)
        accuracy_pct = round(random.uniform(97, 100), 1)

        wave_id = f"WAVE-{planned_date.replace('-', '')}-{i+1:03d}"

        completed_at = None
        if status == "COMPLETED":
            completed_at = f"{planned_date}T17:00:00+09:00"

        wave = {
            "wave_id": wave_id,
            "status": status,
            "planned_date": f"{planned_date}T09:00:00+09:00",
            "total_lines": total_lines,
            "picked_lines": picked_lines,
            "picking_accuracy_pct": accuracy_pct,
            "pkg_schedule_ref": sched["id"],
            "note": f"pkg_schedule: {name}",
        }
        if completed_at:
            wave["completed_at"] = completed_at
        wave_records.append(wave)

        # PickingTask 생성 (Wave 당 total_lines개)
        storage_locs = [f"BW01-ST-A{j:02d}-R01-L1-B01" for j in range(1, 16)]
        for t in range(total_lines):
            task_id = f"TASK-{planned_date.replace('-', '')}-{i+1:02d}-{t+1:02d}"
            planned_qty = random.randint(10, 200)
            is_completed = (t < picked_lines)
            picked_qty = planned_qty if is_completed else 0

            task_records.append({
                "task_id": task_id,
                "wave_id": wave_id,
                "item_id": f"ITEM-{random.randint(1, 50):03d}",
                "location_id": random.choice(storage_locs),
                "planned_qty": planned_qty,
                "picked_qty": picked_qty,
                "status": "COMPLETED" if is_completed else "PENDING",
                "lot_selection": random.choice(["FIFO", "FIFO", "FIFO", "FEFO"]),
                "is_accurate": is_completed,
                "note": f"Wave: {wave_id}",
            })

    clear_table(TBL_WAVE, dry_run)
    clear_table(TBL_PICK, dry_run)
    create_records(TBL_WAVE, wave_records, dry_run)
    create_records(TBL_PICK, task_records, dry_run)
    print(f"  → Wave {len(wave_records)}건, PickingTask {len(task_records)}건 생성 완료")


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", choices=["loc", "sla", "gr", "txn", "led", "wave"], default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    dry_run = args.dry_run
    step = args.step

    if not AIRTABLE_PAT:
        print("ERROR: AIRTABLE_WMS_PAT 또는 AIRTABLE_PAT 환경변수 없음")
        sys.exit(1)

    print(f"WMS SAP 백필 시작 {'(DRY-RUN)' if dry_run else ''}")
    print(f"Base: {BASE_ID}")

    if not step or step == "loc":
        backfill_locations(dry_run)
    if not step or step == "sla":
        backfill_supplier_sla(dry_run)
    if not step or step == "gr":
        gr_records = backfill_goods_receipt(dry_run)
    else:
        gr_records = []
    if not step or step == "txn":
        if not gr_records:
            gr_records = []
        txn_records = backfill_inventory_transactions(gr_records, dry_run)
    else:
        txn_records = []
    if not step or step == "led":
        if not txn_records:
            txn_records = []
        backfill_inventory_ledger(txn_records, dry_run)
    if not step or step == "wave":
        backfill_wave_and_tasks(dry_run)

    print("\n✅ WMS SAP 백필 완료")


if __name__ == "__main__":
    main()
