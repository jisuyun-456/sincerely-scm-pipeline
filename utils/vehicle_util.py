"""차량 적재율(util) 단일 진실원 — 하드코딩 차량 정원 dict 금지 (P2 A3, 2026-06-24).

문제: scripts/tms_weekly_runner.TRUCK_CAPACITY_M3 · pages/generate_scm_report.VEHICLE_CBM ·
구 스펙이 서로 다른 차량 정원을 하드코딩 → 라이브 차량한도(이장훈 4.5)와 40~70%
어긋남(이장훈 7.6 / 5.4). 결과적으로 주간 AutoResearch 리포트와 Pages 대시보드가
서로 다른, 그리고 둘 다 틀린 적재율을 게시하던 상태였다.

해결:
- 차량 정원(차량한도)은 Shipment lookup을 라이브로 읽어 단일 capacity map 구성.
- per-dispatch 적재율은 배차일지 차량이용률(%) formula(=Total_CBM/차량한도)를 권위로 사용.

데이터 품질(2026-06-24 라이브): 배차일지 239행 중 0(미적재) 82 · >100%(오버부킹) 57,
max 544%. raw mean(65.6%)은 오버부킹에 왜곡됨 → median(loaded) + under/over 플래그로 보고.
"""
from __future__ import annotations

import re
import statistics

SHIP_PARTNER_FLD = "fldHZ7yMT3KEu2gSj"   # 배송파트너 (lookup → 기사명)
SHIP_CAP_FLD = "fld9ZixilQySf9taF"       # 차량한도 (lookup, m³) — 정원 SSOT

# 라이브 차량한도 미수신(network/빈값/PAT부재) 시에만 쓰는 fallback (2026-06-24 라이브 실측).
# 절대 권위 아님 — 정상 경로는 fetch_live_capacities()의 Airtable 값.
FALLBACK_CAP: dict[str, float] = {"이장훈": 4.5, "조희선": 7.616, "박종성": 9.486}

_PAREN = re.compile(r"\(([^)]+)\)")


def _as_float(x):
    try:
        if x is None or x == "":
            return None
        return float(str(x).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _first(v):
    """lookup 값(list / valuesByLinkedRecordId dict / scalar) → 첫 스칼라."""
    if isinstance(v, list):
        return v[0] if v else None
    if isinstance(v, dict):
        for vs in v.get("valuesByLinkedRecordId", {}).values():
            if vs:
                return vs[0] if isinstance(vs, list) else vs
        return None
    return v


def bare_driver(name) -> str:
    """'신시어리 기사님 (이장훈)' · '신시어리 (이장훈)' → '이장훈' (괄호 안 토큰)."""
    s = str(name or "")
    m = _PAREN.search(s)
    return (m.group(1) if m else s).strip()


def capacity_for(name, cap_map, default=None):
    """기사명(어떤 표기든) → 라이브 차량한도. bare 정확매칭 후 substring 폴백."""
    bare = bare_driver(name)
    if bare in cap_map:
        return cap_map[bare]
    for k, v in cap_map.items():
        if k and (k in bare or bare in k):
            return v
    return default


def aggregate_capacity(pairs) -> dict[str, float]:
    """(기사명, 차량한도) iterable → {bare기사: 최대 정원}. 0/None 무시."""
    out: dict[str, float] = {}
    for name, cap in pairs:
        c = _as_float(cap)
        if c is None or c <= 0:
            continue
        b = bare_driver(name)
        if b:
            out[b] = max(out.get(b, 0.0), round(c, 3))
    return out


def summarize_util(values, under=50.0, over=100.0) -> dict:
    """차량이용률(%) 값 리스트 → median 중심 분포 + under/over 플래그.

    n_zero=미적재(≤0, 배차 미실차), loaded=실적재(>0). headline=median(loaded).
    mean_capped=각 값을 over로 상한 후 평균(오버부킹 왜곡 차단). raw mean은 참고용.
    """
    vals = [v for v in (_as_float(x) for x in values) if v is not None]
    loaded = [v for v in vals if v > 0]
    n_zero = sum(1 for v in vals if v <= 0)
    n_under = sum(1 for v in loaded if v < under)
    n_over = sum(1 for v in loaded if v > over)
    capped = [min(v, over) for v in loaded]
    return {
        "n": len(vals),
        "n_loaded": len(loaded),
        "n_zero": n_zero,
        "n_under": n_under,
        "n_over": n_over,
        "median": round(statistics.median(loaded), 1) if loaded else 0.0,
        "mean_capped": round(statistics.fmean(capped), 1) if capped else 0.0,
        "mean_raw": round(statistics.fmean(loaded), 1) if loaded else 0.0,
        "under_pct": round(n_under / len(loaded) * 100, 1) if loaded else 0.0,
        "over_pct": round(n_over / len(loaded) * 100, 1) if loaded else 0.0,
    }


def capacities_from_shipments(records, *, partner_fld=SHIP_PARTNER_FLD,
                              cap_fld=SHIP_CAP_FLD, fallback=True) -> dict[str, float]:
    """이미 fetch된 Shipment records(returnFieldsByFieldId)에서 기사별 차량한도 집계.

    별도 Airtable 스캔 없이 호출자의 윈도우 records를 재사용(16k 전수 스캔 회피).
    윈도우에 정원 정보가 0건이면 fallback=FALLBACK_CAP (라이브 실측 2026-06-24).
    """
    pairs = []
    for rec in records or []:
        f = rec.get("fields", {}) if isinstance(rec, dict) else {}
        name = _first(f.get(partner_fld))
        cap = _first(f.get(cap_fld))
        if name is not None and cap is not None:
            pairs.append((name, cap))
    caps = aggregate_capacity(pairs)
    if not caps and fallback:
        return dict(FALLBACK_CAP)
    return caps
