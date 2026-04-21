"""
고객납품 ↔ TO 정합성 주간 체크
Base: SERPA_v3.0 (appLui4ZR5HWcQRri)
Movement 테이블에서 이동목적=고객납품인 레코드를 조회하여
logistics_release(TO) 연결 상태의 2가지 정합성을 확인한다.

사용법:
  python scripts/check_고객납품_TO정합성.py              # 전주 기준
  python scripts/check_고객납품_TO정합성.py --weeks 2    # 최근 2주
  python scripts/check_고객납품_TO정합성.py --start 2026-04-07 --end 2026-04-13
  python scripts/check_고객납품_TO정합성.py --no-save    # 파일 저장 없이 콘솔 출력만

체크 항목:
  [1] 프로젝트별 TO 부분 누락 — 같은 PNA 프로젝트 내 일부 MM만 TO 연결
  [2] 단일 MM에 복수 TO — logistics_release에 TO 번호가 여러 개
"""
import argparse
import os
import re
import sys
import time
from collections import defaultdict
from datetime import date, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()

PAT = os.environ.get(
    "AIRTABLE_PAT",
    "patU9ew1rwbJbEpOn.d5c7c1bb42c3ad69edd2701ee0424ddcb04c4d261a0ed422f8e5edaf1fa20edc",
)
HEADERS = {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}

BASE_ID  = "appLui4ZR5HWcQRri"
TBL_MOV  = "tblwq7Kj5Y9nVjlOw"

FLD_MOV_ID      = "fldOhFtJFBYsxxre7"   # movement_id
FLD_MOV_ITEM    = "fldwZKCYZ4IFOigRp"   # 이동물품
FLD_MOV_QTY     = "fld0XSbknPnJfOYOT"   # 출고수량
FLD_MOV_PURPOSE = "fldFRNxG1pNooEOC7"   # 이동목적 (singleSelect)
FLD_MOV_PROJECT = "fldyIAHkFOzfnW4TW"   # project (singleLineText)
FLD_MOV_TO      = "fld6UXwgrDhkmwTZd"   # logistics_release (singleLineText)
FLD_MOV_DATE    = "fldDXUAF4JOORLJ2v"   # 생성일자 (dateTime)


def last_week_range(n_weeks: int = 1) -> tuple[date, date]:
    today = date.today()
    last_monday = today - timedelta(days=today.weekday() + 7 * n_weeks)
    last_sunday  = last_monday + timedelta(days=7 * n_weeks - 1)
    return last_monday, last_sunday


def _split_to_list(to_str: str) -> list[str]:
    """'TO00016101 TO00016102' 또는 'TO00016101,TO00016102' 형태를 리스트로 분리"""
    if not to_str:
        return []
    parts = re.split(r"[\s,;/]+", to_str.strip())
    return [p for p in parts if re.match(r"TO\d+", p)]


