"""
shipping_mark.py
────────────────────────────────────────────────────────────────────────────
logistics_release → Shipping Mark PDF (150mm × 100mm, 가로)

박스 1개당 1장 쉬핑마크 라벨. 각 카톤 측면에 부착.

사용법:
  python scripts/shipping_mark.py --to-num TO00016012
  python scripts/shipping_mark.py --lr-id recXXXXXX
  python scripts/shipping_mark.py --date 2026-04-30
"""

import argparse, os, platform, re, sys, time
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

BASE_ID     = os.getenv("SERPA_BASE_ID", "appkRWtF2j99XgBTq")
TBL_LR      = os.getenv("SERPA_LR_TABLE_ID", "tblj53ZBaJBpScNNI")
PROJECT_TBL = os.getenv("SERPA_PROJECT_TABLE_ID", "tblcw5sagkDlgAtJN")
PAT = (os.getenv("AIRTABLE_SERPA_PAT")
       or os.getenv("AIRTABLE_WMS_PAT")
       or os.getenv("AIRTABLE_PAT")
       or os.getenv("AIRTABLE_API_KEY", ""))
HEADERS = {"Authorization": f"Bearer {PAT}"}

MARK_W = 150 * mm
MARK_H = 100 * mm

DARK   = colors.HexColor("#1A3A5C")
MID    = colors.HexColor("#2B5380")
LIGHT  = colors.HexColor("#E8F0F7")
LGRAY  = colors.HexColor("#CCCCCC")
ACCENT = colors.HexColor("#1E6091")

if platform.system() == "Windows":
    FONT_REG = r"C:\Windows\Fonts\malgun.ttf"
    FONT_BLD = r"C:\Windows\Fonts\malgunbd.ttf"
else:
    FONT_REG = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
    FONT_BLD = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"


# ────────────────────────────────────────────────────────────────────────────
# 공통 유틸
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
    "수령인(성함)", "수령인(주소)",
]


def fetch_records(lr_id=None, to_num=None, date_str=None) -> list:
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
            "consignee_name": f.get("수령인(성함)", ""),
            "consignee_addr": f.get("수령인(주소)", ""),
            "boxes":          boxes,
        })
    return result


