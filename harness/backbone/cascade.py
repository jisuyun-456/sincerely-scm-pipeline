"""P6a order-trigger 캐스케이드 코어 — 순수 함수만 (IO는 scripts/backbone/order_cascade.py).

설계 SSOT: docs/superpowers/specs/2026-06-11-cbm-p6-order-cascade-design.md
단위 = (PNA, 굿즈) — 전파ID 규약 {project_code}_{goods_name} (ledger.py 준수).
스테이지 실패는 부분/끊김 마킹 후 계속 — abort 없음 (spec §5).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from harness.backbone.keys import (
    PNA_RE,
    compute_soyoryang,
    extract_pts,
    goods_base,
    is_service,
    normalize_goods,
    parse_goods,
    resolve_goods_code,
)
from harness.backbone.ledger import build_propagation_row
from harness.backbone.mes_forecast import build_inbound_forecast
from harness.backbone.mrp import net_requirements
from harness.backbone.product_alias import remap_lines
from harness.backbone.storage import STOCK_TYPE_INCLUDE, ZONE_TYPE_INCLUDE
from harness.dispatch.cbm_estimator import estimate_shipment_cbm_deterministic
from harness.dispatch.wave_assigner import DRIVER_LIMITS
from harness.tms_settlement.config import round_up_500

_log = logging.getLogger(__name__)

REPROCESS_WINDOW_DAYS = 14          # spec §5 — 부분/끊김 재처리 윈도우 = forward 감지 윈도우
ROAD_KM_BAND = (10.0, 60.0)         # S6 주소 미확정 시 수도권 도로거리 추정 밴드 (km)
_NUM_TOL = 1e-4                     # S7 수치 변동 판정 허용오차
ZONE_TYPE_STAGING = "INBOUND_STAGING"   # S4 입하장 — storage.py ZONE_TYPE_INCLUDE(STORAGE)와 별개 zone

# S3 표준 M/H 상수 — scripts/mh_backfill_to_ibsa.py v2026-05-iter22와 동일 값 핀
# (scripts/는 패키지가 아니라 import 불가 — 값 변경 시 양쪽 동기 필수)
_PFD = 1.15
_RECV_MIN_PER_CBM, _RECV_FLOOR_MIN, _RECV_CAP_MIN = 4.0, 0.5, 5.0
_QC_MIN, _QC_DOC_MIN = 2.5, 1.5
_PUTAWAY_BASE_MIN, _PUTAWAY_CAP_MIN, _PUTAWAY_PER_CBM_MIN = 3.0, 5.0, 7.0
_SAMPLE_QC_MIN = 2.5
_COUNTING_FLOOR_MIN, _COUNTING_CAP_MIN, _COUNTING_PER_QTY = 2.0, 7.0, 100.0

# S7 idempotency 비교 대상 (전파ID·shipment_id·cascade_실행ID·생성시각 제외)
CONTENT_FIELDS = (
    "전파상태", "고객주문수량", "자재소요_요약", "추정_CBM_m3",
    "부족자재_요약", "입하CBM_예상_m3", "MH_예상_h", "창고적재_예상",
    "wave_프리뷰", "운임_예상범위",
)


def _n(x) -> float:
    try:
        return float(str(x).replace(",", "") or 0)
    except (ValueError, TypeError):
        return 0.0


def _first(v):
    return v[0] if isinstance(v, list) and v else ("" if isinstance(v, list) else v)


@dataclass
class CascadeUnit:
    pna: str
    goods_name: str
    goods_qty: int
    rows: list[dict] = field(default_factory=list)   # order record fields dicts
    created_max: str = ""                            # ISO createdTime (record metadata)


@dataclass
class CascadeContext:
    """run_unit이 소비하는 전부-사전적재 데이터 (순수성 보장)."""
    pkg_map: dict
    product_lookup: dict
    kit_lookup: dict
    shipment_count: dict
    bom_fields: list[dict]
    stock_rows: list[dict]              # storage.py row shape {pt,stock,warehouse,zone_type,stock_type}
    part_cbm_by_pt: dict[str, float]    # part_cbm_for_pt 4-tier 해소 결과
    mes_rows: list[dict]
    name_to_code: dict[str, str]
    product_by_code: dict[str, tuple]
    max_staging_cbm: float | None       # Σ WMS_Location.Max_CBM (현재 A1-IB-001 57.6)
    rates: dict                         # tms_settlement.config.rates_for(today)
    today: date


# ─── S0 감지 ─────────────────────────────────────────────────────

def collect_units(order_records: list[dict], now: datetime,
                  window_days: int = REPROCESS_WINDOW_DAYS) -> list[CascadeUnit]:
    """order 미러 → (PNA, 굿즈) 단위 그룹핑. forward-only: createdTime 윈도우 내만."""
    groups: dict[tuple[str, str], CascadeUnit] = {}
    for rec in order_records:
        f = rec.get("fields", {})
        m = PNA_RE.search(str(_first(f.get("project_code")) or ""))
        goods_name, goods_qty = parse_goods(str(f.get("굿즈 주문 수량 (자동)") or ""))
        if not m or not goods_name or is_service(goods_name):
            continue
        key = (m.group(0), goods_name)
        u = groups.get(key)
        if u is None:
            u = groups[key] = CascadeUnit(pna=key[0], goods_name=key[1], goods_qty=0)
        u.rows.append(f)
        u.goods_qty = max(u.goods_qty, int(goods_qty or 0))
        created = str(rec.get("createdTime") or "")
        if created > u.created_max:
            u.created_max = created
    cutoff = now - timedelta(days=window_days)
    out = []
    for u in sorted(groups.values(), key=lambda x: (x.pna, x.goods_name)):
        try:
            created_dt = datetime.fromisoformat(u.created_max.replace("Z", "+00:00"))
        except ValueError:
            _log.warning("collect_units: createdTime 파싱 불가 — %s/%s 스킵 "
                         "(매 tick 재시도 불가, 점검 필요)", u.pna, u.goods_name)
            continue
        if created_dt >= cutoff:
            out.append(u)
    return out


def latest_ledger_by_pid(ledger_records: list[dict]) -> dict[str, dict]:
    """전파ID별 최신행 (createdTime max) — 소비자 계약 spec §3.1."""
    latest: dict[str, dict] = {}
    for rec in ledger_records:
        pid = str(rec.get("fields", {}).get("전파ID") or "")
        if not pid:
            continue
        cur = latest.get(pid)
        if cur is None or str(rec.get("createdTime") or "") > str(cur.get("createdTime") or ""):
            latest[pid] = rec
    return latest


# ─── S1+S5 어댑터 (grill Q2 — silent-unmatched 방지, 단위테스트 필수) ──

def build_order_lines(unit: CascadeUnit, pkg_map: dict) -> dict:
    """order 행 → estimate_shipment_cbm_deterministic 입력 계약 [(code, qty)].

    replay_outbound_cbm.build_inputs와 동일 합산 의미론 (코드별 주문수량 Σ).
    """
    counter: dict[str, float] = {}
    src_counts = {"direct": 0, "pkg": 0, "none": 0}
    pts: list[str] = []
    for f in unit.rows:
        code, src = resolve_goods_code(f, pkg_map)
        src_counts[src] = src_counts.get(src, 0) + 1
        if code:
            counter[code] = counter.get(code, 0.0) + _n(f.get("주문수량"))
        for pt in extract_pts(f.get("파츠명")):
            if pt not in pts:
                pts.append(pt)
    lines = sorted(counter.items())
    code = max(counter, key=counter.get) if counter else None
    return {"lines": lines, "code": code, "src_counts": src_counts, "pts": pts}


# ─── S2 MRP ──────────────────────────────────────────────────────

def stock_by_pt(stock_rows: list[dict]) -> dict[str, float]:
    """현재고 — P3' storage.py와 동일 필터(STORAGE·UNRESTRICTED), 새 해석 금지."""
    out: dict[str, float] = {}
    for r in stock_rows:
        if (r.get("zone_type") == ZONE_TYPE_INCLUDE
                and r.get("stock_type") == STOCK_TYPE_INCLUDE):
            pt = r.get("pt") or ""
            if pt:
                out[pt] = out.get(pt, 0.0) + _n(r.get("stock"))
    return out


