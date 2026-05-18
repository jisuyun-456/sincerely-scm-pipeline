"""
tms_weekly_runner.py
──────────────────────────────────────────────────────────────────────────────
TMS 주간 AutoResearch 통합 러너 (매주 월요일 실행)

실행 순서:
  1. 약속납기일 백필  (지난 7일 Shipment)
  2. 데이터 Pull      (Shipment / 배차일지 / OTIF)
  3. 4개 Iteration 분석
  4. 주간 리포트 저장  (_AutoResearch/SCM/outputs/week_YYYYMMDD.md)
  5. log.md 업데이트

사용법:
  python scripts/tms_weekly_runner.py
  python scripts/tms_weekly_runner.py --dry-run   # 백필만 dry-run, 분석은 실행
"""

import argparse
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

# ── 경로 설정 ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
OUTPUTS_DIR = ROOT / "_AutoResearch" / "SCM" / "outputs"
LOG_PATH = ROOT / "_AutoResearch" / "SCM" / "wiki" / "log.md"
INDEX_PATH = ROOT / "_AutoResearch" / "SCM" / "wiki" / "index.md"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Airtable 상수 ──────────────────────────────────────────────────────────────
BASE_ID = "app4x70a8mOrIKsMf"
TBL_SHIPMENT = "tbllg1JoHclGYer7m"
TBL_DISPATCH = "tbl0YCjOC7rYtyXHV"    # 배차일지
TBL_OTIF = "tbl4WfEuGLDlqCTQH"
TBL_SLA = "tblbPC6z0AsbvcVxJ"
TBL_CLAIM = "tblIZ9kco1QDpUz0u"    # 배송클레임
TBL_PARTNER = "tblI4ZXrte7WyhXyd"  # 배송파트너

FORECAST_HIGH_THRESHOLD = 20  # 일별 건수 이 이상이면 추가 배차 권고
BACKFILL_DATE = "2026-05-04"  # 372건 백필 기준일 (zone_classify 314 + events 42 + TRK 16)

# 2026 법정 공휴일 + 대체공휴일 (신시어리 전사 휴무 기준)
HOLIDAYS_2026: dict[date, str] = {
    date(2026,  1,  1): "신정",
    date(2026,  2, 16): "설날 전날",
    date(2026,  2, 17): "설날",
    date(2026,  2, 18): "설날 다음날",
    date(2026,  3,  1): "삼일절",
    date(2026,  3,  2): "대체공휴일(삼일절)",
    date(2026,  5,  1): "노동절",
    date(2026,  5,  5): "어린이날",
    date(2026,  5, 25): "대체공휴일(부처님오신날)",  # 5/24 일요일
    date(2026,  6,  3): "지방선거",
    date(2026,  6,  6): "현충일",
    date(2026,  7, 17): "제헌절",
    date(2026,  8, 17): "대체공휴일(광복절)",        # 8/15 토요일
    date(2026,  9, 24): "추석 전날",
    date(2026,  9, 25): "추석",
    date(2026,  9, 26): "추석 다음날",
    date(2026, 10,  5): "대체공휴일(개천절)",        # 10/3 토요일
    date(2026, 10,  9): "한글날",
    date(2026, 12, 25): "크리스마스",
}

# 기사별 트럭 적재 용량 (m³) — 2026-05-12 확정
TRUCK_CAPACITY_M3: dict[str, float] = {
    "이장훈": 7.6,
    "조희선": 7.6,
    "박종성": 9.5,
}

AIRTABLE_PAT = os.environ.get("AIRTABLE_PAT", "")
HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_PAT}",
    "Content-Type": "application/json",
}


# ── Airtable 헬퍼 ──────────────────────────────────────────────────────────────
def get_all_records(
    table_id: str,
    fields: list[str],
    formula: str | None = None,
    max_records: int | None = None,
) -> list[dict]:
    records, offset = [], None
    while True:
        params: dict = {"fields[]": fields, "pageSize": 100, "returnFieldsByFieldId": "true"}
        if offset:
            params["offset"] = offset
        if formula:
            params["filterByFormula"] = formula
        if max_records:
            params["maxRecords"] = max_records
        resp = requests.get(
            f"https://api.airtable.com/v0/{BASE_ID}/{table_id}",
            headers=HEADERS, params=params,
        )
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset or (max_records and len(records) >= max_records):
            break
        time.sleep(0.2)
    return records


# ── 배송파트너 분류 ────────────────────────────────────────────────────────────
INTERNAL_KEYWORDS = ("이장훈", "조희선", "박종성", "물류팀")
GOGOX_KEYWORDS    = ("고고엑스",)


def classify_partner(name: str) -> str:
    """배송파트너 이름 → 'internal' / 'gogox' / 'external'"""
    for kw in INTERNAL_KEYWORDS:
        if kw in name:
            return "internal"
    for kw in GOGOX_KEYWORDS:
        if kw in name:
            return "gogox"
    return "external"


def patch_records(table_id: str, updates: list[dict]) -> None:
    for i in range(0, len(updates), 10):
        batch = updates[i:i+10]
        resp = requests.patch(
            f"https://api.airtable.com/v0/{BASE_ID}/{table_id}",
            headers=HEADERS, json={"records": batch},
        )
        resp.raise_for_status()
        time.sleep(0.25)


