"""
투입리스트_html.py — 베스트원 → 에이원 자재 투입리스트 HTML 생성기
────────────────────────────────────────────────────────────────────────
movement 베이스(appLui4ZR5HWcQRri)에서 조립투입·생산투입 대상 조회 →
파츠(PT코드)별 그룹핑 + 보충수량 계산 → 프린트 최적화 HTML 출력

사용법:
  python scripts/투입리스트_html.py              # 기본(오늘~+14일), 그룹1만
  python scripts/투입리스트_html.py --days 7     # 7일 이내
  python scripts/투입리스트_html.py --all        # 날짜 제한 없음 (전체 미완료)
  python scripts/투입리스트_html.py --group2     # 생산투입(신시어리웨일즈)만
  python scripts/투입리스트_html.py --both       # 그룹1 + 그룹2 모두
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

# ──────────────────────────────────────────────────────────────────────────────
# Airtable 설정 (movement 베이스)
# ──────────────────────────────────────────────────────────────────────────────
BASE_ID  = "appLui4ZR5HWcQRri"
TABLE_ID = "tblwq7Kj5Y9nVjlOw"
API_URL  = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}"
# movement 베이스용 PAT: AIRTABLE_MOVEMENT_PAT > AIRTABLE_WMS_PAT > AIRTABLE_PAT 순서로 시도
PAT      = (
    os.getenv("AIRTABLE_MOVEMENT_PAT")
    or os.getenv("AIRTABLE_WMS_PAT")
    or os.getenv("AIRTABLE_PAT", "")
)
HEADERS  = {"Authorization": f"Bearer {PAT}"}

# 이동목적 choice ID
MOVE_PURPOSE_G1 = "selwGJ94MwL0h4m39"   # 조립투입
MOVE_PURPOSE_G2 = "selAEMzDXYNmFXJlv"   # 생산투입
# 완료 상태 choice ID (제외)
STATUS_DONE     = "selt0CWNOSqUoL56A"
# 숨김 처리 필드 choice ID (제외)
HIDDEN_ID       = "seljhUVyWRxzUYS56"

# 필드 ID
F_MOV_ID    = "fldOhFtJFBYsxxre7"   # movement_id
F_ITEM      = "fldwZKCYZ4IFOigRp"   # 이동물품
F_PART      = "fldQevLGnuqIuFRVO"   # 출고자재 (PT코드 포함)
F_PURPOSE   = "fldFRNxG1pNooEOC7"   # 이동목적
F_QTY_REQ   = "fld9JMFhIrTDzRzrD"   # 발주요청수량
F_QTY_STOCK = "fldd7yU3V7LEYuKk3"   # 에이원재고
F_DATE      = "fldTS5N9aClRhFUSy"   # 임가공 예정일(+요일)
F_STATUS    = "fld8dqGaGuLHefQUs"   # 자재투입현황
F_PROJECT   = "fldyIAHkFOzfnW4TW"   # project (조립투입)
F_SUPPLIER  = "fldZXtEg9gLBMcGZh"   # 수주처 (생산투입: 신시어리웨일즈)
F_MAT_TYPE  = "fldIBiWgP52yoWaMz"   # 출고자재_자재구분
F_PKG_TASK  = "fldh2SAAq7u7tZUkG"   # pkg_task


# ──────────────────────────────────────────────────────────────────────────────
# 유틸
# ──────────────────────────────────────────────────────────────────────────────
def parse_qty(v) -> float:
    try:
        return float(str(v).replace(",", "")) if v else 0.0
    except Exception:
        return 0.0


def parse_date_str(s: str) -> date | None:
    """'4/14 (화)' 또는 'M/D' 형식 파싱. 60일 이상 과거면 내년으로."""
    if not s:
        return None
    s = str(s).strip()
    m = re.match(r"(\d{1,2})/(\d{1,2})", s)
    if not m:
        return None
    today = date.today()
    mo, dy = int(m.group(1)), int(m.group(2))
    try:
        d = date(today.year, mo, dy)
        if (today - d).days > 60:
            d = date(today.year + 1, mo, dy)
        return d
    except ValueError:
        return None


def extract_pt_code(part_str: str) -> str:
    """'PT1493-오픈박스... || PNA50803 || 에이원' → 'PT1493-오픈박스...' """
    if not part_str:
        return ""
    return part_str.split(" || ")[0].strip()


def airtable_get_all(extra_params: dict | None = None) -> list:
    params = {"pageSize": 100}
    if extra_params:
        params.update(extra_params)
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


# ──────────────────────────────────────────────────────────────────────────────
# 데이터 조회
# ──────────────────────────────────────────────────────────────────────────────
def fetch_group(
    purpose_id: str,
    start_date: date | None,
    end_date: date | None,
    require_pkg_task: bool = True,
    supplier_filter: str | None = None,
) -> list:
    raw = airtable_get_all()

    result = []
    for r in raw:
        f = r.get("fields", {})

        # 이동목적 필터
        purposes = f.get(F_PURPOSE) or []
        if isinstance(purposes, str):
            purposes = [purposes]
        if purpose_id not in purposes:
            continue

        # 완료 상태 제외
        statuses = f.get(F_STATUS) or []
        if isinstance(statuses, str):
            statuses = [statuses]
        if STATUS_DONE in statuses:
            continue

        # 숨김 처리 제외 (fldwgaM8OnKubM8oE — 필드 존재 시)
        hidden_vals = f.get("fldwgaM8OnKubM8oE") or []
        if isinstance(hidden_vals, str):
            hidden_vals = [hidden_vals]
        if HIDDEN_ID in hidden_vals:
            continue

        # 에이원 포함 여부
        item_str = str(f.get(F_ITEM) or "")
        if "에이원" not in item_str:
            continue

        # 생산품자재 제외 (그룹1만)
        mat_type = str(f.get(F_MAT_TYPE) or "")
        if require_pkg_task and "생산품자재" in mat_type:
            continue

        # pkg_task 필수 (그룹1만)
        if require_pkg_task and not f.get(F_PKG_TASK):
            continue

        # 돌돌이/양면테이프 제외 (그룹1만)
        if require_pkg_task:
            if "돌돌이" in item_str or "양면테이프" in item_str:
                continue

        # 수주처 필터 (그룹2)
        if supplier_filter:
            supplier = str(f.get(F_SUPPLIER) or "")
            if supplier_filter not in supplier:
                continue

        # 날짜 파싱 & 필터 (그룹1만)
        date_str = str(f.get(F_DATE) or "")
        d = parse_date_str(date_str)
        if require_pkg_task:
            if not d:
                continue  # 그룹1: 날짜 없으면 제외
            if start_date and end_date:
                if not (start_date <= d <= end_date):
                    continue

        part_str = str(f.get(F_PART) or "")
        pt_code  = extract_pt_code(part_str)
        project  = str(f.get(F_PROJECT) or "").strip()
        if not project:
            project = str(f.get(F_SUPPLIER) or "").strip() or "(프로젝트 없음)"

        result.append({
            "rec_id":    r["id"],
            "mov_id":    str(f.get(F_MOV_ID) or r["id"])[:18],
            "pt_code":   pt_code,
            "part":      part_str,
            "project":   project,
            "date":      d,
            "date_str":  date_str,
            "qty_req":   parse_qty(f.get(F_QTY_REQ)),
            "qty_stock": parse_qty(f.get(F_QTY_STOCK)),
            "status":    str(statuses[0] if statuses else ""),
            "mat_type":  mat_type,
        })

    return result


def calc_restock(pt_rows: list) -> float:
    """보충수량 = MAX(0, 총 발주요청수량 - 에이원재고 + 100)"""
    total_req   = sum(r["qty_req"] for r in pt_rows)
    stock       = pt_rows[0]["qty_stock"] if pt_rows else 0.0
    return max(0.0, total_req - stock + 100)


# ──────────────────────────────────────────────────────────────────────────────
# 그룹핑
# ──────────────────────────────────────────────────────────────────────────────
def group_by_pt(records: list) -> list:
    """PT코드 기준으로 그룹핑 + 보충수량 계산."""
    grouped: dict[str, list] = defaultdict(list)
    for r in records:
        key = r["pt_code"] or r["part"] or "(PT코드 없음)"
        grouped[key].append(r)

    result = []
    for pt_key, rows in grouped.items():
        restock  = calc_restock(rows)
        stock    = rows[0]["qty_stock"]
        min_date = min((r["date"] for r in rows if r["date"]), default=None)
        result.append({
            "pt_key":    pt_key,
            "rows":      rows,
            "total_req": sum(r["qty_req"] for r in rows),
            "stock":     stock,
            "restock":   restock,
            "min_date":  min_date,
            "count":     len(rows),
        })

    # 보충수량 > 0 인 파츠만
    result = [g for g in result if g["restock"] > 0]
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


# ──────────────────────────────────────────────────────────────────────────────
# HTML 생성
# ──────────────────────────────────────────────────────────────────────────────
def build_group_rows(groups: list, show_date_col: bool) -> str:
    rows = []
    for g in groups:
        ug = urgency_class(g["min_date"])
        dt_badge = g["min_date"].strftime("%m/%d (%a)") if g["min_date"] else "날짜 미정"
        restock_badge = f'<span class="badge {ug}">{int(g["restock"]):,}개 보충</span>'

        # PT 헤더 행
        date_td = f'<td class="date-cell">{dt_badge}</td>' if show_date_col else ""
        rows.append(f"""
  <tr class="pt-header {ug}">
    <td class="chk-cell"><input type="checkbox"></td>
    <td class="pt-name" colspan="{"3" if show_date_col else "4"}">
      <span class="pt-label">{g["pt_key"][:60]}</span>
      <span class="sub-cnt">&nbsp;{g["count"]}건</span>
    </td>
    {date_td}
    <td class="restock-cell">{restock_badge}</td>
  </tr>""")

        # 레코드 행
        for r in sorted(g["rows"], key=lambda x: x["date"] or date.max):
            date_td2 = f'<td class="date-col">{r["date_str"] or "-"}</td>' if show_date_col else ""
            rows.append(f"""
  <tr class="item-row">
    <td><input type="checkbox" class="item-chk"></td>
    <td class="id-cell">{r["mov_id"]}</td>
    <td class="proj-cell">{r["project"][:30]}</td>
    <td class="qty-cell"><b class="qty-num">{int(r["qty_req"]):,}개</b></td>
    {date_td2}
    <td class="stock-col">재고 <b>{int(r["qty_stock"]):,}</b></td>
  </tr>""")

    return "".join(rows)


def build_html(
    g1_groups: list,
    g2_groups: list,
    date_label: str,
) -> str:
    today_str = date.today().strftime("%Y-%m-%d")
    total_pt  = len(g1_groups) + len(g2_groups)
    total_rec = sum(g["count"] for g in g1_groups + g2_groups)

    rows_g1 = build_group_rows(
        sorted(g1_groups, key=lambda x: x["min_date"] or date.max),
        show_date_col=True,
    )
    rows_g2 = build_group_rows(
        sorted(g2_groups, key=lambda x: -x["restock"]),
        show_date_col=False,
    )

    no_data = '<tr><td colspan="6" class="empty-msg">보충 필요 파츠 없음 ✅</td></tr>'

    def section(title: str, rows: str, count: int, show_date: bool) -> str:
        cols = "<th>이동ID</th><th>프로젝트</th><th>발주요청</th>"
        if show_date:
            cols += "<th>임가공예정일</th>"
        cols += "<th>에이원재고</th>"
        return f"""
