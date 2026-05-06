"""
packing_list.py
────────────────────────────────────────────────────────────────────────────
logistics_release → Packing List PDF (A4, 글로벌 표준)

사용법:
  python scripts/packing_list.py --to-num TO00016012
  python scripts/packing_list.py --lr-id recXXXXXX
  python scripts/packing_list.py --date 2026-04-30
"""

import argparse, os, platform, re, sys, time
from datetime import datetime
from io import BytesIO

import requests
from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Table, TableStyle

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

BASE_ID     = os.getenv("SERPA_BASE_ID", "appkRWtF2j99XgBTq")
TBL_LR      = os.getenv("SERPA_LR_TABLE_ID", "tblj53ZBaJBpScNNI")
PROJECT_TBL = os.getenv("SERPA_PROJECT_TABLE_ID", "tblcw5sagkDlgAtJN")
PAT = (os.getenv("AIRTABLE_SERPA_PAT")
       or os.getenv("AIRTABLE_WMS_PAT")
       or os.getenv("AIRTABLE_PAT")
       or os.getenv("AIRTABLE_API_KEY", ""))
HEADERS = {"Authorization": f"Bearer {PAT}"}

PW, PH = A4   # 210mm × 297mm
MARGIN = 18 * mm

if platform.system() == "Windows":
    FONT_REG = r"C:\Windows\Fonts\malgun.ttf"
    FONT_BLD = r"C:\Windows\Fonts\malgunbd.ttf"
else:
    FONT_REG = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
    FONT_BLD = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"

DARK  = colors.HexColor("#1A3A5C")
LIGHT = colors.HexColor("#E8F0F7")
LGRAY = colors.HexColor("#DDDDDD")
MID   = colors.HexColor("#4A7BA0")


# ────────────────────────────────────────────────────────────────────────────
# 공통 유틸 (outer_box_label.py와 동일 패턴)
# ────────────────────────────────────────────────────────────────────────────
def register_fonts():
    try:
        pdfmetrics.registerFont(TTFont("Malgun",     FONT_REG))
        pdfmetrics.registerFont(TTFont("MalgunBold", FONT_BLD))
        return "Malgun", "MalgunBold"
    except Exception:
        return "Helvetica", "Helvetica-Bold"


def clear_attachment_field(record_id: str, field_id: str) -> None:
    try:
        r = requests.patch(
            f"https://api.airtable.com/v0/{BASE_ID}/{TBL_LR}/{record_id}",
            headers={"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"},
            json={"fields": {field_id: []}},
            timeout=30,
        )
        r.raise_for_status()
        print("  🗑️ 기존 첨부 초기화")
    except Exception as e:
        print(f"  ⚠️ 기존 첨부 삭제 실패 (무시): {e}")


def upload_via_content_api(record_id: str, field_id: str,
                           filename: str, pdf_bytes: bytes) -> bool:
    import base64
    url = (f"https://content.airtable.com/v0/{BASE_ID}"
           f"/{record_id}/{field_id}/uploadAttachment")
    payload = {
        "contentType": "application/pdf",
        "filename":    filename,
        "file":        base64.b64encode(pdf_bytes).decode("ascii"),
    }
    for _ in range(2):
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


_BOX_ROW        = re.compile(r"^(\d+)(\s*\+\s*[^\s*]+(?:\([^)]*\))*)?\s*\*\s*(\d+)\s*(.+?)\s*$")
_BOX_ROW_INLINE = re.compile(r"^(.+?)\s+(\d+(?:[+][^\s*]+)?)\s*\*\s*(\d+)\s+([대중소]형?)\s*$")


def _clean_item_name(s: str) -> str:
    return re.sub(r"\s*\d+$", "", s).strip()


def _format_qty(qty_str: str) -> str:
    m = re.match(r"^(\d+)\+(.+)$", qty_str)
    if not m:
        return qty_str
    bonus = re.sub(r"\([^)]*\)", "", m.group(2)).strip()
    return f"{m.group(1)} + {bonus}" if bonus else m.group(1)


