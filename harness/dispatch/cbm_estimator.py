"""CBM 추정 엔진 (Sub-Spec 2).

Shipment 출하 품목 텍스트 → 라인별 (품목, 본수량+여분, 여분) 추출 → Product
매칭 → 예상 CBM 산출. 시점 분기:
- Total_CBM > 0  → 실측 사용 (confidence=1.0, mode='실측')
- 최종 출고 품목 및 수량 (임가공 후)  → mode='임가공_후_추정'
- 최종 출하 품목 (임가공 전)         → mode='임가공_전_추정'

Step 1 of Task 3 — parse_product_lines_v2 (이번 commit 범위).
Step 2 (estimate_shipment_cbm) + write-back은 다음 commit.
"""
from __future__ import annotations

import math
import re

from harness.settlement.cbm_calc import match_product

# Thousand-separator: '1,000' → '1000' (digit-comma-three-digits, not in larger run)
_THOUSANDS_COMMA = re.compile(r"(\d),(?=\d{3}(?!\d))")

# Split AFTER quantity-unit when followed by more text (multi-product no-delim case).
# e.g. '핸디링미니선풍기 2500개 페이퍼샤쉐[1] 1000개' → split after '2500개 '
_SPLIT_AFTER_QTY_UNIT = re.compile(
    r"(\d+\s*(?:개|EA|ea|set|SET|박스))\s+(?=\S)"
)

# Bare-digit qty split: 'product1 200 product2' — split only when followed by NOT a unit.
# Requires preceding char to be Korean/Latin/]/) (i.e., end of a product name).
_SPLIT_AFTER_BARE_QTY = re.compile(
    r"(?<=[가-힣A-Za-z\]\)])\s+(\d+)\s+(?!(?:개|EA|ea|set|SET|박스)(?:\s|$))"
)

# Trailing quantity patterns, ordered most-specific first.
_QTY_SUFFIX_PATTERNS = [
    re.compile(r"[×xX*]\s*(\d+)\s*$"),
    re.compile(r"(\d+)\s*(?:개|EA|ea|set|SET|박스)\s*$"),
    re.compile(r"\s+(\d+)\s*$"),
]

# No-whitespace quantity: '에코컵(커스텀박스)3000개' (한글/Latin/) directly followed by digits+개|EA)
_QTY_NOSPACE = re.compile(r"([가-힣A-Za-z\)])(\d+)\s*(?:개|EA|ea)\s*$")

# Extra qty marker: '+10', '+여분 5', '여분 5'
_EXTRA_PATTERN = re.compile(r"\+\s*(?:여분\s*)?(\d+)")

# '[N]' split-notation marker — strip from product name (영향: 페이퍼샤쉐[1]/[2]/...)
_BRACKET_INDEX = re.compile(r"\s*\[\d+\]\s*")


def parse_product_lines_v2(text: str) -> list[tuple[str, int, int]]:
    """Returns ``[(product_name, total_qty, extra), ...]``.

    ``total_qty``는 본수량 + 여분이며 ``extra``는 여분만. extra/qty > 20%이면
    오인식으로 판단해 ``extra=0`` 으로 리셋.
    """
    if not text:
        return []

    # 1) thousand-separator preprocess
    while _THOUSANDS_COMMA.search(text):
        text = _THOUSANDS_COMMA.sub(r"\1", text)

    # 2) segment by [,/\n;]+
    raw_segments = re.split(r"[,/\n;]+", text)

    # 3) further split each on qty-unit + space + new content
    segments: list[str] = []
    for seg in raw_segments:
        seg = seg.strip()
        if not seg:
            continue
        spliced = _SPLIT_AFTER_QTY_UNIT.sub(r"\1|", seg)
        spliced = _SPLIT_AFTER_BARE_QTY.sub(r" \1|", spliced)
        for sub in spliced.split("|"):
            sub = sub.strip()
            if sub:
                segments.append(sub)

    # 4) parse each
    results: list[tuple[str, int, int]] = []
    for segment in segments:
        extra = 0
        m_extra = _EXTRA_PATTERN.search(segment)
        if m_extra:
            extra = int(m_extra.group(1))
            segment = _EXTRA_PATTERN.sub("", segment).strip()

        qty = 0
        prod = segment
        matched = False
        for p in _QTY_SUFFIX_PATTERNS:
            m = p.search(prod)
            if m:
                qty = int(m.group(1))
                prod = prod[: m.start()].strip()
                matched = True
                break
        if not matched:
            m_ns = _QTY_NOSPACE.search(prod)
            if m_ns:
                qty = int(m_ns.group(2))
                prod = prod[: m_ns.start() + 1].strip()

        # strip '[N]' index markers from product name (normalize for matching)
        prod = _BRACKET_INDEX.sub("", prod).strip()

        # extra sanity: > 20% of qty is suspicious — likely a parse mis-attribution
        if qty > 0 and extra > qty * 0.2:
            extra = 0

        if prod:
            results.append((prod, qty + extra, extra))
    return results


