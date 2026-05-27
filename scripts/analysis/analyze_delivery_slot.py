"""배송슬롯 + 4 필드 패턴 분석 (P3 brainstorm 입력)

기간: 2025-01-01 ~ 2026-05-27
필드:
- 배송슬롯 (singleSelect, fldcSrlxCngYQHtSV) — 사용자 수동 결정 SSOT
- 배송시간(수정) (singleLineText, fldxvTp1sDVAon1Oh)
- 고객 희망 수령 시간 (singleLineText, fldydAmdTYfqTianY)
- 배송 특이사항란 (multilineText, fldaJ3YsrY5t6Lqh2)
- 체크파이널(배송 및 임가공 특이사항) (richText, fldrAuvgODWq67D9O)
- 배송방식 (rollup) — 택배 제외
- 출하확정일 (multipleLookupValues, fldzysbxmy4bMDk9U)
"""
import os
import json
import sys
from collections import Counter, defaultdict
from urllib.parse import urlencode

import urllib.request

PAT = os.environ.get("AIRTABLE_PAT")
if not PAT and len(sys.argv) > 1:
    PAT = sys.argv[1]
if not PAT:
    raise SystemExit("AIRTABLE_PAT required (env or argv[1])")

BASE = "app4x70a8mOrIKsMf"
TABLE = "tbllg1JoHclGYer7m"  # Shipment
URL = f"https://api.airtable.com/v0/{BASE}/{TABLE}"

FIELDS = [
    "출하확정일",
    "배송슬롯",
    "배송 특이사항란",
    "배송 방식",
    "배송요청",  # link to 배송요청 table for joining
]

import urllib.parse

# date filter applied in Python (multipleLookupValues makes formula tricky)
DATE_FROM = "2025-01-01"
DATE_TO = "2026-05-27"

