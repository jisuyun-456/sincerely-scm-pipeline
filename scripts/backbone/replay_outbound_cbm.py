"""P1 Task 1.5 — 결정론 출고 CBM replay.

dry-run(기본, 쓰기 0): 16,190 shipment을 결정론 경로(견적코드 조인)로 통과시켜
  resolvable% 측정 → Gate ≥70% 판정.
--write: deterministic(conf≥0.7) shipment에 estimated_cbm/estimation_confidence/
  estimation_updated_at batch PATCH (10/req). Total_CBM 미터치. idempotent(동일 est skip).

조인: Shipment.'project code'(공백) PNA → order.project_code(_) PNA 그룹 →
  order.굿즈코드 → Product[견적코드] CBM. 1출하 프로젝트만 기록(다차=partial_skip).

Usage:
  python scripts/backbone/replay_outbound_cbm.py            # dry-run 측정
  python scripts/backbone/replay_outbound_cbm.py --write    # live PATCH (CHECKPOINT 후)
"""
import argparse
import collections
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.settlement.cbm_calc import load_product_lookup  # noqa: E402
from harness.dispatch.cbm_estimator import (  # noqa: E402
    estimate_shipment_cbm_deterministic, estimate_shipment_cbm, build_kit_cbm_lookup,
)
from harness.backbone.keys import (  # noqa: E402
    resolve_goods_code, build_pkg_goods_map, normalize_goods,
)

load_dotenv()
TP = os.environ["AIRTABLE_PAT"]
WP = os.environ["AIRTABLE_WMS_PAT"]
TMS = "app4x70a8mOrIKsMf"
WMS = "appLui4ZR5HWcQRri"
SHIP = "tbllg1JoHclGYer7m"
ORDER = "tblJslWg8sYEdCkXw"
PKG_SCHED = "tblae2NqJaexwjN9R"   # WMS ⚡pkg_schedule mirror (굿즈코드 필드 없음 — 굿즈명만)
SYNC_ITEM = "tblwnNgHQxZ0WhDBh"   # WMS ⚡sync_item (굿즈명→굿즈코드 브릿지)
BOM_TBL = "tblopHqepkx6mNEHL"     # WMS_BOM (kit-CBM 폴백 소스)
ITEM_TBL = "tbl5ZGY373D5SCONV"    # WMS_ItemMaster
PNA = re.compile(r"PNA\d+")
WRITE_TOL = 1e-4  # idempotency: 기존 estimated_cbm와 이 이내면 skip


def fetch(base, tid, pat, fields):
    out, off = [], None
    while True:
        p = {"pageSize": 100, "fields[]": fields}
        if off:
            p["offset"] = off
        r = requests.get(
            f"https://api.airtable.com/v0/{base}/{tid}",
            headers={"Authorization": f"Bearer {pat}"}, params=p, timeout=60,
        )
        r.raise_for_status()
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


def patch_batch(url, headers, batch):
    """10건 이하 batch PATCH. Returns (ok, err)."""
    for attempt in range(3):
        try:
            r = requests.patch(url, headers=headers, json={"records": batch}, timeout=30)
            time.sleep(0.25)
            if r.ok:
                return len(batch), 0
            if r.status_code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(30 * (attempt + 1))
                continue
            print(f"  ERROR {r.status_code}: {r.text[:120]}", flush=True)
            return 0, len(batch)
        except requests.exceptions.ConnectionError:
            if attempt < 2:
                time.sleep(30 * (attempt + 1))
            else:
                return 0, len(batch)
    return 0, len(batch)


def build_pkg_fallback():
    """sync_item 굿즈명→굿즈코드 + pkg_schedule → {PNA: 견적코드} (단일 코드 프로젝트만)."""
    print("pkg_schedule 폴백 맵 로딩...", flush=True)
    items = fetch(WMS, SYNC_ITEM, WP, ["굿즈명", "굿즈코드"])
    name2code = {}
    for r in items:
        f = r["fields"]
        nm = normalize_goods(str(f.get("굿즈명") or ""))
        cd = str(f.get("굿즈코드") or "").strip().upper()
        if nm and cd:
            name2code[nm] = cd
    pkgs = fetch(WMS, PKG_SCHED, WP, [
        "프로젝트 코드 (PK) (from project)",
        "주문 굿즈 리스트 (자동) (from project)",
        "단품 굿즈 품목 및 수량",
    ])
    pkg_map = build_pkg_goods_map((r["fields"] for r in pkgs), name2code)
    print(f"  pkg 폴백 맵: {len(pkg_map)} 프로젝트 (sync_item 매핑 {len(name2code)}건)", flush=True)
    return pkg_map, name2code


