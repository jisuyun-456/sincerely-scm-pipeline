"""휴면 재고 후보 36개 → WMS Airtable movement 교차검증.

Base: WMS (appLui4ZR5HWcQRri) — PAT는 .env 의 AIRTABLE_WMS_PAT 사용
Movement table: tblwq7Kj5Y9nVjlOw
Field IDs (from wms_slack_crossvalidation.py):
  F_ITEM_ALT  = fldwZKCYZ4IFOigRp   이동물품 (PT코드 포함 텍스트)
  F_PURPOSE   = fldFRNxG1pNooEOC7   이동목적
  F_IN_QTY    = fldV8kVokQqMIsif0   입하수량
  F_OUT_QTY   = fld0XSbknPnJfOYOT   출고수량
  F_CREATED   = fldDXUAF4JOORLJ2v   생성일자
  F_MOV_ID    = fldOhFtJFBYsxxre7   movement_id
"""
from __future__ import annotations

import io
import os
import re
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

PAT = os.environ.get("AIRTABLE_WMS_PAT", "")
if not PAT:
    raise SystemExit("ERROR: AIRTABLE_WMS_PAT not set in environment (.env)")
BASE    = "appLui4ZR5HWcQRri"
TBL_MOV = "tblwq7Kj5Y9nVjlOw"
HDRS    = {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}

F_MOV_ID   = "fldOhFtJFBYsxxre7"
F_ITEM_ALT = "fldwZKCYZ4IFOigRp"
F_PURPOSE  = "fldFRNxG1pNooEOC7"
F_IN_QTY   = "fldV8kVokQqMIsif0"
F_OUT_QTY  = "fld0XSbknPnJfOYOT"
F_CREATED  = "fldDXUAF4JOORLJ2v"
F_CANCEL   = "fldwgaM8OnKubM8oE"

DORMANT_CSV = Path(__file__).parent / "dormant_candidates.csv"
OUT         = Path(__file__).parent / "analyze_dormant_out.txt"

# 검증 기간: 6개월 (2025-11-01 ~ 2026-04-30)
DATE_FROM = "2025-11-01"
DATE_TO   = "2026-04-30"


def paginate(formula: str, fields: list[str]) -> list[dict]:
    url    = f"https://api.airtable.com/v0/{BASE}/{TBL_MOV}"
    params: dict = {
        "returnFieldsByFieldId": "true",
        "fields[]": fields,
        "pageSize": 100,
        "filterByFormula": formula,
    }
    records = []
    offset  = None
    while True:
        if offset:
            params["offset"] = offset
        r = requests.get(url, headers=HDRS, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records


def sel_name(v) -> str:
    if isinstance(v, dict):
        return v.get("name", "")
    return str(v) if v else ""


def main() -> None:
    # ---- 1. Load dormant PT codes ----
    import csv
    with open(DORMANT_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    pt_codes = [r["pt"] for r in rows]
    pt_qty   = {r["pt"]: int(r["실물재고수량"]) for r in rows}
    print(f"Dormant PT codes: {len(pt_codes)}", flush=True)

    # ---- 2. Fetch per-PT movements from WMS (avoid full-table scan timeout) ----
    fields_to_fetch = [F_MOV_ID, F_ITEM_ALT, F_PURPOSE, F_IN_QTY, F_OUT_QTY, F_CREATED, F_CANCEL]
    pt_activity: dict[str, list] = defaultdict(list)
    total_fetched = 0

    for i, pt in enumerate(pt_codes):
        formula = (
            f"AND("
            f"SEARCH(\"{pt}\",{{{F_ITEM_ALT}}})>0,"
            f"IS_AFTER({{{F_CREATED}}},'{DATE_FROM}T00:00:00.000Z'),"
            f"IS_BEFORE({{{F_CREATED}}},'{DATE_TO}T23:59:59.000Z')"
            f")"
        )
        try:
            recs = paginate(formula, fields_to_fetch)
        except Exception as e:
            print(f"  [{pt}] ERROR: {e}", flush=True)
            continue

        total_fetched += len(recs)
        if recs:
            print(f"  [{i+1}/{len(pt_codes)}] {pt}: {len(recs)} movements", flush=True)
        for rec in recs:
            f = rec.get("fields", {})
            pt_activity[pt].append({
                "mm_id":   f.get(F_MOV_ID, ""),
                "purpose": sel_name(f.get(F_PURPOSE)),
                "in_qty":  f.get(F_IN_QTY, 0) or 0,
                "out_qty": f.get(F_OUT_QTY, 0) or 0,
                "created": str(f.get(F_CREATED, "") or "")[:10],
                "cancel":  sel_name(f.get(F_CANCEL)),
            })
        time.sleep(0.25)

    print(f"  Total movement records across all PTs: {total_fetched}", flush=True)

    # ---- 4. Build report ----
    buf = io.StringIO()
    buf.write(f"===== 에이원 휴면 재고 WMS 교차검증 =====\n")
    buf.write(f"기간: {DATE_FROM} ~ {DATE_TO}\n")
    buf.write(f"검증 PT 수: {len(pt_codes)}\n")
    buf.write(f"WMS movement 총 조회: {total_fetched:,}건\n\n")

    active_pts  = sorted(pt_activity.keys())
    dormant_pts = [pt for pt in pt_codes if pt not in pt_activity]

    buf.write(f"[WMS에 movement 있는 PT] {len(active_pts)}개\n")
    for pt in active_pts:
        mvs = pt_activity[pt]
        latest = max(m["created"] for m in mvs)
        purposes = ", ".join({m["purpose"] for m in mvs if m["purpose"]})
        buf.write(f"  {pt:<12} {len(mvs):>4}건  최신={latest}  목적={purposes}\n")
        for m in mvs[:3]:  # top 3
            buf.write(f"    └ {m['mm_id']}  in={m['in_qty']}  out={m['out_qty']}  {m['created']}"
                      f"{'  [취소]' if m['cancel']=='취소' else ''}\n")

    buf.write(f"\n[WMS movement 없는 PT - 진짜 휴면] {len(dormant_pts)}개\n")
    total_dormant_qty = 0
    for pt in sorted(dormant_pts, key=lambda p: -pt_qty.get(p, 0)):
        qty = pt_qty.get(pt, 0)
        total_dormant_qty += qty
        name = next((r["sync_parts"] for r in rows if r["pt"] == pt), "?")
        buf.write(f"  {pt:<12} {qty:>6}개  {name}\n")

    buf.write(f"\n===== 최종 요약 =====\n")
    buf.write(f"  총 휴면 후보      : {len(pt_codes)}종\n")
    buf.write(f"  WMS 활동 확인됨   : {len(active_pts)}종 (Excel 출하예정 없어도 움직임 있음)\n")
    buf.write(f"  진짜 완전 휴면    : {len(dormant_pts)}종\n")
    buf.write(f"  진짜 휴면 재고수량: {total_dormant_qty:,}개\n")
    total_all = sum(pt_qty.values())
    buf.write(f"  전체 후보 재고수량: {total_all:,}개\n")

    # Append to existing analyze_dormant_out.txt
    existing = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
    OUT.write_text(existing + "\n\n" + buf.getvalue(), encoding="utf-8")
    print(f"WROTE {OUT}", flush=True)
    print(buf.getvalue())


if __name__ == "__main__":
    main()
