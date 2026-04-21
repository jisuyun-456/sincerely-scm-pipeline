"""
picking_list_html.py  (v2 — Barcode 베이스)
────────────────────────────────────────────────────────────────────────────
다영기획 이동 피킹리스트 HTML 생성기

Barcode 베이스 이동리스트(tblnxU0PlegXT7bYj)에서 다영기획 이동 대상 조회 →
프로젝트(PNA번호)별 그룹핑 → 피킹 작업에 최적화된 HTML 출력

특징:
  - 프로젝트(PNA번호)별 그룹핑 — 박스 단위 작업 흐름에 맞춤
  - 임박 날짜 기준 색상 코딩 (오늘·내일=긴급, 3일 이내=주의)
  - PT코드 + 품목명 + 수량 + 박스수 명시
  - 체크박스 (프린트 후 펜으로 체크)
  - A4 프린트 최적화 (Ctrl+P)

사용법:
  python scripts/picking_list_html.py              # 전체 미완료
  python scripts/picking_list_html.py --days 7     # 7일 이내 이동 예정
  python scripts/picking_list_html.py --date 2026-04-25  # 특정 날짜
  python scripts/picking_list_html.py --all        # 날짜 제한 없음 (기본)
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

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

# ────────────────────────────────────────────────────────────────────────────
# 상수 (Barcode 베이스)
# ────────────────────────────────────────────────────────────────────────────
BASE_ID  = "app4LvuNIDiqTmhnv"    # Barcode 베이스
TABLE_ID = "tblnxU0PlegXT7bYj"   # 이동리스트
API_URL  = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}"
PAT      = os.getenv("AIRTABLE_WMS_PAT") or os.getenv("AIRTABLE_PAT", "")
HEADERS  = {"Authorization": f"Bearer {PAT}"}

# 필드명 (이동리스트 — Barcode 베이스 실측 확인)
F_MOV_ID    = "movement_id"
F_PT        = "파츠코드"
F_OUT       = "출고물품"
F_QTY_MOV   = "이동수량"
F_QTY_PLAN  = "계획수량"
F_QTY_CONF  = "이동수량(확정)"
F_BOX       = "라벨 박스수량"
F_PROJECT   = "project"
F_DATE      = "임가공 예정일"       # 형식: "November 27, 2025"
F_LOCATION  = "재고좌표(합산)"      # 실측 필드명
F_STATUS    = "이동리스트현황(확정수량으로)"
F_MAT_TYPE  = "출고자재_자재구분"


# ────────────────────────────────────────────────────────────────────────────
# 유틸
# ────────────────────────────────────────────────────────────────────────────
def parse_qty(v) -> int:
    try:
        return int(float(str(v).replace(",", ""))) if v else 0
    except Exception:
        return 0


def parse_date_str(s: str) -> date | None:
    if not s:
        return None
    s = str(s).strip()
    # ISO: 2026-04-25
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    # Airtable 날짜 형식: "November 27, 2025" / "April 25, 2026"
    from datetime import datetime
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    # M/D 형식: 4/25
    m2 = re.match(r"(\d{1,2})/(\d{1,2})", s)
    if m2:
        today = date.today()
        mo, dy = int(m2.group(1)), int(m2.group(2))
        try:
            d = date(today.year, mo, dy)
            if (today - d).days > 60:
                d = date(today.year + 1, mo, dy)
            return d
        except ValueError:
            pass
    return None


def airtable_get(params: dict) -> list:
    records, offset = [], None
    while True:
        p = dict(params)
        if offset:
            p["offset"] = offset
        resp = requests.get(API_URL, headers=HEADERS, params=p, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records


# ────────────────────────────────────────────────────────────────────────────
# 데이터 조회
# ────────────────────────────────────────────────────────────────────────────
def fetch_picking(start_date: date | None, end_date: date | None) -> list:
    """이동리스트 조회 (Barcode 베이스 = 다영기획 전용)

    주의: 일부 필드명에 괄호()가 포함되어 fields[] 파라미터 422 오류 발생.
    → fields[] 없이 전체 레코드 조회 후 클라이언트에서 필드 추출.
    """
    raw = airtable_get({
        "pageSize": 100,
    })

    result = []
    for r in raw:
        f = r.get("fields", {})

        # 날짜 파싱
        d = parse_date_str(f.get(F_DATE, ""))

        # 날짜 범위 필터 (클라이언트 사이드)
        if start_date and end_date and d:
            if not (start_date <= d <= end_date):
                continue

        # 완료 제외 (클라이언트 사이드 — 필드명 불확실 시 안전 처리)
        status = (f.get(F_STATUS) or "").strip()
        if status in ("피킹완료", "자재투입완료", "완료"):
            continue

        pt   = (f.get(F_PT) or "").strip()
        name = (f.get(F_OUT) or "").strip()
        product = f"{pt}-{name}" if pt and name else (pt or name or "-")

        qty   = parse_qty(
            f.get(F_QTY_CONF) or f.get(F_QTY_MOV) or f.get(F_QTY_PLAN)
        )
        boxes = max(1, parse_qty(f.get(F_BOX)) or 1)

        result.append({
            "rec_id":   r["id"],
            "mov_id":   (f.get(F_MOV_ID) or r["id"])[:18],
            "pt":       pt,
            "name":     name,
            "product":  product,
            "project":  (f.get(F_PROJECT) or "").strip(),
            "date":     d,
            "date_str": str(f.get(F_DATE) or "")[:10],
            "qty":      qty,
            "boxes":    boxes,
            "location": (f.get(F_LOCATION) or "").strip(),
            "status":   status,
            "mat_type": (f.get(F_MAT_TYPE) or "").strip(),
        })

    return result


# ────────────────────────────────────────────────────────────────────────────
# 그룹핑
# ────────────────────────────────────────────────────────────────────────────
def group_by_project(records: list) -> list:
    grouped: dict[str, list] = defaultdict(list)
    for r in records:
        key = r["project"] or "(프로젝트 없음)"
        grouped[key].append(r)

    result = []
    for proj, recs in grouped.items():
        total_qty  = sum(r["qty"] for r in recs)
        total_box  = sum(r["boxes"] for r in recs)
        min_date   = min((r["date"] for r in recs if r["date"]), default=None)
        result.append({
            "project":   proj,
            "recs":      sorted(recs, key=lambda x: x["pt"]),
            "total_qty": total_qty,
            "total_box": total_box,
            "min_date":  min_date,
        })

    result.sort(key=lambda x: x["min_date"] or date.max)
    return result


def urgency_class(d: date | None) -> str:
    if d is None:
        return "normal"
    diff = (d - date.today()).days
    if diff <= 1:
        return "urgent"
    if diff <= 3:
        return "warning"
    return "normal"


# ────────────────────────────────────────────────────────────────────────────
# HTML 생성
# ────────────────────────────────────────────────────────────────────────────
def build_html(groups: list, date_label: str) -> str:
    today_str  = date.today().strftime("%Y-%m-%d")
    total_proj = len(groups)
    total_items = sum(len(g["recs"]) for g in groups)
    total_qty   = sum(g["total_qty"] for g in groups)
    total_box   = sum(g["total_box"] for g in groups)

    # ── 테이블 행 생성 ──────────────────────────────────────────────────────
    def make_rows() -> str:
        rows = []
        for g in groups:
            ug       = urgency_class(g["min_date"])
            dt_badge = g["min_date"].strftime("%m/%d (%a)") if g["min_date"] else "날짜 없음"
            qty_badge = f'<span class="badge {ug}">{g["total_qty"]:,}개</span>'

            # 프로젝트 헤더 행
            rows.append(f"""
  <tr class="proj-header {ug}">
    <td class="chk-cell"><input type="checkbox"></td>
    <td class="proj-name" colspan="4">
      <span class="proj-label">{g['project']}</span>
      <span class="sub-cnt">&nbsp;{len(g['recs'])}품목 / {g['total_box']}박스</span>
    </td>
    <td class="date-cell">{dt_badge}</td>
    <td class="qty-cell">{qty_badge}</td>
  </tr>""")

            # 품목 행들
            for r in g["recs"]:
                loc_html = (
                    f'<span class="loc">{r["location"]}</span>'
                    if r["location"] else
                    '<span class="loc empty">-</span>'
                )
                mat_html = (
                    f'<span class="mat-type">{r["mat_type"]}</span>'
                    if r["mat_type"] else ""
                )
                rows.append(f"""
  <tr class="item-row">
    <td><input type="checkbox" class="item-chk"></td>
    <td class="pt-cell">{r['pt'] or '-'}</td>
    <td class="name-cell">{(r['name'] or r['product'])[:50]}</td>
    <td class="mat-cell">{mat_html}</td>
    <td class="loc-col">{loc_html}</td>
    <td class="date-col">{r['date_str'] or '-'}</td>
    <td class="qty-col">
      <b class="qty-num">{r['qty']:,}개</b>
      <span class="box-cnt">{r['boxes']}박스</span>
    </td>
  </tr>""")

        return "".join(rows)

    rows_html = make_rows()
    empty_msg = '<tr><td colspan="7" class="empty-msg">이동 예정 피킹 항목 없음</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>다영기획 이동 피킹리스트 {today_str}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Malgun Gothic', '맑은 고딕', sans-serif;
    font-size: 13px;
    color: #1a1a2e;
    background: #f0f4f8;
    padding: 16px;
  }}

  /* ── 페이지 헤더 ── */
  .page-header {{
    background: linear-gradient(135deg, #1a3a5c, #0d2236);
    color: white;
    border-radius: 10px;
    padding: 16px 22px;
    margin-bottom: 14px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    box-shadow: 0 3px 10px rgba(0,0,0,0.2);
  }}
  .page-header h1 {{ font-size: 20px; font-weight: 700; letter-spacing: -0.3px; }}
  .page-header .sub {{ font-size: 12px; opacity: 0.7; margin-top: 4px; }}
  .page-header .meta {{ font-size: 11px; opacity: 0.82; text-align: right; line-height: 1.8; }}

  /* ── 요약 칩 ── */
  .summary-row {{
    display: flex; gap: 10px; margin-bottom: 12px; flex-wrap: wrap;
  }}
  .chip {{
    background: white; border-radius: 20px; padding: 5px 16px;
    font-size: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.10);
    border-left: 4px solid #1a3a5c;
  }}
  .chip b {{ color: #1a3a5c; }}

  /* ── 범례 ── */
  .legend {{
    display: flex; gap: 16px; margin-bottom: 12px;
    font-size: 11px; align-items: center; flex-wrap: wrap;
    background: white; padding: 8px 14px; border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }}
  .legend b {{ margin-right: 6px; color: #444; }}
  .leg-dot {{
    display: inline-block; width: 10px; height: 10px;
    border-radius: 2px; margin-right: 4px; vertical-align: middle;
  }}
  .dot-urgent  {{ background: #E53E3E; }}
  .dot-warning {{ background: #E67E22; }}
  .dot-normal  {{ background: #3B82F6; }}

  /* ── 테이블 ── */
  table {{
    width: 100%; border-collapse: collapse;
    background: white; border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 1px 8px rgba(0,0,0,0.10);
  }}
  thead tr {{
    background: #1a3a5c; color: white;
  }}
  th {{
    padding: 9px 10px; font-size: 11px;
    font-weight: 600; text-align: left; white-space: nowrap;
  }}
  th:first-child {{ width: 34px; }}

  /* ── 프로젝트 헤더 행 ── */
  tr.proj-header td {{
    padding: 11px 10px 9px;
    border-top: 2px solid #e2e8f0;
  }}
  tr.proj-header.urgent  {{
    background: #FFF5F5;
    border-left: 5px solid #E53E3E;
  }}
  tr.proj-header.warning {{
    background: #FFFBF0;
    border-left: 5px solid #E67E22;
  }}
  tr.proj-header.normal  {{
    background: #EFF6FF;
    border-left: 5px solid #3B82F6;
  }}
  .proj-label {{
    font-size: 14px; font-weight: 700; color: #1a2744;
  }}
  .sub-cnt {{ font-size: 11px; color: #888; }}
  td.chk-cell {{ width: 34px; text-align: center; }}
  td.chk-cell input[type=checkbox],
  .item-chk {{
    width: 16px; height: 16px; cursor: pointer;
    accent-color: #1a3a5c;
  }}

  /* ── 품목 행 ── */
  tr.item-row {{ border-left: 5px solid transparent; }}
  tr.item-row:nth-child(even) {{ background: #fafbff; }}
  tr.item-row:hover {{ background: #EFF6FF; }}
  tr.item-row td {{
    padding: 6px 10px; font-size: 12px;
    border-bottom: 1px solid #eef0f6;
    vertical-align: middle;
  }}

  /* ── PT코드 ── */
  .pt-cell {{
    font-family: 'Consolas', 'D2Coding', monospace;
    font-size: 11.5px; color: #4A5FA5;
    font-weight: 600; white-space: nowrap; min-width: 80px;
  }}

  /* ── 품목명 ── */
  .name-cell {{ font-weight: 500; color: #1a1a2e; }}

  /* ── 수량 ── */
  .qty-col {{ white-space: nowrap; }}
  .qty-num {{ color: #1a3a5c; font-size: 13px; }}
  .box-cnt {{
    font-size: 10px; color: #888;
    background: #f0f4f8; padding: 1px 6px;
    border-radius: 3px; margin-left: 4px;
  }}
  .date-col {{ font-size: 11px; color: #666; white-space: nowrap; }}

  /* ── 재고위치 ── */
  .loc {{
    font-family: 'Consolas', monospace; font-size: 11px;
    background: #EEF2FF; padding: 2px 8px;
    border-radius: 4px; color: #4338CA; white-space: nowrap;
    font-weight: 600;
  }}
  .loc.empty {{ color: #bbb; background: #f5f5f5; font-weight: 400; }}
  .loc-col {{ white-space: nowrap; }}

  /* ── 자재구분 ── */
  .mat-type {{
    font-size: 10px; padding: 2px 7px;
    border-radius: 3px; white-space: nowrap;
    background: #E8F5E9; color: #2E7D32;
  }}

  /* ── 배지 ── */
  .badge {{
    display: inline-block; padding: 3px 10px;
    border-radius: 12px; font-size: 12px; font-weight: 700;
  }}
  .badge.urgent  {{ background: #FED7D7; color: #C53030; }}
  .badge.warning {{ background: #FEEBC8; color: #9C6E00; }}
  .badge.normal  {{ background: #BEE3F8; color: #2B6CB0; }}

  /* ── 날짜 / 수량 셀 ── */
  td.date-cell {{ font-size: 12px; white-space: nowrap; color: #555; }}
  td.qty-cell  {{ white-space: nowrap; text-align: right; padding-right: 12px; }}

  /* ── 빈 결과 ── */
  .empty-msg {{
    padding: 28px; text-align: center;
    color: #aaa; font-size: 13px;
  }}

  /* ── 프린트 최적화 ── */
  @media print {{
    body {{ background: white; padding: 6px; font-size: 11px; }}
    .page-header, tr.proj-header, .badge, thead {{
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }}
    .summary-row, .legend {{ page-break-inside: avoid; }}
    table {{ page-break-inside: auto; }}
    tr.proj-header {{ page-break-before: auto; page-break-after: avoid; }}
    tr.item-row {{ page-break-inside: avoid; }}
  }}
</style>
</head>
<body>

<div class="page-header">
  <div>
    <h1>📦 다영기획 이동 피킹리스트</h1>
    <div class="sub">에이원지식산업센터 → 다영기획 (임가공 이동)</div>
  </div>
  <div class="meta">
    조회 범위: {date_label}<br>
    생성: {today_str}<br>
    {total_proj}개 프로젝트 · {total_items}품목 · {total_qty:,}개 · {total_box}박스
  </div>
</div>

<div class="summary-row">
  <div class="chip">프로젝트: <b>{total_proj}개</b></div>
  <div class="chip">품목 종류: <b>{total_items}건</b></div>
  <div class="chip">총 수량: <b>{total_qty:,}개</b></div>
  <div class="chip">총 박스: <b>{total_box}박스</b></div>
</div>

<div class="legend">
  <b>임박도</b>
  <span><span class="leg-dot dot-urgent"></span>오늘·내일 (긴급)</span>
  <span><span class="leg-dot dot-warning"></span>3일 이내 (주의)</span>
  <span><span class="leg-dot dot-normal"></span>4일 이후</span>
  <span style="margin-left:auto;color:#888">
    <span class="loc" style="font-size:10px">A-2-1</span> 재고위치
    &nbsp;|&nbsp;
    <span class="mat-type">생산품자재</span> 자재구분
  </span>
</div>

<table>
  <thead>
    <tr>
      <th></th>
      <th>PT코드</th>
      <th>품목명</th>
      <th>자재구분</th>
      <th>재고위치</th>
      <th>이동예정일</th>
      <th>수량 / 박스</th>
    </tr>
  </thead>
  <tbody>
    {rows_html if groups else empty_msg}
  </tbody>
</table>

</body>
</html>"""


