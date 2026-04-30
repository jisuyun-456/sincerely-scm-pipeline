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


_BOX_ROW = re.compile(r"^(\d+)(\+\S+)?\s*\*\s*(\d+)\s+(.+?)\s*$")


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
        line = line.strip()
        if not line:
            continue
        m = _BOX_ROW.match(line)
        if m and current_item:
            qty_str = m.group(1) + (m.group(2) or "")
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
            "box_sum":        f.get("외박스 수량", ""),
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
    W = PW
    M = MARGIN
    y = PH - M   # 현재 y 위치 (위에서 아래로 진행)

    def ln(h=5*mm):
        nonlocal y
        y -= h

    # ── 타이틀 헤더 ─────────────────────────────────────────────────────────
    c.setFillColor(DARK)
    c.rect(M, y - 18*mm, W - 2*M, 18*mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont(font_bold, 20)
    c.drawString(M + 5*mm, y - 13*mm, "PACKING LIST")
    c.setFont(font, 9)
    c.drawRightString(W - M - 5*mm, y - 8*mm, f"Date: {rec['date']}")
    c.drawRightString(W - M - 5*mm, y - 13*mm, f"Ref No.: {rec['to_num']}")
    y -= 18*mm
    ln(4*mm)

    # ── 발송인 / 수취인 2단 ──────────────────────────────────────────────────
    COL = (W - 2*M) / 2 - 3*mm
    BLOCK_H = 30*mm
    # 발송인 블록
    c.setFillColor(LIGHT)
    c.setStrokeColor(LGRAY)
    c.setLineWidth(0.5)
    c.rect(M, y - BLOCK_H, COL, BLOCK_H, fill=1, stroke=1)
    c.setFillColor(MID)
    c.setFont(font_bold, 8)
    c.drawString(M + 3*mm, y - 5*mm, "FROM (SHIPPER)")
    c.setFillColor(colors.HexColor("#222222"))
    c.setFont(font_bold, 9)
    c.drawString(M + 3*mm, y - 10*mm, "SINCERELY Co., Ltd.")
    c.setFont(font, 8.5)
    shipper_addr = rec["shipper_addr"] or "서울시 성동구 왕십리로88 노벨빌딩 4층"
    c.drawString(M + 3*mm, y - 15*mm, shipper_addr[:30])
    if len(shipper_addr) > 30:
        c.drawString(M + 3*mm, y - 20*mm, shipper_addr[30:60])
    if rec["shipper_name"]:
        c.drawString(M + 3*mm, y - 25*mm, f"담당: {rec['shipper_name']}")
    if rec["shipper_tel"]:
        c.drawString(M + 3*mm, y - 29*mm, f"Tel: {rec['shipper_tel']}")

    # 수취인 블록
    rx = M + COL + 6*mm
    c.setFillColor(LIGHT)
    c.rect(rx, y - BLOCK_H, COL, BLOCK_H, fill=1, stroke=1)
    c.setFillColor(MID)
    c.setFont(font_bold, 8)
    c.drawString(rx + 3*mm, y - 5*mm, "TO (CONSIGNEE)")
    company_short = rec["company"].split("-", 1)[-1] if "-" in rec["company"] else rec["company"]
    c.setFillColor(colors.HexColor("#222222"))
    c.setFont(font_bold, 9)
    c.drawString(rx + 3*mm, y - 10*mm, company_short or rec["consignee_name"])
    c.setFont(font, 8.5)
    addr = rec["consignee_addr"] or ""
    c.drawString(rx + 3*mm, y - 15*mm, addr[:30])
    if len(addr) > 30:
        c.drawString(rx + 3*mm, y - 20*mm, addr[30:60])
    if rec["consignee_name"]:
        c.drawString(rx + 3*mm, y - 25*mm, f"담당: {rec['consignee_name']}")
    if rec["consignee_tel"]:
        c.drawString(rx + 3*mm, y - 29*mm, f"Tel: {rec['consignee_tel']}")
    y -= BLOCK_H
    ln(4*mm)

    # ── 참조 정보 라인 ─────────────────────────────────────────────────────
    c.setFillColor(colors.HexColor("#F8F8F8"))
    c.setStrokeColor(LGRAY)
    c.rect(M, y - 8*mm, W - 2*M, 8*mm, fill=1, stroke=1)
    c.setFillColor(DARK)
    c.setFont(font_bold, 9)
    c.drawString(M + 3*mm, y - 5*mm, f"PROJECT REF.:  {rec['company']}")
    c.drawRightString(W - M - 3*mm, y - 5*mm, f"TOTAL: {rec['box_sum']}")
    y -= 8*mm
    ln(4*mm)

    # ── 아이템 테이블 ────────────────────────────────────────────────────────
    TBL_W = W - 2*M

    # 헤더 행
    HDR = ["BOX No.", "DESCRIPTION OF GOODS", "QTY / UNIT", "SIZE", "REMARKS"]
    col_w = [20*mm, TBL_W - 20*mm - 22*mm - 18*mm - 25*mm, 22*mm, 18*mm, 25*mm]
    data = [HDR]

    for grp in rec["groups"]:
        box_label = (f"{grp['box_start']} ~ {grp['box_end']}"
                     if grp["box_start"] != grp["box_end"]
                     else str(grp["box_start"]))
        qty_str = _format_qty(grp["qty"])
        desc = grp["item"]
        row = [box_label, desc, f"{qty_str} EA", f"{grp['size']}형", ""]
        data.append(row)

        # 잔여분 서브 행
        for rem in grp.get("remainder_items", []):
            data.append(["", f"  └ {rem['name']}", f"{rem['qty']} EA", "", ""])

    tbl = Table(data, colWidths=col_w, repeatRows=1)
    tbl_style = TableStyle([
        # 헤더
        ("BACKGROUND",  (0, 0), (-1, 0), DARK),
        ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
        ("FONTNAME",    (0, 0), (-1, 0), font_bold),
        ("FONTSIZE",    (0, 0), (-1, 0), 8),
        ("ALIGN",       (0, 0), (-1, 0), "CENTER"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        # 데이터 행
        ("FONTNAME",    (0, 1), (-1, -1), font),
        ("FONTSIZE",    (0, 1), (-1, -1), 8.5),
        ("ALIGN",       (0, 1), (0, -1), "CENTER"),
        ("ALIGN",       (2, 1), (2, -1), "CENTER"),
        ("ALIGN",       (3, 1), (3, -1), "CENTER"),
        # 교대 배경
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F8FB")]),
        # 그리드
        ("GRID",        (0, 0), (-1, -1), 0.4, LGRAY),
        ("LINEBELOW",   (0, 0), (-1, 0), 1.0, DARK),
        # 잔여분 서브 행 들여쓰기 색상
        ("TEXTCOLOR",   (1, 1), (1, -1), colors.HexColor("#444444")),
        # 패딩
        ("TOPPADDING",  (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (1, 0), (1, -1), 4),
    ])
    tbl.setStyle(tbl_style)

    tbl_h = tbl.wrap(TBL_W, PH)[1]
    tbl.drawOn(c, M, y - tbl_h)
    y -= tbl_h
    ln(6*mm)

    # ── 합계 / 서명 ─────────────────────────────────────────────────────────
    c.setFillColor(colors.HexColor("#F4F8FB"))
    c.setStrokeColor(LGRAY)
    c.rect(M, y - 10*mm, W - 2*M, 10*mm, fill=1, stroke=1)
    c.setFillColor(DARK)
    c.setFont(font_bold, 9)
    c.drawString(M + 3*mm, y - 6.5*mm,
                 f"TOTAL CARTONS: {rec['boxes'][0]['total_boxes']}  CTN")
    c.setFont(font, 8.5)
    c.drawRightString(W - M - 3*mm, y - 6.5*mm, f"ORIGIN: KOREA")
    y -= 10*mm
    ln(8*mm)

    # 서명란
    sig_w = (W - 2*M) / 2 - 5*mm
    for label, xpos in [("Prepared by:", M), ("Approved by:", M + sig_w + 10*mm)]:
        c.setFont(font, 8)
        c.setFillColor(colors.HexColor("#888888"))
        c.drawString(xpos, y - 3*mm, label)
        c.setStrokeColor(LGRAY)
        c.line(xpos, y - 12*mm, xpos + sig_w, y - 12*mm)
        if label == "Prepared by:":
            c.setFont(font, 8.5)
            c.setFillColor(colors.HexColor("#444444"))
            name = rec["shipper_name"] or "SINCERELY"
            c.drawString(xpos, y - 11*mm, name)
    y -= 14*mm

    # ── 하단 페이지 번호 ─────────────────────────────────────────────────────
    c.setFillColor(colors.HexColor("#AAAAAA"))
    c.setFont(font, 7.5)
    c.drawCentredString(W / 2, M / 2, f"SINCERELY Co., Ltd.  ·  Packing List  ·  {rec['to_num']}")


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
        upload_via_content_api(records[0]["rec_id"], upload_field, filename, pdf_bytes)
    else:
        from pathlib import Path
        out = Path(os.getenv("PDF_OUTPUT_DIR", r"C:\Users\yjisu\Desktop")) / filename
        out.write_bytes(pdf_bytes)
        print(f"\n✅ 완료 — {n}건 저장: {out}")


if __name__ == "__main__":
    main()
