"""NEST × WMS 키트/굿즈 레벨 BOM 시뮬레이션 — 2026-03~06 4개월 표본 (읽기 전용).

L0(프로젝트)→L1(키트/단품 포장)→L2(굿즈)→L3(PT) 레벨 전개를 표본 전체에 돌려
깊이 분포·변동성(월별 신규율·재사용)·옵션 다양성·단품박스/인쇄 프록시·문제 케이스를 집계.

읽기 전용: NEST GET + Airtable GET만. 산출물은 로컬 JSON/stdout.

Usage:
  python scripts/analysis/nest_level_sim.py --out <dir> [--from 2026-03-01 --to 2026-07-01]
"""
import argparse
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.backbone.keys import (  # noqa: E402
    PNA_RE, goods_base, is_service, normalize_goods, parse_goods,
)
from harness.backbone.product_alias import (  # noqa: E402
    inject_synthetic, resolve_registered_code,
)
from harness.settlement.cbm_calc import load_product_lookup  # noqa: E402

WMS = "appLui4ZR5HWcQRri"
ORDER = "tblJslWg8sYEdCkXw"
SYNC_ITEM = "tblwnNgHQxZ0WhDBh"
BOM_TBL = "tblopHqepkx6mNEHL"
NEST_BASE = "https://nest.sincerely.work/api/internal/v1"
PACE_SEC = 1.25
KST = timezone(timedelta(hours=9))

_PRINT_RE = re.compile(r"인쇄|프린팅|printing", re.IGNORECASE)
_BOX_RE = re.compile(r"박스|box", re.IGNORECASE)
_SIZE_RE = re.compile(r"사이즈|size", re.IGNORECASE)
_COLOR_RE = re.compile(r"색상|컬러|color", re.IGNORECASE)


def _at_get(url, pat, params, retries=4):
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers={"Authorization": f"Bearer {pat}"},
                             params=params, timeout=60)
            if r.status_code in {429, 500, 502, 503, 504}:
                raise requests.exceptions.RetryError(f"HTTP {r.status_code}")
            r.raise_for_status()
            return r
        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
                requests.exceptions.RetryError) as err:
            if attempt == retries:
                raise
            wait = 2 ** attempt
            print(f"[RETRY {attempt}/{retries}] {type(err).__name__} — {wait}s",
                  flush=True)
            time.sleep(wait)


def at_fetch(base, tid, pat, fields=None):
    out, off = [], None
    while True:
        p = {"pageSize": 100}
        if fields:
            p["fields[]"] = fields
        if off:
            p["offset"] = off
        r = _at_get(f"https://api.airtable.com/v0/{base}/{tid}", pat, p)
        d = r.json()
        out += d["records"]
        off = d.get("offset")
        if not off:
            break
        time.sleep(0.2)
    return out


