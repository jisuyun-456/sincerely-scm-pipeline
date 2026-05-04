"""
outer_box_label.py
────────────────────────────────────────────────────────────────────────────
logistics_release 테이블 → 외박스 품목 라벨 PDF 생성기

SINCERELY 스타일 (기본): 기업명 서브헤더 + 잔여분 구성품 표시
글로벌 스타일 (--style global): 국제 표준 Carton Label + Code128 바코드

사용법:
  python scripts/outer_box_label.py                          # 임가공 완료 전체
  python scripts/outer_box_label.py --lr-id recXXXXXX       # 단건
  python scripts/outer_box_label.py --to-num TO00015476     # TO번호로
  python scripts/outer_box_label.py --date 2026-04-30       # 날짜 필터
  python scripts/outer_box_label.py --style global          # 글로벌 스타일
  python scripts/outer_box_label.py --demo                  # 2페이지 비교 PDF
  python scripts/outer_box_label.py --dry-run               # 데이터 출력만
  python scripts/outer_box_label.py --lr-id recXXX --upload-field fldXXX
"""

import argparse, base64, os, platform, re, sys, time
from datetime import datetime
from io import BytesIO

import requests
from dotenv import load_dotenv
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

BASE_ID = os.getenv("SERPA_BASE_ID", "appkRWtF2j99XgBTq")
TBL_LR  = os.getenv("SERPA_LR_TABLE_ID", "tblj53ZBaJBpScNNI")
PAT     = (os.getenv("AIRTABLE_SERPA_PAT")
           or os.getenv("AIRTABLE_WMS_PAT")
           or os.getenv("AIRTABLE_PAT")
           or os.getenv("AIRTABLE_API_KEY", ""))
HEADERS = {"Authorization": f"Bearer {PAT}"}

LABEL_W = 150 * mm
LABEL_H = 100 * mm

F_TO_NUM       = "프로젝트명 (출고)"
F_DATE         = "출고 요청일"
F_PACKING      = "외박스 포장 내역"
F_BOX_SUM      = "외박스 수량"
F_STATUS       = "진행현황 (from Packaging_Schedule)"
F_COMPANY      = "기업명(알림톡2)"
F_COMPANY2     = "회사명"
F_PROJECT_LINK = "project"
F_PNA_SHORT    = "프로젝트명 (Short ver.) (from project)"   # PNA51357-산업연구원
PROJECT_TBL    = os.getenv("SERPA_PROJECT_TABLE_ID", "tblcw5sagkDlgAtJN")

if platform.system() == "Windows":
    FONT_REG = r"C:\Windows\Fonts\malgun.ttf"
    FONT_BLD = r"C:\Windows\Fonts\malgunbd.ttf"
else:
    FONT_REG = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
    FONT_BLD = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"


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


def airtable_get(table_id: str, params: dict) -> list:
    url = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}"
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


def upload_via_content_api(record_id: str, field_id: str,
                            filename: str, pdf_bytes: bytes) -> bool:
    url = (f"https://content.airtable.com/v0/{BASE_ID}"
           f"/{record_id}/{field_id}/uploadAttachment")
    payload = {
        "contentType": "application/pdf",
        "filename":    filename,
        "file":        base64.b64encode(pdf_bytes).decode("ascii"),
    }
    for attempt in range(2):
        try:
            r = requests.post(
                url,
                headers={"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"},
                json=payload, timeout=60,
            )
            if r.status_code == 429:
                time.sleep(int(r.headers.get("Retry-After", 10)))
                continue
            r.raise_for_status()
            print(f"  ✅ 업로드: {filename}")
            return True
        except requests.HTTPError as e:
            print(f"  ❌ 업로드 실패 {e.response.status_code}: {e.response.text[:200]}")
            return False
        except Exception as e:
            print(f"  ❌ 업로드 실패: {e}")
            return False
    return False