# ── STEP 1: 약속납기일 백필 ────────────────────────────────────────────────────
def step_backfill(dry_run: bool) -> dict:
    print("\n[STEP 1] 약속납기일 백필 (지난 7일)")

    # SLA 룩업
    sla_recs = get_all_records(TBL_SLA, [
        "fldOcAzLmHw3gb6Gr",  # 구간유형
        "fldpm7IsG1gZrvsfG",  # 배송방식
        "fldlZ0INaM3CNidcD",  # 목표배송일수
    ])
    sla_map: dict[tuple, int] = {}
    for r in sla_recs:
        f = r["fields"]
        zone = f.get("fldOcAzLmHw3gb6Gr") or ""
        method = f.get("fldpm7IsG1gZrvsfG") or ""
        days = f.get("fldlZ0INaM3CNidcD")
        if zone and method and days is not None:
            sla_map[(zone, method)] = int(days)

    # 지난 7일 Shipment
    cutoff = (date.today() - timedelta(days=7)).isoformat()
    ship_recs = get_all_records(TBL_SHIPMENT, [
        "fldQvmEwwzvQW95h9",  # 출하확정일
        "fldyYIfBhhu7sEX1P",  # 약속납기일
        "fldp6haTDFzzF5C74",  # 구간유형
        "flduzH5tS7orqGG3o",  # 배송 방식 (rollup)
    ])

    updates, updated_count = [], 0
    for rec in ship_recs:
        f = rec["fields"]
        confirmed = f.get("fldQvmEwwzvQW95h9")
        promised = f.get("fldyYIfBhhu7sEX1P")
        if not confirmed or confirmed < cutoff:
            continue
        if promised and promised != confirmed:
            continue  # 이미 실측값 있음

        zone = f.get("fldp6haTDFzzF5C74") or ""
        method_raw = f.get("flduzH5tS7orqGG3o")
        method = ""
        if isinstance(method_raw, list) and method_raw:
            first = method_raw[0]
            method = first.get("value", "") if isinstance(first, dict) else first
        elif isinstance(method_raw, str):
            method = method_raw
        # 배송방식 정규화: 변형 표기 → SLA 표준키
        method = {"택배(분할)": "택배", "택배(일반)": "택배"}.get(method, method)

        lead = sla_map.get((zone, method))
        if lead is None:
            lead = next((v for (z, _), v in sla_map.items() if z == zone), 2)

        new_promised = (date.fromisoformat(confirmed) + timedelta(days=lead)).isoformat()
        updates.append({"id": rec["id"], "fields": {"fldyYIfBhhu7sEX1P": new_promised}})

    print(f"  대상: {len(updates)}건 | dry_run={dry_run}")
    if not dry_run and updates:
        patch_records(TBL_SHIPMENT, updates)
        updated_count = len(updates)
        print(f"  완료: {updated_count}건 업데이트")

    return {"backfill_count": len(updates), "dry_run": dry_run}


# ── STEP 2: 데이터 Pull ────────────────────────────────────────────────────────
def step_pull_data() -> dict:
    print("\n[STEP 2] 데이터 Pull")

    # Shipment (최근 30일)
    cutoff = (date.today() - timedelta(days=30)).isoformat()
    ship_recs = get_all_records(TBL_SHIPMENT, [
        "fldQvmEwwzvQW95h9",  # 출하확정일
        "fldp6haTDFzzF5C74",  # 구간유형
        "flduzH5tS7orqGG3o",  # 배송방식
        "fldyYIfBhhu7sEX1P",  # 약속납기일
    ])
    recent_ships = [
        r for r in ship_recs
        if (r["fields"].get("fldQvmEwwzvQW95h9") or "") >= cutoff
    ]

    # 배송파트너 이름 캐시 (ID → 이름)
    partner_recs = get_all_records(TBL_PARTNER, ["fldUCl2kD890FqRkt"])  # 배송파트너 이름
    partner_cache = {r["id"]: r["fields"].get("fldUCl2kD890FqRkt", "") for r in partner_recs}

    # 퀵(수도권) Shipment (최근 30일, 최대 300건) — 내부 소화율 계산용
    quik_all = get_all_records(
        TBL_SHIPMENT,
        fields=["fldM2u6RwLRrO7ymW", "fldtEykbFxkO31FZP"],  # 배송파트너, 출하일자
        formula="FIND('퀵(수도권)', {배송 방식}) > 0",
        max_records=300,
    )
    quik_ships = [
        r for r in quik_all
        if (r["fields"].get("fldtEykbFxkO31FZP") or "") >= cutoff
    ]

    # 배차일지 (최근 30일) — 날짜 필터 적용
    dispatch_cutoff = (date.today() - timedelta(days=30)).isoformat()
    all_dispatch_recs = get_all_records(TBL_DISPATCH, [
        "fldZh2mZDIPQXfOcO",  # 날짜
        "fldVJoKjjzcwpHIHC",  # Total_CBM
        "fldIQqaoj2CYlCSFH",  # 배송파트너 (링크)
        "fldwrsxDL2VFdmUKo",  # 오버부킹
    ])
    dispatch_recs = [
        r for r in all_dispatch_recs
        if (r["fields"].get("fldZh2mZDIPQXfOcO") or "") >= dispatch_cutoff
    ]

    # 배송클레임 (최근 90일)
    claim_cutoff = (date.today() - timedelta(days=90)).isoformat()
    all_claim_recs = get_all_records(TBL_CLAIM, [
        "fldL2x3aqDQ4qjlD6",  # 클레임유형
        "fldiNGNqgmQH1MFB7",  # 발생일
        "fldxBT0XumwS7u3Kk",  # 피해금액
        "fldk6eb7QZar8tzBR",  # 보상금액
        "fldevAs6IBB0rN2MY",  # 처리상태
    ])
    claim_recs = [
        r for r in all_claim_recs
        if (r["fields"].get("fldiNGNqgmQH1MFB7") or "") >= claim_cutoff
    ]

    # OTIF (전체)
    otif_recs = get_all_records(TBL_OTIF, [
        "fldoUQOue0umGJ2xk",  # On_Time
        "fldiFhyU1k9YsnoGh",  # In_Full
        "fldRrWN15iV9BoToc",  # OTIF_Score
        "fldZJD4YRYg8Mr6yi",  # 납기차이일
    ])

    print(f"  Shipment(최근30일): {len(recent_ships)}건")
    print(f"  퀵(수도권)(최근30일): {len(quik_ships)}건")
    print(f"  배차일지(최근30일): {len(dispatch_recs)}건 (전체 {len(all_dispatch_recs)}건 중)")
    print(f"  배송클레임(최근90일): {len(claim_recs)}건")
    print(f"  OTIF(전체): {len(otif_recs)}건")

    return {
        "shipments": recent_ships,
        "dispatches": dispatch_recs,
        "otifs": otif_recs,
        "all_shipments": ship_recs,
        "claims": claim_recs,
        "quik_ships": quik_ships,
        "partner_cache": partner_cache,
    }


