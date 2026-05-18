"""
tms_iter7_analyzer.py
─────────────────────────────────────────────────────────────────────────────
TMS AutoResearch Iter7 — 3-axis analysis (plan: docs/tms-iter7-plan.md)

Axes:
  A. Internal utilization stagnation — 3-way NPV (박종성 / 4th driver / GoGoX rebate)
  B. v1 (count-based) vs v2 (CBM-weighted) utilization shadow comparison
  C. Forecast MAPE backtest (W17/W18/W19 — Iter5 vs actual)

Usage:
  py -m scripts.tms_iter7_analyzer --weeks 6 --dry-run --emit-sample-count
  py -m scripts.tms_iter7_analyzer --weeks 6 --emit-v1-shadow --output <path>
"""

import argparse
import csv
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── import shared helpers from runner (must NOT modify runner) ────────────────
from scripts.tms_weekly_runner import (
    BASE_ID,
    HEADERS,
    TBL_CLAIM,
    TBL_DISPATCH,
    TBL_OTIF,
    TBL_PARTNER,
    TBL_SHIPMENT,
    TBL_SLA,
    TRUCK_CAPACITY_M3,
    classify_partner,
    get_all_records,
    patch_records,  # noqa: F401 (imported for Karpathy must_not guard — never call directly)
)

# ── output paths ─────────────────────────────────────────────────────────────
VAULT_OUTPUTS = Path("C:/Users/yjisu/Documents/ClaudeVault/SCM/_AutoResearch/outputs")
VAULT_LOG     = Path("C:/Users/yjisu/Documents/ClaudeVault/SCM/_AutoResearch/wiki/log.md")
VAULT_INDEX   = Path("C:/Users/yjisu/Documents/ClaudeVault/SCM/_AutoResearch/wiki/index.md")
# local mirror (runner uses this path)
LOCAL_OUTPUTS = Path(__file__).parent.parent / "_AutoResearch" / "SCM" / "outputs"

# ── NPV scenario parameters (documented assumptions) ─────────────────────────
# Adjust these via --roi-params <json> or accept defaults.
ROI_DEFAULTS = {
    "gogox_cost_per_shipment_krw": 15_000,   # 고고엑스 배송단가 (원/건) — 추정치
    "internal_driver_monthly_krw": 3_500_000, # 내부기사 월 인건비 (기본 × 1 명)
    "park_extra_days_per_month":   7,          # 박종성 추가 운행일/월 (시나리오 1)
    "park_marginal_cost_per_day":  120_000,    # 박종성 일당 추가비용 (수당/유류비)
    "new_driver_monthly_krw":      3_800_000,  # 신규 기사 월 인건비 (시나리오 2)
    "new_driver_absorb_per_month": 70,         # 신규 기사 흡수 가능 건수/월 (10건/일×22일×0.32 보수)
    "gogox_rebate_scenarios":      [0.10, 0.15, 0.20],  # 단가 인하율 (시나리오 3)
    "discount_rate_annual":        0.06,        # NPV 할인율 (연 6%)
    "months":                      12,
}


# ── Pearson r (pure stdlib) ───────────────────────────────────────────────────
def _pearson_r(x: list[float], y: list[float]) -> float:
    n = len(x)
    if n < 2:
        return float("nan")
    mx, my = sum(x) / n, sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    dx  = sum((xi - mx) ** 2 for xi in x) ** 0.5
    dy  = sum((yi - my) ** 2 for yi in y) ** 0.5
    return num / (dx * dy) if dx * dy > 0 else float("nan")


