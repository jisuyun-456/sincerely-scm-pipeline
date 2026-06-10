"""
cbm_inbound_check.py
─────────────────────────────────────────────────────────────────────────────
WMS 입하 CBM 산출 스크립트

movement (이동목적 ∈ 외부입하 — 생산산출·재고생산·고객물품, CP② 승인 2026-06-10)
레코드의 제품 규격 × 입하수량으로 CBM 계산. 제품 규격 없는 경우 sync_parts.규격 fallback.

CBM = 단위 부피(m³) × 입하수량  [근삿값, 포장 오버헤드 미포함]

사용법:
  python scripts/cbm_inbound_check.py                    # 전체 조회
  python scripts/cbm_inbound_check.py --week 2026-W21   # 특정 주 입하예정일 필터
  python scripts/cbm_inbound_check.py --dry-run          # 샘플 10건만 출력
"""

import argparse
import csv
import math
import os
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.cbm_utils import (  # noqa: E402
    EXTERNAL_INBOUND_PURPOSES,
    build_inbound_formula,
    calc_cbm,
    load_sync_parts_lookup,
    parse_date,
    parse_inbound_item,
)

load_dotenv()

# ── Airtable 상수 ─────────────────────────────────────────────────────────────
BASE_ID = "appLui4ZR5HWcQRri"      # WMS base
TBL_MOV = "tblwq7Kj5Y9nVjlOw"      # movement
TBL_SP  = "tblzJh0V4hdo4Xbvx"      # sync_parts

# movement 필드 ID
FLD_MOV_ID      = "fldOhFtJFBYsxxre7"   # movement_id (MM00xxxxx)
FLD_MOV_ITEM    = "fldwZKCYZ4IFOigRp"   # 이동물품
FLD_MOV_PURPOSE = "fldFRNxG1pNooEOC7"   # 이동목적
FLD_MOV_EXP_DATE = "fldlpGxylH72YPs7V"  # 입하예상일
FLD_MOV_ACT_DATE = "flduN8khmYwdn7uVD"  # 실제입하일
FLD_MOV_IN_QTY  = "fldV8kVokQqMIsif0"  # 입하수량
FLD_MOV_SPEC    = "fldiYU7b6Ogf0zm2D"   # 제품 규격 (치수 문자열)

# sync_parts 필드 ID
FLD_SP_CODE = "fld8gjySjm4XkCpMc"   # 파츠 코드
FLD_SP_SPEC = "fldRseOMNseg15D6R"   # 규격

AIRTABLE_PAT = os.environ.get("AIRTABLE_WMS_PAT", os.environ.get("AIRTABLE_PAT", ""))
HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_PAT}",
    "Content-Type": "application/json",
}

ROOT = Path(__file__).parent.parent
OUTPUTS_DIR = ROOT / "reports"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


# ── Airtable 조회 ─────────────────────────────────────────────────────────────
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


# ── 파싱 헬퍼 ────────────────────────────────────────────────────────────────
def parse_week(week_str: str) -> tuple[date, date]:
    year, week = week_str.split("-W")
    monday = datetime.strptime(f"{year}-W{int(week):02d}-1", "%G-W%V-%u").date()
    sunday = monday + timedelta(days=6)
    return monday, sunday