def estimate_shipment_cbm(shipment: dict, lookup: dict) -> dict:
    """Shipment 1건 → 예상 CBM. Returns dict with estimated_cbm·confidence·mode·matched·unmatched.

    ``shipment``는 Airtable record dict (fields key 포함) 또는 fields dict.
    ``lookup``은 ``product_loader.load(headers).lookup`` 또는
    ``cbm_calc.load_product_lookup(headers)`` 결과.
    """
    f = shipment.get("fields", shipment)

    try:
        total_cbm = float(f.get("Total_CBM") or 0)
    except (TypeError, ValueError):
        total_cbm = 0.0
    if total_cbm > 0:
        return {
            "estimated_cbm": round(total_cbm, 4),
            "confidence": 1.0,
            "mode": "실측",
            "matched": [],
            "unmatched": [],
        }

    post_text = (f.get("최종 출고 품목 및 수량") or "").strip()
    pre_text = (f.get("최종 출하 품목") or "").strip()
    text = post_text or pre_text
    mode = "임가공_후_추정" if post_text else "임가공_전_추정"
    if not text:
        return {
            "estimated_cbm": 0.0,
            "confidence": 0.0,
            "mode": "no_text",
            "matched": [],
            "unmatched": [],
        }

    lines = parse_product_lines_v2(text)
    if not lines:
        return {
            "estimated_cbm": 0.0,
            "confidence": 0.0,
            "mode": "no_match",
            "matched": [],
            "unmatched": [],
        }

    total = 0.0
    matched: list[dict] = []
    unmatched: list[str] = []
    scores: list[float] = []
    for name, qty, extra in lines:
        if qty == 0:
            scores.append(0.0)
            unmatched.append(name)
            continue
        key, entry, score = match_product(name, lookup)
        if entry is None:
            scores.append(0.0)
            unmatched.append(name)
            continue
        n_boxes = math.ceil(qty / entry["qty_per_box"])
        total += n_boxes * entry["cbm_per_box"]
        scores.append(score)
        matched.append({
            "name": name,
            "matched_key": key,
            "score": round(score, 3),
            "qty": qty,
            "extra": extra,
            "n_boxes": n_boxes,
            "cbm_per_box": entry["cbm_per_box"],
        })

    matched_count = sum(1 for s in scores if s >= 0.4)
    confidence = matched_count / len(lines) if lines else 0.0
    return {
        "estimated_cbm": round(total, 4),
        "confidence": round(confidence, 2),
        "mode": mode,
        "matched": matched,
        "unmatched": unmatched,
    }


def estimate_shipment_cbm_deterministic(
    project_code: str,
    order_by_project: dict[str, list[tuple[str, float]]],
    lookup: dict,
    shipment_count: dict[str, int],
) -> dict:
    """결정론 출고 CBM. order.굿즈코드→Product[견적코드]→ceil(qty/qpb)*cbm. 퍼지 없음.

    다차 출하 프로젝트(95% 예외)는 partial_skip(중복합산 방지) — 1출하 프로젝트만 기록.
    blank project_code/no order는 호출측에서 기존 퍼지 estimate_shipment_cbm 폴백.
    Returns dict: {estimated_cbm, confidence, mode, matched(codes), unmatched(codes)}.
    """
    if shipment_count.get(project_code, 0) > 1:
        return {"estimated_cbm": 0.0, "confidence": 0.0, "mode": "partial_skip",
                "matched": [], "unmatched": []}
    lines = order_by_project.get(project_code)
    if not lines:
        return {"estimated_cbm": 0.0, "confidence": 0.0, "mode": "no_order",
                "matched": [], "unmatched": []}
    total = 0.0
    matched: list[str] = []
    unmatched: list[str] = []
    for code, qty in lines:
        e = lookup.get(str(code).lower())
        if e and e["cbm_per_box"] > 0 and qty > 0:
            total += math.ceil(qty / e["qty_per_box"]) * e["cbm_per_box"]
            matched.append(code)
        else:
            unmatched.append(code)
    conf = 1.0 if matched and not unmatched else (0.7 if matched else 0.0)
    return {"estimated_cbm": round(total, 4), "confidence": conf,
            "mode": "deterministic", "matched": matched, "unmatched": unmatched}