# ────────────────────────────────────────────────────────────────────────────
# 메인
# ────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="다영기획 이동 피킹리스트 HTML 생성")
    parser.add_argument("--days",  type=int, help="이동 예정일 기준 N일 이내 (예: 7)")
    parser.add_argument("--date",  type=str, help="특정 날짜 (YYYY-MM-DD)")
    parser.add_argument("--all",   action="store_true", help="날짜 제한 없음 (기본값)")
    args = parser.parse_args()

    if not PAT:
        print("[ERROR] AIRTABLE_WMS_PAT 환경변수를 .env에 설정하세요")
        sys.exit(1)

    today = date.today()

    if args.date:
        try:
            target = date.fromisoformat(args.date)
        except ValueError:
            print(f"[ERROR] 날짜 형식 오류: {args.date}  →  YYYY-MM-DD 형식 사용")
            sys.exit(1)
        start_d, end_d = target, target
        date_label = target.strftime("%Y-%m-%d")
    elif args.days:
        start_d = today
        end_d   = today + timedelta(days=args.days)
        date_label = f"{today.strftime('%m/%d')} ~ {end_d.strftime('%m/%d')} ({args.days}일)"
    else:
        start_d, end_d = None, None
        date_label = "전체 (날짜 무제한)"

    print(f"▶ 이동리스트 조회 중… ({date_label})")
    records = fetch_picking(start_d, end_d)
    print(f"  조회: {len(records)}건")

    if not records:
        print("피킹 대상 없음 — HTML 생성 건너뜀")
        return

    groups = group_by_project(records)
    total_qty = sum(g["total_qty"] for g in groups)
    print(f"  → {len(groups)}개 프로젝트 / 총 {total_qty:,}개\n")
    for g in groups:
        dt = g["min_date"].strftime("%m/%d") if g["min_date"] else "날짜 없음"
        ug = "🔴" if urgency_class(g["min_date"]) == "urgent" else \
             "🟡" if urgency_class(g["min_date"]) == "warning" else "🔵"
        print(f"  {ug} {g['project'][:28]:<28} | {len(g['recs'])}품목 | "
              f"{g['total_qty']:>6,}개 | {g['total_box']}박스 | {dt}")

    html      = build_html(groups, date_label)
    today_str = today.strftime("%Y-%m-%d")
    out_path  = rf"C:\Users\yjisu\Desktop\SCM_WORK\다영기획_피킹리스트_{today_str}.html"

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    print(f"\n✅ HTML 생성 완료 → {out_path}")
    print("   브라우저에서 열어 확인하거나 Ctrl+P 로 프린트하세요")

    # Windows 자동 브라우저 열기
    try:
        import subprocess
        subprocess.Popen(["start", out_path], shell=True)
    except Exception:
        pass


if __name__ == "__main__":
    main()