<section>
  <h2 class="section-title">{title} — 보충필요 {count}개 파츠</h2>
  <table>
    <thead>
      <tr>
        <th style="width:34px"></th>
        {cols}
        <th>보충수량</th>
      </tr>
    </thead>
    <tbody>
      {rows if count else no_data}
    </tbody>
  </table>
</section>"""

    sec1 = section("조립투입 재고자재",     rows_g1, len(g1_groups), show_date=True)
    sec2 = section("생산투입 (신시어리웨일즈)", rows_g2, len(g2_groups), show_date=False)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>투입리스트 {today_str}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Malgun Gothic', '맑은 고딕', sans-serif;
    font-size: 13px;
    color: #1a1a2e;
    background: #f0f4f8;
    padding: 16px;
  }}

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
  .page-header h1 {{ font-size: 20px; font-weight: 700; }}
  .page-header .sub {{ font-size: 12px; opacity: 0.7; margin-top: 4px; }}
  .page-header .meta {{ font-size: 11px; opacity: 0.82; text-align: right; line-height: 1.8; }}

  .summary-row {{ display: flex; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }}
  .chip {{
    background: white; border-radius: 20px; padding: 5px 16px;
    font-size: 12px; box-shadow: 0 1px 4px rgba(0,0,0,0.10);
    border-left: 4px solid #1a3a5c;
  }}
  .chip b {{ color: #1a3a5c; }}

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

  section {{ margin-bottom: 20px; }}
  .section-title {{
    font-size: 15px; font-weight: 700; color: #1a2744;
    padding: 8px 0 8px 10px;
    border-left: 4px solid #1a3a5c;
    margin-bottom: 8px;
  }}

  table {{
    width: 100%; border-collapse: collapse;
    background: white; border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 1px 8px rgba(0,0,0,0.10);
  }}
  thead tr {{ background: #1a3a5c; color: white; }}
  th {{
    padding: 9px 10px; font-size: 11px;
    font-weight: 600; text-align: left; white-space: nowrap;
  }}
  th:first-child {{ width: 34px; }}

  tr.pt-header td {{ padding: 11px 10px 9px; border-top: 2px solid #e2e8f0; }}
  tr.pt-header.urgent  {{ background: #FFF5F5; border-left: 5px solid #E53E3E; }}
  tr.pt-header.warning {{ background: #FFFBF0; border-left: 5px solid #E67E22; }}
  tr.pt-header.normal  {{ background: #EFF6FF; border-left: 5px solid #3B82F6; }}
  .pt-label {{ font-size: 13px; font-weight: 700; color: #1a2744; }}
  .sub-cnt {{ font-size: 11px; color: #888; }}
  td.chk-cell {{ width: 34px; text-align: center; }}
  td.chk-cell input[type=checkbox], .item-chk {{
    width: 16px; height: 16px; cursor: pointer; accent-color: #1a3a5c;
  }}

  tr.item-row {{ border-left: 5px solid transparent; }}
  tr.item-row:nth-child(even) {{ background: #fafbff; }}
  tr.item-row:hover {{ background: #EFF6FF; }}
  tr.item-row td {{
    padding: 6px 10px; font-size: 12px;
    border-bottom: 1px solid #eef0f6; vertical-align: middle;
  }}

  .id-cell {{
    font-family: 'Consolas', 'D2Coding', monospace;
    font-size: 11px; color: #4A5FA5; white-space: nowrap;
  }}
  .proj-cell {{ color: #1a1a2e; font-weight: 500; }}
  .qty-cell {{ white-space: nowrap; }}
  .qty-num {{ color: #1a3a5c; font-size: 13px; }}
  .date-col {{ font-size: 11px; color: #666; white-space: nowrap; }}
  .stock-col {{ font-size: 11px; color: #555; white-space: nowrap; }}
  td.date-cell {{ font-size: 12px; white-space: nowrap; color: #555; }}
  td.restock-cell {{ white-space: nowrap; text-align: right; padding-right: 12px; }}

  .badge {{
    display: inline-block; padding: 3px 10px;
    border-radius: 12px; font-size: 12px; font-weight: 700;
  }}
  .badge.urgent  {{ background: #FED7D7; color: #C53030; }}
  .badge.warning {{ background: #FEEBC8; color: #9C6E00; }}
  .badge.normal  {{ background: #BEE3F8; color: #2B6CB0; }}

  .empty-msg {{ padding: 28px; text-align: center; color: #aaa; font-size: 13px; }}

  @media print {{
    body {{ background: white; padding: 6px; font-size: 11px; }}
    .page-header, tr.pt-header, .badge, thead {{
      -webkit-print-color-adjust: exact; print-color-adjust: exact;
    }}
    .summary-row, .legend {{ page-break-inside: avoid; }}
    table {{ page-break-inside: auto; }}
    tr.pt-header {{ page-break-before: auto; page-break-after: avoid; }}
    tr.item-row {{ page-break-inside: avoid; }}
  }}
</style>
</head>
<body>

<div class="page-header">
  <div>
    <h1>📦 자재 투입리스트</h1>
    <div class="sub">베스트원 → 에이원 자재 보충 현황</div>
  </div>
  <div class="meta">
    조회 범위: {date_label}<br>
    생성: {today_str}<br>
    {total_pt}개 파츠 · {total_rec}건
  </div>
</div>

<div class="summary-row">
  <div class="chip">조립투입 보충필요: <b>{len(g1_groups)}개 파츠</b></div>
  <div class="chip">생산투입 보충필요: <b>{len(g2_groups)}개 파츠</b></div>
  <div class="chip">총 파츠: <b>{total_pt}개</b></div>
</div>

<div class="legend">
  <b>임박도 (조립투입)</b>
  <span><span class="leg-dot dot-urgent"></span>오늘·내일 (긴급)</span>
  <span><span class="leg-dot dot-warning"></span>3일 이내 (주의)</span>
  <span><span class="leg-dot dot-normal"></span>4일 이후</span>
  <span style="margin-left:auto;color:#888">보충수량 = MAX(0, 총 발주요청 − 에이원재고 + 100)</span>
</div>

{sec1}
{sec2}

</body>
</html>"""