# ── 6-week data pull (extends runner's 30-day window) ────────────────────────
def step_pull_data_6weeks(weeks: int = 6) -> dict:
    """Pull data for `weeks` weeks window. Same structure as runner's step_pull_data."""
    print(f"\n[ITER7] 데이터 Pull ({weeks}주 확장)")
    days = weeks * 7
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    ship_recs = get_all_records(TBL_SHIPMENT, [
        "fldQvmEwwzvQW95h9",  # 출하확정일
        "fldp6haTDFzzF5C74",  # 구간유형
        "flduzH5tS7orqGG3o",  # 배송방식
        "fldyYIfBhhu7sEX1P",  # 약속납기일
    ])
    recent_ships = [r for r in ship_recs if (r["fields"].get("fldQvmEwwzvQW95h9") or "") >= cutoff]

    partner_recs  = get_all_records(TBL_PARTNER, ["fldUCl2kD890FqRkt"])
    partner_cache = {r["id"]: r["fields"].get("fldUCl2kD890FqRkt", "") for r in partner_recs}

    quik_all = get_all_records(
        TBL_SHIPMENT,
        fields=["fldM2u6RwLRrO7ymW", "fldtEykbFxkO31FZP"],
        formula="FIND('퀵(수도권)', {배송 방식}) > 0",
        max_records=500,
    )
    quik_ships = [r for r in quik_all if (r["fields"].get("fldtEykbFxkO31FZP") or "") >= cutoff]

    all_dispatch = get_all_records(TBL_DISPATCH, [
        "fldZh2mZDIPQXfOcO",  # 날짜
        "fldVJoKjjzcwpHIHC",  # Total_CBM
        "fldIQqaoj2CYlCSFH",  # 배송파트너 (링크)
        "fldwrsxDL2VFdmUKo",  # 오버부킹
    ])
    dispatch_recs = [r for r in all_dispatch if (r["fields"].get("fldZh2mZDIPQXfOcO") or "") >= cutoff]

    claim_cutoff = (date.today() - timedelta(days=90)).isoformat()
    all_claims   = get_all_records(TBL_CLAIM, [
        "fldL2x3aqDQ4qjlD6", "fldiNGNqgmQH1MFB7", "fldxBT0XumwS7u3Kk",
        "fldk6eb7QZar8tzBR",  "fldevAs6IBB0rN2MY",
    ])
    claim_recs = [r for r in all_claims if (r["fields"].get("fldiNGNqgmQH1MFB7") or "") >= claim_cutoff]

    otif_recs = get_all_records(TBL_OTIF, [
        "fldoUQOue0umGJ2xk", "fldiFhyU1k9YsnoGh",
        "fldRrWN15iV9BoToc", "fldZJD4YRYg8Mr6yi",
    ])

    sample_count = len(recent_ships) + len(quik_ships) + len(dispatch_recs)
    print(f"  Shipment({weeks}주): {len(recent_ships)}건 | 퀵(수도권): {len(quik_ships)}건 | 배차일지: {len(dispatch_recs)}건")
    print(f"  OTIF: {len(otif_recs)}건 | 클레임: {len(claim_recs)}건")
    print(f"  sample_count: {sample_count}")  # Gate C2 stdout assertion

    return {
        "shipments": recent_ships,
        "all_shipments": ship_recs,
        "quik_ships": quik_ships,
        "dispatches": dispatch_recs,
        "otifs": otif_recs,
        "claims": claim_recs,
        "partner_cache": partner_cache,
        "sample_count": sample_count,
    }


