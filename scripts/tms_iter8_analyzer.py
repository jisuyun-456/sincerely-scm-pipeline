"""
tms_iter8_analyzer.py
─────────────────────────────────────────────────────────────────────────────
TMS AutoResearch Iter8 — 3-axis analysis

Axes:
  A. Lane × CBM 통합 ROI (구간별 CBM당 운임 수익성)
  B. Driver 회전율 / 피로도 (6주 기사별 운행 패턴)
  C. GoGoX 외주 추이 + NPV 실사 (실제 운임 기반 손익분기 재산출)

NPV 가정:
  GoGoX 단가 = 거리 기준 차등 (CBM→차종→거리요율). 실발주 운임 역산 우선.
  박종성 한계비용 = 배차일지 운임합계 ÷ 운행일로 역산.
  Iter7의 15,000원/건 고정단가 가정은 폐기.

Usage:
  py -m scripts.tms_iter8_analyzer
  py -m scripts.tms_iter8_analyzer --dry-run
  py -m scripts.tms_iter8_analyzer --weeks 8
"""

import argparse
import os
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from statistics import mean

from dotenv import load_dotenv

load_dotenv()

from scripts.tms_weekly_runner import (
    BASE_ID,
    HEADERS,
    HOLIDAYS_2026,
    INTERNAL_KEYWORDS,
    TBL_DISPATCH,
    TBL_PARTNER,
    TBL_SHIPMENT,
    TRUCK_CAPACITY_M3,
    classify_partner,
    get_all_records,
)

VAULT_OUTPUTS = Path("C:/Users/yjisu/Documents/ClaudeVault/SCM/_AutoResearch/outputs")
VAULT_LOG     = Path("C:/Users/yjisu/Documents/ClaudeVault/SCM/_AutoResearch/wiki/log.md")
VAULT_INDEX   = Path("C:/Users/yjisu/Documents/ClaudeVault/SCM/_AutoResearch/wiki/index.md")


# ── 데이터 Pull ───────────────────────────────────────────────────────────────

def pull_iter8_data(weeks: int = 6) -> dict:
    print(f"\n[ITER8] 데이터 Pull ({weeks}주)")
    cutoff = (date.today() - timedelta(weeks=weeks)).isoformat()

    ship_recs = get_all_records(TBL_SHIPMENT, [
        "fldQvmEwwzvQW95h9",  # 출하확정일
        "fldp6haTDFzzF5C74",  # 구간유형
        "flduzH5tS7orqGG3o",  # 배송방식 (rollup)
        "fldRT95SC88KSBATT",  # 운송비용
        "fldxmAZrBGqS7sQoL",  # 상하차비용
        "fldM2u6RwLRrO7ymW",  # 배송파트너 (GoGoX 판별용)
    ])
    recent_ships = [r for r in ship_recs if (r["fields"].get("fldQvmEwwzvQW95h9") or "") >= cutoff]

    partner_recs  = get_all_records(TBL_PARTNER, ["fldUCl2kD890FqRkt"])
    partner_cache = {r["id"]: r["fields"].get("fldUCl2kD890FqRkt", "") for r in partner_recs}

    all_dispatch = get_all_records(TBL_DISPATCH, [
        "fldZh2mZDIPQXfOcO",  # 날짜
        "fldVJoKjjzcwpHIHC",  # Total_CBM
        "fldIQqaoj2CYlCSFH",  # 배송파트너 (링크)
        "fldwrsxDL2VFdmUKo",  # 오버부킹
        "fldoT3HlVBWmxJBLs",  # 운임합계
    ])
    dispatch_recs = [r for r in all_dispatch if (r["fields"].get("fldZh2mZDIPQXfOcO") or "") >= cutoff]

    print(f"  Shipment({weeks}주): {len(recent_ships)}건 | 배차일지: {len(dispatch_recs)}건")
    return {
        "shipments":    recent_ships,
        "dispatches":   dispatch_recs,
        "partner_cache": partner_cache,
    }


def _resolve_driver(rec: dict, partner_cache: dict) -> str:
    links = rec["fields"].get("fldIQqaoj2CYlCSFH") or []
    if not links:
        return ""
    pid = links[0] if isinstance(links[0], str) else links[0].get("id", "")
    return partner_cache.get(pid, "")


