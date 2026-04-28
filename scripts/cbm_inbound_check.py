"""
cbm_inbound_check.py
─────────────────────────────────────────────────────────────────────────────
WMS 입하 CBM 검증 스크립트

자재관리.movement (이동목적=생산산출) 레코드를 조회하여
이동물품 필드를 파싱하고 CSV로 출력.

목적:
  - movement_id (MM00xxxxx) 기준 PK 확인
  - 이동물품 필드 로직 검증 (파츠코드 || 프로젝트코드 || 센터명)
  - Barcode 베이스 CBM 마스터와 매핑 준비

사용법:
  python scripts/cbm_inbound_check.py                    # 전체 조회
  python scripts/cbm_inbound_check.py --week 2026-W18   # 특정 주 입하예정일 필터
  python scripts/cbm_inbound_check.py --dry-run          # 샘플 10건만 출력
"""

import argparse
import csv
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

# ── Airtable 상수 (자재테스트_지수 베이스 = Barcode WMS 베이스) ──────────────
BASE_ID  = "appLui4ZR5HWcQRri"       # 자재테스트_지수 (Barcode)
TBL_MOV  = "tblwq7Kj5Y9nVjlOw"       # ⚡movement (자재관리에서 sync됨)

# movement 필드 ID (⚡movement 테이블 기준)
FLD_MOV_ID         = "fldOhFtJFBYsxxre7"   # movement_id (MM00xxxxx)
FLD_MOV_ITEM       = "fldwZKCYZ4IFOigRp"   # 이동물품 (multilineText)
FLD_MOV_PURPOSE    = "fldFRNxG1pNooEOC7"   # 이동목적 (singleSelect)
FLD_MOV_RECORD_ID  = None                   # synced table: record_id formula 없음
FLD_MOV_EXP_DATE   = "fldlpGxylH72YPs7V"   # 입하예상일 (date)
FLD_MOV_ACT_DATE   = "flduN8khmYwdn7uVD"   # 실제입하일 (date)
FLD_MOV_IN_QTY     = "fldV8kVokQqMIsif0"   # 입하수량 (number)
FLD_MOV_PARTS_CODE = None                   # synced table에 파츠코드 별도 없음

# 생산산출 choice
PURPOSE_FILTER = '"생산산출"'

AIRTABLE_PAT = os.environ.get("AIRTABLE_WMS_PAT", os.environ.get("AIRTABLE_PAT", ""))
HEADERS = {
    "Authorization": f"Bearer {AIRTABLE_PAT}",
    "Content-Type": "application/json",
}

ROOT = Path(__file__).parent.parent
OUTPUTS_DIR = ROOT / "reports"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


# ── 헬퍼 ────────────────────────────────────────────────────────────────────
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


def parse_week(week_str: str) -> tuple[date, date]:
    """'2026-W18' → (monday, sunday)"""
    year, week = week_str.split("-W")
    monday = datetime.strptime(f"{year}-W{int(week):02d}-1", "%G-W%V-%u").date()
    sunday = monday + timedelta(days=6)
    return monday, sunday


def parse_inbound_item(raw: str | None) -> dict:
    """
    이동물품 필드 파싱.
    형식: "PT3137-사각스티커(커스텀인쇄)_화이트+디지털풀컬러 || PNA35889_어텐션스포츠보틀 || 에이원지식산업센터"
    """
    if not raw:
        return {"parts_code": "", "parts_name": "", "project_code": "", "project_name": "", "center": ""}

    parts = [p.strip() for p in raw.split(" || ")]

    # 파츠 파싱
    parts_full = parts[0] if len(parts) > 0 else ""
    dash_idx = parts_full.find("-")
    if dash_idx != -1:
        parts_code = parts_full[:dash_idx]
        parts_name = parts_full[dash_idx + 1:]
    else:
        parts_code = parts_full
        parts_name = ""

    # 프로젝트 파싱
    project_full = parts[1] if len(parts) > 1 else ""
    under_idx = project_full.find("_")
    if under_idx != -1:
        project_code = project_full[:under_idx]
        project_name = project_full[under_idx + 1:]
    else:
        project_code = project_full
        project_name = ""

    center = parts[2] if len(parts) > 2 else ""

    return {
        "parts_code": parts_code,
        "parts_name": parts_name,
        "project_code": project_code,
        "project_name": project_name,
        "center": center,
    }