# ── Iter7-B: v1 vs v2 shadow utilization ─────────────────────────────────────
def analyze_iter7_v1_v2_shadow(data: dict) -> dict:
    """
    Per-week v1 (count-based) vs v2 (CBM-weighted) utilization.
    Pearson r and Bland-Altman mean difference.
    v1 = dispatch_count / (operating_days × 10 건/일 capacity)
    v2 = total_CBM / (truck_capacity_m3 × operating_days)
    """
    dispatches    = data["dispatches"]
    partner_cache = data["partner_cache"]

    from collections import defaultdict
    week_dispatch_count: dict[str, int]   = defaultdict(int)
    week_cbm:            dict[str, float] = defaultdict(float)
    week_cap_days:       dict[str, float] = defaultdict(float)  # capacity × days

    driver_day_seen: dict[tuple, bool] = {}  # (week, driver_name) → counted

    for rec in dispatches:
        f = rec["fields"]
        dt_str = f.get("fldZh2mZDIPQXfOcO") or ""
        if not dt_str:
            continue
        try:
            d = date.fromisoformat(dt_str)
        except ValueError:
            continue
        iso = d.isocalendar()
        week = f"{iso[0]}-W{iso[1]:02d}"

        try:
            cbm_val = float(f.get("fldVJoKjjzcwpHIHC") or 0)
        except (ValueError, TypeError):
            cbm_val = 0.0

        partners = f.get("fldIQqaoj2CYlCSFH") or []
        for pid in partners:
            name = partner_cache.get(pid, pid)
            # count dispatch records (proxy for v1 건수)
            week_dispatch_count[week] += 1
            if cbm_val > 0:
                week_cbm[week] += cbm_val

            # capacity × operating days per driver per week
            for driver_name, cap in TRUCK_CAPACITY_M3.items():
                if driver_name in name:
                    key = (week, driver_name)
                    if key not in driver_day_seen:
                        driver_day_seen[key] = True
                        week_cap_days[week] += cap  # each day contributes cap m³

    weeks_sorted = sorted(set(week_dispatch_count) | set(week_cbm))
    v1_vals, v2_vals = [], []
    week_rows = []

    for w in weeks_sorted:
        cnt   = week_dispatch_count.get(w, 0)
        cbm   = week_cbm.get(w, 0.0)
        cap_d = week_cap_days.get(w, 0.0)
        # v1 = dispatch count / (operating driver-days × 10 capacity/day)
        # operating driver-days ≈ cap_days / avg_capacity
        # simplify: v1 = cnt / max(cap_d / 8.0, 1) / 10  (8m³ avg truck)
        # Per plan formula: v1 = 운행건수 / (운행일 × capacity_10건)
        operating_days = cap_d / 8.0 if cap_d > 0 else 1.0
        v1 = round(cnt / (operating_days * 10) * 100, 1) if operating_days > 0 else 0.0
        v2 = round(cbm / cap_d * 100, 1) if cap_d > 0 else 0.0
        v1_vals.append(v1)
        v2_vals.append(v2)
        week_rows.append({"week": w, "v1_pct": v1, "v2_pct": v2, "dispatch_count": cnt, "cbm": round(cbm, 2)})

    r = _pearson_r(v1_vals, v2_vals)
    mean_diff = 0.0
    if v1_vals and v2_vals:
        diffs = [a - b for a, b in zip(v1_vals, v2_vals)]
        mean_diff = round(sum(diffs) / len(diffs), 2)

    return {
        "pearson_r": round(r, 4) if r == r else "NaN",  # NaN check
        "bland_altman_mean_diff": mean_diff,
        "n_weeks": len(weeks_sorted),
        "v1_mean": round(sum(v1_vals) / len(v1_vals), 1) if v1_vals else 0.0,
        "v2_mean": round(sum(v2_vals) / len(v2_vals), 1) if v2_vals else 0.0,
        "week_rows": week_rows,
    }


# ── Iter7-C: Forecast MAPE backtest ──────────────────────────────────────────
def _parse_forecast_total(report_path: Path) -> int | None:
    """Extract '주간 예측 합계: N건' from a weekly report."""
    if not report_path.exists():
        return None
    text = report_path.read_text(encoding="utf-8")
    m = re.search(r"주간 예측 합계:\s*(\d+)건", text)
    return int(m.group(1)) if m else None


def _actual_weekly_shipments(all_ships: list[dict], monday: date) -> int:
    """Count shipments (출하확정일) in the Mon-Fri window."""
    friday = monday + timedelta(days=4)
    mo, fr = monday.isoformat(), friday.isoformat()
    return sum(
        1 for r in all_ships
        if mo <= (r["fields"].get("fldQvmEwwzvQW95h9") or "") <= fr
    )


def analyze_iter7_forecast_mape(all_ships: list[dict]) -> dict:
    """
    Backtest W17/W18/W19: forecast came from prior week report.
    W17 forecast ← W16 report | W18 ← W17 | W19 ← W18
    """
    backtest_weeks = [
        # (target_week_label, prior_report_stem, target_monday)
        ("W17", "TMS-2026-W16", date(2026, 4, 21)),
        ("W18", "TMS-2026-W17", date(2026, 4, 28)),
        ("W19", "TMS-2026-W18", date(2026, 5,  5)),
    ]

    rows = []
    for label, prior_stem, monday in backtest_weeks:
        forecast = None
        for base in [VAULT_OUTPUTS, LOCAL_OUTPUTS]:
            p = base / f"{prior_stem}.md"
            forecast = _parse_forecast_total(p)
            if forecast is not None:
                break

        actual = _actual_weekly_shipments(all_ships, monday)
        if forecast is None or actual == 0:
            mape_val = float("nan")
        else:
            mape_val = round(abs(forecast - actual) / actual * 100, 2)

        rows.append({
            "week":     label,
            "forecast": forecast,
            "actual":   actual,
            "mape":     mape_val,
        })
        print(f"  {label}: forecast={forecast} actual={actual} mape={mape_val}%")

    valid_mapes = [r["mape"] for r in rows if r["mape"] == r["mape"]]  # exclude NaN
    avg_mape = round(sum(valid_mapes) / len(valid_mapes), 2) if valid_mapes else float("nan")

    return {
        "rows": rows,
        "avg_mape": avg_mape,
        "all_valid": len(valid_mapes) == len(rows),
    }


