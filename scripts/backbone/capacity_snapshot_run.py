"""P4 — capacity_series.json 시계열 runner (Airtable write 0, 로컬 파일만).

3트랙을 스냅샷 1건으로 집계해 data/capacity_series.json에 idempotent append.
출고: TMS Shipment(출하확정일 14d 윈도우, CBM_유효) / 보관: InventoryLedger×ItemMaster
/ 입하: movement(입하예상일 14d 윈도우, EXTERNAL_INBOUND_PURPOSES) + MES 납기일
forecast(AIRTABLE_MES_PAT 부재·실패 시 null 생략 — 핵심 3트랙은 영향 없음).

Usage:
  python scripts/backbone/capacity_snapshot_run.py            # series append
  python scripts/backbone/capacity_snapshot_run.py --dry-run  # 스냅샷 출력만
"""
import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness._core.calendar import KST, today_kst  # noqa: E402
from harness.backbone.capacity_snapshot import (  # noqa: E402
    HORIZON_DAYS, append_series, build_inbound_scheduled,
    build_outbound_forward, build_snapshot,
)
from harness.backbone.keys import normalize_goods  # noqa: E402
from harness.backbone.mes_forecast import build_inbound_forecast  # noqa: E402
from harness.backbone.storage import (  # noqa: E402
    aggregate_occupied, parse_pt_from_ledger_key,
)
from harness.settlement.cbm_calc import load_product_lookup  # noqa: E402
from utils.cbm_utils import (  # noqa: E402
    EXTERNAL_INBOUND_PURPOSES, fetch_inbound_cbm, load_sync_parts_lookup,
)

load_dotenv()
TP = os.environ["AIRTABLE_PAT"]
WP = os.environ["AIRTABLE_WMS_PAT"]
MP = os.environ.get("AIRTABLE_MES_PAT")   # 없으면 MES forecast 생략
TMS = "app4x70a8mOrIKsMf"
WMS = "appLui4ZR5HWcQRri"
MES = "appNSAPadsHbfaSHv"
SHIP = "tbllg1JoHclGYer7m"
ITEM = "tbl5ZGY373D5SCONV"     # WMS_ItemMaster
LEDGER = "tbl4DcXQRHJj921MN"   # WMS_InventoryLedger
LOC = "tblRwUTP5kWnHFt5P"      # WMS_Location
MES_V2 = "tblg96ys2vfPdyxHq"   # MES ver.2.0 (primary)
SYNC_ITEM = "tblwnNgHQxZ0WhDBh"
SERIES_PATH = Path(__file__).resolve().parents[2] / "data" / "capacity_series.json"


_FETCH_RETRIES = 4          # cron 무인 실행 transient 보강 (order_cascade._get_with_retry 이식)
_RETRY_STATUS = {429, 500, 502, 503, 504}


def _get_with_retry(url, pat, params):
    """timeout·연결오류·429/5xx에 한해 지수 backoff 재시도, 소진 시 loud raise."""
    for attempt in range(1, _FETCH_RETRIES + 1):
        try:
            r = requests.get(url, headers={"Authorization": f"Bearer {pat}"},
                             params=params, timeout=60)
            if r.status_code in _RETRY_STATUS:
                raise requests.exceptions.RetryError(
                    f"HTTP {r.status_code}: {r.text[:200]}")
            r.raise_for_status()
            return r
        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
                requests.exceptions.RetryError) as err:
            if attempt == _FETCH_RETRIES:
                raise
            wait = 2 ** attempt
            print(f"[RETRY {attempt}/{_FETCH_RETRIES}] {url.rsplit('/', 1)[-1]} "
                  f"{type(err).__name__} — {wait}s 후 재시도", flush=True)
            time.sleep(wait)


def fetch(base, tid, pat, fields, formula=None):
    out, off = [], None
    url = f"https://api.airtable.com/v0/{base}/{tid}"
    while True:
        p = {"pageSize": 100, "fields[]": fields}
        if off:
            p["offset"] = off
        if formula:
            p["filterByFormula"] = formula
        r = _get_with_retry(url, pat, p)
        d = r.json()
        out += d["records"]
        off = d.get("offset")
        if not off:
            break
    return out


def n(x):
    try:
        return float(str(x).replace(",", "") or 0)
    except (ValueError, TypeError):
        return 0.0


def collect_outbound(today):
    """출하확정일 윈도우 서버필터 — CBM_유효 formula coalesce 소비."""
    end = today + timedelta(days=HORIZON_DAYS)
    formula = (
        "AND({출하확정일}!='', "
        f"IS_AFTER({{출하확정일}}, DATEADD('{today.isoformat()}', -1, 'days')), "
        f"IS_BEFORE({{출하확정일}}, DATEADD('{end.isoformat()}', 1, 'days')))"
    )
    recs = fetch(TMS, SHIP, TP, ["출하확정일", "CBM_유효"], formula)
    rows = [{"ship_date": r["fields"].get("출하확정일"),
             "cbm_valid": n(r["fields"].get("CBM_유효"))} for r in recs]
    print(f"  출고: 윈도우 {len(rows)}건", flush=True)
    return build_outbound_forward(rows, today)