# ────────────────────────────────────────────────────────────────────────────
# 쉬핑마크 1장 그리기 (150mm × 100mm, 가로)
# ────────────────────────────────────────────────────────────────────────────
def draw_shipping_mark(c: rl_canvas.Canvas, x: float, y: float,
                       box: dict, to_num: str, date_str: str,
                       company: str, consignee_name: str, consignee_addr: str,
                       font: str, font_bold: str):
    W, H = MARK_W, MARK_H
    PAD  = 5 * mm

    # 외곽 테두리 (2중 선)
    c.setStrokeColor(DARK)
    c.setLineWidth(2.0)
    c.rect(x, y, W, H)
    c.setLineWidth(0.5)
    c.setStrokeColor(colors.HexColor("#6699BB"))
    c.rect(x + 2*mm, y + 2*mm, W - 4*mm, H - 4*mm)

    cy = y + H   # 현재 그리기 위치 (위에서 아래)

    # ── 1. 발송인 (SHIPPER) 블록 (15mm) ─────────────────────────────────────
    BLK1_H = 15 * mm
    c.setFillColor(DARK)
    c.rect(x, cy - BLK1_H, W, BLK1_H, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont(font_bold, 13)
    c.drawCentredString(x + W/2, cy - 7*mm, "SINCERELY")
    c.setFont(font, 7)
    c.drawCentredString(x + W/2, cy - 12*mm, "신시어리 ·  Seoul, Korea")
    cy -= BLK1_H

    # 구분선
    c.setStrokeColor(DARK)
    c.setLineWidth(1.0)
    c.line(x, cy, x + W, cy)

    # ── 2. 수취인 (CONSIGNEE) 블록 (25mm) ───────────────────────────────────
    BLK2_H = 25 * mm
    c.setFillColor(LIGHT)
    c.rect(x, cy - BLK2_H, W, BLK2_H, fill=1, stroke=0)
    c.setFillColor(MID)
    c.setFont(font_bold, 7)
    c.drawString(x + PAD, cy - 5*mm, "CONSIGNEE / 수취인")
    consignee_label = company.split("-", 1)[-1] if "-" in company else company
    c.setFillColor(colors.HexColor("#111111"))
    c.setFont(font_bold, 11)
    if consignee_label:
        c.drawString(x + PAD, cy - 11*mm, consignee_label[:28])
    c.setFont(font, 8)
    addr = consignee_addr or ""
    # 공백 기준 줄바꿈 (150mm 너비에 맞게 40자씩)
    words = addr.split()
    addr_lines, cur = [], ""
    for w in words:
        if cur and len(cur) + len(w) + 1 > 38:
            addr_lines.append(cur); cur = w
        else:
            cur = (cur + " " + w).strip() if cur else w
    if cur:
        addr_lines.append(cur)
    for i, line in enumerate(addr_lines[:2]):
        c.drawString(x + PAD, cy - (16 + i*4.5)*mm, line)
    if consignee_name:
        c.setFont(font, 7.5)
        c.setFillColor(colors.HexColor("#444444"))
        c.drawString(x + PAD, cy - 23*mm, f"담당: {consignee_name}")
    cy -= BLK2_H

    # 구분선
    c.setStrokeColor(LGRAY)
    c.setLineWidth(0.8)
    c.line(x + PAD, cy, x + W - PAD, cy)
    cy -= 2*mm

    # ── 3. 주문 참조 블록 (14mm) ─────────────────────────────────────────────
    BLK3_H = 14 * mm
    c.setFillColor(colors.HexColor("#F8FBFF"))
    c.rect(x, cy - BLK3_H, W, BLK3_H, fill=1, stroke=0)
    c.setFillColor(MID)
    c.setFont(font_bold, 7)
    c.drawString(x + PAD, cy - 5*mm, "SHIPPING REF. / 출고번호")
    c.setFillColor(colors.HexColor("#111111"))
    c.setFont(font_bold, 11)
    c.drawString(x + PAD, cy - 11*mm, to_num)
    cy -= BLK3_H

    # 구분선
    c.setStrokeColor(LGRAY)
    c.setLineWidth(0.8)
    c.line(x + PAD, cy, x + W - PAD, cy)
    cy -= 2*mm

    # ── 4. 박스 번호 블록 (18mm) ─────────────────────────────────────────────
    BLK4_H = 18 * mm
    c.setFillColor(LIGHT)
    c.rect(x, cy - BLK4_H, W, BLK4_H, fill=1, stroke=0)
    c.setFillColor(MID)
    c.setFont(font_bold, 7)
    c.drawString(x + PAD, cy - 5*mm, "CARTON No. / 박스 번호")
    c.setFillColor(DARK)
    c.setFont(font_bold, 18)
    box_label = f"C/No.  {box['box_num']} / {box['total_boxes']}"
    c.drawCentredString(x + W/2, cy - 14*mm, box_label)
    cy -= BLK4_H

    # 구분선
    c.setStrokeColor(LGRAY)
    c.setLineWidth(0.8)
    c.line(x + PAD, cy, x + W - PAD, cy)
    cy -= 2*mm

    # ── 5. 규격 + 원산지 (나머지 ~22mm) ─────────────────────────────────────
    remaining = cy - (y + 4*mm)
    c.setFillColor(colors.white)
    c.rect(x, y + 4*mm, W, remaining, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#555555"))
    c.setFont(font_bold, 9)
    c.drawCentredString(x + W/2, cy - 6*mm, f"SIZE: {box['size']}형")
    c.setFillColor(DARK)
    c.setFont(font_bold, 10)
    c.drawCentredString(x + W/2, cy - 12*mm, "MADE IN KOREA")
    c.setFont(font, 7.5)
    c.setFillColor(colors.HexColor("#888888"))
    c.drawCentredString(x + W/2, y + 7*mm, f"SHIP DATE: {date_str}")


# ────────────────────────────────────────────────────────────────────────────
# PDF 생성
# ────────────────────────────────────────────────────────────────────────────
def generate_shipping_marks(records: list, output) -> int:
    font, font_bold = register_fonts()
    c = rl_canvas.Canvas(output, pagesize=(MARK_W, MARK_H))
    count = 0
    for rec in records:
        for box in rec["boxes"]:
            draw_shipping_mark(
                c, 0, 0, box, rec["to_num"], rec["date"],
                rec["company"], rec["consignee_name"], rec["consignee_addr"],
                font, font_bold,
            )
            c.showPage()
            count += 1
    c.save()
    return count


def main():
    parser = argparse.ArgumentParser(description="Shipping Mark PDF 생성기")
    parser.add_argument("--lr-id",        help="logistics_release record ID")
    parser.add_argument("--to-num",       help="TO번호")
    parser.add_argument("--date",         help="출고 요청일 필터 (예: 2026-04-30)")
    parser.add_argument("--upload-field", help="업로드할 Airtable 필드 ID")
    args = parser.parse_args()

    if not PAT:
        print("[ERROR] AIRTABLE_SERPA_PAT 환경변수를 설정하세요")
        sys.exit(1)

    print("▶ 데이터 조회 중…")
    records = fetch_records(
        lr_id=getattr(args, "lr_id", None),
        to_num=getattr(args, "to_num", None),
        date_str=args.date,
    )
    if not records:
        print("조회 결과 없음")
        return

    for r in records:
        print(f"  • {r['to_num']}  {r['date']}  {r['company']}  → {len(r['boxes'])}장 쉬핑마크")

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    suffix = f"_{args.to_num}" if args.to_num else (f"_{getattr(args,'lr_id','')[:8]}" if getattr(args,'lr_id',None) else f"_{args.date}" if args.date else "")
    filename = f"쉬핑마크{suffix}_{stamp}.pdf"

    buf = BytesIO()
    n = generate_shipping_marks(records, buf)
    pdf_bytes = buf.getvalue()

    upload_field = getattr(args, "upload_field", None)
    if upload_field and len(records) == 1:
        print(f"\n▶ {filename} 업로드 중…")
        upload_via_content_api(records[0]["rec_id"], upload_field, filename, pdf_bytes)
    else:
        from pathlib import Path
        out = Path(os.getenv("PDF_OUTPUT_DIR", r"C:\Users\yjisu\Desktop")) / filename
        out.write_bytes(pdf_bytes)
        print(f"\n✅ 완료 — {n}장 저장: {out}")


if __name__ == "__main__":
    main()
