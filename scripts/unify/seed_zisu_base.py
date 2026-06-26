"""Seed the unified sandbox base 지수_테스트 from live WMS/TMS (read-only sources).

Bounded seed: ~20 example projects end-to-end (their order/task/movement/
pkg_schedule/Shipment/배송요청) + ~50% of the goods/material masters
(ItemMaster⊕Product, BOM, sync_parts, sync_item, material, KeyCrosswalk,
InventoryLedger) + small reference tables. PropagationLedger left empty.

Run:  AIRTABLE_ZISU_PAT=... AIRTABLE_WMS_PAT=... AIRTABLE_PAT=... \
      python scripts/unify/seed_zisu_base.py [--projects 20] [--frac 0.5] [--force]

Only writes to the new base (apptJBFsVRGaeUvLW). Never mutates WMS/TMS.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ZBASE = "apptJBFsVRGaeUvLW"
WBASE = "appLui4ZR5HWcQRri"
TBASE = "app4x70a8mOrIKsMf"
IDS = json.load(open(os.path.join(os.path.dirname(__file__), "zisu_tableids.json"), encoding="utf-8"))
PNARE = re.compile(r"(PNA\d+)")

ZPAT = os.environ["AIRTABLE_ZISU_PAT"]
WPAT = os.environ["AIRTABLE_WMS_PAT"]
TPAT = os.environ["AIRTABLE_PAT"]

# ---- live source table ids --------------------------------------------------
S = {
    "project": (WBASE, "tblMc5HLfMqe4g4pE", WPAT),
    "order": (WBASE, "tblJslWg8sYEdCkXw", WPAT),
    "task": (WBASE, "tblsIiXQzrHMSPqH7", WPAT),
    "movement": (WBASE, "tblwq7Kj5Y9nVjlOw", WPAT),
    "pkg_schedule": (WBASE, "tblae2NqJaexwjN9R", WPAT),
    "material": (WBASE, "tblaRpZstW10EwDlo", WPAT),
    "sync_parts": (WBASE, "tblzJh0V4hdo4Xbvx", WPAT),
    "sync_item": (WBASE, "tblwnNgHQxZ0WhDBh", WPAT),
    "ItemMaster": (WBASE, "tbl5ZGY373D5SCONV", WPAT),
    "BOM": (WBASE, "tblopHqepkx6mNEHL", WPAT),
    "KeyCrosswalk": (WBASE, "tblJK5eyQGGx5X1oH", WPAT),
    "InventoryLedger": (WBASE, "tbl4DcXQRHJj921MN", WPAT),
    "WMS_Location": (WBASE, "tblRwUTP5kWnHFt5P", WPAT),
    "Shipment": (TBASE, "tbllg1JoHclGYer7m", TPAT),
    "배송요청": (TBASE, "tblfIEiPJaEF0DVoM", TPAT),
    "배송파트너": (TBASE, "tblI4ZXrte7WyhXyd", TPAT),
    "운임단가": (TBASE, "tblQA1ev9fjbowUoP", TPAT),
    "배차일지": (TBASE, "tbl0YCjOC7rYtyXHV", TPAT),
    "Product": (TBASE, "tblBNh6oGDlTKGrdQ", TPAT),
    "Box": (TBASE, "tbltwH7bHk41rTzhM", TPAT),
    "TMS_Location": (TBASE, "tblSObcLUA5iO1TTx", TPAT),
}

# ---- HTTP -------------------------------------------------------------------
def _open(req):
    for attempt in range(5):
        try:
            return json.load(urllib.request.urlopen(req))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < 4:
                time.sleep(1.5 * (attempt + 1)); continue
            raise SystemExit(f"[HTTP {e.code}] {req.full_url}\n{e.read().decode()}")


def live(name, fields=None, formula=None, maxrec=None):
    base, tid, pat = S[name]
    params = {}
    if fields:
        params["fields[]"] = fields
    if formula:
        params["filterByFormula"] = formula
    if maxrec:
        params["maxRecords"] = maxrec
    out, offset = [], None
    while True:
        p = dict(params)
        if offset:
            p["offset"] = offset
        url = f"https://api.airtable.com/v0/{base}/{tid}?" + urllib.parse.urlencode(p, doseq=True)
        data = _open(urllib.request.Request(url, headers={"Authorization": f"Bearer {pat}"}))
        out.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset or (maxrec and len(out) >= maxrec):
            break
    return out


def write(name, rows):
    """rows = list of fields-dicts. Returns key->newRecordId is caller's job."""
    tid = IDS[name]
    created = []
    for i in range(0, len(rows), 10):
        chunk = [{"fields": f} for f in rows[i:i + 10]]
        url = f"https://api.airtable.com/v0/{ZBASE}/{tid}"
        body = json.dumps({"records": chunk, "typecast": True}).encode()
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Authorization": f"Bearer {ZPAT}",
                                              "Content-Type": "application/json"})
        created.extend(_open(req).get("records", []))
        time.sleep(0.22)  # stay under 5 req/s on the target base
    return created


