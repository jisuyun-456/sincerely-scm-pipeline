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


def load_product_lookup(headers: dict) -> dict[str, dict]:
    """
    Product 테이블 전체 조회 → 품목명(lower)/견적코드(lower) → entry dict.
    entry: {rec_id, name, code, box_type, qty_per_box, cbm_per_box}
    동일 entry가 name/code 두 키로 참조될 수 있음.
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
            entries.append({
                "rec_id":      rec["id"],
                "name":        str(f.get(FLD_PROD_NAME) or "").strip(),
                "code":        str(f.get(FLD_PROD_CODE) or "").strip().upper(),
                "box_type":    str(f.get(FLD_PROD_BOX_TYPE) or "").strip(),
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
            lookup[e["code"].lower()] = e
    return lookup


def _tokenize(text: str) -> frozenset:
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
) -> dict:
    """
    품목+수량 텍스트 → {"unload_fee", "total_cbm", "matched", "unmatched"}.

    qty_hint: 수량 정보가 텍스트에 없을 때 첫 번째 품목에 적용.
    """
    lines = parse_product_lines(product_text)
    if not lines:
        return {"unload_fee": 0, "total_cbm": 0.0, "matched": [], "unmatched": []}

    if qty_hint > 0 and all(q == 0 for _, q in lines):
        lines = [(p, qty_hint if i == 0 else 0) for i, (p, _) in enumerate(lines)]

    buckets: dict[str, int] = {"heavy": 0, "large": 0, "xlarge": 0}
    total_cbm = 0.0
    matched_list: list[dict] = []
    unmatched_list: list[str] = []

    for prod_name, qty in lines:
        key, entry, score = match_product(prod_name, lookup)
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
            "score":       score,
            "qty":         qty,
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