def _parse_remainder(qty_str: str) -> list[dict]:
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
        line = re.sub(r'\s+', ' ', line).strip().rstrip('`').strip()
        if not line:
            continue
        m = _BOX_ROW.match(line)
        if m and current_item:
            extra   = re.sub(r'\s*\+\s*', '+', m.group(2) or "")
            qty_str = m.group(1) + extra
            for _ in range(int(m.group(3))):
                box_num += 1
                boxes.append({
                    "box_num":        box_num,
                    "size":           m.group(4).strip(),
                    "item":           _clean_item_name(current_item),
                    "qty":            qty_str,
                    "remainder_items": _parse_remainder(qty_str),
                })
        else:
            mi = _BOX_ROW_INLINE.match(line)
            if mi:
                current_item = mi.group(1).strip()
                qty_str = mi.group(2)
                for _ in range(int(mi.group(3))):
                    box_num += 1
                    boxes.append({
                        "box_num":        box_num,
                        "size":           mi.group(4).strip(),
                        "item":           _clean_item_name(current_item),
                        "qty":            qty_str,
                        "remainder_items": _parse_remainder(qty_str),
                    })
            else:
                current_item = line
    return boxes


def consolidate_boxes(boxes: list[dict]) -> list[dict]:
    """연속된 동일 품목·수량 박스를 통합: [{box_range, item, qty, size, remainder_items}]"""
    if not boxes:
        return []
    groups = []
    cur = {**boxes[0], "box_start": boxes[0]["box_num"], "box_end": boxes[0]["box_num"]}
    for b in boxes[1:]:
        if b["item"] == cur["item"] and b["qty"] == cur["qty"] and b["size"] == cur["size"]:
            cur["box_end"] = b["box_num"]
        else:
            groups.append(cur)
            cur = {**b, "box_start": b["box_num"], "box_end": b["box_num"]}
    groups.append(cur)
    return groups


def _fetch_project_name(project_id: str) -> str:
    if not project_id:
        return ""
    try:
        recs = airtable_get(PROJECT_TBL, {
            "fields[]": ["Name"],
            "filterByFormula": f'RECORD_ID()="{project_id}"',
            "pageSize": 1,
        })
        return recs[0]["fields"].get("Name", "") if recs else ""
    except Exception:
        return ""


FIELDS = [
    "프로젝트명 (출고)", "출고 요청일", "외박스 포장 내역", "외박스 수량",
    "진행현황 (from Packaging_Schedule)",
    "기업명(알림톡2)", "회사명", "project",
    "수령인(성함)", "수령인(주소)", "수령인(연락처)",
    "발신인_CX", "발신인주소(CX)", "발신인연락처(CX)",
]


def fetch_record(lr_id=None, to_num=None, date_str=None) -> list:
    formula_parts = []
    if lr_id:
        formula_parts.append(f'RECORD_ID()="{lr_id}"')
    elif to_num:
        formula_parts.append(f'{{프로젝트명 (출고)}}="{to_num}"')
    else:
        formula_parts.append('FIND("5. 임가공 완료", ARRAYJOIN({진행현황 (from Packaging_Schedule)}))')
        if date_str:
            formula_parts.append(f'{{출고 요청일}}="{date_str}"')

    formula = ("AND(" + ",".join(formula_parts) + ")") if len(formula_parts) > 1 else formula_parts[0]

    recs = airtable_get(TBL_LR, {
        "fields[]":           FIELDS,
        "filterByFormula":    formula,
        "pageSize":           100,
        "sort[0][field]":     "출고 요청일",
        "sort[0][direction]": "asc",
    })

    result = []
    for r in recs:
        f = r.get("fields", {})
        boxes = parse_packing_detail(f.get("외박스 포장 내역", ""))
        if not boxes:
            continue
        total = len(boxes)
        box_sum_raw = f.get("외박스 수량")
        if box_sum_raw is not None and int(box_sum_raw) != total:
            print(f"  ⚠️ [수량 불일치] {f.get('프로젝트명 (출고)', '')} — "
                  f"외박스 수량 필드={int(box_sum_raw)}  포장내역 파싱={total}")
        for b in boxes:
            b["total_boxes"] = total

        proj_ids = f.get("project", [])
        proj_name = _fetch_project_name(proj_ids[0] if proj_ids else "")
        company = proj_name or f.get("기업명(알림톡2)") or f.get("회사명", "")

        result.append({
            "rec_id":         r["id"],
            "to_num":         f.get("프로젝트명 (출고)", ""),
            "date":           (f.get("출고 요청일") or "")[:10],
            "company":        company,
            "box_sum":        str(f.get("외박스 수량") or ""),
            "consignee_name": f.get("수령인(성함)", ""),
            "consignee_addr": f.get("수령인(주소)", ""),
            "consignee_tel":  f.get("수령인(연락처)", ""),
            "shipper_name":   f.get("발신인_CX", ""),
            "shipper_addr":   f.get("발신인주소(CX)", ""),
            "shipper_tel":    f.get("발신인연락처(CX)", ""),
            "boxes":          boxes,
            "groups":         consolidate_boxes(boxes),
        })
    return result


