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

import argparse, base64, io, os, platform, re, sys, time
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
TABLE_ID = "tblnxU0PlegXT7bYj"   # 이동리스트
TBL_DC   = "tblMQG1PYioIUWdbe"   # 출고확인서
PAT      = (os.getenv("AIRTABLE_API_KEY")
            or os.getenv("AIRTABLE_WMS_PAT")
            or os.getenv("AIRTABLE_PAT", ""))
HEADERS  = {"Authorization": f"Bearer {PAT}"}

ATTACH_FIELD_ID = "fldWczicq4KAoI5OX"   # 피킹리스트_python on TBL_DC

if platform.system() == "Windows":
    FONT_REG = r"C:\Windows\Fonts\malgun.ttf"
    FONT_BLD = r"C:\Windows\Fonts\malgunbd.ttf"
else:
    FONT_REG = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
    FONT_BLD = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"

OUT_DIR = Path(os.getenv("PDF_OUTPUT_DIR", r"C:\Users\yjisu\Desktop"))

F_PT       = "파츠코드"
F_OUT      = "출고물품"
F_QTY_CONF = "이동수량(확정)"
F_QTY_MOV  = "이동수량"
F_QTY_PLAN = "계획수량"
F_BOX      = "라벨 박스수량"
F_PROJECT  = "project"
F_DATE     = "임가공 예정일"
F_LOCATION = "입고좌표"
F_STATUS   = "이동리스트현황(확정수량으로)"
F_MAT_TYPE = "출고자재_자재구분"

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

# 컬럼 너비 (INNER_W ≈ 170mm) — 재고좌표 컬럼 제거, 헤더에 통합
no_w   =  8 * mm
pt_w   = 24 * mm
name_w = 82 * mm
qty_w  = 22 * mm
box_w  = 18 * mm
chk_w  = 16 * mm
COL_W  = [no_w, pt_w, name_w, qty_w, box_w, chk_w]
HDR_ROW = ["No", "PT코드", "품목명", "수량", "박스", "확인"]


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


def fetch_dc_record(record_id: str) -> dict | None:
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_DC}"
    r = requests.get(url, headers=HEADERS,
                     params={"filterByFormula": f'RECORD_ID()="{record_id}"', "pageSize": 1},
                     timeout=30)
    r.raise_for_status()
    recs = r.json().get("records", [])
    return recs[0] if recs else None


def upload_via_content_api(record_id: str, field_id: str,
                           filename: str, pdf_bytes: bytes) -> bool:
    url = (f"https://content.airtable.com/v0/{BASE_ID}"
           f"/{record_id}/{field_id}/uploadAttachment")
    payload = {
        "contentType": "application/pdf",
        "filename":    filename,
        "file":        base64.b64encode(pdf_bytes).decode("ascii"),
    }
    try:
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"},
            json=payload, timeout=60,
        )
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", 10)))
            r = requests.post(url, headers={"Authorization": f"Bearer {PAT}",
                                             "Content-Type": "application/json"},
                              json=payload, timeout=60)
        r.raise_for_status()
        print(f"  ✅ 업로드: {filename}")
        return True
    except requests.HTTPError as e:
        print(f"  ❌ 업로드 실패 {e.response.status_code}: {e.response.text[:200]}")
        return False
    except Exception as e:
        print(f"  ❌ 업로드 실패: {e}")
        return False