def fetch_all():
    records = []
    offset = None
    page = 0
    while True:
        page += 1
        qs = "&".join(f"fields[]={urllib.parse.quote(f)}" for f in FIELDS)
        qs += "&pageSize=100"
        if offset:
            qs += f"&offset={urllib.parse.quote(offset)}"
        req = urllib.request.Request(
            f"{URL}?{qs}",
            headers={"Authorization": f"Bearer {PAT}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            print(f"HTTPError {e.code}: {body}", file=sys.stderr)
            print(f"URL: {URL}?{qs}", file=sys.stderr)
            raise
        batch = data.get("records", [])
        records.extend(batch)
        offset = data.get("offset")
        if page % 5 == 0:
            print(f"  ... page {page}, cumulative {len(records)} records", file=sys.stderr)
        if not offset:
            break
    return records

def in_date_range(record):
    val = record.get("fields", {}).get("출하확정일")
    if isinstance(val, list):
        val = val[0] if val else None
    if not val:
        return False
    return DATE_FROM <= str(val)[:10] <= DATE_TO

def fetch_요청_lookup(record_ids):
    """배송요청 table에서 시간·특이사항 필드 가져오기 (Shipment.배송요청 링크 기준)."""
    REQ_TABLE = "tblfIEiPJaEF0DVoM"
    REQ_FIELDS = ["배송시간(수정)", "고객 희망 수령 시간", "체크파이널(배송 및 임가공 특이사항)"]
    out = {}
    # Batch by 10 record IDs at a time (filterByFormula OR)
    batch_size = 10
    ids = list(record_ids)
    for i in range(0, len(ids), batch_size):
        batch = ids[i:i+batch_size]
        formula = "OR(" + ",".join(f"RECORD_ID()='{rid}'" for rid in batch) + ")"
        qs = "&".join(f"fields[]={urllib.parse.quote(f)}" for f in REQ_FIELDS)
        qs += f"&filterByFormula={urllib.parse.quote(formula)}&pageSize={batch_size}"
        req = urllib.request.Request(
            f"https://api.airtable.com/v0/{BASE}/{REQ_TABLE}?{qs}",
            headers={"Authorization": f"Bearer {PAT}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            print(f"WARN: 배송요청 fetch failed for batch {i}: {e.code} {e.read()[:200]}", file=sys.stderr)
            continue
        for r in data.get("records", []):
            out[r["id"]] = r.get("fields", {})
    return out

if __name__ == "__main__":
    all_records = fetch_all()
    print(f"TOTAL fetched (all dates): {len(all_records)}")
    records = [r for r in all_records if in_date_range(r)]
    print(f"In date range 2025-01-01 ~ 2026-05-27: {len(records)}")

    # Filter out 택배
    non_parcel = []
    parcel_count = 0
    for r in records:
        f = r.get("fields", {})
        method = f.get("배송 방식")
        if isinstance(method, list):
            method = method[0] if method else ""
        if method == "택배":
            parcel_count += 1
            continue
        non_parcel.append(r)
    print(f"택배 제외: {len(non_parcel)} non-택배 / {parcel_count} 택배")

    # 배송슬롯 distribution
    slot_counts = Counter()
    for r in non_parcel:
        slot = r["fields"].get("배송슬롯") or "(NULL)"
        slot_counts[slot] += 1
    print("\n=== 배송슬롯 분포 (택배 제외, n={}) ===".format(len(non_parcel)))
    for k, v in slot_counts.most_common():
        pct = v * 100 / len(non_parcel) if non_parcel else 0
        print(f"  {k}: {v} ({pct:.1f}%)")

    # 배송방식 distribution (within non-parcel)
    method_counts = Counter()
    for r in non_parcel:
        m = r["fields"].get("배송 방식")
        if isinstance(m, list):
            m = m[0] if m else "(NULL)"
        method_counts[m or "(NULL)"] += 1
    print("\n=== 배송방식 분포 (택배 제외) ===")
    for k, v in method_counts.most_common():
        print(f"  {k}: {v} ({v*100/len(non_parcel):.1f}%)")

    # 배송 특이사항란 fill rate by slot
    print("\n=== 슬롯별 배송 특이사항란 채워짐 비율 ===")
    by_slot = defaultdict(list)
    for r in non_parcel:
        slot = r["fields"].get("배송슬롯") or "(NULL)"
        by_slot[slot].append(r)
    for slot, bucket in sorted(by_slot.items(), key=lambda x: -len(x[1]))[:8]:
        with_note = sum(1 for r in bucket if r["fields"].get("배송 특이사항란"))
        print(f"  {slot}: 특이사항 {with_note}/{len(bucket)} ({with_note*100/len(bucket):.0f}%)")

    # 슬롯별 sample 특이사항 텍스트 (top 5 slots, 5 examples)
    print("\n=== 슬롯별 배송 특이사항란 sample (top 5 slots, max 5) ===")
    for slot, bucket in sorted(by_slot.items(), key=lambda x: -len(x[1]))[:5]:
        if slot == "(NULL)":
            continue
        print(f"\n  ▸ {slot} (n={len(bucket)})")
        samples = []
        for r in bucket:
            v = r["fields"].get("배송 특이사항란")
            if v:
                snippet = str(v)[:140].replace("\n", " | ")
                samples.append(f"    {snippet}")
            if len(samples) >= 5:
                break
        for s in samples:
            print(s)

    # 배송요청 join — sample 10 records per slot
    print("\n=== 배송요청 시간 필드 sample (slot별 max 3) ===")
    sample_record_ids = set()
    slot_to_req_ids = defaultdict(list)
    for slot, bucket in sorted(by_slot.items(), key=lambda x: -len(x[1]))[:5]:
        if slot == "(NULL)":
            continue
        sampled = 0
        for r in bucket:
            req_ids = r["fields"].get("배송요청") or []
            if not req_ids:
                continue
            rid = req_ids[0] if isinstance(req_ids, list) else req_ids
            slot_to_req_ids[slot].append(rid)
            sample_record_ids.add(rid)
            sampled += 1
            if sampled >= 3:
                break

    req_lookup = fetch_요청_lookup(sample_record_ids)
    for slot, rids in slot_to_req_ids.items():
        print(f"\n  ▸ {slot}")
        for rid in rids:
            f = req_lookup.get(rid, {})
            time_mod = f.get("배송시간(수정)", "")
            time_req = f.get("고객 희망 수령 시간", "")
            check = f.get("체크파이널(배송 및 임가공 특이사항)", "")
            if isinstance(check, dict):
                check = check.get("text", str(check)[:80])
            check_snip = str(check)[:100].replace("\n", " | ") if check else ""
            print(f"    배송시간(수정)='{time_mod}' / 희망='{time_req}' / 체크='{check_snip}'")
