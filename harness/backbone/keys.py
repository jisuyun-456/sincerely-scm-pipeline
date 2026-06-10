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


def extract_pts(text) -> list[str]:
    """텍스트 내 모든 PT#### 코드 (중복 제거, 등장 순서 유지)."""
    if not text:
        return []
    return list(dict.fromkeys(PT_RE.findall(str(text))))


def build_mes_crosswalk_rows(
    mes_parts: set[str],
    mes_goods: dict[str, str],
    existing_keys: set[str],
    wms_item_keys: set[str],
    product_codes: set[str],
) -> tuple[list[dict], dict]:
    """MES 키 → WMS_KeyCrosswalk 신규행 + 매칭 stats. INSERT-only(기존 표준키 스킵).

    mes_goods: MES 제품명 → 굿즈코드(by DB). product_codes: TMS 견적코드(lower).
    행 출처='mes_crosswalk' 태깅 (rollback 식별 마커).
    """
    rows: list[dict] = []
    stats = {"parts_total": len(mes_parts), "parts_already": 0, "parts_in_wms": 0,
             "parts_new": 0, "goods_total": len(mes_goods), "goods_already": 0,
             "goods_no_code": 0, "goods_code_in_tms": 0, "goods_new": 0}
    for pt in sorted(mes_parts):
        in_wms = pt in wms_item_keys
        if in_wms:
            stats["parts_in_wms"] += 1  # 해소율 집계는 INSERT 여부와 무관 (재실행 안정)
        if pt in existing_keys:
            stats["parts_already"] += 1
            continue
        stats["parts_new"] += 1
        rows.append({
            "표준키": pt, "키유형": "파츠", "TMS_견적코드": "",
            "WMS_아이템코드": pt if in_wms else "", "MES_파츠코드": pt,
            "매칭방식": "정확", "매칭신뢰도": 1.0 if in_wms else 0.5,
            "검증상태": "확정" if in_wms else "미검증", "출처": "mes_crosswalk",
        })
    for name in sorted(mes_goods):
        code = str(mes_goods[name] or "").strip().upper()
        if name in existing_keys:
            stats["goods_already"] += 1
            continue
        if not code:
            stats["goods_no_code"] += 1
            continue
        in_tms = code.lower() in product_codes
        if in_tms:
            stats["goods_code_in_tms"] += 1
        stats["goods_new"] += 1
        rows.append({
            "표준키": name, "키유형": "굿즈", "TMS_견적코드": code,
            "WMS_아이템코드": "", "MES_파츠코드": "",
            "매칭방식": "정확" if in_tms else "수기",
            "매칭신뢰도": 1.0 if in_tms else 0.5,
            "검증상태": "확정" if in_tms else "보류", "출처": "mes_crosswalk",
        })
    return rows, stats


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
