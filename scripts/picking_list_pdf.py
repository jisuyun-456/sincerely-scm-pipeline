"""
picking_list_pdf.py
────────────────────────────────────────────────────────────────────────────
다영기획 이동 피킹리스트 PDF 생성기 (Airtable 미니익스텐션 대체)

특징:
  - 프로젝트(PNA)별 섹션, 임박도 색상 코딩
  - 자재구분 서브그룹: 재고자재 → 생산품자재 순
  - 재고자재는 공통 재고좌표 헤더에 표시
  - 입고박스 수량 표시 (sync_box_count.py 실행 후 채워짐)
  - ReportLab PDF, A4 프린트 최적화

사용법:
  python scripts/picking_list_pdf.py                     # 전체 미완료
  python scripts/picking_list_pdf.py --date 2026-04-22  # 특정 날짜
  python scripts/picking_list_pdf.py --project PNA38579  # 프로젝트 필터
  python scripts/picking_list_pdf.py --days 7           # 7일 이내
  python scripts/picking_list_pdf.py --dry-run          # 미리보기만
"""

import argparse, os, re, sys, time
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Table, TableStyle

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

# ────────────────────────────────────────────────────────────────────────────
# 상수
# ────────────────────────────────────────────────────────────────────────────
BASE_ID  = "app4LvuNIDiqTmhnv"
TABLE_ID = "tblnxU0PlegXT7bYj"
PAT      = (os.getenv("AIRTABLE_API_KEY")
            or os.getenv("AIRTABLE_WMS_PAT")
            or os.getenv("AIRTABLE_PAT", ""))
HEADERS  = {"Authorization": f"Bearer {PAT}"}

F_PT       = "파츠코드"
F_OUT      = "출고물품"
F_QTY_CONF = "이동수량(확정)"
F_QTY_MOV  = "이동수량"
F_QTY_PLAN = "계획수량"
F_BOX      = "라벨 박스수량"
F_PROJECT  = "project"
F_DATE     = "임가공 예정일"
F_LOCATION = "재고좌표(합산)"
F_STATUS   = "이동리스트현황(확정수량으로)"
F_MAT_TYPE = "출고자재_자재구분"

FONT_REG = r"C:\Windows\Fonts\malgun.ttf"
FONT_BLD = r"C:\Windows\Fonts\malgunbd.ttf"
OUT_DIR  = Path(r"C:\Users\yjisu\Desktop\SCM_WORK")

A4_W, A4_H = A4
MARGIN  = 20 * mm
INNER_W = A4_W - 2 * MARGIN

# 색상
COLOR_HEADER  = colors.HexColor("#1a3a5c")
COLOR_PROJ    = colors.HexColor("#2c5282")
COLOR_STOCK   = colors.HexColor("#e8f5e9")   # 재고자재 서브섹션
COLOR_PROD    = colors.HexColor("#fff3e0")   # 생산품자재 서브섹션
COLOR_OTHER   = colors.HexColor("#f3e8ff")   # 기타
COLOR_ALT     = colors.HexColor("#f7f9fc")
COLOR_INFO    = colors.HexColor("#f0f4f8")

# 자재구분 그룹 정의
MAT_STOCK = {"재고자재"}
MAT_PROD  = {"생산품자재", "생산자재", "기타자재"}

GROUP_LABELS = {0: "▪ 재고자재", 1: "▪ 생산품자재", 2: "▪ 기타"}
GROUP_BG     = {0: COLOR_STOCK, 1: COLOR_PROD, 2: COLOR_OTHER}

# 컬럼 너비 (INNER_W ≈ 170mm)
no_w   =  8 * mm
pt_w   = 22 * mm
name_w = 52 * mm
loc_w  = 30 * mm
qty_w  = 22 * mm
box_w  = 18 * mm
chk_w  = 18 * mm
COL_W  = [no_w, pt_w, name_w, loc_w, qty_w, box_w, chk_w]
HDR_ROW = ["No", "PT코드", "품목명", "재고좌표", "수량", "박스", "확인"]


# ────────────────────────────────────────────────────────────────────────────
# 유틸
# ────────────────────────────────────────────────────────────────────────────
def register_fonts():
    try:
        pdfmetrics.registerFont(TTFont("Malgun",     FONT_REG))
        pdfmetrics.registerFont(TTFont("MalgunBold", FONT_BLD))
        return "Malgun", "MalgunBold"
    except Exception:
        return "Helvetica", "Helvetica-Bold"


