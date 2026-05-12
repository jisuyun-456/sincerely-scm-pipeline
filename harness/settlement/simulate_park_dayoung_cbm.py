"""
박종성 다영기획 출발 상하차비용 CBM 시뮬레이션 (2024-01-01 ~ 현재)

목적:
  - F_BOX_TEXT(외박스 수량 rollup)이 없는 박종성 다영기획 건에 대해
  - 새 Product 테이블 CBM 마스터로 하차비/Total_CBM 계산 가능 여부 검증
  - 매칭 성공률, 미매칭 품목 리스트를 보고

NOT a backfill — 읽기 전용, Airtable에 쓰지 않음.

Usage:
  py harness/settlement/simulate_park_dayoung_cbm.py
  py harness/settlement/simulate_park_dayoung_cbm.py --start 2024-01-01 --end 2026-05-12
"""
import argparse
import os
import sys
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from cbm_calc import calc_from_products, load_product_lookup

load_dotenv()
PAT = os.environ.get("AIRTABLE_PAT", "")
TMS_BASE = "app4x70a8mOrIKsMf"
TBL_SHIPMENT = "tbllg1JoHclGYer7m"
DRIVER_PARK = "recXCfwVTqaoeQ9SS"

F_SC_ID         = "fldBUwhBlhOMsJZdv"
F_DATE          = "fldQvmEwwzvQW95h9"
F_PARTNER       = "fldM2u6RwLRrO7ymW"
F_FARE          = "fldRT95SC88KSBATT"
F_UNLOAD        = "fldxmAZrBGqS7sQoL"
F_ORIGIN        = "fldb24I9EQ2KPXv6S"
F_BOX_TEXT      = "fldTjLDmw5sNGszeD"
F_BOX_DIRECT    = "fldRjMaXa5TdSsGDL"
F_BOX_QTY       = "fldGXhlBwI6toXSJC"
F_ITEMS_MFG     = "fldCnwsVrpkKHt4Hl"
F_PRODUCT_FINAL = "fldgSupj5XLjJXYQo"
F_PROJECT_CODE  = "fldTs3FzaSdGYEiKX"


def _str(raw) -> str:
    if isinstance(raw, list):
        return str(raw[0] or "").strip() if raw else ""
    return str(raw or "").strip()


def fetch_park_dayoung(headers: dict, start: str, end: str) -> list[dict]:
    """박종성 + 다영기획 출발 Shipment 조회."""
    end_excl = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    formula = (
        f"AND({{출하확정일}}>='{start}',{{출하확정일}}<'{end_excl}',"
        f"NOT({{배송파트너}}=''))"
    )
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_SHIPMENT}"
    records: list[dict] = []
    cursor = None
    while True:
        params: dict = {
            "filterByFormula": formula,
            "returnFieldsByFieldId": "true",
            "fields[]": [
                F_SC_ID, F_DATE, F_PARTNER, F_FARE, F_UNLOAD, F_ORIGIN,
                F_BOX_TEXT, F_BOX_DIRECT, F_BOX_QTY,
                F_ITEMS_MFG, F_PRODUCT_FINAL, F_PROJECT_CODE,
            ],
            "pageSize": 100,
        }
        if cursor:
            params["offset"] = cursor
        r = requests.get(url, headers=headers, params=params, timeout=30)
        if not r.ok:
            raise RuntimeError(f"Airtable {r.status_code}: {r.text[:200]}")
        data = r.json()
        for rec in data.get("records", []):
            f = rec["fields"]
            if DRIVER_PARK not in (f.get(F_PARTNER) or []):
                continue
            origin = _str(f.get(F_ORIGIN))
            if "다영" not in origin and "성남시 중원구" not in origin:
                continue
            records.append(rec)
        cursor = data.get("offset")
        if not cursor:
            break
        time.sleep(0.2)
    return records


