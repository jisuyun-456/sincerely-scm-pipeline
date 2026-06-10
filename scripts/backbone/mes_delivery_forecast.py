"""P3' Task 6 — MES 납기일 → 입하 CBM forecast (read-only, 쓰기 0).

MES ver.2.0(primary) 작업 row의 납기일·계획수량을 sync_item 브릿지(굿즈명→견적코드)
× TMS Product(견적코드→박스 CBM)로 join → 다음 7/14d 입하 예정 CBM 리포트.
P2b 크로스워크 소비 항목 (YAGNI: 집계 리포트만, 예측 모델·쓰기 없음).

Usage:
  python scripts/backbone/mes_delivery_forecast.py
"""
import os
import sys
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.backbone.keys import normalize_goods  # noqa: E402
from harness.backbone.mes_forecast import build_inbound_forecast  # noqa: E402
from harness.settlement.cbm_calc import load_product_lookup  # noqa: E402

load_dotenv()
MP = os.environ.get("AIRTABLE_MES_PAT") or sys.exit(
    "ERROR: AIRTABLE_MES_PAT 미설정 — .env 추가 필요")
WP = os.environ["AIRTABLE_WMS_PAT"]
TP = os.environ["AIRTABLE_PAT"]
MES = "appNSAPadsHbfaSHv"
MES_V2 = "tblg96ys2vfPdyxHq"    # MES ver.2.0 (primary)
MES_V1 = "tbljL0OqDoRW0Y5aD"    # MES 구버전 (cross-check)
WMS = "appLui4ZR5HWcQRri"
SYNC_ITEM = "tblwnNgHQxZ0WhDBh"   # sync_item (read-only ⚡미러, 굿즈명→굿즈코드 브릿지)


def fetch(base, tid, pat, fields):
    out, off = [], None
    while True:
        p = {"pageSize": 100, "fields[]": fields}
        if off:
            p["offset"] = off
        r = requests.get(f"https://api.airtable.com/v0/{base}/{tid}",
                         headers={"Authorization": f"Bearer {pat}"}, params=p, timeout=60)
        r.raise_for_status()
        d = r.json()
        out += d["records"]
        off = d.get("offset")
        if not off:
            break
    return out


def main():
    print("로딩: MES ver2.0 / sync_item 브릿지 / TMS Product...")
    mes = fetch(MES, MES_V2, MP, ["굿즈", "계획수량", "납기일", "작업 상태"])
    mes_v1 = fetch(MES, MES_V1, MP, ["납기일"])
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
    print(f"  MES v2 {len(mes)}행 (구버전 {len(mes_v1)}행 참고) / "
          f"브릿지 {len(name2code)}건 / Product 코드 {len(product_by_code)}건")

    out = build_inbound_forecast(
        [r["fields"] for r in mes], name2code, product_by_code, date.today())

    print("\n=== MES 납기일 입하 CBM forecast ===")
    print(f"대상 {out['n_total']}행 | 완료 제외 {out['n_excluded_status']} | "
          f"join 성공 {out['n_joined']} | 코드 미매칭 {out['n_unmatched_code']} | "
          f"납기일 없음 {out['n_no_date']} | 과거 납기 {out['n_past_due']} | "
          f"CBM 부재 {out['n_no_cbm']}")
    for h, cbm in sorted(out["by_horizon"].items()):
        print(f"  다음 {h}일 입하 예정: {cbm:.4f} m³")
    upcoming = sorted(out["by_date"].items())[:10]
    if upcoming:
        print("납기일별(최근 10):")
        for d, cbm in upcoming:
            print(f"  {d}: {cbm:.4f} m³")


if __name__ == "__main__":
    main()
