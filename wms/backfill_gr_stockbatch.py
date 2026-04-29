"""
WMS_GoodsReceipt + WMS_StockBatch backfill
Source: txn_batches.json의 501 입하(무PO) 109건 → movement 레코드 조회 → GR+Batch 생성
"""
import json, sys, time, urllib.request, urllib.error
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

PAT = "***REDACTED_PAT***"
BASE = "appLui4ZR5HWcQRri"
MOVEMENT_TBL = "tblwq7Kj5Y9nVjlOw"
GR_TBL = "tblFFrpYeHt58T59u"
BATCH_TBL = "tblvkbRU1GfgI6Bul"
DEFAULT_LOCATION = "recN8X0ZsGL75xb0Q"  # 기본 입하위치 (WMS_Location)

BATCH_FILE = r"C:\Users\yjisu\Desktop\SCM_WORK\wms\txn_batches.json"

# WMS_GoodsReceipt 필드 IDs
GR_FIELDS = {
    "GR_ID":            "fldaJPmfoZ1wbrKwh",
    "GR_Date":          "fldjXHg5ZB1xiUAFA",
    "Supplier_Name":    "fldIzDHylct9N6Qeu",
    "Order_Ref":        "fldGdLPx6YzROuSJW",
    "Movement_Type":    "fldeWZBSZOtuYTwqp",
    "Expected_Arrival": "fld59DlanUhwmu0hX",
    "Actual_Arrival":   "fldlUW4Q16wj2MZUY",
    "Expected_Qty":     "fldHizjVLF6ejjNXC",
    "Received_Qty":     "fldnscUm2LgELFntU",
    "QC_Result":        "fldNQ8SPFRs6GLv5c",
    "Put_Away_Location":"fldDmqpGSOl0V9wWc",
    "Remarks":          "fldfT4lYJgiIMdy7z",
}

# WMS_StockBatch 필드 IDs
SB_FIELDS = {
    "Batch_ID":        "fldQ5qRL55XT0jLkS",
    "GR_Link":         "fldrYH63eXR52fMGF",
    "Material":        "fldMQ8fchJdWOFcm7",
    "Inbound_Date":    "fld6zHPlJbUzo608M",
    "Received_Qty":    "fldgCNI2A3fs2V0wL",
    "Current_Qty":     "fld2Vs15foy68zSRj",
    "Location":        "flda5tejCqv6lAArp",
    "Status":          "fld7elLdcLcPzy9OV",
    "Created_At":      "fldqsvSejPFZDos8Z",
    "WMS_GoodsReceipt":"fldoVWFcAAkNPa2fk",
}