# ────────────────────────────────────────────────────────────────────────────
# PDF 그리기
# ────────────────────────────────────────────────────────────────────────────
def draw_packing_list(c: rl_canvas.Canvas, rec: dict, font: str, font_bold: str):
    """HTML 디자인 기반 Packing List (A4) — 네이비 헤더 / 주소 카드 / 품목표 / 합계 바"""
    W, M = PW, MARGIN
    y    = PH - M

    NAVY  = colors.HexColor("#0b2747")
    NAVY2 = colors.HexColor("#173559")
    INK   = colors.HexColor("#0f0f10")
    INK2  = colors.HexColor("#3a3a3d")
    MUTED = colors.HexColor("#7c7c82")
    LINE  = colors.HexColor("#dde0e6")
    LINE2 = colors.HexColor("#eef0f4")
    TINT  = colors.HexColor("#eef3fa")
    TINT2 = colors.HexColor("#f6f8fb")
    W_MUT = colors.HexColor("#c4d3e2")   # rgba(white, .78) on navy bg

    def ln(h=5*mm):
        nonlocal y; y -= h

    # ── 1. 헤더 (전폭 네이비, 30mm) ─────────────────────────────────────────
    HDR_H = 30 * mm
    c.setFillColor(NAVY)
    c.rect(0, y - HDR_H, W, HDR_H, fill=1, stroke=0)

    c.setFillColor(colors.white)
    c.setFont(font_bold, 40)
    c.drawString(M, y - 22*mm, "PACKING LIST")

    def hdr_kv(key, val, row_y):
        vw = c.stringWidth(val, font_bold, 9)
        sw = c.stringWidth("  ", font, 9)
        c.setFont(font_bold, 9); c.setFillColor(colors.white)
        c.drawRightString(W - M, row_y, val)
        c.setFont(font, 9); c.setFillColor(W_MUT)
        c.drawRightString(W - M - vw - sw, row_y, key)

    hdr_kv("Date",    rec["date"],    y - 10*mm)
    hdr_kv("Ref No.", rec["to_num"],  y - 16*mm)

    y -= HDR_H; ln(8*mm)

    # ── 2. 주소 카드 2단 (38mm) ──────────────────────────────────────────────
    CARD_GAP = 5 * mm
    CARD_W   = (W - 2*M - CARD_GAP) / 2
    CARD_H   = 38 * mm

    def draw_addr(cx, label, name, addr, attn, tel):
        c.setFillColor(TINT2); c.setStrokeColor(LINE); c.setLineWidth(0.85)
        c.rect(cx, y - CARD_H, CARD_W, CARD_H, fill=1, stroke=1)
        c.setFillColor(NAVY)
        c.rect(cx, y - 0.8*mm, CARD_W, 0.8*mm, fill=1, stroke=0)
        IP = 5.5 * mm
        c.setFont(font_bold, 7.4); c.setFillColor(NAVY)
        c.drawString(cx + IP, y - 5.5*mm, label.upper())
        c.setFont(font_bold, 13); c.setFillColor(INK)
        c.drawString(cx + IP, y - 12*mm, (name or "—")[:22])
        c.setFont(font, 9); c.setFillColor(INK2)
        addr_text = addr or ""
        CHR = 27
        c.drawString(cx + IP, y - 19*mm, addr_text[:CHR])
        if len(addr_text) > CHR:
            c.drawString(cx + IP, y - 24*mm, addr_text[CHR:CHR * 2])
        ry = y - 28.5*mm
        for key, val in [("담당", attn), ("Tel", tel)]:
            if val:
                c.setFont(font_bold, 7.9); c.setFillColor(MUTED)
                c.drawString(cx + IP, ry, key)
                c.setFont(font, 9); c.setFillColor(INK2)
                c.drawString(cx + IP + 11*mm, ry, str(val))
                ry -= 5*mm

    shipper_name = rec.get("shipper_name") or "현동원"
    shipper_addr = (rec.get("shipper_addr")
                    or "서울시 성동구 왕십리로88 노벨빌딩 4층 신시어리")
    shipper_tel  = rec.get("shipper_tel") or ""
    company_disp = (rec["company"].split("-", 1)[-1]
                    if "-" in rec["company"] else rec["company"])
    cons_attn    = rec.get("consignee_name") or company_disp

    draw_addr(M, "From (Shipper)",
              "SINCERELY Co., Ltd.", shipper_addr, shipper_name, shipper_tel)
    draw_addr(M + CARD_W + CARD_GAP, "To (Consignee)",
              company_disp, rec.get("consignee_addr", ""),
              cons_attn,    rec.get("consignee_tel", ""))
    y -= CARD_H; ln(7*mm)

    # ── 3. 프로젝트 참조 바 (tint, 10mm) ─────────────────────────────────────
    PROJ_H = 10 * mm
    c.setFillColor(TINT); c.setStrokeColor(colors.HexColor("#cfd9e8"))
    c.setLineWidth(0.85)
    c.rect(M, y - PROJ_H, W - 2*M, PROJ_H, fill=1, stroke=1)

    c.setFont(font_bold, 8); c.setFillColor(NAVY)
    c.drawString(M + 5*mm, y - 6.5*mm, "Project Ref.")
    kw = c.stringWidth("Project Ref.  ", font_bold, 8)
    c.setFont(font, 9.1); c.setFillColor(INK)
    c.drawString(M + 5*mm + kw, y - 6.5*mm, rec["company"])

    bw = c.stringWidth(rec["box_sum"], font_bold, 9.1)
    sw = c.stringWidth("   ", font, 8)
    c.setFont(font_bold, 9.1); c.setFillColor(INK)
    c.drawRightString(W - M - 5*mm, y - 6.5*mm, rec["box_sum"])
    c.setFont(font_bold, 8); c.setFillColor(NAVY)
    c.drawRightString(W - M - 5*mm - bw - sw, y - 6.5*mm, "Total")

    y -= PROJ_H; ln(6*mm)

    # ── 4. 품목 테이블 (canvas 직접 그리기, platypus 미사용) ─────────────────
    TBL_W  = W - 2*M
    desc_w = TBL_W - 18*mm - 30*mm - 18*mm - 30*mm
    COL_W  = [18*mm, desc_w, 30*mm, 18*mm, 30*mm]
    COL_AL = ["C", "L", "C", "C", "C"]
    HDR_H_TBL = 8 * mm
    ROW_H_TBL = 7.5 * mm

    # 헤더 행
    c.setFillColor(NAVY)
    c.rect(M, y - HDR_H_TBL, TBL_W, HDR_H_TBL, fill=1, stroke=0)
    c.setFont(font_bold, 8); c.setFillColor(colors.white)
    hx = M
    for hdr, cw in zip(
        ["BOX No.", "DESCRIPTION OF GOODS", "QTY / UNIT", "SIZE", "REMARKS"], COL_W
    ):
        c.drawCentredString(hx + cw / 2, y - HDR_H_TBL + 2.5 * mm, hdr)
        hx += cw
    y -= HDR_H_TBL

    # 데이터 행
    row_data = []
    for grp in rec["groups"]:
        box_lbl = (f"{grp['box_start']} ~ {grp['box_end']}"
                   if grp["box_start"] != grp["box_end"] else str(grp["box_start"]))
        row_data.append((box_lbl, grp["item"][:38],
                         f"{_format_qty(grp['qty'])} EA", f"{grp['size']}형", ""))
        for rem in grp.get("remainder_items", []):
            row_data.append(("", f"  └ {rem['name'][:32]}", f"{rem['qty']} EA", "", ""))

    tbl_start_y = y
    for ri, row in enumerate(row_data):
        bg = colors.white if ri % 2 == 0 else colors.HexColor("#fafbfd")
        c.setFillColor(bg)
        c.rect(M, y - ROW_H_TBL, TBL_W, ROW_H_TBL, fill=1, stroke=0)
        c.setStrokeColor(LINE); c.setLineWidth(0.85)
        c.line(M, y - ROW_H_TBL, M + TBL_W, y - ROW_H_TBL)
        c.setFont(font, 9.1); c.setFillColor(INK)
        rx = M
        for j, (cell, cw, align) in enumerate(zip(row, COL_W, COL_AL)):
            if align == "C":
                c.drawCentredString(rx + cw / 2, y - ROW_H_TBL + 2.5 * mm, str(cell))
            else:
                pad = 5 * mm if j == 1 else 3 * mm
                c.drawString(rx + pad, y - ROW_H_TBL + 2.5 * mm, str(cell))
            rx += cw
        y -= ROW_H_TBL

    c.setStrokeColor(LINE); c.setLineWidth(0.85)
    c.rect(M, y, TBL_W, tbl_start_y - y + HDR_H_TBL, stroke=1, fill=0)
    ln(7*mm)

    # ── 5. 합계 바 (네이비, 12mm) ─────────────────────────────────────────────
    TOTAL_H = 12 * mm
    c.setFillColor(NAVY)
    c.rect(M, y - TOTAL_H, W - 2*M, TOTAL_H, fill=1, stroke=0)

    total_ctn = rec["boxes"][0]["total_boxes"] if rec["boxes"] else 0
    c.setFont(font_bold, 9.6); c.setFillColor(W_MUT)
    c.drawString(M + 5*mm, y - 7.5*mm, "Total Cartons")
    kw2 = c.stringWidth("Total Cartons   ", font_bold, 9.6)
    c.setFillColor(colors.white)
    c.drawString(M + 5*mm + kw2, y - 7.5*mm, f"{total_ctn} CTN")

    c.drawRightString(W - M - 5*mm, y - 7.5*mm, "KOREA")
    origin_w = c.stringWidth("KOREA  ", font_bold, 9.6)
    c.setFillColor(W_MUT)
    c.drawRightString(W - M - 5*mm - origin_w, y - 7.5*mm, "Origin")

    y -= TOTAL_H; ln(11*mm)

    # ── 6. 서명란 ────────────────────────────────────────────────────────────
    SIG_W = (W - 2*M - 10*mm) / 2
    for i, (lbl, sx) in enumerate([("Prepared by", M),
                                    ("Approved by", M + SIG_W + 10*mm)]):
        c.setFont(font_bold, 8); c.setFillColor(NAVY)
        c.drawString(sx, y, lbl.upper())
        sig_name = (rec.get("shipper_name") or "SINCERELY") if i == 0 else ""
        if sig_name:
            c.setFont(font_bold, 10.2); c.setFillColor(INK)
            c.drawString(sx, y - 7.5*mm, sig_name)
        c.setStrokeColor(INK2 if sig_name else LINE)
        c.setLineWidth(1.1)
        c.line(sx, y - 9*mm, sx + SIG_W, y - 9*mm)

    # ── 7. 페이지 하단 ───────────────────────────────────────────────────────
    c.setFillColor(MUTED); c.setFont(font, 7.5)
    c.drawCentredString(W / 2, M / 2,
                        f"SINCERELY Co., Ltd.  ·  Packing List  ·  {rec['to_num']}")


