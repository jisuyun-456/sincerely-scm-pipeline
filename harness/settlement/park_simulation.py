"""
박종성 운임 정합성 시뮬레이션
기간: 2025-01-01 ~ 2026-05-11 (어제 기준, 오늘 자동입력분 제외)
목적: 실제 지급 운임 vs 새 공식(55,421 + 831 × haversine×1.35) 오차 분석

실행: py harness/settlement/park_simulation.py
"""
import json
import math
import statistics
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

REPORT_PATH = Path(__file__).parent / "state" / "crossval_report.json"

# 새 공식 파라미터
BASE_FARE   = 55_421
KM_RATE     = 831
ROAD_FACTOR = 1.35   # haversine → road km

# 분석 기간
DATE_FROM = "2025-01-01"
DATE_TO   = "2026-05-11"   # 어제 기준 (오늘 자동입력분 제외)

# 외주임가공 다영기획 건: 새 공식 대상 아님 → 별도 집계
OUTSOURCE_DEST = "다영기획"


def calc_formula(road_km: float) -> int:
    return round(BASE_FARE + KM_RATE * road_km)


def pct_err(calc: int, actual: int) -> float:
    return (calc - actual) / actual * 100 if actual else 0


def main():
    if not REPORT_PATH.exists():
        print("crossval_report.json 없음 — crossvalidation.py 먼저 실행")
        return

    with open(REPORT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    all_recs = data["records"]

    # 기간 필터
    recs_period = [
        r for r in all_recs
        if DATE_FROM <= r.get("date", "")[:10] <= DATE_TO
        and r["fare"] > 0
        and r["road_km"] > 0
    ]

    # 외주임가공 분리
    outsource = [r for r in recs_period if OUTSOURCE_DEST in (r.get("dest") or "")]
    normal    = [r for r in recs_period if OUTSOURCE_DEST not in (r.get("dest") or "")]

    print(f"분석 기간: {DATE_FROM} ~ {DATE_TO}")
    print(f"총 레코드 (좌표 추정 성공): {len(recs_period)}건")
    print(f"  일반 건 (새 공식 대상): {len(normal)}건")
    print(f"  다영기획 외주건 (제외): {len(outsource)}건\n")

    # ── 일반 건 오차 계산 ──
    for r in normal:
        r["calc"] = calc_formula(r["road_km"])
        r["err"]  = pct_err(r["calc"], r["fare"])
        r["abs_err"] = abs(r["calc"] - r["fare"])

    fares     = [r["fare"]    for r in normal]
    calcs     = [r["calc"]    for r in normal]
    errs      = [r["err"]     for r in normal]
    abs_errs  = [r["abs_err"] for r in normal]

    mae   = statistics.mean(abs_errs)
    mape  = statistics.mean(abs(e) for e in errs)
    rmse  = math.sqrt(statistics.mean(e**2 for e in abs_errs))
    bias  = statistics.mean(errs)   # +면 공식이 과대, -면 과소
    med_e = statistics.median(errs)

    within_10 = sum(1 for e in errs if abs(e) <= 10) / len(errs) * 100
    within_20 = sum(1 for e in errs if abs(e) <= 20) / len(errs) * 100
    within_30 = sum(1 for e in errs if abs(e) <= 30) / len(errs) * 100

    # R²
    mean_fare = statistics.mean(fares)
    ss_tot = sum((f - mean_fare)**2 for f in fares)
    ss_res = sum((f - c)**2 for f, c in zip(fares, calcs))
    r2     = 1 - ss_res / ss_tot if ss_tot else 0

    print("=" * 60)
    print("전체 오차 통계 (일반 건)")
    print("=" * 60)
    print(f"  건수       : {len(normal):>6}건")
    print(f"  R²         : {r2:>8.3f}  (1.0이 완벽)")
    print(f"  MAE        : {mae:>8,.0f}원  (평균 절대 오차)")
    print(f"  RMSE       : {rmse:>8,.0f}원  (큰 오차 가중)")
    print(f"  MAPE       : {mape:>8.1f}%   (평균 절대 % 오차)")
    print(f"  Bias (편향) : {bias:>+8.1f}%   (+면 공식이 과대추정)")
    print(f"  Median err : {med_e:>+8.1f}%")
    print(f"\n  ±10% 이내  : {within_10:>5.1f}%  ({int(within_10*len(normal)/100)}건)")
    print(f"  ±20% 이내  : {within_20:>5.1f}%  ({int(within_20*len(normal)/100)}건)")
    print(f"  ±30% 이내  : {within_30:>5.1f}%  ({int(within_30*len(normal)/100)}건)")

    # ── 구간별 오차 ──
    zones = [
        ("수도권 단거리 (<25km)",   lambda r: r["road_km"] <  25),
        ("경기 중거리 (25-60km)",   lambda r: 25 <= r["road_km"] < 60),
        ("지방 장거리 (60km+)",     lambda r: r["road_km"] >= 60),
    ]
    print("\n" + "=" * 60)
    print("구간별 오차")
    print("=" * 60)
    print(f"{'구간':<24} {'건수':>4}  {'실제중간값':>10}  {'공식중간값':>10}  {'MAPE':>6}  {'편향':>6}")
    print("-" * 60)
    for label, fn in zones:
        sub = [r for r in normal if fn(r)]
        if not sub:
            continue
        med_f  = statistics.median(r["fare"]   for r in sub)
        med_c  = statistics.median(r["calc"]   for r in sub)
        mape_s = statistics.mean(abs(r["err"]) for r in sub)
        bias_s = statistics.mean(r["err"]      for r in sub)
        print(f"{label:<24} {len(sub):>4}  {med_f:>10,.0f}  {med_c:>10,.0f}  {mape_s:>5.1f}%  {bias_s:>+5.1f}%")

    # ── 월별 추이 ──
    from collections import defaultdict
    monthly: defaultdict[str, list] = defaultdict(list)
    for r in normal:
        m = r["date"][:7]   # YYYY-MM
        monthly[m].append(r)

    print("\n" + "=" * 60)
    print("월별 오차 추이")
    print("=" * 60)
    print(f"{'월':<8} {'건수':>4}  {'실제합계':>10}  {'공식합계':>10}  {'MAPE':>6}  {'편향':>6}")
    print("-" * 60)
    for m in sorted(monthly.keys()):
        sub    = monthly[m]
        sum_f  = sum(r["fare"] for r in sub)
        sum_c  = sum(r["calc"] for r in sub)
        mape_m = statistics.mean(abs(r["err"]) for r in sub)
        bias_m = statistics.mean(r["err"]      for r in sub)
        print(f"{m:<8} {len(sub):>4}  {sum_f:>10,}  {sum_c:>10,}  {mape_m:>5.1f}%  {bias_m:>+5.1f}%")

    # 총계
    total_paid = sum(r["fare"] for r in normal)
    total_calc = sum(r["calc"] for r in normal)
    print("-" * 60)
    print(f"{'합계':<8} {len(normal):>4}  {total_paid:>10,}  {total_calc:>10,}  "
          f"{'±' + f'{mape:.1f}%':>6}  {bias:>+5.1f}%")

    # ── 오차 큰 이상치 TOP 10 ──
    print("\n" + "=" * 60)
    print("오차 TOP 10 (±30% 초과)")
    print("=" * 60)
    outliers = sorted([r for r in normal if abs(r["err"]) > 30], key=lambda x: abs(x["err"]), reverse=True)[:10]
    if outliers:
        print(f"{'SC ID':<13} {'날짜':<11} {'실제fare':>8} {'공식calc':>8} {'err%':>6}  {'목적지'}")
        print("-" * 60)
        for r in outliers:
            dest = (r.get("dest") or "")[:30]
            print(f"{r['sc_id']:<13} {r['date'][:10]:<11} {r['fare']:>8,} {r['calc']:>8,} "
                  f"{r['err']:>+5.0f}%  {dest}")
    else:
        print("  없음 (모든 건 ±30% 이내)")

    # ── 외주임가공 참고 ──
    if outsource:
        ext_fares = [r["fare"] for r in outsource]
        print("\n" + "=" * 60)
        print("참고: 다영기획 외주임가공 건 (새 공식 대상 아님)")
        print("=" * 60)
        print(f"  건수: {len(outsource)}건  실제 중간값: {statistics.median(ext_fares):,.0f}원")
        print(f"  → 이 건들은 _is_outsource() 분기로 70,000/N건 적용")

    # ── 최종 판단 ──
    print("\n" + "=" * 60)
    print("정합성 판단")
    print("=" * 60)
    if mape < 15:
        grade = "✅ 양호 (MAPE <15%)"
    elif mape < 25:
        grade = "⚠ 보통 (MAPE <25%) — 지방 건 개별 확인 권장"
    else:
        grade = "❌ 주의 (MAPE ≥25%) — 공식 재검토 필요"
    print(f"  전체 MAPE {mape:.1f}% → {grade}")
    print(f"  ±20% 이내 {within_20:.1f}% — 자동화 적용 시 {100-within_20:.1f}%건은 수동 검토 권장")
    print(f"\n  ※ 오늘(2026-05-12) 자동입력분은 이 분석에 미포함")
    print(f"     앞으로 자동 입력되는 건들은 이 공식 기준으로 적용됩니다.")


if __name__ == "__main__":
    main()