def _safe_float(val) -> float:
    try:
        return float(val) if val is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _extract_mode(raw) -> str:
    """flduzH5tS7orqGG3o rollup 값 → 문자열 추출 (list[dict|str] or str)"""
    if not raw:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list) and raw:
        first = raw[0]
        return first.get("value", "") if isinstance(first, dict) else str(first)
    return ""


# ── Iter8-A: Lane × CBM ROI ──────────────────────────────────────────────────

def analyze_iter8_lane_roi(data: dict) -> dict:
    ships     = data["shipments"]
    dispatches = data["dispatches"]

    # 전체 배차 CBM (비례 배분 기준)
    total_dispatch_cbm = sum(_safe_float(r["fields"].get("fldVJoKjjzcwpHIHC")) for r in dispatches)

    zone_count: dict[str, int]   = defaultdict(int)
    zone_fare:  dict[str, float] = defaultdict(float)

    for rec in ships:
        f    = rec["fields"]
        zone = f.get("fldp6haTDFzzF5C74") or "미분류"
        fare = _safe_float(f.get("fldRT95SC88KSBATT")) + _safe_float(f.get("fldxmAZrBGqS7sQoL"))
        zone_count[zone] += 1
        zone_fare[zone]  += fare

    total_count = sum(zone_count.values()) or 1
    rows = []
    for zone in sorted(zone_count, key=lambda z: zone_count[z], reverse=True):
        cnt      = zone_count[zone]
        fare_sum = zone_fare[zone]
        cbm_est  = round(total_dispatch_cbm * cnt / total_count, 2)
        fare_per_cbm = round(fare_sum / cbm_est, 1) if cbm_est > 0 and fare_sum > 0 else 0.0
        rows.append({
            "zone":        zone,
            "count":       cnt,
            "fare_sum":    round(fare_sum),
            "cbm_est":     cbm_est,
            "fare_per_cbm": fare_per_cbm,
            "share_pct":   round(cnt / total_count * 100, 1),
        })

    fare_data_available = any(r["fare_sum"] > 0 for r in rows)
    top_zone = max(rows, key=lambda r: r["fare_per_cbm"]) if fare_data_available else None

    return {
        "rows":               rows,
        "total_dispatch_cbm": round(total_dispatch_cbm, 2),
        "fare_data_available": fare_data_available,
        "top_roi_zone":       top_zone["zone"] if top_zone else "데이터 없음",
    }


# ── Iter8-B: Driver 피로도 ────────────────────────────────────────────────────

def analyze_iter8_driver_fatigue(data: dict) -> dict:
    dispatches    = data["dispatches"]
    partner_cache = data["partner_cache"]

    driver_dates:   dict[str, list]  = defaultdict(list)
    driver_cbm:     dict[str, float] = defaultdict(float)
    driver_overbook: dict[str, int]  = defaultdict(int)

    for rec in dispatches:
        name = _resolve_driver(rec, partner_cache)
        if not any(kw in name for kw in ("이장훈", "조희선", "박종성")):
            continue
        f  = rec["fields"]
        dt = f.get("fldZh2mZDIPQXfOcO")
        if dt:
            driver_dates[name].append(dt)
        driver_cbm[name] += _safe_float(f.get("fldVJoKjjzcwpHIHC"))
        if f.get("fldwrsxDL2VFdmUKo"):
            driver_overbook[name] += 1

    # 영업일 기준 6주 윈도우
    today      = date.today()
    cutoff_day = today - timedelta(weeks=6)
    biz_days   = sum(
        1 for i in range(42)
        if (cutoff_day + timedelta(i)).weekday() < 5
        and (cutoff_day + timedelta(i)) not in HOLIDAYS_2026
    )

    rows = []
    for name in sorted(driver_dates.keys()):
        dates_sorted = sorted(set(driver_dates[name]))
        op_days = len(dates_sorted)

        # 최장 연속 운행일 (영업일 기준: 하루 이상 간격이면 리셋)
        max_streak = streak = 1
        for i in range(1, len(dates_sorted)):
            d_prev = date.fromisoformat(dates_sorted[i - 1])
            d_curr = date.fromisoformat(dates_sorted[i])
            gap    = (d_curr - d_prev).days
            if gap <= 3:  # 주말 포함 최대 3일(금→월) 허용
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 1

        rows.append({
            "name":            name,
            "op_days":         op_days,
            "rest_days":       biz_days - op_days,
            "total_cbm":       round(driver_cbm[name], 1),
            "avg_cbm_per_day": round(driver_cbm[name] / op_days, 2) if op_days else 0.0,
            "max_streak":      max_streak,
            "overbooking":     driver_overbook[name],
            "fatigue_flag":    "⚠️" if max_streak >= 5 else "✅",
        })

    return {"rows": rows, "biz_days": biz_days}