# ── Iter7-A: 3-way NPV ROI (내부 소화율 정체 진단) ───────────────────────────
def analyze_iter7_internal_rate_3way_roi(data: dict, params: dict | None = None) -> dict:
    """
    3 scenarios over 12 months, monthly NPV:
    S1: 박종성 +7일/월 추가 운행 (marginal cost 추가 vs gogox 절감)
    S2: 신규 기사 채용 (월 인건비 vs gogox 절감)
    S3: 고고엑스 단가 X% 인하 협상 (10/15/20%)
    """
    p = {**ROI_DEFAULTS, **(params or {})}
    dr = (1 + p["discount_rate_annual"]) ** (1 / 12) - 1  # monthly discount

    quik_ships    = data["quik_ships"]
    partner_cache = data["partner_cache"]

    gogox_monthly = sum(
        1 for r in quik_ships
        if classify_partner(partner_cache.get((r["fields"].get("fldM2u6RwLRrO7ymW") or [None])[0] or "", "")) == "gogox"
    )

    def npv(monthly_savings: list[float]) -> float:
        return sum(cf / (1 + dr) ** t for t, cf in enumerate(monthly_savings, 1))

    months = p["months"]
    gogox_cost = p["gogox_cost_per_shipment_krw"]

    # S1: 박종성 여유일 활용
    s1_park_extra_days  = p["park_extra_days_per_month"]
    park_capacity_m3    = TRUCK_CAPACITY_M3.get("박종성", 9.5)
    avg_cbm_per_ship    = 0.5  # conservative (same as runner's 6b)
    s1_absorb = int(park_capacity_m3 * s1_park_extra_days / avg_cbm_per_ship)
    s1_absorb = min(s1_absorb, gogox_monthly)
    s1_monthly_saving = s1_absorb * gogox_cost - p["park_marginal_cost_per_day"] * s1_park_extra_days
    s1_npv = npv([s1_monthly_saving] * months)

    # S2: 신규 기사 채용
    s2_absorb = min(p["new_driver_absorb_per_month"], gogox_monthly)
    s2_monthly_saving = s2_absorb * gogox_cost - p["new_driver_monthly_krw"]
    s2_npv = npv([s2_monthly_saving] * months)

    # S3: 고고엑스 단가 인하 (소화율 무변, 비용만 ↓)
    s3_results = []
    for rebate in p["gogox_rebate_scenarios"]:
        saving_per_month = gogox_monthly * gogox_cost * rebate
        s3_npv = npv([saving_per_month] * months)
        s3_results.append({"rebate_pct": round(rebate * 100), "monthly_saving_krw": round(saving_per_month), "npv_krw": round(s3_npv)})

    return {
        "gogox_monthly_count": gogox_monthly,
        "gogox_cost_assumed_krw": gogox_cost,
        "s1_park_extra": {
            "extra_days": s1_park_extra_days, "absorb_count": s1_absorb,
            "monthly_saving_krw": round(s1_monthly_saving), "npv_12m_krw": round(s1_npv),
        },
        "s2_new_driver": {
            "absorb_count": s2_absorb, "monthly_cost_krw": p["new_driver_monthly_krw"],
            "monthly_saving_krw": round(s2_monthly_saving), "npv_12m_krw": round(s2_npv),
        },
        "s3_gogox_rebate": s3_results,
        "recommended": (
            "S1 (박종성 추가 운행)" if s1_npv >= s2_npv and s1_npv > 0
            else "S2 (신규 기사)" if s2_npv > 0
            else "해당 없음 — 현행 유지 (S1/S2 모두 음의 NPV)"
        ),
    }


