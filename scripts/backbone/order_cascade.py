"""P6a — order-trigger 캐스케이드 orchestrator (S0~S7, dry-run 기본).

주문(PNA,굿즈) 1단위 → S1 키해소 → S2 MRP → S3 입하CBM·M/H·MES → S4 창고 →
S5 배차 프리뷰 → S6 운임 프리뷰 → S7 PropagationLedger 행 (spec §1).
코어 로직은 harness/backbone/cascade.py (순수) — 본 스크립트는 IO 조립만.

dry-run(기본): Airtable write 0. 리포트 json+md + audit jsonl만 산출 (VC-4·5).
--write: action in {new, changed} 행을 PropagationLedger에 batch INSERT
  (P6b에서 필드 7개 신설 후 첫 실행 — P6a에서는 실행 금지).

Usage:
  python scripts/backbone/order_cascade.py                 # dry-run
  python scripts/backbone/order_cascade.py --window 14
  python scripts/backbone/order_cascade.py --write         # P6b 이후에만
"""
import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.backbone.cascade import (  # noqa: E402
    REPROCESS_WINDOW_DAYS,
    CascadeContext,
    collect_units,
    latest_ledger_by_pid,
    run_unit,
)
from harness.backbone.digest import build_digest  # noqa: E402
from harness.backbone.keys import normalize_goods  # noqa: E402
from harness.backbone.part_cbm import part_cbm_for_pt  # noqa: E402
from harness.backbone.storage import parse_pt_from_ledger_key  # noqa: E402
from harness.dispatch.cbm_estimator import build_kit_cbm_lookup  # noqa: E402
from harness.backbone.keys import PNA_RE, build_pkg_goods_map  # noqa: E402
from harness.backbone.product_alias import inject_synthetic  # noqa: E402
from harness.settlement.cbm_calc import load_product_lookup  # noqa: E402
from harness.tms_settlement.config import rates_for  # noqa: E402
from utils.cbm_utils import load_sync_parts_lookup  # noqa: E402

WMS = "appLui4ZR5HWcQRri"
TMS = "app4x70a8mOrIKsMf"
MES = "appNSAPadsHbfaSHv"
ORDER = "tblJslWg8sYEdCkXw"
LEDGER_TBL = "tblkQmontWGSjo8c5"   # WMS_PropagationLedger (allowlist 내)
BOM_TBL = "tblopHqepkx6mNEHL"
ITEM_TBL = "tbl5ZGY373D5SCONV"
INV_LEDGER = "tbl4DcXQRHJj921MN"
LOC_TBL = "tblRwUTP5kWnHFt5P"
PKG_SCHED = "tblae2NqJaexwjN9R"
SYNC_ITEM = "tblwnNgHQxZ0WhDBh"
SHIP = "tbllg1JoHclGYer7m"
MES_V2 = "tblg96ys2vfPdyxHq"
KST = timezone(timedelta(hours=9))


_FETCH_RETRIES = 4          # P6a validator WARN — cron 무인 실행 전 transient 보강
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


