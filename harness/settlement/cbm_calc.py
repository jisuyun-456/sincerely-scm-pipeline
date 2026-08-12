"""
CBM 기반 상하차비용 + 총 CBM 계산 공용 모듈.
Product 테이블(tblBNh6oGDlTKGrdQ)에서 품목 룩업을 빌드하고,
출하 품목+수량 텍스트로 하차비와 총 CBM을 계산한다.
"""
import math
import os
import re
import time

import requests
from dotenv import load_dotenv

load_dotenv()
TMS_BASE = "app4x70a8mOrIKsMf"
TBL_PRODUCT = "tblBNh6oGDlTKGrdQ"

FLD_PROD_NAME     = "fldx01uKEnCd0J0nP"   # Name (primary)
FLD_PROD_CODE     = "fldtpUf2UVooLcxwd"   # 견적코드
FLD_PROD_BOX_TYPE = "fldqGM1lw2TUpZdKW"   # 박스명칭 (singleSelect)
FLD_PROD_QTY      = "fldENIdfxbVn8YnPI"   # 박스당 제품수 (number)
FLD_PROD_CBM_BOX  = "fldSBWylTZwGf1aEh"   # 박스 당 CBM (formula)

# 박스 타입 → (bucket_key, unit_size, fee_per_unit)
BOX_FEE_RULES: dict[str, tuple[str, int, int]] = {
    "중대형": ("heavy",  5, 5_000),
    "대형":   ("large",  3, 5_000),
    "특대형": ("xlarge", 3, 5_000),
}
MAX_UNLOAD_FEE = 50_000

# Standard box volume (m³) — fallback when Airtable '박스 당 CBM' formula returns 0.
# The formula maps 박스사이즈(mm) → m³ but covers only 3 sizes, AND most records have
# blank 박스사이즈, so ~98% of products return 0. This dict is the authoritative source.
BOX_TYPE_TO_CBM_M3: dict[str, float] = {
    "극소형": 0.0098,   # S280 (280×250×140)
    "중형":   0.0201,   # M350 (350×250×230)
    "중대형": 0.0493,   # M480 (480×380×270)
    "대형":   0.1066,   # L510 (510×510×410)
    "특대형": 0.1662,   # L560 (560×530×560)
}

# 박스명칭 → 박스사이즈 (singleSelect option string) for Airtable inserts.
BOX_TYPE_TO_SIZE_STR: dict[str, str] = {
    "극소형": "280*250*140",
    "중형":   "350*250*230",
    "중대형": "480*380*270",
    "대형":   "510*510*410",
    "특대형": "560*530*560",
}


def _resolve_dup(a: dict, b: dict) -> dict:
    """중복 견적코드 결정론 해소: formula CBM>0 우선 → 큰 qty_per_box → rec_id 사전순."""
    for x, y in [(a, b), (b, a)]:
        if x["cbm_per_box"] > 0 and y["cbm_per_box"] <= 0:
            return x
    if a["qty_per_box"] != b["qty_per_box"]:
        return a if a["qty_per_box"] > b["qty_per_box"] else b
    return a if a["rec_id"] <= b["rec_id"] else b


