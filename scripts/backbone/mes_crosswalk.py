"""P2b Task 2b.1 — MES↔PT/굿즈코드 크로스워크.

MES read-only: [sync]파츠별_자재이동.파츠코드(PT hop) + 내부인쇄_제품 DB.Name/굿즈코드(by DB)(굿즈 hop)
→ WMS_KeyCrosswalk 신규 키 INSERT(출처='mes_crosswalk') + 매칭률 stdout 리포트.
dry-run 기본, --write 게이트. YAGNI 가드(spec §6-3): 키 해소만 — 집계·예측·MES 복제 금지. MES write 0.

Usage:
  python scripts/backbone/mes_crosswalk.py            # dry-run 매칭률 측정
  python scripts/backbone/mes_crosswalk.py --write    # 신규 키 INSERT
"""
import argparse
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.backbone.keys import extract_pts, build_mes_crosswalk_rows  # noqa: E402
from harness.settlement.cbm_calc import load_product_lookup  # noqa: E402

load_dotenv()
# MES read-only. cron 편입 시 GH secret AIRTABLE_MES_PAT 추가 필요 (현재 .env 전용)
MP = os.environ.get("AIRTABLE_MES_PAT") or sys.exit(
    "ERROR: AIRTABLE_MES_PAT 미설정 — .env 추가 필요 (memory reference_airtable_mes_pat)")
WP = os.environ["AIRTABLE_WMS_PAT"]
TP = os.environ["AIRTABLE_PAT"]
MES = "appNSAPadsHbfaSHv"
WMS = "appLui4ZR5HWcQRri"
MES_SYNC_PARTS = "tbliMelPWs1epoMkK"  # [sync]파츠별_자재이동 (read-only)
MES_PRINT_DB = "tblvaQeb5NTP0iFng"    # 내부인쇄_제품 DB (read-only)
XWALK = "tblJK5eyQGGx5X1oH"           # WMS_KeyCrosswalk (allowlist INSERT 대상)
ITEM = "tbl5ZGY373D5SCONV"            # WMS_ItemMaster


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


def post_batch(url, headers, batch):
    """10건 이하 batch INSERT. Returns (ok, err)."""
    for attempt in range(3):
        try:
            r = requests.post(url, headers=headers,
                              json={"records": batch, "typecast": True}, timeout=30)
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="신규 키 INSERT (기본 dry-run)")
    args = ap.parse_args()

    print("MES [sync]파츠별_자재이동 로딩...", flush=True)
    mes_parts: set = set()
    for r in fetch(MES, MES_SYNC_PARTS, MP, ["파츠코드"]):
        mes_parts.update(extract_pts(r["fields"].get("파츠코드")))
    print(f"  MES 파츠(PT) {len(mes_parts)}종", flush=True)

    print("MES 내부인쇄_제품 DB 로딩...", flush=True)
    mes_goods = {}
    for r in fetch(MES, MES_PRINT_DB, MP, ["Name", "굿즈코드(by DB)"]):
        f = r["fields"]
        nm = str(f.get("Name") or "").strip()
        if nm:
            mes_goods[nm] = str(f.get("굿즈코드(by DB)") or "")
    print(f"  MES 굿즈 {len(mes_goods)}종", flush=True)

    existing_keys = {str(r["fields"].get("표준키") or "").strip()
                     for r in fetch(WMS, XWALK, WP, ["표준키"])}
    wms_item_keys = {str(r["fields"].get("품목키") or "").strip()
                     for r in fetch(WMS, ITEM, WP, ["품목키"])}
    lookup = load_product_lookup({"Authorization": f"Bearer {TP}"})
    rows, s = build_mes_crosswalk_rows(
        mes_parts, mes_goods, existing_keys, wms_item_keys,
        {str(k).lower() for k in lookup})

    pt_rate = s["parts_in_wms"] / s["parts_total"] * 100 if s["parts_total"] else 0.0
    gd_known = s["goods_total"] - s["goods_no_code"]
    gd_rate = s["goods_code_in_tms"] / gd_known * 100 if gd_known else 0.0
    print("\n=== MES 크로스워크 매칭률 (hop 해소율) ===", flush=True)
    print(f"  파츠 hop: MES PT {s['parts_total']}종 — WMS ItemMaster 해소 "
          f"{s['parts_in_wms']} ({pt_rate:.1f}%) / 기존 스킵 {s['parts_already']} "
          f"/ 신규 INSERT {s['parts_new']}", flush=True)
    print(f"  굿즈 hop: MES 굿즈 {s['goods_total']}종 — 코드없음 {s['goods_no_code']} "
          f"/ TMS Product 해소 {s['goods_code_in_tms']}/{gd_known} ({gd_rate:.1f}%) "
          f"/ 기존 스킵 {s['goods_already']} / 신규 INSERT {s['goods_new']}", flush=True)

    if not args.write:
        print(f"\n[DRY-RUN] INSERT 예정 {len(rows)}행 — 반영하려면 --write", flush=True)
        return
    headers = {"Authorization": f"Bearer {WP}", "Content-Type": "application/json"}
    url = f"https://api.airtable.com/v0/{WMS}/{XWALK}"
    ok = err = 0
    for i in range(0, len(rows), 10):
        o, e = post_batch(url, headers, [{"fields": r} for r in rows[i:i + 10]])
        ok += o
        err += e
        print(f"  INSERT {i + len(rows[i:i + 10])}/{len(rows)} (ok={ok} err={err})", flush=True)
    print(f"\n[WRITE] KeyCrosswalk inserted={ok} err={err} (출처='mes_crosswalk')", flush=True)


if __name__ == "__main__":
    main()