def build_context(tp, wp, mp, today):
    """전 스테이지 입력 사전적재 → CascadeContext (cascade.py 순수 코어 소비)."""
    print("로딩: Product 룩업...", flush=True)
    lk = load_product_lookup({"Authorization": f"Bearer {tp}"})
    inject_synthetic(lk)   # Product 미등록 신규 SKU(TWKF 등) 권위 스펙 런타임 주입 (쓰기 0)
    product_by_code = {}
    for e in lk.values():
        code = str(e.get("code") or "").strip().upper()
        if code and e.get("cbm_per_box", 0) > 0:
            product_by_code[code] = (e.get("qty_per_box") or 1, e["cbm_per_box"])

    print("로딩: sync_item 브릿지 + pkg_schedule 폴백...", flush=True)
    items = fetch(WMS, SYNC_ITEM, wp, ["굿즈명", "굿즈코드"])
    name2code = {}
    for r in items:
        f = r["fields"]
        nm = normalize_goods(str(f.get("굿즈명") or ""))
        cd = str(f.get("굿즈코드") or "").strip().upper()
        if nm and cd:
            name2code[nm] = cd
    pkgs = fetch(WMS, PKG_SCHED, wp, [
        "프로젝트 코드 (PK) (from project)",
        "주문 굿즈 리스트 (자동) (from project)",
        "단품 굿즈 품목 및 수량",
    ])
    pkg_map = build_pkg_goods_map((r["fields"] for r in pkgs), name2code)

    print("로딩: WMS_BOM + ItemMaster (MRP·kit·part CBM)...", flush=True)
    bom = fetch(WMS, BOM_TBL, wp, ["프로젝트코드", "모품목_굿즈명", "소품목_PT",
                                   "소요량_개당", "검증상태"])
    bom_fields = [r["fields"] for r in bom]
    im_recs = fetch(WMS, ITEM_TBL, wp, ["품목키", "CBM_개당_m3", "출처"])
    item_master = {}
    for r in im_recs:
        f = r["fields"]
        k = str(f.get("품목키") or "").strip()
        if k:
            item_master[k] = (float(f.get("CBM_개당_m3") or 0),
                              str(f.get("출처") or ""))
    kit = build_kit_cbm_lookup(bom_fields, item_master, name2code)

    print("로딩: InventoryLedger + Location (재고·staging·Max_CBM)...", flush=True)
    locs = {r["id"]: r["fields"]
            for r in fetch(WMS, LOC_TBL, wp, ["Warehouse", "Zone_Type", "Max_CBM"])}
    max_staging = sum(float(f.get("Max_CBM") or 0) for f in locs.values()
                      if f.get("Zone_Type") == "INBOUND_STAGING") or None
    inv = fetch(WMS, INV_LEDGER, wp, ["Ledger_Key", "Current_Stock", "Location",
                                      "Stock_Type"])
    stock_rows = []
    for rec in inv:
        f = rec.get("fields", {})
        pt = parse_pt_from_ledger_key(str(f.get("Ledger_Key", "")))
        if not pt:
            continue
        loc_ids = f.get("Location") or []
        loc = locs.get(loc_ids[0], {}) if loc_ids else {}
        stock_rows.append({
            "pt": pt,
            "stock": f.get("Current_Stock") or 0,
            "warehouse": loc.get("Warehouse") or "미지정",
            "zone_type": loc.get("Zone_Type") or "",
            "stock_type": f.get("Stock_Type") or "",
        })

    # part CBM 4-tier — tier0 ItemMaster(P3' 백필 포함) + tier1 sync_parts 치수
    # (tier2 movement 규격·tier3 QC버킷은 P3' 백필이 ItemMaster에 이미 반영 — 미적재)
    sp_lookup = load_sync_parts_lookup()
    pts = set(item_master) | set(sp_lookup)
    part_cbm_by_pt = {}
    for pt in pts:
        cbm, _conf, tier = part_cbm_for_pt(pt, item_master, sp_lookup)
        if cbm > 0:
            part_cbm_by_pt[pt] = cbm

    print("로딩: TMS Shipment count...", flush=True)
    ships = fetch(TMS, SHIP, tp, ["project code"])
    shipment_count = {}
    for r in ships:
        m = PNA_RE.search(str(r["fields"].get("project code") or ""))
        if m:
            shipment_count[m.group(0)] = shipment_count.get(m.group(0), 0) + 1

    mes_rows = []
    if mp:
        print("로딩: MES ver2.0 (납기 forecast)...", flush=True)
        mes_rows = [r["fields"] for r in
                    fetch(MES, MES_V2, mp, ["굿즈", "계획수량", "납기일", "작업 상태"])]
    else:
        print("[WARN] AIRTABLE_MES_PAT 미설정 — S3 MES 타임라인 생략 (degrade)",
              flush=True)

    return CascadeContext(
        pkg_map=pkg_map, product_lookup=lk, kit_lookup=kit,
        shipment_count=shipment_count, bom_fields=bom_fields,
        stock_rows=stock_rows, part_cbm_by_pt=part_cbm_by_pt,
        mes_rows=mes_rows, name_to_code=name2code,
        product_by_code=product_by_code, max_staging_cbm=max_staging,
        rates=rates_for(today.isoformat()), today=today)