def build_kit_lookup(name2code):
    """WMS_BOM × ItemMaster → {(PNA, 견적코드): (kit_cbm, conf)} (P2b kit-CBM 폴백)."""
    print("WMS_BOM·ItemMaster 로딩 (kit-CBM 폴백)...", flush=True)
    bom = fetch(WMS, BOM_TBL, WP, ["프로젝트코드", "모품목_굿즈명", "소품목_PT", "소요량_개당"])
    items = fetch(WMS, ITEM_TBL, WP, ["품목키", "CBM_개당_m3", "출처"])
    item_master = {}
    for r in items:
        f = r["fields"]
        k = str(f.get("품목키") or "").strip()
        if k:
            item_master[k] = (n(f.get("CBM_개당_m3")), str(f.get("출처") or ""))
    kit = build_kit_cbm_lookup((r["fields"] for r in bom), item_master, name2code)
    print(f"  kit 폴백: {len(kit)} (프로젝트,굿즈코드) 엔트리 (BOM {len(bom)}행)", flush=True)
    return kit


def build_inputs():
    """order_by_project[PNA]=[(code,qty)], shipment_count[PNA]=N, + Product lookup."""
    print("Product 룩업 로딩...", flush=True)
    lk = load_product_lookup({"Authorization": f"Bearer {TP}"})
    print("order 로딩...", flush=True)
    orders = fetch(WMS, ORDER, WP, ["project_code", "굿즈코드 (from sync_itemdb)", "주문수량"])
    pkg_map, name2code = build_pkg_fallback()
    kit = build_kit_lookup(name2code)
    opg = collections.defaultdict(collections.Counter)
    src_count = collections.Counter()
    for r in orders:
        f = r["fields"]
        m = PNA.search(str(f.get("project_code") or ""))
        if not m:
            continue
        code, src = resolve_goods_code(f, pkg_map)
        src_count[src] += 1
        if code:
            opg[m.group(0)][code] += n(f.get("주문수량"))
    blank_total = src_count["pkg"] + src_count["none"]
    rate = src_count["pkg"] / blank_total * 100 if blank_total else 0.0
    print(f"  굿즈코드 리졸브: direct={src_count['direct']} pkg폴백={src_count['pkg']} "
          f"미회수={src_count['none']} (blank-code 회수율 {rate:.1f}%)", flush=True)
    order_by_project = {pna: list(c.items()) for pna, c in opg.items()}
    # 굿즈 CBM 커버리지 (P2b gate ≥85%): order 등장 고유 굿즈코드 기준
    codes = {c for lines in order_by_project.values() for c, _ in lines}
    direct = {c for c in codes
              if (lk.get(str(c).lower()) or {}).get("cbm_per_box", 0) > 0}
    covered = direct | ({c for _, c in kit} & codes)
    print(f"  굿즈 CBM 커버리지: direct {len(direct)}/{len(codes)} "
          f"({len(direct)/max(len(codes),1)*100:.1f}%) → +kit "
          f"{len(covered)}/{len(codes)} ({len(covered)/max(len(codes),1)*100:.1f}%) "
          f"[Gate ≥85%]", flush=True)
    print("shipment 로딩...", flush=True)
    ships = fetch(TMS, SHIP, TP, ["project code", "Total_CBM", "estimated_cbm",
                                  "최종 출고 품목 및 수량", "최종 출하 품목"])
    shipment_count = collections.Counter()
    for r in ships:
        m = PNA.search(str(r["fields"].get("project code") or ""))
        if m:
            shipment_count[m.group(0)] += 1
    return lk, order_by_project, dict(shipment_count), ships, kit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="live PATCH estimated_cbm (CHECKPOINT 후)")
    ap.add_argument("--recent", type=int, default=0,
                    help="최근 N일 shipment만 측정 (createdTime 기준; order 미러 커버리지 window forward-coverage 측정용)")
    args = ap.parse_args()

    lk, obp, scount, ships, kit = build_inputs()
    full = len(ships)
    if args.recent:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=args.recent)).isoformat()
        ships = [r for r in ships if r.get("createdTime", "") >= cutoff]
        print(f"\n[--recent {args.recent}d] {full} → {len(ships)}건 (createdTime ≥ {cutoff[:10]})", flush=True)
    total = len(ships)
    print(f"\n=== Shipment {total}건 결정론 replay ===", flush=True)

    measured = newly = partial = no_order = blank = unmatched_only = kit_adds = 0
    have_est_now = cbm_valid_now = 0   # P0 이후 현재 상태
    cbm_valid_after = 0                 # replay 반영 후 (deterministic only)
    cbm_valid_hybrid = 0                # deterministic + 퍼지 폴백 합산 (achievable ceiling)
    fuzzy_only_adds = 0                 # det 못 풀고 퍼지만 푸는 건수
    to_patch = []  # (rec_id, est, conf)
    for r in ships:
        f = r["fields"]
        m = PNA.search(str(f.get("project code") or ""))
        tot = n(f.get("Total_CBM"))
        est_existing = n(f.get("estimated_cbm"))
        if tot > 0:
            measured += 1
        if est_existing > 0:
            have_est_now += 1
        valid_now = tot > 0 or est_existing > 0
        if valid_now:
            cbm_valid_now += 1
        det_est = 0.0
        if not m:
            blank += 1
        else:
            res = estimate_shipment_cbm_deterministic(m.group(0), obp, lk, scount,
                                                      kit_lookup=kit)
            mode = res["mode"]
            if mode == "partial_skip":
                partial += 1
            elif mode == "no_order":
                no_order += 1
            elif res["estimated_cbm"] > 0:
                det_est = res["estimated_cbm"]
                if res["kit_used"]:
                    kit_adds += 1
                if tot <= 0:
                    newly += 1
                if res["confidence"] >= 0.7:
                    cur = n(f.get("estimated_cbm"))
                    if abs(cur - res["estimated_cbm"]) > WRITE_TOL:
                        to_patch.append((r["id"], res["estimated_cbm"], res["confidence"]))
            else:  # deterministic but est==0 (전부 unmatched/qty0)
                unmatched_only += 1
        if valid_now or det_est > 0:
            cbm_valid_after += 1
        # 퍼지 폴백 (spec §6: 다차/blank/no_order → 기존 free-text estimator)
        fuzzy_est = det_est
        if fuzzy_est <= 0 and not valid_now:
            fz = estimate_shipment_cbm(f, lk)
            fuzzy_est = fz["estimated_cbm"]
            if fuzzy_est > 0:
                fuzzy_only_adds += 1
        if valid_now or det_est > 0 or fuzzy_est > 0:
            cbm_valid_hybrid += 1

    print(f"  [현재 P0후] 실측 Total_CBM>0     : {measured:>6} ({measured/total*100:5.1f}%)")
    print(f"  [현재 P0후] estimated_cbm>0      : {have_est_now:>6} ({have_est_now/total*100:5.1f}%)")
    print(f"  [현재 P0후] CBM_유효>0 (둘 중 1) : {cbm_valid_now:>6} ({cbm_valid_now/total*100:5.1f}%)  ← 진짜 baseline")
    print("  " + "─" * 56)
    print(f"  결정론 신규 resolvable(est>0)   : {newly:>6} ({newly/total*100:5.1f}%)")
    print(f"  → CBM_유효>0 (결정론만 반영)    : {cbm_valid_after:>6} ({cbm_valid_after/total*100:5.1f}%)")
    print(f"  퍼지 폴백 추가(free-text)       : {fuzzy_only_adds:>6} ({fuzzy_only_adds/total*100:5.1f}%)")
    print(f"  → CBM_유효>0 (결정론+퍼지 ceiling): {cbm_valid_hybrid:>5} ({cbm_valid_hybrid/total*100:5.1f}%)  [Gate ≥70%]")
    print("  " + "─" * 56)
    print(f"  kit-CBM 폴백 적용(결정론 내)    : {kit_adds:>6} ({kit_adds/total*100:5.1f}%)")
    print(f"  partial_skip(다차 출하)         : {partial:>6} ({partial/total*100:5.1f}%)")
    print(f"  no_order(PNA 매칭無 order)      : {no_order:>6} ({no_order/total*100:5.1f}%)  ← order 미러 커버리지 한계")
    print(f"  unmatched_only(코드/CBM 부재)   : {unmatched_only:>6} ({unmatched_only/total*100:5.1f}%)  ← Task 1.4 대상")
    print(f"  blank project code              : {blank:>6} ({blank/total*100:5.1f}%)")
    print(f"\n  PATCH 대상(신규/변경 estimated_cbm, 결정론 conf≥0.7): {len(to_patch)}건", flush=True)
    resolvable = cbm_valid_hybrid

    if not args.write:
        gate = "✅ PASS" if resolvable / total >= 0.70 else "❌ <70% (Task 1.4 누락코드 백필 먼저)"
        print(f"\n[DRY-RUN] Gate: {gate}. live 반영하려면 --write (CHECKPOINT 승인 후).", flush=True)
        return

    # --write: estimated_cbm batch PATCH (Total_CBM 미터치)
    now_iso = datetime.now(timezone.utc).isoformat()
    headers = {"Authorization": f"Bearer {TP}", "Content-Type": "application/json"}
    url = f"https://api.airtable.com/v0/{TMS}/{SHIP}"
    ok = err = 0
    for i in range(0, len(to_patch), 10):
        chunk = to_patch[i:i + 10]
        batch = [{"id": rid, "fields": {
            "estimated_cbm": est,
            "estimation_confidence": conf,
            "estimation_updated_at": now_iso,
        }} for rid, est, conf in chunk]
        o, e = patch_batch(url, headers, batch)
        ok += o
        err += e
        print(f"  PATCH {i + len(chunk)}/{len(to_patch)} (ok={ok} err={err})", flush=True)
    print(f"\n[WRITE] estimated_cbm patched={ok} err={err}. Total_CBM 미터치.", flush=True)


if __name__ == "__main__":
    main()
