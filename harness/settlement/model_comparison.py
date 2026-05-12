"""
두 운임 모델 정확도 비교 — 박종성 기사님 2026년 1월 데이터 기준

모델 A (현재): fare = 55,421 + 831 × (haversine_km × 1.35)
모델 B (Naver 퀵): fare = 100,000 + 166.67×est_time(min) + 2.7×(est_toll+est_fuel) + 45,000

Naver 퀵 파라미터 추정:
  road_km   = haversine × 1.35 (동일 proxy)
  time(min) = road_km / 평균속도 × 60
              - 서울/수도권 단거리(<30km) : 25 km/h (정체 고려)
              - 경기 중거리(30-80km)      : 45 km/h
              - 지방 장거리(>80km)        : 70 km/h
  연료비     = road_km / 10.5 × 1,700 (경유 1,700원/L, 1톤트럭 4등급 10.5km/L)
  통행료     = road_km > 60km 구간만 50원/km 적용 (고속도로 구간 추정)

퀵 계산기 공식 역산 검증:
  입력값: 시간 152분, 통행료 3,900, 연료비 17,062
  → 원가 = 100,000 + 166.67×152 + 2.7×(3,900+17,062) = 181,931
  → 견적가 = 181,931 + 45,000 = 226,931  ✓ (스프레드시트와 일치)
"""

import json
import math
import statistics
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

CACHE_PATH = Path(__file__).parent / "state" / "crossval_cache.json"

# 공식 파라미터
MODEL_A_BASE    = 55_421   # 현재 haversine 기본운임
MODEL_A_KM_RATE = 831      # 현재 km당 운임

NAVER_BASE_FARE   = 100_000  # 기본비
NAVER_TIME_RATE   = 166.67   # 원/분
NAVER_MARGIN_MULT = 2.70     # 1 + 운전마진(170%)
NAVER_SINCERELY   = 45_000   # 신시어리 마진
DIESEL_PER_L      = 1_700    # 경유 가격 (원/L)
FUEL_EFFICIENCY   = 10.5     # km/L (1톤트럭 4등급 평균)
TOLL_PER_KM_LONG  = 50       # 장거리 통행료 추정 (원/km)

# 제외 대상: 다영기획 행 (외주임가공 35K 건들)
EXCLUDE_DEST = ["다영기획"]


def _est_naver(road_km: float) -> int:
    """Naver 퀵 모델: road_km → 견적가"""
    if road_km < 30:
        avg_speed = 25   # 서울 도심 정체
    elif road_km < 80:
        avg_speed = 45   # 경기 혼재
    else:
        avg_speed = 70   # 지방 고속도로 위주

    time_min = road_km / avg_speed * 60
    fuel     = road_km / FUEL_EFFICIENCY * DIESEL_PER_L
    toll     = max(0, road_km - 60) * TOLL_PER_KM_LONG  # 장거리만 통행료
    cost     = NAVER_BASE_FARE + NAVER_TIME_RATE * time_min + NAVER_MARGIN_MULT * (toll + fuel)
    return round(cost + NAVER_SINCERELY)


def _est_current(road_km: float) -> int:
    return round(MODEL_A_BASE + MODEL_A_KM_RATE * road_km)


def pct_err(calc, actual) -> float:
    return (calc - actual) / actual * 100 if actual else 0


