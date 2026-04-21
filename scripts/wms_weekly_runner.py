"""
wms_weekly_runner.py
──────────────────────────────────────────────────────────────────────────────
WMS 주간 AutoResearch 러너 (매주 월요일 실행)

분석 항목 (AS-IS, 스키마 변경 없음):
  1. QC 불량 proxy   — order.표본 검수 결과 + movement.검수 status 텍스트
  2. 입출고 볼륨 트렌드 — movement.이동목적 × 생성일자 주간 집계
  3. 공급사 납기 proxy — order.입고예정일 vs 실제 입고일 diff

사용법:
  python scripts/wms_weekly_runner.py
  python scripts/wms_weekly_runner.py --dry-run   # 분석만, 파일 저장 안 함
"""

import argparse
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

# ── 경로 설정 ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
OUTPUTS_DIR = ROOT / "_AutoResearch" / "WMS" / "outputs"
LOG_PATH = ROOT / "_AutoResearch" / "WMS" / "wiki" / "log.md"
INDEX_PATH = ROOT / "_AutoResearch" / "WMS" / "wiki" / "index.md"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Airtable 상수 ──────────────────────────────────────────────────────────────
BASE_ID = "appLui4ZR5HWcQRri"

TBL_MOVEMENT = "tblwq7Kj5Y9nVjlOw"
TBL_ORDER    = "tblJslWg8sYEdCkXw"

# movement 필드 ID
FLD_MOV_PURPOSE    = "fldFRNxG1pNooEOC7"  # 이동목적 (singleSelect)
FLD_MOV_CREATED    = "fldDXUAF4JOORLJ2v"  # 생성일자 (dateTime)
FLD_MOV_QC_STATUS  = "fldLpIDZBmq9jKYCh"  # 검수 status (multilineText)
FLD_MOV_QC_INBOUND = "fldwIZKLqVgYFq0M0"  # 입고자재_검수 status (multilineText)

# order 필드 ID
FLD_ORD_PLANNED    = "fldjhWR2fGbp8hOn5"  # 입고예정일 (date)
FLD_ORD_ACTUAL     = "fld7NwzcwyjoCldle"  # 실제 입고일 (발주팀 작성) (date)
FLD_ORD_SUPPLIER   = "fldsofqeebz4UnCRN"  # 협력사 (singleLineText)
FLD_ORD_QC_RESULT  = "fldDlQdAT6L25QxEb"  # 표본 검수 결과 (singleSelect)

# QC 불합격 판정 키워드
DEFECT_KEYWORDS = ("불합격", "불량", "반품", "재검", "fail", "reject")

