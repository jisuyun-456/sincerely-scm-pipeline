"""NEST Production Specification API 읽기 전용 PoC 프로브 (2026-07-10).

NEST GET + Airtable GET만 수행 — 어떤 원격 시스템에도 쓰기 없음 (산출물은 로컬 파일만).
목적: "NEST 데이터만 읽어 BOM/CBM cascade 전개가 가능한가" V-게이트 실측.

측정: V2 PNA 커버리지(404율) · V1 키 연결(goodsCode↔sync_item↔TMS견적코드) ·
V1b 사이즈옵션→SKU · C-chk CBM 도달률 · B-chk 키트↔WMS_BOM 연계 ·
V3 수량 정합 · V4 명칭 일치 · V5 instanceId 안정성.

Usage:
  python scripts/backbone/nest_probe.py --out <dir>          # 실측 (~32 calls)
  python scripts/backbone/nest_probe.py --out <dir> --limit 5
"""
import argparse
import json
import os
import re
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.backbone.keys import (  # noqa: E402
    PNA_RE, goods_base, is_service, normalize_goods, parse_goods,
)
from harness.backbone.product_alias import (  # noqa: E402
    SIZE_FAMILY, inject_synthetic, resolve_registered_code,
)
from harness.settlement.cbm_calc import load_product_lookup  # noqa: E402

WMS = "appLui4ZR5HWcQRri"
ORDER = "tblJslWg8sYEdCkXw"
SYNC_ITEM = "tblwnNgHQxZ0WhDBh"
BOM_TBL = "tblopHqepkx6mNEHL"
PKG_SCHED = "tblae2NqJaexwjN9R"

NEST_BASE = "https://nest.sincerely.work/api/internal/v1"
PACE_SEC = 1.3          # ≤50콜/분 (한도 60/min 대비 여유)
KST = timezone(timedelta(hours=9))
_SIZE_CAT_RE = re.compile(r"사이즈|size", re.IGNORECASE)


# ── Airtable 읽기 (order_cascade.py _get_with_retry 패턴, GET only) ─────────
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
            print(f"[RETRY {attempt}/{retries}] {url.rsplit('/', 1)[-1]} "
                  f"{type(err).__name__} — {wait}s 후 재시도", flush=True)
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


# ── NEST 읽기 전용 클라이언트 ────────────────────────────────────────────────
class NestClient:
    def __init__(self, key: str):
        self._key = key
        self.calls = 0
        self.status_counts = defaultdict(int)

    def fetch(self, pna: str) -> tuple[int, dict | None, str]:
        """GET production-specification. Returns (status, payload|None, error_code)."""
        self.calls += 1
        headers = {"X-API-Key": self._key,
                   "X-Request-Id": f"scm-probe-{self.calls:04d}"}
        url = f"{NEST_BASE}/projects/{pna}/production-specification"
        for attempt in range(1, 4):
            try:
                r = requests.get(url, headers=headers,
                                 params={"view": "compact"}, timeout=30)
            except (requests.exceptions.Timeout,
                    requests.exceptions.ConnectionError) as err:
                if attempt == 3:
                    self.status_counts["transport_error"] += 1
                    return 0, None, type(err).__name__
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", "5") or 5)
                print(f"  [429] {pna} — {wait}s 대기", flush=True)
                time.sleep(wait)
                continue
            body = {}
            try:
                body = r.json()
            except ValueError:
                pass
            err_code = str((body.get("error") or {}).get("code") or "")
            if r.status_code == 500 and err_code != "DATA_INTEGRITY_ERROR" \
                    and attempt < 3:
                time.sleep(2 ** attempt)   # INTERNAL_SERVER_ERROR만 백오프 재시도
                continue
            self.status_counts[f"{r.status_code}:{err_code or 'OK'}"] += 1
            if r.status_code == 200:
                return 200, body, ""
            return r.status_code, None, err_code
        return 0, None, "retries_exhausted"