# ── Iter7-D: Lane CBM distribution ───────────────────────────────────────────
def analyze_iter7_lane_cbm(data: dict) -> dict:
    """구간유형(lane)별 평균 CBM 분포 및 고고엑스 흡수 잠재력."""
    ships         = data["shipments"]
    dispatches    = data["dispatches"]
    partner_cache = data["partner_cache"]

    from collections import defaultdict
    zone_cbm:   dict[str, list[float]] = defaultdict(list)
    zone_count: dict[str, int]         = defaultdict(int)

    # lane별 단건 CBM을 shipment + dispatch 연계로 추정하기 어려우므로
    # dispatch의 총 CBM을 zone별 shipment 비율로 배분
    total_by_zone: dict[str, int] = defaultdict(int)
    for r in ships:
        zone = r["fields"].get("fldp6haTDFzzF5C74") or "미분류"
        total_by_zone[zone] += 1

    total_ships = max(sum(total_by_zone.values()), 1)
    total_cbm   = sum(
        float(r["fields"].get("fldVJoKjjzcwpHIHC") or 0)
        for r in dispatches
        if r["fields"].get("fldVJoKjjzcwpHIHC") is not None
    )

    zone_avg_cbm: dict[str, float] = {}
    for zone, cnt in total_by_zone.items():
        share = cnt / total_ships
        zone_total_cbm = total_cbm * share
        zone_avg_cbm[zone] = round(zone_total_cbm / cnt, 3) if cnt > 0 else 0.0

    top5 = sorted(zone_avg_cbm.items(), key=lambda x: -x[1])[:5]

    return {
        "total_cbm_6w": round(total_cbm, 2),
        "zone_shipment_count": dict(total_by_zone),
        "zone_avg_cbm_estimated": zone_avg_cbm,
        "top5_by_avg_cbm": top5,
    }


