"""WMS 네이티브 4테이블 생성 (Airtable meta API, idempotent).

이미 존재하는 테이블/필드는 건너뜀. 쓰기 대상은 WMS 네이티브 한정.
실행: AIRTABLE_WMS_PAT=... python -m harness.backbone.create_tables [--dry-run]
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

from harness.backbone.schema_def import TABLES, LINK_FIELDS, WMS_BASE

META = f"https://api.airtable.com/v0/meta/bases/{WMS_BASE}"


def _hdr() -> dict:
    return {"Authorization": f"Bearer {os.environ['AIRTABLE_WMS_PAT']}",
            "Content-Type": "application/json"}


def _get(url: str) -> dict:
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=_hdr())))


def _post(url: str, payload: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers=_hdr(), method="POST")
    return json.load(urllib.request.urlopen(req))


def existing_tables() -> dict[str, dict]:
    return {t["name"]: t for t in _get(f"{META}/tables")["tables"]}


def main(dry_run: bool = False) -> None:
    have = existing_tables()
    # 1차: 스칼라 테이블 생성
    for name, fields in TABLES.items():
        if name in have:
            print(f"[skip] table exists: {name}")
            continue
        payload = {"name": name, "fields": fields}
        if dry_run:
            print(f"[dry-run] create table {name} ({len(fields)} fields)")
            continue
        res = _post(f"{META}/tables", payload)
        print(f"[created] {name} -> {res['id']}")
    # 2차: 링크 필드 추가
    have = existing_tables()
    for tbl_name, fld_name, target_name in LINK_FIELDS:
        if tbl_name not in have or target_name not in have:
            print(f"[warn] missing table for link {tbl_name}.{fld_name}")
            continue
        tbl = have[tbl_name]
        if any(f["name"] == fld_name for f in tbl["fields"]):
            print(f"[skip] field exists: {tbl_name}.{fld_name}")
            continue
        payload = {"name": fld_name, "type": "multipleRecordLinks",
                   "options": {"linkedTableId": have[target_name]["id"]}}
        if dry_run:
            print(f"[dry-run] add link {tbl_name}.{fld_name} -> {target_name}")
            continue
        _post(f"{META}/tables/{tbl['id']}/fields", payload)
        print(f"[created] link {tbl_name}.{fld_name} -> {target_name}")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