AIRTABLE_PAT = os.environ.get("AIRTABLE_WMS_PAT", os.environ.get("AIRTABLE_PAT", ""))
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
        params: dict = {
            "fields[]": fields,
            "pageSize": 100,
            "returnFieldsByFieldId": "true",
        }
        if offset:
            params["offset"] = offset
        if formula:
            params["filterByFormula"] = formula
        if max_records:
            params["maxRecords"] = max_records
        resp = requests.get(
            f"https://api.airtable.com/v0/{BASE_ID}/{table_id}",
            headers=HEADERS,
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset or (max_records and len(records) >= max_records):
            break
        time.sleep(0.2)
    return records


def parse_date(val: str | None) -> date | None:
    if not val:
        return None
    try:
        return date.fromisoformat(val[:10])
    except ValueError:
        return None


# ── STEP 1: 데이터 Pull ────────────────────────────────────────────────────────
def step_pull_data() -> dict:
    print("\n[STEP 1] 데이터 Pull")

    cutoff_30  = (date.today() - timedelta(days=30)).isoformat()
    cutoff_90  = (date.today() - timedelta(days=90)).isoformat()

    # movement (최근 30일, 생성일자 기준)
    mov_recs = get_all_records(
        TBL_MOVEMENT,
        fields=[FLD_MOV_PURPOSE, FLD_MOV_CREATED, FLD_MOV_QC_STATUS, FLD_MOV_QC_INBOUND],
        max_records=1000,
    )
    recent_mov = [
        r for r in mov_recs
        if (r["fields"].get(FLD_MOV_CREATED) or "") >= cutoff_30
    ]

    # order (전체 fetch 후 Python에서 날짜 필터 — 입고예정일 또는 실제 입고일 기준)
    ord_recs = get_all_records(
        TBL_ORDER,
        fields=[FLD_ORD_PLANNED, FLD_ORD_ACTUAL, FLD_ORD_SUPPLIER, FLD_ORD_QC_RESULT],
        max_records=1000,
    )
    recent_ord = [
        r for r in ord_recs
        if (r["fields"].get(FLD_ORD_PLANNED) or r["fields"].get(FLD_ORD_ACTUAL) or "") >= cutoff_90
    ]

    print(f"  movement (최근 30일): {len(recent_mov)}건 / 전체 {len(mov_recs)}건")
    print(f"  order (최근 90일):    {len(recent_ord)}건 / 전체 {len(ord_recs)}건")

    return {"movements": recent_mov, "orders": recent_ord}


# ── STEP 2-A: QC 불량 proxy ───────────────────────────────────────────────────
def analyze_qc_defect(data: dict) -> dict:
    """order.표본 검수 결과 + movement.검수 status 텍스트 파싱"""
    orders = data["orders"]
    movements = data["movements"]

    # order 기반 — singleSelect
    total_qc = 0
    defect_qc = 0
    for rec in orders:
        result = rec["fields"].get(FLD_ORD_QC_RESULT) or ""
        if result:
            total_qc += 1
            if any(kw in result for kw in DEFECT_KEYWORDS):
                defect_qc += 1

    # movement 기반 — 텍스트 파싱 (fallback 겸 cross-check)
    total_mov_qc = 0
    defect_mov_qc = 0
    for rec in movements:
        for fld in (FLD_MOV_QC_STATUS, FLD_MOV_QC_INBOUND):
            text = (rec["fields"].get(fld) or "").lower()
            if text:
                total_mov_qc += 1
                if any(kw in text for kw in DEFECT_KEYWORDS):
                    defect_mov_qc += 1
                break  # 한 레코드에서 중복 카운트 방지

    defect_rate_order = round(defect_qc / total_qc * 100, 1) if total_qc else None
    defect_rate_mov   = round(defect_mov_qc / total_mov_qc * 100, 1) if total_mov_qc else None

    return {
        "order_total_qc": total_qc,
        "order_defect":   defect_qc,
        "order_defect_rate": defect_rate_order,
        "mov_total_qc":   total_mov_qc,
        "mov_defect":     defect_mov_qc,
        "mov_defect_rate": defect_rate_mov,
    }


# ── STEP 2-B: 입출고 볼륨 트렌드 ──────────────────────────────────────────────
def analyze_volume_trend(data: dict) -> dict:
    """movement.이동목적 × 생성일자 주간 집계"""
    movements = data["movements"]

    weekly: dict[str, dict[str, int]] = {}

    for rec in movements:
        f = rec["fields"]
        created_raw = f.get(FLD_MOV_CREATED) or ""
        d = parse_date(created_raw)
        if not d:
            continue

        iso = d.isocalendar()
        week_key = f"{iso[0]}-W{iso[1]:02d}"

        purpose = (f.get(FLD_MOV_PURPOSE) or "미분류").strip()
        if week_key not in weekly:
            weekly[week_key] = {}
        weekly[week_key][purpose] = weekly[week_key].get(purpose, 0) + 1

    sorted_weeks = sorted(weekly.keys())
    recent_4 = sorted_weeks[-4:] if len(sorted_weeks) >= 4 else sorted_weeks

    # 최근 주간 합계
    this_week = sorted_weeks[-1] if sorted_weeks else "-"
    last_week = sorted_weeks[-2] if len(sorted_weeks) >= 2 else None

    this_total = sum(weekly.get(this_week, {}).values())
    last_total = sum(weekly.get(last_week, {}).values()) if last_week else 0
    wow_change = this_total - last_total

    return {
        "weekly": weekly,
        "recent_4": recent_4,
        "this_week": this_week,
        "this_total": this_total,
        "last_week": last_week,
        "last_total": last_total,
        "wow_change": wow_change,
    }


# ── STEP 2-C: 공급사 납기 proxy ───────────────────────────────────────────────
def analyze_supplier_lead_time(data: dict) -> dict:
    """order.입고예정일 vs 실제 입고일 → 공급사별 평균 납기 편차"""
    orders = data["orders"]

    supplier_diffs: dict[str, list[int]] = {}
    no_actual = 0
    no_planned = 0

    for rec in orders:
        f = rec["fields"]
        planned = parse_date(f.get(FLD_ORD_PLANNED))
        actual  = parse_date(f.get(FLD_ORD_ACTUAL))
        supplier = (f.get(FLD_ORD_SUPPLIER) or "협력사 미기재").strip()

        if not planned:
            no_planned += 1
            continue
        if not actual:
            no_actual += 1
            continue

        diff = (actual - planned).days
        if supplier not in supplier_diffs:
            supplier_diffs[supplier] = []
        supplier_diffs[supplier].append(diff)

    # 공급사별 평균 편차 계산
    supplier_stats: dict[str, dict] = {}
    for sup, diffs in supplier_diffs.items():
        avg = round(sum(diffs) / len(diffs), 1)
        supplier_stats[sup] = {
            "count": len(diffs),
            "avg_diff": avg,
            "late_count": sum(1 for d in diffs if d > 0),
            "early_count": sum(1 for d in diffs if d < 0),
            "on_time_count": sum(1 for d in diffs if d == 0),
        }

    # 납기 지연 Top 3 (평균 편차 내림차순)
    sorted_by_delay = sorted(
        supplier_stats.items(),
        key=lambda x: x[1]["avg_diff"],
        reverse=True,
    )
    top_late = sorted_by_delay[:3]
    top_early = sorted_by_delay[-3:][::-1]

    total_with_data = sum(v["count"] for v in supplier_stats.values())
    overall_avg = (
        round(
            sum(v["avg_diff"] * v["count"] for v in supplier_stats.values())
            / total_with_data,
            1,
        )
        if total_with_data
        else None
    )

    return {
        "supplier_stats": supplier_stats,
        "top_late": top_late,
        "top_early": top_early,
        "total_measured": total_with_data,
        "no_actual": no_actual,
        "no_planned": no_planned,
        "overall_avg_diff": overall_avg,
    }


# ── STEP 3: 리포트 저장 ────────────────────────────────────────────────────────
def step_save_report(
    results: dict,
    week_str: str,
    date_range: str,
    dry_run: bool,
) -> Path | None:
    print("\n[STEP 3] 주간 리포트 저장")

    qc  = results["qc"]
    vol = results["volume"]
    sup = results["supplier"]

    # QC 주요 수치
    qc_rate_str = (
        f"{qc['order_defect_rate']}% (order 표본 검수 결과, {qc['order_total_qc']}건)"
        if qc["order_defect_rate"] is not None
        else f"{qc['mov_defect_rate']}% (movement 검수 status 텍스트, {qc['mov_total_qc']}건)"
        if qc["mov_defect_rate"] is not None
        else "데이터 부족"
    )

    # 볼륨 트렌드
    this_w_detail = vol["weekly"].get(vol["this_week"], {})
    volume_lines = "\n".join(
        f"  {purpose}: {cnt}건" for purpose, cnt in sorted(this_w_detail.items(), key=lambda x: -x[1])
    ) or "  (데이터 없음)"

    recent_trend = ""
    for wk in vol["recent_4"]:
        wk_total = sum(vol["weekly"].get(wk, {}).values())
        recent_trend += f"  {wk}: {wk_total}건\n"

    # 공급사 납기 Top 3 지연
    late_lines = ""
    for sup_name, stat in sup["top_late"]:
        sign = "+" if stat["avg_diff"] > 0 else ""
        late_lines += f"  {sup_name}: 평균 {sign}{stat['avg_diff']}일 ({stat['count']}건)\n"
    if not late_lines:
        late_lines = "  (데이터 없음)\n"

    # 전체 납기 상태
    overall_str = (
        f"{'+' if (sup['overall_avg_diff'] or 0) > 0 else ''}{sup['overall_avg_diff']}일"
        if sup["overall_avg_diff"] is not None
        else "측정 불가"
    )

    report = f"""# WMS Weekly — {week_str}  ({date_range})

> 자동 생성: {date.today().isoformat()} | 분석 기간: movement 최근 30일, order 최근 90일
> [AS-IS] 스키마 변경 없음 - 정밀도 제한 있음

---

## KPI 스냅샷

| 지표 | 실적 | 비고 |
|------|------|------|
| QC 불량 proxy | {qc_rate_str} | 코드 분류 불가, 키워드 파싱 |
| 이번 주 입출고 볼륨 | {vol['this_total']}건 (전주 {vol['last_total']}건, WoW {'+' if vol['wow_change'] >= 0 else ''}{vol['wow_change']}건) | movement.이동목적 기준 |
| 공급사 평균 납기 편차 | {overall_str} | 입고예정일 vs 실제 입고일 |

---

## Iter 1: 입출고 볼륨 트렌드

이번 주 (`{vol['this_week']}`) 이동목적별 분포:
{volume_lines}

최근 4주 추이:
{recent_trend.rstrip()}

---

## Iter 2: QC 불량 proxy

### order 표본 검수 결과 (최근 90일)
- 검수 기록 있는 order: **{qc['order_total_qc']}건**
- 불합격/불량 키워드 포함: **{qc['order_defect']}건**
- 불량 proxy율: **{qc['order_defect_rate']}%**

### movement 검수 status 텍스트 (최근 30일)
- 검수 텍스트 있는 movement: {qc['mov_total_qc']}건
- 불량 키워드 포함: {qc['mov_defect']}건
- 불량 proxy율: {qc['mov_defect_rate']}%

> 한계: 불량 코드 분류 불가. Phase 1 (W-1 불량코드 마스터) 완료 후 정확 집계 가능.

---

## Iter 3: 공급사 납기 proxy

- 납기 측정 가능 order: **{sup['total_measured']}건**
- 실제 입고일 미기재: {sup['no_actual']}건 (분석 제외)
- 입고예정일 미기재: {sup['no_planned']}건 (분석 제외)
- 전체 평균 납기 편차: **{overall_str}** (양수=지연, 음수=조기)

### 납기 지연 Top 3 공급사
{late_lines.rstrip()}

> 한계: SLA 기준 없어 "지연 여부" 판단 불가. 편차값만 제공.

---

## 다음 주 체크포인트

- [ ] QC 불량 proxy 트렌드 추적 (이번 주 대비 개선/악화)
- [ ] 납기 지연 Top 3 공급사 현황 모니터링
- [ ] 입출고 볼륨 이상치 여부 확인

---

## 💬 개선 논의

> Phase 0 착수 판단 기준: 음수재고가 계속 발생하거나 QC proxy율 ≥ 10% 지속 시 SAP_이동유형 필드 추가 우선 검토

---
"""

    if dry_run:
        print("  [dry-run] 파일 저장 건너뜀")
        safe = report[:500].encode("cp949", errors="replace").decode("cp949")
        print(safe + "\n  ...")
        return None

    output_path = OUTPUTS_DIR / f"WMS-{week_str}.md"
    output_path.write_text(report, encoding="utf-8")
    print(f"  저장: {output_path}")
    return output_path


# ── STEP 4: log.md 업데이트 ───────────────────────────────────────────────────
def step_update_log(results: dict, report_path: Path, week_str: str) -> None:
    print("\n[STEP 4] log.md 업데이트")

    qc  = results["qc"]
    vol = results["volume"]
    sup = results["supplier"]

    qc_str = (
        f"{qc['order_defect_rate']}%" if qc["order_defect_rate"] is not None
        else f"{qc['mov_defect_rate']}% (텍스트 파싱)"
    )
    overall_str = (
        f"{'+' if (sup['overall_avg_diff'] or 0) > 0 else ''}{sup['overall_avg_diff']}일"
        if sup["overall_avg_diff"] is not None else "측정 불가"
    )

    entry = f"""
## [{date.today().isoformat()}] WEEKLY | 주간 분석 {week_str}

**상태:** 완료

### KPI 스냅샷
- QC 불량 proxy: {qc_str}
- 입출고 볼륨: {vol['this_total']}건 (WoW {'+' if vol['wow_change'] >= 0 else ''}{vol['wow_change']}건)
- 공급사 평균 납기 편차: {overall_str}

### 산출물
- [{report_path.name}](../outputs/{report_path.name})

### 다음 주 포커스
- 납기 지연 공급사 지속 모니터링
"""

    existing = LOG_PATH.read_text(encoding="utf-8") if LOG_PATH.exists() else ""
    LOG_PATH.write_text(existing + entry, encoding="utf-8")

    # index.md 업데이트
    idx = INDEX_PATH.read_text(encoding="utf-8") if INDEX_PATH.exists() else ""
    new_row = f"| [{report_path.name}](../outputs/{report_path.name}) | 주간 | {date.today().isoformat()} | 완료 |\n"
    if report_path.name not in idx:
        if "(첫 번째 리포트" in idx:
            idx = idx.replace("| (첫 번째 리포트 생성 후 자동 추가) | | | |\n", new_row)
        else:
            idx += new_row
        INDEX_PATH.write_text(idx, encoding="utf-8")

    print("  log.md / index.md 업데이트 완료")


# ── 주차 레이블 계산 ──────────────────────────────────────────────────────────
def _compute_week_label(override_week: str | None = None) -> tuple[str, str]:
    if override_week:
        # 형식: "2026-W16" 또는 "2026-16"
        part = override_week.replace("W", "").replace("-", " ").split()
        if len(part) == 2:
            year, week = int(part[0]), int(part[1])
        else:
            raise ValueError(f"--week 형식 오류: '{override_week}' → 예: 2026-W16")
        monday = date.fromisocalendar(year, week, 1)
        friday = date.fromisocalendar(year, week, 5)
        week_id    = f"{year}-W{week:02d}"
        date_range = f"{monday.strftime('%m/%d')}~{friday.strftime('%m/%d')}"
        return week_id, date_range

    today = date.today()
    # 직전 ISO 주(월~금) 계산
    iso_year, iso_week, iso_dow = today.isocalendar()
    # 이번 주 월요일에서 7일 전 = 직전 주 월요일
    prev_monday = today - timedelta(days=iso_dow - 1 + 7)
    prev_friday = prev_monday + timedelta(days=4)
    p_year, p_week, _ = prev_monday.isocalendar()
    week_id    = f"{p_year}-W{p_week:02d}"
    date_range = f"{prev_monday.strftime('%m/%d')}~{prev_friday.strftime('%m/%d')}"
    return week_id, date_range


# ── 메인 ───────────────────────────────────────────────────────────────────────
def main(dry_run: bool, override_week: str | None = None) -> None:
    if not AIRTABLE_PAT:
        print("[ERROR] AIRTABLE_WMS_PAT (또는 AIRTABLE_PAT) 환경변수 없음. .env 파일 확인")
        sys.exit(1)

    week_id, date_range = _compute_week_label(override_week)
    print(f"\n{'='*60}")
    print(f"WMS 주간 AutoResearch | {week_id} ({date_range})")
    print(f"{'='*60}")

    # 1. 데이터 Pull
    data = step_pull_data()

    # 2. 분석
    print("\n[STEP 2] KPI 분석")
    qc  = analyze_qc_defect(data)
    vol = analyze_volume_trend(data)
    sup = analyze_supplier_lead_time(data)
    print(f"  QC 불량 proxy: order {qc['order_defect_rate']}% / movement {qc['mov_defect_rate']}%")
    print(f"  볼륨: 이번 주 {vol['this_total']}건 (WoW {'+' if vol['wow_change'] >= 0 else ''}{vol['wow_change']}건)")
    print(f"  공급사 평균 납기 편차: {sup['overall_avg_diff']}일 ({sup['total_measured']}건 측정)")

    results = {"qc": qc, "volume": vol, "supplier": sup}

    # 3. 리포트 저장
    report_path = step_save_report(results, week_id, date_range, dry_run)

    # 4. log 업데이트
    if not dry_run and report_path:
        step_update_log(results, report_path, week_id)

    print(f"\n{'='*60}")
    print("WMS 주간 분석 완료")
    if report_path:
        print(f"리포트: {report_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WMS 주간 AutoResearch 러너")
    parser.add_argument("--dry-run", action="store_true", help="분석만, 파일 저장 안 함")
    parser.add_argument("--week", default=None, help="분석 주차 지정 (예: 2026-W16). 생략 시 직전 주 자동 계산")
    args = parser.parse_args()
    main(args.dry_run, args.week)