def collect_storage_and_max():
    """보관 occupied 분자 (storage_occupied.py 패턴) + Max_CBM 분모 맵."""
    locs = {r["id"]: r["fields"]
            for r in fetch(WMS, LOC, WP, ["Warehouse", "Zone_Type", "Max_CBM"])}
    storage_max, staging_max = {}, {}
    for f in locs.values():
        mx = n(f.get("Max_CBM"))
        if mx <= 0:
            continue
        wh = f.get("Warehouse") or "미지정"
        if f.get("Zone_Type") == "STORAGE":
            storage_max[wh] = round(storage_max.get(wh, 0.0) + mx, 4)
        elif f.get("Zone_Type") == "INBOUND_STAGING":
            staging_max[wh] = round(staging_max.get(wh, 0.0) + mx, 4)
    items = fetch(WMS, ITEM, WP, ["품목키", "CBM_개당_m3"])
    part_cbm = {r["fields"]["품목키"]: r["fields"]["CBM_개당_m3"]
                for r in items
                if (r["fields"].get("CBM_개당_m3") or 0) > 0
                and parse_pt_from_ledger_key(str(r["fields"].get("품목키", "")))}
    ledger = fetch(WMS, LEDGER, WP,
                   ["Ledger_Key", "Current_Stock", "Location", "Stock_Type"])
    rows = []
    for rec in ledger:
        f = rec.get("fields", {})
        pt = parse_pt_from_ledger_key(str(f.get("Ledger_Key", "")))
        if not pt:
            continue
        loc_ids = f.get("Location") or []
        loc = locs.get(loc_ids[0], {}) if loc_ids else {}
        rows.append({"pt": pt, "stock": f.get("Current_Stock") or 0,
                     "warehouse": loc.get("Warehouse") or "미지정",
                     "zone_type": loc.get("Zone_Type") or "",
                     "stock_type": f.get("Stock_Type") or ""})
    agg = aggregate_occupied(rows, part_cbm)
    print(f"  보관: occupied {agg['total_occupied_cbm']}m³ "
          f"(PT 커버 {agg['pt_coverage_pct']}%) | Max 시드 "
          f"storage={storage_max} staging={staging_max}", flush=True)
    return agg, storage_max, staging_max


def collect_inbound(today):
    """movement 입하예상일 윈도우 — 외부입하 subset (CP② 분류)."""
    sp_lookup = load_sync_parts_lookup()
    out = fetch_inbound_cbm(sp_lookup, since=today,
                            until=today + timedelta(days=HORIZON_DAYS),
                            purposes=EXTERNAL_INBOUND_PURPOSES)
    print(f"  입하: 윈도우 {len(out['records'])}건 "
          f"(규격해소 {out['n_matched']}/{out['n_matched'] + out['n_unmatched']})",
          flush=True)
    return build_inbound_scheduled(out["records"], today)


def collect_mes(today):
    """MES 납기일 forecast — PAT 부재/요청 실패 시 None (graceful skip)."""
    if not MP:
        print("  MES: AIRTABLE_MES_PAT 미설정 — forecast 생략(null)", flush=True)
        return None
    try:
        mes = fetch(MES, MES_V2, MP, ["굿즈", "계획수량", "납기일", "작업 상태"])
        items = fetch(WMS, SYNC_ITEM, WP, ["굿즈명", "굿즈코드"])
        name2code = {}
        for r in items:
            f = r["fields"]
            nm = normalize_goods(str(f.get("굿즈명") or ""))
            cd = str(f.get("굿즈코드") or "").strip().upper()
            if nm and cd:
                name2code[nm] = cd
        lk = load_product_lookup({"Authorization": f"Bearer {TP}"})
        product_by_code = {}
        for e in lk.values():
            code = str(e.get("code") or "").strip().upper()
            if code and e.get("cbm_per_box", 0) > 0:
                product_by_code[code] = (e.get("qty_per_box") or 1, e["cbm_per_box"])
        out = build_inbound_forecast([r["fields"] for r in mes],
                                     name2code, product_by_code, today)
        print(f"  MES: join {out['n_joined']}/{out['n_total']} | "
              f"by_horizon {out['by_horizon']}", flush=True)
        return out
    except requests.RequestException as e:
        print(f"  MES: 요청 실패({e.__class__.__name__}) — forecast 생략(null)", flush=True)
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="스냅샷 출력만, 파일 미기록")
    args = ap.parse_args()

    today = today_kst()
    print(f"=== capacity snapshot {today} (horizon {HORIZON_DAYS}d) ===", flush=True)
    outbound = collect_outbound(today)
    storage_agg, storage_max, staging_max = collect_storage_and_max()
    inbound = collect_inbound(today)
    mes = collect_mes(today)

    snap = build_snapshot(today, outbound, storage_agg, inbound, mes,
                          storage_max_cbm=storage_max, staging_max_cbm=staging_max,
                          generated_at=datetime.now(KST).isoformat())

    print("\n--- snapshot 요약 ---")
    print(f"출고 forward 14d: {outbound['forward_total_cbm']}m³ "
          f"({outbound['n_shipments_window']}건, 커버 {outbound['coverage_pct']}%)")
    print(f"보관 occupied: {storage_agg['total_occupied_cbm']}m³ "
          f"(PT 커버 {storage_agg['pt_coverage_pct']}%)")
    print(f"입하 scheduled 14d: {inbound['scheduled_total_cbm']}m³ "
          f"({inbound['n_rows_window']}건, 커버 {inbound['coverage_pct']}%)")
    print(f"MES forecast: {'null' if mes is None else mes['by_horizon']}")

    if args.dry_run:
        print("\n[DRY-RUN] 파일 미기록. snapshot JSON:")
        print(json.dumps(snap, ensure_ascii=False, indent=2))
        return

    series = []
    if SERIES_PATH.exists():
        series = json.loads(SERIES_PATH.read_text(encoding="utf-8"))
    series = append_series(series, snap)
    SERIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=SERIES_PATH.parent,
                                     suffix=".tmp", delete=False) as tf:
        json.dump(series, tf, ensure_ascii=False, indent=1)
        tmp = tf.name
    os.replace(tmp, SERIES_PATH)
    print(f"\n[APPEND] {SERIES_PATH.name}: {len(series)} 엔트리 "
          f"(snapshot_date {snap['snapshot_date']})", flush=True)


if __name__ == "__main__":
    main()