# ── 샘플 선정 ────────────────────────────────────────────────────────────────
def pick_sample(orders, pkg_rows, today, n_recent=20, n_edge=10):
    """order 미러 → PNA별 요약 → 최근 20 + 엣지 10 (재제작/multi-goods/단품/보령)."""
    by_pna = {}
    for rec in orders:
        f = rec["fields"]
        m = PNA_RE.search(str(f.get("project_code") or ""))
        if not m:
            continue
        pna = m.group(0)
        g = by_pna.setdefault(pna, {"created_max": "", "goods": set(),
                                    "repro": False})
        g["created_max"] = max(g["created_max"], rec.get("createdTime", ""))
        gname = parse_goods(str(f.get("굿즈 주문 수량 (자동)") or ""))[0]
        if gname and not is_service(gname):
            g["goods"].add(gname)
            if goods_base(gname) != re.sub(r"\[\d+\]", "", gname).strip():
                g["repro"] = True

    cutoff = (today - timedelta(days=60)).isoformat()
    recent = [p for p, g in sorted(by_pna.items(),
                                   key=lambda kv: kv[1]["created_max"],
                                   reverse=True)
              if g["created_max"][:10] >= cutoff][:n_recent]

    danpum = set()
    for rec in pkg_rows:
        f = rec["fields"]
        if str(f.get("단품 굿즈 품목 및 수량") or "").strip():
            m = PNA_RE.search(str(f.get("프로젝트 코드 (PK) (from project)") or ""))
            if m:
                danpum.add(m.group(0))

    edge, seen = [], set(recent)

    def _add(p):
        if p in by_pna and p not in seen and len(edge) < n_edge:
            edge.append(p)
            seen.add(p)

    _add("PNA51684")                                       # 보령 레퍼런스
    for p, g in by_pna.items():                            # 재제작 접미
        if g["repro"]:
            _add(p)
        if len(edge) >= 4:
            break
    for p, _g in sorted(by_pna.items(), key=lambda kv: -len(kv[1]["goods"]))[:8]:
        _add(p)                                            # multi-goods 상위
        if len(edge) >= 7:
            break
    for p in sorted(danpum & set(by_pna), reverse=True):   # 단품-heavy
        _add(p)
    for p, _g in sorted(by_pna.items(),
                        key=lambda kv: kv[1]["created_max"], reverse=True):
        _add(p)                                            # 부족분 최근순 충원
    return recent, edge, by_pna


# ── 분석 ────────────────────────────────────────────────────────────────────
def flatten_goods(payload):
    """quoteGoods[] → [{code,name,qty,unassigned,size_opts,instance_id}]."""
    out = []
    for g in (payload.get("productionSpecification") or {}).get("quoteGoods", []):
        size_opts = []
        for it in g.get("quoteItems") or []:
            cat = str(it.get("optionCategoryName") or "")
            if _SIZE_CAT_RE.search(cat):
                size_opts.append(str(it.get("optionName") or ""))
        out.append({
            "instance_id": str(g.get("quoteGoodsInstanceId") or ""),
            "code": str(g.get("goodsCode") or "").strip().upper(),
            "name": str(g.get("goodsName") or "").strip(),
            "qty": int(g.get("quoteGoodsQuantity") or 0),
            "unassigned": int(g.get("unassignedQuantity") or 0),
            "size_opts": size_opts,
        })
    return out


