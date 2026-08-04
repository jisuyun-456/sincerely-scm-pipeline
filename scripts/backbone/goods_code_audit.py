"""Goods-code drift audit — 3-way reconciliation across the codes that the
cascade / settlement actually consume. Read-only; no Airtable writes.

마스터(Google Sheet 견적서)는 코드에서 못 읽으므로, 읽을 수 있는 3곳을 대조해
**수동 유지하는 TMS Product에 무엇을 추가/보정해야 하는지** 액션 리스트로 뽑는다:
  1. TMS Product 견적코드     (S5 출하CBM·운임정산 권위)
  2. WMS sync_item 굿즈코드    (운영 코드)
  3. live order 출하코드        (캐스케이드가 실제 필요로 하는 코드)
선택 4. 견적서 master CSV(--csv) — 있으면 drift_vs_master 버킷 추가.

규율(plan B): 신제품 Product 추가 시 ① 견적코드 = sync_item 굿즈코드 동일 문자열,
② Product 품목명 = 출하 굿즈명 일치(정산 상하차비는 코드 아닌 품목명 Jaccard로 CBM을
끌어오므로). 본 리포트의 register_in_product가 ①을, name_match_weak가 ②를 감시한다.

Usage:
  py scripts/backbone/goods_code_audit.py                         # all-time, no CSV
  py scripts/backbone/goods_code_audit.py --window 60             # 최근 60일 주문만
  py scripts/backbone/goods_code_audit.py --csv data/quotation_master.csv
"""
import argparse
import csv
import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.backbone.keys import (  # noqa: E402
    is_service,
    normalize_goods,
    parse_goods,
    resolve_goods_code,
)
from harness.backbone.product_alias import ALIAS, SIZE_FAMILY, SYNTHETIC  # noqa: E402
from harness.settlement.cbm_calc import load_product_lookup, match_product  # noqa: E402

WMS = "appLui4ZR5HWcQRri"
TMS = "app4x70a8mOrIKsMf"
ORDER = "tblJslWg8sYEdCkXw"
SYNC_ITEM = "tblwnNgHQxZ0WhDBh"
KST = timezone(timedelta(hours=9))

# 비물리 placeholder 견적코드 — 라인 굿즈명이 제각각이라 is_service로 못 거를 때가 있어
# 코드 자체로 service 처리 (analyze_cascade_vulnerability.V2_SERVICE와 동일 집합).
SERVICE_CODES = {"SSSV", "STCK", "DP45", "SLGN", "CSPR"}

# Airtable fetch (order_cascade.fetch/_get_with_retry 패턴 — scripts는 패키지 아님→복제).
_FETCH_RETRIES = 4
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


def fetch(base, tid, pat, fields=None):
    out, off = [], None
    while True:
        p = {"pageSize": 100}
        if fields:
            p["fields[]"] = fields
        if off:
            p["offset"] = off
        r = _get_with_retry(f"https://api.airtable.com/v0/{base}/{tid}", pat, p)
        d = r.json()
        out += d["records"]
        off = d.get("offset")
        if not off:
            break
    return out


# ── pure helpers (네트워크 0, 단위테스트 대상) ────────────────────────────────

def normalize_code(raw) -> str:
    """Airtable 값(리스트/None/공백 포함) → 대문자 코드. 빈값은 ""."""
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    return str(raw or "").strip().upper()


def annotate_alias(code: str) -> dict | None:
    """code가 V2 런타임 alias(ALIAS/SIZE_FAMILY/SYNTHETIC)로 가려지는지 분류."""
    c = (code or "").upper()
    if c in SYNTHETIC:
        return {"kind": "synthetic", "spec": SYNTHETIC[c]}
    if c in ALIAS:
        return {"kind": "1:1", "target": ALIAS[c]}
    if c in SIZE_FAMILY:
        return {"kind": "size_family", "targets": SIZE_FAMILY[c]}
    return None