# ── 메인 ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="WMS 입하 CBM 산출")
    parser.add_argument("--week", help="입하예정일 필터 (예: 2026-W21)")
    parser.add_argument("--dry-run", action="store_true", help="샘플 10건만 출력")
    parser.add_argument("--output", help="출력 CSV 경로")
    args = parser.parse_args()

    if not AIRTABLE_PAT:
        print("ERROR: AIRTABLE_PAT 환경변수가 없습니다.", file=sys.stderr)
        sys.exit(1)

    print("sync_parts 규격 룩업 로딩 중...")
    sp_lookup = load_sync_parts_lookup()
    print(f"  → {len(sp_lookup)}개 PT코드 로드")

    # 날짜 필터
    week_filter = ""
    week_label = "전체"
    if args.week:
        try:
            monday, sunday = parse_week(args.week)
            week_filter = (
                f"AND("
                f"IS_AFTER({{{FLD_MOV_EXP_DATE}}}, DATEADD('{monday.isoformat()}', -1, 'days')), "
                f"IS_BEFORE({{{FLD_MOV_EXP_DATE}}}, DATEADD('{sunday.isoformat()}', 1, 'days'))"
                f")"
            )
            week_label = f"{args.week} ({monday} ~ {sunday})"
        except ValueError:
            print(f"ERROR: 잘못된 주 형식 '{args.week}'. 예: 2026-W21", file=sys.stderr)
            sys.exit(1)

    formula = build_inbound_formula(EXTERNAL_INBOUND_PURPOSES)
    if week_filter:
        formula = f"AND({formula}, {week_filter})"

    max_records = 10 if args.dry_run else None

    print(f"조회 중: 이동목적={sorted(EXTERNAL_INBOUND_PURPOSES)}, 입하예정일={week_label}")
    if args.dry_run:
        print("  [dry-run] 최대 10건")

    records = get_all_records(
        table_id=TBL_MOV,
        fields=[FLD_MOV_ID, FLD_MOV_ITEM, FLD_MOV_PURPOSE,
                FLD_MOV_EXP_DATE, FLD_MOV_ACT_DATE, FLD_MOV_IN_QTY, FLD_MOV_SPEC],
        formula=formula,
        max_records=max_records,
    )
    print(f"조회 완료: {len(records)}건")

    rows = []
    by_date: dict[str, dict] = defaultdict(lambda: {"cbm": 0.0, "cnt": 0, "no_spec": 0})
    n_spec_mov, n_spec_sp, n_no_spec = 0, 0, 0

    for rec in records:
        f = rec.get("fields", {})
        movement_id  = f.get(FLD_MOV_ID, "")
        inbound_item = f.get(FLD_MOV_ITEM, "")
        exp_date     = parse_date(f.get(FLD_MOV_EXP_DATE))
        act_date     = parse_date(f.get(FLD_MOV_ACT_DATE))
        in_qty       = float(f.get(FLD_MOV_IN_QTY) or 0)
        mov_spec     = str(f.get(FLD_MOV_SPEC) or "").strip()

        parsed = parse_inbound_item(inbound_item)
        parts_code = parsed["parts_code"]

        # 규격 우선순위: movement.제품 규격 → sync_parts.규격
        spec_used = ""
        spec_src = "none"
        if mov_spec:
            cbm, ok = calc_cbm(mov_spec, in_qty)
            if ok:
                spec_used = mov_spec
                spec_src = "mov"
                n_spec_mov += 1
            else:
                cbm = 0.0
        else:
            cbm = 0.0

        if spec_src == "none" and parts_code:
            sp_spec = sp_lookup.get(parts_code, "")
            if sp_spec:
                cbm, ok = calc_cbm(sp_spec, in_qty)
                if ok:
                    spec_used = sp_spec
                    spec_src = "sp"
                    n_spec_sp += 1

        if spec_src == "none":
            n_no_spec += 1

        d_key = exp_date.isoformat() if exp_date else "날짜없음"
        by_date[d_key]["cbm"]     += cbm
        by_date[d_key]["cnt"]     += 1
        by_date[d_key]["no_spec"] += 1 if spec_src == "none" else 0

        rows.append({
            "movement_id":   movement_id,
            "airtable_rec":  rec["id"],
            "parts_code":    parts_code,
            "parts_name":    parsed["parts_name"],
            "project_code":  parsed["project_code"],
            "project_name":  parsed["project_name"],
            "center":        parsed["center"],
            "expected_date": exp_date.isoformat() if exp_date else "",
            "actual_date":   act_date.isoformat() if act_date else "",
            "in_qty":        in_qty,
            "spec_used":     spec_used,
            "spec_src":      spec_src,
            "cbm_total":     cbm,
            "raw_item":      inbound_item,
        })

    # ── 콘솔 요약 ─────────────────────────────────────────────────────────────
    total_cbm = sum(r["cbm_total"] for r in rows)
    n = len(rows)
    days_with_data = len([d for d in by_date if d != "날짜없음"])

    print(f"\n{'='*60}")
    print(f"[{week_label} 입하 CBM 리포트]  ※ 제품규격 × 수량 기준")
    print(f"총 입하: {n}건 | mov규격: {n_spec_mov}건 | SP규격: {n_spec_sp}건 | 규격없음: {n_no_spec}건")
    print(f"총 CBM: {total_cbm:.4f} m³", end="")
    if days_with_data > 0:
        print(f" | 일평균: {total_cbm / days_with_data:.4f} m³", end="")
    print()

    if by_date:
        print(f"\n[일별]")
        for d in sorted(by_date.keys()):
            entry = by_date[d]
            if d == "날짜없음":
                label = "날짜없음"
            else:
                try:
                    wd = ["월", "화", "수", "목", "금", "토", "일"][date.fromisoformat(d).weekday()]
                    label = f"{wd}({d[5:]})"
                except ValueError:
                    label = d
            no_s = f" [규격없음 {entry['no_spec']}건]" if entry["no_spec"] else ""
            print(f"  {label}: {entry['cbm']:.4f} m³ / {entry['cnt']}건{no_s}")

    if n_no_spec:
        no_spec_codes = sorted({r["parts_code"] for r in rows if r["spec_src"] == "none" and r["parts_code"]})
        print(f"\n[규격 없는 PT코드 ({n_no_spec}건)]")
        print(f"  {', '.join(no_spec_codes)}")

    print(f"{'='*60}")

    # ── CSV 저장 ──────────────────────────────────────────────────────────────
    out_path = args.output or str(OUTPUTS_DIR / f"cbm_inbound_{date.today().strftime('%Y%m%d')}.csv")
    if rows:
        with open(out_path, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nCSV 저장: {out_path}")
    else:
        print("\n레코드 없음 — CSV 저장 생략")


if __name__ == "__main__":
    main()