def load_product_lookup(headers: dict) -> dict[str, dict]:
    """
    Product 테이블 전체 조회 → 품목명(lower)/견적코드(lower) → entry dict.
    entry: {rec_id, name, code, box_type, qty_per_box, cbm_per_box}
    동일 entry가 name/code 두 키로 참조될 수 있음.
    중복 견적코드는 _resolve_dup로 결정론 해소 (formula CBM>0 우선).
    """
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_PRODUCT}"
    entries: list[dict] = []
    cursor = None
    while True:
        params: dict = {
            "returnFieldsByFieldId": "true",
            "fields[]": [FLD_PROD_NAME, FLD_PROD_CODE, FLD_PROD_BOX_TYPE,
                         FLD_PROD_QTY, FLD_PROD_CBM_BOX],
            "pageSize": 100,
        }
        if cursor:
            params["offset"] = cursor
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        for rec in data.get("records", []):
            f = rec["fields"]
            try:
                cbm_box = float(f.get(FLD_PROD_CBM_BOX) or 0)
            except (ValueError, TypeError):
                cbm_box = 0.0
            box_type = str(f.get(FLD_PROD_BOX_TYPE) or "").strip()
            if cbm_box <= 0:
                cbm_box = BOX_TYPE_TO_CBM_M3.get(box_type, 0.0)
            entries.append({
                "rec_id":      rec["id"],
                "name":        str(f.get(FLD_PROD_NAME) or "").strip(),
                "code":        str(f.get(FLD_PROD_CODE) or "").strip().upper(),
                "box_type":    box_type,
                "qty_per_box": max(1, int(f.get(FLD_PROD_QTY) or 1)),
                "cbm_per_box": cbm_box,
            })
        cursor = data.get("offset")
        if not cursor:
            break
        time.sleep(0.2)

    lookup: dict[str, dict] = {}
    for e in entries:
        if e["name"]:
            lookup[e["name"].lower()] = e
        if e["code"]:
            ck = e["code"].lower()
            lookup[ck] = _resolve_dup(lookup[ck], e) if ck in lookup else e
    # 공백 제거 alias — 붙임/띄움 철자 변형 매칭('스펙트럼컬러펜'↔'스펙트럼 컬러펜').
    # 실제 name/code 키는 절대 덮지 않음(gap fill만). alias 간 충돌은 _resolve_dup로 해소.
    real_keys = set(lookup.keys())
    for e in entries:
        if not e["name"]:
            continue
        nk = e["name"].lower().replace(" ", "")
        if not nk or nk in real_keys:
            continue
        lookup[nk] = _resolve_dup(lookup[nk], e) if nk in lookup else e
    return lookup


def _tokenize(text: str) -> frozenset:
    # Split on Korean↔Latin character boundaries before tokenizing
    # so "Tailored스트랩박스" → "Tailored 스트랩박스" and matches the Product table name
    text = re.sub(r"([가-힣])([A-Za-z])", r"\1 \2", text)
    text = re.sub(r"([A-Za-z])([가-힣])", r"\1 \2", text)
    tokens: set[str] = set()
    for part in re.split(r"[\s,+×()/·xX*]+", text):
        stripped = re.sub(r"\d+", "", part).strip()
        if len(stripped) >= 2:
            tokens.add(stripped.lower())
    return frozenset(tokens)