# ────────────────────────────────────────────────────────────────────────────
# 파싱
# ────────────────────────────────────────────────────────────────────────────
_BOX_ROW = re.compile(r"^(\d+)(\+\S+)?\s*\*\s*(\d+)\s+(.+?)\s*$")


def _clean_item_name(s: str) -> str:
    return re.sub(r"\s*\d+$", "", s).strip()


def _format_qty(qty_str: str) -> str:
    """
    '125+1'          → '125 + 1'
    '3+잔여분(...)'  → '3 + 잔여분'   (괄호 내용은 별도 표시)
    '125'            → '125'
    """
    m = re.match(r"^(\d+)\+(.+)$", qty_str)
    if not m:
        return qty_str
    bonus = re.sub(r"\([^)]*\)", "", m.group(2)).strip()
    return f"{m.group(1)} + {bonus}" if bonus else m.group(1)


def _parse_remainder(qty_str: str) -> list[dict]:
    """
    '3+잔여분(브랜디드타월1,브랜디드피규어키링2,올웨이즈양우산1)'
    → [{"name":"브랜디드타월","qty":"1"}, {"name":"브랜디드피규어키링","qty":"2"}, ...]
    """
    m = re.search(r"\+잔여분\(([^)]+)\)", qty_str)
    if not m:
        return []
    result = []
    for item_str in m.group(1).split(","):
        item_str = item_str.strip()
        nm = re.match(r"^(.+?)(\d+)$", item_str)
        if nm:
            result.append({"name": nm.group(1).strip(), "qty": nm.group(2)})
        else:
            result.append({"name": item_str, "qty": ""})
    return result


def parse_packing_detail(text: str) -> list[dict]:
    boxes = []
    current_item = None
    box_num = 0
    for line in (text or "").strip().splitlines():
        line = line.strip()
        if not line:
            continue
        m = _BOX_ROW.match(line)
        if m and current_item:
            qty_main  = m.group(1)
            qty_bonus = m.group(2) or ""
            count     = int(m.group(3))
            size      = m.group(4).strip()
            qty_str   = qty_main + qty_bonus
            for _ in range(count):
                box_num += 1
                boxes.append({
                    "box_num":        box_num,
                    "size":           size,
                    "item":           _clean_item_name(current_item),
                    "qty":            qty_str,
                    "remainder_items": _parse_remainder(qty_str),
                })
        else:
            current_item = line
    return boxes


# ────────────────────────────────────────────────────────────────────────────
# 데이터 조회
# ────────────────────────────────────────────────────────────────────────────
def _fetch_project_names(project_ids: list[str]) -> dict[str, str]:
    """project record ID 배치 조회 → {rec_id: 'PNA51357-산업연구원', ...}"""
    if not project_ids:
        return {}
    results: dict[str, str] = {}
    for i in range(0, len(project_ids), 10):
        batch = project_ids[i:i + 10]
        parts   = [f'RECORD_ID()="{pid}"' for pid in batch]
        formula = f"OR({','.join(parts)})"
        try:
            recs = airtable_get(PROJECT_TBL, {
                "fields[]":        ["Name"],
                "filterByFormula": formula,
                "pageSize":        100,
            })
            for r in recs:
                results[r["id"]] = r["fields"].get("Name", "")
        except Exception:
            pass
    return results


