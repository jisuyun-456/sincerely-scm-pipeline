"""
출고확인서_pdf.py
────────────────────────────────────────────────────────────────────────────
Barcode 베이스 → 출고확인서 PDF 생성기

출고확인서 테이블(tblMQG1PYioIUWdbe) 1건 = A4 확인서 1장
섹션 1: 품목별 합계 + 어떤 라벨에 들어가는지
섹션 2: 박스별 구성 (합포장/분산포장 한눈에 파악)

사용법:
  python scripts/출고확인서_pdf.py                         # 전체
  python scripts/출고확인서_pdf.py --project PNA38579      # 프로젝트 필터
  python scripts/출고확인서_pdf.py --date 2026-04-22       # 날짜 필터
  python scripts/출고확인서_pdf.py --dry-run               # 미리보기만
"""

import argparse, base64, io, os, platform, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from datetime import date, datetime
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

BASE_ID  = "app4LvuNIDiqTmhnv"
TBL_DC   = "tblMQG1PYioIUWdbe"   # 출고확인서
TBL_IL   = "tblnxU0PlegXT7bYj"   # 이동리스트
TBL_BC   = "tbl0K3QP5PCd06Cxv"   # 바코드 (외박스)

API_KEY  = os.getenv("AIRTABLE_API_KEY", "")
HEADERS  = {"Authorization": f"Bearer {API_KEY}"}
_SESSION = requests.Session()
_SESSION.headers.update(HEADERS)

ATTACH_FIELD_ID = "fldXde5mrRIaqZHiG"   # 출고확인서_python on TBL_DC

if platform.system() == "Windows":
    FONT_REG = r"C:\Windows\Fonts\malgun.ttf"
    FONT_BLD = r"C:\Windows\Fonts\malgunbd.ttf"
else:
    FONT_REG = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
    FONT_BLD = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"

OUT_DIR = Path(os.getenv("PDF_OUTPUT_DIR", r"C:\Users\yjisu\Desktop"))

A4_W, A4_H = A4
MARGIN  = 20 * mm
INNER_W = A4_W - 2 * MARGIN

# 박스 섹션에서 합포장(PT 2개 이상) 행 배경색
COLOR_MIXED = colors.HexColor("#fff3cd")   # 노란빛
COLOR_HEADER = colors.HexColor("#1a3a5c")
COLOR_INFO   = colors.HexColor("#f0f4f8")
COLOR_TOTAL  = colors.HexColor("#e8f0fe")
COLOR_ALT    = colors.HexColor("#f7f9fc")


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
        r = _SESSION.post(url, headers={"Content-Type": "application/json"},
                          json=payload, timeout=60)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", 10)))
            r = _SESSION.post(url, headers={"Content-Type": "application/json"},
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


def airtable_get(table_id: str, params: dict) -> list:
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}"
    records, offset = [], None
    while True:
        p = dict(params)
        if offset:
            p["offset"] = offset
        r = _SESSION.get(url, params=p, timeout=30)
        r.raise_for_status()
        data = r.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records


def fetch_by_ids(table_id: str, record_ids: list[str], batch_size: int = 30) -> list[dict]:
    """RECORD_ID() 기반 배치 조회"""
    if not record_ids:
        return []
    result = []
    for i in range(0, len(record_ids), batch_size):
        batch = record_ids[i:i + batch_size]
        formula = "OR(" + ",".join(f'RECORD_ID()="{rid}"' for rid in batch) + ")"
        recs = airtable_get(table_id, {"filterByFormula": formula, "pageSize": 100})
        result.extend(recs)
        if i + batch_size < len(record_ids):
            time.sleep(0.2)
    return result


def parse_date_rollup(val) -> str:
    if isinstance(val, list):
        val = next((v for v in val if v), None)
    if not val:
        return ""
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(val).strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return str(val)[:10]


def parse_total_boxes(f: dict) -> str:
    copy = (f.get("박스 수량 copy") or "").strip()
    if copy:
        return copy
    return (f.get("박스 수량") or "?").strip()


def lable_short(full: str) -> str:
    """'Lable-03086' → '03086'"""
    return full.replace("Lable-", "").strip()