def analyze(snapshots, orders, name2code, lookup, bom_fields):
    """수집된 스냅샷 + Airtable 읽기 데이터 → V/B/C 체크 집계 dict."""
    code2name = {}
    for nm, cd in name2code.items():
        code2name.setdefault(cd, nm)
    registered = {k.upper() for k, e in lookup.items()
                  if e.get("code", "").lower() == k and e.get("cbm_per_box", 0) > 0}
    bom_parents = {goods_base(str(f.get("모품목_굿즈명") or "")).strip()
                   for f in bom_fields if f.get("모품목_굿즈명")}

    # order 측: (PNA → code→qty, name set)  — 서비스 라인 제외
    ord_qty, ord_names = defaultdict(dict), defaultdict(set)
    for rec in orders:
        f = rec["fields"]
        m = PNA_RE.search(str(f.get("project_code") or ""))
        if not m:
            continue
        pna = m.group(0)
        gname, gqty = parse_goods(str(f.get("굿즈 주문 수량 (자동)") or ""))
        if not gname or is_service(gname):
            continue
        ord_names[pna].add(gname)
        raw = f.get("굿즈코드 (from sync_itemdb)")
        if isinstance(raw, list):
            raw = raw[0] if raw else ""
        code = str(raw or "").strip().upper()
        if code and gqty:
            ord_qty[pna][code] = max(ord_qty[pna].get(code, 0), gqty)

    res = {"v1": defaultdict(int), "v1b": defaultdict(int),
           "cchk": defaultdict(int), "bchk": defaultdict(int),
           "v3_deltas": [], "v3_order_only": 0, "v3_nest_only": 0,
           "v3_pairs": 0, "v4": defaultdict(int),
           "kit_stats": defaultdict(int), "per_pna": {}}
    distinct = {}     # goodsCode → 대표 goods dict (V1 distinct 대조용)

    for pna, payload in snapshots.items():
        goods = flatten_goods(payload)
        asm = (payload.get("productionSpecification") or {}).get("assemblies", [])
        nest_qty = defaultdict(int)
        for g in goods:
            nest_qty[g["code"]] += g["qty"]
            distinct.setdefault(g["code"], g)

            # V4 명칭 — NEST goodsName vs 이 PNA의 order 굿즈명
            res["v4"]["total"] += 1
            onames = ord_names.get(pna, set())
            if g["name"] in onames:
                res["v4"]["exact"] += 1
            elif normalize_goods(g["name"]) in {normalize_goods(n) for n in onames}:
                res["v4"]["normalized"] += 1
            elif g["code"] and g["code"] in ord_qty.get(pna, {}):
                res["v4"]["code_mediated"] += 1
            else:
                res["v4"]["unmatched"] += 1

            # C-chk CBM 도달 경로 (결정론 경로만; jaccard 제외)
            res["cchk"]["total"] += 1
            rc = resolve_registered_code(g["code"], g["name"], lookup)
            nm_code = name2code.get(normalize_goods(g["name"]), "")
            if g["code"] in registered:
                res["cchk"]["direct"] += 1
            elif rc != g["code"] and rc in registered:
                res["cchk"]["alias_size"] += 1
            elif nm_code and resolve_registered_code(
                    nm_code, g["name"], lookup) in registered:
                res["cchk"]["via_name2code"] += 1
            else:
                res["cchk"]["unresolved"] += 1

            # B-chk goods→PT 연쇄 (WMS_BOM 모품목 존재율)
            res["bchk"]["goods_total"] += 1
            wms_name = g["name"] if g["name"] in bom_parents else (
                code2name.get(g["code"], ""))
            if goods_base(wms_name) in bom_parents or g["name"] in bom_parents:
                res["bchk"]["bom_parent_hit"] += 1

            # V1b 사이즈 옵션
            if g["size_opts"]:
                res["v1b"]["with_size_opt"] += 1
                fam = SIZE_FAMILY.get(g["code"], {})
                sku = fam.get((g["size_opts"][0] or "").upper())
                if g["code"] in registered or (sku and sku in registered):
                    res["v1b"]["resolvable"] += 1

        # V3 수량 대사 (code 기준 페어)
        for code, oq in ord_qty.get(pna, {}).items():
            if code in nest_qty:
                nq = nest_qty[code]
                res["v3_pairs"] += 1
                res["v3_deltas"].append(abs(oq - nq) / max(nq, 1) * 100)
            else:
                res["v3_order_only"] += 1
        res["v3_nest_only"] += sum(1 for c in nest_qty
                                   if c not in ord_qty.get(pna, {}))

        # 키트 구조 통계
        res["kit_stats"]["projects_with_kit"] += 1 if asm else 0
        res["kit_stats"]["kits"] += len(asm)
        for a in asm:
            res["kit_stats"]["kit_goods_lines"] += len(a.get("assignedGoods") or [])
        res["per_pna"][pna] = {
            "goods": len(goods), "kits": len(asm),
            "order_codes": len(ord_qty.get(pna, {})),
            "nest_codes": len(nest_qty),
            "code_overlap": len(set(ord_qty.get(pna, {})) & set(nest_qty)),
        }

    # V1 distinct 코드 대조
    sync_codes = set(name2code.values())
    for code, _g in distinct.items():
        res["v1"]["distinct_total"] += 1
        if code in sync_codes:
            res["v1"]["in_sync_item"] += 1
        if code in registered:
            res["v1"]["in_tms_registered"] += 1
        rc = resolve_registered_code(code, _g["name"], lookup)
        if rc in registered:
            res["v1"]["tms_reachable_with_alias"] += 1
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="raw 응답·요약 저장 디렉토리 (repo 밖)")
    ap.add_argument("--limit", type=int, default=0, help="샘플 수 제한 (시운전)")
    args = ap.parse_args()
    out_dir = Path(args.out)
    (out_dir / "raw").mkdir(parents=True, exist_ok=True)

    load_dotenv()
    nest_key = os.environ["NEST_PRODUCTION_SPECIFICATION_API_KEY"]
    tp = os.environ["AIRTABLE_PAT"]
    wp = os.environ["AIRTABLE_WMS_PAT"]
    today = datetime.now(KST).date()

    print("로딩: TMS Product 룩업...", flush=True)
    lookup = load_product_lookup({"Authorization": f"Bearer {tp}"})
    inject_synthetic(lookup)
    print("로딩: sync_item / WMS_BOM / pkg_schedule / order 미러...", flush=True)
    name2code = {}
    for r in at_fetch(WMS, SYNC_ITEM, wp, ["굿즈명", "굿즈코드"]):
        f = r["fields"]
        nm = normalize_goods(str(f.get("굿즈명") or ""))
        cd = str(f.get("굿즈코드") or "").strip().upper()
        if nm and cd:
            name2code[nm] = cd
    bom_fields = [r["fields"] for r in at_fetch(
        WMS, BOM_TBL, wp, ["프로젝트코드", "모품목_굿즈명", "소품목_PT", "소요량_개당"])]
    pkg_rows = at_fetch(WMS, PKG_SCHED, wp, [
        "프로젝트 코드 (PK) (from project)", "단품 굿즈 품목 및 수량"])
    orders = at_fetch(WMS, ORDER, wp, ["project_code", "굿즈 주문 수량 (자동)",
                                       "주문수량", "굿즈코드 (from sync_itemdb)"])

    recent, edge, _ = pick_sample(orders, pkg_rows, today)
    sample = (recent + edge)[:args.limit] if args.limit else recent + edge
    print(f"샘플: 최근 {len(recent)} + 엣지 {len(edge)} → 호출 대상 {len(sample)}",
          flush=True)

    client = NestClient(nest_key)
    snapshots, statuses = {}, {}
    for pna in sample:
        st, payload, err = client.fetch(pna)
        statuses[pna] = f"{st}:{err or 'OK'}"
        print(f"  {pna} → {statuses[pna]}", flush=True)
        if payload:
            snapshots[pna] = payload
            (out_dir / "raw" / f"{pna}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=1),
                encoding="utf-8")
        time.sleep(PACE_SEC)

    # V5 안정성 — 성공 상위 2건 재호출
    v5 = []
    for pna in list(snapshots)[:2]:
        st, payload, _ = client.fetch(pna)
        if st == 200 and payload:
            a = {g["instance_id"] for g in flatten_goods(snapshots[pna])}
            b = {g["instance_id"] for g in flatten_goods(payload)}
            v5.append({"pna": pna, "stable": a == b,
                       "only_first": len(a - b), "only_second": len(b - a)})
        time.sleep(PACE_SEC)

    res = analyze(snapshots, orders, name2code, lookup, bom_fields)
    ok = sum(1 for s in statuses.values() if s.startswith("200"))
    attempted = len(statuses)
    summary = {
        "run_at": datetime.now(KST).isoformat(),
        "calls_total": client.calls,
        "status_counts": dict(client.status_counts),
        "statuses": statuses,
        "v2_coverage_pct": round(ok / attempted * 100, 1) if attempted else 0,
        "v1": dict(res["v1"]), "v1b": dict(res["v1b"]),
        "cchk": dict(res["cchk"]), "bchk": dict(res["bchk"]),
        "v3": {"pairs": res["v3_pairs"],
               "median_delta_pct": round(statistics.median(res["v3_deltas"]), 1)
               if res["v3_deltas"] else None,
               "order_only_codes": res["v3_order_only"],
               "nest_only_codes": res["v3_nest_only"]},
        "v4": dict(res["v4"]), "v5": v5,
        "kit_stats": dict(res["kit_stats"]),
        "per_pna": res["per_pna"],
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n===== NEST PoC 요약 =====")
    print(json.dumps({k: v for k, v in summary.items()
                      if k not in ("statuses", "per_pna")},
                     ensure_ascii=False, indent=1))
    print(f"\nsummary → {out_dir / 'summary.json'}")


if __name__ == "__main__":
    main()
