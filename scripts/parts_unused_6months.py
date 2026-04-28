"""
parts_unused_6months.py  v2
────────────────────────────────────────────────────────────────────────────
⚡movement 테이블 기준 마지막 활동일로 6개월+ 미사용 파츠 목록 추출
(이전 버전은 order 테이블을 사용했으나 2026년 데이터만 존재해 부정확)

사용법:
  python scripts/parts_unused_6months.py
  python scripts/parts_unused_6months.py --months 3
  python scripts/parts_unused_6months.py --output reports/unused_parts_bestone_v2.md
"""

import argparse
import os
import re
import sys
from datetime import date, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()
sys.stdout.reconfigure(encoding="utf-8")

BASE_ID = "appLui4ZR5HWcQRri"
TBL_MOVEMENT    = "tblwq7Kj5Y9nVjlOw"   # ⚡movement
TBL_SYNC_PARTS  = "tblzJh0V4hdo4Xbvx"   # ⚡sync_parts

# ── movement 필드 ──────────────────────────────────────────────────────────
MV_PARTS_CODE    = "fldKwSo9C9M2paibK"   # 파츠코드 (PT1234)
MV_DATE_ACTUAL   = "flduN8khmYwdn7uVD"   # 실제입하일
MV_DATE_COMPLETE = "fldDVoNYuutabrwI1"   # 입하완료일자
MV_DATE_OUTBOUND = "fldIXLGK9538hkfd0"   # 출하확정일
MV_DATE_CONFIRM  = "fld0YFK290KAjYdXg"   # 입하확정일
MV_CANCEL        = "fldwgaM8OnKubM8oE"   # 취소 여부
MV_CREATED       = "fldDXUAF4JOORLJ2v"   # 생성일자 (dateTime — 항상 존재)

# ── sync_parts 필드 ───────────────────────────────────────────────────────
SP_NAME    = "fldl9H11lWgz2l3Yp"          # 파츠명
SP_CODE    = "fld8gjySjm4XkCpMc"          # 파츠 코드 (PK)  예: PT2330
SP_GRAD    = "fld5xc3pc2QPvKhTo"          # 졸업 Status
SP_TYPE    = "fldaGX8DpArGed5tW"          # 파츠 유형
SP_LOC_QTY = "fldXlbEApr3iBNfSg"         # 재고위치별 수량 (텍스트: "에이원[x] / 베스트원[x]")


def get_pat() -> str:
    pat = os.environ.get("AIRTABLE_WMS_PAT", os.environ.get("AIRTABLE_PAT", ""))
    if not pat:
        sys.exit("AIRTABLE_WMS_PAT (또는 AIRTABLE_PAT) 환경변수가 설정되지 않았습니다.")
    return pat


def fetch_all(pat: str, table_id: str, fields: list[str], retries: int = 5) -> list[dict]:
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}"
    headers = {"Authorization": f"Bearer {pat}"}
    params: dict = {
        "fields[]": fields,
        "returnFieldsByFieldId": "true",
        "pageSize": 100,
    }
    records: list[dict] = []
    offset = None
    while True:
        if offset:
            params["offset"] = offset
        for attempt in range(retries):
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=120)
                resp.raise_for_status()
                break
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                if attempt == retries - 1:
                    raise
                import time
                wait = 2 ** attempt
                print(f"\n  타임아웃/연결오류, {wait}s 후 재시도 ({attempt+1}/{retries})…", end="")
                time.sleep(wait)
        data = resp.json()
        records.extend(data.get("records", []))
        print(f"\r  fetching {table_id[:14]}… {len(records):,}건", end="", flush=True)
        offset = data.get("offset")
        if not offset:
            break
    print()
    return records


def pick_best_date(fields: dict) -> date | None:
    """실제 날짜 필드 중 가장 최신 날짜 반환.
    생성일자(created datetime)는 시스템 입력 시점이라 제외 —
    실제 물리적 이동이 확인된 날짜만 사용."""
    candidates: list[date] = []
    for fid in (MV_DATE_ACTUAL, MV_DATE_COMPLETE, MV_DATE_OUTBOUND, MV_DATE_CONFIRM):
        v = fields.get(fid)
        if v:
            try:
                candidates.append(date.fromisoformat(str(v)[:10]))
            except ValueError:
                pass
    return max(candidates) if candidates else None