def fetch_lr_records(lr_id=None, to_num=None, date_str=None) -> list:
    formula_parts = []
    if lr_id:
        formula_parts.append(f'RECORD_ID()="{lr_id}"')
    elif to_num:
        formula_parts.append(f'{{{F_TO_NUM}}}="{to_num}"')
    else:
        formula_parts.append(
            f'FIND("5. 임가공 완료", ARRAYJOIN({{{F_STATUS}}}))'
        )
        if date_str:
            formula_parts.append(f'{{{F_DATE}}}="{date_str}"')

    formula = ("AND(" + ",".join(formula_parts) + ")") if len(formula_parts) > 1 else formula_parts[0]

    recs = airtable_get(TBL_LR, {
        "fields[]":           [F_TO_NUM, F_DATE, F_PACKING, F_BOX_SUM,
                               F_STATUS, F_COMPANY, F_COMPANY2, F_PROJECT_LINK,
                               F_PNA_SHORT],
        "filterByFormula":    formula,
        "pageSize":           100,
        "sort[0][field]":     F_DATE,
        "sort[0][direction]": "asc",
    })

    # project 이름 배치 조회
    proj_id_map: dict[str, str] = {}   # airtable_rec_id → project_rec_id
    for r in recs:
        linked = r.get("fields", {}).get(F_PROJECT_LINK, [])
        if linked:
            proj_id_map[r["id"]] = linked[0]
    proj_name_map = _fetch_project_names(list(set(proj_id_map.values())))

    result = []
    for r in recs:
        f = r.get("fields", {})
        packing_text = f.get(F_PACKING, "")
        if not packing_text:
            print(f"  ⚠  {f.get(F_TO_NUM, r['id'])} — 외박스 포장 내역 없음, 건너뜀")
            continue
        boxes = parse_packing_detail(packing_text)
        if not boxes:
            print(f"  ⚠  {f.get(F_TO_NUM, r['id'])} — 포장 내역 파싱 결과 없음, 건너뜀")
            continue
        total = len(boxes)
        for b in boxes:
            b["total_boxes"] = total

        # PO 표시: PNA short ver 우선 (PNA51357-산업연구원), 없으면 기업명 fallback
        _pna = f.get(F_PNA_SHORT, "")
        pna_short = (_pna[0] if isinstance(_pna, list) else _pna) or ""
        company = str(pna_short or f.get(F_COMPANY) or f.get(F_COMPANY2) or "")

        result.append({
            "rec_id":  r["id"],
            "to_num":  f.get(F_TO_NUM, ""),
            "date":    (f.get(F_DATE) or "")[:10],
            "box_sum": f.get(F_BOX_SUM, ""),
            "company": company,
            "boxes":   boxes,
        })
    return result