def zexists(name):
    """True if the target table already has at least one record."""
    u = f"https://api.airtable.com/v0/{ZBASE}/{IDS[name]}?maxRecords=1"
    d = _open(urllib.request.Request(u, headers={"Authorization": f"Bearer {ZPAT}"}))
    return len(d.get("records", [])) > 0


# ---- value coercion ---------------------------------------------------------
def C(v, kind):
    if v is None or v == "":
        return None
    if isinstance(v, list):
        if not v:
            return None
        if kind in ("num", "date", "dt", "bool"):
            v = v[0]
        else:
            return ", ".join(str(x) for x in v)
    if kind == "num":
        if isinstance(v, (int, float)):
            return v
        m = re.search(r"-?\d+\.?\d*", str(v).replace(",", ""))
        return float(m.group()) if m else None
    if kind == "bool":
        return bool(v)
    return v if isinstance(v, str) else str(v)


def of(values, field, func="eq"):
    """Build an OR(...) filterByFormula over a list of values."""
    if func == "eq":
        terms = [f'{{{field}}}="{v}"' for v in values]
    else:  # find substring
        terms = [f'FIND("{v}",{{{field}}})' for v in values]
    return "OR(" + ",".join(terms) + ")"


def build(rec, spec):
    """spec = list of (target, source, kind). Pull from rec['fields']."""
    f = rec.get("fields", {})
    row = {}
    for tgt, src, kind in spec:
        val = C(f.get(src), kind)
        if val is not None:
            row[tgt] = val
    return row