# ──────────────────────────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="자재 투입리스트 HTML 생성 (베스트원→에이원)")
    parser.add_argument("--days",   type=int,  help="임가공예정일 기준 N일 이내 (그룹1)")
    parser.add_argument("--all",    action="store_true", help="날짜 제한 없음")
    parser.add_argument("--group2", action="store_true", help="생산투입(신시어리웨일즈)만")
    parser.add_argument("--both",   action="store_true", help="그룹1 + 그룹2 모두 (기본값)")
    args = parser.parse_args()

    if not PAT:
        print("[ERROR] AIRTABLE_WMS_PAT 또는 AIRTABLE_PAT 환경변수를 .env에 설정하세요")
        sys.exit(1)

    today = date.today()

    # 날짜 범위 결정 (그룹1용)
    if args.all or args.group2:
        start_d, end_d = None, None
        date_label = "전체 미완료"
    elif args.days:
        start_d = today
        end_d   = today + timedelta(days=args.days)
        date_label = f"{today.strftime('%m/%d')} ~ {end_d.strftime('%m/%d')} ({args.days}일)"
    else:
        start_d = today
        end_d   = today + timedelta(days=14)
        date_label = f"{today.strftime('%m/%d')} ~ {end_d.strftime('%m/%d')} (14일)"

    show_g1 = not args.group2
    show_g2 = args.group2 or args.both or (not args.group2)  # 기본 both

    g1_groups, g2_groups = [], []

    if show_g1:
        print("▶ 그룹1 (조립투입) 조회 중…")
        recs1 = fetch_group(
            purpose_id=MOVE_PURPOSE_G1,
            start_date=start_d,
            end_date=end_d,
            require_pkg_task=True,
        )
        g1_groups = group_by_pt(recs1)
        g1_groups.sort(key=lambda x: x["min_date"] or date.max)
        print(f"  → 보충필요 {len(g1_groups)}개 파츠 ({sum(g['count'] for g in g1_groups)}건)")

    if show_g2:
        print("▶ 그룹2 (생산투입/신시어리웨일즈) 조회 중…")
        recs2 = fetch_group(
            purpose_id=MOVE_PURPOSE_G2,
            start_date=None,
            end_date=None,
            require_pkg_task=False,
            supplier_filter="신시어리웨일즈",
        )
        g2_groups = group_by_pt(recs2)
        g2_groups.sort(key=lambda x: -x["restock"])
        print(f"  → 보충필요 {len(g2_groups)}개 파츠 ({sum(g['count'] for g in g2_groups)}건)")

    if not g1_groups and not g2_groups:
        print("보충 필요 파츠 없음 — HTML 생성 건너뜀")
        return

    html      = build_html(g1_groups, g2_groups, date_label)
    today_str = today.strftime("%Y-%m-%d")
    out_path  = rf"C:\Users\yjisu\Desktop\SCM_WORK\투입리스트_{today_str}.html"

    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(html)

    print(f"\n✅ HTML 생성 완료 → {out_path}")
    print("   브라우저에서 열거나 Ctrl+P 로 프린트하세요")

    try:
        import subprocess
        subprocess.Popen(["start", out_path], shell=True)
    except Exception:
        pass


if __name__ == "__main__":
    main()
