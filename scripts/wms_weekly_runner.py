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

# SAP EWM 테이블
TBL_GR      = "tblcuauVL8DxlxdjL"  # WMS_GoodsReceipt
TBL_LEDGER  = "tblpe5o5UfVRtQkrt"  # WMS_InventoryLedger
TBL_WAVE    = "tblX8yotSTOlfaoeI"  # WMS_Wave
TBL_PICKING = "tblIcdVfnm88JlpMf"  # WMS_PickingTask

# movement 필드 ID
FLD_MOV_PURPOSE    = "fldFRNxG1pNooEOC7"  # 이동목적 (singleSelect)
FLD_MOV_CREATED    = "fldDXUAF4JOORLJ2v"  # 생성일자 (dateTime)
FLD_MOV_QC_STATUS  = "fldLpIDZBmq9jKYCh"  # 검수 status (multilineText)
FLD_MOV_QC_INBOUND = "fldwIZKLqVgYFq0M0"  # 입고자재_검수 status (multilineText)
FLD_MOV_ISSUE_CAT  = "fldudxogG53VjQmvX"  # 이슈카테고리 (multipleSelects)
FLD_MOV_NO_ARRIVE  = "fldjZYoxIe1GI4DGa"  # 미입하 발생이력 (checkbox)
FLD_MOV_EXP_DATE   = "fldlpGxylH72YPs7V"  # 입하예상일 (date)
FLD_MOV_ACT_DATE   = "flduN8khmYwdn7uVD"  # 실제입하일 (date)
FLD_MOV_SUPPLIER   = "fldqGAjPo0SHxx2qW"  # (파트너)발주협력사명 텍스트

# SAP GoodsReceipt 필드 ID
FLD_GR_SUPPLIER    = "fldaxIoZHjqyvTEpm"  # supplier_name
FLD_GR_STATUS      = "fldBdtbA9xyH8INvZ"  # status (singleSelect)
FLD_GR_PROMISED    = "fldArJVYkAO3kTN4j"  # promised_date (date)
FLD_GR_RECEIVED    = "fldOoesot79LX4YEg"  # received_at (dateTime)
FLD_GR_DOCK_MIN    = "fldcfP2SIzTtTZzZp"  # dock_to_stock_min (number)
FLD_GR_QC_RESULT   = "fldtvkxQelsElZTL9"  # qc_result (singleSelect)
FLD_GR_DEFECT_CODE = "fldDAXIN3eK5KiszX"  # defect_code (singleSelect)

# SAP InventoryLedger 필드 ID
FLD_LED_STOCK_TYPE  = "fldSr2c9ZfFpZGppj"  # stock_type (singleSelect)
FLD_LED_QTY_HAND    = "fldzW3RLidcGq2fMM"  # qty_on_hand (number)
FLD_LED_QTY_AVAIL   = "fldmLAKI2MKy1oNFM"  # qty_available (number)

# SAP Wave/PickingTask 필드 ID
FLD_WAVE_STATUS       = "fldiemiuNUtedJsE1"  # status (singleSelect)
FLD_WAVE_TOTAL_LINES  = "fldKsY7KulOf80Dud"  # total_lines (number)
FLD_WAVE_PICKED_LINES = "fldlZPFKLmmAtpojQ"  # picked_lines (number)
FLD_WAVE_ACCURACY     = "fldQb960UOwCfuhhp"  # picking_accuracy_pct (number)
FLD_TASK_STATUS       = "fldVvLj54Nx0QthkB"  # status (singleSelect)
FLD_TASK_PLANNED_QTY  = "fldplWTtcG5G0UEU8"  # planned_qty (number)
FLD_TASK_PICKED_QTY   = "fldGfqaFtj3JFWXuS"  # picked_qty (number)
FLD_TASK_ACCURATE     = "fldyMyfB4JyiFhrsJ"  # is_accurate (checkbox)

# 이동목적 QC 분석 대상 (Airtable API는 option name 반환)
MOV_PURPOSE_QC_TARGETS = {"생산산출", "재고생산"}

# Dock-to-Stock 목표: ≤ 480분 (8시간)
DTS_TARGET_MIN = 480

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