# ── STEP 3: Iteration 분석 ─────────────────────────────────────────────────────
def analyze_iter1_volume(data: dict) -> dict:
    """Iteration 1: 배송 볼륨 패턴"""
    ships = data["shipments"]
    weekday_map = {0:"월", 1:"화", 2:"수", 3:"목", 4:"금", 5:"토", 6:"일"}
    weekday_count: dict[str, int] = {v: 0 for v in weekday_map.values()}
    zone_count: dict[str, int] = {}

    for rec in ships:
        f = rec["fields"]
        confirmed = f.get("fldQvmEwwzvQW95h9")
        if confirmed:
            try:
                d = date.fromisoformat(confirmed)
                weekday_count[weekday_map[d.weekday()]] += 1
            except ValueError:
                pass
        zone = f.get("fldp6haTDFzzF5C74") or "기타"
        zone_count[zone] = zone_count.get(zone, 0) + 1

    peak_day = max(weekday_count, key=weekday_count.get) if weekday_count else "-"
    top_zone = max(zone_count, key=zone_count.get) if zone_count else "-"

    return {
        "total_shipments": len(ships),
        "by_weekday": weekday_count,
        "peak_day": peak_day,
        "by_zone": zone_count,
        "top_zone": top_zone,
    }


def analyze_iter2_dispatch_efficiency(data: dict) -> dict:
    """Iteration 2: 배송 효율 (내부 소화율 + 기사별 운행일)"""
    quik_ships    = data["quik_ships"]
    partner_cache = data["partner_cache"]
    dispatches    = data["dispatches"]

    # ── 내부 소화율 (퀵 수도권 Shipment 기준) ──────────────────────────────────
    cat: dict[str, int] = {"internal": 0, "gogox": 0, "external": 0, "none": 0}
    for rec in quik_ships:
        partners = rec["fields"].get("fldM2u6RwLRrO7ymW") or []
        if not partners:
            cat["none"] += 1
            continue
        # 첫 번째 파트너 기준으로 분류
        name = partner_cache.get(partners[0], "")
        cat[classify_partner(name)] += 1

    total = sum(cat.values()) or 1

    # ── 기사별 운행일 + CBM 집계 (배차일지 CBM>0 기준) ────────────────────────
    driver_days: dict[str, int] = {}
    driver_cbm:  dict[str, float] = {}

    for rec in dispatches:
        f = rec["fields"]
        cbm_raw = f.get("fldVJoKjjzcwpHIHC")
        try:
            cbm_val = float(cbm_raw) if cbm_raw is not None else 0.0
        except (ValueError, TypeError):
            cbm_val = 0.0
        if cbm_val <= 0:
            continue
        for pid in (f.get("fldIQqaoj2CYlCSFH") or []):
            name = partner_cache.get(pid, pid)
            driver_days[name] = driver_days.get(name, 0) + 1
            driver_cbm[name]  = driver_cbm.get(name, 0.0) + cbm_val

    # ── util_v2: CBM 적재율 per driver (Σ CBM / Σ capacity×days) ───────────────
    driver_util_v2: dict[str, float] = {}
    for driver_name, cap in TRUCK_CAPACITY_M3.items():
        # partner_cache 이름에 기사 이름 substring 매칭
        matched_name = next(
            (n for n in driver_days if driver_name in n), None
        )
        if matched_name:
            days = driver_days.get(matched_name, 0)
            cbm  = driver_cbm.get(matched_name, 0.0)
            driver_util_v2[driver_name] = round(cbm / (cap * days) * 100, 1) if days > 0 else 0.0
        else:
            driver_util_v2[driver_name] = 0.0

    # overall CBM 적재율
    total_cbm_loaded  = sum(driver_cbm.values())
    total_cap_avail   = sum(
        TRUCK_CAPACITY_M3.get(dn, 0) * driver_days.get(
            next((n for n in driver_days if dn in n), ""), 0
        )
        for dn in TRUCK_CAPACITY_M3
    )
    util_v2_overall = round(
        total_cbm_loaded / total_cap_avail * 100, 1
    ) if total_cap_avail > 0 else 0.0

    return {
        "sample_size":     len(quik_ships),
        "internal_rate":   round(cat["internal"] / total * 100, 1),
        "gogox_rate":      round(cat["gogox"]    / total * 100, 1),
        "external_rate":   round(cat["external"] / total * 100, 1),
        "none_rate":       round(cat["none"]     / total * 100, 1),
        "driver_days":     driver_days,
        "driver_cbm":      driver_cbm,
        "driver_util_v2":  driver_util_v2,
        "util_v2_overall": util_v2_overall,
    }


def analyze_iter3_cost(data: dict) -> dict:
    """Iteration 3: 운송비 (배송방식 분포 기반 추정)"""
    ships = data["all_shipments"]
    method_count: dict[str, int] = {}

    for rec in ships:
        f = rec["fields"]
        method_raw = f.get("flduzH5tS7orqGG3o")
        method = ""
        if isinstance(method_raw, list) and method_raw:
            first = method_raw[0]
            method = first.get("value", "") if isinstance(first, dict) else str(first)
        elif isinstance(method_raw, str):
            method = method_raw
        method = method.strip() or "미분류"
        method_count[method] = method_count.get(method, 0) + 1

    total = sum(method_count.values()) or 1
    method_pct = {k: round(v / total * 100, 1) for k, v in method_count.items()}

    return {
        "total_shipments": sum(method_count.values()),
        "by_method": method_count,
        "by_method_pct": method_pct,
    }