def build_project_board(results: list[dict]) -> list[str]:
    """프로젝트(PNA)별 진행 롤업 보드 — BOM·CBM 트레이스 한눈에 (P1).

    ledger row를 프로젝트코드로 묶어 자재 입하CBM ↔ 완제품 출하CBM,
    WMS M/H, 상태 분포를 1행으로 요약. 굿즈 단위 상세는 아래 단위별 테이블 참조.
    신규 연산 없음 — 기존 ledger row 필드만 집계.
    """
    by_pna: dict[str, list[dict]] = {}
    for r in results:
        pna = r["row"].get("프로젝트코드") or "—"
        by_pna.setdefault(pna, []).append(r)

    def _min_date(rs, field):
        ds = [r["row"].get(field) for r in rs if r["row"].get(field)]
        return min(ds) if ds else "—"

    lines = ["", "## 프로젝트별 진행 보드 (P1·P3)", "",
             f"- 프로젝트 {len(by_pna)}개 / 단위 {len(results)}개", "",
             "| 프로젝트 | 굿즈 | 완결 | 부분 | 끊김 | 입하CBM | 출하CBM "
             "| WMS M/H(h) | 출고요청일 | 생산납기 | 미산출 |",
             "|---|--:|--:|--:|--:|--:|--:|--:|---|---|--:|"]
    for pna in sorted(by_pna):
        rs = by_pna[pna]
        done = sum(1 for r in rs if r["row"]["전파상태"] == "완결")
        part = sum(1 for r in rs if r["row"]["전파상태"] == "부분")
        broke = sum(1 for r in rs if r["row"]["전파상태"] == "끊김")
        in_cbm = round(sum(float(r["row"].get("입하CBM_예상_m3") or 0) for r in rs), 4)
        out_cbm = round(sum(float(r["row"].get("추정_CBM_m3") or 0) for r in rs), 4)
        mh = round(sum(float(r["row"].get("MH_예상_h") or 0) for r in rs), 2)
        uncovered = sum(1 for r in rs if r["reasons"])
        lines.append(
            f"| {pna} | {len(rs)} | {done} | {part} | {broke} "
            f"| {in_cbm} | {out_cbm} | {mh} "
            f"| {_min_date(rs, '출고요청일')} | {_min_date(rs, '생산_납기일')} "
            f"| {uncovered} |")
    return lines


def _iso_date(raw):
    try:
        return date.fromisoformat(str(raw or "")[:10])
    except ValueError:
        return None


def weekly_outbound_forecast(results: list[dict]) -> dict:
    """D1 — ship_req(출고요청일) ISO주차별 추정_CBM_m3 집계 (출하CBM 사전계획).

    PropLedger 추정_CBM_m3는 날짜 미저장(cdb8d29) → cascade 결과 in-memory ship_req로
    버킷. CBM 0(끊김·미산출)·날짜 없는 단위는 미산입 — coverage_pct로 투명화.
    """
    buckets: dict[str, dict] = {}
    cbm_total = cbm_dated = 0.0
    n_total = n_dated = 0
    for r in results:
        cbm = float(r["row"].get("추정_CBM_m3") or 0)
        if cbm <= 0:
            continue
        n_total += 1
        cbm_total += cbm
        d = _iso_date(r.get("ship_req"))
        if d is None:
            continue
        n_dated += 1
        cbm_dated += cbm
        y, w, _ = d.isocalendar()
        label = f"{y}-W{w:02d}"
        # week_start = 해당 주 월요일 (date.fromisocalendar W53/short-year ValueError 회피)
        b = buckets.setdefault(label, {
            "cbm": 0.0, "n": 0,
            "week_start": (d - timedelta(days=d.weekday())).isoformat()})
        b["cbm"] = round(b["cbm"] + cbm, 4)
        b["n"] += 1
    return {
        "by_week": dict(sorted(buckets.items())),
        "total_cbm": round(cbm_total, 4),
        "dated_cbm": round(cbm_dated, 4),
        "n_units": n_total,
        "n_dated": n_dated,
        "coverage_pct": round(cbm_dated / cbm_total * 100, 1) if cbm_total else 0.0,
    }


