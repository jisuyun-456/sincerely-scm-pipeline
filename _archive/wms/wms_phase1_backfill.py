"""
WMS Phase 1 Historical Backfill
--------------------------------
Creates WMS_InventoryTransaction and WMS_InventoryLedger records
by reading from the movement sync table and material table.

Run: python wms_phase1_backfill.py
Env: AIRTABLE_PAT must be set
"""

import os, time, re, math
from datetime import datetime, timedelta, timezone
import requests

# ── Config ──────────────────────────────────────────────────────────────────
PAT       = os.environ.get("AIRTABLE_PAT", "")
BASE_ID   = "appLui4ZR5HWcQRri"
HEADERS   = {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}
API_BASE  = "https://api.airtable.com/v0"

# Source tables
TABLE_MOVEMENT = "tblwq7Kj5Y9nVjlOw"
TABLE_MATERIAL = "tblaRpZstW10EwDlo"

# WMS tables
TABLE_TXN     = "tblmNiQDYzcq1A6vp"   # WMS_InventoryTransaction
TABLE_LEDGER  = "tbl4DcXQRHJj921MN"   # WMS_InventoryLedger
TABLE_LOC     = "tblRwUTP5kWnHFt5P"   # WMS_Location
TABLE_GR      = "tblFFrpYeHt58T59u"   # WMS_GoodsReceipt

# WMS_Location record IDs (seeded in Phase 0)
LOC = {
    "BW01-IB-001": "recf2n4NG79Q8dh2E",
    "BW01-ST-A01": "recN8X0ZsGL75xb0Q",
    "BW01-ST-A02": "recSqS8hsJXpP7jXY",
    "BW01-OB-001": "recBoNW2ElQ3ndsQi",
    "BW01-QH-001": "recKXQSSyJH3KIjwL",
    "BW01-QU-001": "recVAHU26RO1xcdeI",
    "A1-IB-001":   "rec0oHWSNxrcSH7Z2",
    "A1-ST-A01":   "recwIY0TxRPA6gNRz",
    "A1-ASSY-001": "recjwtN1kPCZNRerG",
    "A1-OB-001":   "recrh3eAADny08dlQ",
}

# 이동목적 → SAP Movement Type + sign (+/-) + description
MOVEMENT_MAP = {
    "재고이동":           ("311", +1, "창고간이동"),
    "재고조정":           ("701", +1, "재고조정"),
    "재고생산":           ("531", +1, "생산산출"),
    "생산투입":           ("261", -1, "생산투입"),
    "생산산출":           ("531", +1, "생산산출"),
    "생산샘플":           ("531", +1, "생산샘플"),
    "조립투입":           ("261", -1, "조립투입"),
    "조립산출":           ("531", +1, "조립산출"),
    "고객납품":           ("601", -1, "고객납품"),
    "생산이동":           ("311", +1, "생산이동"),
    "회수":               ("122", +1, "반품회수"),
    "MD샘플":             ("601", -1, "MD샘플출하"),
    "부자재":             ("501", +1, "무PO입하"),
    "고객물품":           ("501", +1, "고객물품입하"),
    "외주임가공":         ("311", -1, "외주임가공이동"),
    "리턴":               ("122", +1, "리턴반품"),
    "기타(메모에 입력)":  ("701",  0, "기타"),
    "CSO요청":            ("601", -1, "CSO출하"),
    "이슈로 협력사 회수": ("122", +1, "협력사회수"),
}

# ── Helpers ──────────────────────────────────────────────────────────────────
def airtable_get(table_id, params):
    url = f"{API_BASE}/{BASE_ID}/{table_id}"
    r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_all(table_id, fields, filter_formula=None, max_records=None):
    """Paginate through all records (or up to max_records)."""
    records = []
    params = {"fields[]": fields, "pageSize": 100}
    if filter_formula:
        params["filterByFormula"] = filter_formula
    if max_records:
        params["maxRecords"] = max_records

    while True:
        data = airtable_get(table_id, params)
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset or (max_records and len(records) >= max_records):
            break
        params["offset"] = offset
        time.sleep(0.2)
    return records


def batch_create(table_id, records, batch_size=10):
    """Create records in batches of 10 (Airtable limit)."""
    url = f"{API_BASE}/{BASE_ID}/{table_id}"
    created = 0
    for i in range(0, len(records), batch_size):
        chunk = records[i:i + batch_size]
        payload = {"records": [{"fields": r} for r in chunk]}
        r = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        if not r.ok:
            print(f"  ERROR batch {i//batch_size}: {r.text[:200]}")
        else:
            created += len(chunk)
        time.sleep(0.25)
    return created


