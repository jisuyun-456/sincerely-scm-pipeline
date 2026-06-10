"""WMS order/movement 텍스트에서 키를 추출·정규화하는 순수 함수.

- PT#### : 파츠(범용 품목키). order.파츠명 / movement.이동물품에 임베드됨.
- 굿즈명 : order '굿즈 주문 수량 (자동)' = "이름 수량" 형태.
- 소요량 : 주문수량 / 굿즈수량.
"""
from __future__ import annotations

import re

PT_RE = re.compile(r"\b(PT\d{3,6})\b")
PNA_RE = re.compile(r"PNA\d+")  # replay_outbound_cbm.py와 동일 패턴 (PNA뒤 '_'는 \b 미매칭)
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


def resolve_goods_code(
    row: dict, pkg_goods_by_project: dict[str, str] | None = None
) -> tuple[str | None, str]:
    """order/shipment row → (견적코드, 출처). 우선순위: order.굿즈코드 → pkg_schedule 폴백 → None.
    Returns (code_upper, 'direct'|'pkg'|'none'). Airtable lookup 필드는 list로 올 수 있어 언랩."""
    raw = row.get("굿즈코드 (from sync_itemdb)")
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    code = str(raw or "").strip().upper()
    if code:
        return code, "direct"
    if pkg_goods_by_project:
        m = PNA_RE.search(str(row.get("project_code") or ""))
        if m and m.group(0) in pkg_goods_by_project:
            return pkg_goods_by_project[m.group(0)].strip().upper(), "pkg"
    return None, "none"


def build_pkg_goods_map(pkg_rows, name_to_code: dict[str, str]) -> dict[str, str]:
    """pkg_schedule fields-dict 목록 + sync_item 굿즈명→굿즈코드 → {PNA: 견적코드}.
    pkg_schedule에는 굿즈코드 필드가 없어 굿즈명을 sync_item으로 브릿지.
    다중 코드 프로젝트는 order行 귀속 불가 → 제외(단일 코드만)."""
    by_pna: dict[str, set[str]] = {}
    for f in pkg_rows:
        m = PNA_RE.search(str(f.get("프로젝트 코드 (PK) (from project)") or ""))
        if not m:
            continue
        codes = by_pna.setdefault(m.group(0), set())
        for src in ("주문 굿즈 리스트 (자동) (from project)", "단품 굿즈 품목 및 수량"):
            for part in re.split(r"[,\n/]+", str(f.get(src) or "")):
                name = normalize_goods(parse_goods(part.strip())[0])
                if name and not is_service(name) and name in name_to_code:
                    codes.add(name_to_code[name])
    return {pna: next(iter(c)) for pna, c in by_pna.items() if len(c) == 1}