# ── Iter8-C: 외주 추이 + NPV 실사 ────────────────────────────────────────────

def analyze_iter8_outsourcing_trend(data: dict) -> dict:
    dispatches    = data["dispatches"]
    ships         = data["shipments"]
    partner_cache = data["partner_cache"]

    # GoGoX는 배차일지 없음 — 퀵(수도권) shipment의 배송파트너로 추적
    week_gogox: dict[str, int] = defaultdict(int)
    gogox_ship_fares: list[float] = []
    for rec in ships:
        f    = rec["fields"]
        mode = _extract_mode(f.get("flduzH5tS7orqGG3o"))
        if "퀵" not in mode:
            continue
        partners = f.get("fldM2u6RwLRrO7ymW") or []
        if not partners:
            continue
        pid   = partners[0] if isinstance(partners[0], str) else partners[0].get("id", "")
        pname = partner_cache.get(pid, "")
        if classify_partner(pname) != "gogox":
            continue
        dt = f.get("fldQvmEwwzvQW95h9")
        if dt:
            d   = date.fromisoformat(dt)
            iso = d.isocalendar()
            week_gogox[f"{iso[0]}-W{iso[1]:02d}"] += 1
        fare = _safe_float(f.get("fldRT95SC88KSBATT")) + _safe_float(f.get("fldxmAZrBGqS7sQoL"))
        if fare > 0:
            gogox_ship_fares.append(fare)

    # 박종성 배차일지 운임합계
    park_dispatches = [
        r for r in dispatches
        if "박종성" in _resolve_driver(r, partner_cache)
    ]

    weeks_sorted   = sorted(week_gogox)
    weekly_counts  = [week_gogox[w] for w in weeks_sorted]
    monthly_avg    = round(mean(weekly_counts) * 4.33, 1) if weekly_counts else 0.0

    # 선형 추세
    n = len(weekly_counts)
    if n >= 2:
        xs  = list(range(n))
        mx, my = sum(xs) / n, sum(weekly_counts) / n
        cov = sum((x - mx) * (y - my) for x, y in zip(xs, weekly_counts))
        var = sum((x - mx) ** 2 for x in xs)
        slope = cov / var if var > 0 else 0.0
    else:
        slope = 0.0

    # 박종성 한계비용: 배차일지 트립 평균
    park_trip_fares = [_safe_float(r["fields"].get("fldoT3HlVBWmxJBLs")) for r in park_dispatches]
    park_trip_fares = [v for v in park_trip_fares if v > 0]
    avg_park_fare   = mean(park_trip_fares) if park_trip_fares else 0.0

    # GoGoX 건당 운임: shipment-level 우선 (CBM 기반 차등요율 반영)
    avg_gogox_fare = mean(gogox_ship_fares) if gogox_ship_fares else 0.0

    fare_source   = "실발주 shipment" if gogox_ship_fares else "배차일지 트립 추정"
    fare_sample_n = len(gogox_ship_fares)

    # NPV (월할인 0.5%)
    s1_saving_per   = avg_gogox_fare - avg_park_fare  # 건당 절감 (한계비용 기준)
    s1_monthly_sav  = s1_saving_per * monthly_avg
    s1_npv_12m      = round(sum(s1_monthly_sav / (1.005 ** m) for m in range(1, 13)))

    s2_monthly_sav  = avg_gogox_fare * monthly_avg - 3_800_000
    s2_npv_12m      = round(sum(s2_monthly_sav / (1.005 ** m) for m in range(1, 13)))

    s1_breakeven = round(avg_park_fare / s1_saving_per) if s1_saving_per > 0 else 999
    s2_breakeven = round(3_800_000 / avg_gogox_fare)    if avg_gogox_fare > 0 else 999

    # S1 손익분기 도달 예상 주차
    if slope > 0 and monthly_avg < s1_breakeven:
        weeks_to_be = round((s1_breakeven - monthly_avg) / (slope * 4.33))
    else:
        weeks_to_be = None

    return {
        "weeks_sorted":          weeks_sorted,
        "weekly_counts":         weekly_counts,
        "monthly_avg":           monthly_avg,
        "slope_per_week":        round(slope, 2),
        "avg_gogox_fare":        round(avg_gogox_fare),
        "avg_park_fare":         round(avg_park_fare),
        "s1_saving_per_ship":    round(s1_saving_per),
        "s1_npv_12m":            s1_npv_12m,
        "s1_breakeven":          s1_breakeven,
        "s2_npv_12m":            s2_npv_12m,
        "s2_breakeven":          s2_breakeven,
        "weeks_to_s1_breakeven": weeks_to_be,
        "fare_source":           fare_source,
        "fare_sample_n":         fare_sample_n,
    }


