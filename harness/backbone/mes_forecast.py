"""mes_forecast — MES 납기일 → 입하 CBM forecast (P3' T6, pure logic, read-only 소비).

MES 작업 row(굿즈·계획수량·납기일 lookup)를 크로스워크(굿즈명→견적코드)와
TMS Product(견적코드→박스 CBM)로 join해 horizon별 입하 예정 CBM을 산출.
박스 수학은 결정론 estimator와 동일: ceil(qty / qty_per_box) × cbm_per_box.
"""
from __future__ import annotations

import math
from datetime import date

from harness.backbone.keys import normalize_goods

EXCLUDE_STATUSES = {"완료"}   # 이미 산출 완료 — 입하 forecast 대상 아님


def _first(v):
    """multipleLookupValues unwrap: [x] → x."""
    if isinstance(v, list):
        return v[0] if v else None
    return v


def build_inbound_forecast(
    mes_rows: list[dict],
    name_to_code: dict[str, str],
    product_by_code: dict[str, tuple[float, float]],   # code -> (qty_per_box, cbm_per_box)
    today: date,
    horizons: tuple[int, ...] = (7, 14),
) -> dict:
    """Returns by_horizon(누적)·by_date·join 카운터."""
    by_horizon = {h: 0.0 for h in horizons}
    by_date: dict[str, float] = {}
    n = {"n_total": 0, "n_excluded_status": 0, "n_no_date": 0,
         "n_unmatched_code": 0, "n_no_cbm": 0, "n_past_due": 0, "n_joined": 0}

    for f in mes_rows:
        n["n_total"] += 1
        if str(f.get("작업 상태") or "") in EXCLUDE_STATUSES:
            n["n_excluded_status"] += 1
            continue
        goods = str(_first(f.get("굿즈")) or "").strip()
        code = name_to_code.get(normalize_goods(goods)) if goods else None
        if not code:
            n["n_unmatched_code"] += 1
            continue
        due_raw = str(_first(f.get("납기일")) or "").strip()
        if not due_raw:
            n["n_no_date"] += 1
            continue
        try:
            due = date.fromisoformat(due_raw[:10])
        except ValueError:
            n["n_no_date"] += 1
            continue
        if due < today:
            n["n_past_due"] += 1
            continue
        prod = product_by_code.get(code)
        qty = float(_first(f.get("계획수량")) or 0)
        if not prod or qty <= 0 or prod[0] <= 0:
            n["n_no_cbm"] += 1
            continue
        qpb, cbm_per_box = prod
        cbm = math.ceil(qty / qpb) * cbm_per_box
        n["n_joined"] += 1
        days = (due - today).days
        for h in horizons:
            if days <= h:
                by_horizon[h] += cbm
        by_date[due.isoformat()] = by_date.get(due.isoformat(), 0.0) + cbm

    by_horizon = {h: round(v, 4) for h, v in by_horizon.items()}
    return {"by_horizon": by_horizon, "by_date": by_date, **n}
