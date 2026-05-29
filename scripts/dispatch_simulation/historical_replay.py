"""
scripts/dispatch_simulation/historical_replay.py
─────────────────────────────────────────────────────────────────────────────
배차 자동화 시뮬레이션 — 2025-01-01 ~ 2026-05-27

실제 배차 내역(Airtable)에 wave_assigner 알고리즘을 소급 적용해 운임 차이를 계산.

비교 방법:
  [실제] 실제 배송파트너 기준 정산 공식 적용 (이장훈/조희선/박종성 일별 정액 + 로젠/고고엑스 실비)
  [시뮬] assign_waves() 출력 기준 동일 정산 공식 적용

Usage:
  py -m scripts.dispatch_simulation.historical_replay
  py -m scripts.dispatch_simulation.historical_replay --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from harness._core.geo import estimate_dest_coord, haversine_km
from harness.dispatch.wave_assigner import DRIVER_LIMITS, Shipment, assign_waves
from harness.tms_settlement.config import (
    DRIVER_CHO,
    DRIVER_LEE,
    DRIVER_PARK,
    ORIGINS,
    RATE_HISTORY,
    rates_for,
    round_up_500,
)


def _rates_for_sim(date_iso: str) -> dict:
    """rates_for() wrapper: falls back to oldest known rate for pre-RATE_HISTORY dates."""
    try:
        return rates_for(date_iso)
    except ValueError:
        return RATE_HISTORY[-1]  # RATE_HISTORY is newest-first; last = oldest

# ── Airtable 상수 ─────────────────────────────────────────────────────────────
BASE_ID = "app4x70a8mOrIKsMf"
TBL_SHIPMENT = "tbllg1JoHclGYer7m"
AIRTABLE_PAT = os.environ.get("AIRTABLE_PAT", "")
HEADERS = {"Authorization": f"Bearer {AIRTABLE_PAT}", "Content-Type": "application/json"}

# ── 필드 ID ───────────────────────────────────────────────────────────────────
F_DATE        = "fldQvmEwwzvQW95h9"   # 출하확정일
F_CBM         = "fldJ9DHjwoRyeUEqE"   # Total_CBM (backfilled)
F_CBM_EST     = "fldaP8D9AM8CHEZ2o"   # estimated_cbm (cbm_estimator fallback)
F_ZONE        = "fldp6haTDFzzF5C74"   # 구간유형
F_FARE        = "fldRT95SC88KSBATT"   # 운송비용 (실제)
F_UNLOAD      = "fldxmAZrBGqS7sQoL"  # 상하차비용 (실제)
F_PARTNER     = "fldM2u6RwLRrO7ymW"  # 배송파트너 (multipleRecordLinks)
F_PARTNER_NAME = "fldHZ7yMT3KEu2gSj" # 배송파트너명 (lookup)
F_SLOT        = "fldcSrlxCngYQHtSV"  # 배송슬롯
F_DEST_ADDR   = "fldyJHUh9gN44Ggnh"  # 수령인(주소)
F_ORIGIN_ADDR = "fldb24I9EQ2KPXv6S"  # 출고지 주소
F_BOX_TEXT    = "fldTjLDmw5sNGszeD"  # 최종 외박스 수량 값 (박종성 상하차비)

FETCH_FIELDS = [
    F_DATE, F_CBM, F_CBM_EST, F_ZONE, F_FARE, F_UNLOAD, F_PARTNER, F_PARTNER_NAME,
    F_SLOT, F_DEST_ADDR, F_ORIGIN_ADDR, F_BOX_TEXT,
]

# ── 시뮬레이션 파라미터 ────────────────────────────────────────────────────────
DATE_FROM = "2025-01-01"
DATE_TO   = "2026-05-27"

# 외부 운임 단가
LOGEN_PER_CBM   = 12_000  # 로젠택배 CBM당
GOGOX_PER_SHIP  = 15_000  # 고고엑스 건당 (flat)

# 박종성 기본 origin (에이원지식산업센터 우선)
DEFAULT_ORIGIN  = ORIGINS.get("에이원지식산업센터", (37.5477, 127.0446))
PARK_AVG_KM     = 25.0   # 좌표 추정 불가 시 fallback 거리

# 드라이버 ID 세트 (known internal drivers)
KNOWN_DRIVERS = {DRIVER_LEE, DRIVER_CHO, DRIVER_PARK}

# partner_autonomy: wave_assigner가 모든 드라이버를 후보로 취급하도록 'normal' 설정
PARTNER_AUTONOMY: dict[str, str] = {
    DRIVER_LEE:  "normal",
    DRIVER_CHO:  "normal",
    DRIVER_PARK: "normal",
}


# ── Airtable 헬퍼 ─────────────────────────────────────────────────────────────
def _str_field(raw: object) -> str:
    if isinstance(raw, list):
        return str(raw[0] or "").strip() if raw else ""
    return str(raw or "").strip()


def fetch_shipments() -> list[dict]:
    """출하확정일 기준으로 DATE_FROM ~ DATE_TO 전체 출하 레코드를 가져온다."""
    formula = (
        f"AND("
        f"IS_AFTER({{출하확정일}}, DATEADD('{DATE_FROM}', -1, 'days')), "
        f"IS_BEFORE({{출하확정일}}, DATEADD('{DATE_TO}', 1, 'days'))"
        f")"
    )
    records, offset = [], None
    page = 0
    while True:
        params: dict = {
            "fields[]": FETCH_FIELDS,
            "pageSize": 100,
            "returnFieldsByFieldId": "true",
            "filterByFormula": formula,
        }
        if offset:
            params["offset"] = offset
        resp = requests.get(
            f"https://api.airtable.com/v0/{BASE_ID}/{TBL_SHIPMENT}",
            headers=HEADERS, params=params, timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        batch = data.get("records", [])
        records.extend(batch)
        page += 1
        print(f"  fetch page {page}: +{len(batch)} records (total={len(records)})")
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records


# ── 구간유형 → tier 매핑 ──────────────────────────────────────────────────────
def zone_to_tier(zone: str) -> str:
    if zone == "수도권":
        return "tier1_seoul"
    if "지방" in zone or "도서산간" in zone:
        return "tier5_provincial"
    return "unknown"


# ── 실제 파트너 분류 ──────────────────────────────────────────────────────────
def classify_actual_partner(fields: dict) -> str | None:
    """
    배송파트너 record ID 목록에서 실제 담당자를 판별한다.
    반환: 'lee' | 'cho' | 'park' | 'logen' | 'gogox' | 'external' | None(미지정)
    """
    partners = fields.get(F_PARTNER) or []
    if not partners:
        # 이름 필드로 fallback
        name = _str_field(fields.get(F_PARTNER_NAME))
        if "이장훈" in name:
            return "lee"
        if "조희선" in name:
            return "cho"
        if "박종성" in name:
            return "park"
        if "로젠" in name:
            return "logen"
        if "고고엑스" in name or "고고" in name:
            return "gogox"
        return None
    pid = partners[0]
    if pid == DRIVER_LEE:
        return "lee"
    if pid == DRIVER_CHO:
        return "cho"
    if pid == DRIVER_PARK:
        return "park"
    name = _str_field(fields.get(F_PARTNER_NAME))
    if "로젠" in name:
        return "logen"
    if "고고엑스" in name or "고고" in name:
        return "gogox"
    return "external"


# ── 박종성 거리 계산 ──────────────────────────────────────────────────────────
def park_fare_for_rec(rec: dict, rates: dict) -> int:
    dest_addr   = _str_field(rec["fields"].get(F_DEST_ADDR))
    origin_addr = _str_field(rec["fields"].get(F_ORIGIN_ADDR))

    # origin: 에이원 우선, 다영기획 fallback
    origin_coord = DEFAULT_ORIGIN
    if "다영" in origin_addr:
        origin_coord = ORIGINS.get("다영기획", DEFAULT_ORIGIN)

    dest_coord = estimate_dest_coord(dest_addr)
    if dest_coord:
        km = haversine_km(*origin_coord, *dest_coord)
    else:
        km = PARK_AVG_KM  # fallback

    fare = round_up_500(rates["park_base"] + rates["park_km"] * km * rates["park_road_factor"])
    return fare


def parse_unload_fee(box_text: str) -> int:
    import re
    if not box_text:
        return 0
    try:
        heavy  = int(re.search(r"중대(\d+)", box_text).group(1)) if re.search(r"중대(\d+)", box_text) else 0
        large  = int(re.search(r"(?<!중)(?<!특)대(\d+)", box_text).group(1)) if re.search(r"(?<!중)(?<!특)대(\d+)", box_text) else 0
        xlarge = int(re.search(r"특대(\d+)", box_text).group(1)) if re.search(r"특대(\d+)", box_text) else 0
        return min((heavy // 5) * 5_000 + (large // 3) * 5_000 + (xlarge // 3) * 5_000, 50_000)
    except Exception:
        return 0


# ── 실제 비용 계산 (날짜별) ───────────────────────────────────────────────────
def calc_actual_cost_for_day(day_recs: list[dict], date_iso: str) -> tuple[int, dict]:
    """
    Returns (total_cost_krw, breakdown_dict)
    breakdown: {'lee': int, 'cho': int, 'park': int, 'logen': int, 'gogox': int,
                'external': int, 'unknown': int}
    """
    rates = _rates_for_sim(date_iso)
    by_partner: dict[str, list[dict]] = defaultdict(list)
    for rec in day_recs:
        p = classify_actual_partner(rec["fields"])
        by_partner[p or "unknown"].append(rec)

    breakdown = {k: 0 for k in ("lee", "cho", "park", "logen", "gogox", "external", "unknown")}

    # 이장훈: 일별 정액
    if by_partner["lee"]:
        n = len(by_partner["lee"])
        breakdown["lee"] = rates["lee_daily"]

    # 조희선: 기본 + 경기 할증
    if by_partner["cho"]:
        n = len(by_partner["cho"])
        gyeonggi = sum(1 for r in by_partner["cho"] if "경기" in _str_field(r["fields"].get(F_DEST_ADDR)))
        surcharge = max(0, gyeonggi - 1) * rates["cho_gyeonggi_surcharge"]
        breakdown["cho"] = rates["cho_base"] + surcharge

    # 박종성: 건별 거리 요금 + 상하차비
    for rec in by_partner["park"]:
        fare = park_fare_for_rec(rec, rates)
        box_text = _str_field(rec["fields"].get(F_BOX_TEXT))
        unload = parse_unload_fee(box_text)
        breakdown["park"] += fare + unload

    # 로젠: CBM 기반 또는 실제 운송비용
    for rec in by_partner["logen"]:
        actual = rec["fields"].get(F_FARE) or 0
        if actual:
            breakdown["logen"] += int(actual)
        else:
            cbm = rec["fields"].get(F_CBM) or 0
            breakdown["logen"] += int(cbm * LOGEN_PER_CBM) if cbm else 0

    # 고고엑스: 실제 or 건당 flat
    for rec in by_partner["gogox"]:
        actual = rec["fields"].get(F_FARE) or 0
        if actual:
            breakdown["gogox"] += int(actual)
        else:
            breakdown["gogox"] += GOGOX_PER_SHIP

    # 기타 외부
    for rec in by_partner["external"]:
        actual = rec["fields"].get(F_FARE) or 0
        breakdown["external"] += int(actual) if actual else 0

    # 미지정
    for rec in by_partner["unknown"]:
        actual = rec["fields"].get(F_FARE) or 0
        breakdown["unknown"] += int(actual) if actual else 0

    total = sum(breakdown.values())
    return total, breakdown


# ── 시뮬레이션 비용 계산 (날짜별) ────────────────────────────────────────────
def calc_simulated_cost_for_day(
    wave_plans: dict,
    rec_by_id: dict[str, dict],
    date_iso: str,
) -> tuple[int, dict]:
    """
    assign_waves() 결과(wave_plans)로 날짜별 시뮬레이션 비용을 계산.
    Returns (total_cost_krw, breakdown_dict)
    """
    rates = _rates_for_sim(date_iso)
    breakdown = {k: 0 for k in ("W1", "W2", "W3", "logen", "gogox", "locked", "manual")}

    # W1: 이장훈 정액 (당일 W1 배정 건 있으면 하루 정액)
    w1_ships = wave_plans.get("W1")
    if w1_ships and w1_ships.count > 0:
        breakdown["W1"] = rates["lee_daily"]

    # W2: 조희선 기본 + 경기 할증
    w2_ships = wave_plans.get("W2")
    if w2_ships and w2_ships.count > 0:
        w2_recs = [rec_by_id[s.id] for s in w2_ships.shipments if s.id in rec_by_id]
        gyeonggi = sum(1 for r in w2_recs if "경기" in _str_field(r["fields"].get(F_DEST_ADDR)))
        surcharge = max(0, gyeonggi - 1) * rates["cho_gyeonggi_surcharge"]
        breakdown["W2"] = rates["cho_base"] + surcharge

    # W3: 박종성 건별 거리 요금 + 상하차비
    w3_ships = wave_plans.get("W3")
    if w3_ships and w3_ships.count > 0:
        for s in w3_ships.shipments:
            rec = rec_by_id.get(s.id)
            if rec is None:
                continue
            fare = park_fare_for_rec(rec, rates)
            box_text = _str_field(rec["fields"].get(F_BOX_TEXT))
            unload = parse_unload_fee(box_text)
            breakdown["W3"] += fare + unload

    # spillover_로젠: CBM당
    logen_ships = wave_plans.get("spillover_로젠")
    if logen_ships and logen_ships.count > 0:
        for s in logen_ships.shipments:
            rec = rec_by_id.get(s.id)
            cbm = s.cbm if s.cbm else (rec["fields"].get(F_CBM) or 0 if rec else 0)
            breakdown["logen"] += int(cbm * LOGEN_PER_CBM) if cbm else LOGEN_PER_CBM

    # spillover_고고엑스: 건당 flat
    gogox_ships = wave_plans.get("spillover_고고엑스")
    if gogox_ships and gogox_ships.count > 0:
        breakdown["gogox"] += gogox_ships.count * GOGOX_PER_SHIP

    total = sum(breakdown.values())
    return total, breakdown


# ── 메인 시뮬레이션 ───────────────────────────────────────────────────────────
def run_simulation(records: list[dict], dry_run: bool = False) -> dict:
    """
    전체 레코드를 날짜별로 시뮬레이션하고 비용 차이를 집계한다.
    """
    total = len(records)
    skipped_no_cbm = 0
    skipped_no_zone = 0
    skipped_no_date = 0
    valid_records: list[dict] = []

    for rec in records:
        f = rec["fields"]
        d = f.get(F_DATE)
        if not d:
            skipped_no_date += 1
            continue
        cbm = f.get(F_CBM) or f.get(F_CBM_EST)
        if not cbm or cbm <= 0:
            skipped_no_cbm += 1
            continue
        zone = f.get(F_ZONE)
        if not zone:
            skipped_no_zone += 1
            continue
        tier = zone_to_tier(zone)
        if tier == "unknown":
            skipped_no_zone += 1
            continue
        valid_records.append(rec)

    skipped_total = skipped_no_date + skipped_no_cbm + skipped_no_zone
    coverage_pct = len(valid_records) / total * 100 if total else 0

    print(f"\n데이터 필터 결과:")
    print(f"  전체: {total}건 / 유효: {len(valid_records)}건 ({coverage_pct:.1f}%)")
    print(f"  스킵: {skipped_total}건 (날짜없음={skipped_no_date}, CBM없음={skipped_no_cbm}, Zone없음={skipped_no_zone})")

    if dry_run:
        # 날짜 범위 확인
        dates = sorted({rec["fields"][F_DATE] for rec in valid_records if rec["fields"].get(F_DATE)})
        print(f"\n--dry-run: 시뮬레이션 미실행")
        print(f"  날짜 범위: {dates[0] if dates else 'N/A'} ~ {dates[-1] if dates else 'N/A'}")
        print(f"  처리 예정 날짜 수: {len(dates)}일")
        return {}

    # 날짜별 그룹화
    by_date: dict[str, list[dict]] = defaultdict(list)
    for rec in valid_records:
        by_date[rec["fields"][F_DATE]].append(rec)

    rec_by_id = {rec["id"]: rec for rec in valid_records}

    # 날짜별 시뮬레이션
    daily_results: list[dict] = []

    for date_iso in sorted(by_date.keys()):
        day_recs = by_date[date_iso]

        # Shipment 객체 생성
        shipments: list[Shipment] = []
        for rec in day_recs:
            f = rec["fields"]
            zone = f.get(F_ZONE, "")
            tier = zone_to_tier(zone)
            cbm = float(f.get(F_CBM) or f.get(F_CBM_EST) or 0)
            slot = f.get(F_SLOT) or "무관"
            if slot not in ("오전", "오후", "무관", "야간", "수동"):
                slot = "무관"
            shipments.append(Shipment(
                id=rec["id"],
                project_code="",
                slot=slot,
                region=tier,
                cbm=cbm,
                cbm_confidence=0.7,
                slot_confidence=0.8,
                wave_locked=False,
            ))

        # 시뮬레이션 실행
        try:
            wave_plans = assign_waves(shipments, PARTNER_AUTONOMY, date_iso, use_sa=True, sa_seed=42)
        except Exception as e:
            print(f"  {date_iso}: assign_waves error — {e}")
            continue

        # 비용 계산
        actual_cost, actual_breakdown   = calc_actual_cost_for_day(day_recs, date_iso)
        sim_cost, sim_breakdown         = calc_simulated_cost_for_day(wave_plans, rec_by_id, date_iso)
        delta = actual_cost - sim_cost

        # 시뮬레이션 배정 수 집계
        sim_counts = {
            wid: wave_plans[wid].count if wid in wave_plans else 0
            for wid in ("W1", "W2", "W3", "spillover_로젠", "spillover_고고엑스", "수동")
        }

        daily_results.append({
            "date":             date_iso,
            "n_shipments":      len(day_recs),
            "actual_cost":      actual_cost,
            "sim_cost":         sim_cost,
            "delta":            delta,
            "actual_breakdown": actual_breakdown,
            "sim_breakdown":    sim_breakdown,
            "sim_counts":       sim_counts,
        })

    return {
        "daily": daily_results,
        "total_records": total,
        "valid_records": len(valid_records),
        "skipped_no_cbm": skipped_no_cbm,
        "skipped_no_zone": skipped_no_zone,
        "skipped_no_date": skipped_no_date,
    }


# ── 리포트 생성 ───────────────────────────────────────────────────────────────
def generate_report(results: dict, output_path: Path) -> None:
    daily = results["daily"]
    if not daily:
        print("결과 없음 — 리포트 미생성")
        return

    total_actual = sum(d["actual_cost"] for d in daily)
    total_sim    = sum(d["sim_cost"]    for d in daily)
    total_delta  = total_actual - total_sim
    delta_pct    = total_delta / total_actual * 100 if total_actual else 0

    # 월별 집계
    monthly: dict[str, dict] = defaultdict(lambda: {"actual": 0, "sim": 0, "n": 0, "days": 0})
    for d in daily:
        ym = d["date"][:7]  # YYYY-MM
        monthly[ym]["actual"] += d["actual_cost"]
        monthly[ym]["sim"]    += d["sim_cost"]
        monthly[ym]["n"]      += d["n_shipments"]
        monthly[ym]["days"]   += 1

    # 드라이버 배정 건수 집계 (시뮬 vs 실제)
    sim_driver_days: dict[str, int] = defaultdict(int)
    actual_driver_days: dict[str, int] = defaultdict(int)
    for d in daily:
        for wid, cnt in d["sim_counts"].items():
            if cnt > 0:
                sim_driver_days[wid] += 1
        for partner, cost in d["actual_breakdown"].items():
            if cost > 0 and partner in ("lee", "cho", "park", "logen", "gogox"):
                actual_driver_days[partner] += 1

    # 최대 delta 상위 3개월
    top3 = sorted(monthly.items(), key=lambda x: abs(x[1]["actual"] - x[1]["sim"]), reverse=True)[:3]

    lines = [
        f"# 배차 자동화 시뮬레이션 결과 — {DATE_FROM} ~ {DATE_TO}",
        f"",
        f"생성: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"",
        f"## Executive Summary",
        f"",
        f"| 구분 | 비용 |",
        f"|------|------|",
        f"| 실제 운임 (actual) | ₩{total_actual:,} |",
        f"| 시뮬레이션 운임 (simulated) | ₩{total_sim:,} |",
        f"| 차이 (actual − sim) | ₩{total_delta:,} ({delta_pct:+.1f}%) |",
        f"",
    ]
    if total_delta > 0:
        lines.append(f"> **자동화 알고리즘 적용 시 약 ₩{total_delta:,} ({delta_pct:.1f}%) 절감 가능** (실제 > 시뮬레이션)")
    elif total_delta < 0:
        lines.append(f"> 시뮬레이션 비용이 실제보다 ₩{abs(total_delta):,} ({abs(delta_pct):.1f}%) 높음 — 실제 배차가 더 효율적이었음")
    else:
        lines.append(f"> 실제 비용과 시뮬레이션 비용이 동일")

    lines += [
        f"",
        f"## 월별 비교",
        f"",
        f"| 월 | 건수 | 운행일 | 실제(₩) | 시뮬(₩) | 차이(₩) | 차이(%) |",
        f"|----|----|------|--------|--------|--------|--------|",
    ]
    for ym in sorted(monthly.keys()):
        m = monthly[ym]
        delta = m["actual"] - m["sim"]
        pct   = delta / m["actual"] * 100 if m["actual"] else 0
        lines.append(
            f"| {ym} | {m['n']} | {m['days']} | {m['actual']:,} | {m['sim']:,} | {delta:+,} | {pct:+.1f}% |"
        )

    lines += [
        f"",
        f"## 드라이버·운송수단 배정 비교 (운행일 수 기준)",
        f"",
        f"| 구분 | 실제 운행일 | 시뮬 운행일 | 차이 |",
        f"|------|-----------|-----------|------|",
        f"| W1 이장훈 | {actual_driver_days.get('lee', 0)} | {sim_driver_days.get('W1', 0)} | {sim_driver_days.get('W1', 0) - actual_driver_days.get('lee', 0):+d} |",
        f"| W2 조희선 | {actual_driver_days.get('cho', 0)} | {sim_driver_days.get('W2', 0)} | {sim_driver_days.get('W2', 0) - actual_driver_days.get('cho', 0):+d} |",
        f"| W3 박종성 | {actual_driver_days.get('park', 0)} | {sim_driver_days.get('W3', 0)} | {sim_driver_days.get('W3', 0) - actual_driver_days.get('park', 0):+d} |",
        f"| spillover 로젠 | {actual_driver_days.get('logen', 0)} | {sim_driver_days.get('spillover_로젠', 0)} | {sim_driver_days.get('spillover_로젠', 0) - actual_driver_days.get('logen', 0):+d} |",
        f"| spillover 고고엑스 | {actual_driver_days.get('gogox', 0)} | {sim_driver_days.get('spillover_고고엑스', 0)} | {sim_driver_days.get('spillover_고고엑스', 0) - actual_driver_days.get('gogox', 0):+d} |",
        f"",
        f"## 데이터 커버리지",
        f"",
        f"| 항목 | 값 |",
        f"|------|----|",
        f"| 총 Shipment 레코드 | {results['total_records']} |",
        f"| 유효 레코드 (CBM+Zone 있음) | {results['valid_records']} ({results['valid_records'] / results['total_records'] * 100:.1f}%) |",
        f"| 스킵 (CBM 없음) | {results['skipped_no_cbm']} |",
        f"| 스킵 (Zone 없음) | {results['skipped_no_zone']} |",
        f"| 스킵 (날짜 없음) | {results['skipped_no_date']} |",
        f"",
        f"## 주요 관찰",
        f"",
        f"### 월별 차이 Top 3",
        f"",
    ]
    for i, (ym, m) in enumerate(top3, 1):
        delta = m["actual"] - m["sim"]
        pct   = delta / m["actual"] * 100 if m["actual"] else 0
        direction = "절감" if delta > 0 else "추가비용"
        lines.append(f"{i}. **{ym}**: {direction} ₩{abs(delta):,} ({abs(pct):.1f}%) — 실제 ₩{m['actual']:,} vs 시뮬 ₩{m['sim']:,}")

    lines += [
        f"",
        f"---",
        f"",
        f"*비용 모델: 이장훈 ₩160,000/일 정액 / 조희선 기본 ₩360,000+경기할증 / 박종성 거리요금(₩{55421:,}+₩831×km×1.35) / 로젠 ₩{LOGEN_PER_CBM:,}/CBM / 고고엑스 ₩{GOGOX_PER_SHIP:,}/건*",
        f"*비교 방법: 실제 배송파트너 기준 동일 정산공식 적용 (운송비용 필드 아닌 계산값)*",
    ]

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n리포트 저장: {output_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="배차 자동화 시뮬레이션")
    parser.add_argument("--dry-run", action="store_true", help="데이터 fetch 후 시뮬레이션 미실행")
    args = parser.parse_args()

    if not AIRTABLE_PAT:
        print("ERROR: AIRTABLE_PAT 환경변수가 설정되지 않았습니다.")
        sys.exit(1)

    print(f"=== 배차 시뮬레이션 {DATE_FROM} ~ {DATE_TO} ===")
    print("Airtable에서 Shipment 레코드 가져오는 중...")
    records = fetch_shipments()
    print(f"총 {len(records)}건 fetch 완료")

    results = run_simulation(records, dry_run=args.dry_run)

    if not args.dry_run and results:
        today = datetime.now().strftime("%Y-%m-%d")
        output_dir = ROOT / "_AutoResearch" / "SCM" / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{today}-dispatch-simulation-2025-2026.md"
        generate_report(results, output_path)

        total_actual = sum(d["actual_cost"] for d in results["daily"])
        total_sim    = sum(d["sim_cost"]    for d in results["daily"])
        delta_pct    = (total_actual - total_sim) / total_actual * 100 if total_actual else 0
        print(f"\n=== 요약 ===")
        print(f"실제 운임: ₩{total_actual:,}")
        print(f"시뮬레이션: ₩{total_sim:,}")
        print(f"차이: ₩{total_actual - total_sim:,} ({delta_pct:+.1f}%)")


if __name__ == "__main__":
    main()