def select_bom_rows(pna: str, goods_name: str, bom_fields: list[dict],
                    unit: CascadeUnit | None = None) -> tuple[list[dict], int]:
    """(PNA, 굿즈)의 BOM — PT별 검증완료행 우선, 없으면 order 유도 폴백.

    Returns (rows [{소품목_PT, 소요량_개당}], n_verified).
    """
    def _collect(name_match) -> tuple[dict, set]:
        by_pt: dict[str, dict] = {}
        verified: set[str] = set()
        for f in bom_fields:
            m = PNA_RE.search(str(f.get("프로젝트코드") or ""))
            if not m or m.group(0) != pna:
                continue
            if not name_match(str(f.get("모품목_굿즈명") or "")):
                continue
            pt = str(f.get("소품목_PT") or "")
            if not pt:
                continue
            is_verified = f.get("검증상태") == "검증완료"
            if pt not in by_pt or (is_verified and pt not in verified):
                by_pt[pt] = {"소품목_PT": pt, "소요량_개당": f.get("소요량_개당")}
                if is_verified:
                    verified.add(pt)
        return by_pt, verified

    by_pt, verified = _collect(lambda nm: nm == goods_name)
    if not by_pt:
        # V3.1 — 재제작/추가제작 주문은 굿즈명에 접미가 붙어 베이스 BOM과 불일치.
        # 베이스명 폴백 (검증 승급 없음 — 재제작 BOM이 베이스와 다를 수 있어 보수적).
        base = goods_base(goods_name)
        if base != goods_name:
            by_pt, _v = _collect(lambda nm: goods_base(nm) == base)
            verified = set()   # 베이스 매칭은 미검증 취급
    if by_pt:
        rows = [by_pt[pt] for pt in sorted(by_pt)]
        return rows, len(verified)
    if unit is not None and unit.goods_qty > 0:
        for f in unit.rows:
            for pt in extract_pts(f.get("파츠명"))[:1]:
                if pt not in by_pt:
                    soyo = compute_soyoryang(_n(f.get("주문수량")), unit.goods_qty)
                    by_pt[pt] = {"소품목_PT": pt, "소요량_개당": soyo}
        return [by_pt[pt] for pt in sorted(by_pt)], 0
    return [], 0