def _jaccard(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if (a and b) else 0.0


def match_product(name: str, lookup: dict) -> tuple[str, dict | None, float]:
    """
    품목명 → lookup 매칭. exact 먼저, 실패 시 Jaccard(≥0.4).
    Returns: (matched_key, entry_or_None, score)
    """
    name = name.strip()
    key = name.lower()
    if not key:
        return "", None, 0.0
    if key in lookup:
        return key, lookup[key], 1.0
    nk = key.replace(" ", "")   # 공백 무시 매칭 (룩업의 stripped alias와 연결)
    if nk != key and nk in lookup:
        return nk, lookup[nk], 1.0

    tgt = _tokenize(name)
    if not tgt:
        return "", None, 0.0

    best_key, best_score = "", 0.0
    seen_ids: set[str] = set()
    for k, entry in lookup.items():
        rid = entry["rec_id"]
        if rid in seen_ids:
            continue
        seen_ids.add(rid)
        score = _jaccard(tgt, _tokenize(entry["name"]))
        if score > best_score:
            best_score = score
            best_key = k

    if best_score >= 0.4:
        return best_key, lookup[best_key], best_score
    return "", None, 0.0


def parse_product_lines(text: str) -> list[tuple[str, int]]:
    """
    출하 품목+수량 텍스트 → [(품목명, 수량), ...].
    수량 없으면 0 반환.
    예: "굿이너프 비치타월×40 / Solid G형 L×20" → [("굿이너프 비치타월", 40), ("Solid G형 L", 20)]
    """
    results: list[tuple[str, int]] = []
    for segment in re.split(r"[,/\n;]+", text):
        segment = segment.strip()
        if not segment:
            continue
        m = re.search(r"[×xX*]\s*(\d+)\s*$", segment)
        if m:
            qty = int(m.group(1))
            prod = segment[: m.start()].strip()
        else:
            m2 = re.search(r"\s+(\d+)\s*$", segment)
            if m2 and int(m2.group(1)) > 0:
                qty = int(m2.group(1))
                prod = segment[: m2.start()].strip()
            else:
                qty = 0
                prod = segment
        if prod:
            results.append((prod, qty))
    return results


def calc_from_products(
    product_text: str,
    lookup: dict,
    qty_hint: int = 0,
    name2code: dict | None = None,
) -> dict:
    """
    품목+수량 텍스트 → {"unload_fee", "total_cbm", "matched", "unmatched"}.

    파싱은 parse_product_lines_v2 (보너스 수량 '100+1' · '[N]' 인덱스 · 천단위 콤마 처리).

    qty_hint: 수량 정보가 텍스트에 없을 때 첫 번째 품목에 적용.
    name2code: sync_item 굿즈명→굿즈코드. 주어지면 공유 리졸버(이름→코드→V2 alias→Product)로
      캐스케이드와 동일 경로 해소, 실패 시 이름 Jaccard 폴백. None이면 현행 Jaccard 동작 보존.
    """
    from harness.backbone.product_alias import resolve_product_entry
    from harness.dispatch.cbm_estimator import parse_product_lines_v2

    # v2 파서: 보너스 수량('100+1')·'[N]' 인덱스·천단위 콤마·무공백 수량을 처리한다.
    # v1은 '100+1'에서 수량을 유실해 n_boxes=1로 CBM을 과소계상했다(실측 5,583 라인).
    lines = parse_product_lines_v2(product_text)
    if not lines:
        return {"unload_fee": 0, "total_cbm": 0.0, "matched": [], "unmatched": []}

    if qty_hint > 0 and all(q == 0 for _, q, _x in lines):
        lines = [(p, qty_hint if i == 0 else 0, x)
                 for i, (p, _q, x) in enumerate(lines)]

    buckets: dict[str, int] = {"heavy": 0, "large": 0, "xlarge": 0}
    total_cbm = 0.0
    matched_list: list[dict] = []
    unmatched_list: list[str] = []

    for prod_name, qty, extra in lines:
        entry, key, _method = resolve_product_entry(prod_name, None, name2code, lookup)
        if entry is None:
            unmatched_list.append(prod_name)
            continue

        qty_per_box = entry["qty_per_box"]
        cbm_per_box = entry["cbm_per_box"]
        box_type = entry["box_type"]

        n_boxes = math.ceil(qty / qty_per_box) if qty > 0 else 1
        total_cbm += n_boxes * cbm_per_box

        rule = BOX_FEE_RULES.get(box_type)
        if rule:
            bucket_name, _, _ = rule
            buckets[bucket_name] += n_boxes

        matched_list.append({
            "name":        prod_name,
            "matched_key": key,
            "method":      _method,
            "qty":         qty,
            "extra":       extra,
            "n_boxes":     n_boxes,
            "box_type":    box_type,
            "cbm_per_box": cbm_per_box,
        })

    unload = 0
    for _, (bucket_name, unit_size, fee) in BOX_FEE_RULES.items():
        unload += (buckets[bucket_name] // unit_size) * fee
    unload = min(unload, MAX_UNLOAD_FEE)

    return {
        "unload_fee": unload,
        "total_cbm":  round(total_cbm, 4),
        "matched":    matched_list,
        "unmatched":  unmatched_list,
    }