def main():
    if not CACHE_PATH.exists():
        print("캐시 없음. crossvalidation.py 먼저 실행하세요.")
        return

    with open(CACHE_PATH, encoding="utf-8") as f:
        records = json.load(f)

    print(f"총 캐시 레코드: {len(records)}")

    # 2026-01-01 이후 + 운송비용 있는 것만
    recs_2026 = [
        r for r in records
        if (r.get("fields", {}).get("fldQvmEwwzvQW95h9") or "") >= "2026-01-01"
        and r.get("fields", {}).get("fldRT95SC88KSBATT")
    ]
    print(f"2026년 박종성 레코드: {len(recs_2026)}")

    # crossval_report에서 이미 계산된 processed results 사용
    report_path = Path(__file__).parent / "state" / "crossval_report.json"
    if not report_path.exists():
        print("crossval_report.json 없음. crossvalidation.py 먼저 실행하세요.")
        return

    with open(report_path, encoding="utf-8") as f:
        report = json.load(f)

    all_processed = report["records"]

    # 2026년 1월 이후만 필터 (date 필드 앞 10자리)
    recs = [
        r for r in all_processed
        if r.get("date", "") >= "2026-01-01"
        and r["fare"] > 0
        and r["road_km"] > 0
        and not any(ex in (r.get("dest") or "") for ex in EXCLUDE_DEST)
    ]
    print(f"분석 대상 (다영기획 제외): {len(recs)}건\n")

    if len(recs) < 10:
        print("데이터 부족 — 전체 기간 데이터 사용")
        recs = [
            r for r in all_processed
            if r["fare"] > 0 and r["road_km"] > 0
            and not any(ex in (r.get("dest") or "") for ex in EXCLUDE_DEST)
        ]
        print(f"  (전체 기간) 분석 대상: {len(recs)}건\n")

    # 모델별 예측값 계산
    for r in recs:
        r["calc_A"] = _est_current(r["road_km"])
        r["calc_B"] = _est_naver(r["road_km"])
        r["err_A"]  = pct_err(r["calc_A"], r["fare"])
        r["err_B"]  = pct_err(r["calc_B"], r["fare"])

    # 전체 MAPE, MAE
    mae_A  = statistics.mean(abs(r["calc_A"] - r["fare"]) for r in recs)
    mae_B  = statistics.mean(abs(r["calc_B"] - r["fare"]) for r in recs)
    mape_A = statistics.mean(abs(r["err_A"]) for r in recs)
    mape_B = statistics.mean(abs(r["err_B"]) for r in recs)

    print("=" * 65)
    print("모델 비교 결과 (2026년 데이터)")
    print("=" * 65)
    print(f"{'지표':<20} {'모델A (haversine현재)':>22} {'모델B (Naver퀵)':>18}")
    print("-" * 65)
    print(f"{'MAE (원)':<20} {mae_A:>22,.0f} {mae_B:>18,.0f}")
    print(f"{'MAPE (%)':<20} {mape_A:>22.1f}% {mape_B:>18.1f}%")
    winner_mae  = "A" if mae_A < mae_B else "B"
    winner_mape = "A" if mape_A < mape_B else "B"
    print(f"\n  MAE 우위: 모델 {winner_mae}  /  MAPE 우위: 모델 {winner_mape}")

    # 거리 구간별 비교
    zones = [
        ("수도권 단거리 (<25km)",  lambda r: r["road_km"] < 25),
        ("경기 중거리 (25-60km)",  lambda r: 25 <= r["road_km"] < 60),
        ("지방 장거리 (60km+)",    lambda r: r["road_km"] >= 60),
    ]

    print("\n" + "=" * 65)
    print("구간별 MAPE 비교")
    print("=" * 65)
    print(f"{'구간':<25} {'건수':>4}  {'모델A':>8}  {'모델B':>8}  {'우위'}")
    print("-" * 65)
    for label, fn in zones:
        sub = [r for r in recs if fn(r)]
        if not sub:
            continue
        mA = statistics.mean(abs(r["err_A"]) for r in sub)
        mB = statistics.mean(abs(r["err_B"]) for r in sub)
        win = "A ✓" if mA < mB else "B ✓"
        print(f"{label:<25} {len(sub):>4}  {mA:>7.1f}%  {mB:>7.1f}%  {win}")

    # 실제 vs 계산 샘플 (지방 장거리만)
    print("\n" + "=" * 65)
    print("지방 장거리 (60km+) 상세 비교")
    print("=" * 65)
    long_recs = sorted([r for r in recs if r["road_km"] >= 60], key=lambda x: x["road_km"])
    print(f"{'SC ID':<13} {'road_km':>7} {'실제fare':>9} {'모델A':>9} {'모델B':>9}  {'errA':>6}  {'errB':>6}")
    print("-" * 65)
    for r in long_recs:
        print(f"{r['sc_id']:<13} {r['road_km']:>6.0f}km "
              f"{r['fare']:>9,} {r['calc_A']:>9,} {r['calc_B']:>9,}  "
              f"{r['err_A']:>+5.0f}%  {r['err_B']:>+5.0f}%")

    # 결론
    print("\n" + "=" * 65)
    print("구조적 차이 분석")
    print("=" * 65)
    seoul_fares = [r["fare"] for r in recs if r["road_km"] < 25]
    if seoul_fares:
        med_s = statistics.median(seoul_fares)
        print(f"  수도권 중간값: {med_s:,.0f}원  — 모델A 예측: {_est_current(15):,.0f}원  / 모델B: {_est_naver(15):,.0f}원")
    long_fares = [r["fare"] for r in recs if r["road_km"] >= 60]
    if long_fares:
        med_l = statistics.median(long_fares)
        km90  = statistics.median(r["road_km"] for r in recs if r["road_km"] >= 60)
        print(f"  지방 중간값:   {med_l:,.0f}원  — 모델A 예측: {_est_current(km90):,.0f}원  / 모델B: {_est_naver(km90):,.0f}원")

    print("\n★ 권고:")
    if mape_A < mape_B:
        print("  전체적으로 현재 haversine 모델(A)이 더 정확합니다.")
        print("  → 수도권 단거리가 건수가 많아 전체 MAPE를 좌우함")
    else:
        print("  전체적으로 Naver 퀵 모델(B)이 더 정확합니다.")
    print("\n  현실적 권고: 구간별 하이브리드")
    print(f"    수도권(<25km):  모델A (simple) — 건수 많고 실제 요율이 낮음")
    print(f"    지방(60km+):   모델B (Naver퀵) or 수동 퀵 요율표 사용")


if __name__ == "__main__":
    main()