def get_item_name(item: dict) -> str:
    """출고물품 필드 우선, 없으면 이동물품에서 PT코드 접두어 제거 후 추출"""
    name = (item.get("출고물품") or "").strip()
    if name:
        return name
    raw = (item.get("이동물품") or "").strip()
    if raw:
        part = raw.split(" || ")[0].strip()
        part = re.sub(r"_[0-9]{3,}-[0-9]+$", "", part)   # 배치번호 제거
        part = re.sub(r"^PT\w+-", "", part)               # PT코드 접두어 제거
        return part.strip()
    return ""


def char_w(s: str) -> int:
    """줄 길이 추정: 한글=2, ASCII=1"""
    return sum(2 if ord(c) > 127 else 1 for c in s)


def split_to_lines(pt_labels: list[str], max_w: int = 80) -> list[str]:
    """PT 목록을 너비 기반으로 여러 줄로 나눔"""
    SEP = "  ·  "
    sep_w = char_w(SEP)
    lines, cur, cur_w = [], [], 0
    for pt in pt_labels:
        w = char_w(pt)
        add = (sep_w + w) if cur else w
        if cur_w + add > max_w and cur:
            lines.append(SEP.join(cur))
            cur, cur_w = [pt], w
        else:
            cur.append(pt)
            cur_w += add
    if cur:
        lines.append(SEP.join(cur))
    return lines or [""]


def format_labels_for_cell(lable_list: list[str]) -> str:
    """라벨 목록 → 셀 표시용 문자열 (5개 초과 시 축약)"""
    shorts = sorted(lable_short(l) for l in lable_list)
    if len(shorts) <= 5:
        return ", ".join(shorts)
    return ", ".join(shorts[:4]) + f" (+{len(shorts)-4})"