# ── STEP 1-B: SAP 데이터 Pull ─────────────────────────────────────────────────
def step_pull_sap_data() -> dict:
    """WMS_GoodsReceipt / WMS_InventoryLedger / WMS_Wave / WMS_PickingTask Pull"""
    print("\n[STEP 1-B] SAP EWM 데이터 Pull")

    # GoodsReceipt — CONFIRMED/QC_FAIL/PARTIAL 전체
    gr_recs = get_all_records(
        TBL_GR,
        fields=[FLD_GR_SUPPLIER, FLD_GR_STATUS, FLD_GR_PROMISED,
                FLD_GR_RECEIVED, FLD_GR_DOCK_MIN, FLD_GR_QC_RESULT, FLD_GR_DEFECT_CODE],
    )

    # InventoryLedger — 전체 원장
    ledger_recs = get_all_records(
        TBL_LEDGER,
        fields=[FLD_LED_STOCK_TYPE, FLD_LED_QTY_HAND, FLD_LED_QTY_AVAIL],
    )

    # Wave — COMPLETED만 (피킹 정확도 계산용)
    wave_recs = get_all_records(
        TBL_WAVE,
        fields=[FLD_WAVE_STATUS, FLD_WAVE_TOTAL_LINES, FLD_WAVE_PICKED_LINES, FLD_WAVE_ACCURACY],
        formula="status='COMPLETED'",
    )

    # PickingTask — 전체 (SHORT 비율 계산용)
    task_recs = get_all_records(
        TBL_PICKING,
        fields=[FLD_TASK_STATUS, FLD_TASK_PLANNED_QTY, FLD_TASK_PICKED_QTY, FLD_TASK_ACCURATE],
    )

    print(f"  WMS_GoodsReceipt: {len(gr_recs)}건")
    print(f"  WMS_InventoryLedger: {len(ledger_recs)}건")
    print(f"  WMS_Wave(COMPLETED): {len(wave_recs)}건")
    print(f"  WMS_PickingTask: {len(task_recs)}건")

    return {
        "gr_recs":     gr_recs,
        "ledger_recs": ledger_recs,
        "wave_recs":   wave_recs,
        "task_recs":   task_recs,
    }


# ── STEP 1: 데이터 Pull ────────────────────────────────────────────────────────
def step_pull_data() -> dict:
    print("\n[STEP 1] 데이터 Pull")

    cutoff_30 = (date.today() - timedelta(days=30)).isoformat()

    # ① 볼륨 트렌드용 — 최근 1000건 (생성일자 최신순)
    mov_vol = get_all_records(
        TBL_MOVEMENT,
        fields=[FLD_MOV_PURPOSE, FLD_MOV_CREATED],
        max_records=1000,
    )
    recent_mov = [
        r for r in mov_vol
        if (r["fields"].get(FLD_MOV_CREATED) or "") >= cutoff_30
    ]

    # ② QC 이슈 proxy — 이슈카테고리 있는 전체 레코드 (필터 pull)
    qc_recs = get_all_records(
        TBL_MOVEMENT,
        fields=[FLD_MOV_PURPOSE, FLD_MOV_ISSUE_CAT],
        formula=f"OR({{이동목적}}='생산산출', {{이동목적}}='재고생산')",
    )

    # ③ 미입하 발생이력 — checkbox=TRUE 레코드만 (필터 pull)
    no_arrive_recs = get_all_records(
        TBL_MOVEMENT,
        fields=[FLD_MOV_NO_ARRIVE, FLD_MOV_EXP_DATE, FLD_MOV_ACT_DATE, FLD_MOV_SUPPLIER],
        formula="{미입하 발생이력}=TRUE()",
    )

    print(f"  movement 볼륨용 (최근 30일): {len(recent_mov)}건 / 전체 {len(mov_vol)}건")
    print(f"  QC 이슈 대상 (생산산출+재고생산): {len(qc_recs)}건")
    print(f"  미입하 발생이력 체크: {len(no_arrive_recs)}건")

    return {
        "movements":       recent_mov,
        "all_movements":   qc_recs,
        "no_arrive_recs":  no_arrive_recs,
    }


