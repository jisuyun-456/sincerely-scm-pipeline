"""북극성 측정 — 에이원·다영 출하 CBM_유효 완결율 (읽기 전용).

spec: docs/superpowers/specs/2026-08-12-bridge-cbm-crosswalk-design.md §1.1

분모 = **품목 텍스트를 보유한 출하** (텍스트 없는 건은 어떤 매핑으로도 구제 불가).
CBM_유효 보유 = Total_CBM > 0 또는 estimated_cbm > 0.

미보유 건은 셋으로 분해한다:
  ① 라인 해소됨(백필 미반영)  — 지금 코드로 계산되는데 estimated 가 안 쓰인 것
  ② 브릿지 등재로 순증 가능    — 부분 토큰 겹침이 있어 사람이 매핑 가능
  ③ 마스터 부재(규격요청/P2)   — Product 에 대응이 없음

거점 판정은 harness/tms_settlement/calc.py 와 동일 규칙(출고지 주소).
Airtable GET only.

실행: python scripts/crosswalk/measure_northstar.py [--json <path>]
필요 env: AIRTABLE_PAT (TMS), AIRTABLE_WMS_PAT (sync_item)
"""
from __future__ import annotations

import collections
import json
import os
import re
import sys

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
load_dotenv()

from harness.backbone.keys import is_service, normalize_goods
from harness.backbone.product_alias import inject_synthetic, resolve_product_entry
from harness.dispatch.cbm_estimator import parse_product_lines_v2
from harness.settlement.cbm_calc import _jaccard, _tokenize, load_product_lookup
from harness.tms_settlement.fetch import load_name2code

TMS_BASE = "app4x70a8mOrIKsMf"
SHIP_TBL = "tbllg1JoHclGYer7m"

F_SC = "fldBUwhBlhOMsJZdv"          # SC ID
F_TOTAL_CBM = "fldJ9DHjwoRyeUEqE"   # Total_CBM (실측)
F_EST_CBM = "fldaP8D9AM8CHEZ2o"     # estimated_cbm
F_ORIGIN = "fldb24I9EQ2KPXv6S"      # 출고지 주소 (rollup)
F_POST = "fldXXnGOXkm90snKn"        # 최종 출고 품목 및 수량
F_OUT = "fldgSupj5XLjJXYQo"         # 최종 출하 품목

# 사람이 매핑 가능하다고 볼 부분겹침 구간 (리졸버 임계 0.4 미만)
MAP_LOW, MAP_HIGH = 0.15, 0.40
_DANGLING_PAREN = re.compile(r"\([^)]*$")


def _str_field(v) -> str:
    if isinstance(v, list):
        return " ".join(str(x) for x in v if x)
    return str(v or "")