def shortage_text(reqs: list[dict]) -> str:
    """spec §3.1 부족자재_요약 — 'PT0123×500(재고 200/소요 700)' 줄 단위."""
    return "\n".join(
        f"{r['pt']}×{r['shortfall']}(재고 {r['stock']:g}/소요 {r['gross']})"
        for r in reqs if r["shortfall"] > 0)


# ─── S3 입하 CBM·M/H ─────────────────────────────────────────────

def mh_for_inbound(cbm: float, qty: int) -> float:
    """입하 1건(입하+검수+입고) 표준 M/H — mh_backfill_to_ibsa v2026-05-iter22 동일식."""
    recv = min(_RECV_CAP_MIN, max(_RECV_FLOOR_MIN, cbm * _RECV_MIN_PER_CBM)) * _PFD
    qc = (_QC_MIN + _QC_DOC_MIN) * _PFD
    extra = min(_PUTAWAY_CAP_MIN - _PUTAWAY_BASE_MIN,
                cbm * _PUTAWAY_PER_CBM_MIN) if cbm > 0 else 0.0
    movement = (_PUTAWAY_BASE_MIN + extra) * _PFD
    counting = max(_COUNTING_FLOOR_MIN,
                   min(_COUNTING_CAP_MIN, _COUNTING_FLOOR_MIN + qty / _COUNTING_PER_QTY))
    return round((recv + qc + movement + _SAMPLE_QC_MIN + counting) / 60.0, 2)


def stage_inbound(reqs: list[dict], part_cbm_by_pt: dict[str, float]) -> dict:
    """부족분 PT별 입하 CBM·M/H. CBM 미산출 PT는 uncovered로 마킹 후 계속."""
    inbound_cbm = 0.0
    mh = 0.0
    uncovered: list[str] = []
    for r in reqs:
        short = r["shortfall"]
        if short <= 0:
            continue
        cbm_unit = part_cbm_by_pt.get(r["pt"]) or 0.0
        if cbm_unit <= 0:
            uncovered.append(r["pt"])
            continue
        cbm = cbm_unit * short
        inbound_cbm += cbm
        mh += mh_for_inbound(cbm, short)
    return {"inbound_cbm": round(inbound_cbm, 4), "mh_hours": round(mh, 2),
            "uncovered": uncovered}