def classify(sources: dict) -> dict:
    """primitive 소스 → 액션 버킷. 순수함수 (네트워크·match_product 호출 없음).

    sources keys:
      product   : {code: {name, box_type, qty_per_box, cbm_per_box, rec_id}}
      sync      : set[code]
      ship      : {code: freq}            (service 라인은 이미 제외됨)
      ship_goods: {code: [굿즈명, ...]}
      name_weak : {code: [{name, score, matched_code}, ...]}  (precomputed)
      csv       : {code: {box_type, qty_per_box, cbm_per_box}} | None
    """
    product = sources["product"]
    sync = sources["sync"]
    ship = sources["ship"]
    ship_goods = sources.get("ship_goods", {})
    name_weak = sources.get("name_weak", {})
    csv_master = sources.get("csv")

    buckets = {
        "register_in_product": [],
        "alias_papered_over": [],
        "name_match_weak": [],
        "data_gap": [],
        "stale_unused": [],
        "sync_only_unshipped": [],
        "service_codes": [],
        "drift_vs_master": [],
    }

    universe = set(product) | set(sync) | set(ship)
    if csv_master:
        universe |= set(csv_master)

    for code in sorted(universe):
        in_p = code in product
        in_s = code in sync
        freq = ship.get(code, 0)
        in_ship = freq > 0
        alias = annotate_alias(code)
        goods = sorted(ship_goods.get(code, []))[:3]

        if code in SERVICE_CODES:           # 비물리 placeholder → 등록 대상 아님
            buckets["service_codes"].append({"code": code, "freq": freq, "goods": goods})
            continue

        if not in_p:
            if alias:
                buckets["alias_papered_over"].append(
                    {"code": code, "freq": freq, "goods": goods, "alias": alias})
            elif in_ship:
                buckets["register_in_product"].append(
                    {"code": code, "freq": freq, "in_sync": in_s, "goods": goods})
            elif csv_master and code in csv_master:
                # 견적서 master에만 있고 Product 미등록 → 등록 필요 (아직 미출하)
                buckets["register_in_product"].append(
                    {"code": code, "freq": 0, "in_sync": in_s, "goods": goods,
                     "source": "csv_master"})
            elif in_s:
                buckets["sync_only_unshipped"].append({"code": code, "goods": goods})
        else:
            meta = product[code]
            if meta.get("cbm_per_box", 0) <= 0:
                buckets["data_gap"].append(
                    {"code": code, "name": meta.get("name"),
                     "box_type": meta.get("box_type"), "rec_id": meta.get("rec_id")})
            if not in_ship:
                buckets["stale_unused"].append({"code": code, "name": meta.get("name")})

        if code in name_weak:
            buckets["name_match_weak"].append(
                {"code": code, "freq": freq, "weak": name_weak[code][:5]})

        if csv_master and code in csv_master and in_p:
            cm, pm = csv_master[code], product[code]
            diffs = {}
            if str(cm.get("box_type") or "") != str(pm.get("box_type") or ""):
                diffs["box_type"] = [cm.get("box_type"), pm.get("box_type")]
            if int(cm.get("qty_per_box") or 0) != int(pm.get("qty_per_box") or 0):
                diffs["qty_per_box"] = [cm.get("qty_per_box"), pm.get("qty_per_box")]
            if abs(float(cm.get("cbm_per_box") or 0) - float(pm.get("cbm_per_box") or 0)) > 1e-4:
                diffs["cbm_per_box"] = [cm.get("cbm_per_box"), pm.get("cbm_per_box")]
            if diffs:
                buckets["drift_vs_master"].append({"code": code, "diffs": diffs})

    return buckets


# ── source loading (네트워크) ────────────────────────────────────────────────

