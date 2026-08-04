"""WMS_BOM task↔BOM 검증률 측정 — READ-ONLY (PATCH 경로 없음).

task_bom_verify.py의 dry-run 측정만 분리한 읽기 전용 도구.
승급(--write)은 task_bom_verify.py로만 수행.
"""
import os
import sys
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
TASK = "tblsIiXQzrHMSPqH7"
BOM = "tblopHqepkx6mNEHL"


def fetch(tid, fields):
    out, off = [], None
    while True:
        p = {"pageSize": 100, "fields[]": fields}
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


tasks = fetch(TASK, ["project_code", *TASK_MATERIAL_FIELDS])
pairs = extract_task_pairs(r["fields"] for r in tasks)
bom = fetch(BOM, ["프로젝트코드", "소품목_PT", "검증상태"])
ids, s = select_bom_promotions(bom, pairs)
isong = s["matched"] + s["unmatched"]
rate = s["matched"] / isong * 100 if isong else 0.0
cur_verified = s["total"] - isong - s["no_key"]
print(f"task {len(tasks)}행 → (PNA,PT) 쌍 {len(pairs)}")
print(f"BOM {s['total']}행: 이송(미검증) {isong} / 비대상 {s['not_isong']} / 키없음 {s['no_key']}")
print(f"현재 검증완료: {cur_verified} ({cur_verified/s['total']*100:.1f}%)")
print(f"task 일치 승급대상: {len(ids)} → 승급 후 검증완료 {cur_verified+len(ids)} "
      f"({(cur_verified+len(ids))/s['total']*100:.1f}%)")
print(f"승급률(이송 중): {rate:.1f}% / 미일치 {s['unmatched']}")