# ── STEP 2-A: QC 불량 proxy ───────────────────────────────────────────────────
def analyze_qc_defect(data: dict) -> dict:
    """이동목적(생산산출/재고생산) × 이슈카테고리 multiSelect 기반 QC proxy"""
    all_movements = data["all_movements"]

    by_category: dict[str, int] = {"품질이슈": 0, "수량이슈": 0, "운영이슈": 0}

    target_total = 0
    issue_total = 0

    for rec in all_movements:
        f = rec["fields"]
        purpose_choice = f.get(FLD_MOV_PURPOSE)
        if purpose_choice not in MOV_PURPOSE_QC_TARGETS:
            continue
        target_total += 1

        cats = f.get(FLD_MOV_ISSUE_CAT) or []
        if cats:
            issue_total += 1
            for cat in cats:
                if cat in by_category:
                    by_category[cat] += 1

    issue_rate = round(issue_total / target_total * 100, 1) if target_total else None

    return {
        "target_total": target_total,
        "issue_total":  issue_total,
        "issue_rate":   issue_rate,
        "by_category":  by_category,
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
    """미입하 발생이력 checkbox 기반 공급사별 미입하 건수 + 입하예상일 vs 실제입하일 diff"""
    no_arrive_recs = data["no_arrive_recs"]

    supplier_no_arrive: dict[str, list[int | None]] = {}

    for rec in no_arrive_recs:
        f = rec["fields"]
        if not f.get(FLD_MOV_NO_ARRIVE):
            continue

        supplier = (f.get(FLD_MOV_SUPPLIER) or "협력사 미기재").strip()
        if not supplier:
            supplier = "협력사 미기재"

        exp  = parse_date(f.get(FLD_MOV_EXP_DATE))
        act  = parse_date(f.get(FLD_MOV_ACT_DATE))
        diff = (act - exp).days if (exp and act) else None

        if supplier not in supplier_no_arrive:
            supplier_no_arrive[supplier] = []
        supplier_no_arrive[supplier].append(diff)

    # 공급사별 통계
    supplier_stats: dict[str, dict] = {}
    for sup, diffs in supplier_no_arrive.items():
        measured = [d for d in diffs if d is not None]
        supplier_stats[sup] = {
            "no_arrive_count": len(diffs),
            "measured_count":  len(measured),
            "avg_diff": round(sum(measured) / len(measured), 1) if measured else None,
        }

    # Top 3: 미입하 건수 내림차순
    top_late = sorted(
        supplier_stats.items(),
        key=lambda x: x[1]["no_arrive_count"],
        reverse=True,
    )[:3]

    no_arrive_total = sum(v["no_arrive_count"] for v in supplier_stats.values())
    measured_total  = sum(v["measured_count"]  for v in supplier_stats.values())

    return {
        "supplier_stats":  supplier_stats,
        "top_late":        top_late,
        "no_arrive_total": no_arrive_total,
        "measured_count":  measured_total,
    }


# ── Iter 4: Dock-to-Stock KPI ─────────────────────────────────────────────────
def analyze_dock_to_stock(sap_data: dict) -> dict:
    """WMS_GoodsReceipt.dock_to_stock_min 기반 Dock-to-Stock KPI"""
    gr_recs = sap_data["gr_recs"]

    dts_values: list[float] = []
    within_target = 0

    for rec in gr_recs:
        f = rec["fields"]
        if f.get(FLD_GR_STATUS) not in {"CONFIRMED", "QC_PASS"}:
            continue
        dts = f.get(FLD_GR_DOCK_MIN)
        if dts is None:
            continue
        dts_values.append(float(dts))
        if dts <= DTS_TARGET_MIN:
            within_target += 1

    total = len(dts_values)
    avg_dts   = round(sum(dts_values) / total, 0) if total else None
    target_pct = round(within_target / total * 100, 1) if total else None
    min_dts   = round(min(dts_values), 0) if total else None
    max_dts   = round(max(dts_values), 0) if total else None

    return {
        "total":        total,
        "avg_dts":      avg_dts,
        "min_dts":      min_dts,
        "max_dts":      max_dts,
        "within_target": within_target,
        "target_pct":   target_pct,
    }


# ── Iter 5: 재고 정확도 ────────────────────────────────────────────────────────
def analyze_inventory_accuracy(sap_data: dict) -> dict:
    """WMS_InventoryLedger × WMS_PickingTask 기반 재고 정확도"""
    ledger_recs = sap_data["ledger_recs"]
    task_recs   = sap_data["task_recs"]

    # 재고 원장 집계
    total_locations = len(ledger_recs)
    unrestricted    = sum(1 for r in ledger_recs if r["fields"].get(FLD_LED_STOCK_TYPE) == "UNRESTRICTED")
    total_qty       = sum(r["fields"].get(FLD_LED_QTY_HAND, 0) or 0 for r in ledger_recs)
    avail_qty       = sum(r["fields"].get(FLD_LED_QTY_AVAIL, 0) or 0 for r in ledger_recs)

    # 피킹 정확도 (is_accurate 체크박스 기반)
    task_total    = len(task_recs)
    task_accurate = sum(1 for r in task_recs if r["fields"].get(FLD_TASK_ACCURATE))
    task_short    = sum(1 for r in task_recs if r["fields"].get(FLD_TASK_STATUS) == "SHORT")

    picking_acc_pct = round(task_accurate / task_total * 100, 1) if task_total else None
    short_rate_pct  = round(task_short / task_total * 100, 1) if task_total else None

    return {
        "total_locations":  total_locations,
        "unrestricted":     unrestricted,
        "total_qty":        total_qty,
        "avail_qty":        avail_qty,
        "task_total":       task_total,
        "task_accurate":    task_accurate,
        "task_short":       task_short,
        "picking_acc_pct":  picking_acc_pct,
        "short_rate_pct":   short_rate_pct,
    }


# ── Iter 6: QC 불량코드 Pareto ─────────────────────────────────────────────────
def analyze_qc_pareto(sap_data: dict) -> dict:
    """WMS_GoodsReceipt.defect_code 기반 QC 불량코드 Pareto"""
    gr_recs = sap_data["gr_recs"]

    defect_counts: dict[str, int] = {}
    qc_fail_total = 0
    qc_pass_total = 0
    qc_partial_total = 0

    for rec in gr_recs:
        f = rec["fields"]
        result = f.get(FLD_GR_QC_RESULT)
        if result == "PASS":
            qc_pass_total += 1
        elif result == "FAIL":
            qc_fail_total += 1
        elif result == "PARTIAL":
            qc_partial_total += 1

        code = f.get(FLD_GR_DEFECT_CODE)
        if code:
            defect_counts[code] = defect_counts.get(code, 0) + 1

    total_inspected = qc_pass_total + qc_fail_total + qc_partial_total
    fail_rate = round((qc_fail_total + qc_partial_total) / total_inspected * 100, 1) if total_inspected else None

    top5_defects = sorted(defect_counts.items(), key=lambda x: -x[1])[:5]

    return {
        "total_inspected":  total_inspected,
        "qc_pass":          qc_pass_total,
        "qc_fail":          qc_fail_total,
        "qc_partial":       qc_partial_total,
        "fail_rate":        fail_rate,
        "top5_defects":     top5_defects,
    }


# ── Iter 7: 공급사 납기 준수율 ─────────────────────────────────────────────────
def analyze_supplier_ontime(sap_data: dict) -> dict:
    """WMS_GoodsReceipt.promised_date vs received_at 기반 공급사 납기 준수율"""
    gr_recs = sap_data["gr_recs"]

    supplier_stats: dict[str, dict] = {}

    for rec in gr_recs:
        f = rec["fields"]
        supplier = (f.get(FLD_GR_SUPPLIER) or "미기재").strip()
        promised = parse_date(f.get(FLD_GR_PROMISED))
        received_raw = f.get(FLD_GR_RECEIVED)
        received = parse_date(received_raw) if received_raw else None

        if supplier not in supplier_stats:
            supplier_stats[supplier] = {"total": 0, "ontime": 0, "late": 0}

        supplier_stats[supplier]["total"] += 1
        if promised and received:
            if received <= promised:
                supplier_stats[supplier]["ontime"] += 1
            else:
                supplier_stats[supplier]["late"] += 1

    # 전체 납기 준수율
    total_gr   = sum(v["total"] for v in supplier_stats.values())
    total_on   = sum(v["ontime"] for v in supplier_stats.values())
    overall_pct = round(total_on / total_gr * 100, 1) if total_gr else None

    # 공급사별 정렬 (납기 건수 내림차순)
    ranked = sorted(
        [
            (sup, v, round(v["ontime"] / v["total"] * 100, 1) if v["total"] else None)
            for sup, v in supplier_stats.items()
            if v["total"] >= 2  # 2건 미만은 통계 의미 없어 제외
        ],
        key=lambda x: -x[1]["total"],
    )[:5]

    return {
        "total_gr":    total_gr,
        "total_on":    total_on,
        "overall_pct": overall_pct,
        "ranked":      ranked,
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
    dts = results.get("dts")
    inv = results.get("inv")
    qcp = results.get("qcp")
    sot = results.get("sot")

    # QC 주요 수치
    qc_rate_str = (
        f"{qc['issue_rate']}% ({qc['issue_total']}/{qc['target_total']}건)"
        if qc["issue_rate"] is not None
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

    # 공급사 납기 Top 3 (미입하 건수 내림차순)
    late_lines = ""
    for i, (sup_name, stat) in enumerate(sup["top_late"], 1):
        diff_str = ""
        if stat["avg_diff"] is not None:
            sign = "+" if stat["avg_diff"] > 0 else ""
            diff_str = f", 평균 {sign}{stat['avg_diff']}일"
        late_lines += f"  {i}. {sup_name}: 미입하 {stat['no_arrive_count']}건{diff_str}\n"
    if not late_lines:
        late_lines = "  (데이터 없음)\n"

    # SAP KPI 섹션 빌드
    sap_section = _build_sap_section(dts, inv, qcp, sot)

    # KPI 스냅샷 SAP 행 추가
    dts_snap = f"{dts['avg_dts']:.0f}분 (목표≤{DTS_TARGET_MIN}분 달성 {dts['target_pct']}%)" if dts and dts["avg_dts"] else "데이터 부족"
    inv_snap = f"피킹 정확도 {inv['picking_acc_pct']}% (SHORT {inv['task_short']}건/{inv['task_total']}건)" if inv and inv["picking_acc_pct"] else "데이터 부족"
    qcp_snap = f"QC 불합격률 {qcp['fail_rate']}% ({qcp['qc_fail']+qcp['qc_partial']}/{qcp['total_inspected']}건)" if qcp and qcp["fail_rate"] else "데이터 부족"
    sot_snap = f"공급사 납기 준수율 {sot['overall_pct']}% ({sot['total_on']}/{sot['total_gr']}건)" if sot and sot["overall_pct"] else "데이터 부족"

    report = f"""# WMS Weekly — {week_str}  ({date_range})

> 자동 생성: {date.today().isoformat()} | 볼륨: movement 최근 30일 / QC·납기: 전체 누적
> [AS-IS] 스키마 변경 없음 - 정밀도 제한 있음 | [SAP EWM] 가상 백필 데이터 기반

---

## KPI 스냅샷

| 지표 | 실적 | 비고 |
|------|------|------|
| QC 이슈 proxy | {qc_rate_str} | 생산산출+재고생산 중 이슈카테고리 발생률 |
| 이번 주 입출고 볼륨 | {vol['this_total']}건 (전주 {vol['last_total']}건, WoW {'+' if vol['wow_change'] >= 0 else ''}{vol['wow_change']}건) | movement.이동목적 기준 |
| 미입하 발생이력 | {sup['no_arrive_total']}건 (diff 측정 {sup['measured_count']}건) | 미입하 발생이력 checkbox 기준 |
| **Dock-to-Stock** | **{dts_snap}** | WMS_GoodsReceipt SAP EWM |
| **피킹 정확도** | **{inv_snap}** | WMS_PickingTask SAP EWM |
| **QC 불합격률** | **{qcp_snap}** | WMS_GoodsReceipt SAP EWM |
| **공급사 납기** | **{sot_snap}** | WMS_GoodsReceipt SAP EWM |

---

## Iter 1: 입출고 볼륨 트렌드

이번 주 (`{vol['this_week']}`) 이동목적별 분포:
{volume_lines}

최근 4주 추이:
{recent_trend.rstrip()}

---

## Iter 2: QC 이슈 proxy (이동목적 × 이슈카테고리)

- 생산산출 + 재고생산 총: **{qc['target_total']}건**
- 이슈 발생: **{qc['issue_total']}건** (이슈 proxy율 **{qc['issue_rate']}%**)

| 이슈카테고리 | 건수 |
|------------|------|
| 품질이슈 | {qc['by_category']['품질이슈']}건 |
| 수량이슈 | {qc['by_category']['수량이슈']}건 |
| 운영이슈 | {qc['by_category']['운영이슈']}건 |

> 한계: Phase 1 (W-1 불량코드 마스터) 완료 후 불량코드별 Pareto 가능.

---

## Iter 3: 공급사 납기 proxy (미입하 발생이력)

- 미입하 발생이력 체크 총: **{sup['no_arrive_total']}건**
- diff 측정 가능 (입하예상일+실제입하일 모두 있음): {sup['measured_count']}건

### 미입하 Top 3 협력사
{late_lines.rstrip()}

> 한계: SLA 기준 없어 "지연 여부" 판단 불가. 미입하 건수와 편차값만 제공.

---
{sap_section}
## 다음 주 체크포인트

- [ ] QC 불량 proxy 트렌드 추적 (이번 주 대비 개선/악화)
- [ ] 납기 지연 Top 3 공급사 현황 모니터링
- [ ] 입출고 볼륨 이상치 여부 확인
- [ ] Dock-to-Stock KPI 목표(≤{DTS_TARGET_MIN}분) 달성 여부 확인
- [ ] 피킹 SHORT 발생 로케이션 재고 점검

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


def _build_sap_section(dts, inv, qcp, sot) -> str:
    """Iter 4~7 SAP EWM 섹션 마크다운 빌드"""
    lines = []

    # Iter 4: Dock-to-Stock
    if dts:
        lines.append("## Iter 4: Dock-to-Stock KPI (SAP EWM)")
        lines.append("")
        lines.append(f"- 분석 대상 GR: **{dts['total']}건** (CONFIRMED 기준)")
        lines.append(f"- 평균 Dock-to-Stock: **{dts['avg_dts']:.0f}분**")
        lines.append(f"- 목표(≤{DTS_TARGET_MIN}분) 달성: **{dts['within_target']}건 ({dts['target_pct']}%)**")
        lines.append(f"- 범위: 최소 {dts['min_dts']:.0f}분 ~ 최대 {dts['max_dts']:.0f}분")
        status = "✅ 목표 달성" if (dts['target_pct'] or 0) >= 90 else "⚠️ 목표 미달 (목표: ≥90%)"
        lines.append(f"- 판정: **{status}**")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Iter 5: 재고 정확도
    if inv:
        lines.append("## Iter 5: 재고 정확도 · 피킹 정확도 (SAP EWM)")
        lines.append("")
        lines.append(f"| 지표 | 값 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 재고 원장 로케이션 수 | {inv['total_locations']}건 |")
        lines.append(f"| UNRESTRICTED 재고 | {inv['unrestricted']}로케이션 |")
        lines.append(f"| 총 재고 수량 | {inv['total_qty']:,}개 |")
        lines.append(f"| 가용 재고 수량 | {inv['avail_qty']:,}개 |")
        lines.append(f"| 피킹 태스크 총 | {inv['task_total']}건 |")
        lines.append(f"| 피킹 정확도 | **{inv['picking_acc_pct']}%** |")
        lines.append(f"| SHORT 발생 | {inv['task_short']}건 ({inv['short_rate_pct']}%) |")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Iter 6: QC 불량코드 Pareto
    if qcp:
        lines.append("## Iter 6: QC 불량코드 Pareto (SAP EWM)")
        lines.append("")
        lines.append(f"- 검수 대상 GR: **{qcp['total_inspected']}건**")
        lines.append(f"- PASS: {qcp['qc_pass']}건 / FAIL: {qcp['qc_fail']}건 / PARTIAL: {qcp['qc_partial']}건")
        lines.append(f"- QC 불합격률: **{qcp['fail_rate']}%** (FAIL+PARTIAL)")
        lines.append("")
        if qcp["top5_defects"]:
            lines.append("| 불량코드 | 건수 |")
            lines.append("|---------|------|")
            for code, cnt in qcp["top5_defects"]:
                lines.append(f"| {code} | {cnt}건 |")
        else:
            lines.append("> 불량 없음")
        lines.append("")
        lines.append("---")
        lines.append("")

    # Iter 7: 공급사 납기 준수율
    if sot:
        lines.append("## Iter 7: 공급사 납기 준수율 (SAP EWM)")
        lines.append("")
        lines.append(f"- 전체 납기 준수율: **{sot['overall_pct']}%** ({sot['total_on']}/{sot['total_gr']}건)")
        lines.append("")
        if sot["ranked"]:
            lines.append("| 공급사 | 총 납품 | 준수 | 지연 | 준수율 |")
            lines.append("|--------|--------|------|------|--------|")
            for sup_name, v, pct in sot["ranked"]:
                lines.append(f"| {sup_name} | {v['total']}건 | {v['ontime']}건 | {v['late']}건 | {pct}% |")
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ── STEP 4: log.md 업데이트 ───────────────────────────────────────────────────
def step_update_log(results: dict, report_path: Path, week_str: str) -> None:
    print("\n[STEP 4] log.md 업데이트")

    qc  = results["qc"]
    vol = results["volume"]
    sup = results["supplier"]

    qc_str = (
        f"{qc['issue_rate']}% ({qc['issue_total']}/{qc['target_total']}건)"
        if qc["issue_rate"] is not None else "데이터 부족"
    )

    entry = f"""
## [{date.today().isoformat()}] WEEKLY | 주간 분석 {week_str}

**상태:** 완료

### KPI 스냅샷
- QC 이슈 proxy: {qc_str} (생산산출+재고생산 중 이슈카테고리 발생률)
- 입출고 볼륨: {vol['this_total']}건 (WoW {'+' if vol['wow_change'] >= 0 else ''}{vol['wow_change']}건)
- 미입하 발생이력: {sup['no_arrive_total']}건

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
    data     = step_pull_data()
    sap_data = step_pull_sap_data()

    # 2. 분석
    print("\n[STEP 2] KPI 분석 (AS-IS)")
    qc  = analyze_qc_defect(data)
    vol = analyze_volume_trend(data)
    sup = analyze_supplier_lead_time(data)
    print(f"  QC 이슈 proxy: {qc['issue_rate']}% ({qc['issue_total']}/{qc['target_total']}건)")
    print(f"  볼륨: 이번 주 {vol['this_total']}건 (WoW {'+' if vol['wow_change'] >= 0 else ''}{vol['wow_change']}건)")
    print(f"  미입하 발생이력: {sup['no_arrive_total']}건 (diff 측정 {sup['measured_count']}건)")

    print("\n[STEP 2-SAP] SAP EWM KPI 분석")
    dts = analyze_dock_to_stock(sap_data)
    inv = analyze_inventory_accuracy(sap_data)
    qcp = analyze_qc_pareto(sap_data)
    sot = analyze_supplier_ontime(sap_data)
    print(f"  Dock-to-Stock: 평균 {dts['avg_dts']}분, 목표 달성 {dts['target_pct']}%")
    print(f"  피킹 정확도: {inv['picking_acc_pct']}% (SHORT {inv['task_short']}건)")
    print(f"  QC 불합격률: {qcp['fail_rate']}% ({qcp['qc_fail']+qcp['qc_partial']}/{qcp['total_inspected']}건)")
    print(f"  납기 준수율: {sot['overall_pct']}% ({sot['total_on']}/{sot['total_gr']}건)")

    results = {"qc": qc, "volume": vol, "supplier": sup,
               "dts": dts, "inv": inv, "qcp": qcp, "sot": sot}

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