def extract_pt_code(moving_items_text):
    """Extract PT code from 이동물품 field, e.g. 'PT1373-...' → 'PT1373'."""
    if not moving_items_text:
        return None
    parts = str(moving_items_text).strip().split("-")
    if parts and re.match(r"^PT\d+$", parts[0]):
        return parts[0]
    return None


def get_qty(fields, sign, movement_purpose):
    """Determine Qty_Change based on movement type."""
    # Field IDs in movement table
    입하수량   = fields.get("fldV8kVokQqMIsif0", 0) or 0
    출고수량   = fields.get("fld0XSbknPnJfOYOT", 0) or 0
    반입수량   = fields.get("fldjQX03iIsT1UATv", 0) or 0
    이동수량   = fields.get("fld8i5WLz1UNmzvvB", 0) or 0
    입고수량   = fields.get("fldlJt3RPY6E8JB4G", 0) or 0

    if sign > 0:
        qty = 반입수량 or 입하수량 or 입고수량 or 이동수량
    elif sign < 0:
        qty = 출고수량 or 이동수량 or 입하수량
    else:
        qty = 이동수량
    return qty * sign


def location_for_purpose(purpose, 입하장소, 출하장소):
    """Infer To/From location record IDs based on 이동목적."""
    # Map warehouse names to location IDs
    def map_loc(name):
        if not name:
            return None
        n = str(name)
        if "에이원" in n:
            return LOC["A1-ST-A01"]
        if "베스트원" in n or "best" in n.lower():
            return LOC["BW01-ST-A01"]
        return None

    to_loc   = map_loc(입하장소)
    from_loc = map_loc(출하장소)

    # Override for specific types
    if purpose in ("생산산출", "조립산출", "재고생산", "생산샘플"):
        to_loc = to_loc or LOC["A1-IB-001"]
        from_loc = from_loc or LOC["A1-ASSY-001"]
    elif purpose in ("생산투입", "조립투입", "외주임가공"):
        from_loc = from_loc or LOC["A1-ST-A01"]
        to_loc   = to_loc   or LOC["A1-ASSY-001"]
    elif purpose in ("고객납품", "MD샘플", "CSO요청"):
        from_loc = from_loc or LOC["BW01-OB-001"]
    elif purpose in ("부자재", "고객물품"):
        to_loc = to_loc or LOC["BW01-IB-001"]
    elif purpose in ("회수", "리턴", "이슈로 협력사 회수"):
        to_loc = to_loc or LOC["BW01-QH-001"]
    elif purpose == "재고이동":
        from_loc = from_loc or LOC["BW01-ST-A01"]
        to_loc   = to_loc   or LOC["BW01-ST-A02"]

    return to_loc, from_loc


# ── Step 1: Build material PT code → record_id map ───────────────────────────
def build_material_map():
    print("Loading material(parts-stock) table...")
    recs = fetch_all(
        TABLE_MATERIAL,
        fields=["fldclYkWLmwrTzuF6",  # 파츠 코드
                "fldAFkM4HtGJsitOk",  # 전산재고수량
                "fld5XQQv2P9YJZP6n",  # 실물재고수량
                "fldZ5qLZKp0yy28So",  # 가용재고수량
                "fldsDSdkogmJ0qsVC"], # 좌표(coordinates)
    )
    pt_map = {}   # PT코드 → {record_id, 전산재고수량, 실물재고수량, 가용재고수량}
    for r in recs:
        f = r["fields"]
        code = f.get("fldclYkWLmwrTzuF6", "")
        if code and re.match(r"^PT\d+", code):
            pt_map[code] = {
                "id":   r["id"],
                "전산": f.get("fldAFkM4HtGJsitOk", 0) or 0,
                "실물": f.get("fld5XQQv2P9YJZP6n", 0) or 0,
                "가용": f.get("fldZ5qLZKp0yy28So", 0) or 0,
            }
    print(f"  {len(pt_map)} materials with PT codes")
    return pt_map


