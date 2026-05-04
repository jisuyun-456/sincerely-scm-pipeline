"""
inbound_label.py
────────────────────────────────────────────────────────────────────────────
movement 테이블 → 입고 라벨 PDF (80×55mm)

사용법:
  python scripts/inbound_label.py --record-id recXXXXXX
  python scripts/inbound_label.py --record-id recXXXXXX --upload-field fldXXX
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

BASE_ID  = os.getenv("SERPA_BASE_ID", "appkRWtF2j99XgBTq")
TBL_MOV  = "tblsG3x3gCSZGPVB9"
PAT      = (os.getenv("AIRTABLE_SERPA_PAT") or os.getenv("AIRTABLE_WMS_PAT")
            or os.getenv("AIRTABLE_PAT") or os.getenv("AIRTABLE_API_KEY", ""))
HEADERS  = {"Authorization": f"Bearer {PAT}"}

LABEL_W  = 80 * mm
LABEL_H  = 55 * mm

DEFAULT_UPLOAD_FLD = "fld9Kw9WXR20RGs9G"  # 입고라벨지

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


def _parse_label_field(raw: str) -> tuple[str, str]:
    """
    "PT4592-배경지 || PNA51446_라이트 샤오미펜"
    → (pna="PNA51446", proj_name="라이트 샤오미펜")
    """
    raw = str(raw or "").strip()
    parts = raw.split(" || ")
    if len(parts) >= 2:
        second = parts[1].strip()
        m = re.match(r"(PNA\d+)_(.*)", second)
        if m:
            return m.group(1), m.group(2).strip()
    return "", raw


# ── 데이터 조회 ───────────────────────────────────────────────────────────────

def fetch_record(record_id: str) -> dict:
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_MOV}/{record_id}"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    f = r.json().get("fields", {})

    label_raw = f.get("품목명(라벨출력용)", "")
    if isinstance(label_raw, list):
        label_raw = label_raw[0] if label_raw else ""
    label_raw = str(label_raw).strip()
    pna, proj_name = _parse_label_field(label_raw)

    proj_code = f.get("프로젝트코드", [])
    if isinstance(proj_code, list) and proj_code and proj_code[0]:
        pna = proj_code[0]

    mm_id = str(f.get("movement_id", "") or "—")

    pack_raw = f.get("입고물품_단위", [])
    if isinstance(pack_raw, list):
        pack_unit = next((str(v) for v in pack_raw if v not in (None, "")), "—")
    else:
        pack_unit = str(pack_raw) if pack_raw else "—"

    qty     = f.get("입고수량") or f.get("입하수량") or 0
    box_qty = f.get("입고박스수량", "") or "—"

    return {
        "rec_id":    record_id,
        "pna":       pna or "—",
        "proj_name": proj_name,
        "mm_id":     mm_id,
        "item_raw":  label_raw,
        "pack_unit": pack_unit,
        "qty":       qty,
        "box_qty":   str(box_qty),
    }


# ── PDF 드로잉 ────────────────────────────────────────────────────────────────

def _split_name(name: str, font: str, font_size: float, max_w: float) -> list[str]:
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


def _draw_header(c, font, font_bold, project: str):
    W, H  = LABEL_W, LABEL_H
    PAD   = 3.5 * mm
    NAVY  = colors.HexColor("#0b2747")
    TINT  = colors.HexColor("#eef3fa")
    LINE  = colors.HexColor("#d8d9dd")
    HDR_H = 10 * mm
    HDR_Y = H - HDR_H
    PRJ_H = 8 * mm
    PRJ_Y = HDR_Y - PRJ_H

    c.setFillColor(NAVY)
    c.rect(0, HDR_Y, W, HDR_H, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont(font_bold, 7.5)
    c.drawString(PAD, HDR_Y + 3.5 * mm, "■  INBOUND")
    c.setFont(font_bold, 8)
    c.drawRightString(W - PAD, HDR_Y + 3.5 * mm, "SINCERELY")

    c.setFillColor(TINT)
    c.rect(0, PRJ_Y, W, PRJ_H, fill=1, stroke=0)
    c.setStrokeColor(LINE); c.setLineWidth(0.6)
    c.line(0, PRJ_Y, W, PRJ_Y)
    c.setFont(font_bold, 7); c.setFillColor(NAVY)
    c.drawString(PAD, PRJ_Y + 2.5 * mm, (project or "—")[:32])

    return PRJ_Y


def draw_label_page(c, font, font_bold, data: dict):
    W, H   = LABEL_W, LABEL_H
    PAD    = 3.5 * mm
    INK    = colors.HexColor("#0f0f10")
    INK2   = colors.HexColor("#3a3a3d")
    LINE   = colors.HexColor("#d8d9dd")
    FS     = 7.0
    LINE_H = FS * 1.35 * (25.4 / 72) * mm
    V_PAD  = 1.3 * mm
    ASCENT = FS * 0.72 * (25.4 / 72) * mm
    TEXT_MAX_W = W - PAD * 2

    header_proj = f"{data['pna']}-{data['proj_name']}" if data["proj_name"] else data["pna"]
    PROJ_Y = _draw_header(c, font, font_bold, header_proj)
    cur_y  = PROJ_Y - 0.5 * mm

    rows = [
        ("MM번호",   data["mm_id"]),
        ("품목명",   data["item_raw"] or "—"),
        ("패킹단위", data["pack_unit"]),
        ("입고수량", str(int(data["qty"])) if data["qty"] else "—"),
    ]

    for i, (lbl, val) in enumerate(rows):
        lbl_str = lbl + " : "
        lbl_w   = pdfmetrics.stringWidth(lbl_str, font_bold, FS)
        val_max = max(TEXT_MAX_W - lbl_w, 10 * mm)
        val_lines = _split_name(val, font, FS, val_max)
        row_h = max(3.0 * mm, len(val_lines) * LINE_H + V_PAD * 2)

        ry = cur_y - row_h
        bg = colors.white if i % 2 == 0 else colors.HexColor("#f6f8fb")
        c.setFillColor(bg)
        c.rect(0, ry, W, row_h, fill=1, stroke=0)
        c.setStrokeColor(LINE); c.setLineWidth(0.4)
        c.line(0, ry, W, ry)

        text_y0 = ry + row_h - V_PAD - ASCENT
        c.setFont(font_bold, FS); c.setFillColor(INK2)
        c.drawString(PAD, text_y0, lbl_str)
        c.setFont(font, FS); c.setFillColor(INK)
        for j, ln in enumerate(val_lines):
            c.drawString(PAD + lbl_w, text_y0 - j * LINE_H, ln)

        cur_y = ry

    c.setStrokeColor(colors.HexColor("#333333")); c.setLineWidth(1.0)
    c.rect(0, 0, W, H, stroke=1, fill=0)


def generate_pdf(rec: dict, output) -> None:
    font, font_bold = register_fonts()
    c = rl_canvas.Canvas(output, pagesize=(LABEL_W, LABEL_H))
    draw_label_page(c, font, font_bold, rec)
    c.save()


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="입고 라벨 PDF 생성기")
    parser.add_argument("--record-id",    required=True, help="movement record ID")
    parser.add_argument("--upload-field", default=DEFAULT_UPLOAD_FLD,
                        help="업로드할 Airtable 필드 ID")
    args = parser.parse_args()

    if not PAT:
        print("[ERROR] AIRTABLE_SERPA_PAT 환경변수를 설정하세요")
        sys.exit(1)

    print(f"▶ 조회: {args.record_id}")
    rec = fetch_record(args.record_id)
    print(f"  {rec['pna']}-{rec['proj_name']}  MM: {rec['mm_id']}  수량: {rec['qty']}")

    buf = BytesIO()
    generate_pdf(rec, buf)
    pdf_bytes = buf.getvalue()

    fname = f"입고라벨_{rec['pna'] or args.record_id}.pdf"
    upload_pdf(rec["rec_id"], args.upload_field, fname, pdf_bytes)
    print("✅ 완료")


if __name__ == "__main__":
    main()