def build_d1_outbound_section(results: list[dict]) -> list[str]:
    """D1 출하CBM 주별 사전계획 마크다운 섹션 (출하확정 14d보다 먼 사전수요)."""
    f = weekly_outbound_forecast(results)
    lines = ["", "## D1 출하CBM 주별 사전계획 (ship_req 출고요청일 기준)", "",
             f"- 출하CBM 단위 {f['n_units']}개 / 날짜 확보 {f['n_dated']}개 "
             f"(CBM 커버 {f['coverage_pct']}%) | 합계 {f['total_cbm']}m³ "
             f"(날짜확보 {f['dated_cbm']}m³)", "",
             "| ISO주차 | 주 시작 | 출하CBM(m³) | 단위 |",
             "|---|---|--:|--:|"]
    for label, b in f["by_week"].items():
        lines.append(f"| {label} | {b['week_start']} | {b['cbm']} | {b['n']} |")
    if not f["by_week"]:
        lines.append("| (날짜 확보 단위 없음) | — | — | — |")
    lines += ["", "> PropLedger 추정_CBM 기반 사전수요 — capacity_series outbound(출하확정 "
              "14d)보다 먼 윈도우. D2 완전주문(OTIF×BOM)은 P5에서 결합."]
    return lines


def write_report(out_dir: Path, run_id: str, results: list[dict], totals: dict,
                 window_days: int):
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {"run_id": run_id, "window_days": window_days, "totals": totals,
               "units": [{k: v for k, v in r.items()} for r in results]}
    (out_dir / f"report_{run_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    lines = [f"# Order Cascade Report — {run_id}", "",
             f"- 감지 윈도우: {window_days}d (forward-only)",
             f"- 단위: {totals['units']} (PNA,굿즈) | INSERT 대상 "
             f"{totals['new'] + totals['changed']} "
             f"(new {totals['new']} / changed {totals['changed']} / "
             f"unchanged {totals['unchanged']})",
             f"- 상태: 완결 {totals['완결']} / 부분 {totals['부분']} / "
             f"끊김 {totals['끊김']}"]
    lines += build_project_board(results)
    lines += build_d1_outbound_section(results)
    lines += ["", "## 단위별 상세 (전파ID)", "",
              "| 전파ID | 상태 | action | 부족자재 | 입하CBM | 출하CBM | M/H "
              "| wave | 운임범위 | 사유 |",
              "|---|---|---|---|--:|--:|--:|---|---|---|"]
    for r in results:
        row = r["row"]
        shortage = str(row.get("부족자재_요약") or "").replace("\n", "<br>")
        lines.append(
            f"| {row['전파ID']} | {row['전파상태']} | {r['action']} "
            f"| {shortage or '—'} | {row.get('입하CBM_예상_m3', '—')} "
            f"| {row.get('추정_CBM_m3', '—')} "
            f"| {row.get('MH_예상_h', '—')} | {row.get('wave_프리뷰', '—')} "
            f"| {row.get('운임_예상범위', '—')} "
            f"| {'; '.join(r['reasons']) or '—'} |")
    lines += ["", "> MRP 협력사별 부족분 묶음·Slack digest는 P6b.",
              "> 리포트는 영속 아님 — 영속 기록은 PropagationLedger (spec §3.2)."]
    (out_dir / f"report_{run_id}.md").write_text("\n".join(lines),
                                                 encoding="utf-8")


def send_slack(text: str) -> None:
    """digest DM 발송 — 미설정/실패는 WARN만 (발송이 run 성패를 좌우하지 않음)."""
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    user = os.environ.get("SLACK_DM_USER_ID", "")
    if not token or not user:
        print("[WARN] SLACK_BOT_TOKEN/SLACK_DM_USER_ID 미설정 — digest 발송 생략",
              flush=True)
        return
    try:
        r = requests.post("https://slack.com/api/chat.postMessage",
                          headers={"Authorization": f"Bearer {token}"},
                          json={"channel": user, "text": text}, timeout=30)
        data = r.json()
        if data.get("ok"):
            print("[SLACK] digest 발송 완료", flush=True)
        else:
            print(f"[WARN] Slack 발송 실패: {data.get('error')}", flush=True)
    except requests.exceptions.RequestException as err:
        print(f"[WARN] Slack 발송 예외: {err}", flush=True)