def analyze_iter4_otif(data: dict) -> dict:
    """Iteration 4: OTIF 실측 전환 현황 + 배송클레임 분석"""
    otifs = data["otifs"]
    ships = data["all_shipments"]
    claims = data.get("claims", [])

    on_time_count = 0
    in_full_count = 0
    otif_scores = []
    delay_days = []

    for rec in otifs:
        f = rec["fields"]
        on_time = f.get("fldoUQOue0umGJ2xk")
        in_full = f.get("fldiFhyU1k9YsnoGh")
        score = f.get("fldRrWN15iV9BoToc")
        diff = f.get("fldZJD4YRYg8Mr6yi")

        # formula 결과가 "true"/"false" 문자열 또는 bool
        if str(on_time).lower() in ("true", "1"):
            on_time_count += 1
        if str(in_full).lower() in ("true", "1"):
            in_full_count += 1
        if score is not None:
            try:
                otif_scores.append(float(score))
            except (TypeError, ValueError):
                pass
        if diff is not None:
            try:
                delay_days.append(float(diff))
            except (TypeError, ValueError):
                pass

    total_otif = len(otifs) or 1

    # 약속납기일 실측 전환율
    proxy_count = sum(
        1 for r in ships
        if (r["fields"].get("fldyYIfBhhu7sEX1P") or "") ==
           (r["fields"].get("fldQvmEwwzvQW95h9") or "X")
    )
    conversion_rate = round((1 - proxy_count / max(len(ships), 1)) * 100, 1)

    # 배송클레임 분석 (최근 90일)
    claim_type_count: dict[str, int] = {}
    claim_total_damage = 0.0
    claim_total_compensation = 0.0
    claim_pending = 0

    for rec in claims:
        f = rec["fields"]
        c_type = f.get("fldL2x3aqDQ4qjlD6") or "미분류"
        claim_type_count[c_type] = claim_type_count.get(c_type, 0) + 1

        damage = f.get("fldxBT0XumwS7u3Kk")
        if damage is not None:
            try:
                claim_total_damage += float(damage)
            except (TypeError, ValueError):
                pass

        compensation = f.get("fldk6eb7QZar8tzBR")
        if compensation is not None:
            try:
                claim_total_compensation += float(compensation)
            except (TypeError, ValueError):
                pass

        status = f.get("fldevAs6IBB0rN2MY") or ""
        if status not in ("완료", "종결"):
            claim_pending += 1

    return {
        "total_otif_records": len(otifs),
        "on_time_rate": round(on_time_count / total_otif * 100, 1),
        "in_full_rate": round(in_full_count / total_otif * 100, 1),
        "avg_otif_score": round(sum(otif_scores) / len(otif_scores) * 100, 1) if otif_scores else 0,
        "avg_delay_days": round(sum(delay_days) / len(delay_days), 1) if delay_days else 0,
        "proxy_conversion_rate": conversion_rate,
        # 배송클레임
        "claim_count": len(claims),
        "claim_by_type": claim_type_count,
        "claim_total_damage": round(claim_total_damage),
        "claim_total_compensation": round(claim_total_compensation),
        "claim_pending": claim_pending,
    }


def analyze_iter5_forecast(data: dict) -> dict:
    """Iteration 5: 다음 주 배송 볼륨 예측 (요일 패턴 기반)"""
    from collections import defaultdict

    ships = data["all_shipments"]
    cutoff_90 = (date.today() - timedelta(days=90)).isoformat()
    hist = [r for r in ships if (r["fields"].get("fldQvmEwwzvQW95h9") or "") >= cutoff_90]

    weekday_map = {0: "월", 1: "화", 2: "수", 3: "목", 4: "금", 5: "토", 6: "일"}

    # {year-Www: {요일: count}}
    week_day: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for rec in hist:
        confirmed = rec["fields"].get("fldQvmEwwzvQW95h9")
        if not confirmed:
            continue
        try:
            d = date.fromisoformat(confirmed)
            if d > date.today():  # 미래 날짜 skip (약속납기일 혼입 방지)
                continue
            iso = d.isocalendar()
            wk = f"{iso[0]}-W{iso[1]:02d}"
            week_day[wk][weekday_map[d.weekday()]] += 1
        except ValueError:
            pass

    sorted_weeks = sorted(week_day.keys())
    recent_4 = sorted_weeks[-4:] if len(sorted_weeks) >= 4 else sorted_weeks
    prior_8  = sorted_weeks[-12:-4] if len(sorted_weeks) >= 12 else sorted_weeks[:-4]

    weekdays_order = ["월", "화", "수", "목", "금"]
    day_forecast: dict[str, dict] = {}

    # 다음 주 월~금 실제 날짜 계산 (공휴일 zeroing 용)
    today = date.today()
    days_to_next_monday = (7 - today.weekday()) % 7 or 7
    next_monday = today + timedelta(days=days_to_next_monday)
    next_week_dates = {
        "월": next_monday,
        "화": next_monday + timedelta(1),
        "수": next_monday + timedelta(2),
        "목": next_monday + timedelta(3),
        "금": next_monday + timedelta(4),
    }

    for day in weekdays_order:
        recent_vals = [week_day[w].get(day, 0) for w in recent_4]
        prior_vals  = [week_day[w].get(day, 0) for w in prior_8] if prior_8 else []

        avg_recent = sum(recent_vals) / len(recent_vals) if recent_vals else 0
        avg_prior  = sum(prior_vals)  / len(prior_vals)  if prior_vals else avg_recent

        trend = (avg_recent - avg_prior) / avg_prior if avg_prior > 0 else 0
        base_forecast = max(0, round(avg_recent * (1 + trend * 0.15)))  # 추세 보정계수 0.15 (Iter7-C 근거)

        actual_date = next_week_dates[day]
        holiday_name = HOLIDAYS_2026.get(actual_date)
        forecast = 0 if holiday_name else base_forecast

        day_forecast[day] = {
            "forecast":     forecast,
            "avg_recent":   round(avg_recent, 1),
            "trend_pct":    round(trend * 100, 1),
            "holiday":      holiday_name,
            "actual_date":  actual_date.isoformat(),
        }

    total_forecast = sum(v["forecast"] for v in day_forecast.values())
    high_days = [d for d, v in day_forecast.items() if v["forecast"] >= FORECAST_HIGH_THRESHOLD]
    peak_day = max(
        (d for d in day_forecast if not day_forecast[d]["holiday"]),
        key=lambda d: day_forecast[d]["forecast"],
        default="-",
    )
    holiday_days = [d for d, v in day_forecast.items() if v["holiday"]]

    return {
        "day_forecast":     day_forecast,
        "total_forecast":   total_forecast,
        "high_volume_days": high_days,
        "data_weeks":       len(sorted_weeks),
        "peak_day":         peak_day,
        "holiday_days":     holiday_days,
    }