def api_get(path, timeout=30):
    url = f"https://api.airtable.com/v0/{BASE}/{path}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {PAT}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def api_post(table, records, timeout=30):
    payload = json.dumps(
        {"records": [{"fields": r} for r in records]},
        ensure_ascii=True
    ).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.airtable.com/v0/{BASE}/{table}",
        data=payload,
        headers={"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:300]}"


def to_datetime(date_str):
    """날짜 문자열 → Airtable dateTime 포맷 (UTC 00:00)"""
    if not date_str:
        return None
    try:
        # 형식: "2026-04-03" or "4/8/2026"
        if "/" in date_str:
            parts = date_str.split("/")
            return f"20{parts[2][-2:]}-{parts[0].zfill(2)}-{parts[1].zfill(2)}T00:00:00.000Z"
        return f"{date_str}T00:00:00.000Z"
    except Exception:
        return None


def extract_supplier(items_field):
    """이동물품 'PT...-명칭 || 공급업체명' → 공급업체명"""
    if not items_field:
        return "미상"
    if "||" in items_field:
        return items_field.split("||")[-1].strip()
    return items_field.strip()


def map_qc(status):
    if not status:
        return "PASS"
    s = str(status)
    if "완료" in s or "합격" in s:
        return "PASS"
    if "불합격" in s or "실패" in s or "FAIL" in s:
        return "FAIL"
    if "부분" in s or "PARTIAL" in s:
        return "PARTIAL_PASS"
    return "PASS"


# ──────────────────────────────────────────────
# STEP 1: txn_batches에서 501 입하 레코드 수집
# ──────────────────────────────────────────────
print("STEP 1: txn_batches.json에서 501 입하 레코드 수집")
with open(BATCH_FILE, encoding="utf-8") as f:
    batches = json.load(f)

inbound_txns = []
for batch in batches:
    for r in batch:
        if "501" in r.get("fldrXLvg0FtbjLNop", ""):
            inbound_txns.append(r)

print(f"  501 입하 레코드: {len(inbound_txns)}건")

# Source_Movement_ID별로 그룹화 (중복 제거)
src_map = {}  # src_movement_id → txn record
for r in inbound_txns:
    sid = r.get("fldGAeLHZN9QCwz2B")
    if sid and sid not in src_map:
        src_map[sid] = r

print(f"  고유 movement 레코드: {len(src_map)}개")
print()


# ──────────────────────────────────────────────
# STEP 2: 각 movement 레코드 조회 → GR 데이터 구성
# ──────────────────────────────────────────────
print("STEP 2: movement 레코드 조회")
gr_data = []  # list of (gr_fields_dict, material_id, src_txn_date)

for i, (sid, txn) in enumerate(src_map.items()):
    try:
        rec = api_get(f"{MOVEMENT_TBL}/{sid}")
        f = rec["fields"]

        supplier = extract_supplier(f.get("이동물품", ""))
        actual_date = f.get("실제입하일", txn.get("fldBudFsApmx3V9cW", ""))
        expected_date = f.get("입하예상일") or f.get("납기일_개별", "")
        expected_qty = int(f.get("계획수량") or f.get("이동수량_예정") or 0)
        received_qty = int(f.get("입하수량") or f.get("이동수량(변경)📝") or txn.get("flduvvNFtbSNScVGB", 0))
        order_ref = str(f.get("order", "")) if f.get("order") else ""
        qc_status = f.get("검수 status", "")
        qc_result = map_qc(qc_status)

        # Material link from txn (optional)
        material_ids = txn.get("fldY4hrRmqkM2Kt6F")  # list of rec IDs

        gr_data.append({
            "actual_date": actual_date,
            "expected_date": expected_date,
            "supplier": supplier,
            "order_ref": order_ref,
            "expected_qty": expected_qty,
            "received_qty": received_qty,
            "qc_result": qc_result,
            "material_ids": material_ids,
        })

        if (i + 1) % 20 == 0:
            print(f"  조회 {i+1}/{len(src_map)}")
        time.sleep(0.21)

    except Exception as e:
        print(f"  [WARN] {sid}: {e}")
        gr_data.append({
            "actual_date": txn.get("fldBudFsApmx3V9cW", ""),
            "expected_date": "",
            "supplier": "미상",
            "order_ref": "",
            "expected_qty": 0,
            "received_qty": int(txn.get("flduvvNFtbSNScVGB", 0)),
            "qc_result": "PASS",
            "material_ids": None,
        })
        time.sleep(0.21)

print(f"  완료: {len(gr_data)}건 GR 데이터 구성")
print()


# ──────────────────────────────────────────────
# STEP 3: GR 날짜 기준 정렬 + GR_ID 부여
# ──────────────────────────────────────────────
print("STEP 3: GR 데이터 정렬 + ID 부여")

def sort_key(d):
    dt = d.get("actual_date") or "9999-12-31"
    if "/" in dt:
        parts = dt.split("/")
        return f"{parts[2][-4:]}-{parts[0].zfill(2)}-{parts[1].zfill(2)}"
    return dt

gr_data.sort(key=sort_key)

for i, d in enumerate(gr_data):
    date_str = d["actual_date"] or "20260101"
    if "/" in date_str:
        parts = date_str.split("/")
        date_compact = f"{parts[2][-4:]}{parts[0].zfill(2)}{parts[1].zfill(2)}"
    else:
        date_compact = date_str.replace("-", "")
    d["gr_id"] = f"GR-{date_compact}-{i+1:03d}"

print(f"  GR ID 범위: {gr_data[0]['gr_id']} ~ {gr_data[-1]['gr_id']}")
print()


# ──────────────────────────────────────────────
# STEP 4: WMS_GoodsReceipt 생성
# ──────────────────────────────────────────────
print("STEP 4: WMS_GoodsReceipt 생성")
gr_records_to_create = []
for d in gr_data:
    fields = {
        GR_FIELDS["GR_ID"]:         d["gr_id"],
        GR_FIELDS["Movement_Type"]: "501",
        GR_FIELDS["QC_Result"]:     d["qc_result"],
        GR_FIELDS["Put_Away_Location"]: [DEFAULT_LOCATION],
    }
    if d["actual_date"]:
        fields[GR_FIELDS["GR_Date"]] = d["actual_date"] if "-" in d["actual_date"] else None
        fields[GR_FIELDS["Actual_Arrival"]] = to_datetime(d["actual_date"])
    if d["expected_date"]:
        fields[GR_FIELDS["Expected_Arrival"]] = to_datetime(d["expected_date"])
    if d["supplier"] and d["supplier"] != "미상":
        fields[GR_FIELDS["Supplier_Name"]] = d["supplier"][:100]
    if d["order_ref"]:
        fields[GR_FIELDS["Order_Ref"]] = d["order_ref"]
    if d["expected_qty"]:
        fields[GR_FIELDS["Expected_Qty"]] = d["expected_qty"]
    if d["received_qty"]:
        fields[GR_FIELDS["Received_Qty"]] = d["received_qty"]
    gr_records_to_create.append(fields)

gr_created = []  # list of created record IDs in order
errors_gr = []

for i in range(0, len(gr_records_to_create), 10):
    chunk = gr_records_to_create[i:i+10]
    result, err = api_post(GR_TBL, chunk)
    if err:
        errors_gr.append((i, err))
        print(f"  [ERROR] batch {i//10}: {err}")
        gr_created.extend([None] * len(chunk))
    else:
        ids = [r["id"] for r in result.get("records", [])]
        gr_created.extend(ids)
        print(f"  GR 생성 {i + len(chunk)}/{len(gr_records_to_create)}")
    time.sleep(0.21)

print(f"  완료: {len([x for x in gr_created if x])}건 생성, 오류: {len(errors_gr)}건")
print()


# ──────────────────────────────────────────────
# STEP 5: WMS_StockBatch 생성 (GR와 1:1 연결)
# ──────────────────────────────────────────────
print("STEP 5: WMS_StockBatch 생성")
sb_records_to_create = []
now_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")

for i, (d, gr_rec_id) in enumerate(zip(gr_data, gr_created)):
    if not gr_rec_id:
        continue

    batch_id = d["gr_id"].replace("GR-", "BATCH-")
    fields = {
        SB_FIELDS["Batch_ID"]:    batch_id,
        SB_FIELDS["GR_Link"]:     [gr_rec_id],
        SB_FIELDS["WMS_GoodsReceipt"]: [gr_rec_id],
        SB_FIELDS["Status"]:      "ACTIVE",
        SB_FIELDS["Created_At"]:  now_str,
    }
    if d["actual_date"] and "-" in d["actual_date"]:
        fields[SB_FIELDS["Inbound_Date"]] = d["actual_date"]
    if d["received_qty"]:
        fields[SB_FIELDS["Received_Qty"]] = d["received_qty"]
        fields[SB_FIELDS["Current_Qty"]]  = d["received_qty"]
    fields[SB_FIELDS["Location"]] = [DEFAULT_LOCATION]
    if d.get("material_ids"):
        fields[SB_FIELDS["Material"]] = d["material_ids"]

    sb_records_to_create.append(fields)

sb_created = 0
errors_sb = []

for i in range(0, len(sb_records_to_create), 10):
    chunk = sb_records_to_create[i:i+10]
    result, err = api_post(BATCH_TBL, chunk)
    if err:
        errors_sb.append((i, err))
        print(f"  [ERROR] batch {i//10}: {err}")
    else:
        sb_created += len(result.get("records", []))
        print(f"  StockBatch 생성 {i + len(chunk)}/{len(sb_records_to_create)}")
    time.sleep(0.21)

print(f"  완료: {sb_created}건 생성, 오류: {len(errors_sb)}건")
print()


# ──────────────────────────────────────────────
# FINAL SUMMARY
# ──────────────────────────────────────────────
print("=" * 60)
print(f"WMS_GoodsReceipt : {len([x for x in gr_created if x])}건 생성")
print(f"WMS_StockBatch   : {sb_created}건 생성")
if errors_gr or errors_sb:
    print("오류:")
    for idx, msg in errors_gr:
        print(f"  GR batch {idx}: {msg[:150]}")
    for idx, msg in errors_sb:
        print(f"  SB batch {idx}: {msg[:150]}")