# ---- field specs (target, source, kind) -------------------------------------
SPEC = {
    "order": [("project_code", "project_code", "text"), ("굿즈주문수량", "굿즈 주문 수량 (자동)", "multi"),
              ("주문수량", "주문수량", "num"), ("파츠명", "파츠명", "text"),
              ("굿즈코드", "굿즈코드 (from sync_itemdb)", "text"), ("거래처명", "거래처명", "text"),
              ("출고요청일", "출고 요청일", "text"), ("규격", "규격(가로x세로x높이)", "text")],
    "task": [("task_id", "task_id", "text"), ("project_code", "project_code", "text"),
             ("굿즈", "goods (from order)", "multi"), ("고객주문수량", "고객주문수량", "num"),
             ("과업지시상태", "과업지시상태", "multi"), ("납기일", "납기일", "text"),
             ("이동목적", "이동목적", "multi")],
    "movement": [("이동물품", "이동물품", "multi"), ("이동목적", "이동목적", "text"),
                 ("입하수량", "입하수량", "num"), ("출고수량", "출고수량", "num"),
                 ("이동수량", "이동수량(변경)📝", "num"), ("제품규격", "제품 규격", "text"),
                 ("실제입하일", "실제입하일", "date"), ("생성일자", "생성일자", "dt")],
    "pkg_schedule": [("Name", "Name", "multi"), ("굿즈리스트", "주문 굿즈 리스트 (자동) (from project)", "text"),
                     ("외박스수량_stk", "외박스수량_stk", "multi"),
                     ("외박스포장품목및수량", "배송차수별 외박스 포장 품목 및 수량_test_수현", "multi"),
                     ("임가공예정일", "임가공 예정일", "date")],
    "Shipment": [("project_code", "project code", "text"), ("발송상태_TMS", "발송상태_TMS", "text"),
                 ("Total_CBM", "Total_CBM", "num"), ("estimated_cbm", "estimated_cbm", "num"),
                 ("estimation_confidence", "estimation_confidence", "num"), ("CBM_유효", "CBM_유효", "num"),
                 ("wave_recommendation", "wave_recommendation", "text"),
                 ("wave_confidence", "wave_confidence", "num"), ("wave_locked", "wave_locked", "bool"),
                 ("배송슬롯", "배송슬롯", "text")],
    "배송요청": [("project_code", "project", "text"), ("수령인주소", "수령인(주소)", "text"),
               ("출고지", "출고지", "text"), ("외박스수량", "외박스 수량", "num"),
               ("출고품목및수량", "출고 품목 및 수량", "multi"), ("이동목적", "이동목적", "text"),
               ("배송슬롯", "배송 슬롯", "text")],
    "ItemMaster": [("품목키", "품목키", "text"), ("품목명", "품목명", "text"), ("품목유형", "품목유형", "text"),
                   ("CBM_개당_m3", "CBM_개당_m3", "num"), ("박스규격", "박스규격", "text"),
                   ("박스당_제품수", "박스당_제품수", "num"), ("박스당_CBM_m3", "박스당_CBM_m3", "num"),
                   ("출처", "출처", "text")],
    "Product": [("품목명", "Name", "text"), ("견적코드", "견적코드", "text"),
                ("박스명칭", "박스명칭", "text"), ("박스당_제품수", "박스당 제품수", "num"),
                ("박스당_CBM_m3", "박스 당 CBM", "num"), ("품목유형", "단품/키트", "text")],
    "BOM": [("BOM_ID", "BOM_ID", "text"), ("프로젝트코드", "프로젝트코드", "text"),
            ("모품목_굿즈명", "모품목_굿즈명", "text"), ("소품목_PT", "소품목_PT", "text"),
            ("소요량_개당", "소요량_개당", "num"), ("구성유형", "구성유형", "text"),
            ("신뢰도", "신뢰도", "num"), ("검증상태", "검증상태", "text"), ("출처", "출처", "text")],
    "sync_parts": [("파츠코드_PK", "파츠 코드 (PK)", "text"),
                   ("파츠명", "파츠명 (재고관리/정보관리용 명칭)", "multi"),
                   ("규격", "규격", "multi"), ("재고분류", "재고 분류", "text"),
                   ("입하부피_QC", "입하부피 by QC", "text")],
    "sync_item": [("아이템코드_PK", "아이템 코드 (PK)", "text"), ("굿즈명", "굿즈명", "text"),
                  ("굿즈코드", "굿즈코드", "text"), ("파츠명", "파츠명", "multi"),
                  ("파츠코드", "파츠 코드", "text"), ("규격", "규격(가로x세로x높이)", "text")],
    "material": [("파츠코드", "파츠 코드 (from sync_parts)", "text"), ("Name", "Name", "text"),
                 ("적용굿즈명", "적용 굿즈명", "multi"), ("실물재고수량", "실물재고수량", "num"),
                 ("전산재고수량", "전산재고수량", "num"), ("가용재고수량", "가용재고수량", "num"),
                 ("재고위치", "재고위치", "multi"), ("발주점", "발주점", "num"),
                 ("고객주문수량", "고객주문수량", "num")],
    "KeyCrosswalk": [("표준키", "표준키", "text"), ("키유형", "키유형", "text"),
                     ("TMS_견적코드", "TMS_견적코드", "text"), ("WMS_아이템코드", "WMS_아이템코드", "text"),
                     ("MES_파츠코드", "MES_파츠코드", "text"), ("매칭방식", "매칭방식", "text"),
                     ("매칭신뢰도", "매칭신뢰도", "num"), ("검증상태", "검증상태", "text"),
                     ("출처", "출처", "text")],
    "InventoryLedger": [("Ledger_Key", "Ledger_Key", "text"), ("Stock_Type", "Stock_Type", "text"),
                        ("Current_Stock", "Current_Stock", "num"), ("Snapshot_Week", "Snapshot_Week", "text"),
                        ("Last_Movement_Date", "Last_Movement_Date", "date")],
    "Box": [("Box_Code", "Box Code", "text"), ("박스", "박스", "text"), ("가로", "가로", "text"),
            ("세로", "세로", "text"), ("높이", "높이", "text"), ("cbm", "cbm", "num")],
    "배송파트너": [("배송파트너", "배송파트너", "text"), ("배송파트너_CBM", "배송파트너_CBM", "num"),
                ("contract_type", "contract_type", "text"), ("wave_pattern", "wave_pattern", "text"),
                ("autonomy_level", "autonomy_level", "text"), ("max_daily_orders", "max_daily_orders", "num"),
                ("residence", "residence", "text")],
    "운임단가": [("단가코드", "단가코드", "text"), ("구간유형", "구간유형", "text"),
               ("CBM_최소", "CBM_최소", "num"), ("CBM_최대", "CBM_최대", "num"),
               ("기본운임", "기본운임", "num"), ("CBM당_추가운임", "CBM당_추가운임", "num"),
               ("유효시작일", "유효시작일", "date"), ("유효종료일", "유효종료일", "date")],
    "배차일지": [("날짜", "날짜", "date"), ("Total_CBM", "Total_CBM", "num"), ("지연건수", "지연건수", "num"),
               ("운임합계", "운임합계", "num"), ("차량이용률", "차량이용률(%)", "num"),
               ("전주평균CBM", "전주_평균_CBM", "num")],
}