def clean(s) -> str:
    """Airtable 배열 수식 필드 세미콜론·공백 제거"""
    return str(s or "").strip().rstrip(";").strip()


def parse_qty(v) -> int:
    try:
        return int(float(clean(str(v)).replace(",", ""))) if v else 0
    except Exception:
        return 0


def parse_date_str(s) -> date | None:
    s = clean(s)
    if not s:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def urgency(d: date | None) -> str:
    if d is None:
        return "normal"
    diff = (d - date.today()).days
    return "urgent" if diff <= 1 else "warning" if diff <= 3 else "normal"


def mat_group(mat_type: str) -> int:
    if mat_type in MAT_STOCK:
        return 0
    if mat_type in MAT_PROD:
        return 1
    return 2


# ────────────────────────────────────────────────────────────────────────────
# 데이터 조회
# ────────────────────────────────────────────────────────────────────────────
def airtable_get(params: dict) -> list:
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TABLE_ID}"
    records, offset = [], None
    while True:
        p = dict(params)
        if offset:
            p["offset"] = offset
        r = requests.get(url, headers=HEADERS, params=p, timeout=30)
        r.raise_for_status()
        data = r.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records


def fetch_picking(start_date=None, end_date=None, project_filter=None) -> list:
    raw = airtable_get({"pageSize": 100})
    result = []
    for r in raw:
        f   = r.get("fields", {})
        d   = parse_date_str(f.get(F_DATE, ""))
        sts = clean(f.get(F_STATUS) or "")
        if sts in ("피킹완료", "자재투입완료", "완료"):
            continue
        if start_date and end_date and d:
            if not (start_date <= d <= end_date):
                continue
        pt   = clean(f.get(F_PT) or "")
        name = clean(f.get(F_OUT) or "")
        proj = clean(f.get(F_PROJECT) or "")
        if project_filter and project_filter not in proj:
            continue
        qty   = parse_qty(f.get(F_QTY_CONF) or f.get(F_QTY_MOV) or f.get(F_QTY_PLAN))
        boxes = parse_qty(f.get(F_BOX)) or 0
        result.append({
            "rec_id":   r["id"],
            "pt":       pt,
            "name":     name,
            "project":  proj,
            "date":     d,
            "qty":      qty,
            "boxes":    boxes,
            "location": clean(f.get(F_LOCATION) or ""),
            "mat_type": clean(f.get(F_MAT_TYPE) or ""),
        })
    return result


# ────────────────────────────────────────────────────────────────────────────
# 그룹핑
# ────────────────────────────────────────────────────────────────────────────
def group_records(records: list) -> list:
    by_proj: dict[str, list] = defaultdict(list)
    for r in records:
        by_proj[r["project"] or "(프로젝트 없음)"].append(r)

    projects = []
    for proj, recs in by_proj.items():
        min_date = min((r["date"] for r in recs if r["date"]), default=None)

        recs_sorted = sorted(recs, key=lambda r: (mat_group(r["mat_type"]), r["pt"]))
        subgroups, cur_items, cur_key = [], [], None
        for r in recs_sorted:
            g = mat_group(r["mat_type"])
            if g != cur_key:
                if cur_items:
                    subgroups.append({"group_key": cur_key, "items": cur_items})
                cur_items, cur_key = [r], g
            else:
                cur_items.append(r)
        if cur_items:
            subgroups.append({"group_key": cur_key, "items": cur_items})

        projects.append({
            "project":     proj,
            "min_date":    min_date,
            "urgency":     urgency(min_date),
            "subgroups":   subgroups,
            "total_qty":   sum(r["qty"]   for r in recs),
            "total_box":   sum(r["boxes"] for r in recs),
            "total_items": len(recs),
        })

    projects.sort(key=lambda p: p["min_date"] or date.max)
    return projects


