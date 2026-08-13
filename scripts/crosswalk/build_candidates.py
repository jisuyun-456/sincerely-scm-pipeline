"""크로스워크 후보 생성 — 실측 시드에서 초기 채우기 (읽기 전용).

spec: docs/superpowers/specs/2026-08-12-bridge-cbm-crosswalk-design.md §6

Airtable 은 GET 만 한다. 산출물은 git 파일 2개:
  data/crosswalk/goods_crosswalk.csv  — SSOT (확정 + 미검증)
  data/crosswalk/pending_specs.csv    — 보류 = 규격요청 리스트 (품질혁신파트 전달)

⚠️ INSERT-only: 기존 행은 어떤 컬럼도 수정하지 않는다. 신규 표준키만 append.
   사람이 미검증→확정으로 올린 판정을 재실행이 되돌리면 거버넌스가 무너진다.

실행: python scripts/crosswalk/build_candidates.py [--write]
필요 env: AIRTABLE_PAT (TMS), AIRTABLE_WMS_PAT (sync_item)
"""
from __future__ import annotations

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

COLUMNS = ["표준키", "키유형", "TMS_견적코드", "매칭방식",
           "매칭신뢰도", "검증상태", "근거"]

CROSSWALK_CSV = os.path.join("data", "crosswalk", "goods_crosswalk.csv")
PENDING_CSV = os.path.join("data", "crosswalk", "pending_specs.csv")

AUTO_CONFIRM_SCORE = 1.0    # 정규화 후 exact — 철자변형일 뿐 (spec D2)
PENDING_SCORE = 0.5         # 미만이면 규격요청 대상 (spec §6.2)


def classify(score: float, matched: bool) -> tuple[str, str]:
    """(검증상태, 매칭방식) — spec §6.2 진입 규칙."""
    if not matched:
        return "보류", "수기"
    if score >= AUTO_CONFIRM_SCORE:
        return "확정", "정확"
    if score < PENDING_SCORE:
        return "보류", "유사"
    return "미검증", "유사"


def merge_rows(existing: list[dict], candidates: list[dict]) -> tuple[list[dict], int]:
    """INSERT-only 병합 — 기존 행 무수정, 신규 표준키만 append (spec §6.3).

    정렬: 키유형 → 표준키. diff 안정성이 리뷰게이트의 전제다.
    """
    seen = {(r.get("표준키") or "").strip() for r in existing}
    added = 0
    out = list(existing)
    for c in candidates:
        k = (c.get("표준키") or "").strip()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(c)
        added += 1
    out.sort(key=lambda r: ((r.get("키유형") or ""), (r.get("표준키") or "")))
    return out, added


def read_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: str, rows: list[dict], *, bom: bool = False) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    enc = "utf-8-sig" if bom else "utf-8"
    with open(path, "w", encoding=enc, newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})


def collect_candidates() -> tuple[list[dict], list[dict], dict]:
    """Shipment 텍스트 전수 → (crosswalk 후보, 규격요청 후보, stats). Airtable GET only."""
    import collections

    import requests
    from dotenv import load_dotenv

    from harness.backbone.keys import is_service
    from harness.backbone.product_alias import inject_synthetic, resolve_product_entry
    from harness.dispatch.cbm_estimator import parse_product_lines_v2
    from harness.settlement.cbm_calc import load_product_lookup, match_product
    from harness.tms_settlement.fetch import load_name2code

    load_dotenv()
    tp = os.environ["AIRTABLE_PAT"]
    headers = {"Authorization": f"Bearer {tp}"}
    lookup = load_product_lookup(headers)
    inject_synthetic(lookup)
    name2code = load_name2code(os.environ.get("AIRTABLE_WMS_PAT"))

    url = "https://api.airtable.com/v0/app4x70a8mOrIKsMf/tbllg1JoHclGYer7m"
    recs, cursor = [], None
    while True:
        params = {"pageSize": 100, "returnFieldsByFieldId": "true",
                  "fields[]": ["fldXXnGOXkm90snKn", "fldgSupj5XLjJXYQo"]}
        if cursor:
            params["offset"] = cursor
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        d = r.json()
        recs.extend(d.get("records", []))
        cursor = d.get("offset")
        if not cursor:
            break

    freq: collections.Counter = collections.Counter()
    best: dict[str, tuple[float, str, str]] = {}   # name → (score, code, method)
    for rec in recs:
        f = rec["fields"]
        text = f.get("fldXXnGOXkm90snKn") or f.get("fldgSupj5XLjJXYQo") or ""
        if not text:
            continue
        for nm, _q, _x in parse_product_lines_v2(str(text)):
            if not nm or is_service(nm):
                continue
            freq[nm] += 1
            if nm in best:
                continue
            entry, code, method = resolve_product_entry(nm, None, name2code, lookup)
            if entry is None:
                best[nm] = (0.0, "", method)
                continue
            if method in ("code", "crosswalk", "name2code"):
                score = 1.0
            else:
                _k, e, s = match_product(nm, lookup)
                if e is None:
                    from harness.backbone.keys import normalize_goods
                    _k, e, s = match_product(normalize_goods(nm), lookup)
                score = s if e is not None else 0.0
            best[nm] = (score, code or "", method)

    cross, pending = [], []
    stats = collections.Counter()
    for nm, (score, code, method) in best.items():
        status, how = classify(score, bool(code))
        row = {"표준키": nm, "키유형": "굿즈명", "TMS_견적코드": code,
               "매칭방식": how, "매칭신뢰도": f"{score:.2f}",
               "검증상태": status,
               "근거": f"{method} score={score:.2f} freq={freq[nm]}"}
        stats[status] += 1
        (pending if status == "보류" else cross).append(row)

    # 규격요청은 빈도 내림차순 — 무엇부터 요청할지 우선순위
    pending.sort(key=lambda r: -freq.get(r["표준키"], 0))
    return cross, pending, dict(stats)


def main() -> None:
    write = "--write" in sys.argv
    cross, pending, stats = collect_candidates()
    existing = read_csv(CROSSWALK_CSV)
    merged, added = merge_rows(existing, cross)
    pend_existing = read_csv(PENDING_CSV)
    pend_merged, pend_added = merge_rows(pend_existing, pending)

    print(f"후보: crosswalk {len(cross)} (신규 {added}) / 규격요청 {len(pending)} "
          f"(신규 {pend_added})")
    print(f"진입 분포: {stats}")
    if not write:
        print("DRY-RUN — 쓰려면 --write")
        return
    write_csv(CROSSWALK_CSV, merged)
    write_csv(PENDING_CSV, pend_merged, bom=True)
    print(f"WROTE {CROSSWALK_CSV} ({len(merged)}행) / {PENDING_CSV} ({len(pend_merged)}행)")


if __name__ == "__main__":
    main()