def nest_fetch(pna, key, req_no):
    headers = {"X-API-Key": key, "X-Request-Id": f"scm-levelsim-{req_no:04d}"}
    url = f"{NEST_BASE}/projects/{pna}/production-specification"
    for attempt in range(1, 4):
        try:
            r = requests.get(url, headers=headers,
                             params={"view": "compact"}, timeout=30)
        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError) as err:
            if attempt == 3:
                return 0, None, type(err).__name__
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", "5") or 5))
            continue
        body = {}
        try:
            body = r.json()
        except ValueError:
            pass
        err_code = str((body.get("error") or {}).get("code") or "")
        if r.status_code == 500 and err_code != "DATA_INTEGRITY_ERROR" and attempt < 3:
            time.sleep(2 ** attempt)
            continue
        return r.status_code, (body if r.status_code == 200 else None), err_code
    return 0, None, "retries_exhausted"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--from", dest="d_from", default="2026-03-01")
    ap.add_argument("--to", dest="d_to", default="2026-07-01")
    args = ap.parse_args()
    out_dir = Path(args.out)
    (out_dir / "raw").mkdir(parents=True, exist_ok=True)

    load_dotenv()
    nest_key = os.environ["NEST_PRODUCTION_SPECIFICATION_API_KEY"]
    tp = os.environ["AIRTABLE_PAT"]
    wp = os.environ["AIRTABLE_WMS_PAT"]

    print("로딩: TMS Product...", flush=True)
    lookup = load_product_lookup({"Authorization": f"Bearer {tp}"})
    inject_synthetic(lookup)
    registered = {k.upper() for k, e in lookup.items()
                  if e.get("code", "").lower() == k and e.get("cbm_per_box", 0) > 0}

    print("로딩: sync_item / WMS_BOM / order...", flush=True)
    name2code, sync_codes = {}, set()
    for r in at_fetch(WMS, SYNC_ITEM, wp, ["굿즈명", "굿즈코드"]):
        f = r["fields"]
        nm = normalize_goods(str(f.get("굿즈명") or ""))
        cd = str(f.get("굿즈코드") or "").strip().upper()
        if cd:
            sync_codes.add(cd)
        if nm and cd:
            name2code[nm] = cd

    bom_by_goods = defaultdict(list)   # goods_base(모품목) → [(PT, 소요량, 구성유형)]
    comp_types = Counter()
    for r in at_fetch(WMS, BOM_TBL, wp,
                      ["모품목_굿즈명", "소품목_PT", "소요량_개당", "구성유형"]):
        f = r["fields"]
        gb = goods_base(str(f.get("모품목_굿즈명") or "")).strip()
        pt = str(f.get("소품목_PT") or "").strip()
        ctype = str(f.get("구성유형") or "").strip()
        if gb and pt:
            bom_by_goods[gb].append((pt, f.get("소요량_개당"), ctype))
            comp_types[ctype or "(공백)"] += 1

    orders = at_fetch(WMS, ORDER, wp, ["project_code", "굿즈 주문 수량 (자동)",
                                       "굿즈코드 (from sync_itemdb)"])
    pna_month, ord_names = {}, defaultdict(set)
    for rec in orders:
        f = rec["fields"]
        m = PNA_RE.search(str(f.get("project_code") or ""))
        if not m:
            continue
        pna = m.group(0)
        ct = str(rec.get("createdTime") or "")[:10]
        if args.d_from <= ct < args.d_to:
            if pna not in pna_month or ct < pna_month[pna]:
                pna_month[pna] = ct
        gname = parse_goods(str(f.get("굿즈 주문 수량 (자동)") or ""))[0]
        if gname and not is_service(gname):
            ord_names[pna].add(gname)
    scope = sorted(pna_month, key=lambda p: pna_month[p])
    print(f"표본: {args.d_from}~{args.d_to} PNA {len(scope)}건 "
          f"(예상 소요 ~{len(scope) * PACE_SEC / 60:.0f}분)", flush=True)

    # ── NEST 배치 (raw 캐시 재사용 — 재실행 안전) ──
    statuses, snapshots = {}, {}
    n_call = 0
    for pna in scope:
        cache = out_dir / "raw" / f"{pna}.json"
        if cache.exists():
            snapshots[pna] = json.loads(cache.read_text(encoding="utf-8"))
            statuses[pna] = "200:cached"
            continue
        n_call += 1
        st, payload, err = nest_fetch(pna, nest_key, n_call)
        statuses[pna] = f"{st}:{err or 'OK'}"
        if payload:
            snapshots[pna] = payload
            cache.write_text(json.dumps(payload, ensure_ascii=False),
                             encoding="utf-8")
        if n_call % 25 == 0:
            print(f"  ...{n_call} calls", flush=True)
        time.sleep(PACE_SEC)
    print(f"NEST 호출 {n_call}건 (캐시 {len(scope) - n_call}건)", flush=True)

    # ── 레벨 분석 ──
    month_of = {p: pna_month[p][:7] for p in scope}
    monthly = defaultdict(lambda: defaultdict(int))
    first_seen_code, first_seen_kitsig = {}, {}
    code_projects = defaultdict(set)
    code_names = defaultdict(set)
    opt_categories = Counter()
    kit_lines_dist, qpk_values, kit_memos = [], [], Counter()
    depth_dist = Counter()
    proj_rows = []
    box_crosstab = Counter()   # (in_kit, has_box_bom_line)
    print_stats = Counter()
    multi_inst = 0
    nest_not_in_sync = set()

    for pna in scope:
        mo = month_of[pna]
        monthly[mo]["projects"] += 1
        st = statuses.get(pna, "")
        if not st.startswith("200"):
            monthly[mo]["nest_404" if st.startswith("404") else "nest_err"] += 1
            continue
        ps = (snapshots[pna].get("productionSpecification") or {})
        goods = [g for g in ps.get("quoteGoods", [])]
        asm = ps.get("assemblies", []) or []
        kit_goods_iids = set()
        for a in asm:
            for ag in (a.get("assignedGoods") or []):
                kit_goods_iids.add(str(ag.get("quoteGoodsInstanceId") or ""))
            pgo = a.get("packageGoods") or {}
            kit_goods_iids.add(str(pgo.get("quoteGoodsInstanceId") or ""))

        phys, svc_n = [], 0
        seen_codes_this = Counter()
        for g in goods:
            name = str(g.get("goodsName") or "").strip()
            code = str(g.get("goodsCode") or "").strip().upper()
            if is_service(name):
                svc_n += 1
                continue
            phys.append(g)
            seen_codes_this[code] += 1
            code_projects[code].add(pna)
            code_names[code].add(name)
            if code and code not in sync_codes:
                nest_not_in_sync.add(code)
            if code not in first_seen_code:
                first_seen_code[code] = mo
                monthly[mo]["new_codes"] += 1
            monthly[mo]["goods_instances"] += 1
            has_print_opt = False
            for it in (g.get("quoteItems") or []):
                cat = str(it.get("optionCategoryName") or "")
                opt_categories[cat] += 1
                if _PRINT_RE.search(cat):
                    has_print_opt = True
            # L3: WMS_BOM 연쇄 + 구성유형 프록시
            brows = bom_by_goods.get(goods_base(name), [])
            has_box_line = any(_BOX_RE.search(c or "") for _pt, _q, c in brows)
            has_print_line = any(_PRINT_RE.search(c or "") for _pt, _q, c in brows)
            in_kit = str(g.get("quoteGoodsInstanceId") or "") in kit_goods_iids
            box_crosstab[(in_kit, has_box_line)] += 1
            print_stats["opt_print" if has_print_opt else "opt_noprint"] += 1
            if brows:
                print_stats["bom_print" if has_print_line else "bom_noprint"] += 1
            monthly[mo]["goods_with_bom"] += 1 if brows else 0
        multi_inst += sum(1 for c, n in seen_codes_this.items() if n > 1)

        # 키트 구조
        monthly[mo]["kits"] += len(asm)
        if asm:
            monthly[mo]["projects_with_kit"] += 1
        for a in asm:
            ags = a.get("assignedGoods") or []
            kit_lines_dist.append(len(ags))
            memo = str(a.get("kitMemo") or "").strip()
            if memo:
                kit_memos[memo[:40]] += 1
            for ag in ags:
                q = ag.get("quantityPerKit")
                if q is not None:
                    qpk_values.append(float(q))
            sig_codes = []
            for ag in ags:
                iid = str(ag.get("quoteGoodsInstanceId") or "")
                gm = next((str(g.get("goodsCode") or "").upper() for g in goods
                           if str(g.get("quoteGoodsInstanceId") or "") == iid), "")
                sig_codes.append(gm)
            sig = "|".join(sorted(sig_codes))
            if sig and sig not in first_seen_kitsig:
                first_seen_kitsig[sig] = mo
                monthly[mo]["new_kit_sigs"] += 1

        # 깊이: L0 + (L1 키트 or 단품포장) + L2 굿즈 + L3 BOM
        n_bom = sum(1 for g in phys
                    if bom_by_goods.get(goods_base(str(g.get("goodsName") or ""))))
        if asm and n_bom:
            depth = "L0-L1-L2-L3 (4계층)"
        elif asm:
            depth = "L0-L1-L2 (BOM 끊김)"
        elif n_bom:
            depth = "L0-L1'-L2-L3 (단품 4계층)"
        elif phys:
            depth = "L0-L1'-L2 (BOM 끊김)"
        else:
            depth = "물리 굿즈 없음"
        depth_dist[depth] += 1
        proj_rows.append({"pna": pna, "month": mo, "goods": len(phys),
                          "svc": svc_n, "kits": len(asm), "depth": depth,
                          "bom_hit": f"{n_bom}/{len(phys)}"})

    # CBM 도달 (월별 안정성)
    cbm_monthly = defaultdict(lambda: [0, 0])
    for pna in scope:
        if not statuses.get(pna, "").startswith("200"):
            continue
        mo = month_of[pna]
        for g in (snapshots[pna].get("productionSpecification") or {}).get("quoteGoods", []):
            name = str(g.get("goodsName") or "").strip()
            code = str(g.get("goodsCode") or "").strip().upper()
            if is_service(name):
                continue
            cbm_monthly[mo][1] += 1
            rc = resolve_registered_code(code, name, lookup)
            if code in registered or rc in registered:
                cbm_monthly[mo][0] += 1

    reuse = Counter(len(v) for v in code_projects.values())
    drift = {c: sorted(ns) for c, ns in code_names.items() if len(ns) > 1}
    summary = {
        "run_at": datetime.now(KST).isoformat(),
        "window": [args.d_from, args.d_to],
        "scope_pnas": len(scope),
        "statuses_count": dict(Counter(v.split(":")[0] for v in statuses.values())),
        "status_detail": dict(Counter(statuses.values())),
        "monthly": {m: dict(v) for m, v in sorted(monthly.items())},
        "cbm_reach_monthly": {m: {"reach": v[0], "total": v[1],
                                  "pct": round(v[0] / v[1] * 100, 1) if v[1] else None}
                              for m, v in sorted(cbm_monthly.items())},
        "depth_dist": dict(depth_dist),
        "kit_lines_dist": dict(Counter(kit_lines_dist)),
        "qpk": {"n": len(qpk_values),
                "eq1": sum(1 for q in qpk_values if q == 1),
                "gt1": sum(1 for q in qpk_values if q > 1),
                "frac": sum(1 for q in qpk_values if q != int(q)),
                "max": max(qpk_values) if qpk_values else None},
        "goods_reuse_dist": {str(k): v for k, v in sorted(reuse.items())},
        "distinct_codes": len(code_projects),
        "multi_instance_cases": multi_inst,
        "opt_categories_top": dict(opt_categories.most_common(20)),
        "print_stats": dict(print_stats),
        "box_crosstab": {f"in_kit={k[0]},box_bom={k[1]}": v
                         for k, v in sorted(box_crosstab.items())},
        "comp_types": dict(comp_types.most_common(15)),
        "kit_memos_top": dict(kit_memos.most_common(15)),
        "identity_drift": dict(list(drift.items())[:20]),
        "identity_drift_n": len(drift),
        "nest_not_in_sync_item": sorted(nest_not_in_sync),
        "kit_sig_total": len(first_seen_kitsig),
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "projects.json").write_text(
        json.dumps(proj_rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items()
                      if k not in ("status_detail", "identity_drift")},
                     ensure_ascii=False, indent=1))
    print(f"\nsummary → {out_dir / 'summary.json'}")


if __name__ == "__main__":
    main()
