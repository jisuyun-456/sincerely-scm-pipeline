"""P3' Task 5 — WMS_BOM.구성유형 백필 (sync_parts.파츠유형 매핑).

소품목_PT → sync_parts.'파츠 유형 (right data)' → 구성유형(원부자재/포장재/임가공).
Phantom·유형없음·미등록PT는 미매핑 리포트(추측 금지, '키트'는 파생 불가).
매핑률은 PATCH 무관 집계(재실행 안정). dry-run 기본, --write 게이트(CP③).

Usage:
  python scripts/backbone/bom_component_type.py            # dry-run 분포 리포트
  python scripts/backbone/bom_component_type.py --write    # 구성유형 PATCH
"""
import argparse
import os
import sys
import time
from collections import Counter
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.backbone.bom_bootstrap import map_parttype_to_component  # noqa: E402

load_dotenv()
WP = os.environ["AIRTABLE_WMS_PAT"]
WMS = "appLui4ZR5HWcQRri"
BOM = "tblopHqepkx6mNEHL"   # WMS_BOM (allowlist 내 — 구성유형 PATCH만)
SP = "tblzJh0V4hdo4Xbvx"    # sync_parts (read-only ⚡미러)
F_SP_CODE = "fld8gjySjm4XkCpMc"        # 파츠 코드
F_SP_TYPE = "fldaGX8DpArGed5tW"        # 파츠 유형 (right data) — (wrong data!) 쌍둥이 주의


def fetch(tid, fields, by_field_id=False):
    out, off = [], None
    while True:
        p = {"pageSize": 100, "fields[]": fields}
        if by_field_id:
            p["returnFieldsByFieldId"] = "true"
        if off:
            p["offset"] = off
        r = requests.get(f"https://api.airtable.com/v0/{WMS}/{tid}",
                         headers={"Authorization": f"Bearer {WP}"}, params=p, timeout=60)
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
            print(f"  PATCH 실패 {r.status_code}: {r.text[:200]}")
            return 0, len(batch)
        except requests.RequestException as exc:
            if attempt < 2:
                time.sleep(30 * (attempt + 1))
                continue
            print(f"  PATCH 예외: {exc}")
            return 0, len(batch)
    return 0, len(batch)


def main():
    ap = argparse.ArgumentParser(description="WMS_BOM 구성유형 백필")
    ap.add_argument("--write", action="store_true", help="구성유형 PATCH 실행")
    args = ap.parse_args()

    print("로딩: WMS_BOM / sync_parts 파츠유형...")
    bom = fetch(BOM, ["소품목_PT", "구성유형"])
    sp = fetch(SP, [F_SP_CODE, F_SP_TYPE], by_field_id=True)
    pt_type = {}
    for rec in sp:
        f = rec.get("fields", {})
        code = str(f.get(F_SP_CODE) or "").strip()
        if code:
            pt_type[code] = str(f.get(F_SP_TYPE) or "").strip()
    print(f"  BOM {len(bom)}행 / sync_parts 유형 {len(pt_type)}PT")

    dist = Counter()
    unmapped = Counter()
    to_write = []
    n_already = 0
    for rec in bom:
        f = rec.get("fields", {})
        pt = str(f.get("소품목_PT") or "").strip()
        comp = map_parttype_to_component(pt_type.get(pt))
        if comp is None:
            reason = ("PT_미등록" if pt not in pt_type
                      else (pt_type.get(pt) or "유형없음"))
            unmapped[reason] += 1
            continue
        dist[comp] += 1
        cur = f.get("구성유형")
        if cur == comp:
            n_already += 1
        else:
            to_write.append({"id": rec["id"], "fields": {"구성유형": comp}})

    n = len(bom)
    mapped = sum(dist.values())
    print("\n=== WMS_BOM 구성유형 백필 ===")
    print(f"BOM {n}행 | 매핑 가능 {mapped} ({mapped / n * 100:.1f}%) | 기적용 {n_already}")
    print("분포: " + " / ".join(f"{k} {v}" for k, v in dist.most_common()))
    print("미매핑: " + " / ".join(f"{k} {v}" for k, v in unmapped.most_common()))

    if not args.write:
        print(f"\n[DRY-RUN] PATCH 예정 {len(to_write)}행 — 반영하려면 --write (CP③ 승인)")
        return

    ok = err = 0
    url = f"https://api.airtable.com/v0/{WMS}/{BOM}"
    headers = {"Authorization": f"Bearer {WP}", "Content-Type": "application/json"}
    for i in range(0, len(to_write), 10):
        o, e = patch_batch(url, headers, to_write[i:i + 10])
        ok += o
        err += e
    print(f"\n[WRITE] WMS_BOM 구성유형 patched={ok} err={err}")


if __name__ == "__main__":
    main()
