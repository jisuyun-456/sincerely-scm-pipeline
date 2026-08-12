"""출하 CBM 커버리지 전수 측정 + 정산 금액 delta 리포트 (읽기 전용).

Spec: docs/superpowers/specs/2026-08-11-shipment-cbm-parse-match-design.md §7

실행: python scripts/settlement/measure_cbm_coverage.py
필요 env: AIRTABLE_PAT (TMS), AIRTABLE_WMS_PAT (sync_item name2code)
"""
from __future__ import annotations

import collections
import json
import os
import sys
from datetime import date

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
load_dotenv()

from harness.backbone.keys import is_service
from harness.backbone.product_alias import inject_synthetic
from harness.settlement.cbm_calc import (calc_from_products, load_product_lookup,
                                         match_product)
from harness.tms_settlement.config import (DRIVER_PARK, F_BOX_QTY, F_BOX_QTY_DIRECT,
                                           F_BOX_TEXT, F_ITEMS_MFG, F_PARTNER,
                                           F_PRODUCT_FINAL, F_PROJECT_CODE)
from harness.tms_settlement.fetch import load_name2code

TMS_BASE = "app4x70a8mOrIKsMf"
TBL_SHIP = "tbllg1JoHclGYer7m"
FLD_OUT = "fldgSupj5XLjJXYQo"    # 최종 출하 품목
FLD_POST = "fldXXnGOXkm90snKn"   # 최종 출고 품목 및 수량
FLD_SC = "fldBUwhBlhOMsJZdv"     # SC ID

# 정산 노출(박종성) 섹션용 추가 필드 — calc_park 게이팅 미러링
# (harness/tms_settlement/calc.py:185-243)
SETTLEMENT_EXTRA_FIELDS = [F_PARTNER, F_BOX_TEXT, F_BOX_QTY_DIRECT, F_BOX_QTY,
                           F_PROJECT_CODE, F_ITEMS_MFG]


def _str_field(raw: object) -> str:
    """calc.py:_str_field 미러 — rollup list 필드에서 첫 값을 뽑는다."""
    if isinstance(raw, list):
        return str(raw[0] or "").strip() if raw else ""
    return str(raw or "").strip()


def fetch_shipments(headers: dict) -> list[dict]:
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_SHIP}"
    out: list[dict] = []
    cursor = None
    while True:
        params = {"pageSize": 100, "returnFieldsByFieldId": "true",
                  "fields[]": [FLD_OUT, FLD_POST, FLD_SC] + SETTLEMENT_EXTRA_FIELDS}
        if cursor:
            params["offset"] = cursor
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        d = r.json()
        out.extend(d.get("records", []))
        cursor = d.get("offset")
        if not cursor:
            return out