# ────────────────────────────────────────────────────────────────────────────
# PDF 드로잉 헬퍼
# ────────────────────────────────────────────────────────────────────────────
def new_page_if_needed(c: rl_canvas.Canvas, y: float, needed: float,
                       font: str, font_bold: str,
                       project: str, page_info: list) -> tuple[float, int]:
    """y가 부족하면 새 페이지 시작, (새 y, 새 page_num) 반환"""
    if y < needed:
        c.showPage()
        page_info[0] += 1
        c.setPageSize(A4)
        # 연속 페이지 미니 헤더
        c.setFillColor(COLOR_HEADER)
        c.rect(MARGIN, A4_H - MARGIN - 8*mm, INNER_W, 8*mm, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont(font_bold, 9)
        c.drawString(MARGIN + 3*mm, A4_H - MARGIN - 5*mm, f"자재 출고확인서 (계속)  |  {project}")
        c.setFont(font, 8)
        c.drawRightString(MARGIN + INNER_W - 2*mm, A4_H - MARGIN - 5*mm,
                          f"Page {page_info[0]}/{page_info[1]}")
        return A4_H - MARGIN - 8*mm - 4*mm, page_info[0]
    return y, page_info[0]


def draw_section_title(c: rl_canvas.Canvas, y: float, title: str, font_bold: str) -> float:
    c.setFillColor(colors.HexColor("#2c5282"))
    c.setFont(font_bold, 8.5)
    c.drawString(MARGIN, y, title)
    c.setStrokeColor(colors.HexColor("#2c5282"))
    c.setLineWidth(0.5)
    c.line(MARGIN, y - 1*mm, MARGIN + INNER_W, y - 1*mm)
    return y - 5*mm


# ────────────────────────────────────────────────────────────────────────────
# PDF 한 문서 그리기
# ────────────────────────────────────────────────────────────────────────────
def draw_confirmation(c: rl_canvas.Canvas, doc: dict, page_num: int, total_pages: int,
                      font: str, font_bold: str) -> int:
    """출고확인서 1건 그리기. 페이지 넘김 발생 시 실제 사용된 마지막 page_num 반환."""
    f          = doc["fields"]
    project    = f.get("프로젝트명", "")
    move_date  = parse_date_rollup(f.get("임가공 예정일"))
    total_box  = parse_total_boxes(f)
    sample_box = f.get("샘플박스수량") or ""
    items      = doc["items"]           # 이동리스트 fields, 파츠코드 정렬됨
    box_rows   = doc["box_rows"]        # [(lable_str, [pt_label, ...], is_mixed), ...]
    today_str  = date.today().strftime("%Y-%m-%d")

    page_info = [page_num, total_pages]  # mutable ref for new_page_if_needed

    c.setPageSize(A4)
    y = A4_H - MARGIN

    # ── 헤더 배너 ─────────────────────────────────────────────────────────
    banner_h = 14 * mm
    c.setFillColor(COLOR_HEADER)
    c.rect(MARGIN, y - banner_h, INNER_W, banner_h, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont(font_bold, 14)
    c.drawCentredString(A4_W / 2, y - banner_h + 4*mm, "자재 출고확인서")
    c.setFont(font, 8)
    c.drawRightString(MARGIN + INNER_W - 2*mm, y - banner_h + 3*mm,
                      f"Page {page_num}/{total_pages}")
    y -= banner_h + 4*mm

    # ── 프로젝트 정보 블록 ────────────────────────────────────────────────
    info_h = 24 * mm
    c.setFillColor(COLOR_INFO)
    c.roundRect(MARGIN, y - info_h, INNER_W, info_h, 3, fill=1, stroke=0)

    lx = MARGIN + 5*mm
    c.setFillColor(COLOR_HEADER)
    c.setFont(font_bold, 11)
    c.drawString(lx, y - 8*mm, project)

    c.setFont(font, 9)
    c.setFillColor(colors.HexColor("#444444"))
    c.drawString(lx, y - 14*mm, f"임가공 예정일: {move_date or '미정'}")
    c.drawString(lx, y - 19*mm, f"출력일: {today_str}")

    # ── 총 박스 수량 강조 블록 ────────────────────────────────────────────
    rx = MARGIN + INNER_W / 2
    BOX_ACCENT = colors.HexColor("#d97706")   # 앰버
    box_label_str = "총 박스 수량"
    box_val_str   = str(total_box)
    # 배경 강조 박스
    accent_x  = rx - 2*mm
    accent_y  = y - 4*mm
    accent_h  = 13*mm
    accent_w  = INNER_W / 2 - 3*mm
    c.setFillColor(colors.HexColor("#fff8ec"))
    c.roundRect(accent_x, accent_y - accent_h, accent_w, accent_h, 2, fill=1, stroke=0)
    c.setStrokeColor(BOX_ACCENT); c.setLineWidth(1.0)
    c.roundRect(accent_x, accent_y - accent_h, accent_w, accent_h, 2, fill=0, stroke=1)
    # 라벨
    c.setFillColor(colors.HexColor("#92400e"))
    c.setFont(font_bold, 7.5)
    c.drawString(accent_x + 3*mm, accent_y - 4.5*mm, box_label_str)
    # 값 (크고 굵게)
    c.setFillColor(BOX_ACCENT)
    c.setFont(font_bold, 15)
    c.drawString(accent_x + 3*mm, accent_y - 11.5*mm, box_val_str)
    if sample_box:
        c.setFillColor(colors.HexColor("#444444"))
        c.setFont(font, 8)
        c.drawRightString(accent_x + accent_w - 2*mm, accent_y - 11.5*mm, f"샘플 {sample_box}박스")
    y -= info_h + 4*mm

    # ══════════════════════════════════════════════════════════════════════
    # 섹션 1 — 품목별 합계 + 라벨 번호
    # ══════════════════════════════════════════════════════════════════════
    y = draw_section_title(c, y, "▌ 품목별 출고 내역", font_bold)

    header = ["No", "PT코드", "품목명", "수량", "박스", "라벨 번호"]
    lbl_w  = 38 * mm
    box_w  = 16 * mm
    qty_w  = 18 * mm
    pt_w   = 20 * mm
    no_w   = 8  * mm
    name_w = INNER_W - no_w - pt_w - qty_w - box_w - lbl_w
    col_w  = [no_w, pt_w, name_w, qty_w, box_w, lbl_w]

    rows = [header]
    # 합포장 라벨 집합 (is_mixed=True인 라벨 → 박스 컬럼에 "(합)" 태그)
    mixed_labels = {lable for lable, _, is_mixed, _ in box_rows if is_mixed}
    # 총 박스 수: 고유 라벨 단위 합산 (합포장 중복 방지)
    if box_rows:
        total_box_cnt = sum(bc for _, _, _, bc in box_rows)
    else:
        unique_labels = {lbl for g in doc["grouped_items"] for lbl in g["_labels"]}
        total_box_cnt = len(unique_labels) if unique_labels else sum(g["_boxes"] for g in doc["grouped_items"])
    total_qty = 0
    for idx, g in enumerate(doc["grouped_items"], 1):
        pt      = g.get("파츠코드", "")
        name    = g["_name"]
        qty     = g["_qty"]
        boxes   = g["_boxes"]
        lbl_str = format_labels_for_cell(g["_labels"]) if g["_labels"] else "-"
        box_str = f"{int(boxes)}박스" if boxes else "-"
        if boxes and any(lbl in mixed_labels for lbl in g["_labels"]):
            box_str += " (합)"

        rows.append([str(idx), pt, name,
                     f"{int(qty):,}" if qty else "-",
                     box_str,
                     lbl_str])
        total_qty += qty

    rows.append(["", "", "합  계", f"{total_qty:,}", f"{total_box_cnt}박스", ""])

    row_h = 7 * mm
    # 서명 영역(38mm) + 섹션2 최소 높이(30mm) 보장
    avail = y - MARGIN - 68*mm
    max_data_rows = max(3, int(avail / row_h))
    if len(rows) - 2 > max_data_rows:   # -2: header + total
        shown = rows[:max_data_rows + 1]  # header + data rows
        omit  = len(items) - max_data_rows
        shown.append(["…", "", f"이하 {omit}건 생략", "", "", ""])
        shown.append(rows[-1])  # 합계
        rows = shown

    tbl = Table(rows, colWidths=col_w)
    ts  = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  COLOR_HEADER),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",      (0, 0), (-1, 0),  font_bold),
        ("FONTSIZE",      (0, 0), (-1, 0),  8.5),
        ("ALIGN",         (0, 0), (-1, 0),  "CENTER"),
        ("FONTNAME",      (0, 1), (-1, -1), font),
        ("FONTSIZE",      (0, 1), (-1, -1), 8),
        ("ALIGN",         (0, 1), (1, -1),  "CENTER"),
        ("ALIGN",         (3, 1), (4, -1),  "CENTER"),
        ("BACKGROUND",    (0, -1), (-1, -1), COLOR_TOTAL),
        ("FONTNAME",      (0, -1), (-1, -1), font_bold),
        ("ALIGN",         (2, -1), (2, -1),  "RIGHT"),
        ("GRID",          (0, 0), (-1, -1),  0.4, colors.HexColor("#aaaaaa")),
        ("ROWBACKGROUNDS",(0, 1), (-1, -2),  [colors.white, COLOR_ALT]),
        ("TOPPADDING",    (0, 0), (-1, -1),  2),
        ("BOTTOMPADDING", (0, 0), (-1, -1),  2),
        ("LEFTPADDING",   (0, 0), (-1, -1),  3),
        ("RIGHTPADDING",  (0, 0), (-1, -1),  3),
        ("VALIGN",        (0, 0), (-1, -1),  "MIDDLE"),
    ])
    tbl.setStyle(ts)
    _, h_tbl = tbl.wrapOn(c, INNER_W, avail)
    tbl.drawOn(c, MARGIN, y - h_tbl)
    y -= h_tbl + 6*mm

    # ══════════════════════════════════════════════════════════════════════
    # 섹션 2 — 박스별 구성
    # ══════════════════════════════════════════════════════════════════════
    if box_rows:
        # 섹션2가 들어갈 공간 없으면 새 페이지
        y, page_num = new_page_if_needed(
            c, y, MARGIN + 38*mm + 12*mm, font, font_bold, project, page_info)

        y = draw_section_title(c, y, "▌ 박스별 구성", font_bold)

        LINE_H     = 5 * mm
        LABLE_COL  = 28 * mm   # 라벨 번호 컬럼 너비
        ARROW_X    = MARGIN + LABLE_COL
        MAX_BOX_ROWS = 20

        display_rows = box_rows[:MAX_BOX_ROWS]
        omit_count   = len(box_rows) - MAX_BOX_ROWS if len(box_rows) > MAX_BOX_ROWS else 0

        for lable_str, pt_labels, is_mixed, box_cnt in display_rows:
            # 줄 수 계산 (너비 80단위 기준)
            lines   = split_to_lines(pt_labels, max_w=80)
            row_h   = max(LINE_H + 2*mm, len(lines) * LINE_H + 2*mm)

            # 공간 체크
            y, page_num = new_page_if_needed(
                c, y, MARGIN + 38*mm + row_h, font, font_bold, project, page_info)

            bg = COLOR_MIXED if is_mixed else colors.white
            c.setFillColor(bg)
            c.rect(MARGIN, y - row_h, INNER_W, row_h, fill=1, stroke=0)

            # 구분선 (하단)
            c.setStrokeColor(colors.HexColor("#cccccc"))
            c.setLineWidth(0.3)
            c.line(MARGIN, y - row_h, MARGIN + INNER_W, y - row_h)

            # 라벨 번호 (수직 중앙 정렬)
            label_text_y = y - row_h / 2 - 1.5*mm
            c.setFillColor(COLOR_HEADER)
            c.setFont(font_bold, 8)
            c.drawString(MARGIN + 2*mm, label_text_y, lable_str)

            # 화살표
            c.setFillColor(colors.HexColor("#555555"))
            c.setFont(font, 7.5)
            c.drawString(ARROW_X - 5*mm, label_text_y, "→")

            # PT 목록 (여러 줄)
            c.setFillColor(colors.HexColor("#333333"))
            pt_font = font_bold if is_mixed else font
            c.setFont(pt_font, 7.5)
            for li, line in enumerate(lines):
                line_y = y - LINE_H * (li + 1) - 0.5*mm
                c.drawString(ARROW_X, line_y, line)

            # 박스수 + 합포장 태그 (우상단)
            box_label = f"{box_cnt}박스"
            if is_mixed:
                c.setFillColor(colors.HexColor("#d97706"))
                c.setFont(font_bold, 7)
                c.drawRightString(MARGIN + INNER_W - 2*mm, y - 4*mm,
                                  f"합포장  {box_label}")
            else:
                c.setFillColor(COLOR_HEADER)
                c.setFont(font_bold, 7)
                c.drawRightString(MARGIN + INNER_W - 2*mm, y - 4*mm, box_label)

            y -= row_h

        if omit_count:
            c.setFont(font, 7.5)
            c.setFillColor(colors.HexColor("#888888"))
            c.drawString(MARGIN + 2*mm, y - 4*mm,
                         f"  … 이하 {omit_count}건 생략 (전체 {len(box_rows)}박스)")
            y -= LINE_H + 2*mm

        y -= 3*mm

    # ── 서명 영역 ─────────────────────────────────────────────────────────
    # 항상 페이지 하단 고정
    sign_y = MARGIN + 10*mm
    c.setStrokeColor(colors.HexColor("#aaaaaa"))
    c.setLineWidth(0.5)
    c.line(MARGIN, sign_y + 32*mm, MARGIN + INNER_W, sign_y + 32*mm)

    c.setFillColor(colors.HexColor("#333333"))
    c.setFont(font_bold, 9)
    c.drawString(MARGIN, sign_y + 28*mm, "수령 확인 (다영기획)")
    c.setFont(font, 8.5)
    c.drawString(MARGIN, sign_y + 21*mm, "수령인:")
    c.line(MARGIN + 18*mm, sign_y + 21*mm, MARGIN + 90*mm, sign_y + 21*mm)
    c.drawString(MARGIN, sign_y + 13*mm, "수령 일시:")
    c.line(MARGIN + 22*mm, sign_y + 13*mm, MARGIN + 90*mm, sign_y + 13*mm)
    c.drawString(MARGIN, sign_y + 5*mm, "서명:")
    c.line(MARGIN + 13*mm, sign_y + 5*mm, MARGIN + 90*mm, sign_y + 5*mm)

    c.setFont(font, 7.5)
    c.setFillColor(colors.HexColor("#888888"))
    c.drawRightString(MARGIN + INNER_W - 2*mm, sign_y + 26*mm, "발행: 신시어리 웨일즈 물류팀")
    c.drawRightString(MARGIN + INNER_W - 2*mm, sign_y + 20*mm, f"출력: {today_str}")

    return page_info[0]