def bestone_qty(loc_str: str | None) -> int:
    if not loc_str:
        return 0
    m = re.search(r'베스트원\[(\d+)\]', str(loc_str))
    return int(m.group(1)) if m else 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=6, help="미사용 기준 개월수 (기본 6)")
    parser.add_argument("--output", default="reports/unused_parts_bestone_v2.md",
                        help="MD 출력 파일 경로")
    args = parser.parse_args()

    today = date.today()
    cutoff = today - timedelta(days=args.months * 30)

    print(f"[movement 기준 6개월+ 미사용 파츠] 기준일: {today}  /  컷오프: {cutoff}")
    pat = get_pat()

    # ── 1. sync_parts 마스터 로드 ──────────────────────────────────────────
    print("\n[1/2] sync_parts 로딩…")
    sp_recs = fetch_all(pat, TBL_SYNC_PARTS, [SP_NAME, SP_CODE, SP_GRAD, SP_TYPE, SP_LOC_QTY])
    parts_master: dict[str, dict] = {}
    for rec in sp_recs:
        f = rec.get("fields", {})
        code_raw = f.get(SP_CODE) or ""
        # SP_CODE 가 multilineText 일 수 있어 첫 줄만 사용
        code = str(code_raw).splitlines()[0].strip()
        if not code:
            continue
        parts_master[code] = {
            "name":    (f.get(SP_NAME) or "").strip(),
            "grad":    str(f.get(SP_GRAD) or "").strip(),
            "type":    str(f.get(SP_TYPE) or "").strip(),
            "bestone": bestone_qty(f.get(SP_LOC_QTY)),
        }
    print(f"  sync_parts 파츠: {len(parts_master):,}개")

    # ── 2. movement 로드 → 파츠코드별 최신 활동일 ────────────────────────
    print("\n[2/2] movement 로딩…")
    mv_recs = fetch_all(pat, TBL_MOVEMENT, [
        MV_PARTS_CODE, MV_DATE_ACTUAL, MV_DATE_COMPLETE,
        MV_DATE_OUTBOUND, MV_DATE_CONFIRM, MV_CANCEL, MV_CREATED,
    ])

    last_activity: dict[str, date] = {}   # 실제 날짜 있는 최신 날짜
    has_movement:  set[str] = set()       # WMS 레코드 존재 여부
    skipped_cancel = 0
    skipped_no_code = 0
    for rec in mv_recs:
        f = rec.get("fields", {})
        cancel = str(f.get(MV_CANCEL) or "").strip()
        if cancel and "취소" in cancel:
            skipped_cancel += 1
            continue
        code_raw = f.get(MV_PARTS_CODE) or ""
        code = str(code_raw).strip()
        if not code:
            skipped_no_code += 1
            continue
        has_movement.add(code)
        d = pick_best_date(f)
        if d and (code not in last_activity or d > last_activity[code]):
            last_activity[code] = d

    print(f"  movement 레코드: {len(mv_recs):,}건  (취소제외: {skipped_cancel}, 파츠코드없음: {skipped_no_code})")
    print(f"  파츠코드 매핑: {len(has_movement):,}개  (실제 날짜 확인: {len(last_activity):,}개)")

    # ── 3. 필터링 ─────────────────────────────────────────────────────────
    # A: 실제 날짜 있고 cutoff 이전 → 미사용 확정
    unused:        list[tuple[str, dict, date]] = []
    # B: WMS 레코드 있으나 실제 날짜 없음 → 미확인(주의 대상)
    no_date:       list[tuple[str, dict]] = []
    # C: WMS 레코드 없음 → 이력 없음
    no_movement:   list[tuple[str, dict]] = []

    for code, info in parts_master.items():
        if info["grad"] == "졸업":
            continue
        if info["bestone"] <= 0:
            continue
        last_d = last_activity.get(code)
        if last_d is not None:
            if last_d < cutoff:
                unused.append((code, info, last_d))
            # else: 최근 활동 → 포함 안 함
        elif code in has_movement:
            no_date.append((code, info))   # WMS 기록 있으나 날짜 미기재
        else:
            no_movement.append((code, info))  # WMS 이력 없음

    unused.sort(key=lambda x: x[2])  # 오래된 순

    # ── 4. 콘솔 출력 ─────────────────────────────────────────────────────
    total_bestone  = sum(info["bestone"] for _, info, _ in unused)
    no_dt_total    = sum(info["bestone"] for _, info in no_date)
    no_mv_total    = sum(info["bestone"] for _, info in no_movement)

    print(f"\n{'─'*110}")
    print(f"[A] 실제 날짜 기준 {args.months}개월+ 미사용")
    print(f"{'순위':<5} {'파츠코드':<10} {'파츠명':<50} {'마지막활동':<12} {'경과(일)':<8} {'베스트원재고':>10}")
    print(f"{'─'*110}")
    for i, (code, info, last_d) in enumerate(unused, 1):
        elapsed = (today - last_d).days
        print(f"{i:<5} {code:<10} {info['name']:<50} {str(last_d):<12} {elapsed:<8} {info['bestone']:>10,}")
    print(f"{'─'*110}")
    print(f"총 {len(unused)}건  /  베스트원 재고 합계: {total_bestone:,}개")

    if no_date:
        print(f"\n[B] WMS 레코드 있으나 실제 이동일 미기재 — {len(no_date)}건  (베스트원재고: {no_dt_total:,}개)")
        print("    ※ 이동 발생했지만 날짜 미확인 — 실제 현황 확인 필요")
        for code, info in sorted(no_date, key=lambda x: -x[1]["bestone"])[:20]:
            print(f"  {code:<10} {info['name']:<50} {info['bestone']:>8,}")
        if len(no_date) > 20:
            print(f"  ... 외 {len(no_date)-20}건 (MD 파일 참조)")

    if no_movement:
        print(f"\n[C] WMS 이력 전혀 없음 — {len(no_movement)}건  (베스트원재고: {no_mv_total:,}개)")
        for code, info in sorted(no_movement, key=lambda x: -x[1]["bestone"]):
            print(f"  {code:<10} {info['name']:<50} {info['bestone']:>8,}")

    # ── 5. MD 파일 출력 ──────────────────────────────────────────────────
    if args.output:
        _write_md(args.output, unused, no_date, no_movement, today, cutoff, args.months)
        print(f"\n[MD 저장] {args.output}")