def main():
    ap = argparse.ArgumentParser(description="박종성 다영기획 CBM 하차비 시뮬레이션")
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end",   default=date.today().isoformat())
    args = ap.parse_args()

    if not PAT:
        print("ERROR: AIRTABLE_PAT not set", file=sys.stderr)
        return

    out = sys.stdout.buffer
    headers = {
        "Authorization": f"Bearer {PAT}",
        "Content-Type": "application/json",
    }

    out.write(f"[1/3] Product CBM 룩업 로딩...\n".encode("utf-8"))
    lookup = load_product_lookup(headers)
    out.write(f"  품목 수: {len(lookup)//2}종 (name+code 각 키)\n\n".encode("utf-8"))

    out.write(f"[2/3] 박종성 다영기획 출발 조회 ({args.start} ~ {args.end})...\n".encode("utf-8"))
    recs = fetch_park_dayoung(headers, args.start, args.end)
    out.write(f"  전체 {len(recs)}건\n\n".encode("utf-8"))

    no_box = []
    has_box = 0
    for rec in recs:
        f = rec["fields"]
        box = _str(f.get(F_BOX_TEXT)) or _str(f.get(F_BOX_DIRECT)) or _str(f.get(F_BOX_QTY))
        if box:
            has_box += 1
        else:
            no_box.append(rec)

    out.write(f"  박스 데이터 있음 (시뮬 제외): {has_box}건\n".encode("utf-8"))
    out.write(f"  박스 데이터 없음 (시뮬 대상): {len(no_box)}건\n\n".encode("utf-8"))

    out.write(f"[3/3] CBM 매칭 시뮬레이션\n".encode("utf-8"))
    header = (
        f"{'SC ID':<13} {'날짜':<11} {'fare':>8} {'paid_unl':>8} "
        f"{'sim_unl':>8} {'cbm':>6}  {'matched/total':<14}  items\n"
    )
    out.write(header.encode("utf-8"))
    out.write(("-" * 130 + "\n").encode())

    total_sim_unload = 0
    total_paid_unload = 0
    total_cbm_sum = 0.0
    success = 0
    partial = 0
    fail = 0
    no_items = 0
    unmatched_counter: Counter = Counter()

    rows = []
    for rec in sorted(no_box, key=lambda r: (r["fields"].get(F_DATE) or "")):
        f = rec["fields"]
        sc_id = _str(f.get(F_SC_ID))
        date_val = (f.get(F_DATE) or "")[:10]
        fare = f.get(F_FARE) or 0
        paid_unload = f.get(F_UNLOAD) or 0

        items_text = _str(f.get(F_ITEMS_MFG)) or _str(f.get(F_PRODUCT_FINAL))
        if not items_text:
            no_items += 1
            rows.append((sc_id, date_val, fare, paid_unload, 0, 0.0, "0/0", "(품목 없음)"))
            continue

        result = calc_from_products(items_text, lookup)
        sim_unload = result["unload_fee"]
        cbm = result["total_cbm"]
        matched = result["matched"]
        unmatched = result["unmatched"]

        n_matched = len(matched)
        n_total = n_matched + len(unmatched)
        if n_total == 0:
            fail += 1
        elif len(unmatched) == 0:
            success += 1
        else:
            partial += 1

        for um in unmatched:
            unmatched_counter[um] += 1

        total_sim_unload += sim_unload
        total_paid_unload += paid_unload
        total_cbm_sum += cbm

        rows.append((
            sc_id, date_val, fare, paid_unload, sim_unload, cbm,
            f"{n_matched}/{n_total}", items_text[:55],
        ))

    for r in rows:
        sc_id, date_val, fare, paid_unl, sim_unl, cbm, mr, items = r
        line = (
            f"{sc_id:<13} {date_val:<11} {fare:>8,} {paid_unl:>8,} "
            f"{sim_unl:>8,} {cbm:>6.2f}  {mr:<14}  {items}\n"
        )
        out.write(line.encode("utf-8"))

    out.write(("-" * 130 + "\n").encode())

    n = len(no_box)
    nonzero_sim = sum(1 for r in rows if r[4] > 0)
    summary = (
        f"\n[요약 — 박종성 다영기획 박스 데이터 없는 {n}건]\n"
        f"  완전 매칭 (모든 품목 hit) : {success}건 ({success*100/max(1,n):.1f}%)\n"
        f"  부분 매칭 (일부 hit)      : {partial}건 ({partial*100/max(1,n):.1f}%)\n"
        f"  전부 미매칭               : {fail}건 ({fail*100/max(1,n):.1f}%)\n"
        f"  품목 텍스트 없음          : {no_items}건 ({no_items*100/max(1,n):.1f}%)\n"
        f"  → 하차비 계산 가능 (sim_unl > 0): {nonzero_sim}건 ({nonzero_sim*100/max(1,n):.1f}%)\n\n"
        f"  시뮬 하차비 합계 : {total_sim_unload:,}원\n"
        f"  실제 지급 하차비 : {total_paid_unload:,}원\n"
        f"  시뮬 Total_CBM합 : {total_cbm_sum:.2f} m³\n"
    )
    out.write(summary.encode("utf-8"))

    if unmatched_counter:
        out.write("\n[미매칭 품목 Top 30 (빈도순)]\n".encode("utf-8"))
        for prod, cnt in unmatched_counter.most_common(30):
            out.write(f"  {cnt:>3}회  {prod}\n".encode("utf-8"))


if __name__ == "__main__":
    main()
