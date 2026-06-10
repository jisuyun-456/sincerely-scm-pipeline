"""P2b Task 2b.2 — ⚡task 투입자재 vs WMS_BOM 검증·승급.

⚡task read-only → (PNA, PT) 쌍 추출 → WMS_BOM(검증상태='이송') 대조 →
일치 row '검증완료' PATCH + 검증률 stdout 리포트. WMS_BOM 신규 INSERT 0.
dry-run 기본, --write 게이트.

Usage:
  python scripts/backbone/task_bom_verify.py            # dry-run 검증률 측정
  python scripts/backbone/task_bom_verify.py --write    # 검증상태 승급 PATCH
"""
import argparse
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.backbone.task_verify import (  # noqa: E402
    TASK_MATERIAL_FIELDS, extract_task_pairs, select_bom_promotions,
)

load_dotenv()
WP = os.environ["AIRTABLE_WMS_PAT"]
WMS = "appLui4ZR5HWcQRri"
TASK = "tblsIiXQzrHMSPqH7"   # ⚡task (read-only)
BOM = "tblopHqepkx6mNEHL"    # WMS_BOM (검증상태 PATCH만 — INSERT 금지)


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="검증상태 승급 PATCH (기본 dry-run)")
    args = ap.parse_args()

    print("⚡task 로딩 (read-only)...", flush=True)
    tasks = fetch(WMS, TASK, WP, ["project_code", *TASK_MATERIAL_FIELDS])
    pairs = extract_task_pairs(r["fields"] for r in tasks)
    print(f"  task {len(tasks)}행 → (PNA, PT) 쌍 {len(pairs)}종", flush=True)

    print("WMS_BOM 로딩...", flush=True)
    bom = fetch(WMS, BOM, WP, ["프로젝트코드", "소품목_PT", "검증상태"])
    ids, s = select_bom_promotions(bom, pairs)
    isong = s["matched"] + s["unmatched"]
    rate = s["matched"] / isong * 100 if isong else 0.0
    print("\n=== task↔BOM 검증률 (hop 해소율) ===", flush=True)
    print(f"  BOM {s['total']}행: 이송 {isong} / 비대상(검증완료·폐기 등) {s['not_isong']} "
          f"/ 키없음 {s['no_key']}", flush=True)
    print(f"  task 일치 → 승급 대상: {s['matched']}/{isong} ({rate:.1f}%) "
          f"/ 미일치 {s['unmatched']}", flush=True)

    if not args.write:
        print(f"\n[DRY-RUN] 검증완료 승급 예정 {len(ids)}행 — 반영하려면 --write", flush=True)
        return
    headers = {"Authorization": f"Bearer {WP}", "Content-Type": "application/json"}
    url = f"https://api.airtable.com/v0/{WMS}/{BOM}"
    ok = err = 0
    for i in range(0, len(ids), 10):
        batch = [{"id": rid, "fields": {"검증상태": "검증완료"}} for rid in ids[i:i + 10]]
        o, e = patch_batch(url, headers, batch)
        ok += o
        err += e
        print(f"  PATCH {i + len(batch)}/{len(ids)} (ok={ok} err={err})", flush=True)
    print(f"\n[WRITE] BOM 검증상태 승급={ok} err={err}. INSERT 0.", flush=True)


if __name__ == "__main__":
    main()