# ── 보고서 빌드 ───────────────────────────────────────────────────────────────

def _build_report(week_str: str, r_a: dict, r_b: dict, r_c: dict) -> str:
    def lane_row(r):
        fare_col = f"{r['fare_sum']:,}원" if r["fare_sum"] > 0 else "(미집계)"
        cpf_col  = f"{r['fare_per_cbm']:,}원/m³" if r["fare_per_cbm"] > 0 else "-"
        return f"| {r['zone']} | {r['count']}건 | {fare_col} | {r['cbm_est']}m³ | {cpf_col} | {r['share_pct']}% |"

    def driver_row(r):
        return (f"| {r['name']} | {r['op_days']}일 | {r['rest_days']}일 | "
                f"{r['total_cbm']}m³ | {r['avg_cbm_per_day']}m³/일 | "
                f"최대 {r['max_streak']}일 | {r['overbooking']}건 | {r['fatigue_flag']} |")

    gogox_rows = "\n".join(
        f"| {w} | {c}건 |"
        for w, c in zip(r_c["weeks_sorted"], r_c["weekly_counts"])
    ) or "| (데이터 없음) | - |"

    fare_note = (
        f"> 운임 기준: {r_c['fare_source']} ({r_c['fare_sample_n']}건 실측)"
        if r_c["fare_sample_n"] > 0
        else f"> 운임 기준: {r_c['fare_source']} — shipment 운임 백필 완료 시 정밀도 향상"
    )

    if r_c["weeks_to_s1_breakeven"]:
        be_note = f"현재 추세({r_c['slope_per_week']:+}건/주) 지속 시 약 **{r_c['weeks_to_s1_breakeven']}주 후** S1 손익분기 도달 예상"
    elif r_c["s1_saving_per_ship"] <= 0:
        be_note = "GoGoX 단가 ≤ 박종성 한계비용 → S1 내부화 시 비용 증가. 단가 데이터 보강 필요."
    else:
        be_note = f"현재 외주 건수({r_c['monthly_avg']}건/월)가 이미 S1 손익분기({r_c['s1_breakeven']}건/월) 근접 또는 초과"

    lane_note = (
        f"> 내부화 우선 구간: **{r_a['top_roi_zone']}** (CBM당 운임 최고 — 밀도 대비 수익성 우수)"
        if r_a["fare_data_available"]
        else "> ⚠️ 운임 데이터 미집계 — fldRT95SC88KSBATT 백필 완료 후 재실행 시 ROI 산출 가능"
    )

    return f"""# TMS AutoResearch — {week_str} + Iter8 Analysis

> 자동 생성: {date.today().isoformat()} | Iter8: Lane ROI / Driver 피로도 / NPV 실사

---

## 1. Iter8-A: Lane × CBM 통합 ROI

> 6주 총 배차 CBM: {r_a['total_dispatch_cbm']}m³ | CBM = 배차일지 Total_CBM 비례 배분

| 구간유형 | 건수 | 총 운임 | 추정 CBM | CBM당 운임 | 구성비 |
|---------|------|--------|---------|-----------|-------|
{chr(10).join(lane_row(r) for r in r_a['rows'])}

{lane_note}

---

## 2. Iter8-B: Driver 회전율 / 피로도

> 분석 기간: 6주 | 영업일 기준: {r_b['biz_days']}일 (공휴일 제외)

| 기사 | 운행일 | 휴식일 | 총 CBM | 일평균 CBM | 최장 연속 | 오버부킹 | 피로도 |
|------|-------|-------|-------|-----------|---------|---------|------|
{chr(10).join(driver_row(r) for r in r_b['rows'])}

> 연속 운행 판정: 금→월(3일 이하 간격) 포함. ⚠️ = 5일 이상 연속 운행.

---

## 3. Iter8-C: GoGoX 외주 추이 + NPV 실사

{fare_note}

### 주별 GoGoX 건수

| 주차 | GoGoX 건수 |
|------|-----------|
{gogox_rows}

- **월 평균: {r_c['monthly_avg']}건/월** | 주간 추세: {r_c['slope_per_week']:+}건/주

### NPV 재산출 (실운임 기반)

> GoGoX 평균 단가: **{r_c['avg_gogox_fare']:,}원/건** | 박종성 한계비용: **{r_c['avg_park_fare']:,}원/트립**
> ※ Iter7의 15,000원/건 고정단가 가정 폐기 — 실거리 기준 차등요율 반영

| 시나리오 | 건당 절감 | 12개월 NPV | 손익분기 |
|---------|---------|----------|--------|
| S1 (박종성 추가 운행) | {r_c['s1_saving_per_ship']:,}원/건 | **{r_c['s1_npv_12m']:,}원** | {r_c['s1_breakeven']}건/월 |
| S2 (신규 기사 채용) | {r_c['avg_gogox_fare']:,}원/건 | **{r_c['s2_npv_12m']:,}원** | {r_c['s2_breakeven']}건/월 |

> {be_note}

---

## 4. Iter9 후보

1. **운임 백필 완성** — fldRT95SC88KSBATT 누락 shipment 보완 → Lane ROI 정밀도 향상
2. **GoGoX 볼륨 임계점 모니터링** — S1 손익분기({r_c['s1_breakeven']}건/월) 도달 시 즉시 내부화 검토
3. **기사 배차 최적화** — CBM 불균형 해소 (일평균 CBM 편차 최소화)
"""