def mes_timeline(goods_code: str | None, mes_rows: list[dict], name_to_code: dict,
                 product_by_code: dict, today: date) -> dict:
    """생산중 파츠 납기 forecast — 해당 굿즈코드 MES 행만 P3' build_inbound_forecast 재사용."""
    if not goods_code or not mes_rows:
        return {}
    rows = [r for r in mes_rows
            if name_to_code.get(normalize_goods(str(_first(r.get("굿즈")) or "")))
            == goods_code]
    if not rows:
        return {}
    return build_inbound_forecast(rows, name_to_code, product_by_code, today)["by_date"]


# ─── S4 창고 투영 ────────────────────────────────────────────────

def staging_projection(stock_rows: list[dict], part_cbm_by_pt: dict[str, float],
                       inbound_cbm: float, max_staging_cbm: float | None,
                       ) -> tuple[str, bool]:
    """입하장 적재 투영 — spec §3.1 '창고적재_예상' (staging now%→after%)."""
    if not max_staging_cbm or max_staging_cbm <= 0:
        return f"부분: Max_CBM 미실측 (입하 +{inbound_cbm:.1f}m³)", False
    now_cbm = sum(
        _n(r.get("stock")) * (part_cbm_by_pt.get(r.get("pt") or "") or 0.0)
        for r in stock_rows
        if r.get("zone_type") == ZONE_TYPE_STAGING
        and r.get("stock_type") == STOCK_TYPE_INCLUDE)
    now_pct = now_cbm / max_staging_cbm * 100
    after_pct = (now_cbm + inbound_cbm) / max_staging_cbm * 100
    return (f"staging {now_pct:.1f}%→{after_pct:.1f}% (Max {max_staging_cbm:g}m³)",
            True)


# ─── S5 배차 프리뷰 (capacity-feasibility — assign_waves dry-call 금지) ──

def wave_preview(est_cbm: float) -> tuple[str, bool]:
    if est_cbm <= 0:
        return "부분: 출하CBM 미산출", False
    feasible = [w for w in ("W1", "W2", "W3")
                if est_cbm <= DRIVER_LIMITS[w]["max_cbm"]]
    if not feasible:
        return (f"용량 초과 (CBM {est_cbm:.2f} > W3 max "
                f"{DRIVER_LIMITS['W3']['max_cbm']}) — 분할/외주 검토", False)
    caps = "/".join(f"{DRIVER_LIMITS[w]['max_cbm']:g}" for w in feasible)
    return f"{'/'.join(feasible)} 가능 (CBM {est_cbm:.2f} ≤ max {caps})", True


# ─── S6 운임 프리뷰 ──────────────────────────────────────────────

def fare_preview(est_cbm: float, rates: dict) -> tuple[str, bool]:
    """order 미러에 주소 없음 → 수도권 도로거리 밴드(ROAD_KM_BAND) 요율 범위."""
    if est_cbm <= 0:
        return "부분: 출하CBM 미산출", False
    lo = round_up_500(rates["park_base"] + rates["park_km"] * ROAD_KM_BAND[0])
    hi = round_up_500(rates["park_base"] + rates["park_km"] * ROAD_KM_BAND[1])
    return f"₩{lo:,}~₩{hi:,} (주소 미확정·수도권 거리대)", True


# ─── S7 idempotency ──────────────────────────────────────────────

def decide_insert(row: dict, prior_fields: dict | None) -> str:
    """spec §5 — 전파ID별 최신행 대비 상태·수치 변동 시에만 신규 INSERT.

    Airtable은 빈 문자열 필드를 응답에서 누락 → ''와 None 동일 취급
    (P6b VC-2 실측 — 미정규화 시 BOM 없는 단위가 매 run 재INSERT churn).
    수치 0은 실값이라 누락과 동일 취급하지 않는다.
    """
    if prior_fields is None:
        return "new"
    for k in CONTENT_FIELDS:
        a, b = row.get(k), prior_fields.get(k)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            if abs(a - b) > _NUM_TOL:
                return "changed"
        elif (None if a == "" else a) != (None if b == "" else b):
            return "changed"
    return "unchanged"


# ─── 단위 실행 (S1~S7 — 부분/끊김 마킹 후 계속) ──────────────────