# ── Step 2: WMS_InventoryTransaction backfill (last 30 days) ─────────────────
def backfill_transactions(pt_map, days=30):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    filter_formula = f"IS_AFTER({{생성일자}}, '{cutoff}')"

    print(f"\nLoading movement records (last {days} days)...")
    recs = fetch_all(
        TABLE_MOVEMENT,
        fields=[
            "fldOhFtJFBYsxxre7",  # movement_id
            "fldwZKCYZ4IFOigRp",  # 이동물품
            "fldFRNxG1pNooEOC7",  # 이동목적
            "fldV8kVokQqMIsif0",  # 입하수량
            "fld0XSbknPnJfOYOT",  # 출고수량
            "fld8i5WLz1UNmzvvB",  # 이동수량(변경)
            "fldjQX03iIsT1UATv",  # 반입수량
            "fldlJt3RPY6E8JB4G",  # 입고수량
            "flduN8khmYwdn7uVD",  # 실제입하일
            "fldDXUAF4JOORLJ2v",  # 생성일자
            "fldCvFgo3U6mdufWB",  # 입하장소
            "fldz7ZLrZw7inalHz",  # 출하장소
            "fldg9uQvxM8esINDP",  # order
            "fldwgaM8OnKubM8oE",  # 취소 여부
        ],
        filter_formula=filter_formula,
    )
    print(f"  {len(recs)} movement records in last {days} days")

    to_create = []
    skipped   = 0
    txn_counter = 1

    today_str = datetime.now().strftime("%Y%m%d")

    for r in recs:
        f = r["fields"]

        # Skip cancelled
        cancel = f.get("fldwgaM8OnKubM8oE", {})
        if isinstance(cancel, dict) and cancel.get("name") == "취소":
            skipped += 1
            continue

        purpose_obj = f.get("fldFRNxG1pNooEOC7", {})
        purpose = purpose_obj.get("name") if isinstance(purpose_obj, dict) else purpose_obj
        if not purpose or purpose not in MOVEMENT_MAP:
            skipped += 1
            continue

        sap_type, sign, desc = MOVEMENT_MAP[purpose]
        qty = get_qty(f, sign, purpose)
        if qty == 0:
            skipped += 1
            continue

        # Material link
        pt_code  = extract_pt_code(f.get("fldwZKCYZ4IFOigRp", ""))
        mat_info = pt_map.get(pt_code) if pt_code else None
        mat_link = [mat_info["id"]] if mat_info else []

        # Date
        txn_date = (f.get("flduN8khmYwdn7uVD") or
                    str(f.get("fldDXUAF4JOORLJ2v", ""))[:10] or
                    datetime.now().strftime("%Y-%m-%d"))
        txn_date = str(txn_date)[:10]  # keep YYYY-MM-DD only

        # Locations
        to_loc, from_loc = location_for_purpose(
            purpose,
            f.get("fldCvFgo3U6mdufWB", ""),
            f.get("fldz7ZLrZw7inalHz", ""),
        )

        txn_id = f"TXN-{today_str}-{txn_counter:05d}"
        txn_counter += 1

        row = {
            "fld9CtrWq70Tw5t1G": txn_id,          # TXN_ID
            "fldQvRBk8SXVwF9wg": sap_type,         # Movement_Type (singleSelect)
            "fldrXLvg0FtbjLNop": desc,              # Movement_Desc
            "fldBudFsApmx3V9cW": txn_date,          # TXN_Date
            "flduvvNFtbSNScVGB": qty,               # Qty_Change
            "fldGAeLHZN9QCwz2B": r["fields"].get("fldOhFtJFBYsxxre7", ""),  # Source_Movement_ID
            "fldOQSCy0NE3yBWUW": r["fields"].get("fldg9uQvxM8esINDP", ""),  # Reference_Doc
        }
        if mat_link:
            row["fldY4hrRmqkM2Kt6F"] = mat_link    # Material
        if to_loc:
            row["fldHOodsMi7kPQ8Bw"] = [to_loc]    # To_Location
        if from_loc:
            row["fldSYUa88zLdNn1Jz"] = [from_loc]  # From_Location

        to_create.append(row)

    print(f"  Creating {len(to_create)} transactions (skipped {skipped})...")
    created = batch_create(TABLE_TXN, to_create)
    print(f"  Done: {created} WMS_InventoryTransaction records created")
    return to_create


# ── Step 3: WMS_InventoryLedger snapshot ─────────────────────────────────────
def backfill_ledger(pt_map):
    print("\nBuilding WMS_InventoryLedger snapshot from material table...")

    week_str = datetime.now().strftime("%Y-W%V")  # e.g. 2026-W18
    today_str = datetime.now().strftime("%Y-%m-%d")

    # Default location: 베스트원 STORAGE
    default_loc = LOC["BW01-ST-A01"]
    a1_loc      = LOC["A1-ST-A01"]

    to_create = []
    for pt_code, info in pt_map.items():
        전산재고 = info["전산"]
        실물재고 = info["실물"]
        if 전산재고 == 0 and 실물재고 == 0:
            continue  # Skip zero-stock items

        stock_qty = 실물재고 if 실물재고 > 0 else 전산재고

        ledger_key = f"{pt_code}|BW01-ST-A01|UNRESTRICTED"
        row = {
            "fldUxFrOMgWewhwuv": ledger_key,                # Ledger_Key
            "fldOD1BqKtTKNGstu": [info["id"]],              # Material
            "fldW7C7Yq6kgtBNAe": [default_loc],             # Location
            "fldO5uuXHnftxmaAy": "UNRESTRICTED",            # Stock_Type
            "flde9K3lpJMl3piBN": stock_qty,                  # Opening_Qty
            "fldMCNFaUBRWgiPQc": 0,                          # Total_In
            "fldzeUfyVlEPaaqYf": 0,                          # Total_Out
            "fldK0ivn2inlOaIZU": week_str,                   # Snapshot_Week
            "fldv3QSNKS6iw3e0A": today_str,                  # Last_Movement_Date
            "fldrYLzhViYk9xc4P": stock_qty,                  # Current_Stock
        }
        to_create.append(row)

    print(f"  Creating {len(to_create)} ledger records...")
    created = batch_create(TABLE_LEDGER, to_create)
    print(f"  Done: {created} WMS_InventoryLedger records created")