def analyze_iter6_post_backfill(data: dict) -> dict:
    """Iteration 6a: 2026-05-04 백필(372건) 이후 구간유형 커버리지 측정"""
    ships = data["all_shipments"]

    pre: list[dict] = []
    post: list[dict] = []
    for r in ships:
        confirmed = r["fields"].get("fldQvmEwwzvQW95h9") or ""
        (post if confirmed >= BACKFILL_DATE else pre).append(r)

    def _coverage(records: list[dict]) -> tuple[float, int, int]:
        with_zone = sum(1 for r in records if r["fields"].get("fldp6haTDFzzF5C74"))
        total = len(records) or 1
        return round(with_zone / total * 100, 1), with_zone, len(records)

    pre_pct, pre_with, pre_total   = _coverage(pre)
    post_pct, post_with, post_total = _coverage(post)

    zone_dist: dict[str, int] = {}
    for r in post:
        zone = r["fields"].get("fldp6haTDFzzF5C74") or "미분류"
        zone_dist[zone] = zone_dist.get(zone, 0) + 1

    return {
        "backfill_date":    BACKFILL_DATE,
        "pre_backfill":     {"total": pre_total, "with_zone": pre_with, "coverage_pct": pre_pct},
        "post_backfill":    {"total": post_total, "with_zone": post_with, "coverage_pct": post_pct},
        "coverage_delta_pp": round(post_pct - pre_pct, 1),
        "zone_distribution_post": zone_dist,
    }


def analyze_iter6_absorption_gap(data: dict) -> dict:
    """Iteration 6b: 고고엑스 내부 흡수 가능성 갭 분석 (CBM 기준)"""
    quik_ships    = data["quik_ships"]
    partner_cache = data["partner_cache"]
    dispatches    = data["dispatches"]

    gogox_count = 0
    current_internal = 0
    for r in quik_ships:
        partners = r["fields"].get("fldM2u6RwLRrO7ymW") or []
        if not partners:
            continue
        cat = classify_partner(partner_cache.get(partners[0], ""))
        if cat == "gogox":
            gogox_count += 1
        elif cat == "internal":
            current_internal += 1

    # 기사별 여유 CBM 계산 (배차일지 기준)
    driver_days: dict[str, int]   = {}
    driver_cbm:  dict[str, float] = {}
    for rec in dispatches:
        f = rec["fields"]
        try:
            cbm_val = float(f.get("fldVJoKjjzcwpHIHC") or 0)
        except (ValueError, TypeError):
            cbm_val = 0.0
        if cbm_val <= 0:
            continue
        for pid in (f.get("fldIQqaoj2CYlCSFH") or []):
            name = partner_cache.get(pid, pid)
            driver_days[name] = driver_days.get(name, 0) + 1
            driver_cbm[name]  = driver_cbm.get(name, 0.0) + cbm_val

    total_headroom = 0.0
    driver_headroom: dict[str, float] = {}
    for driver_name, cap in TRUCK_CAPACITY_M3.items():
        matched = next((n for n in driver_days if driver_name in n), None)
        if matched:
            headroom = max(0.0, cap * driver_days[matched] - driver_cbm.get(matched, 0.0))
        else:
            headroom = 0.0
        driver_headroom[driver_name] = round(headroom, 2)
        total_headroom += headroom

    # 건당 평균 CBM 보수적 추정 (퀵 수도권 소형화물 기준)
    avg_cbm_per_shipment = 0.5
    absorbable = min(gogox_count, int(total_headroom / avg_cbm_per_shipment))

    total_quik = len(quik_ships) or 1
    new_internal_rate = round((current_internal + absorbable) / total_quik * 100, 1)
    current_internal_rate = round(current_internal / total_quik * 100, 1)
    gap_closure_pp = round(new_internal_rate - current_internal_rate, 1)

    recs = [
        f"트럭 여유 합계 {total_headroom:.1f}m³ — 고고엑스 {absorbable}건 즉시 흡수 가능",
        f"흡수 후 내부 소화율 {current_internal_rate}% → {new_internal_rate}% ({gap_closure_pp:+.1f}pp)",
        "일별 고고엑스 사전 알림 → 기사 조기 배정으로 추가 흡수 기회 확보",
        "CBM 데이터 Airtable 입력 표준화 → 정밀 분석 가능 (현재 0.5m³ 추정치 사용)",
        f"목표 80% 달성까지 잔여 {max(0, 80 - new_internal_rate):.1f}pp — 배송방식 전환 검토 필요",
    ]

    return {
        "gogox_count":               gogox_count,
        "current_internal_rate_pct": current_internal_rate,
        "total_headroom_cbm":        round(total_headroom, 2),
        "driver_headroom_cbm":       driver_headroom,
        "avg_cbm_assumed":           avg_cbm_per_shipment,
        "absorbable_count":          absorbable,
        "new_internal_rate_pct":     new_internal_rate,
        "gap_closure_pp":            gap_closure_pp,
        "top_recommendations":       recs,
    }