def run_unit(unit: CascadeUnit, prior_fields: dict | None, ctx: CascadeContext,
             run_id: str) -> dict:
    """(PNA,굿즈) 1단위 S1~S7 실행 → ledger row + action.

    수량 기준이 2개임에 주의 (의도된 분리 — code review 2026-06-11):
    - 고객주문수량(MRP gross) = parse_goods 굿즈수량 (예: '트로피 125' → 125)
    - 추정_CBM_m3(S5 출하) = 코드별 주문수량 Σ (replay_outbound_cbm 의미론 미러)
    멀티 파츠행 주문은 후자가 더 클 수 있어 행 내 CBM/수량 비율이 달라 보일 수 있음.
    """
    reasons: list[str] = []
    lines_info = build_order_lines(unit, ctx.pkg_map)
    # V2 견적코드 정합 — WMS sync_item 코드를 TMS Product 등록코드(권위 스펙)로 재매핑.
    # alias(동일명 쌍둥이) + 사이즈군(굿즈명 사이즈 파싱). 미해소는 원본 유지 → S5 정직 미산출.
    # ※ lines_info["code"]는 갱신하지 않음 — mes_timeline은 name_to_code(WMS코드 키스페이스)를
    #    소비하므로 원본 WMS 코드 유지가 필요 (registered 코드로 덮으면 MES forecast 무음 실패).
    lines_info["lines"] = remap_lines(lines_info["lines"], unit.goods_name,
                                      ctx.product_lookup)
    oqty = unit.goods_qty or int(max(
        (_n(f.get("주문수량")) for f in unit.rows), default=0))

    if not lines_info["lines"]:
        reasons.append("S1 키해소 실패 (굿즈코드 미해소 — direct·pkg 모두 없음)")
        row = build_propagation_row(unit.pna, unit.goods_name, oqty, [], None, "",
                                    status="끊김", cascade_run_id=run_id)
        return {"row": row, "action": decide_insert(row, prior_fields),
                "status": "끊김", "reasons": reasons, "mes_by_date": {},
                "src_counts": lines_info["src_counts"]}

    bom_rows, n_verified = select_bom_rows(unit.pna, unit.goods_name,
                                           ctx.bom_fields, unit=unit)
    reqs: list[dict] = []
    if not bom_rows:
        reasons.append("S2 BOM 행 없음 (WMS_BOM·order 유도 모두 실패)")
    else:
        reqs = net_requirements(bom_rows, oqty, stock_by_pt(ctx.stock_rows))

    inb = stage_inbound(reqs, ctx.part_cbm_by_pt)
    if inb["uncovered"]:
        reasons.append("S3 part CBM 미산출 PT: " + ", ".join(inb["uncovered"]))

    stag, ok4 = staging_projection(ctx.stock_rows, ctx.part_cbm_by_pt,
                                   inb["inbound_cbm"], ctx.max_staging_cbm)
    if not ok4:
        reasons.append("S4 " + stag)

    est = estimate_shipment_cbm_deterministic(
        unit.pna, {unit.pna: lines_info["lines"]}, ctx.product_lookup,
        ctx.shipment_count, kit_lookup=ctx.kit_lookup)
    est_cbm = est["estimated_cbm"]
    if est_cbm <= 0:
        reasons.append(f"S5 출하CBM 미산출 (mode={est['mode']}, "
                       f"unmatched={est['unmatched']})")

    wv, ok5 = wave_preview(est_cbm)
    if est_cbm > 0 and not ok5:
        reasons.append("S5 " + wv)
    fare, _ok6 = fare_preview(est_cbm, ctx.rates)

    mes = mes_timeline(lines_info["code"], ctx.mes_rows, ctx.name_to_code,
                       ctx.product_by_code, ctx.today)

    status = "완결" if not reasons else "부분"
    cbm_per_unit = est_cbm / oqty if est_cbm > 0 and oqty > 0 else None
    shortage = (shortage_text(reqs) or "부족분 없음") if bom_rows else None
    row = build_propagation_row(
        unit.pna, unit.goods_name, oqty, bom_rows, cbm_per_unit, "",
        shortage_summary=shortage,
        inbound_cbm_m3=inb["inbound_cbm"] if bom_rows else None,
        mh_hours=inb["mh_hours"] if bom_rows else None,
        storage_projection=stag, wave_preview=wv, fare_range=fare,
        cascade_run_id=run_id, status=status)
    return {"row": row, "action": decide_insert(row, prior_fields),
            "status": status, "reasons": reasons, "mes_by_date": mes,
            "src_counts": lines_info["src_counts"]}
