"""
pkg_schedule_label.py
────────────────────────────────────────────────────────────────────────────
pkg_schedule 테이블 → 투입자재 피킹 라벨 PDF (80×55mm)

사용법:
  python scripts/pkg_schedule_label.py --record-id recXXXXXX
  python scripts/pkg_schedule_label.py --record-id recXXXXXX --upload-field fldXXX
"""

import argparse, base64, os, platform, re, sys, time
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

BASE_ID   = os.getenv("SERPA_BASE_ID", "appkRWtF2j99XgBTq")
TBL_PKG   = "tblQak5BYnGqKmvAq"
PAT = (os.getenv("AIRTABLE_SERPA_PAT")
       or os.getenv("AIRTABLE_WMS_PAT")
       or os.getenv("AIRTABLE_PAT")
       or os.getenv("AIRTABLE_API_KEY", ""))
HEADERS   = {"Authorization": f"Bearer {PAT}"}

LABEL_W = 80 * mm
LABEL_H = 55 * mm

F_PROJECT = "프로젝트명 (Short ver.)"
F_ITEMS   = "재고 투입자재 (from pkg_task)"
F_QTYS    = "출고수량 (from movement)"
DEFAULT_UPLOAD_FLD = "fldtcblsJJsQYFdWU"   # 투입자재_pdf

if platform.system() == "Windows":
    FONT_REG = r"C:\Windows\Fonts\malgun.ttf"
    FONT_BLD = r"C:\Windows\Fonts\malgunbd.ttf"
else:
    FONT_REG = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
    FONT_BLD = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"


# ── 유틸 ─────────────────────────────────────────────────────────────────────

def register_fonts():
    try:
        pdfmetrics.registerFont(TTFont("Malgun",     FONT_REG))
        pdfmetrics.registerFont(TTFont("MalgunBold", FONT_BLD))
        return "Malgun", "MalgunBold"
    except Exception:
        return "Helvetica", "Helvetica-Bold"


def upload_pdf(record_id: str, field_id: str, filename: str, pdf_bytes: bytes) -> bool:
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


# ── 데이터 파싱 ───────────────────────────────────────────────────────────────

def _parse_items(raw) -> list[str]:
    """'PT4731-사용설명서(전용)_화이트 || 다영기획, PT4730-...; ' → ['PT4731-사용설명서(전용)_화이트', ...]"""
    if not raw:
        return []
    if isinstance(raw, list):
        raw = ", ".join(str(x) for x in raw)
    result = []
    for part in str(raw).rstrip(";").split(","):
        name = part.split(" || ")[0].strip()
        if name:
            result.append(name)
    return result


def _parse_qtys(raw) -> list[str]:
    """'210; 201; 210;' → ['210', '201', '210']"""
    if not raw:
        return []
    if isinstance(raw, (int, float)):
        return [str(int(raw))]
    result = []
    for part in str(raw).rstrip(";").split(";"):
        part = part.strip()
        if part:
            result.append(part)
    return result


def fetch_record(record_id: str) -> dict:
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_PKG}/{record_id}"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    f = r.json().get("fields", {})

    proj_raw  = f.get(F_PROJECT, "")
    project   = (proj_raw[0] if isinstance(proj_raw, list) else proj_raw) or ""
    items     = _parse_items(f.get(F_ITEMS, ""))
    qtys      = _parse_qtys(f.get(F_QTYS, ""))

    return {"rec_id": record_id, "project": str(project), "items": items, "qtys": qtys}


# ── PDF 드로잉 ────────────────────────────────────────────────────────────────