# ────────────────────────────────────────────────────────────────────────────
# SINCERELY 스타일 라벨 (기본)
# ────────────────────────────────────────────────────────────────────────────
def draw_label(c: rl_canvas.Canvas, x: float, y: float,
               box: dict, to_num: str, date_str: str, company: str,
               font: str, font_bold: str):
    W, H  = LABEL_W, LABEL_H
    PAD   = 5 * mm
    DARK  = colors.HexColor("#1A3A5C")
    MID   = colors.HexColor("#2B5380")
    LIGHT = colors.HexColor("#E8F0F7")
    LGRAY = colors.HexColor("#CCCCCC")

    # 테두리
    c.setStrokeColor(colors.HexColor("#333333"))
    c.setLineWidth(1.0)
    c.rect(x, y, W, H)

    # ── 헤더 띠 (dark navy, 13mm) ────────────────────────────────────────────
    HDR_H = 13 * mm
    c.setFillColor(DARK)
    c.rect(x, y + H - HDR_H, W, HDR_H, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont(font, 10)
    c.drawString(x + PAD, y + H - HDR_H + 5 * mm, "SINCERELY  외박스 라벨")
    c.setFont(font_bold, 11)
    c.drawRightString(x + W - PAD, y + H - HDR_H + 5 * mm, to_num)

    # ── 서브헤더 (medium navy, 7mm) — 기업명 ─────────────────────────────────
    SUB_H = 7 * mm
    SUB_Y = y + H - HDR_H - SUB_H
    c.setFillColor(MID)
    c.rect(x, SUB_Y, W, SUB_H, fill=1, stroke=0)
    if company:
        c.setFillColor(colors.HexColor("#B8D4EA"))
        c.setFont(font, 8.5)
        c.drawRightString(x + W - PAD, SUB_Y + 2 * mm, company)

    # ── 박스번호 / 규격 블록 (light blue, 20mm) ──────────────────────────────
    BOX_BLK_H = 20 * mm
    BOX_BLK_Y = SUB_Y - BOX_BLK_H
    c.setFillColor(LIGHT)
    c.rect(x, BOX_BLK_Y, W, BOX_BLK_H, fill=1, stroke=0)
    c.setFillColor(DARK)
    c.setFont(font_bold, 20)
    c.drawString(x + PAD, BOX_BLK_Y + 6 * mm,
                 f"박스  {box['box_num']}  /  {box['total_boxes']}")
    c.setFont(font, 12)
    c.setFillColor(colors.HexColor("#555555"))
    c.drawRightString(x + W - PAD, BOX_BLK_Y + 7 * mm, f"[ {box['size']}형 ]")

    # 구분선
    sep_y = BOX_BLK_Y - 3 * mm
    c.setStrokeColor(LGRAY)
    c.setLineWidth(0.5)
    c.line(x + PAD, sep_y, x + W - PAD, sep_y)

    # ── 품목명 ──────────────────────────────────────────────────────────────
    ITEM_Y = sep_y - 9 * mm
    c.setFillColor(colors.black)
    c.setFont(font_bold, 14)
    c.drawString(x + PAD, ITEM_Y, box["item"][:30])

    # ── 수량 ────────────────────────────────────────────────────────────────
    QTY_Y = ITEM_Y - 13 * mm
    c.setFont(font, 10)
    c.setFillColor(colors.HexColor("#666666"))
    c.drawString(x + PAD, QTY_Y + 2 * mm, "수  량")
    c.setFont(font_bold, 24)
    c.setFillColor(DARK)
    qty_display = _format_qty(box["qty"])
    c.drawRightString(x + W - PAD, QTY_Y, f"{qty_display}  개")

    # ── 잔여분 구성품 ─────────────────────────────────────────────────────────
    remainders = box.get("remainder_items", [])
    if remainders:
        REM_TOP = QTY_Y - 5 * mm
        REM_H   = len(remainders) * 4 * mm + 5 * mm
        REM_BOT = REM_TOP - REM_H
        c.setFillColor(colors.HexColor("#F0F4F8"))
        c.setStrokeColor(colors.HexColor("#BBCCDD"))
        c.setLineWidth(0.4)
        c.rect(x + PAD, REM_BOT, W - 2 * PAD, REM_H, fill=1, stroke=1)
        # 섹션 레이블
        c.setFillColor(colors.HexColor("#7A9AB8"))
        c.setFont(font, 7)
        c.drawString(x + PAD + 2 * mm, REM_BOT + REM_H - 4 * mm, "잔여분 구성품")
        # 각 품목
        for i, rem in enumerate(remainders):
            iy = REM_BOT + REM_H - (i + 2) * 4 * mm + 1 * mm
            c.setFillColor(colors.HexColor("#222222"))
            c.setFont(font, 9)
            c.drawString(x + PAD + 3 * mm, iy,
                         f"•  {rem['name']}  ×  {rem['qty']}개")

    # ── 하단 출고 요청일 ─────────────────────────────────────────────────────
    c.setFillColor(colors.HexColor("#999999"))
    c.setFont(font, 9)
    c.drawString(x + PAD, y + 4 * mm, f"출고 요청일: {date_str}")


# ────────────────────────────────────────────────────────────────────────────
# 글로벌 스타일 라벨 (국제 표준 Carton Label + Code128)
# ────────────────────────────────────────────────────────────────────────────
def draw_label_global(c: rl_canvas.Canvas, x: float, y: float,
                      box: dict, to_num: str, date_str: str, company: str,
                      font: str, font_bold: str):
    """HTML 기반 Carton Label (150×100mm) — CARTON LABEL 헤더 / TO·PO·BOX meta / 품목+수량 / 푸터"""
    W, H  = LABEL_W, LABEL_H
    PAD   = 5.5 * mm
    NAVY  = colors.HexColor("#0b2747")
    INK   = colors.HexColor("#0f0f10")
    INK2  = colors.HexColor("#3a3a3d")
    MUTED = colors.HexColor("#7c7c82")
    MUTED2 = colors.HexColor("#9aa0a8")
    LINE  = colors.HexColor("#d8d9dd")

    # ── 헤더 (navy, 10.5mm) ────────────────────────────────────────────────
    HDR_H = 10.5 * mm
    HDR_Y = y + H - HDR_H
    c.setFillColor(NAVY)
    c.rect(x, HDR_Y, W, HDR_H, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont(font_bold, 8.5)
    c.drawString(x + PAD, HDR_Y + 3.5 * mm, "■  CARTON LABEL")
    c.setFont(font_bold, 9.1)
    c.drawRightString(x + W - PAD, HDR_Y + 3.5 * mm, "SINCERELY")

    # ── Meta 섹션 (22mm, 하단 구분선 + 수직 구분선) ──────────────────────
    META_H = 22 * mm
    META_Y = HDR_Y - META_H
    DIV_X  = x + W - 28 * mm

    c.setStrokeColor(LINE); c.setLineWidth(0.85)
    c.line(x, META_Y, x + W, META_Y)       # 하단선
    c.line(DIV_X, META_Y, DIV_X, HDR_Y)    # 수직 구분선

    for i, (k, v) in enumerate([
        ("TO",  to_num),
        ("PO",  (company or "")[:28]),
        ("BOX", f"{box['box_num']} / {box['total_boxes']}"),
    ]):
        ry = HDR_Y - (5 * mm + i * 6.5 * mm)
        c.setFont(font_bold, 7.4); c.setFillColor(MUTED)
        c.drawString(x + PAD, ry, k)
        c.setFont(font_bold, 9.1); c.setFillColor(INK)
        c.drawString(x + PAD + 14 * mm, ry, v)

    c.setFont(font_bold, 7.4); c.setFillColor(MUTED)
    c.drawRightString(x + W - PAD, HDR_Y - 5 * mm, "SIZE")
    c.setFont(font_bold, 15.3); c.setFillColor(INK)
    c.drawRightString(x + W - PAD, HDR_Y - 14 * mm, f"{box['size']}형")

    # ── Body (Contents + Qty 수직 중앙) ──────────────────────────────────
    FTR_H  = 8.5 * mm
    BODY_H = META_Y - (y + FTR_H)     # ~59mm
    CNT_Y  = META_Y - BODY_H * 0.32   # Contents 섹션 상단

    # Contents
    c.setFont(font_bold, 7.4); c.setFillColor(MUTED)
    c.drawString(x + PAD, CNT_Y + 3 * mm, "CONTENTS")
    c.setFont(font_bold, 25.5); c.setFillColor(INK)
    c.drawString(x + PAD, CNT_Y - 2.5 * mm, box["item"][:18])

    # Qty
    QTY_Y = CNT_Y - 17 * mm
    c.setFont(font_bold, 7.4); c.setFillColor(MUTED)
    c.drawString(x + PAD, QTY_Y + 3 * mm, "QTY")

    m_qty = re.match(r"^(\d+)(?:\+(\d+))?", box["qty"])
    main  = m_qty.group(1) if m_qty else box["qty"]
    extra = m_qty.group(2) if m_qty else None

    c.setFont(font_bold, 31.2); c.setFillColor(INK)
    c.drawString(x + PAD, QTY_Y - 2 * mm, main)
    cur_x = x + PAD + c.stringWidth(main, font_bold, 31.2)

    if extra:
        c.setFont(font_bold, 9); c.setFillColor(MUTED2)
        c.drawString(cur_x + 1 * mm, QTY_Y + 2 * mm, "+")
        cur_x += 1 * mm + c.stringWidth("+", font_bold, 9)
        c.setFont(font_bold, 22.7); c.setFillColor(INK2)
        c.drawString(cur_x + 1 * mm, QTY_Y - 1 * mm, extra)
        cur_x += 1 * mm + c.stringWidth(extra, font_bold, 22.7)

    c.setFont(font_bold, 17); c.setFillColor(INK2)
    c.drawString(cur_x + 2 * mm, QTY_Y - 1 * mm, "EA")

    # ── 푸터 (연회색 배경, 상단 구분선) ──────────────────────────────────
    c.setFillColor(colors.HexColor("#fafbfd"))
    c.rect(x, y, W, FTR_H, fill=1, stroke=0)
    c.setStrokeColor(LINE); c.setLineWidth(0.85)
    c.line(x, y + FTR_H, x + W, y + FTR_H)

    c.setFont(font_bold, 6.8); c.setFillColor(MUTED)
    c.drawString(x + PAD, y + 4.5 * mm, "SHIP")
    ship_kw = c.stringWidth("SHIP  ", font_bold, 6.8)
    c.setFont(font_bold, 7.9); c.setFillColor(INK2)
    c.drawString(x + PAD + ship_kw, y + 4.5 * mm, date_str)

    div1_x = x + PAD + ship_kw + c.stringWidth(date_str, font_bold, 7.9) + 4 * mm
    c.setStrokeColor(LINE); c.setLineWidth(0.85)
    c.line(div1_x, y + 1.5 * mm, div1_x, y + 6 * mm)

    c.setFont(font_bold, 6.8); c.setFillColor(MUTED)
    c.drawString(div1_x + 3 * mm, y + 4.5 * mm, "ORIGIN")
    orig_kw = c.stringWidth("ORIGIN  ", font_bold, 6.8)
    c.setFont(font_bold, 7.9); c.setFillColor(INK2)
    c.drawString(div1_x + 3 * mm + orig_kw, y + 4.5 * mm, "KOR")

    c.setFont(font_bold, 7.9); c.setFillColor(NAVY)
    c.drawRightString(x + W - PAD, y + 4.5 * mm, "SINCERELY Co.")

    # ── 외곽선 ────────────────────────────────────────────────────────────
    c.setStrokeColor(colors.HexColor("#333333"))
    c.setLineWidth(1.0)
    c.rect(x, y, W, H, stroke=1, fill=0)


# ────────────────────────────────────────────────────────────────────────────
# PDF 생성
# ────────────────────────────────────────────────────────────────────────────
def generate_pdf(lr_records: list, output, style: str = "sincerely") -> int:
    font, font_bold = register_fonts()
    c = rl_canvas.Canvas(output, pagesize=(LABEL_W, LABEL_H))
    draw_fn = draw_label_global if style == "global" else draw_label
    count = 0
    for lr in lr_records:
        for box in lr["boxes"]:
            draw_fn(c, 0, 0, box, lr["to_num"], lr["date"],
                    lr["company"], font, font_bold)
            c.showPage()
            count += 1
    c.save()
    return count


def generate_demo_pdf(lr_records: list, output) -> int:
    """잔여분이 있는 박스를 골라 SINCERELY/글로벌 2페이지 비교 PDF 생성"""
    font, font_bold = register_fonts()
    c = rl_canvas.Canvas(output, pagesize=(LABEL_W, LABEL_H))

    # 잔여분 박스 우선, 없으면 첫 번째 박스
    demo_box = None
    demo_lr  = None
    for lr in lr_records:
        for box in lr["boxes"]:
            if box.get("remainder_items"):
                demo_box = box
                demo_lr  = lr
                break
        if demo_box:
            break
    if not demo_box:
        demo_lr  = lr_records[0]
        demo_box = lr_records[0]["boxes"][0]

    # 페이지 1: SINCERELY 스타일
    draw_label(c, 0, 0, demo_box, demo_lr["to_num"], demo_lr["date"],
               demo_lr["company"], font, font_bold)
    c.showPage()
    # 페이지 2: 글로벌 스타일
    draw_label_global(c, 0, 0, demo_box, demo_lr["to_num"], demo_lr["date"],
                      demo_lr["company"], font, font_bold)
    c.showPage()
    c.save()
    return 2


# ────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="외박스 품목 라벨 PDF 생성기")
    parser.add_argument("--lr-id",        help="logistics_release record ID")
    parser.add_argument("--to-num",       help="TO번호 (예: TO00015476)")
    parser.add_argument("--date",         help="출고 요청일 필터 (예: 2026-04-30)")
    parser.add_argument("--upload-field", help="업로드할 Airtable 필드 ID")
    parser.add_argument("--style",        choices=["sincerely", "global"],
                        default="sincerely", help="라벨 스타일 (기본: sincerely)")
    parser.add_argument("--demo",         action="store_true",
                        help="SINCERELY+글로벌 2페이지 비교 PDF 생성")
    parser.add_argument("--dry-run",      action="store_true",
                        help="데이터 출력만, PDF 미생성")
    args = parser.parse_args()

    if not PAT:
        print("[ERROR] AIRTABLE_WMS_PAT 또는 AIRTABLE_PAT 환경변수를 .env에 설정하세요")
        sys.exit(1)

    lr_id  = getattr(args, "lr_id", None)
    to_num = getattr(args, "to_num", None)

    print("▶ logistics_release 조회 중…")
    records = fetch_lr_records(lr_id=lr_id, to_num=to_num, date_str=args.date)

    if not records:
        print("조회 결과 없음 (임가공 완료 레코드 없거나 외박스 포장 내역 미입력)")
        return

    total_labels = sum(len(r["boxes"]) for r in records)
    print(f"  {len(records)}건 조회 → 총 {total_labels}장 라벨\n")
    for r in records:
        print(f"  • {r['to_num']:<14}  {r['date']}  {r['company']}  {r['box_sum']}")
        for b in r["boxes"]:
            rem_str = f"  [{', '.join(x['name'] for x in b['remainder_items'])}]" \
                      if b["remainder_items"] else ""
            print(f"      박스{b['box_num']:>2}/{b['total_boxes']}  [{b['size']:4}형]  "
                  f"{b['item'][:25]:<25}  {b['qty']}개{rem_str}")

    if args.dry_run:
        print("\n[dry-run] PDF 생성 건너뜀")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    if lr_id:
        suffix = f"_{lr_id[:8]}"
    elif to_num:
        suffix = f"_{to_num}"
    elif args.date:
        suffix = f"_{args.date}"
    else:
        suffix = ""

    if args.demo:
        filename = f"외박스라벨_비교예시{suffix}_{stamp}.pdf"
    elif args.style == "global":
        filename = f"외박스라벨_글로벌{suffix}_{stamp}.pdf"
    else:
        filename = f"외박스라벨{suffix}_{stamp}.pdf"

    buf = BytesIO()
    if args.demo:
        n = generate_demo_pdf(records, buf)
    else:
        n = generate_pdf(records, buf, style=args.style)
    pdf_bytes = buf.getvalue()

    upload_field = getattr(args, "upload_field", None)
    if upload_field and len(records) == 1:
        print(f"\n▶ {filename} 업로드 중…")
        upload_via_content_api(records[0]["rec_id"], upload_field, filename, pdf_bytes)
    else:
        from pathlib import Path
        out_dir  = Path(os.getenv("PDF_OUTPUT_DIR", r"C:\Users\yjisu\Desktop"))
        out_path = out_dir / filename
        out_path.write_bytes(pdf_bytes)
        print(f"\n✅ 완료 — {n}페이지 저장: {out_path}")


if __name__ == "__main__":
    main()