def _write_md(
    path: str,
    unused: list[tuple[str, dict, date]],
    no_date: list[tuple[str, dict]],
    no_movement: list[tuple[str, dict]],
    today: date,
    cutoff: date,
    months: int,
) -> None:
    total_A = sum(info["bestone"] for _, info, _ in unused)
    total_B = sum(info["bestone"] for _, info in no_date)
    total_C = sum(info["bestone"] for _, info in no_movement)
    lines: list[str] = [
        "# 장기 미사용 파츠 (베스트원 재고 보유)",
        "",
        f"> **기준**: ⚡movement 실제 이동일 기준 {months}개월 이상 미사용  ",
        f"> 생성: {today}  /  컷오프: {cutoff}  ",
        "> 졸업 파츠 제외 · 베스트원 재고 > 0 필터  ",
        f"> A(미사용확정): {len(unused)}건/{total_A:,}개  "
        f"B(날짜미기재): {len(no_date)}건/{total_B:,}개  "
        f"C(WMS이력없음): {len(no_movement)}건/{total_C:,}개",
        "",
    ]

    # A: 미사용 확정
    if unused:
        by_type: dict[str, list] = {}
        for code, info, last_d in unused:
            t = info.get("type") or "기타"
            by_type.setdefault(t, []).append((code, info, last_d))
        lines += ["## A. 실제 이동일 기준 미사용 확정", ""]
        for type_name, items in sorted(by_type.items()):
            type_total = sum(i["bestone"] for _, i, _ in items)
            lines += [
                f"### {type_name} — {len(items)}개 파츠 / {type_total:,}개",
                "",
                "| 순위 | 파츠코드 | 파츠명 | 마지막 활동일 | 경과(일) | 베스트원 재고 |",
                "|---:|:---|:---|:---:|---:|---:|",
            ]
            for i, (code, info, last_d) in enumerate(items, 1):
                elapsed = (today - last_d).days
                lines.append(f"| {i} | {code} | {info['name']} | {last_d} | {elapsed} | {info['bestone']:,} |")
            lines.append("")
    else:
        lines += ["## A. 실제 이동일 기준 미사용 확정", "", "_(해당 파츠 없음)_", ""]

    # B: WMS 레코드 있으나 날짜 미기재
    if no_date:
        lines += [
            f"## B. WMS 레코드 있으나 실제 이동일 미기재 — {len(no_date)}건 / {total_B:,}개",
            "",
            "> ⚠ 이동 발생 확인되었으나 날짜 미기재 — 실제 현황 직접 확인 필요",
            "",
            "| 파츠코드 | 파츠명 | 유형 | 베스트원 재고 |",
            "|:---|:---|:---|---:|",
        ]
        for code, info in sorted(no_date, key=lambda x: -x[1]["bestone"]):
            lines.append(f"| {code} | {info['name']} | {info['type']} | {info['bestone']:,} |")
        lines.append("")

    # C: WMS 이력 없음
    if no_movement:
        lines += [
            f"## C. WMS 이력 전혀 없음 — {len(no_movement)}건 / {total_C:,}개",
            "",
            "| 파츠코드 | 파츠명 | 유형 | 베스트원 재고 |",
            "|:---|:---|:---|---:|",
        ]
        for code, info in sorted(no_movement, key=lambda x: -x[1]["bestone"]):
            lines.append(f"| {code} | {info['name']} | {info['type']} | {info['bestone']:,} |")

    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