def generate_packing_list(records: list, output) -> int:
    font, font_bold = register_fonts()
    c = rl_canvas.Canvas(output, pagesize=A4)
    for rec in records:
        draw_packing_list(c, rec, font, font_bold)
        c.showPage()
    c.save()
    return len(records)


def main():
    parser = argparse.ArgumentParser(description="Packing List PDF 생성기")
    parser.add_argument("--lr-id",        help="logistics_release record ID")
    parser.add_argument("--to-num",       help="TO번호")
    parser.add_argument("--date",         help="출고 요청일 필터 (예: 2026-04-30)")
    parser.add_argument("--upload-field", help="업로드할 Airtable 필드 ID")
    args = parser.parse_args()

    if not PAT:
        print("[ERROR] AIRTABLE_SERPA_PAT 환경변수를 설정하세요")
        sys.exit(1)

    print("▶ 데이터 조회 중…")
    records = fetch_record(
        lr_id=getattr(args, "lr_id", None),
        to_num=getattr(args, "to_num", None),
        date_str=args.date,
    )
    if not records:
        print("조회 결과 없음")
        return

    for r in records:
        print(f"  • {r['to_num']}  {r['date']}  {r['company']}  {r['box_sum']}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    suffix = f"_{args.to_num}" if args.to_num else (f"_{getattr(args,'lr_id','')[:8]}" if getattr(args,'lr_id',None) else f"_{args.date}" if args.date else "")
    filename = f"패킹리스트{suffix}_{stamp}.pdf"

    buf = BytesIO()
    n = generate_packing_list(records, buf)
    pdf_bytes = buf.getvalue()

    upload_field = getattr(args, "upload_field", None)
    if upload_field and len(records) == 1:
        print(f"\n▶ {filename} 업로드 중…")
        clear_attachment_field(records[0]["rec_id"], upload_field)
        upload_via_content_api(records[0]["rec_id"], upload_field, filename, pdf_bytes)
    else:
        from pathlib import Path
        out = Path(os.getenv("PDF_OUTPUT_DIR", r"C:\Users\yjisu\Desktop")) / filename
        out.write_bytes(pdf_bytes)
        print(f"\n✅ 완료 — {n}건 저장: {out}")


if __name__ == "__main__":
    main()