def _load_csv_master(csv_path: Path) -> dict | None:
    if not csv_path.exists():
        print(f"[WARN] --csv 파일 없음: {csv_path} — drift_vs_master 생략", flush=True)
        return None
    out = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            code = normalize_code(row.get("견적코드") or row.get("code"))
            if not code:
                continue
            out[code] = {
                "box_type": (row.get("박스명칭") or "").strip(),
                "qty_per_box": row.get("박스당수량") or row.get("박스당 제품수") or 0,
                "cbm_per_box": row.get("박스당CBM") or row.get("박스 당 CBM") or 0,
            }
    return out


def load_sources(tp: str, wp: str, csv_path: Path | None, window_days: int | None) -> dict:
    print("로딩: TMS Product 룩업...", flush=True)
    lookup = load_product_lookup({"Authorization": f"Bearer {tp}"})
    product, product_names = {}, {}
    for e in lookup.values():
        code = normalize_code(e.get("code"))
        if not code:
            continue
        product[code] = {
            "name": e.get("name", ""), "box_type": e.get("box_type", ""),
            "qty_per_box": e.get("qty_per_box", 1), "cbm_per_box": e.get("cbm_per_box", 0),
            "rec_id": e.get("rec_id", ""),
        }

    print("로딩: WMS sync_item...", flush=True)
    sync, sync_goods = set(), defaultdict(set)
    for r in fetch(WMS, SYNC_ITEM, wp, ["굿즈명", "굿즈코드"]):
        f = r["fields"]
        code = normalize_code(f.get("굿즈코드"))
        if code:
            sync.add(code)
            nm = str(f.get("굿즈명") or "").strip()
            if nm:
                sync_goods[code].add(nm)

    print("로딩: WMS order 출하코드...", flush=True)
    cutoff = None
    if window_days:
        cutoff = (datetime.now(KST) - timedelta(days=window_days)).isoformat()
    ship_freq = Counter()
    ship_goods = defaultdict(set)
    service_filtered = 0
    for rec in fetch(WMS, ORDER, wp,
                     ["project_code", "굿즈코드 (from sync_itemdb)", "굿즈 주문 수량 (자동)"]):
        if cutoff and str(rec.get("createdTime") or "") < cutoff:
            continue
        f = rec.get("fields", {})
        goods_name, _ = parse_goods(str(f.get("굿즈 주문 수량 (자동)") or ""))
        if goods_name and is_service(goods_name):
            service_filtered += 1
            continue
        code, _src = resolve_goods_code(f)
        if not code:
            continue
        ship_freq[code] += 1
        if goods_name:
            ship_goods[code].add(goods_name)

    # name_match_weak: ship∩product 중, 출하 굿즈명이 match_product로 자기 코드 entry를
    # 못 찾는 것 (settlement 이름매칭 경로가 실패할 코드).
    name_weak = {}
    for code in set(ship_freq) & set(product):
        weak = []
        for nm in sorted(ship_goods.get(code, [])):
            _k, entry, score = match_product(nm, lookup)
            matched = normalize_code(entry.get("code")) if entry else None
            if entry is None or matched != code:
                weak.append({"name": nm, "score": round(score, 3), "matched_code": matched})
        if weak:
            name_weak[code] = weak

    csv_master = _load_csv_master(csv_path) if csv_path else None

    return {
        "product": product, "product_names": product_names,
        "sync": sync, "sync_goods": {k: sorted(v) for k, v in sync_goods.items()},
        "ship": dict(ship_freq), "ship_goods": {k: sorted(v) for k, v in ship_goods.items()},
        "name_weak": name_weak, "csv": csv_master,
        "service_filtered": service_filtered,
    }


# ── report output ────────────────────────────────────────────────────────────

def _md_table(rows: list[dict], cols: list[tuple[str, str]]) -> list[str]:
    out = ["| " + " | ".join(h for _, h in cols) + " |",
           "|" + "|".join("---" for _ in cols) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(r.get(k, "")) for k, _ in cols) + " |")
    return out