# ── Step 4: WMS_NCR from quality issues ──────────────────────────────────────
def backfill_ncr(pt_map, days=90):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    filter_formula = (
        f"AND("
        f"IS_AFTER({{생성일자}}, '{cutoff}'), "
        f"{{품질 이슈 리포팅}}=1"
        f")"
    )

    print(f"\nLoading quality-issue movement records (last {days} days)...")
    recs = fetch_all(
        TABLE_MOVEMENT,
        fields=[
            "fldOhFtJFBYsxxre7",  # movement_id
            "fldwZKCYZ4IFOigRp",  # 이동물품
            "fldDXUAF4JOORLJ2v",  # 생성일자
            "fld3lQvblfrqTl4O8",  # 불량수량_샘플링검수
            "fldsTXzxUeerw4qw2",  # 불량수량_전수검수
            "fld0ZtsqLg4HIM4zg",  # 품질이슈내용
            "fldhah8PRdngeDvYY",  # 품질이슈내용구분
        ],
        filter_formula=filter_formula,
    )
    print(f"  {len(recs)} quality-issue records")

    TABLE_NCR = "tblMODxFEWpkKWG4Y"
    today_str = datetime.now().strftime("%Y%m%d")

    to_create = []
    for i, r in enumerate(recs):
        f = r["fields"]
        pt_code  = extract_pt_code(f.get("fldwZKCYZ4IFOigRp", ""))
        mat_info = pt_map.get(pt_code) if pt_code else None
        mat_link = [mat_info["id"]] if mat_info else []

        defect_qty = (f.get("fld3lQvblfrqTl4O8") or
                      f.get("fldsTXzxUeerw4qw2") or 0)

        detect_date = str(f.get("fldDXUAF4JOORLJ2v", ""))[:10]

        issue_content = f.get("fld0ZtsqLg4HIM4zg", "")
        issue_type_obj = f.get("fldhah8PRdngeDvYY", {})
        issue_type = issue_type_obj.get("name") if isinstance(issue_type_obj, dict) else ""

        # Map to defect code
        defect_code = "QC-007 기타"
        if "수량" in str(issue_type) or "수량" in str(issue_content):
            defect_code = "QC-001 수량부족"
        elif "외관" in str(issue_type) or "외관" in str(issue_content):
            defect_code = "QC-002 외관불량"
        elif "규격" in str(issue_type) or "사이즈" in str(issue_content):
            defect_code = "QC-003 규격불일치"
        elif "오염" in str(issue_content) or "이물" in str(issue_content):
            defect_code = "QC-004 오염·이물"
        elif "인쇄" in str(issue_type) or "색" in str(issue_content):
            defect_code = "QC-005 인쇄불량"
        elif "포장" in str(issue_type) or "박스" in str(issue_content):
            defect_code = "QC-006 포장불량"

        ncr_id = f"NCR-{today_str}-{i+1:04d}"
        row = {
            "fld93Fagb87nX8koG": ncr_id,                    # NCR_ID
            "fldywyXZbxkgY5FUR": defect_code,               # Defect_Code
            "fldhBzrL7jx7TEbon": defect_qty,                # Defect_Qty
            "fldliElDm2UTh2QMm": detect_date,               # Detection_Date
            "fld6w8QPuPER9pmvV": "ACCEPT_AS_IS",            # Disposition (default)
            "fldI2sJOYXfVrwyds": "CLOSED",                  # Status
            "fldlDAIF5BcORPGMb": str(issue_content)[:500],  # Root_Cause
        }
        if mat_link:
            row["fldCJ7kIxQWo5DYju"] = mat_link             # Material
        to_create.append(row)

    print(f"  Creating {len(to_create)} NCR records...")
    created = batch_create(TABLE_NCR, to_create)
    print(f"  Done: {created} WMS_NCR records created")


# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not PAT:
        raise SystemExit("ERROR: AIRTABLE_PAT env var not set")

    print("=" * 60)
    print("WMS Phase 1 Backfill")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    pt_map = build_material_map()

    backfill_transactions(pt_map, days=30)
    backfill_ledger(pt_map)
    backfill_ncr(pt_map, days=90)

    print("\n✓ Phase 1 backfill complete")
