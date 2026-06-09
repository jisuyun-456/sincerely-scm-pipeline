"""WMS order/movement 텍스트에서 키를 추출·정규화하는 순수 함수.

- PT#### : 파츠(범용 품목키). order.파츠명 / movement.이동물품에 임베드됨.
- 굿즈명 : order '굿즈 주문 수량 (자동)' = "이름 수량" 형태.
- 소요량 : 주문수량 / 굿즈수량.
"""
from __future__ import annotations

import re

PT_RE = re.compile(r"\b(PT\d{3,6})\b")
_TRAIL_QTY = re.compile(r"\s+(\d[\d,]*)\s*$")
_SERVICE_KW = ("배송", "하차", "퀵", "다마스", "택배", "설치", "용차", "탑차")


def extract_pt(text: str) -> str | None:
    """텍스트 내 첫 PT#### 코드. 없으면 None."""
    if not text:
        return None
    m = PT_RE.search(text)
    return m.group(1) if m else None


def parse_goods(text: str) -> tuple[str, int]:
    """'심볼아크릴트로피 125' → ('심볼아크릴트로피', 125). 수량 없으면 0."""
    s = (text or "").strip()
    m = _TRAIL_QTY.search(s)
    if m:
        return s[: m.start()].strip(), int(m.group(1).replace(",", ""))
    return s, 0


def normalize_goods(name: str) -> str:
    """매칭률 향상용 정규화: [n] 인덱스·(...) 괄호·_접미 제거."""
    s = re.sub(r"\[\d+\]", "", name or "")
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"_.*$", "", s)
    return s.strip()


def is_service(name: str) -> bool:
    """배송·하차 등 비물리 서비스 라인 판별(CBM/BOM 대상 제외)."""
    return any(k in (name or "") for k in _SERVICE_KW)


def compute_soyoryang(order_qty, goods_qty) -> float | None:
    """품목 1개당 소요량 = 주문수량 / 굿즈수량. 산출 불가 시 None."""
    try:
        gq = float(goods_qty)
        if gq <= 0:
            return None
        return round(float(order_qty) / gq, 4)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def resolve_goods_code(row: dict) -> tuple[str | None, str]:
    """order/shipment row → (견적코드, 출처). 우선순위: order.굿즈코드 → (향후 pkg_schedule/crosswalk) → None.
    Returns (code_upper, 'direct'|'none'). Airtable lookup 필드는 list로 올 수 있어 언랩."""
    raw = row.get("굿즈코드 (from sync_itemdb)")
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    code = str(raw or "").strip().upper()
    if code:
        return code, "direct"
    return None, "none"
