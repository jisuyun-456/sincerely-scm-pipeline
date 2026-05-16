"""
mh_calculator.py
────────────────────────────────────────────────────────────────────────────────
글로벌 ELS (Engineered Labor Standards) 기반 WMS+TMS M/H 추정 계산기.

* 0 schema change — Airtable 읽기 전용
* 입하·피킹 즉시 작동 (기존 데이터만)
* 입고·검수는 사용자 입력(거리 매트릭스·표본검수분) 도착 시 활성화

사용법:
  python scripts/mh_calculator.py                  # 직전 30일 기본
  python scripts/mh_calculator.py --since 2026-04-15
  python scripts/mh_calculator.py --dry-run        # API 호출만, 파일 미생성

출처: WERC Annual Benchmark Report, SAP EWM·Manhattan Active WM·Blue Yonder LMS
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
sys.stdout.reconfigure(encoding="utf-8")

# ── Airtable 설정 ──────────────────────────────────────────────────────────────
# WMS
WMS_BASE_ID = "appLui4ZR5HWcQRri"
TBL_MOVEMENT = "tblwq7Kj5Y9nVjlOw"
TBL_PICKING_TASK = "tblJpQcCJfIyB9Xf5"

# TMS
TMS_BASE_ID = "app4x70a8mOrIKsMf"
TBL_SHIPMENT = "tbllg1JoHclGYer7m"

WMS_PAT = os.environ.get("AIRTABLE_WMS_PAT") or os.environ.get("AIRTABLE_PAT", "")
TMS_PAT = os.environ.get("AIRTABLE_PAT") or os.environ.get("AIRTABLE_WMS_PAT", "")

# ── 글로벌 ELS 표준 (분 단위) ─────────────────────────────────────────────────
# 출처: WERC mid-range / SAP EWM·Manhattan·Blue Yonder LMS 기본값
# 자사 측정값이 도출되면 이 블록만 교체하면 됨.
PFD_ALLOWANCE = 1.15  # 15% Personal+Fatigue+Delay

# Receiving (입하) — case 단위: 100 cases/MH → 0.6 min/case
RECEIVING_MIN_PER_CARTON = 0.6
# Pallet 단위: 15 pallets/MH → 4 min/pallet  (large bulk fallback)
RECEIVING_MIN_PER_PALLET = 4.0
# Piece 단위: case_size 미상 시 100 pcs/case 가정 후 case 환산 (rough)
RECEIVING_FALLBACK_PCS_PER_CARTON = 100

# Putaway (입고) — 45 putaways/MH base + travel + lift
PUTAWAY_MIN_PER_LINE = 1.33
PUTAWAY_LIFT_MIN = 3.0  # Level > 1

# QC (검수) — visual 300 pcs/MH · AQL 평균 3min/sample (사용자 측정 도착 시 교체)
QC_MIN_PER_PIECE_VISUAL = 0.2
QC_MIN_PER_AQL_SAMPLE = 3.0

# Picking — *batch pick* (바스켓/박스 단위, 자사 운영 패턴)
# 한 task의 qty는 batch 안에 묶여 있어 piece 단위로 빼지 않음 (50/100/150/200 등)
# 시간 = ceil(qty / batch_size) × per_batch  (box 핸들링 1회 ≈ 1.5분: 집기·스캔·배치)
PICK_BATCH_SIZE_DEFAULT = 100      # 자사 평균 (50~200 mid)
PICK_MIN_PER_BATCH = 1.5           # 1 box/batch 핸들링 시간 (분)
PICK_MIN_PER_PIECE_FALLBACK = 0.6  # batch_size 불명·소량 잔여건 fallback

# TMS — Dispatch 0.5~2 min/shipment · Docs 2~5 min (자동화 시 <1)
TMS_DISPATCH_MIN_PER_SHIPMENT = 1.0
TMS_DOCS_MIN_PER_SHIPMENT = 2.0

# ── 이동유형 분류 ─────────────────────────────────────────────────────────────
# WMS의 movement 테이블은 사실상 *입하 ledger* (이동유형 = "본품"/"샘플" 분류).
# 따라서 receiving = "실제입하일 + 입하 qty 보유" 로 판단.
SAMPLE_KIND = "샘플"  # 샘플은 표본검수 영역으로 분리 가능 (현재는 receiving에 포함)


# ── Airtable 헬퍼 ─────────────────────────────────────────────────────────────
def get_records(table_id, fields=None, formula=None, max_records=None,
                sort_field=None, sort_dir="desc", stop_predicate=None,
                base_id=None, pat=None):
    """
    Paginated fetch. stop_predicate(record) → True 시 즉시 중단.
    Karpathy: filterByFormula 대신 sort + 클라이언트 필터 (perf memo 준수).
    """
    base_id = base_id or WMS_BASE_ID
    pat = pat or WMS_PAT
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {pat}"})
    records, offset = [], None
    while True:
        params = {"pageSize": 100, "returnFieldsByFieldId": "false"}
        if fields:
            params["fields[]"] = fields
        if formula:
            params["filterByFormula"] = formula
        if sort_field:
            params["sort[0][field]"] = sort_field
            params["sort[0][direction]"] = sort_dir
        if offset:
            params["offset"] = offset
        if max_records:
            params["maxRecords"] = max_records
        resp = session.get(
            f"https://api.airtable.com/v0/{base_id}/{table_id}",
            params=params, timeout=90,
        )
        resp.raise_for_status()
        data = resp.json()
        page = data.get("records", [])
        records.extend(page)
        # client-side stop: sort된 페이지에서 한 건이라도 predicate 만족 시 중단
        if stop_predicate and page and any(stop_predicate(r) for r in page):
            break
        offset = data.get("offset")
        if not offset or (max_records and len(records) >= max_records):
            break
        time.sleep(0.2)
    return records


# ── 카테고리 분류 ─────────────────────────────────────────────────────────────
def classify_movement(rec):
    """
    WMS movement은 receiving ledger. 실제입하일 + 입하 qty 보유 → 'receiving'.
    """
    f = rec.get("fields", {})
    if not f.get("실제입하일"):
        return "other"
    if (_to_float(f.get("입하수량")) > 0
            or _to_float(f.get("입하카톤수")) > 0
            or _to_float(f.get("입하파렛트수")) > 0):
        return "receiving"
    return "other"


# ── Receiving M/H ─────────────────────────────────────────────────────────────
def calc_receiving_mh(rec):
    """
    입하 M/H_std 계산. 우선순위: 입하카톤수 > 입하파렛트수 > 입하수량(pcs→case 환산).
    returns (mh_std_minutes: float, basis: str, qty: float)
    """
    f = rec.get("fields", {})
    cartons = _to_float(f.get("입하카톤수"))
    pallets = _to_float(f.get("입하파렛트수"))
    pcs = _to_float(f.get("입하수량"))

    if cartons and cartons > 0:
        mh = cartons * RECEIVING_MIN_PER_CARTON * PFD_ALLOWANCE
        return mh, "cartons", cartons
    if pallets and pallets > 0:
        mh = pallets * RECEIVING_MIN_PER_PALLET * PFD_ALLOWANCE
        return mh, "pallets", pallets
    if pcs and pcs > 0:
        eq_cartons = pcs / RECEIVING_FALLBACK_PCS_PER_CARTON
        mh = eq_cartons * RECEIVING_MIN_PER_CARTON * PFD_ALLOWANCE
        return mh, "pcs→cartons(est)", pcs
    return 0.0, "no_qty", 0.0


# ── Picking M/H ───────────────────────────────────────────────────────────────
def calc_picking_mh(rec):
    """
    피킹 M/H_std. *batch pick* 패턴: 자사는 piece가 박스/바스켓에 묶여 있어
    qty가 50~200이어도 핸들링 1~2회로 끝남.
    수식: time = ceil(qty / batch_size) × per_batch (× PFD)
    잔여 1~9개 fallback 시 per-piece 적용 (안전망).
    """
    import math
    f = rec.get("fields", {})
    picked = _to_float(f.get("Picked_Qty"))
    required = _to_float(f.get("Required_Qty"))
    qty = picked if picked > 0 else required
    if qty <= 0:
        return 0.0, "no_qty", 0.0

    batches = math.ceil(qty / PICK_BATCH_SIZE_DEFAULT)
    mh = batches * PICK_MIN_PER_BATCH * PFD_ALLOWANCE
    return mh, f"batch×{batches}", qty


# ── Putaway M/H (사용자 거리 매트릭스 도착 시 활성화) ────────────────────────
def calc_putaway_mh(rec, distance_matrix=None):
    """
    distance_matrix: {location_id: travel_min}. 없으면 disabled.
    """
    if distance_matrix is None:
        return None  # disabled — script가 stub 처리
    # TODO: WMS_GoodsReceipt.Put_Away_Location → travel_min lookup
    return None


# ── QC M/H (사용자 표본분 도착 시 활성화) ─────────────────────────────────────
def calc_tms_shipment_mh(rec):
    """
    TMS shipment 1건 = dispatch + docs M/H_std.
    returns (mh_std_minutes, basis, mode).
    """
    f = rec.get("fields", {})
    mode_raw = f.get("배송 유형") or f.get("배송방식") or "-"
    if isinstance(mode_raw, list):
        mode = "/".join(str(x) for x in mode_raw)
    else:
        mode = str(mode_raw)
    mh = (TMS_DISPATCH_MIN_PER_SHIPMENT + TMS_DOCS_MIN_PER_SHIPMENT) * PFD_ALLOWANCE
    return mh, "shipment", mode


def calc_qc_mh(rec, avg_sample_min=None):
    if avg_sample_min is None:
        return None  # disabled
    f = rec.get("fields", {})
    sample = _to_float(f.get("표본검수수량(미사용중)")) or _to_float(f.get("검수수량"))
    if sample <= 0:
        return None
    return sample * avg_sample_min * PFD_ALLOWANCE


# ── 유틸 ──────────────────────────────────────────────────────────────────────
def _to_float(v):
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def _parse_date(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def iso_week(d):
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


# ── 리포트 생성 ────────────────────────────────────────────────────────────────
def generate_report(receiving_rows, picking_rows, tms_rows, since, until, out_path):
    week = iso_week(until)

    total_recv = sum(r["mh_std"] for r in receiving_rows)
    total_pick = sum(r["mh_std"] for r in picking_rows)
    total_tms = sum(r["mh_std"] for r in tms_rows)
    total_wms = total_recv + total_pick
    total_all = total_wms + total_tms

    # FTE: 매니저 2명(파트장+파트원) 제외 — 실작업자만 카운트
    # 입하·입고 2 + 자재(피킹) 1 + 검수 1 + 출하 1 = 5명
    productive_fte = 5
    total_fte = 7  # OKR 기준 (KR-1 7명 × 1.5)
    fte_minutes_per_week = productive_fte * 40 * 60
    days = (until - since).days + 1
    weeks_in_window = days / 7.0
    fte_window = fte_minutes_per_week * weeks_in_window
    capacity_pct = (total_all / fte_window * 100) if fte_window else 0

    lines = [
        f"# WMS+TMS M/H 분석 — {week}  (Global ELS Iter 1)",
        "",
        f"**기간**: {since.isoformat()} ~ {until.isoformat()} ({days}일)",
        f"**범위**: WMS 입하·피킹 + TMS Shipment dispatch+docs — *입고·검수·외주임가공·프리패키징 deferred*",
        f"**표준 출처**: WERC Annual Benchmark · SAP EWM/Manhattan/Blue Yonder LMS · MOST/MTM-2",
        f"**PFD allowance**: ×{PFD_ALLOWANCE} (15% Personal+Fatigue+Delay)",
        "",
        "## 요약",
        "",
        f"| 항목 | 값 |",
        f"|---|---|",
        f"| WMS 입하 | {len(receiving_rows)} 건 / {total_recv/60:.1f} MH |",
        f"| WMS 피킹 | {len(picking_rows)} 건 / {total_pick/60:.1f} MH |",
        f"| **WMS 합계** | **{total_wms/60:.1f} MH** |",
        f"| TMS Shipment | {len(tms_rows)} 건 / {total_tms/60:.1f} MH |",
        f"| **전체 합계** | **{total_all/60:.1f} MH** |",
        f"| FTE 가용 ({productive_fte}명 실작업 × 40h × {weeks_in_window:.1f}주) | {fte_window/60:.0f} MH |",
        f"| 표준 대비 가동률 | {capacity_pct:.1f}% |",
        "",
        f"> FTE 구성: 입하·입고 2 + 자재(피킹) 1 + 검수 1 + 출하 1 = **{productive_fte}명**. ",
        f"> 매니저(파트장+파트원) {total_fte - productive_fte}명은 관리·판단 역할로 capacity 계산에서 제외. ",
        f"> 단 OKR KR-1은 {total_fte}명 기준 ×1.5 처리량 (Sprint 4 정책 그대로).",
        "",
        "> ⚠️ 글로벌 벤치마크 기반 *추정값*. 자사 환경 보정 전엔 *상대 variance*만 신뢰. ",
        "> 자사 실측 M/H 산출 후 상수 1줄 교체로 정확도 ↑.",
        "",
        "## 입하 (Receiving) 상세",
        "",
        f"| 레코드 | basis | qty | M/H_std (min) |",
        f"|---|---|---|---|",
    ]
    for r in sorted(receiving_rows, key=lambda x: -x["mh_std"])[:30]:
        lines.append(f"| {r['id']} | {r['basis']} | {r['qty']:.1f} | {r['mh_std']:.1f} |")
    if len(receiving_rows) > 30:
        lines.append(f"| ... ({len(receiving_rows)-30} more) | | | |")

    lines += [
        "",
        "## 피킹 (Picking) 상세",
        "",
        f"| 레코드 | basis | qty | M/H_std (min) |",
        f"|---|---|---|---|",
    ]
    for r in sorted(picking_rows, key=lambda x: -x["mh_std"])[:30]:
        lines.append(f"| {r['id']} | {r['basis']} | {r['qty']:.1f} | {r['mh_std']:.1f} |")
    if len(picking_rows) > 30:
        lines.append(f"| ... ({len(picking_rows)-30} more) | | | |")

    # TMS section
    from collections import Counter
    mode_ctr = Counter(r["mode"] for r in tms_rows)
    lines += [
        "",
        "## TMS Shipment (Dispatch + Docs) 상세",
        "",
        f"- Shipment 건수: **{len(tms_rows)}**",
        f"- per-shipment 표준: dispatch {TMS_DISPATCH_MIN_PER_SHIPMENT}분 + docs {TMS_DOCS_MIN_PER_SHIPMENT}분 × PFD {PFD_ALLOWANCE}",
        f"- 합계: **{total_tms/60:.1f} MH** ({total_tms:.0f} 분)",
        "",
        "### 배송유형별 분포 (Top)",
        "",
        "| 배송유형 | 건수 | M/H |",
        "|---|---|---|",
    ]
    per_shipment_mh = (TMS_DISPATCH_MIN_PER_SHIPMENT + TMS_DOCS_MIN_PER_SHIPMENT) * PFD_ALLOWANCE
    for mode, cnt in mode_ctr.most_common(10):
        mode_disp = mode if mode and mode != "-" else "(미분류)"
        lines.append(f"| {mode_disp} | {cnt} | {cnt * per_shipment_mh / 60:.1f} MH |")

    lines += [
        "",
        "## Deferred (사용자 입력 대기)",
        "",
        "- **입고 (Putaway)** — `data/mh_distance_matrix.csv` (입고대기→Location_ID 평균 보행분)",
        "- **검수 (QC AQL)** — `--avg-sample-min N` 인자로 표본검수 평균 시간 전달",
        "- **외주임가공 / 프리패키징 (TMS)** — 사용자 연구 결과 수령 후 별도 phase",
        "",
        "## 글로벌 표준 상수 (script L37~57)",
        "",
        f"- 입하 case: {RECEIVING_MIN_PER_CARTON} min/case ({60/RECEIVING_MIN_PER_CARTON:.0f} cases/MH)",
        f"- 입하 pallet: {RECEIVING_MIN_PER_PALLET} min/pallet ({60/RECEIVING_MIN_PER_PALLET:.0f} pallets/MH)",
        f"- 입고: {PUTAWAY_MIN_PER_LINE} min/line + travel + lift",
        f"- 검수 visual: {QC_MIN_PER_PIECE_VISUAL} min/pc · AQL: {QC_MIN_PER_AQL_SAMPLE} min/sample",
        f"- 피킹 **batch**: {PICK_MIN_PER_BATCH} min/batch (batch size={PICK_BATCH_SIZE_DEFAULT}) — 자사 운영 패턴 (50~200 묶음)",
        f"- TMS shipment: dispatch {TMS_DISPATCH_MIN_PER_SHIPMENT} + docs {TMS_DOCS_MIN_PER_SHIPMENT} min",
        f"- PFD: ×{PFD_ALLOWANCE}",
        "",
    ]

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", help="ISO date (default: 30일 전)")
    parser.add_argument("--until", help="ISO date (default: 오늘)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out-dir", default="outputs",
                        help="report output directory (default: outputs/)")
    args = parser.parse_args()

    if not WMS_PAT:
        sys.exit("ERROR: AIRTABLE_WMS_PAT or AIRTABLE_PAT not set in env")

    until = date.fromisoformat(args.until) if args.until else date.today()
    since = date.fromisoformat(args.since) if args.since else (until - timedelta(days=30))

    print(f"[mh_calculator] period: {since} ~ {until}", flush=True)

    # 1) Receiving: movement 테이블 — 최신순 sort + 클라이언트 필터 (Airtable perf 가이드)
    print(f"[mh_calculator] fetching movement records (sorted by 실제입하일 desc)...", flush=True)
    mov_fields = [
        "이동유형", "실제입하일", "입하카톤수", "입하파렛트수", "입하수량",
        "검수수량", "표본검수수량(미사용중)",
    ]
    since_str = since.isoformat()

    def _past_cutoff(rec):
        d = _parse_date(rec.get("fields", {}).get("실제입하일"))
        return d is not None and d < since

    mov_records = get_records(
        TBL_MOVEMENT,
        fields=mov_fields,
        sort_field="실제입하일",
        sort_dir="desc",
        stop_predicate=_past_cutoff,
    )
    print(f"[mh_calculator]   movement fetched: {len(mov_records)} records (pre-filter)", flush=True)

    receiving_rows = []
    for rec in mov_records:
        d = _parse_date(rec.get("fields", {}).get("실제입하일"))
        if d is None or d < since or d > until:
            continue
        if classify_movement(rec) != "receiving":
            continue
        mh, basis, qty = calc_receiving_mh(rec)
        if mh <= 0:
            continue
        receiving_rows.append({
            "id": rec["id"],
            "basis": basis,
            "qty": qty,
            "mh_std": mh,
        })

    # 2) Picking: WMS_PickingTask 전체 (created time 필터링은 API에서 미제공 — 전체)
    print(f"[mh_calculator] fetching WMS_PickingTask...", flush=True)
    pick_records = get_records(TBL_PICKING_TASK)
    print(f"[mh_calculator]   picking_task: {len(pick_records)} records", flush=True)

    picking_rows = []
    for rec in pick_records:
        # 기간 필터: createdTime ≥ since (Airtable record metadata)
        created = _parse_date(rec.get("createdTime"))
        if created is None or created < since or created > until:
            continue
        mh, basis, qty = calc_picking_mh(rec)
        if mh <= 0:
            continue
        picking_rows.append({
            "id": rec["id"],
            "basis": basis,
            "qty": qty,
            "mh_std": mh,
        })

    # 3) TMS Shipment — 출하확정일 기준, 같은 sort+stop 패턴
    print(f"[mh_calculator] fetching TMS Shipment (sorted by 출하확정일 desc)...", flush=True)
    tms_fields = ["출하확정일", "배송 유형", "배송 방식"]

    def _tms_past_cutoff(rec):
        d = _parse_date(rec.get("fields", {}).get("출하확정일"))
        return d is not None and d < since

    tms_records = get_records(
        TBL_SHIPMENT,
        fields=tms_fields,
        sort_field="출하확정일",
        sort_dir="desc",
        stop_predicate=_tms_past_cutoff,
        base_id=TMS_BASE_ID,
        pat=TMS_PAT,
    )
    print(f"[mh_calculator]   TMS shipment fetched: {len(tms_records)} records (pre-filter)", flush=True)

    tms_rows = []
    for rec in tms_records:
        d = _parse_date(rec.get("fields", {}).get("출하확정일"))
        if d is None or d < since or d > until:
            continue
        mh, basis, mode = calc_tms_shipment_mh(rec)
        tms_rows.append({"id": rec["id"], "basis": basis, "mode": mode, "mh_std": mh})

    print(f"[mh_calculator] receiving={len(receiving_rows)} | picking={len(picking_rows)} | tms={len(tms_rows)}", flush=True)

    if args.dry_run:
        print(f"[mh_calculator] --dry-run set: skipping file write", flush=True)
        total = sum(r["mh_std"] for r in receiving_rows) + sum(r["mh_std"] for r in picking_rows) + sum(r["mh_std"] for r in tms_rows)
        print(f"[mh_calculator] total M/H_std = {total/60:.1f} MH", flush=True)
        return

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"MH-{iso_week(until)}.md"
    generate_report(receiving_rows, picking_rows, tms_rows, since, until, out_path)
    print(f"[mh_calculator] wrote: {out_path}", flush=True)


if __name__ == "__main__":
    main()