def write_report(out_dir: Path, run_id: str, sources: dict, buckets: dict) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stats = {
        "product": len(sources["product"]), "sync": len(sources["sync"]),
        "ship_distinct": len(sources["ship"]),
        "universe": len(set(sources["product"]) | set(sources["sync"]) | set(sources["ship"])),
        "service_filtered": sources.get("service_filtered", 0),
    }
    payload = {
        "run_id": run_id, "csv_used": sources.get("csv") is not None,
        "stats": stats,
        "buckets": {k: v for k, v in buckets.items()},
    }
    out_path = out_dir / f"audit_{run_id}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "latest_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # stdout markdown
    print(f"\n# Goods-Code Drift Report — {run_id}\n")
    print(f"- Product {stats['product']} / sync_item {stats['sync']} / "
          f"출하 distinct {stats['ship_distinct']} / universe {stats['universe']} "
          f"/ service 제외 {stats['service_filtered']}\n")

    reg = buckets["register_in_product"]
    print(f"## 1. register_in_product — Product 등록 필요 ({len(reg)})  ← S5 미산출 직접 원인")
    print("\n".join(_md_table(sorted(reg, key=lambda x: -x["freq"]),
          [("code", "코드"), ("freq", "출하빈도"), ("in_sync", "sync"), ("goods", "굿즈명")])) if reg else "  (없음)")

    al = buckets["alias_papered_over"]
    print(f"\n## 2. alias_papered_over — V2 런타임 다리 (은퇴 백로그) ({len(al)})")
    for r in sorted(al, key=lambda x: -x["freq"]):
        print(f"  {r['code']:6s} freq={r['freq']:3d}  {r['alias']['kind']:11s}  {r['goods']}")

    nw = buckets["name_match_weak"]
    print(f"\n## 3. name_match_weak — 정산 품목명 매칭 약함 ({len(nw)})  ← 정산 상하차비 영향")
    for r in sorted(nw, key=lambda x: -x["freq"]):
        print(f"  {r['code']:6s} freq={r['freq']:3d}  {r['weak']}")

    dg = buckets["data_gap"]
    print(f"\n## 4. data_gap — Product에 있으나 박스/CBM 미입력 ({len(dg)})")
    for r in dg:
        print(f"  {r['code']:6s} box='{r['box_type']}'  ({r['name']})  rec={r['rec_id']}")

    print(f"\n## 5. stale_unused: {len(buckets['stale_unused'])}  | "
          f"sync_only_unshipped: {len(buckets['sync_only_unshipped'])}  | "
          f"service_codes: {len(buckets['service_codes'])}")
    if sources.get("csv") is not None:
        print(f"## 6. drift_vs_master: {len(buckets['drift_vs_master'])}")
        for r in buckets["drift_vs_master"]:
            print(f"  {r['code']:6s} {r['diffs']}")

    print("\n## 다음 액션")
    print(f"  - Product 신규 등록: {len(reg)}건 (견적코드 = sync_item 코드 동일 문자열)")
    print(f"  - alias 은퇴 후보: {len(al)}건")
    print(f"  - Product 품목명 보정(정산): {len(nw)}건")
    print(f"  - 박스/CBM 채우기: {len(dg)}건")
    print(f"\n[saved] {out_path}")
    return out_path


def main():
    ap = argparse.ArgumentParser(description="Goods-code drift audit (read-only)")
    ap.add_argument("--csv", type=str, default=None, help="견적서 master CSV 경로 (선택)")
    ap.add_argument("--window", type=int, default=None, help="최근 N일 주문만 (기본 all-time)")
    ap.add_argument("--out", type=str, default="data/goods_code_audit", help="출력 디렉터리")
    args = ap.parse_args()

    load_dotenv()
    tp = os.environ["AIRTABLE_PAT"]
    wp = os.environ["AIRTABLE_WMS_PAT"]
    csv_path = Path(args.csv) if args.csv else None

    sources = load_sources(tp, wp, csv_path, args.window)
    buckets = classify(sources)
    run_id = datetime.now(KST).strftime("%Y%m%d-%H%M")
    write_report(Path(args.out), run_id, sources, buckets)


if __name__ == "__main__":
    main()
