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
        name = part.split(" || ")[0].strip().lstrip(";").strip()
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
    PROJ_H = 12 * mm
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

    # 프로젝트명: 9pt bold, 2줄 지원, 수직 중앙 정렬
    FS_P     = 9
    ASCENT_P = FS_P * 0.72 * (25.4 / 72) * mm
    LH_P     = FS_P * 1.35 * (25.4 / 72) * mm
    proj_lines = _split_name(project or "—", font_bold, FS_P, W - PAD * 2)[:2]
    total_h  = len(proj_lines) * LH_P
    y0 = PROJ_Y + (PROJ_H + total_h) / 2 - ASCENT_P
    c.setFont(font_bold, FS_P); c.setFillColor(NAVY)
    for idx, ln in enumerate(proj_lines):
        c.drawString(PAD, y0 - idx * LH_P, ln)

    return PROJ_Y   # 아이템 시작 Y


def _split_name(name: str, font: str, font_size: float, max_w: float) -> list[str]:
    """max_w 너비를 초과하지 않도록 문자 단위로 줄 분리"""
    lines, cur = [], ""
    for ch in name:
        if pdfmetrics.stringWidth(cur + ch, font, font_size) <= max_w:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines or [""]


def draw_label_page(c, font, font_bold, project: str, pairs: list[tuple],
                    font_size: float = 7.5):
    """80×55mm 1장 그리기. pairs = [(name, qty), ...]"""
    W, H   = LABEL_W, LABEL_H
    PAD    = 3.5 * mm
    INK    = colors.HexColor("#0f0f10")
    INK2   = colors.HexColor("#3a3a3d")
    LINE   = colors.HexColor("#d8d9dd")
    QTY_W  = 16 * mm
    FS     = font_size                 # pt — 기본 7.5, fit-page 모드에서 자동 축소
    LINE_H = FS * 1.35 * (25.4 / 72) * mm   # ≈ 3.6mm / 줄
    V_PAD  = 1.5 * mm                 # 행 상하 여백
    ASCENT = FS * 0.72 * (25.4 / 72) * mm   # baseline 위 높이 ≈ 1.9mm
    TEXT_W = W - QTY_W - PAD - 1.5 * mm    # 품목명 가용 너비

    PROJ_Y = _draw_header(c, font, font_bold, project)
    cur_y  = PROJ_Y - 0.5 * mm        # 첫 행 상단 — 프로젝트 바 바로 아래

    for i, (name, qty) in enumerate(pairs):
        lines = _split_name(name, font, FS, TEXT_W)
        row_h = max(3.0 * mm, len(lines) * LINE_H + V_PAD * 2)

        ry = cur_y - row_h
        bg = colors.white if i % 2 == 0 else colors.HexColor("#f6f8fb")
        c.setFillColor(bg)
        c.rect(0, ry, W, row_h, fill=1, stroke=0)
        c.setStrokeColor(LINE); c.setLineWidth(0.4)
        c.line(0, ry, W, ry)
        c.line(W - QTY_W, ry, W - QTY_W, ry + row_h)

        # 품목명: 행 상단에서 V_PAD 아래부터 아래로 출력
        text_y0 = ry + row_h - V_PAD - ASCENT
        for j, ln in enumerate(lines):
            c.setFont(font, FS)
            c.setFillColor(INK)
            c.drawString(PAD, text_y0 - j * LINE_H, ln)

        # 수량: 행 수직 중앙
        qty_y = ry + row_h / 2 - ASCENT / 2
        c.setFont(font_bold, FS)
        c.setFillColor(INK2)
        c.drawCentredString(W - QTY_W / 2, qty_y, str(qty))

        cur_y = ry

    c.setStrokeColor(colors.HexColor("#333333")); c.setLineWidth(1.0)
    c.rect(0, 0, W, H, stroke=1, fill=0)


def generate_pdf(rec: dict, output, fit_page: bool = False) -> int:
    font, font_bold = register_fonts()
    c = rl_canvas.Canvas(output, pagesize=(LABEL_W, LABEL_H))

    items = rec["items"]
    qtys  = rec["qtys"]
    pairs = [(items[i], qtys[i] if i < len(qtys) else "") for i in range(len(items))]
    project = rec["project"]

    # 상수 (draw_label_page와 동기; PROJ_H=12mm 반영)
    QTY_W  = 16 * mm
    PAD    = 3.5 * mm
    BODY_H = LABEL_H - 10 * mm - 12 * mm - 1 * mm  # ≈ 32mm

    def _row_h(name: str, fs: float) -> float:
        lh = fs * 1.35 * (25.4 / 72) * mm
        tw = LABEL_W - QTY_W - PAD - 1.5 * mm
        return max(3.0 * mm, len(_split_name(name, font, fs, tw)) * lh + 1.5 * mm * 2)

    if fit_page:
        # Option 1: 폰트를 7.5→4.5pt까지 줄여 단일 페이지에 맞춤
        fs_used = 4.5
        for fs_10 in range(75, 44, -5):
            fs = fs_10 / 10
            if sum(_row_h(n, fs) for n, _ in pairs) <= BODY_H:
                fs_used = fs
                break
        draw_label_page(c, font, font_bold, project, pairs, font_size=fs_used)
        n_pages = 1
    else:
        # Option 2 (기본): 실제 행 높이 기반 멀티 페이지
        page_list, cur_page, cur_h = [], [], 0.0
        for pair in pairs:
            rh = _row_h(pair[0], 7.5)
            if cur_page and cur_h + rh > BODY_H:
                page_list.append(cur_page)
                cur_page, cur_h = [pair], rh
            else:
                cur_page.append(pair)
                cur_h += rh
        if cur_page:
            page_list.append(cur_page)
        if not page_list:
            page_list = [[]]

        for pi, page_pairs in enumerate(page_list):
            if pi > 0:
                c.showPage()
            draw_label_page(c, font, font_bold, project, page_pairs)
        n_pages = len(page_list)

    c.save()
    return n_pages


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="투입자재 피킹 라벨 PDF 생성기")
    parser.add_argument("--record-id",    required=True, help="pkg_schedule record ID")
    parser.add_argument("--upload-field", default=DEFAULT_UPLOAD_FLD,
                        help="업로드할 Airtable 필드 ID")
    parser.add_argument("--fit-page", action="store_true",
                        help="폰트 축소로 단일 페이지에 전체 항목 맞춤 (Option 1)")
    args = parser.parse_args()

    if not PAT:
        print("[ERROR] AIRTABLE_SERPA_PAT 환경변수를 설정하세요")
        sys.exit(1)

    print(f"▶ 조회: {args.record_id}")
    rec = fetch_record(args.record_id)
    print(f"  프로젝트: {rec['project']}")
    print(f"  품목 {len(rec['items'])}개")

    buf = BytesIO()
    pages = generate_pdf(rec, buf, fit_page=args.fit_page)
    pdf_bytes = buf.getvalue()

    fname = f"투입자재_{rec['project'] or args.record_id}.pdf"
    upload_pdf(rec["rec_id"], args.upload_field, fname, pdf_bytes)
    print(f"✅ 완료 ({pages}페이지)")


if __name__ == "__main__":
    main()