# ── STEP 4: 리포트 저장 ────────────────────────────────────────────────────────
def _load_prior_kpis(week_str: str) -> dict:
    """직전 주 리포트에서 KPI 수치를 추출해 delta 계산용으로 반환."""
    import re
    try:
        iso_year, iso_week = week_str.split("-W")
        prev_week = int(iso_week) - 1
        prev_year = int(iso_year)
        if prev_week < 1:
            prev_week = 52
            prev_year -= 1
        prev_path = OUTPUTS_DIR / f"TMS-{prev_year}-W{prev_week:02d}.md"
        if not prev_path.exists():
            return {}
        text = prev_path.read_text(encoding="utf-8")
        m_internal = re.search(r"내부 소화율.*?\|\s*([\d.]+)%", text)
        m_otif     = re.search(r"OTIF On-Time율.*?\|\s*([\d.]+)%", text)
        return {
            "internal_rate": float(m_internal.group(1)) if m_internal else None,
            "on_time_rate":  float(m_otif.group(1))     if m_otif     else None,
        }
    except Exception:
        return {}


def _delta(current: float, prior: float | None) -> str:
    if prior is None:
        return ""
    diff = current - prior
    return f" ({'+' if diff >= 0 else ''}{diff:.1f}pp)"


def step_save_report(results: dict, week_str: str, date_range: str = "") -> Path:
    print("\n[STEP 4] 주간 리포트 저장")
    r1  = results["iter1"]
    r2  = results["iter2"]
    r3  = results["iter3"]
    r4  = results["iter4"]
    r5  = results["iter5"]
    r6a = results["iter6a"]
    r6b = results["iter6b"]
    bf  = results["backfill"]
    prior = _load_prior_kpis(week_str)

    efficiency_status = "달성" if r2["internal_rate"] >= 80 else "미달"
    otif_status = "달성" if r4["on_time_rate"] >= 90 else "미달"
    header_label = f"{week_str}  ({date_range})" if date_range else week_str

    report = f"""# TMS 주간 분석 — {header_label}

> 자동 생성: {date.today().isoformat()} | 분석 기간: 최근 30일 기준

---

## KPI 요약

| 지표 | 실적 | 전주 대비 | 목표 | 상태 |
|------|------|---------|------|------|
| 내부 소화율 (퀵 수도권) | {r2["internal_rate"]}% | {_delta(r2["internal_rate"], prior.get("internal_rate"))} | ≥80% | {efficiency_status} |
| OTIF On-Time율 | {r4["on_time_rate"]}% | {_delta(r4["on_time_rate"], prior.get("on_time_rate"))} | ≥90% | {otif_status} |
| In-Full율 | {r4["in_full_rate"]}% | — | ≥95% | - |
| 약속납기일 실측 전환율 | {r4["proxy_conversion_rate"]}% | — | 100% | - |

---

## Iteration 1: 배송 볼륨 패턴

- 분석 대상: {r1["total_shipments"]}건 (최근 30일)
- 최다 출하 요일: **{r1["peak_day"]}요일**
- 주요 구간: **{r1["top_zone"]}** 집중

요일별 분포:
{chr(10).join(f"  {k}: {v}건" for k, v in r1["by_weekday"].items())}

구간유형 분포:
{chr(10).join(f"  {k}: {v}건" for k, v in r1["by_zone"].items())}

---

## Iteration 2: 배송 효율 (내부 소화율 + 차량이용률)

- 분석 샘플: {r2["sample_size"]}건 (퀵 수도권 최근 30일)
- 내부 소화율: **{r2["internal_rate"]}%** (목표 ≥80%)
- 고고엑스 비중: {r2["gogox_rate"]}%
- 외부 파트너: {r2["external_rate"]}%

기사별 운행일 (최근 30일):
{chr(10).join(f"  {k}: {v}일" for k, v in r2["driver_days"].items()) if r2["driver_days"] else "  (데이터 없음)"}

### K1 차량이용률 v2 (CBM 적재율)

> util_v2 = Total_CBM 합계 / (트럭 용량 x 운행일수)

| 기사 | 트럭 용량 | 총 CBM | 운행일 | 적재율 |
|------|---------|--------|--------|--------|
{chr(10).join(
    f"| {dn} | {TRUCK_CAPACITY_M3.get(dn, '-')}m³ | "
    + f"{r2['driver_cbm'].get(next((n for n in r2['driver_cbm'] if dn in n), ''), 0.0):.2f}m³ | "
    + f"{r2['driver_days'].get(next((n for n in r2['driver_days'] if dn in n), ''), 0)}일 | "
    + f"**{r2['driver_util_v2'].get(dn, 0.0)}%** |"
    for dn in ["이장훈", "조희선", "박종성"]
)}
| **전체** | - | {sum(r2['driver_cbm'].values()):.2f}m³ | - | **{r2['util_v2_overall']}%** |

> {'목표 달성' if r2["internal_rate"] >= 80 else f'미달 — {80 - r2["internal_rate"]:.1f}%p 개선 필요 (고고엑스 건 내부 흡수 검토)'}

---

## Iteration 3: 배송방식 분포

- 전체 Shipment: {r3["total_shipments"]}건

방식별 비중:
{chr(10).join(f"  {k}: {v}건 ({r3['by_method_pct'].get(k, 0)}%)" for k, v in r3["by_method"].items())}

---

## Iteration 4: OTIF 실측 전환

- OTIF 레코드: {r4["total_otif_records"]}건
- On-Time율: **{r4["on_time_rate"]}%**
- In-Full율: **{r4["in_full_rate"]}%**
- 평균 납기차이: {r4["avg_delay_days"]}일
- 약속납기일 실측 전환율: **{r4["proxy_conversion_rate"]}%**

### 배송클레임 (최근 90일)

- 총 클레임: {r4["claim_count"]}건 (미처리 {r4["claim_pending"]}건)
- 피해금액 합계: {r4["claim_total_damage"]:,}원 / 보상금액: {r4["claim_total_compensation"]:,}원

유형별 분포:
{chr(10).join(f"  {k}: {v}건" for k, v in r4["claim_by_type"].items()) if r4["claim_by_type"] else "  (클레임 없음)"}

---

## Iteration 5: 다음 주 배송 볼륨 예측

> 기반 데이터: {r5["data_weeks"]}주치 패턴 (최근 90일) | 최근 4주 이동평균 + 추세 보정 (계수 0.15) | 공휴일 자동 반영

| 요일 | 날짜 | 예측 볼륨 | 최근 4주 평균 | 추세 |
|------|------|----------|-------------|------|
{chr(10).join(f"| {d} | {v['actual_date']} | {'🔴 공휴일 (' + v['holiday'] + ')' if v['holiday'] else str(v['forecast']) + '건'} | {v['avg_recent']}건 | {'+' if v['trend_pct'] >= 0 else ''}{v['trend_pct']}% |" for d, v in r5["day_forecast"].items())}

- **주간 예측 합계: {r5["total_forecast"]}건** (공휴일 제외)
{f"- 🔴 공휴일: **{'·'.join(r5['holiday_days'])}요일** — 출하 없음" if r5["holiday_days"] else ""}
{f"- ⚠️ 배차 권고: **{'·'.join(r5['high_volume_days'])}요일** 볼륨 과다 → 고고엑스 사전 예약 또는 추가 기사 배정 검토" if r5["high_volume_days"] else "- 배차 이슈 없음 (전 요일 정상 범위)"}

---

## Iteration 6: Gap Analysis (Post-Backfill)

### 6a. 구간유형 커버리지 ({BACKFILL_DATE} 백필 기준)

| 구분 | 총건수 | 구간 있음 | 커버리지 |
|------|--------|---------|---------|
| 백필 이전 ({BACKFILL_DATE} 미만) | {r6a["pre_backfill"]["total"]}건 | {r6a["pre_backfill"]["with_zone"]}건 | {r6a["pre_backfill"]["coverage_pct"]}% |
| 백필 이후 ({BACKFILL_DATE} 이상) | {r6a["post_backfill"]["total"]}건 | {r6a["post_backfill"]["with_zone"]}건 | {r6a["post_backfill"]["coverage_pct"]}% |
| **커버리지 델타** | - | - | **{r6a["coverage_delta_pp"]:+.1f}pp** |

백필 이후 구간유형 분포:
{chr(10).join(f"  {k}: {v}건" for k, v in r6a["zone_distribution_post"].items())}

### 6b. 내부 소화율 갭 분석 (CBM 기준)

- 고고엑스 건수 (최근 30일): **{r6b["gogox_count"]}건**
- 트럭 여유 용량 합계: **{r6b["total_headroom_cbm"]}m³** (건당 {r6b["avg_cbm_assumed"]}m³ 가정)
- 흡수 가능 건수: **{r6b["absorbable_count"]}건**
- 예상 내부 소화율: {r6b["current_internal_rate_pct"]}% → **{r6b["new_internal_rate_pct"]}%** ({r6b["gap_closure_pp"]:+.1f}pp)

기사별 여유 CBM:
{chr(10).join(f"  {k}: {v}m³" for k, v in r6b["driver_headroom_cbm"].items())}

---

## ⚡ Action Items

{chr(10).join(f"{i+1}. {rec}" for i, rec in enumerate(r6b["top_recommendations"]))}

---

## 이번 주 백필

- 약속납기일 업데이트: {bf["backfill_count"]}건{"(dry-run)" if bf["dry_run"] else ""}

---

## 다음 주 체크포인트

- [ ] 내부 소화율 {'개선 검토 (고고엑스 건 내부 흡수)' if r2["internal_rate"] < 80 else '목표 달성 — 유지 모니터링'}
- [ ] OTIF {'원인 분석' if r4["on_time_rate"] < 90 else '목표 달성 유지'}
- [ ] 약속납기일 전환율 {'개선 (구간유형/배송방식 매핑 확인)' if r4["proxy_conversion_rate"] < 90 else '100% 유지'}

---

## 💬 개선 논의

> 이 섹션은 Claude Code와의 검토 후 채워집니다.

---

## ✅ 확정 개선안

> 이 섹션은 최종 논의 완료 후 다음 주 AutoResearch에 반영됩니다.
"""

    output_path = OUTPUTS_DIR / f"TMS-{week_str}.md"
    output_path.write_text(report, encoding="utf-8")
    print(f"  저장: {output_path}")
    return output_path


