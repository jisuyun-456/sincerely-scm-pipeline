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

AIRTABLE_PAT = os.environ.get("AIRTABLE_PAT", "")
HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_PAT}",
    "Content-Type": "application/json",
}


# ── Airtable 헬퍼 ──────────────────────────────────────────────────────────────
def get_all_records(table_id: str, fields: list[str]) -> list[dict]:
    records, offset = [], None
    while True:
        params: dict = {"fields[]": fields, "pageSize": 100, "returnFieldsByFieldId": "true"}
        if offset:
            params["offset"] = offset
        resp = requests.get(
            f"https://api.airtable.com/v0/{BASE_ID}/{table_id}",
            headers=HEADERS, params=params,
        )
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records


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

    # 배차일지 (최근 30일)
    dispatch_recs = get_all_records(TBL_DISPATCH, [
        "fldZh2mZDIPQXfOcO",  # 날짜
        "fldyQAoRZFn6oeQ0E",  # 차량이용률(%)
        "fldVJoKjjzcwpHIHC",  # Total_CBM
        "fldwrsxDL2VFdmUKo",  # 오버부킹
    ])

    # OTIF (전체)
    otif_recs = get_all_records(TBL_OTIF, [
        "fldoUQOue0umGJ2xk",  # On_Time
        "fldiFhyU1k9YsnoGh",  # In_Full
        "fldRrWN15iV9BoToc",  # OTIF_Score
        "fldZJD4YRYg8Mr6yi",  # 납기차이일
    ])

    print(f"  Shipment(최근30일): {len(recent_ships)}건")
    print(f"  배차일지(최근30일): {len(dispatch_recs)}건")
    print(f"  OTIF(전체): {len(otif_recs)}건")

    return {
        "shipments": recent_ships,
        "dispatches": dispatch_recs,
        "otifs": otif_recs,
        "all_shipments": ship_recs,
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


def analyze_iter2_utilization(data: dict) -> dict:
    """Iteration 2: 차량이용률"""
    dispatches = data["dispatches"]
    rates = []
    overbooking_count = 0

    for rec in dispatches:
        f = rec["fields"]
        rate_raw = f.get("fldyQAoRZFn6oeQ0E")
        overbook = f.get("fldwrsxDL2VFdmUKo")

        if rate_raw is not None:
            try:
                # formula 결과가 문자열 "%XX" 또는 숫자일 수 있음
                rate_str = str(rate_raw).replace("%", "").strip()
                rates.append(float(rate_str))
            except (ValueError, TypeError):
                pass
        if overbook and str(overbook).lower() not in ("false", "0", ""):
            overbooking_count += 1

    avg_rate = sum(rates) / len(rates) if rates else 0
    min_rate = min(rates) if rates else 0
    max_rate = max(rates) if rates else 0
    below_target = sum(1 for r in rates if r < 70)

    return {
        "total_days": len(dispatches),
        "avg_utilization": round(avg_rate, 1),
        "min_utilization": round(min_rate, 1),
        "max_utilization": round(max_rate, 1),
        "below_70pct_days": below_target,
        "overbooking_count": overbooking_count,
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
    """Iteration 4: OTIF 실측 전환 현황"""
    otifs = data["otifs"]
    ships = data["all_shipments"]

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

    return {
        "total_otif_records": len(otifs),
        "on_time_rate": round(on_time_count / total_otif * 100, 1),
        "in_full_rate": round(in_full_count / total_otif * 100, 1),
        "avg_otif_score": round(sum(otif_scores) / len(otif_scores) * 100, 1) if otif_scores else 0,
        "avg_delay_days": round(sum(delay_days) / len(delay_days), 1) if delay_days else 0,
        "proxy_conversion_rate": conversion_rate,
    }


# ── STEP 4: 리포트 저장 ────────────────────────────────────────────────────────
def step_save_report(results: dict, week_str: str) -> Path:
    print("\n[STEP 4] 주간 리포트 저장")
    r1 = results["iter1"]
    r2 = results["iter2"]
    r3 = results["iter3"]
    r4 = results["iter4"]
    bf = results["backfill"]

    # 이모지 없이 심플하게
    util_status = "달성" if r2["avg_utilization"] >= 70 else "미달"
    otif_status = "달성" if r4["on_time_rate"] >= 90 else "미달"

    report = f"""# TMS 주간 리포트 — {week_str}

> 생성: {date.today().isoformat()} | 기간: 최근 30일 기준

---

## KPI 요약

| 지표 | 실적 | 목표 | 상태 |
|------|------|------|------|
| 차량이용률 (평균) | {r2["avg_utilization"]}% | ≥70% | {util_status} |
| OTIF On-Time율 | {r4["on_time_rate"]}% | ≥90% | {otif_status} |
| In-Full율 | {r4["in_full_rate"]}% | ≥95% | - |
| 약속납기일 실측 전환율 | {r4["proxy_conversion_rate"]}% | 100% | - |

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

## Iteration 2: 차량이용률

- 분석 기간: {r2["total_days"]}일
- 평균 이용률: **{r2["avg_utilization"]}%** (범위: {r2["min_utilization"]}~{r2["max_utilization"]}%)
- 70% 미달 일수: {r2["below_70pct_days"]}일
- 오버부킹 발생: {r2["overbooking_count"]}건

> 목표 70% {'달성중' if r2['avg_utilization'] >= 70 else f'미달 — {70 - r2["avg_utilization"]:.1f}%p 개선 필요'}

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

---

## 이번 주 백필

- 약속납기일 업데이트: {bf["backfill_count"]}건{"(dry-run)" if bf["dry_run"] else ""}

---

## 다음 주 체크포인트

- [ ] 차량이용률 {'개선 방안 검토' if r2["avg_utilization"] < 70 else '유지 모니터링'}
- [ ] OTIF {'원인 분석' if r4["on_time_rate"] < 90 else '목표 달성 유지'}
- [ ] 약속납기일 전환율 {'개선 (구간유형/배송방식 매핑 확인)' if r4["proxy_conversion_rate"] < 90 else '100% 유지'}
"""

    output_path = OUTPUTS_DIR / f"week_{week_str}.md"
    output_path.write_text(report, encoding="utf-8")
    print(f"  저장: {output_path}")
    return output_path


# ── STEP 5: log.md 업데이트 ───────────────────────────────────────────────────
def step_update_log(results: dict, report_path: Path, week_str: str) -> None:
    print("\n[STEP 5] log.md 업데이트")
    r2 = results["iter2"]
    r4 = results["iter4"]

    entry = f"""
## [{date.today().isoformat()}] WEEKLY | 주간 분석 {week_str}

**상태:** 완료

### KPI 스냅샷
- 차량이용률: {r2["avg_utilization"]}% (목표 ≥70%)
- OTIF On-Time: {r4["on_time_rate"]}% (목표 ≥90%)
- 약속납기일 전환율: {r4["proxy_conversion_rate"]}%

### 산출물
- [{report_path.name}](../outputs/{report_path.name})

### 다음 주 포커스
- {'차량이용률 개선' if r2["avg_utilization"] < 70 else 'OTIF 실측 전환 완료' if r4["proxy_conversion_rate"] < 100 else '현상 유지 + 심화 분석'}
"""

    existing = LOG_PATH.read_text(encoding="utf-8") if LOG_PATH.exists() else ""
    LOG_PATH.write_text(existing + entry, encoding="utf-8")

    # index.md 업데이트
    idx = INDEX_PATH.read_text(encoding="utf-8") if INDEX_PATH.exists() else ""
    new_row = f"| [{report_path.name}](../outputs/{report_path.name}) | 주간 | {date.today().isoformat()} | 완료 |\n"
    # 테이블 헤더 뒤에 삽입
    if "| (미생성)" in idx:
        idx = idx.replace("| (미생성) iter1", new_row + "| (미생성) iter1")
    else:
        idx += new_row
    INDEX_PATH.write_text(idx, encoding="utf-8")

    print("  log.md / index.md 업데이트 완료")


# ── 메인 ───────────────────────────────────────────────────────────────────────
def main(dry_run: bool) -> None:
    if not AIRTABLE_PAT:
        print("[ERROR] AIRTABLE_PAT 환경변수 없음. .env 파일 확인")
        sys.exit(1)

    week_str = date.today().strftime("%Y%m%d")
    print(f"\n{'='*60}")
    print(f"TMS 주간 AutoResearch | {week_str}")
    print(f"{'='*60}")

    # 1. 백필
    bf_result = step_backfill(dry_run)

    # 2. 데이터 Pull
    data = step_pull_data()

    # 3. 분석
    print("\n[STEP 3] Iteration 분석")
    r1 = analyze_iter1_volume(data)
    r2 = analyze_iter2_utilization(data)
    r3 = analyze_iter3_cost(data)
    r4 = analyze_iter4_otif(data)
    print(f"  Iter1: 볼륨 {r1['total_shipments']}건, 피크 {r1['peak_day']}요일")
    print(f"  Iter2: 평균 이용률 {r2['avg_utilization']}%, 오버부킹 {r2['overbooking_count']}건")
    print(f"  Iter3: 배송방식 {len(r3['by_method'])}종")
    print(f"  Iter4: OTIF On-Time {r4['on_time_rate']}%, 전환율 {r4['proxy_conversion_rate']}%")

    results = {"backfill": bf_result, "iter1": r1, "iter2": r2, "iter3": r3, "iter4": r4}

    # 4. 리포트 저장
    report_path = step_save_report(results, week_str)

    # 5. log.md 업데이트
    step_update_log(results, report_path, week_str)

    print(f"\n{'='*60}")
    print("주간 분석 완료")
    print(f"리포트: {report_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TMS 주간 AutoResearch 러너")
    parser.add_argument("--dry-run", action="store_true", help="백필 dry-run 모드")
    args = parser.parse_args()
    main(args.dry_run)
