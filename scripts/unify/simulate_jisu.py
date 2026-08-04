"""simulate_jisu.py — run the order cascade against the unified jisu sandbox.

Points the *production* cascade CORE (harness/backbone/cascade.py — pure functions)
at the unified 지수_테스트 base instead of live WMS/TMS, so registering projects in
the sandbox produces the full BOM/CBM/M-H/wave/freight forecast in PropagationLedger.

Why a separate runner (not scripts/backbone/order_cascade.py): that orchestrator
hard-codes the live WMS/TMS/MES base ids AND pulls CBM/part/rate lookups from
helpers that read those bases internally — so it cannot be re-pointed at the sandbox
without contaminating output with production data. This runner rebuilds the whole
CascadeContext from jisu tables only:
  - load_product_lookup (→TMS) is replaced by a builder over jisu ItemMaster.
  - load_sync_parts_lookup (→WMS) is replaced by a builder over jisu sync_parts.
  - rates_for is pure config (RATE_HISTORY) — reused as-is.
Field-name coupling: the core reads live WMS field names; jisu renamed a few
(order 굿즈주문수량/출고요청일/굿즈코드, pkg_schedule, Shipment project_code). A
fetch-time remap aliases them back so the production logic runs unchanged.

The core computes ship_req(출고요청일) per unit but ledger.build_propagation_row drops
it; this runner injects it into the row so rollup_jisu.py can bucket by week/month.

Run:
  AIRTABLE_JISU_PAT=... python scripts/unify/simulate_jisu.py            # dry-run
  AIRTABLE_JISU_PAT=... python scripts/unify/simulate_jisu.py --write    # INSERT ledger
  ... --window N    forward createdTime window in days (default 3650 = all seeded)

INSERT-only to the jisu PropagationLedger via raw urllib (bypasses the production
write allowlist — sandbox base only, never touches live WMS/TMS).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.backbone.cascade import (  # noqa: E402
    collect_units,
    latest_ledger_by_pid,
    run_unit,
)
from harness.backbone.cascade import CascadeContext  # noqa: E402
from harness.backbone.keys import PNA_RE, build_pkg_goods_map, normalize_goods  # noqa: E402
from harness.backbone.part_cbm import part_cbm_for_pt  # noqa: E402
from harness.backbone.product_alias import inject_synthetic  # noqa: E402
from harness.backbone.storage import (  # noqa: E402
    ZONE_TYPE_INCLUDE,
    parse_pt_from_ledger_key,
)
from harness.dispatch.cbm_estimator import build_kit_cbm_lookup  # noqa: E402
from harness.settlement.cbm_calc import BOX_TYPE_TO_CBM_M3  # noqa: E402
from harness.tms_settlement.config import rates_for  # noqa: E402

BASE = "apptJBFsVRGaeUvLW"
IDS = json.load(open(Path(__file__).with_name("jisu_tableids.json"), encoding="utf-8"))
KST = timezone(timedelta(hours=9))

# jisu field name → live WMS field name the cascade core expects (order rows).
ORDER_ALIAS = {
    "굿즈주문수량": "굿즈 주문 수량 (자동)",
    "출고요청일": "출고 요청일",
    "굿즈코드": "굿즈코드 (from sync_itemdb)",
}


def _pat():
    p = os.environ.get("AIRTABLE_JISU_PAT") or os.environ.get("AIRTABLE_ZISU_PAT")
    if not p:
        raise SystemExit("set AIRTABLE_JISU_PAT (legacy AIRTABLE_ZISU_PAT also accepted)")
    return p


def _open(req):
    for attempt in range(5):
        try:
            return json.load(urllib.request.urlopen(req))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < 4:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise SystemExit(f"[HTTP {e.code}] {req.full_url}\n{e.read().decode()}")


def fetch(table_name):
    """Paginated GET of a jisu table → list of record dicts (id/createdTime/fields)."""
    tid = IDS[table_name]
    out, offset = [], None
    while True:
        url = f"https://api.airtable.com/v0/{BASE}/{tid}"
        if offset:
            url += "?" + urllib.parse.urlencode({"offset": offset})
        data = _open(urllib.request.Request(url, headers={"Authorization": f"Bearer {_pat()}"}))
        out.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
    return out


def _f(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def build_jisu_context(today: date) -> CascadeContext:
    """Rebuild CascadeContext from jisu tables only — no live-base read."""
    # --- ItemMaster → product_lookup (outbound box specs) + item_master (part CBM) ---
    product_lookup: dict[str, dict] = {}
    item_master: dict[str, tuple[float, str]] = {}
    for r in fetch("ItemMaster"):
        f = r["fields"]
        key = str(f.get("품목키") or "").strip()
        if key:
            item_master[key] = (_f(f.get("CBM_개당_m3")), str(f.get("출처") or ""))
        code = str(f.get("견적코드") or "").strip()
        name = str(f.get("품목명") or "").strip()
        box_type = str(f.get("박스명칭") or "").strip()
        cbm_box = _f(f.get("박스당_CBM_m3"))
        if cbm_box <= 0:
            cbm_box = BOX_TYPE_TO_CBM_M3.get(box_type, 0.0)
        if not code and cbm_box <= 0:
            continue  # pure WMS item-master row, not a finished-goods product
        entry = {
            "rec_id": r["id"], "name": name, "code": code.upper(), "box_type": box_type,
            "qty_per_box": max(1, int(_f(f.get("박스당_제품수")) or 1)),
            "cbm_per_box": cbm_box,
        }
        if name:
            product_lookup.setdefault(name.lower(), entry)
        if code:
            product_lookup[code.lower()] = entry
    inject_synthetic(product_lookup)
    product_by_code = {
        e["code"]: (e["qty_per_box"], e["cbm_per_box"])
        for e in product_lookup.values()
        if e.get("code") and e["cbm_per_box"] > 0
    }

    # --- sync_item → name2code bridge ---
    name2code: dict[str, str] = {}
    for r in fetch("sync_item"):
        f = r["fields"]
        nm = normalize_goods(str(f.get("굿즈명") or ""))
        cd = str(f.get("굿즈코드") or "").strip().upper()
        if nm and cd:
            name2code[nm] = cd

    # --- pkg_schedule → pkg_map fallback (remap jisu names → live names) ---
    # CAVEAT: the live build_pkg_goods_map also reads "단품 굿즈 품목 및 수량" as a 2nd
    # goods-code fallback, which jisu did not seed — so only the 주문 굿즈 리스트 path is
    # available here. Verified harmless for the seeded set (cascade 끊김 0: every unit
    # resolves its code via order.굿즈코드(direct) or 굿즈리스트). If a future seed adds
    # PNAs that depend on the 단품 fallback, add that field in build/seed + here.
    pkg_fields = [{
        "프로젝트 코드 (PK) (from project)": r["fields"].get("project_code"),
        "주문 굿즈 리스트 (자동) (from project)": r["fields"].get("굿즈리스트"),
    } for r in fetch("pkg_schedule")]
    pkg_map = build_pkg_goods_map(pkg_fields, name2code)

    # --- BOM (native names) → bom_fields + kit lookup ---
    bom_fields = [r["fields"] for r in fetch("BOM")]
    kit = build_kit_cbm_lookup(bom_fields, item_master, name2code)

    # --- sync_parts → PT 규격 + part CBM 4-tier ---
    sp_lookup: dict[str, str] = {}
    for r in fetch("sync_parts"):
        f = r["fields"]
        code = str(f.get("파츠코드_PK") or "").strip()
        if code:
            sp_lookup[code] = str(f.get("규격") or "").strip()
    part_cbm_by_pt: dict[str, float] = {}
    for pt in set(item_master) | set(sp_lookup):
        cbm, _conf, _tier = part_cbm_for_pt(pt, item_master, sp_lookup)
        if cbm > 0:
            part_cbm_by_pt[pt] = cbm

    # --- InventoryLedger → stock_rows (synth zone_type=STORAGE; Stock_Type filter kept) ---
    # jisu InventoryLedger carries the resolved pt + Stock_Type but no Location/zone link
    # (the seed dropped it). Seeded rows ARE storage stock, so we tag zone_type=STORAGE so
    # MRP can net real stock; the UNRESTRICTED Stock_Type filter still does the real gating.
    stock_rows = []
    for r in fetch("InventoryLedger"):
        f = r["fields"]
        pt = str(f.get("pt") or "").strip() or (
            parse_pt_from_ledger_key(str(f.get("Ledger_Key") or "")) or "")
        if not pt:
            continue
        stock_rows.append({
            "pt": pt, "stock": f.get("Current_Stock") or 0, "warehouse": "jisu",
            "zone_type": ZONE_TYPE_INCLUDE, "stock_type": str(f.get("Stock_Type") or ""),
        })

    # --- Location → max staging CBM ---
    max_staging = sum(
        _f(r["fields"].get("Max_CBM")) for r in fetch("Location")
        if r["fields"].get("Zone_Type") == "INBOUND_STAGING") or None

    # --- Shipment → per-PNA count (jisu renamed 'project code' → 'project_code') ---
    shipment_count: dict[str, int] = {}
    for r in fetch("Shipment"):
        m = PNA_RE.search(str(r["fields"].get("project_code") or ""))
        if m:
            shipment_count[m.group(0)] = shipment_count.get(m.group(0), 0) + 1

    return CascadeContext(
        pkg_map=pkg_map, product_lookup=product_lookup, kit_lookup=kit,
        shipment_count=shipment_count, bom_fields=bom_fields, stock_rows=stock_rows,
        part_cbm_by_pt=part_cbm_by_pt, mes_rows=[], name_to_code=name2code,
        product_by_code=product_by_code, max_staging_cbm=max_staging,
        rates=rates_for(today.isoformat()), today=today)


def load_orders():
    """Fetch jisu order rows and remap renamed fields back to live names."""
    records = []
    for r in fetch("order"):
        f = dict(r["fields"])
        for jisu_name, live_name in ORDER_ALIAS.items():
            if jisu_name in f and live_name not in f:
                f[live_name] = f[jisu_name]
        records.append({"id": r["id"], "createdTime": r.get("createdTime", ""), "fields": f})
    return records


def write_ledger(rows):
    """INSERT-only into jisu PropagationLedger (batches of 10, urllib, typecast)."""
    tid = IDS["PropagationLedger"]
    created = 0
    for i in range(0, len(rows), 10):
        chunk = [{"fields": {k: v for k, v in row.items() if v is not None}}
                 for row in rows[i:i + 10]]
        body = json.dumps({"records": chunk, "typecast": True}).encode()
        req = urllib.request.Request(
            f"https://api.airtable.com/v0/{BASE}/{tid}", data=body, method="POST",
            headers={"Authorization": f"Bearer {_pat()}", "Content-Type": "application/json"})
        created += len(_open(req).get("records", []))
        time.sleep(0.22)
    return created


def main():
    ap = argparse.ArgumentParser(description="jisu sandbox order cascade simulation")
    ap.add_argument("--write", action="store_true", help="INSERT into jisu PropagationLedger")
    ap.add_argument("--window", type=int, default=3650,
                    help="forward createdTime window in days (default 3650 = all seeded)")
    ap.add_argument("--out", default=os.path.join(
        os.environ.get("TMPDIR", "."), "simulate_jisu_report.json"),
        help="dry-run report json path")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    today = date.today()
    run_id = "jisu-" + now.astimezone(KST).strftime("%Y%m%d-%H%M")

    print("· building jisu context …", flush=True)
    ctx = build_jisu_context(today)
    print(f"  product_lookup {len(ctx.product_lookup)} · item_master(part_cbm) "
          f"{len(ctx.part_cbm_by_pt)} · bom {len(ctx.bom_fields)} · stock_rows "
          f"{len(ctx.stock_rows)} · shipments(PNA) {len(ctx.shipment_count)} · "
          f"max_staging {ctx.max_staging_cbm}", flush=True)
    print("  [note] staging 현재점유 baseline=0 (jisu InventoryLedger에 zone 정보 없음 → "
          "stock 전량 STORAGE 태깅) — 창고적재_예상은 이 주문의 증분 입하부하만 투영", flush=True)

    orders = load_orders()
    units = collect_units(orders, now, window_days=args.window)
    latest = latest_ledger_by_pid(fetch("PropagationLedger"))
    print(f"· cascade {len(units)} units (order {len(orders)} rows, window "
          f"{args.window}d, ledger 기존 {len(latest)} 전파ID)", flush=True)

    results, totals = [], {"new": 0, "changed": 0, "unchanged": 0,
                           "완결": 0, "부분": 0, "끊김": 0}
    for u in units:
        pid = f"{u.pna}_{u.goods_name}"
        r = run_unit(u, (latest.get(pid) or {}).get("fields"), ctx, run_id)
        if r.get("ship_req"):
            r["row"]["출고요청일"] = r["ship_req"]
        if r.get("mes_by_date"):
            r["row"]["생산_납기일"] = min(r["mes_by_date"])
        results.append(r)
        totals[r["action"]] += 1
        totals[r["status"]] += 1

    in_cbm = round(sum(_f(r["row"].get("입하CBM_예상_m3")) for r in results), 3)
    mh = round(sum(_f(r["row"].get("MH_예상_h")) for r in results), 2)
    out_cbm = round(sum(_f(r["row"].get("추정_CBM_m3")) for r in results), 3)
    dated = sum(1 for r in results if r["row"].get("출고요청일"))
    print(f"  상태: 완결 {totals['완결']} / 부분 {totals['부분']} / 끊김 {totals['끊김']}", flush=True)
    print(f"  입하CBM Σ {in_cbm}m³ · M/H Σ {mh}h · 출하CBM Σ {out_cbm}m³ · "
          f"출고요청일 확보 {dated}/{len(results)} 단위", flush=True)

    to_insert = [r["row"] for r in results if r["action"] in ("new", "changed")]
    if not args.write:
        Path(args.out).write_text(json.dumps(
            {"run_id": run_id, "totals": totals, "to_insert": len(to_insert),
             "units": [{"전파ID": r["row"]["전파ID"], "상태": r["row"]["전파상태"],
                        "출고요청일": r["row"].get("출고요청일"),
                        "입하CBM": r["row"].get("입하CBM_예상_m3"),
                        "MH": r["row"].get("MH_예상_h"),
                        "출하CBM": r["row"].get("추정_CBM_m3")} for r in results]},
            ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"\n[DRY-RUN] write 0 · INSERT 대상 {len(to_insert)} · report {args.out}\n"
              f"  → --write 로 ledger 채운 뒤 rollup_jisu.py 로 주간/월간 집계", flush=True)
        return

    created = write_ledger(to_insert)
    print(f"\n[WRITE] PropagationLedger INSERT {created}행 (INSERT-only). "
          f"unchanged skip {totals['unchanged']}.\n  → rollup_jisu.py 로 주간/월간 forecast", flush=True)


if __name__ == "__main__":
    main()