def half(rows, needed_keys, keyfn, frac):
    """needed rows (key in needed_keys) ∪ first frac of all, dedup by key."""
    seen, out = set(), []
    for r in rows:
        k = keyfn(r)
        if k in needed_keys and k not in seen:
            seen.add(k); out.append(r)
    target = int(len(rows) * frac)
    for r in rows:
        if len(out) >= max(len(seen), target):
            break
        k = keyfn(r)
        if k not in seen:
            seen.add(k); out.append(r)
    return out


def wipe():
    """Delete all records from every seeded table (sandbox reset)."""
    for name in IDS:
        if name == "Table 1":
            continue
        ids, offset = [], None
        while True:
            u = f"https://api.airtable.com/v0/{ZBASE}/{IDS[name]}" + (f"?offset={offset}" if offset else "")
            d = _open(urllib.request.Request(u, headers={"Authorization": f"Bearer {ZPAT}"}))
            ids += [r["id"] for r in d.get("records", [])]
            offset = d.get("offset")
            if not offset:
                break
        for i in range(0, len(ids), 10):
            q = "&".join(f"records[]={rid}" for rid in ids[i:i + 10])
            req = urllib.request.Request(f"https://api.airtable.com/v0/{ZBASE}/{IDS[name]}?{q}",
                                         method="DELETE", headers={"Authorization": f"Bearer {ZPAT}"})
            _open(req)
            time.sleep(0.22)
        if ids:
            print(f"  wiped {name}: {len(ids)}")
    print("✓ wipe complete")