# ── 저장 ──────────────────────────────────────────────────────────────────────

def _save_outputs(week_str: str, report_body: str) -> str:
    VAULT_OUTPUTS.mkdir(parents=True, exist_ok=True)
    report_name = f"TMS-{week_str}-Iter8.md"
    report_path = VAULT_OUTPUTS / report_name
    report_path.write_text(report_body, encoding="utf-8")

    entry_header = f"## [{date.today().isoformat()}] ITER8 | {week_str}"
    log_entry = f"\n{entry_header}\n\n**상태:** 완료\n\n### 산출물\n- [{report_name}](../outputs/{report_name})\n"
    if VAULT_LOG.exists():
        existing = VAULT_LOG.read_text(encoding="utf-8")
        if entry_header not in existing:
            VAULT_LOG.write_text(existing + log_entry, encoding="utf-8")

    new_row = f"| [{report_name}](../outputs/{report_name}) | Iter8 분석 | {date.today().isoformat()} | 완료 |\n"
    if VAULT_INDEX.exists():
        idx = VAULT_INDEX.read_text(encoding="utf-8")
        if report_name not in idx:
            VAULT_INDEX.write_text(idx + new_row, encoding="utf-8")

    return str(report_path)


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="TMS AutoResearch Iter8 Analyzer")
    parser.add_argument("--weeks",   type=int,          default=6)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not os.environ.get("AIRTABLE_PAT"):
        print("[ERROR] AIRTABLE_PAT 환경변수 없음")
        sys.exit(1)

    today            = date.today()
    last_week_anchor = today - timedelta(days=today.weekday() + 7)
    iso              = last_week_anchor.isocalendar()
    week_str         = f"{iso[0]}-W{iso[1]:02d}"

    data = pull_iter8_data(args.weeks)

    if args.dry_run:
        print("\n[DRY-RUN] 데이터 확인 완료. 출력 없음.")
        return

    print("\n[ITER8] 분석 시작")
    r_a = analyze_iter8_lane_roi(data)
    print(f"  Iter8-A: {len(r_a['rows'])}개 구간 | 운임 데이터: {r_a['fare_data_available']}")

    r_b = analyze_iter8_driver_fatigue(data)
    print(f"  Iter8-B: {len(r_b['rows'])}명 기사 | 영업일 {r_b['biz_days']}일")

    r_c = analyze_iter8_outsourcing_trend(data)
    print(f"  Iter8-C: GoGoX {r_c['monthly_avg']}건/월 | S1 손익분기 {r_c['s1_breakeven']}건/월")

    report = _build_report(week_str, r_a, r_b, r_c)
    saved  = _save_outputs(week_str, report)
    print(f"\n[DONE] 리포트: {saved}")


if __name__ == "__main__":
    main()