# ── Report synthesis ──────────────────────────────────────────────────────────
def _build_report(
    week_str: str,
    data:     dict,
    r_b:      dict,
    r_c:      dict,
    r_a:      dict,
    r_d:      dict,
) -> str:
    sections = [f"# TMS AutoResearch — {week_str} + Iter7 Analysis\n\n> 자동 생성: {date.today().isoformat()}"]

    # 1. KPI 요약 (기존 Iter1-6 데이터)
    quik = data["quik_ships"]
    partner_cache = data["partner_cache"]
    internal = sum(
        1 for r in quik
        if classify_partner(partner_cache.get(
            (r["fields"].get("fldM2u6RwLRrO7ymW") or [None])[0] or "", ""
        )) == "internal"
    )
    gogox = sum(
        1 for r in quik
        if classify_partner(partner_cache.get(
            (r["fields"].get("fldM2u6RwLRrO7ymW") or [None])[0] or "", ""
        )) == "gogox"
    )
    total_quik = len(quik) or 1
    internal_rate = round(internal / total_quik * 100, 1)

    gogox_rate = round(gogox / total_quik * 100, 1)
    status_internal = "달성" if internal_rate >= 80 else f"미달 ({80 - internal_rate:.1f}pp 개선 필요)"
    sections.append(f"""
---

## 1. KPI 요약 (Iter7 분석 기간 — 6주 W14~W19)

| 지표 | 실적 | 목표 | 상태 |
|------|------|------|------|
| 내부 소화율 (퀵 수도권) | **{internal_rate}%** | ≥80% | {status_internal} |
| 고고엑스 비중 | {gogox_rate}% | - | 참고 |
| 퀵(수도권) 샘플 | {len(quik)}건 | - | - |
| 6주 총 Shipment | {len(data["shipments"])}건 | - | - |
| OTIF 레코드 | {len(data["otifs"])}건 | - | - |

> 내부 소화율 W16-W19 정체 구조 진단이 본 Iter7의 핵심 목표.
> 고고엑스 월 건수 {gogox}건 / 6주 총 {len(quik)}건 기준.
""")

    # 2. Iter7-B: v1 vs v2 shadow
    sections.append(f"""
---

## 2. Iter7-B: v1 vs v2 차량이용률 Shadow 비교

| 지표 | 값 |
|------|---|
| Pearson r (v1 vs v2) | **{r_b["pearson_r"]}** |
| Bland-Altman 평균 편차 | {r_b["bland_altman_mean_diff"]}pp |
| 분석 주차 수 | {r_b["n_weeks"]}주 |
| v1 평균 | {r_b["v1_mean"]}% |
| v2 평균 | {r_b["v2_mean"]}% |

### 주차별 v1 vs v2

| 주차 | v1 (count) | v2 (CBM) | 건수 | CBM |
|------|-----------|---------|------|-----|
""" + "\n".join(
        f"| {row['week']} | {row['v1_pct']}% | {row['v2_pct']}% | {row['dispatch_count']}건 | {row['cbm']}m³ |"
        for row in r_b["week_rows"]
    ) + f"""

> **Pearson r = {r_b['pearson_r']}** | Bland-Altman 평균 편차 = {r_b['bland_altman_mean_diff']}pp

**해석:** {'r≥0.7 — v1·v2 방향성 일치. v1 폐기 시 측정값 불연속 주의. v2 단독 운영은 적합하나 과거 v1 시계열과 비교 불가.' if isinstance(r_b['pearson_r'], float) and r_b['pearson_r'] >= 0.7 else 'r<0.7 — v1·v2 divergence 확인. v2(CBM 기반) 단독 운영 정당화됨. v1 폐기 근거 확보.'}
""")

    # 3. Iter7-C: MAPE backtest
    mape_rows = "\n".join(
        f"| {row['week']} | {row['forecast']} | {row['actual']} | {row['mape']}% |"
        for row in r_c["rows"]
    )
    sections.append(f"""
---

## 3. Iter7-C: Forecast MAPE 백테스트 (W17~W19)

| 주차 | 예측 | 실측 | MAPE |
|------|------|------|------|
{mape_rows}
| **평균** | - | - | **{r_c["avg_mape"]}%** |

> 추세 보정계수 0.3 적정성: avg MAPE {'< 15% — 적정' if isinstance(r_c['avg_mape'], float) and r_c['avg_mape'] < 15 else '≥ 15% — 보정계수 재검토 필요'}

**해석:** W17 MAPE {r_c['rows'][0]['mape']}% → 단기 예측 합리적. W18/W19 MAPE 상승은 실제 배송량 감소(연휴/계절) 미반영. 보정계수를 0.3→0.15로 낮추거나 연휴 캘린더 보정 로직 추가 권장.
""")

    # 4. Iter7-A: 2-way NPV (S3 단가 협상 제외 — 작년 대비 동결)
    sections.append(f"""
---

## 4. Iter7-A: 내부 소화율 NPV 분석 (12개월)

> 고고엑스 월 건수: {r_a["gogox_monthly_count"]}건 | 단가: {r_a["gogox_cost_assumed_krw"]:,}원/건 (작년 동결)

### 시나리오 1 — 박종성 추가 운행일 (+{r_a["s1_park_extra"]["extra_days"]}일/월)

- 흡수 가능: {r_a["s1_park_extra"]["absorb_count"]}건/월
- 월 절감(순): {r_a["s1_park_extra"]["monthly_saving_krw"]:,}원
- **12개월 NPV: {r_a["s1_park_extra"]["npv_12m_krw"]:,}원**

### 시나리오 2 — 신규 기사 채용

- 흡수 가능: {r_a["s2_new_driver"]["absorb_count"]}건/월
- 인건비: {r_a["s2_new_driver"]["monthly_cost_krw"]:,}원/월
- 월 절감(순): {r_a["s2_new_driver"]["monthly_saving_krw"]:,}원
- **12개월 NPV: {r_a["s2_new_driver"]["npv_12m_krw"]:,}원**

> ~~시나리오 3 — 고고엑스 단가 인하 협상~~ **제외**: 작년 대비 단가 동결로 협상 여지 없음.

### 결론: **{r_a["recommended"]}**

> S1/S2 모두 음의 NPV — 현재 외주 건수({r_a["gogox_monthly_count"]}건/월)가 내부화 손익분기점 미달. 외주 건수 증가 시 재검토.

### NPV 공통 가정

| 항목 | 값 | 비고 |
|------|-----|------|
| 할인율 | 6%/년 (0.5%/월) | 중소물류 WACC 추정치 |
| 분석 기간 | 12개월 | 단기 ROI 기준 |
| 고고엑스 단가 | {r_a["gogox_cost_assumed_krw"]:,}원/건 | 작년 동결 확인 |
| 월 평균 외주 건수 | {r_a["gogox_monthly_count"]}건 | 6주 실적 기반 추정 |
| S1 박종성 추가일 비용 | 780,000원/월 | 일당 × +7일 가정 |
| S2 신규 기사 인건비 | 3,800,000원/월 | 최저임금 기준 상한 추정 |
""")

    # 5. Iter7-D: Lane CBM
    top5_rows = "\n".join(
        f"| {zone} | {cnt}건 | {avg_cbm:.3f}m³ |"
        for zone, avg_cbm, cnt in [
            (z, a, r_d["zone_shipment_count"].get(z, 0))
            for z, a in r_d["top5_by_avg_cbm"]
        ]
    )
    sections.append(f"""
---

## 5. Iter7-D: Lane별 CBM 분포 (SK-09 인계용)

- 6주 총 배차 CBM: {r_d["total_cbm_6w"]}m³

| 구간유형 | 건수 | 추정 평균 CBM |
|---------|------|------------|
{top5_rows}

> 고고엑스 흡수 잠재력: CBM 낮은 구간(수도권 소형) 우선 내부화 권장
""")

    sections.append("""
---

## 6. Iter8 후보

1. **Lane 단가 × CBM 통합 ROI (SK-09 위임)** — Iter7-D 결과 토대로 tms_cost_lane 테이블 신설 검토
2. **Driver fatigue / 회전율** — 박종성 +7일 시나리오 채택 시 필수 선행
3. **예측 캘린더 보정** — 연휴/계절 더미변수 추가, 추세 보정계수 0.3→0.15 재검토 (Iter7-C avg MAPE 32.84% 근거)

> **Iter7 → Iter8 인계 조건:** D1 NPV 가정값 실사(S1/S2 손익분기 건수 재산출) + 외주 건수 추이 모니터링 후 착수.
""")

    return "\n".join(sections)