# ────────────────────────────────────────────────────────────────────────────
# PDF 드로잉
# ────────────────────────────────────────────────────────────────────────────
def draw_page_banner(c, font, font_bold, date_label: str,
                     page_cur: int, page_tot: int) -> float:
    y = A4_H - MARGIN
    h = 14 * mm
    c.setFillColor(COLOR_HEADER)
    c.rect(MARGIN, y - h, INNER_W, h, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont(font_bold, 13)
    c.drawCentredString(A4_W / 2, y - h + 5*mm, "다영기획 이동 피킹리스트")
    c.setFont(font, 7.5)
    c.drawString(MARGIN + 2*mm, y - h + 2.5*mm, f"조회범위: {date_label}")
    c.drawRightString(MARGIN + INNER_W - 2*mm, y - h + 2.5*mm,
                      f"{date.today().strftime('%Y-%m-%d')}   Page {page_cur}/{page_tot}")
    return y - h - 4*mm


def draw_proj_block(c, font, font_bold, proj: dict, y: float) -> float:
    urg = proj["urgency"]
    bg  = colors.HexColor("#fef2f2") if urg == "urgent" else \
          colors.HexColor("#fffbeb") if urg == "warning" else COLOR_INFO
    bar = colors.HexColor("#E53E3E") if urg == "urgent" else \
          colors.HexColor("#E67E22") if urg == "warning" else colors.HexColor("#3B82F6")
    h = 14 * mm
    c.setFillColor(bg)
    c.roundRect(MARGIN, y - h, INNER_W, h, 3, fill=1, stroke=0)
    c.setStrokeColor(bar)
    c.setLineWidth(2.5)
    c.line(MARGIN, y, MARGIN, y - h)
    c.setLineWidth(0.4)
    c.setFillColor(COLOR_PROJ)
    c.setFont(font_bold, 11)
    c.drawString(MARGIN + 5*mm, y - 6*mm, proj["project"])
    c.setFont(font, 8)
    c.setFillColor(colors.HexColor("#444"))
    date_str = proj["min_date"].strftime("%Y-%m-%d") if proj["min_date"] else "날짜 없음"
    c.drawString(MARGIN + 5*mm, y - 11*mm,
                 f"임가공 예정일: {date_str}   |   {proj['total_items']}품목 / "
                 f"총 {proj['total_qty']:,}개 / {proj['total_box']}박스")
    return y - h - 3*mm


def draw_subgroup(c, font, font_bold, group_key: int, items: list,
                  y: float, page_state: list) -> float:
    """page_state = [cur_page, total_pages, date_label]"""

    def maybe_new_page(needed: float) -> float:
        nonlocal y
        if y - needed < MARGIN + 10*mm:
            c.showPage()
            page_state[0] += 1
            c.setPageSize(A4)
            return draw_page_banner(c, font, font_bold,
                                    page_state[2], page_state[0], page_state[1])
        return y

    # ── 서브그룹 헤더 줄 ──────────────────────────────────────────────────
    sg_h = 6.5 * mm
    y = maybe_new_page(sg_h + 10*mm)

    c.setFillColor(GROUP_BG.get(group_key, COLOR_OTHER))
    c.rect(MARGIN, y - sg_h, INNER_W, sg_h, fill=1, stroke=0)
    c.setFillColor(COLOR_PROJ)
    c.setFont(font_bold, 8)
    c.drawString(MARGIN + 3*mm, y - 4.5*mm, GROUP_LABELS.get(group_key, "▪ 기타"))

    # 재고자재: 공통 좌표 우측 표시
    if group_key == 0:
        locs = list(dict.fromkeys(r["location"] for r in items if r["location"]))
        if locs:
            c.setFont(font, 7.5)
            c.setFillColor(colors.HexColor("#2c7a7b"))
            c.drawRightString(MARGIN + INNER_W - 2*mm, y - 4.5*mm,
                              "좌표: " + "  /  ".join(locs[:4]))
    y -= sg_h + 1*mm

    # ── 테이블 ─────────────────────────────────────────────────────────────
    rows = [HDR_ROW]
    for idx, r in enumerate(items, 1):
        rows.append([
            str(idx),
            r["pt"] or "-",
            r["name"][:22] if r["name"] else "-",
            r["location"] or "-",
            f"{r['qty']:,}" if r["qty"] else "-",
            str(r["boxes"]) if r["boxes"] else "-",
            "",
        ])

    tbl = Table(rows, colWidths=COL_W)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  COLOR_HEADER),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",      (0, 0), (-1, 0),  font_bold),
        ("FONTSIZE",      (0, 0), (-1, 0),  7.5),
        ("ALIGN",         (0, 0), (-1, 0),  "CENTER"),
        ("FONTNAME",      (0, 1), (-1, -1), font),
        ("FONTSIZE",      (0, 1), (-1, -1), 7.5),
        ("ALIGN",         (0, 1), (0, -1),  "CENTER"),
        ("ALIGN",         (4, 1), (5, -1),  "RIGHT"),
        ("ALIGN",         (6, 0), (6, -1),  "CENTER"),
        ("GRID",          (0, 0), (-1, -1),  0.3, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1),  [colors.white, COLOR_ALT]),
        ("TOPPADDING",    (0, 0), (-1, -1),  2),
        ("BOTTOMPADDING", (0, 0), (-1, -1),  2),
        ("LEFTPADDING",   (0, 0), (-1, -1),  3),
        ("RIGHTPADDING",  (0, 0), (-1, -1),  3),
        ("VALIGN",        (0, 0), (-1, -1),  "MIDDLE"),
        ("BOX",           (6, 1), (6, -1),   0.5, colors.HexColor("#aaaaaa")),
    ]))

    _, h_tbl = tbl.wrapOn(c, INNER_W, A4_H)
    y = maybe_new_page(h_tbl)
    tbl.drawOn(c, MARGIN, y - h_tbl)
    y -= h_tbl + 3*mm
    return y