# ── STEP 5: log.md 업데이트 ───────────────────────────────────────────────────
def step_update_log(results: dict, report_path: Path, week_str: str) -> None:
    print("\n[STEP 5] log.md 업데이트")
    r2  = results["iter2"]
    r4  = results["iter4"]
    r5  = results["iter5"]
    r6b = results["iter6b"]

    entry = f"""
## [{date.today().isoformat()}] WEEKLY | 주간 분석 {week_str}

**상태:** 완료

### KPI 스냅샷
- 내부 소화율: {r2["internal_rate"]}% (목표 ≥80%) | 고고엑스: {r2["gogox_rate"]}%
- OTIF On-Time: {r4["on_time_rate"]}% (목표 ≥90%)
- 차량이용률 v2 (CBM 적재율): {r2["util_v2_overall"]}%
- 약속납기일 전환율: {r4["proxy_conversion_rate"]}%
- 다음 주 예측: {r5["total_forecast"]}건 (피크 {r5["peak_day"]}요일)

### Iter6 갭분석
- 흡수 가능 고고엑스: {r6b["absorbable_count"]}건 → 내부 소화율 {r6b["new_internal_rate_pct"]}% 달성 예상 ({r6b["gap_closure_pp"]:+.1f}pp)

### 산출물
- [{report_path.name}](../outputs/{report_path.name})

### 다음 주 포커스
- {'내부 소화율 개선 (고고엑스 건 흡수 검토)' if r2["internal_rate"] < 80 else 'OTIF 실측 전환 완료' if r4["proxy_conversion_rate"] < 100 else '현상 유지 + 심화 분석'}
"""

    existing = LOG_PATH.read_text(encoding="utf-8") if LOG_PATH.exists() else ""
    entry_header = f"## [{date.today().isoformat()}] WEEKLY | 주간 분석 {week_str}"
    if entry_header not in existing:
        LOG_PATH.write_text(existing + entry, encoding="utf-8")

    # index.md 업데이트 (중복 방지)
    idx = INDEX_PATH.read_text(encoding="utf-8") if INDEX_PATH.exists() else ""
    new_row = f"| [{report_path.name}](../outputs/{report_path.name}) | 주간 | {date.today().isoformat()} | 완료 |\n"
    if report_path.name not in idx:  # 동일 파일명 중복 삽입 방지
        if "| (미생성)" in idx:
            idx = idx.replace("| (미생성) iter1", new_row + "| (미생성) iter1")
        else:
            idx += new_row
        INDEX_PATH.write_text(idx, encoding="utf-8")

    print("  log.md / index.md 업데이트 완료")