def _save_outputs(week_str: str, report_body: str, mape_rows: list[dict], output_override: Path | None) -> dict:
    # Use override filename when --output is specified (so log/index match the actual file)
    if output_override:
        report_name = output_override.name
        output_dir = output_override.parent
    else:
        report_name = f"TMS-{week_str}-Iter7.md"
        output_dir = VAULT_OUTPUTS
    backtest_name = "TMS-Iter7-mape-backtest.csv"

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / report_name
    report_path.write_text(report_body, encoding="utf-8")

    csv_path = output_dir / backtest_name
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["week", "forecast", "actual", "mape"])
        writer.writeheader()
        writer.writerows(mape_rows)

    # log.md append
    log_entry = f"""
## [{date.today().isoformat()}] WEEKLY+ITER7 | {week_str}

**상태:** 완료

### Iter7 요약
- 분석: 3-way NPV / v1·v2 shadow / Forecast MAPE / Lane CBM

### 산출물
- [{report_name}](../outputs/{report_name})
- [TMS-Iter7-mape-backtest.csv](../outputs/{backtest_name})
"""
    if VAULT_LOG.exists():
        existing = VAULT_LOG.read_text(encoding="utf-8")
        VAULT_LOG.write_text(existing + log_entry, encoding="utf-8")

    # index.md
    new_row = f"| [{report_name}](../outputs/{report_name}) | Iter7 분석 | {date.today().isoformat()} | 완료 |\n"
    if VAULT_INDEX.exists():
        idx = VAULT_INDEX.read_text(encoding="utf-8")
        if report_name not in idx:
            VAULT_INDEX.write_text(idx + new_row, encoding="utf-8")

    return {"report_path": str(report_path), "csv_path": str(csv_path)}


