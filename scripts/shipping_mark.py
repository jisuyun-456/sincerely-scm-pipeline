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


def clear_attachment_field(record_id: str, field_id: str) -> None:
    try:
        r = requests.patch(
            f"https://api.airtable.com/v0/{BASE_ID}/{TBL_LR}/{record_id}",
            headers={"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"},
            json={"fields": {field_id: []}},
            timeout=60,
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
        r = requests.get(url, headers=HEADERS, params=p, timeout=60)
        r.raise_for_status()
        data = r.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records


_BOX_ROW         = re.compile(r"^(\d+)(\s*\+\s*[^\s*]+(?:\([^)]*\))*)?\s*\*\s*(\d+)\s*(.+?)\s*$")
_BOX_ROW_INLINE  = re.compile(r"^(.+?)\s+(\d+(?:[+][^\s*]+)?)\s*\*\s*(\d+)\s+([대중소]형?)\s*$")
_BOX_ROW_COMPACT = re.compile(r"^(.+?)(\d+)\s*\*\s*(\d+)\s+(\S+(?:\s*\([^)]*\))?)\s*$")


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
                mc = _BOX_ROW_COMPACT.match(line)
                if mc:
                    current_item = mc.group(1).strip()
                    qty_str = mc.group(2)
                    for _ in range(int(mc.group(3))):
                        box_num += 1
                        boxes.append({
                            "box_num":         box_num,
                            "size":            mc.group(4).strip(),
                            "item":            current_item,
                            "qty":             qty_str,
                            "remainder_items": [],
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
        box_sum = f.get("외박스 수량")
        _m = re.match(r'\d+', str(box_sum or ""))
        if _m and int(_m.group()) != total:
            print(f"  ⚠️ [수량 불일치] {f.get('프로젝트명 (출고)', '')} — "
                  f"외박스 수량 필드={_m.group()}  포장내역 파싱={total}  "
                  f"→ 포장내역 기준으로 생성")
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
    """HTML 기반 Shipping Mark (150×100mm) — SINCERELY 헤더 / CONSIGNEE·REF·CARTON 행 / 푸터"""
    W, H  = MARK_W, MARK_H
    PAD   = 5 * mm
    NAVY  = colors.HexColor("#0b2747")
    INK   = colors.HexColor("#0f0f10")
    INK2  = colors.HexColor("#3a3a3d")
    MUTED = colors.HexColor("#7c7c82")
    LINE2 = colors.HexColor("#eef0f4")

    # ── 헤더 (navy, 15mm) ────────────────────────────────────────────────
    HDR_H = 15 * mm
    HDR_Y = y + H - HDR_H
    c.setFillColor(NAVY)
    c.rect(x, HDR_Y, W, HDR_H, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont(font_bold, 18)
    c.drawCentredString(x + W / 2, HDR_Y + 7 * mm, "SINCERELY")
    c.setFont(font, 7)
    c.setFillColor(colors.HexColor("#9cc0e8"))
    c.drawCentredString(x + W / 2, HDR_Y + 3 * mm, "신시어리  ·  Seoul, Korea")

    # ── 푸터 (12mm, 상단 구분선) ─────────────────────────────────────────
    FTR_H = 12 * mm
    c.setStrokeColor(LINE2); c.setLineWidth(1.1)
    c.line(x, y + FTR_H, x + W, y + FTR_H)
    c.setFont(font, 8); c.setFillColor(INK2)
    c.drawCentredString(x + W / 2, y + 8.5 * mm, f"SIZE  {box['size']}형")
    c.setFont(font_bold, 8.5); c.setFillColor(NAVY)
    c.drawCentredString(x + W / 2, y + 5.5 * mm, "MADE IN KOREA")
    c.setFont(font, 6); c.setFillColor(MUTED)
    c.drawCentredString(x + W / 2, y + 2.5 * mm, f"SHIP DATE  {date_str}")

    # ── 본문 헬퍼 ─────────────────────────────────────────────────────────
    def hsep(ypos: float):
        c.setStrokeColor(LINE2); c.setLineWidth(0.7)
        c.line(x, ypos, x + W, ypos)

    def row_label(label_en: str, label_ko: str, ypos: float):
        c.setFont(font_bold, 6.5); c.setFillColor(NAVY)
        c.drawString(x + PAD, ypos, label_en)
        en_w = c.stringWidth(label_en, font_bold, 6.5)
        c.setFont(font, 6.5); c.setFillColor(MUTED)
        c.drawString(x + PAD + en_w + 2, ypos, "  " + label_ko)

    # ── 행 1: CONSIGNEE / 수취인 ─────────────────────────────────────────
    R1_TOP = HDR_Y - 2.6 * mm
    row_label("CONSIGNEE", "/ 수취인", R1_TOP)
    consignee_label = company.split("-", 1)[-1] if "-" in company else company
    c.setFont(font_bold, 13); c.setFillColor(INK)
    c.drawString(x + PAD, R1_TOP - 7 * mm, (consignee_label or "—")[:24])
    if consignee_addr:
        c.setFont(font, 7.5); c.setFillColor(MUTED)
        c.drawString(x + PAD, R1_TOP - 13 * mm, consignee_addr[:38])
    if consignee_name:
        c.setFont(font_bold, 8.5); c.setFillColor(INK2)
        c.drawString(x + PAD, R1_TOP - 19 * mm, f"담당  {consignee_name}")
    R1_H   = 22 * mm if (consignee_name or consignee_addr) else 15 * mm
    R1_BOT = R1_TOP - R1_H
    hsep(R1_BOT)

    # ── 행 2: SHIPPING REF. / 출고번호 ──────────────────────────────────
    R2_TOP = R1_BOT - 2.6 * mm
    row_label("SHIPPING REF.", "/ 출고번호", R2_TOP)
    c.setFont(font_bold, 13); c.setFillColor(INK)
    c.drawString(x + PAD, R2_TOP - 7 * mm, to_num)
    R2_BOT = R2_TOP - 13 * mm
    hsep(R2_BOT)

    # ── 행 3: CARTON No. / 박스 번호 ────────────────────────────────────
    R3_TOP = R2_BOT - 2.8 * mm
    c.setFont(font_bold, 6.5); c.setFillColor(NAVY)
    c.drawString(x + PAD, R3_TOP, "CARTON NO.")
    c.setFont(font, 6.5); c.setFillColor(MUTED)
    c.drawString(x + PAD, R3_TOP - 4 * mm, "/ 박스 번호")
    c.setFont(font_bold, 32); c.setFillColor(INK)
    c.drawString(x + PAD, R3_TOP - 17 * mm,
                 f"C/No. {box['box_num']} / {box['total_boxes']}")

    # ── 외곽선 ──────────────────────────────────────────────────────────
    c.setStrokeColor(colors.HexColor("#333333")); c.setLineWidth(1.0)
    c.rect(x, y, W, H, stroke=1, fill=0)


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
        clear_attachment_field(records[0]["rec_id"], upload_field)
        upload_via_content_api(records[0]["rec_id"], upload_field, filename, pdf_bytes)
    else:
        from pathlib import Path
        out = Path(os.getenv("PDF_OUTPUT_DIR", r"C:\Users\yjisu\Desktop")) / filename
        out.write_bytes(pdf_bytes)
        print(f"\n✅ 완료 — {n}장 저장: {out}")


if __name__ == "__main__":
    main()