# ── 메인 ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="WMS 입하 CBM 검증")
    parser.add_argument("--week", help="입하예정일 필터 (예: 2026-W18)")
    parser.add_argument("--dry-run", action="store_true", help="샘플 10건만 출력")
    parser.add_argument("--output", help="출력 CSV 경로 (기본: reports/cbm_inbound_YYYYMMDD.csv)")
    args = parser.parse_args()

    if not AIRTABLE_PAT:
        print("ERROR: AIRTABLE_PAT 환경변수가 없습니다.", file=sys.stderr)
        sys.exit(1)

    # 날짜 범위 계산
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
            print(f"ERROR: 잘못된 주 형식 '{args.week}'. 예: 2026-W18", file=sys.stderr)
            sys.exit(1)

    # Airtable 필터
    formula = f"{{{FLD_MOV_PURPOSE}}}={PURPOSE_FILTER}"
    if week_filter:
        formula = f"AND({formula}, {week_filter})"

    max_records = 10 if args.dry_run else None

    print(f"조회 중: 이동목적=생산산출, 입하예정일={week_label}")
    if args.dry_run:
        print("  [dry-run] 최대 10건")

    fetch_fields = [
        FLD_MOV_ID, FLD_MOV_ITEM, FLD_MOV_PURPOSE,
        FLD_MOV_EXP_DATE, FLD_MOV_ACT_DATE, FLD_MOV_IN_QTY,
    ]

    records = get_all_records(
        table_id=TBL_MOV,
        fields=fetch_fields,
        formula=formula,
        max_records=max_records,
    )

    print(f"조회 완료: {len(records)}건")

    # 파싱
    rows = []
    for rec in records:
        f = rec.get("fields", {})
        movement_id   = f.get(FLD_MOV_ID, "")
        inbound_item  = f.get(FLD_MOV_ITEM, "")
        exp_date      = parse_date(f.get(FLD_MOV_EXP_DATE))
        act_date      = parse_date(f.get(FLD_MOV_ACT_DATE))
        in_qty        = f.get(FLD_MOV_IN_QTY, "")

        parsed = parse_inbound_item(inbound_item)

        rows.append({
            "movement_id":   movement_id,
            "airtable_rec":  rec["id"],           # 이 베이스의 rec ID (synced)
            "parts_code":    parsed["parts_code"],
            "parts_name":    parsed["parts_name"],
            "project_code":  parsed["project_code"],
            "project_name":  parsed["project_name"],
            "center":        parsed["center"],
            "expected_date": exp_date.isoformat() if exp_date else "",
            "actual_date":   act_date.isoformat() if act_date else "",
            "in_qty":        in_qty,
            "raw_item":      inbound_item,
        })

    # 출력 경로
    out_path = args.output
    if not out_path:
        today = date.today().strftime("%Y%m%d")
        out_path = str(OUTPUTS_DIR / f"cbm_inbound_{today}.csv")

    # 요약 출력
    centers = {}
    for r in rows:
        c = r["center"] or "(센터 없음)"
        centers[c] = centers.get(c, 0) + 1

    print(f"\n[요약] 이동목적=생산산출 ({week_label})")
    print(f"  총 {len(rows)}건")
    for c, cnt in sorted(centers.items(), key=lambda x: -x[1]):
        print(f"  {c}: {cnt}건")

    # PK 검증
    pk_ok   = sum(1 for r in rows if r["movement_id"])
    pk_miss = len(rows) - pk_ok
    print(f"\n[PK 검증] movement_id 있음: {pk_ok}건 / 없음: {pk_miss}건")
    if pk_miss > 0:
        print("  ※ movement_id 없는 레코드 — Barcode 베이스 sync 시 매핑 불가")

    # CSV 저장
    if rows:
        fieldnames = list(rows[0].keys())
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nCSV 저장: {out_path}")
    else:
        print("\n레코드 없음 — CSV 저장 생략")


if __name__ == "__main__":
    main()