# ────────────────────────────────────────────────────────────────────────────
# 메인
# ────────────────────────────────────────────────────────────────────────────
def build_box_rows(bc_records: list[dict], il_map: dict) -> tuple[dict, dict]:
    """
    bc_records: 바코드 테이블 레코드 목록
    il_map: IL record_id → fields

    반환:
      il_to_labels: IL record_id → [Lable-XXXXX, ...]
      label_to_box_row: Lable-XXXXX → (lable_str, [pt_label, ...], is_mixed)
    """
    il_to_labels:     dict[str, list[str]] = defaultdict(list)
    label_to_il_ids:  dict[str, list[str]] = {}
    label_box_counts: dict[str, int]       = {}

    for bc in bc_records:
        bf      = bc["fields"]
        lable   = bf.get("Barcode_Number", "")   # "Lable-03086"
        il_ids  = bf.get("이동리스트") or []
        if isinstance(il_ids, list):
            label_to_il_ids[lable]  = il_ids
            label_box_counts[lable] = int(bf.get("라벨 박스수량") or 0)
            for il_id in il_ids:
                il_to_labels[il_id].append(lable)

    # 박스별 PT 라벨 문자열 구성, 라벨 번호 오름차순
    box_rows = []
    for lable in sorted(label_to_il_ids.keys()):
        il_ids   = label_to_il_ids[lable]
        pt_parts = []
        for il_id in il_ids:
            ifields = il_map.get(il_id, {})
            pt   = ifields.get("파츠코드", "")
            name = get_item_name(ifields)
            if pt or name:
                pt_parts.append(f"{pt} {name}".strip())
        if not pt_parts:
            continue
        is_mixed = len(pt_parts) > 1
        # BC 테이블 라벨 박스수량 직접 사용 (primary source), 없으면 1
        box_cnt  = label_box_counts.get(lable, 0) or 1
        box_rows.append((lable, pt_parts, is_mixed, box_cnt))

    return dict(il_to_labels), box_rows