def _fnum(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def site_of(fields: dict) -> str | None:
    """calc.py 와 동일 규칙 — 출고지에 성남/다영이면 다영, 그 외 주소 보유는 에이원."""
    o = _str_field(fields.get(F_ORIGIN))
    if "성남" in o or "다영" in o:
        return "다영"
    return "에이원" if o.strip() else None


def fetch_shipments(headers: dict) -> list[dict]:
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{SHIP_TBL}"
    out: list[dict] = []
    cursor = None
    while True:
        params = {"pageSize": 100, "returnFieldsByFieldId": "true",
                  "fields[]": [F_SC, F_TOTAL_CBM, F_EST_CBM, F_ORIGIN, F_POST, F_OUT]}
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
    inject_synthetic(lookup)
    name2code = load_name2code(os.environ.get("AIRTABLE_WMS_PAT"))
    recs = fetch_shipments(headers)
    print(f"shipments {len(recs)} / product lookup {len(lookup)} / name2code {len(name2code)}")

    # Product 이름 토큰 사전 (rec_id 중복 제거)
    prod_tokens, seen_rid = [], set()
    for e in lookup.values():
        if e["rec_id"] in seen_rid:
            continue
        seen_rid.add(e["rec_id"])
        prod_tokens.append(_tokenize(e["name"]))

    res_cache: dict[str, bool] = {}
    score_cache: dict[str, float] = {}

    def resolves(nm: str) -> bool:
        if nm not in res_cache:
            e, _c, _m = resolve_product_entry(nm, None, name2code, lookup)
            res_cache[nm] = e is not None
        return res_cache[nm]

    def best_score(nm: str) -> float:
        """미해소 이름의 Product 최고 Jaccard. 잘린 괄호는 보정 후 재시도."""
        if nm in score_cache:
            return score_cache[nm]
        cands = [nm]
        fixed = _DANGLING_PAREN.sub("", nm).strip()
        if fixed and fixed != nm:
            cands.append(fixed)
        norm = normalize_goods(nm).strip()
        if norm and norm not in cands:
            cands.append(norm)
        best = 0.0
        for c in cands:
            t = _tokenize(c)
            if not t:
                continue
            for pt in prod_tokens:
                s = _jaccard(t, pt)
                if s > best:
                    best = s
        score_cache[nm] = best
        return best

    st: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    gain: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)

    for rec in recs:
        f = rec["fields"]
        site = site_of(f)
        if not site:
            continue
        text = f.get(F_POST) or f.get(F_OUT) or ""
        lines = [nm for nm, _q, _x in parse_product_lines_v2(str(text))
                 if nm and not is_service(nm)] if text else []
        has_cbm = _fnum(f.get(F_TOTAL_CBM)) > 0 or _fnum(f.get(F_EST_CBM)) > 0

        st[site]["전체"] += 1
        if _fnum(f.get(F_TOTAL_CBM)) > 0:
            st[site]["실측"] += 1
        if not lines:
            st[site]["텍스트없음"] += 1
            continue
        st[site]["텍스트보유"] += 1
        if has_cbm:
            st[site]["CBM유효"] += 1
            continue
        if any(resolves(nm) for nm in lines):
            st[site]["미보유_라인해소됨"] += 1
            continue
        mappable = [nm for nm in lines if MAP_LOW <= best_score(nm) < MAP_HIGH]
        if mappable:
            st[site]["미보유_브릿지순증가능"] += 1
            for nm in mappable:
                gain[site][nm] += 1
        else:
            st[site]["미보유_마스터부재"] += 1

    print()
    out_json: dict = {}
    for site in ("다영", "에이원"):
        s = st[site]
        txt = s["텍스트보유"]
        have = s["CBM유효"]
        pct = have / max(txt, 1) * 100
        print(f"=== {site} ===")
        print(f"  전 출하 {s['전체']} / 텍스트보유 {txt} / 텍스트없음 {s['텍스트없음']}")
        print(f"  ★ CBM_유효 완결율 : {have}/{txt} = {pct:.1f}%   (실측 {s['실측']})")
        print(f"    미보유 — 라인해소됨(백필 미반영) : {s['미보유_라인해소됨']}")
        print(f"    미보유 — 브릿지 등재로 순증 가능  : {s['미보유_브릿지순증가능']}")
        print(f"    미보유 — 마스터 부재(규격요청/P2) : {s['미보유_마스터부재']}")
        print()
        out_json[site] = {**dict(s), "완결율_pct": round(pct, 1)}

    for site in ("다영", "에이원"):
        if gain[site]:
            print(f"--- {site} 브릿지 등재 순증 후보 top 10 ---")
            for nm, c in gain[site].most_common(10):
                print(f"  x{c:<3} {best_score(nm):.2f}  {nm!r}")
            print()

    for i, a in enumerate(sys.argv):
        if a == "--json" and i + 1 < len(sys.argv):
            dest = sys.argv[i + 1]
            os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
            with open(dest, "w", encoding="utf-8") as fh:
                json.dump(out_json, fh, ensure_ascii=False, indent=2)
            print(f"wrote {dest}")


if __name__ == "__main__":
    main()