def fetch_movements(start: date, end: date) -> list[dict]:
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_MOV}"

    formula = (
        f'AND('
        f'  {{이동목적}} = "고객납품",'
        f'  IS_AFTER({{생성일자}}, DATEADD("{start.isoformat()}", -1, "days")),'
        f'  IS_BEFORE({{생성일자}}, DATEADD("{end.isoformat()}", 1, "days"))'
        f')'
    )
    params = {
        "filterByFormula": formula,
        "fields[]": [
            FLD_MOV_ID, FLD_MOV_ITEM, FLD_MOV_QTY,
            FLD_MOV_PROJECT, FLD_MOV_TO, FLD_MOV_DATE,
        ],
        "pageSize": 100,
    }
    records = []
    offset = None
    while True:
        if offset:
            params["offset"] = offset
        resp = requests.get(url, headers=HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()
        records.extend(data["records"])
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records


def check1_partial_to(records: list[dict]) -> list[dict]:
    """[체크1] 같은 PNA 프로젝트 내 일부 MM만 TO 연결 → 나머지 누락 의심"""
    by_project: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        f = rec["fields"]
        proj = (f.get(FLD_MOV_PROJECT) or "").strip()
        if proj:
            by_project[proj].append({
                "movement_id": f.get(FLD_MOV_ID, rec["id"]),
                "to":          (f.get(FLD_MOV_TO) or "").strip(),
                "이동물품":      f.get(FLD_MOV_ITEM, ""),
                "출고수량":      f.get(FLD_MOV_QTY, ""),
                "날짜":         str(f.get(FLD_MOV_DATE, ""))[:10],
            })

    issues = []
    for proj, mvs in by_project.items():
        if len(mvs) < 2:
            continue
        with_to    = [m for m in mvs if m["to"]]
        without_to = [m for m in mvs if not m["to"]]
        if with_to and without_to:
            all_to = sorted({t for m in with_to for t in _split_to_list(m["to"])})
            for m in without_to:
                issues.append({
                    "project":    proj,
                    "movement_id": m["movement_id"],
                    "이동물품":    m["이동물품"],
                    "출고수량":    m["출고수량"],
                    "날짜":       m["날짜"],
                    "같은_프로젝트_TO목록": ", ".join(all_to),
                    "같은_프로젝트_MM수": len(mvs),
                })
    return issues


def check2_multi_to(records: list[dict]) -> list[dict]:
    """[체크2] 단일 MM에 복수 TO 혼재"""
    result = []
    for rec in records:
        f = rec["fields"]
        to_val = (f.get(FLD_MOV_TO) or "").strip()
        to_list = _split_to_list(to_val)
        if len(to_list) > 1:
            result.append({
                "movement_id": f.get(FLD_MOV_ID, rec["id"]),
                "project":     f.get(FLD_MOV_PROJECT, ""),
                "이동물품":      f.get(FLD_MOV_ITEM, ""),
                "출고수량":      f.get(FLD_MOV_QTY, ""),
                "날짜":         str(f.get(FLD_MOV_DATE, ""))[:10],
                "TO목록":       ", ".join(to_list),
                "TO수":         len(to_list),
            })
    return result


def render_report(
    start: date,
    end: date,
    week_num: int,
    c1: list, c2: list,
) -> str:
    lines = [
        f"## 고객납품 TO 정합성 체크 — W{week_num} ({start} ~ {end})",
        "",
        f"### [체크1] 프로젝트별 TO 부분 누락 ({len(c1)}건)",
    ]

    if c1:
        lines.append("| project | movement_id | 이동물품 | 출고수량 | 날짜 | 같은 프로젝트 TO목록 |")
        lines.append("|---------|------------|---------|---------|------|---------------------|")
        for r in c1:
            lines.append(
                f"| {r['project']} | {r['movement_id']} | {r['이동물품']} "
                f"| {r['출고수량']} | {r['날짜']} | {r['같은_프로젝트_TO목록']} |"
            )
    else:
        lines.append("> 이상 없음")

    lines += [
        "",
        f"### [체크2] 단일 MM에 복수 TO ({len(c2)}건)",
    ]
    if c2:
        lines.append("| movement_id | project | 이동물품 | 출고수량 | 날짜 | TO목록 |")
        lines.append("|------------|---------|---------|---------|------|--------|")
        for r in c2:
            lines.append(
                f"| {r['movement_id']} | {r['project']} | {r['이동물품']} "
                f"| {r['출고수량']} | {r['날짜']} | {r['TO목록']} |"
            )
    else:
        lines.append("> 이상 없음")

    lines += [
        "",
        "### 요약",
        f"- 확인 필요: {len(c1)}건 (프로젝트 내 TO 부분 누락)",
        f"- 검토 필요: {len(c2)}건 (단일 MM 복수 TO — 분할 출하 의도 여부 확인)",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="고객납품 TO 정합성 주간 체크")
    parser.add_argument("--start",   help="시작일 YYYY-MM-DD (기본: 전주 월요일)")
    parser.add_argument("--end",     help="종료일 YYYY-MM-DD (기본: 전주 일요일)")
    parser.add_argument("--weeks",   type=int, default=1, help="조회 주간 수 (기본 1)")
    parser.add_argument("--no-save", action="store_true", help="파일 저장 없이 콘솔 출력만")
    args = parser.parse_args()

    if args.start and args.end:
        start = date.fromisoformat(args.start)
        end   = date.fromisoformat(args.end)
    else:
        start, end = last_week_range(args.weeks)

    week_num = start.isocalendar()[1]

    sys.stdout.buffer.write(f"고객납품 TO 정합성 체크 시작: {start} ~ {end}\n".encode("utf-8"))
    sys.stdout.buffer.write(b"  레코드 조회 중...\n")

    records = fetch_movements(start, end)
    sys.stdout.buffer.write(f"  조회된 고객납품 레코드: {len(records)}건\n".encode("utf-8"))

    c1 = check1_partial_to(records)
    c2 = check2_multi_to(records)

    report = render_report(start, end, week_num, c1, c2)
    sys.stdout.buffer.write((report + "\n").encode("utf-8"))

    if not args.no_save:
        report_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports")
        os.makedirs(report_dir, exist_ok=True)
        fname = f"고객납품_TO정합성_{date.today().isoformat()}.md"
        fpath = os.path.join(report_dir, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(report + "\n")
        sys.stdout.buffer.write(f"\n[저장] {fpath}\n".encode("utf-8"))


if __name__ == "__main__":
    main()