def _notify_slack_report(results: dict, week_str: str, report_path: Path) -> None:
    """주간 AutoResearch 리포트 요약을 Slack DM으로 발송."""
    token   = os.environ.get("SLACK_BOT_TOKEN", "")
    user_id = os.environ.get("SLACK_DM_USER_ID", "")
    if not token or not user_id:
        return
    r2  = results["iter2"]
    r4  = results["iter4"]
    r6b = results["iter6b"]
    lines = [
        f"*TMS 주간 AutoResearch — {week_str}*",
        f"  내부 소화율: {r2['internal_rate']}% (목표 ≥80%) | 고고엑스: {r2['gogox_rate']}%",
        f"  OTIF On-Time: {r4['on_time_rate']}%",
        f"  갭분석: 흡수 가능 {r6b['absorbable_count']}건 → 소화율 {r6b['new_internal_rate_pct']}% 달성 예상",
        f"  리포트: {report_path.name}",
    ]
    try:
        ch = requests.post(
            "https://slack.com/api/conversations.open",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"users": user_id}, timeout=10,
        ).json()["channel"]["id"]
        requests.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"channel": ch, "text": "\n".join(lines)},
            timeout=10,
        )
    except Exception:
        pass


# ── 메인 ───────────────────────────────────────────────────────────────────────
def _compute_week_label() -> tuple[str, str, str]:
    """실행일 기준 직전 주 레이블 계산.

    Returns:
        week_id:    "2026-W16"  (ISO 주차, 파일명용)
        date_range: "04/13~04/17" (월~금, 헤더 표시용)
        run_date:   "2026-04-20" (실행일)
    """
    today = date.today()
    # 직전 월요일 = 오늘 - 7일 (GH Actions가 월요일 실행이므로)
    prev_monday = today - timedelta(days=7)
    prev_friday = prev_monday + timedelta(days=4)
    iso_year, iso_week, _ = prev_monday.isocalendar()
    week_id    = f"{iso_year}-W{iso_week:02d}"
    date_range = f"{prev_monday.strftime('%m/%d')}~{prev_friday.strftime('%m/%d')}"
    return week_id, date_range, today.isoformat()


def main(dry_run: bool) -> None:
    if not AIRTABLE_PAT:
        print("[ERROR] AIRTABLE_PAT 환경변수 없음. .env 파일 확인")
        sys.exit(1)

    week_id, date_range, run_date = _compute_week_label()
    week_str = week_id  # 하위 함수 호환용
    print(f"\n{'='*60}")
    print(f"TMS 주간 AutoResearch | {week_id} ({date_range})")
    print(f"{'='*60}")

    # 1. 백필
    bf_result = step_backfill(dry_run)

    # 2. 데이터 Pull
    data = step_pull_data()

    # 3. 분석
    print("\n[STEP 3] Iteration 분석")
    r1  = analyze_iter1_volume(data)
    r2  = analyze_iter2_dispatch_efficiency(data)
    r3  = analyze_iter3_cost(data)
    r4  = analyze_iter4_otif(data)
    r5  = analyze_iter5_forecast(data)
    r6a = analyze_iter6_post_backfill(data)
    r6b = analyze_iter6_absorption_gap(data)
    print(f"  Iter1: 볼륨 {r1['total_shipments']}건, 피크 {r1['peak_day']}요일")
    print(f"  Iter2: 내부 소화율 {r2['internal_rate']}%, 고고엑스 {r2['gogox_rate']}%")
    print(f"  Iter3: 배송방식 {len(r3['by_method'])}종")
    print(f"  Iter4: OTIF On-Time {r4['on_time_rate']}%, 전환율 {r4['proxy_conversion_rate']}%")
    print(f"  Iter5: 다음 주 예측 합계 {r5['total_forecast']}건, 피크 {r5['peak_day']}요일")
    print(f"  Iter6a: 구간 커버리지 델타 {r6a['coverage_delta_pp']:+.1f}pp")
    print(f"  Iter6b: 흡수 가능 {r6b['absorbable_count']}건, 예상 소화율 {r6b['new_internal_rate_pct']}%")

    results = {
        "backfill": bf_result,
        "iter1": r1, "iter2": r2, "iter3": r3, "iter4": r4, "iter5": r5,
        "iter6a": r6a, "iter6b": r6b,
    }

    # 4. 리포트 저장
    report_path = step_save_report(results, week_str, date_range)

    # 5. log.md 업데이트
    step_update_log(results, report_path, week_str)

    # 6. Slack 리포트 발송
    _notify_slack_report(results, week_str, report_path)

    print(f"\n{'='*60}")
    print("주간 분석 완료")
    print(f"리포트: {report_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TMS 주간 AutoResearch 러너")
    parser.add_argument("--dry-run", action="store_true", help="백필 dry-run 모드")
    args = parser.parse_args()
    main(args.dry_run)