def _draw_header(c, font, font_bold, project: str):
    W, H = LABEL_W, LABEL_H
    PAD  = 3.5 * mm
    NAVY = colors.HexColor("#0b2747")
    TINT = colors.HexColor("#eef3fa")
    LINE = colors.HexColor("#d8d9dd")

    HDR_H  = 10 * mm
    HDR_Y  = H - HDR_H
    PROJ_H = 8 * mm
    PROJ_Y = HDR_Y - PROJ_H

    c.setFillColor(NAVY)
    c.rect(0, HDR_Y, W, HDR_H, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont(font_bold, 7.5)
    c.drawString(PAD, HDR_Y + 3.5 * mm, "■  PICKING SLIP")
    c.setFont(font_bold, 8)
    c.drawRightString(W - PAD, HDR_Y + 3.5 * mm, "SINCERELY")

    c.setFillColor(TINT)
    c.rect(0, PROJ_Y, W, PROJ_H, fill=1, stroke=0)
    c.setStrokeColor(LINE); c.setLineWidth(0.6)
    c.line(0, PROJ_Y, W, PROJ_Y)
    c.setFont(font_bold, 7); c.setFillColor(NAVY)
    c.drawString(PAD, PROJ_Y + 2.5 * mm, (project or "—")[:32])

    return PROJ_Y   # 아이템 시작 Y


def draw_label_page(c, font, font_bold, project: str, pairs: list[tuple]):
    """80×55mm 1장 그리기. pairs = [(name, qty), ...]"""
    W, H = LABEL_W, LABEL_H
    PAD  = 3.5 * mm
    INK  = colors.HexColor("#0f0f10")
    INK2 = colors.HexColor("#3a3a3d")
    LINE = colors.HexColor("#d8d9dd")
    QTY_W = 16 * mm

    PROJ_Y = _draw_header(c, font, font_bold, project)

    BODY_H  = PROJ_Y - 1 * mm
    n       = max(1, len(pairs))
    MIN_ROW = 3.0 * mm
    ROW_H   = max(MIN_ROW, BODY_H / n)
    FS      = max(5.0, min(6.5, ROW_H / mm * 1.35))

    for i, (name, qty) in enumerate(pairs):
        ry = PROJ_Y - 0.5 * mm - ROW_H * (i + 1)
        bg = colors.white if i % 2 == 0 else colors.HexColor("#f6f8fb")
        c.setFillColor(bg)
        c.rect(0, ry, W, ROW_H, fill=1, stroke=0)
        c.setStrokeColor(LINE); c.setLineWidth(0.4)
        c.line(0, ry, W, ry)
        c.line(W - QTY_W, ry, W - QTY_W, ry + ROW_H)

        text_y = ry + ROW_H * 0.25
        c.setFont(font, FS); c.setFillColor(INK)
        c.drawString(PAD, text_y, name[:28])
        c.setFont(font_bold, FS); c.setFillColor(INK2)
        c.drawCentredString(W - QTY_W / 2, text_y, str(qty))

    c.setStrokeColor(colors.HexColor("#333333")); c.setLineWidth(1.0)
    c.rect(0, 0, W, H, stroke=1, fill=0)


def generate_pdf(rec: dict, output) -> int:
    font, font_bold = register_fonts()
    c = rl_canvas.Canvas(output, pagesize=(LABEL_W, LABEL_H))

    items = rec["items"]
    qtys  = rec["qtys"]
    pairs = [(items[i], qtys[i] if i < len(qtys) else "") for i in range(len(items))]
    project = rec["project"]

    # 한 페이지에 들어갈 최대 행 수 계산 (최소 row 3mm 기준)
    BODY_H    = LABEL_H - 10 * mm - 8 * mm - 1 * mm   # ~36mm
    MAX_ROWS  = max(1, int(BODY_H / (3.0 * mm)))       # ~12
    pages     = [pairs[i:i + MAX_ROWS] for i in range(0, max(1, len(pairs)), MAX_ROWS)]

    for pi, page_pairs in enumerate(pages):
        if pi > 0:
            c.showPage()
        draw_label_page(c, font, font_bold, project, page_pairs)

    c.save()
    return len(pages)


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="투입자재 피킹 라벨 PDF 생성기")
    parser.add_argument("--record-id",    required=True, help="pkg_schedule record ID")
    parser.add_argument("--upload-field", default=DEFAULT_UPLOAD_FLD,
                        help="업로드할 Airtable 필드 ID")
    args = parser.parse_args()

    if not PAT:
        print("[ERROR] AIRTABLE_SERPA_PAT 환경변수를 설정하세요")
        sys.exit(1)

    print(f"▶ 조회: {args.record_id}")
    rec = fetch_record(args.record_id)
    print(f"  프로젝트: {rec['project']}")
    print(f"  품목 {len(rec['items'])}개")

    buf = BytesIO()
    pages = generate_pdf(rec, buf)
    pdf_bytes = buf.getvalue()

    fname = f"투입자재_{rec['project'] or args.record_id}.pdf"
    upload_pdf(rec["rec_id"], args.upload_field, fname, pdf_bytes)
    print(f"✅ 완료 ({pages}페이지)")


if __name__ == "__main__":
    main()