def main():
    ap = argparse.ArgumentParser(description="order-trigger 캐스케이드 (dry-run 기본)")
    ap.add_argument("--write", action="store_true",
                    help="PropagationLedger INSERT (P6b 필드 신설 후에만)")
    ap.add_argument("--window", type=int, default=REPROCESS_WINDOW_DAYS,
                    help="감지·재처리 윈도우 일수 (기본 14)")
    ap.add_argument("--out", default="data/order_cascade",
                    help="리포트·audit 출력 디렉터리 (gitignored)")
    args = ap.parse_args()

    load_dotenv()
    tp = os.environ["AIRTABLE_PAT"]
    wp = os.environ["AIRTABLE_WMS_PAT"]
    mp = os.environ.get("AIRTABLE_MES_PAT", "")

    now = datetime.now(timezone.utc)
    run_id = now.astimezone(KST).strftime("%Y%m%d-%H%M")
    today = date.today()
    out_dir = Path(args.out)
    audit_path = out_dir / f"audit_{run_id}.jsonl"
    out_dir.mkdir(parents=True, exist_ok=True)

    ctx = build_context(tp, wp, mp, today)

    print("로딩: order 미러 + PropagationLedger 최신행...", flush=True)
    orders = fetch(WMS, ORDER, wp, ["project_code", "굿즈 주문 수량 (자동)",
                                    "주문수량", "파츠명",
                                    "굿즈코드 (from sync_itemdb)",
                                    "출고 요청일"])
    ledger_recs = fetch(WMS, LEDGER_TBL, wp)   # 신설 전 필드 미지정 (전 필드)
    latest = latest_ledger_by_pid(ledger_recs)

    units = collect_units(orders, now, window_days=args.window)
    print(f"\n=== 캐스케이드 {len(units)}단위 (order {len(orders)}행, "
          f"윈도우 {args.window}d, ledger 기존 {len(latest)} 전파ID) ===", flush=True)

    results, totals = [], {"units": len(units), "new": 0, "changed": 0,
                           "unchanged": 0, "완결": 0, "부분": 0, "끊김": 0}
    with audit_path.open("a", encoding="utf-8") as audit:
        for u in units:
            pid = f"{u.pna}_{u.goods_name}"
            prior = (latest.get(pid) or {}).get("fields")
            r = run_unit(u, prior, ctx, run_id)
            results.append(r)
            totals[r["action"]] += 1
            totals[r["status"]] += 1
            audit.write(json.dumps({
                "ts": now.isoformat(), "run_id": run_id, "전파ID": pid,
                "action": r["action"], "status": r["status"],
                "reasons": r["reasons"], "write": False,
            }, ensure_ascii=False) + "\n")

        to_insert = [r["row"] for r in results if r["action"] in ("new", "changed")]
        print(f"\n  완결 {totals['완결']} / 부분 {totals['부분']} / "
              f"끊김 {totals['끊김']} | INSERT 대상 {len(to_insert)} "
              f"(unchanged skip {totals['unchanged']})", flush=True)

        d1 = weekly_outbound_forecast(results)
        print(f"  D1 출하CBM 사전계획: {d1['total_cbm']}m³ / 주차 {len(d1['by_week'])}개 "
              f"(날짜커버 {d1['coverage_pct']}%)", flush=True)

        digest = build_digest(results, totals, run_id, args.window, d1=d1)

        if not args.write:
            write_report(out_dir, run_id, results, totals, args.window)
            if digest:
                print(f"\n[DRY-RUN] Slack digest (미발송):\n{digest}", flush=True)
            print(f"\n[DRY-RUN] Airtable write 0 (VC-5). 리포트: "
                  f"{out_dir}/report_{run_id}.md", flush=True)
            return

        # --write: PropagationLedger INSERT-only (P6b 필드 7개 신설 후 첫 실행)
        from harness._core.airtable import AirtableClient
        client = AirtableClient.get_or_create(WMS, LEDGER_TBL, wp)
        created = 0
        for i in range(0, len(to_insert), 10):
            chunk = [{"fields": row} for row in to_insert[i:i + 10]]
            client.create_records(chunk)
            created += len(chunk)
            audit.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(), "run_id": run_id,
                "action": "insert", "count": len(chunk), "write": True,
            }, ensure_ascii=False) + "\n")
        write_report(out_dir, run_id, results, totals, args.window)
        print(f"\n[WRITE] PropagationLedger INSERT {created}행 "
              f"(UPDATE/DELETE 0 — INSERT-only).", flush=True)
        if digest:
            send_slack(digest)
        else:
            print("[SLACK] 신규 주문 0 — digest 미발송 (spec §3.2)", flush=True)


if __name__ == "__main__":
    main()