# ────────────────────────────────────────────────────────────────────────────
# 메인
# ────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="다영기획 이동 피킹리스트 PDF 생성")
    parser.add_argument("--date",    help="임가공 예정일 (YYYY-MM-DD)")
    parser.add_argument("--project", help="프로젝트 코드 필터 (예: PNA38579)")
    parser.add_argument("--days",    type=int, help="N일 이내")
    parser.add_argument("--dry-run", action="store_true", help="미리보기만")
    args = parser.parse_args()

    if not PAT:
        print("❌ AIRTABLE_WMS_PAT 환경변수 없음"); sys.exit(1)

    font, font_bold = register_fonts()
    today = date.today()

    if args.date:
        target = date.fromisoformat(args.date)
        sd, ed = target, target
        dlabel = args.date
    elif args.days:
        sd, ed = today, today + timedelta(days=args.days)
        dlabel = f"{today.strftime('%m/%d')} ~ {ed.strftime('%m/%d')} ({args.days}일)"
    else:
        sd = ed = None
        dlabel = "전체"

    print(f"▶ 이동리스트 조회 중… ({dlabel})")
    records = fetch_picking(sd, ed, args.project)
    print(f"  {len(records)}건 조회")

    if not records:
        print("  피킹 대상 없음"); return

    projects = group_records(records)
    total_qty = sum(p["total_qty"] for p in projects)
    print(f"  → {len(projects)}개 프로젝트 / 총 {total_qty:,}개\n")

    for p in projects:
        ug = "🔴" if p["urgency"] == "urgent" else \
             "🟡" if p["urgency"] == "warning" else "🔵"
        dt = p["min_date"].strftime("%m/%d") if p["min_date"] else "날짜없음"
        print(f"  {ug} {p['project'][:32]:<32} | {p['total_items']}품목 | "
              f"{p['total_qty']:,}개 | {p['total_box']}박스 | {dt}")
        for sg in p["subgroups"]:
            print(f"       {GROUP_LABELS.get(sg['group_key'], '기타')}: {len(sg['items'])}건")

    if args.dry_run:
        return

    suffix   = f"_{args.project}" if args.project else (f"_{args.date}" if args.date else "")
    out_path = OUT_DIR / f"다영기획_피킹리스트{suffix}_{today.strftime('%Y-%m-%d')}.pdf"

    c          = rl_canvas.Canvas(str(out_path), pagesize=A4)
    page_state = [1, max(len(projects), 1), dlabel]

    y = draw_page_banner(c, font, font_bold, dlabel, page_state[0], page_state[1])

    for proj in projects:
        if y < MARGIN + 45*mm:
            c.showPage()
            page_state[0] += 1
            c.setPageSize(A4)
            y = draw_page_banner(c, font, font_bold, dlabel, page_state[0], page_state[1])

        y = draw_proj_block(c, font, font_bold, proj, y)

        for sg in proj["subgroups"]:
            y = draw_subgroup(c, font, font_bold,
                              sg["group_key"], sg["items"],
                              y, page_state)

        y -= 5*mm

    c.save()
    print(f"\n✅ 완료 — {len(projects)}개 프로젝트 ({out_path})")


if __name__ == "__main__":
    main()