def main():
    parser = argparse.ArgumentParser(description="출고확인서 PDF 생성")
    parser.add_argument("--project",   help="프로젝트 코드 필터 (예: PNA38579)")
    parser.add_argument("--date",      help="임가공 예정일 필터 (YYYY-MM-DD)")
    parser.add_argument("--record-id", help="출고확인서 레코드 ID (Make/GitHub Actions 버튼 트리거)")
    parser.add_argument("--no-upload", action="store_true", help="로컬 저장만, Airtable 업로드 안 함")
    parser.add_argument("--dry-run",   action="store_true", help="PDF 미생성, 미리보기만")
    args = parser.parse_args()
    record_id = getattr(args, "record_id", None)

    if not API_KEY:
        print("❌ AIRTABLE_API_KEY 환경변수 없음")
        sys.exit(1)

    font, font_bold = register_fonts()

    # ── 출고확인서 조회 ───────────────────────────────────────────────────
    print("▶ 출고확인서 조회 중…")
    if record_id:
        params = {"filterByFormula": f'RECORD_ID()="{record_id}"', "pageSize": 1}
    else:
        formula_parts = []
        if args.project:
            formula_parts.append(f"FIND('{args.project}', {{프로젝트명}})")
        if args.date:
            try:
                dt = datetime.strptime(args.date, "%Y-%m-%d")
                date_en = dt.strftime("%B ") + str(dt.day) + dt.strftime(", %Y")
            except Exception:
                date_en = args.date
            formula_parts.append(
                f"OR(FIND('{args.date}', ARRAYJOIN({{임가공 예정일}})),"
                f"FIND('{date_en}', ARRAYJOIN({{임가공 예정일}})))"
            )
        params = {"pageSize": 100}
        if formula_parts:
            params["filterByFormula"] = "AND(" + ",".join(formula_parts) + ")"

    dc_records = airtable_get(TBL_DC, params)
    print(f"  {len(dc_records)}건 조회")
    if not dc_records:
        print("  조회 결과 없음")
        return

    # ── 이동리스트 + 바코드 레코드 사전 조회 ──────────────────────────────
    all_il_ids: list[str] = []
    all_bc_ids: list[str] = []
    for rec in dc_records:
        f = rec["fields"]
        il_ids = f.get("이동리스트") or []
        bc_ids = f.get("외박스 Barcode") or []
        if isinstance(il_ids, list): all_il_ids.extend(il_ids)
        if isinstance(bc_ids, list): all_bc_ids.extend(bc_ids)

    all_il_ids = list(set(all_il_ids))
    all_bc_ids = list(set(all_bc_ids))

    print(f"  이동리스트 {len(all_il_ids)}건 + 바코드 {len(all_bc_ids)}건 병렬 조회 중…")
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_il = ex.submit(fetch_by_ids, TBL_IL, all_il_ids)
        f_bc = ex.submit(fetch_by_ids, TBL_BC, all_bc_ids)
        il_records     = f_il.result()
        bc_records_all = f_bc.result()
    il_map = {r["id"]: {**r["fields"], "_record_id": r["id"]} for r in il_records}
    bc_map = {r["id"]: r for r in bc_records_all}  # id → full record

    # ── 문서 조립 ──────────────────────────────────────────────────────────
    docs = []
    for rec in dc_records:
        f      = rec["fields"]
        il_ids = f.get("이동리스트") or []
        bc_ids = f.get("외박스 Barcode") or []

        bc_recs_for_doc = [bc_map[bid] for bid in bc_ids if bid in bc_map]
        il_to_labels, box_rows = build_box_rows(bc_recs_for_doc, il_map)

        # BC 테이블 라벨별 박스수 룩업 (per-row 박스수·합계·박스별구성 소스 통일)
        label_to_box_cnt = {lable: cnt for lable, _, _, cnt in box_rows}

        items = [il_map[rid] for rid in il_ids if rid in il_map]
        # 라벨 번호 오름차순 → 같은 박스 PT 그룹핑, 동일 라벨 내에선 PT코드 순
        def item_sort_key(item):
            rid = item.get("_record_id", "")
            lbls = il_to_labels.get(rid, [])
            return (min(lbls) if lbls else "Lable-99999", item.get("파츠코드", ""))
        items.sort(key=item_sort_key)

        # ── 품목별 집계 (분산포장 대응: 1 PT → N 박스) ──────────────────────
        pt_agg: dict[str, dict] = {}
        for item in items:
            pt   = item.get("파츠코드") or ""
            name = get_item_name(item)
            key  = pt or name or item.get("_record_id", "")
            if key not in pt_agg:
                pt_agg[key] = {
                    "파츠코드": pt,
                    "_name":   name,
                    "_qty":    0,
                    "_boxes":  0,
                    "_labels": [],
                }
            g = pt_agg[key]
            g["_qty"] += int(item.get("출고수량") or 0)
            il_id = item.get("_record_id", "")
            for lbl in il_to_labels.get(il_id, []):
                if lbl not in g["_labels"]:
                    g["_labels"].append(lbl)

        # BC 기준 박스수로 통일 (IL 필드 대신 사용해 테이블·박스별구성·합계 일치)
        for g in pt_agg.values():
            g["_boxes"] = sum(label_to_box_cnt.get(lbl, 0) for lbl in g["_labels"])

        grouped_items = sorted(
            pt_agg.values(),
            key=lambda g: (min(g["_labels"]) if g["_labels"] else "Lable-99999",
                           g["파츠코드"])
        )

        docs.append({
            "id":             rec["id"],
            "fields":         f,
            "items":          items,
            "grouped_items":  grouped_items,
            "il_to_labels":   il_to_labels,
            "box_rows":       box_rows,
        })

    if args.dry_run:
        print("\n── 미리보기 ──────────────────────────────────────────")
        for d in docs:
            f         = d["fields"]
            n_mixed   = sum(1 for _, _, m, _ in d["box_rows"] if m)
            n_spread  = sum(1 for il_id, lbls in d["il_to_labels"].items() if len(lbls) > 1)
            print(f"  {f.get('프로젝트명','')}  |  예정일: {parse_date_rollup(f.get('임가공 예정일'))}  "
                  f"|  박스: {parse_total_boxes(f)}  |  품목 {len(d['items'])}건  "
                  f"|  합포장 {n_mixed}박스  분산 {n_spread}PT")
        return

    # ── PDF 출력 ───────────────────────────────────────────────────────────
    today_stamp = datetime.now().strftime("%Y%m%d-%H%M")
    suffix = (f"_{record_id}"   if record_id  else
              f"_{args.project}" if args.project else
              f"_{args.date}"    if args.date    else "")

    ok_count = 0
    for doc in docs:
        proj_code = doc["fields"].get("프로젝트명", doc["id"])
        filename  = f"출고확인서_{proj_code}_{today_stamp}.pdf"
        out_path  = OUT_DIR / filename

        buf = io.BytesIO()
        c   = rl_canvas.Canvas(buf, pagesize=A4)
        draw_confirmation(c, doc, 1, 1, font, font_bold)
        c.showPage()
        c.save()
        pdf_bytes = buf.getvalue()

        if not record_id or args.no_upload:
            out_path.write_bytes(pdf_bytes)
            print(f"✅ 저장 — {filename} ({out_path})")
        else:
            print(f"\n▶ {filename} 업로드 중…")
            if upload_via_content_api(doc["id"], ATTACH_FIELD_ID, filename, pdf_bytes):
                ok_count += 1

    if record_id and not args.no_upload:
        print(f"\n✅ 완료 — {ok_count}/{len(docs)}건 업로드")


if __name__ == "__main__":
    main()