def main() -> None:
    tp = os.environ["AIRTABLE_PAT"]
    headers = {"Authorization": f"Bearer {tp}"}
    lookup = load_product_lookup(headers)
    inject_synthetic(lookup)   # SYNTHETIC SKU(TWKF 등) 코드 해소 경로 parity
                                # (harness/tms_settlement/fetch.py:load_cbm_lookup)
    name2code = load_name2code(os.environ.get("AIRTABLE_WMS_PAT"))
    recs = fetch_shipments(headers)
    print(f"shipments: {len(recs)} / product lookup: {len(lookup)} / "
          f"name2code: {len(name2code)}")

    # method='jaccard'는 exact 히트(score 1.0)에도 붙는다(cbm_calc.py:153-157의 정확·무공백
    # alias 경로). matched[]에는 score가 없으므로 위험 구간(0.4~0.5)을 보려면 재계산해야
    # 한다. 동일 굿즈명이 수천 건 반복되므로 이름 단위로 캐시한다.
    score_cache: dict[str, float] = {}

    def name_score(nm: str) -> float:
        if nm not in score_cache:
            _k, e, s = match_product(nm, lookup)
            if e is None:      # jaccard_norm 경로 — 정규화한 이름으로 재계산
                from harness.backbone.keys import normalize_goods
                _k, e, s = match_product(normalize_goods(nm), lookup)
            score_cache[nm] = s if e is not None else 0.0
        return score_cache[nm]

    lines = matched = cbm_able = 0
    by_method: collections.Counter = collections.Counter()
    score_hist: collections.Counter = collections.Counter()
    fuzzy: list[dict] = []
    per_ship: list[dict] = []

    for rec in recs:
        f = rec["fields"]
        text = f.get(FLD_POST) or f.get(FLD_OUT) or ""
        if not text:
            continue
        out = calc_from_products(str(text), lookup, name2code=name2code)
        for m in out["matched"]:
            if is_service(m["name"]):
                continue
            lines += 1
            matched += 1
            by_method[m.get("method", "?")] += 1
            if m["qty"] > 0 and m["cbm_per_box"] > 0:
                cbm_able += 1
            if m.get("method") in ("jaccard", "jaccard_norm"):
                sc = name_score(m["name"])
                score_hist[f"{int(sc * 10) / 10:.1f}"] += 1
                if sc < 1.0:          # exact 히트는 위험 구간이 아니다
                    fuzzy.append({"name": m["name"], "key": m["matched_key"],
                                  "method": m["method"], "score": round(sc, 3),
                                  "qty": m["qty"]})
        for u in out["unmatched"]:
            if not is_service(u):
                lines += 1
        per_ship.append({
            "sc": f.get(FLD_SC), "total_cbm": out["total_cbm"],
            "unload_fee": out["unload_fee"],
            "n_matched": len(out["matched"]),
            "n_unmatched": len(out["unmatched"]),
        })

    print(f"\n=== coverage ===")
    print(f"  분모(파싱된 비서비스 라인) : {lines}")
    print(f"  matched                    : {matched} = {matched / max(lines, 1) * 100:.1f}%")
    print(f"  CBM-able (주 지표, 절대건수): {cbm_able} = "
          f"{cbm_able / max(lines, 1) * 100:.1f}%")
    print(f"  ※ 분모는 파서에 따라 달라진다(v1 19,547 / v2 19,709). % 가 아니라")
    print(f"    CBM-able 절대건수를 baseline 과 비교한다 (기준선 2,828 → 목표 ~12,100).")

    print(f"\n=== 해소 경로 분포 ===")
    for k, v in by_method.most_common():
        print(f"  {k:<16} {v}")

    print(f"\n=== 이름매칭 score 분포 (jaccard 계열) ===")
    for k in sorted(score_hist):
        print(f"  {k}~ : {score_hist[k]}")

    tot_fee = sum(p["unload_fee"] for p in per_ship)
    tot_cbm = sum(p["total_cbm"] for p in per_ship)
    print(f"\n=== 상하차비 무조건 커버리지 합계 (전체 출하 upper bound — 실제 정산 delta 아님) ===")
    print(f"  ※ 아래 값은 calc_park 게이팅(박종성 한정 · F_BOX_TEXT 비었을 때만 CBM 폴백)을")
    print(f"    거치지 않고 전체 {len(per_ship)}건에 무조건 CBM 상하차비를 합산한 커버리지")
    print(f"    상한선이다. 실제 정산 노출 규모는 아래 '실제 정산 노출' 섹션을 봐야 한다.")
    print(f"  상하차비 합계 (upper bound) : {tot_fee:,}원")
    print(f"  CBM 합계 (upper bound)      : {tot_cbm:,.2f} m3")

    # ── 실제 정산 노출 (박종성 calc_park 게이팅 미러) ──────────────────────────
    # calc_park(harness/tms_settlement/calc.py:185-243): CBM 상하차비는 박종성에게만,
    # F_BOX_TEXT(+PNA fallback: F_BOX_QTY_DIRECT → F_BOX_QTY)가 비어있을 때만 폴백으로
    # 계산된다. box_text가 있으면 _parse_unload_fee가 우선하고 cbm_unload는 전량 폐기된다
    # (calc.py:265). 품목 텍스트도 F_ITEMS_MFG 우선 → F_PRODUCT_FINAL 폴백으로, 커버리지
    # 섹션이 쓰는 FLD_POST/FLD_OUT(dispatch/CBM-estimator 파이프라인 필드)와는 다르다.
    park_recs = [r for r in recs if DRIVER_PARK in (r["fields"].get(F_PARTNER) or [])]
    exposed: list[dict] = []
    for rec in park_recs:
        f = rec["fields"]
        box_text = f.get(F_BOX_TEXT, "") or ""
        if not box_text and "PNA" in _str_field(f.get(F_PROJECT_CODE)).upper():
            box_text = (_str_field(f.get(F_BOX_QTY_DIRECT))
                        or _str_field(f.get(F_BOX_QTY)) or "")
        if box_text:
            continue  # box_text 있음 → cbm_unload 미사용 (calc.py:265)
        items_text = _str_field(f.get(F_ITEMS_MFG)) or _str_field(f.get(F_PRODUCT_FINAL))
        if not items_text:
            continue
        exp_out = calc_from_products(items_text, lookup, name2code=name2code)
        exposed.append({"sc": f.get(FLD_SC), "cbm_unload": exp_out["unload_fee"],
                        "total_cbm": exp_out["total_cbm"]})

    exposed_fee = sum(e["cbm_unload"] for e in exposed)
    print(f"\n=== 실제 정산 노출 (박종성 calc_park 게이팅 미러 — 진짜 delta 후보) ===")
    print(f"  박종성 배정 전체건            : {len(park_recs)}")
    print(f"  box_text 없음 & CBM 폴백 노출 : {len(exposed)}")
    print(f"  cbm_unload 합계               : {exposed_fee:,}원")

    top = sorted(per_ship, key=lambda p: p["unload_fee"], reverse=True)[:20]
    print(f"\n=== 상하차비 상위 20건 (표본 확인용) ===")
    for p in top:
        print(f"  {p['sc']}: {p['unload_fee']:,}원 / {p['total_cbm']:.3f} m3 "
              f"(매칭 {p['n_matched']} 미매칭 {p['n_unmatched']})")

    fuzzy.sort(key=lambda x: x["score"])
    print(f"\n=== 위험 구간 매칭 표본 (score<1.0, 낮은 순 20건 — 오매칭 육안 확인) ===")
    for s in fuzzy[:20]:
        print(f"  [{s['method']} {s['score']}] {s['name']!r} -> {s['key']} x{s['qty']}")

    os.makedirs("outputs", exist_ok=True)
    dest = f"outputs/cbm-coverage-{date.today().isoformat()}.json"
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump({"lines": lines, "matched": matched, "cbm_able": cbm_able,
                   "by_method": dict(by_method), "score_hist": dict(score_hist),
                   "total_unload_fee_upper_bound": tot_fee,
                   "total_cbm_upper_bound": round(tot_cbm, 3),
                   "upper_bound_note": (
                       "무조건 전체 출하 합산 커버리지 지표 — calc_park 게이팅 미적용, "
                       "실제 정산 delta 아님. 실제 노출은 settlement_exposure 참조."),
                   "settlement_exposure": {
                       "park_assigned": len(park_recs),
                       "exposed_count": len(exposed),
                       "exposed_cbm_unload_total": exposed_fee,
                       "exposed_samples": exposed[:50],
                   },
                   "fuzzy_samples": fuzzy[:100], "per_shipment": per_ship},
                  fh, ensure_ascii=False, indent=2)
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main()