def fetch_picking(start_date=None, end_date=None, project_filter=None, batch_filter=None) -> list:
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
        if not name:
            raw = clean(f.get("이동물품") or "")
            if raw:
                part = raw.split(" || ")[0].strip()
                part = re.sub(r"_[0-9]{3,}-[0-9]+$", "", part)
                part = re.sub(r"^PT\w+-", "", part)
                name = part.strip()
        proj = clean(f.get(F_PROJECT) or "")
        if project_filter and project_filter not in proj:
            continue
        if batch_filter:
            il_batch = clean(f.get("출고차수") or "")
            if il_batch and il_batch != batch_filter:
                continue
        qty   = parse_qty(f.get(F_QTY_CONF) or f.get(F_QTY_MOV) or f.get("출고수량") or f.get(F_QTY_PLAN))
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
            "locations":   list(dict.fromkeys(r["location"] for r in recs if r["location"])),
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
    urg  = proj["urgency"]
    locs = proj.get("locations", [])
    bg   = colors.HexColor("#fef2f2") if urg == "urgent" else \
           colors.HexColor("#fffbeb") if urg == "warning" else COLOR_INFO
    bar  = colors.HexColor("#E53E3E") if urg == "urgent" else \
           colors.HexColor("#E67E22") if urg == "warning" else colors.HexColor("#3B82F6")
    h = 20 * mm if locs else 14 * mm
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
    c.drawString(MARGIN + 5*mm, y - 12*mm,
                 f"임가공 예정일: {date_str}   |   {proj['total_items']}품목 / "
                 f"총 {proj['total_qty']:,}개 / {proj['total_box']}박스")
    if locs:
        loc_str = "  /  ".join(locs[:5]) + (" ..." if len(locs) > 5 else "")
        c.setFont(font, 8)
        c.setFillColor(colors.HexColor("#2c7a7b"))
        c.drawString(MARGIN + 5*mm, y - 17*mm, f"입고좌표: {loc_str}")
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

    # 모든 그룹: 입고좌표를 서브섹션 헤더 우측에 표시
    locs = list(dict.fromkeys(r["location"] for r in items if r["location"]))
    if locs:
        c.setFont(font, 7.5)
        c.setFillColor(colors.HexColor("#2c7a7b"))
        loc_str = "  /  ".join(locs[:4]) + (" ..." if len(locs) > 4 else "")
        c.drawRightString(MARGIN + INNER_W - 2*mm, y - 4.5*mm,
                          "입고좌표: " + loc_str)
    y -= sg_h + 1*mm

    # ── 테이블 ─────────────────────────────────────────────────────────────
    rows = [HDR_ROW]
    for idx, r in enumerate(items, 1):
        rows.append([
            str(idx),
            r["pt"] or "-",
            r["name"][:30] if r["name"] else "-",
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
    parser.add_argument("--date",      help="임가공 예정일 (YYYY-MM-DD)")
    parser.add_argument("--project",   help="프로젝트 코드 필터 (예: PNA38579)")
    parser.add_argument("--days",      type=int, help="N일 이내")
    parser.add_argument("--record-id", help="출고확인서 레코드 ID (Make/GitHub Actions 버튼 트리거)")
    parser.add_argument("--no-upload", action="store_true", help="로컬 저장만, Airtable 업로드 안 함")
    parser.add_argument("--dry-run",   action="store_true", help="미리보기만")
    args = parser.parse_args()
    record_id = getattr(args, "record_id", None)

    if not PAT:
        print("❌ AIRTABLE_WMS_PAT 환경변수 없음"); sys.exit(1)

    font, font_bold = register_fonts()
    today = date.today()

    # --record-id 모드: DC 레코드에서 프로젝트 코드 추출
    batch = ""
    if record_id:
        print(f"▶ 출고확인서 레코드 조회 중… ({record_id})")
        dc_rec = fetch_dc_record(record_id)
        if not dc_rec:
            print("  레코드 없음"); return
        proj_code = dc_rec["fields"].get("프로젝트명", "")
        batch     = dc_rec["fields"].get("차수", "")
        args.project = proj_code
        dlabel = proj_code or record_id
        sd = ed = None
    elif args.date:
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
    records = fetch_picking(sd, ed, args.project, batch_filter=batch)
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

    today_stamp = datetime.now().strftime("%Y%m%d-%H%M")
    suffix      = f"_{args.project}" if args.project else (f"_{args.date}" if args.date else "")
    filename    = f"다영기획_피킹리스트{suffix}_{today_stamp}.pdf"
    out_path    = OUT_DIR / filename

    buf        = io.BytesIO()
    c          = rl_canvas.Canvas(buf, pagesize=A4)
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
    pdf_bytes = buf.getvalue()

    if not record_id or args.no_upload:
        out_path.write_bytes(pdf_bytes)
        print(f"\n✅ 완료 — {len(projects)}개 프로젝트 ({out_path})")
    else:
        print(f"\n▶ {filename} 업로드 중…")
        if upload_via_content_api(record_id, ATTACH_FIELD_ID, filename, pdf_bytes):
            print(f"✅ 완료 — {len(projects)}개 프로젝트 업로드")


if __name__ == "__main__":
    main()
