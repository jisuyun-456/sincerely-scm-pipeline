"""Build the unified CBM/BOM sandbox base 지수_테스트 (apptJBFsVRGaeUvLW).

Creates ~20 canonical tables (curated fields, live names preserved) via the
Airtable Meta API, then a 2nd pass adds →project / →ItemMaster link fields.
Idempotent: existing tables/fields are skipped, and any field newly added to a
TABLES spec is back-filled onto an already-created table (pass 1b). Writes the
table-id map to jisu_tableids.json for seed_jisu_base.py.

Run:  AIRTABLE_JISU_PAT=... python scripts/unify/build_jisu_base.py [--dry-run]

Read-only to live WMS/TMS — this script only writes to the new sandbox base.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = "apptJBFsVRGaeUvLW"
META = f"https://api.airtable.com/v0/meta/bases/{BASE}"
IDS_OUT = os.path.join(os.path.dirname(__file__), "jisu_tableids.json")

# ---- field-type helpers -----------------------------------------------------
def T(name):       return {"name": name, "type": "singleLineText"}
def ML(name):      return {"name": name, "type": "multilineText"}
def N(name, p=0):  return {"name": name, "type": "number", "options": {"precision": p}}
def DATE(name):    return {"name": name, "type": "date", "options": {"dateFormat": {"name": "iso"}}}
def DT(name):      return {"name": name, "type": "dateTime",
                          "options": {"dateFormat": {"name": "iso"},
                                      "timeFormat": {"name": "24hour"}, "timeZone": "Asia/Seoul"}}
def CB(name):      return {"name": name, "type": "checkbox",
                          "options": {"icon": "check", "color": "greenBright"}}
def SEL(name, *choices):
    return {"name": name, "type": "singleSelect",
            "options": {"choices": [{"name": c} for c in choices]}}

# ---- canonical schema (primary field = fields[0]) ---------------------------
TABLES: dict[str, list[dict]] = {
    # Group A — operational anchors
    "project": [T("project_code"), T("Name"), T("고객회사명"), T("project_status"),
                DATE("출고요청일"), DATE("최종출고일"), ML("발주품목"), N("풀필먼트리드타임")],
    "order": [T("order_id"), T("project_code"), ML("굿즈주문수량"), N("주문수량"),
              T("파츠명"), T("굿즈코드"), T("거래처명"), T("출고요청일"), T("규격")],
    "task": [T("task_id"), T("project_code"), T("굿즈"), N("고객주문수량"),
             T("과업지시상태"), T("납기일"), T("이동목적")],
    "movement": [T("movement_id"), T("project_code"), ML("이동물품"), T("이동목적"),
                 N("입하수량"), N("출고수량"), N("이동수량"), T("제품규격"),
                 DATE("실제입하일"), DT("생성일자")],
    "pkg_schedule": [T("pkg_id"), T("project_code"), ML("Name"), T("굿즈리스트"),
                     T("외박스수량_stk"), ML("외박스포장품목및수량"), DATE("임가공예정일")],
    "material": [T("material_id"), T("파츠코드"), T("Name"), T("적용굿즈명"),
                 N("실물재고수량"), N("전산재고수량"), N("가용재고수량"),
                 T("재고위치"), N("발주점"), N("고객주문수량")],
    "sync_parts": [T("파츠코드_PK"), T("파츠명"), T("규격"), T("재고분류"), T("입하부피_QC")],
    "sync_item": [T("아이템코드_PK"), T("굿즈명"), T("굿즈코드"), T("파츠명"),
                  T("파츠코드"), T("규격")],
    # Group B — outbound / dispatch
    "Shipment": [T("shipment_id"), T("project_code"), T("발송상태_TMS"), N("Total_CBM", 3),
                 N("estimated_cbm", 4), N("estimation_confidence", 2), N("CBM_유효", 4),
                 T("wave_recommendation"), N("wave_confidence", 2), CB("wave_locked"),
                 T("배송슬롯")],
    "배송요청": [T("request_id"), T("project_code"), T("수령인주소"), T("출고지"),
               N("외박스수량"), ML("출고품목및수량"), T("이동목적"), T("배송슬롯")],
    "배송파트너": [T("배송파트너"), N("배송파트너_CBM", 1), T("contract_type"),
                T("wave_pattern"), T("autonomy_level"), N("max_daily_orders"), T("residence")],
    "운임단가": [T("단가코드"), T("구간유형"), N("CBM_최소", 1), N("CBM_최대", 1),
               N("기본운임"), N("CBM당_추가운임"), DATE("유효시작일"), DATE("유효종료일")],
    "배차일지": [T("배차일지_id"), DATE("날짜"), N("Total_CBM", 2), N("지연건수"),
               N("운임합계"), N("차량이용률", 1), N("전주평균CBM", 1)],
    # Group C — canonical CBM master (WMS_ItemMaster ⊕ TMS Product ⊕ Box)
    "ItemMaster": [T("품목키"), T("품목명"),
                   SEL("품목유형", "완제품", "키트", "단품", "부자재", "포장재"),
                   T("견적코드"), N("CBM_개당_m3", 6), T("박스규격"), N("박스당_제품수"),
                   N("박스당_CBM_m3", 4), T("박스명칭"),
                   SEL("출처", "TMS_Product", "박스유도", "MES_제품DB", "수기", "미등록", "치수파싱", "QC버킷")],
    "Box": [T("Box_Code"), T("박스"), T("가로"), T("세로"), T("높이"), N("cbm", 2)],
    # Group D — canonical capacity (WMS_Location ⊕ TMS Location ⊕ Capa)
    "Location": [T("Location_ID"), T("Warehouse"), T("Zone_Type"), N("Max_CBM", 3),
                 N("Current_Occupied_CBM", 3), N("Remaining_CBM", 3),
                 N("Occupancy_Rate", 2), N("Capacity_Units")],
    # Group E — derived BOM / propagation
    "KeyCrosswalk": [T("표준키"), SEL("키유형", "굿즈", "파츠"), T("TMS_견적코드"),
                     T("WMS_아이템코드"), T("MES_파츠코드"), SEL("매칭방식", "정확", "유사", "수기"),
                     N("매칭신뢰도", 2), SEL("검증상태", "미검증", "확정", "보류"), T("출처")],
    "BOM": [T("BOM_ID"), T("프로젝트코드"), T("모품목_굿즈명"), T("소품목_PT"),
            N("소요량_개당", 4), SEL("구성유형", "키트", "임가공", "포장재", "원부자재"),
            N("신뢰도", 2), SEL("검증상태", "이송", "검증완료", "폐기"),
            SEL("출처", "order그룹핑", "MES보강", "movement보강", "수기")],
    "InventoryLedger": [T("Ledger_Key"), T("pt"),
                        SEL("Stock_Type", "UNRESTRICTED", "QUALITY_INSPECTION", "BLOCKED"),
                        N("Current_Stock"), T("Snapshot_Week"), DATE("Last_Movement_Date")],
    "PropagationLedger": [T("전파ID"), T("프로젝트코드"), T("굿즈명"), N("고객주문수량"),
                          ML("자재소요_요약"), ML("포장소요_요약"), N("추정_CBM_m3", 4),
                          T("shipment_id"), SEL("전파상태", "완결", "부분", "끊김"),
                          ML("부족자재_요약"), N("입하CBM_예상_m3", 4), N("MH_예상_h", 2),
                          T("창고적재_예상"), T("wave_프리뷰"), T("운임_예상범위"),
                          DATE("출고요청일"), DATE("생산_납기일"),
                          T("cascade_실행ID"), DT("생성시각")],
}

# 2nd pass — link fields (table, field name, target table)
LINK_FIELDS: list[tuple[str, str, str]] = [
    ("order", "→project", "project"),
    ("task", "→project", "project"),
    ("movement", "→project", "project"),
    ("pkg_schedule", "→project", "project"),
    ("Shipment", "→project", "project"),
    ("배송요청", "→project", "project"),
    ("BOM", "→project", "project"),
    ("PropagationLedger", "→project", "project"),
    ("BOM", "→ItemMaster", "ItemMaster"),
]


def _pat():
    p = os.environ.get("AIRTABLE_JISU_PAT") or os.environ.get("AIRTABLE_ZISU_PAT")
    if not p:
        raise SystemExit("set AIRTABLE_JISU_PAT (legacy AIRTABLE_ZISU_PAT also accepted)")
    return p


def _hdr():
    return {"Authorization": f"Bearer {_pat()}",
            "Content-Type": "application/json"}


def _req(url, payload=None, method="GET"):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=_hdr(), method=method)
    try:
        return json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise SystemExit(f"\n[HTTP {e.code}] {method} {url}\n{body}\n"
                         "→ schema.bases:write scope likely missing on AIRTABLE_ZISU_PAT."
                         if e.code in (403, 401) else f"[HTTP {e.code}] {body}")


def existing():
    return {t["name"]: t for t in _req(f"{META}/tables")["tables"]}


def main(dry_run=False):
    have = existing()
    # pass 1 — scalar tables
    for name, fields in TABLES.items():
        if name in have:
            print(f"[skip] table exists: {name}")
            continue
        if dry_run:
            print(f"[dry-run] create {name} ({len(fields)}f)")
            continue
        res = _req(f"{META}/tables", {"name": name, "fields": fields}, "POST")
        print(f"[created] {name} -> {res['id']} ({len(fields)}f)")
    # pass 1b — back-fill any scalar field newly added to a TABLES spec onto an
    # already-created table (idempotent field add — never modifies/deletes).
    have = existing()
    for name, fields in TABLES.items():
        if name not in have:
            continue
        present = {f["name"] for f in have[name]["fields"]}
        for fld in fields:
            if fld["name"] in present:
                continue
            if dry_run:
                print(f"[dry-run] add field {name}.{fld['name']}")
                continue
            _req(f"{META}/tables/{have[name]['id']}/fields", fld, "POST")
            print(f"[added] field {name}.{fld['name']}")
    # pass 2 — link fields
    have = existing()
    for tbl, fld, target in LINK_FIELDS:
        if tbl not in have or target not in have:
            print(f"[warn] missing table for link {tbl}.{fld}")
            continue
        if any(f["name"] == fld for f in have[tbl]["fields"]):
            print(f"[skip] field exists: {tbl}.{fld}")
            continue
        if dry_run:
            print(f"[dry-run] link {tbl}.{fld} -> {target}")
            continue
        _req(f"{META}/tables/{have[tbl]['id']}/fields",
             {"name": fld, "type": "multipleRecordLinks",
              "options": {"linkedTableId": have[target]["id"]}}, "POST")
        print(f"[created] link {tbl}.{fld} -> {target}")
    # save id map + warn about default Table 1 (API cannot delete tables)
    if not dry_run:
        have = existing()
        json.dump({n: t["id"] for n, t in have.items()},
                  open(IDS_OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"\n[ids] wrote {IDS_OUT}")
        if "Table 1" in have:
            print("[warn] default 'Table 1' still present — delete it manually in the "
                  "Airtable UI (Meta API has no table-delete endpoint).")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