def main():
    if "--wipe" in sys.argv:
        wipe(); return
    n_proj = int(_arg("--projects", 20))
    frac = float(_arg("--frac", 0.5))
    force = "--force" in sys.argv

    if not force and zexists("Shipment"):
        raise SystemExit("Target already seeded (Shipment non-empty). Re-run with --force to add more.")

    # ---- 1. pick PNAs (orders ∩ shipments, prefer those with CBM) -----------
    print("· picking PNAs …")
    ship = live("Shipment", fields=["project code", "estimated_cbm"], maxrec=1500)
    ship_pna = {}
    for r in ship:
        pc = r["fields"].get("project code")
        if pc and PNARE.match(str(pc)):
            pna = PNARE.match(str(pc)).group(1)
            ship_pna[pna] = ship_pna.get(pna, 0) or (C(r["fields"].get("estimated_cbm"), "num") or 0)
    ords = live("order", fields=["project_code"], maxrec=3000)
    ord_pna = {}
    for r in ords:
        pc = r["fields"].get("project_code")
        if pc and PNARE.match(str(pc)):
            p = PNARE.match(str(pc)).group(1); ord_pna[p] = ord_pna.get(p, 0) + 1
    cands = [p for p in ord_pna if p in ship_pna]
    cands.sort(key=lambda p: (ship_pna[p] > 0, ord_pna[p]), reverse=True)
    pnas = cands[:n_proj]
    print(f"  → {len(pnas)} PNAs: {pnas}")
    pset = set(pnas)

    # ---- 2. project (build pna -> new recId) --------------------------------
    print("· project …")
    proj_rows, pna_seen, live_pid2pna = [], {}, {}
    for r in live("project", maxrec=4000):
        nm = r["fields"].get("Name", "")
        m = PNARE.search(str(nm))
        if m and m.group(1) in pset and m.group(1) not in pna_seen:
            pna = m.group(1)
            live_pid2pna[r["id"]] = pna
            row = {"project_code": pna, "Name": C(nm, "text"),
                   "고객회사명": C(r["fields"].get("고객 회사명"), "multi"),
                   "project_status": C(r["fields"].get("project status"), "text"),
                   "출고요청일": C(r["fields"].get("출고 요청일 (최초 출고일 기준)"), "date"),
                   "최종출고일": C(r["fields"].get("최종 출고일"), "date"),
                   "발주품목": C(r["fields"].get("발주 품목"), "multi"),
                   "풀필먼트리드타임": C(r["fields"].get("풀필먼트 리드타임"), "num")}
            pna_seen[pna] = row
            proj_rows.append({k: v for k, v in row.items() if v is not None})
    created = write("project", proj_rows)
    pna2rec = {}
    for rec in created:
        pna2rec[rec["fields"]["project_code"]] = rec["id"]
    print(f"  → {len(created)} projects")

    def link(pna):
        rid = pna2rec.get(pna)
        return {"→project": [rid]} if rid else {}

    # ---- 3. anchors keyed by PNA -------------------------------------------
    def seed_anchor(name, idfield, find_fields):
        # FIND across all candidate fields; over-matches are dropped by the
        # PNARE membership re-check below, so substring matching is safe.
        terms = [f'FIND("{p}",{{{ff}}})' for ff in find_fields for p in pnas]
        recs = live(name, formula="OR(" + ",".join(terms) + ")", maxrec=6000)
        rows = []
        for r in recs:
            blob = " ".join(str(r["fields"].get(ff, "")) for ff in find_fields)
            m = PNARE.search(blob)
            pna = m.group(1) if m else None
            if pna not in pset:
                continue
            row = build(r, SPEC[name])
            if idfield:
                row[idfield] = r["id"]
            row["project_code"] = pna
            row.update(link(pna))
            rows.append(row)
        c = write(name, rows)
        print(f"  → {name}: {len(c)}")
        return c

    print("· anchors …")
    seed_anchor("order", "order_id", ["project_code"])
    seed_anchor("task", "task_id", ["project_code"])
    seed_anchor("movement", "movement_id", ["project", "이동물품"])
    seed_anchor("Shipment", "shipment_id", ["project code"])
    seed_anchor("배송요청", "request_id", ["project"])

    # pkg_schedule links to project by record id, not text — match on the link.
    pkg_fields = ["project", "Name", "주문 굿즈 리스트 (자동) (from project)", "외박스수량_stk",
                  "배송차수별 외박스 포장 품목 및 수량_test_수현", "임가공 예정일"]
    pkg_rows = []
    for r in live("pkg_schedule", fields=pkg_fields, maxrec=6000):
        pna = next((live_pid2pna[i] for i in (r["fields"].get("project") or [])
                    if i in live_pid2pna), None)
        if not pna:
            continue
        row = build(r, SPEC["pkg_schedule"])
        row.update({"pkg_id": r["id"], "project_code": pna}); row.update(link(pna))
        pkg_rows.append(row)
    print(f"  → pkg_schedule: {len(write('pkg_schedule', pkg_rows))}")

    # collect seeded PTs / goods for master 'needed' sets
    GCODE = "굿즈코드 (from sync_itemdb)"
    seeded_orders = live("order", fields=["파츠명", GCODE, "굿즈 주문 수량 (자동)"],
                         formula=of(pnas, "project_code"), maxrec=6000)
    pts, goods = set(), set()
    for r in seeded_orders:
        pm = re.match(r"(PT\d+)", str(r["fields"].get("파츠명", "")))
        if pm:
            pts.add(pm.group(1))
        gc = r["fields"].get(GCODE)
        if gc:
            goods.add(str(gc))

    # ---- 4. masters (needed ∪ ~frac) ---------------------------------------
    print("· masters …")
    # ItemMaster (WMS) + Product merge
    im = live("ItemMaster", maxrec=4000)
    im_sel = half(im, pts | goods, lambda r: str(r["fields"].get("품목키", "")), frac)
    im_rows = [build(r, SPEC["ItemMaster"]) for r in im_sel]
    im_created = write("ItemMaster", [r for r in im_rows if r.get("품목키")])
    pt2im = {rec["fields"].get("품목키"): rec["id"] for rec in im_created}
    # merge TMS Product (keyed by 견적코드, skip dups)
    prod = live("Product", maxrec=1000)
    have_keys = set(pt2im)
    prod_rows = []
    for r in prod:
        key = r["fields"].get("견적코드") or r["fields"].get("Name")
        if not key or str(key) in have_keys:
            continue
        row = build(r, SPEC["Product"]); row["품목키"] = str(key); row["출처"] = "TMS_Product"
        if row.get("품목유형") not in ("단품", "키트"):
            row.pop("품목유형", None)
        have_keys.add(str(key)); prod_rows.append(row)
    pc = write("ItemMaster", prod_rows)
    for rec in pc:
        pt2im[rec["fields"].get("품목키")] = rec["id"]
    print(f"  → ItemMaster: {len(im_created)} (WMS) + {len(pc)} (Product)")

    # BOM (→project, →ItemMaster)
    bom = live("BOM", maxrec=4000)
    bom_sel = half(bom, pset, lambda r: PNARE.match(str(r["fields"].get("프로젝트코드", ""))).group(1)
                   if PNARE.match(str(r["fields"].get("프로젝트코드", ""))) else "", frac)
    bom_rows = []
    for r in bom_sel:
        row = build(r, SPEC["BOM"])
        m = PNARE.match(str(r["fields"].get("프로젝트코드", "")))
        if m and m.group(1) in pna2rec:
            row["→project"] = [pna2rec[m.group(1)]]
        pt = str(r["fields"].get("소품목_PT", ""))
        if pt in pt2im:
            row["→ItemMaster"] = [pt2im[pt]]
        if row.get("BOM_ID"):
            bom_rows.append(row)
    print(f"  → BOM: {len(write('BOM', bom_rows))}")

    # sync_parts / sync_item / material / KeyCrosswalk
    sp = live("sync_parts", maxrec=3000)
    write("sync_parts", [build(r, SPEC["sync_parts"]) for r in
                         half(sp, pts, lambda r: str(r["fields"].get("파츠 코드 (PK)", "")), frac)
                         if r["fields"].get("파츠 코드 (PK)")])
    si = live("sync_item", maxrec=3000)
    write("sync_item", [build(r, SPEC["sync_item"]) for r in
                        half(si, goods, lambda r: str(r["fields"].get("굿즈코드", "")), frac)
                        if r["fields"].get("아이템 코드 (PK)")])
    mat = live("material", maxrec=2000)
    write("material", [build(r, SPEC["material"]) for r in
                       half(mat, pts, lambda r: str(r["fields"].get("파츠 코드 (from sync_parts)", "")), frac)])
    kc = live("KeyCrosswalk", maxrec=4000)
    write("KeyCrosswalk", [build(r, SPEC["KeyCrosswalk"]) for r in kc if r["fields"].get("표준키")])
    print("  → sync_parts / sync_item / material / KeyCrosswalk done")

    # InventoryLedger (resolve Material link -> pt via material map)
    matid2pt = {}
    for r in mat:
        pt = r["fields"].get("파츠 코드 (from sync_parts)")
        if pt:
            matid2pt[r["id"]] = C(pt, "text")
    il = live("InventoryLedger", maxrec=4000)
    il_rows = []
    for r in il:
        row = build(r, SPEC["InventoryLedger"])
        link_ids = r["fields"].get("Material") or []
        pt = matid2pt.get(link_ids[0]) if link_ids else None
        if pt:
            row["pt"] = pt
        if row.get("Ledger_Key"):
            il_rows.append(row)
    il_sel = half(il_rows, pts, lambda r: r.get("pt", ""), frac)
    print(f"  → InventoryLedger: {len(write('InventoryLedger', il_sel))}")

    # ---- 5. small reference tables -----------------------------------------
    print("· references …")
    write("Box", [build(r, SPEC["Box"]) for r in live("Box", maxrec=500) if r["fields"].get("Box Code")])
    # Location = WMS_Location ∪ TMS Location
    loc_rows = []
    for r in live("WMS_Location", maxrec=500):
        f = r["fields"]
        loc_rows.append({"Location_ID": C(f.get("Location_ID"), "text"),
                         "Warehouse": C(f.get("Warehouse"), "text"), "Zone_Type": C(f.get("Zone_Type"), "text"),
                         "Max_CBM": C(f.get("Max_CBM"), "num"), "Capacity_Units": C(f.get("Capacity_Units"), "num")})
    for r in live("TMS_Location", maxrec=500):
        f = r["fields"]
        loc_rows.append({"Location_ID": C(f.get("Name"), "text"), "Max_CBM": C(f.get("Max_CBM"), "num"),
                         "Current_Occupied_CBM": C(f.get("Current_Occupied_CBM"), "num"),
                         "Remaining_CBM": C(f.get("Remaining_CBM"), "num"),
                         "Occupancy_Rate": C(f.get("Occupancy_Rate"), "num")})
    write("Location", [{k: v for k, v in r.items() if v is not None} for r in loc_rows if r.get("Location_ID")])
    write("배송파트너", [build(r, SPEC["배송파트너"]) for r in live("배송파트너", maxrec=200)
                     if r["fields"].get("배송파트너")])
    write("운임단가", [build(r, SPEC["운임단가"]) for r in live("운임단가", maxrec=200)
                   if r["fields"].get("단가코드")])
    write("배차일지", [dict(build(r, SPEC["배차일지"]), **{"배차일지_id": r["id"]})
                   for r in live("배차일지", maxrec=500)])
    print("  → Box / Location / 배송파트너 / 운임단가 / 배차일지 done")
    print("\n✓ seed complete")


def _arg(flag, default):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


if __name__ == "__main__":
    main()
