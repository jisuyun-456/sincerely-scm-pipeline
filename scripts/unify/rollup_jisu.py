"""rollup_jisu.py — weekly/monthly logistics forecast from the jisu PropagationLedger.

Reads the PropagationLedger rows that simulate_jisu.py persisted and buckets the
cascade forecast by 출고요청일 (ship_req) into ISO-week and calendar-month views, so
the floor can pre-plan: inbound CBM load, labor M/H, inbound-staging occupancy %,
and outbound CBM (wave/freight driver).

staging 적재% = Σ입하CBM(bucket) / Σ Max_CBM(INBOUND_STAGING) — that week's inbound
load against dock capacity (additive; the per-row 창고적재_예상 text is a cumulative
projection from one baseline and is NOT summable, so we recompute from 입하CBM).

Run:
  AIRTABLE_JISU_PAT=... python scripts/unify/rollup_jisu.py [--md OUT.md]

Read-only on the jisu sandbox base.
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
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

BASE = "apptJBFsVRGaeUvLW"
IDS = json.load(open(Path(__file__).with_name("jisu_tableids.json"), encoding="utf-8"))


def _pat():
    p = os.environ.get("AIRTABLE_JISU_PAT") or os.environ.get("AIRTABLE_ZISU_PAT")
    if not p:
        raise SystemExit("set AIRTABLE_JISU_PAT (legacy AIRTABLE_ZISU_PAT also accepted)")
    return p


def fetch(table_name):
    tid = IDS[table_name]
    out, offset = [], None
    while True:
        url = f"https://api.airtable.com/v0/{BASE}/{tid}"
        if offset:
            url += "?" + urllib.parse.urlencode({"offset": offset})
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {_pat()}"})
        for attempt in range(5):
            try:
                data = json.load(urllib.request.urlopen(req))
                break
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503) and attempt < 4:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise SystemExit(f"[HTTP {e.code}] {url}\n{e.read().decode()}")
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


def _iso(v):
    try:
        return date.fromisoformat(str(v or "")[:10])
    except ValueError:
        return None


def _agg(rows, keyfn):
    """Bucket ledger rows by keyfn(date) → metric sums."""
    buckets: dict[str, dict] = defaultdict(
        lambda: {"in_cbm": 0.0, "mh": 0.0, "out_cbm": 0.0, "n": 0,
                 "완결": 0, "부분": 0, "끊김": 0, "d": None})
    for r in rows:
        f = r["fields"]
        d = _iso(f.get("출고요청일"))
        if d is None:
            continue
        b = buckets[keyfn(d)]
        b["in_cbm"] += _f(f.get("입하CBM_예상_m3"))
        b["mh"] += _f(f.get("MH_예상_h"))
        b["out_cbm"] += _f(f.get("추정_CBM_m3"))
        b["n"] += 1
        st = f.get("전파상태") or "부분"
        if st in ("완결", "부분", "끊김"):
            b[st] += 1
        if b["d"] is None or d < b["d"]:
            b["d"] = d
    return buckets


def main():
    ap = argparse.ArgumentParser(description="jisu weekly/monthly logistics forecast")
    ap.add_argument("--md", help="also write the markdown report to this path")
    args = ap.parse_args()

    rows = fetch("PropagationLedger")
    staging_max = sum(
        _f(r["fields"].get("Max_CBM")) for r in fetch("Location")
        if r["fields"].get("Zone_Type") == "INBOUND_STAGING") or None

    dated = sum(1 for r in rows if _iso(r["fields"].get("출고요청일")))
    cap = f"{staging_max:g}m³" if staging_max else "미실측"

    def pct(in_cbm):
        return f"{in_cbm / staging_max * 100:.1f}%" if staging_max else "—"

    weekly = _agg(rows, lambda d: f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}")
    monthly = _agg(rows, lambda d: d.strftime("%Y-%m"))

    L = [f"# 지수_테스트 주간/월간 물류 forecast (PropagationLedger {len(rows)}행)", "",
         f"- 집계 기준: 출고요청일(ship_req) · INBOUND_STAGING Max {cap} · "
         f"날짜 확보 {dated}/{len(rows)}행", "",
         "## 주간 forecast (ISO주차)", "",
         "| ISO주차 | 주 시작 | 입하CBM(m³) | M/H(h) | 입하적재% | 출하CBM(m³) | 단위 | 완/부/끊 |",
         "|---|---|--:|--:|--:|--:|--:|---|"]
    for k in sorted(weekly):
        b = weekly[k]
        ws = (b["d"] - timedelta(days=b["d"].weekday())).isoformat()
        L.append(f"| {k} | {ws} | {b['in_cbm']:.3f} | {b['mh']:.2f} | {pct(b['in_cbm'])} "
                 f"| {b['out_cbm']:.3f} | {b['n']} | "
                 f"{b['완결']}/{b['부분']}/{b['끊김']} |")
    L += ["", "## 월간 forecast", "",
          "| 월 | 입하CBM(m³) | M/H(h) | 입하적재% | 출하CBM(m³) | 단위 | 완/부/끊 |",
          "|---|--:|--:|--:|--:|--:|---|"]
    for k in sorted(monthly):
        b = monthly[k]
        L.append(f"| {k} | {b['in_cbm']:.3f} | {b['mh']:.2f} | {pct(b['in_cbm'])} "
                 f"| {b['out_cbm']:.3f} | {b['n']} | {b['완결']}/{b['부분']}/{b['끊김']} |")
    tot_in = sum(b["in_cbm"] for b in monthly.values())
    tot_mh = sum(b["mh"] for b in monthly.values())
    L += ["", f"> 합계: 입하CBM {tot_in:.2f}m³ · M/H {tot_mh:.1f}h · "
          f"주차 {len(weekly)}개 / 월 {len(monthly)}개. "
          f"입하적재%는 주간 입하CBM ÷ staging Max — 누적 아님."]

    report = "\n".join(L)
    print(report)
    if args.md:
        Path(args.md).write_text(report, encoding="utf-8")
        print(f"\n[md] {args.md}", file=sys.stderr)


if __name__ == "__main__":
    main()