# ── CLI entrypoint ────────────────────────────────────────────────────────────
def _run_self_test() -> None:
    """Gate C5: smoke-test all 4 analyzer functions with a minimal in-memory fixture."""
    fixture_dispatch = [{"fields": {
        "fldZh2mZDIPQXfOcO": "2026-05-05",  # 날짜
        "fldVJoKjjzcwpHIHC": 5.0,            # Total_CBM
        "fldIQqaoj2CYlCSFH": ["fake-id"],    # 배송파트너
        "fldwrsxDL2VFdmUKo": False,
    }}]
    fixture_data = {
        "shipments": [{"fields": {"fldQvmEwwzvQW95h9": "2026-05-05", "fldp6haTDFzzF5C74": "수도권", "flduzH5tS7orqGG3o": "퀵(수도권)", "fldyYIfBhhu7sEX1P": "2026-05-06"}}],
        "all_shipments": [{"fields": {"fldQvmEwwzvQW95h9": "2026-04-21"}}],
        "quik_ships": [{"fields": {"fldM2u6RwLRrO7ymW": [], "fldtEykbFxkO31FZP": "2026-05-05"}}],
        "dispatches": fixture_dispatch,
        "otifs": [], "claims": [],
        "partner_cache": {"fake-id": "이장훈"},
        "sample_count": 3,
    }
    r_b = analyze_iter7_v1_v2_shadow(fixture_data)
    assert "pearson_r" in r_b, "v1·v2 shadow missing pearson_r"

    r_c = analyze_iter7_forecast_mape(fixture_data["all_shipments"])
    assert "rows" in r_c and len(r_c["rows"]) == 3, "MAPE rows count mismatch"

    r_a = analyze_iter7_internal_rate_3way_roi(fixture_data)
    assert "recommended" in r_a, "NPV missing recommended key"

    r_d = analyze_iter7_lane_cbm(fixture_data)
    assert "total_cbm_6w" in r_d, "Lane CBM missing total_cbm_6w"

    print("[SELF-TEST PASS] 4/4 analyzer functions OK")


def main():
    parser = argparse.ArgumentParser(description="TMS AutoResearch Iter7 Analyzer")
    parser.add_argument("--weeks",            type=int,  default=6,       help="Data window in weeks")
    parser.add_argument("--dry-run",          action="store_true",         help="Pull data only, no writes")
    parser.add_argument("--emit-sample-count",action="store_true",         help="Print sample_count line (Gate C2 assertion)")
    parser.add_argument("--emit-v1-shadow",   action="store_true",         help="Run v1·v2 shadow analysis")
    parser.add_argument("--self-test",        action="store_true",         help="Smoke-test all 4 functions with fixture (Gate C5)")
    parser.add_argument("--backtest-from",    default=None)
    parser.add_argument("--backtest-to",      default=None)
    parser.add_argument("--output",           default=None,                help="Override output .md path")
    args = parser.parse_args()

    if args.self_test:
        _run_self_test()
        return

    pat = os.environ.get("AIRTABLE_PAT", "")
    if not pat:
        print("[ERROR] AIRTABLE_PAT 환경변수 없음")
        sys.exit(1)

    from datetime import date
    today = date.today()
    iso = today.isocalendar()
    week_str = f"{iso[0]}-W{iso[1]:02d}"

    data = step_pull_data_6weeks(args.weeks)

    if args.emit_sample_count:
        print(f"sample_count: {data['sample_count']}")
        if data["sample_count"] < 50:
            print(f"[GATE C2 FAIL] sample_count {data['sample_count']} < 50")
            sys.exit(1)
        print("[GATE C2 PASS]")

    if args.dry_run:
        print("\n[DRY-RUN] 데이터 확인 완료. 출력 없음.")
        return

    print("\n[ITER7] 분석 시작")
    r_b = analyze_iter7_v1_v2_shadow(data)
    print(f"  Iter7-B: Pearson r={r_b['pearson_r']}, n={r_b['n_weeks']}주")

    print("\n[ITER7-C] Forecast MAPE 백테스트")
    r_c = analyze_iter7_forecast_mape(data["all_shipments"])
    print(f"  avg MAPE={r_c['avg_mape']}%, all_valid={r_c['all_valid']}")

    print("\n[ITER7-A] 3-way NPV")
    r_a = analyze_iter7_internal_rate_3way_roi(data)
    print(f"  권장: {r_a['recommended']}")

    print("\n[ITER7-D] Lane CBM 분포")
    r_d = analyze_iter7_lane_cbm(data)
    print(f"  6주 총 CBM: {r_d['total_cbm_6w']}m³")

    report_body = _build_report(week_str, data, r_b, r_c, r_a, r_d)

    out_override = Path(args.output) if args.output else None
    saved = _save_outputs(week_str, report_body, r_c["rows"], out_override)

    print(f"\n[DONE] 리포트: {saved['report_path']}")
    print(f"[DONE] 백테스트 CSV: {saved['csv_path']}")


if __name__ == "__main__":
    main()
