"""
pkg_return_sheet.py
────────────────────────────────────────────────────────────────────────────
pkg_schedule → 임가공 리턴 자재 구분표 PDF (A4)
  · 임가공 프로젝트 / 품목 / 리턴수량 / 재고보관좌표 표시
  · 하단 절취선 이하 → 바스켓 부착용 프로젝트 코드 스트립

사용법:
  python scripts/pkg_return_sheet.py --record-id recXXXXXX
  python scripts/pkg_return_sheet.py --record-id recXXXXXX --upload-field fldXXX
  python scripts/pkg_return_sheet.py --date 2026-05-05
"""

import argparse, base64, os, platform, re, sys, time
from io import BytesIO
from pathlib import Path

import requests
from dotenv import load_dotenv
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

BASE_ID = os.getenv("SERPA_BASE_ID", "appkRWtF2j99XgBTq")
TBL_PKG = "tblQak5BYnGqKmvAq"
PAT = (os.getenv("AIRTABLE_SERPA_PAT")
       or os.getenv("AIRTABLE_WMS_PAT")
       or os.getenv("AIRTABLE_PAT")
       or os.getenv("AIRTABLE_API_KEY", ""))
HEADERS = {"Authorization": f"Bearer {PAT}"}

PW, PH = A4   # 595.3pt × 841.9pt (≈ 210×297mm)

# 필드명 상수
F_PROJECT_NAME = "프로젝트명 (Short ver.)"
F_PNA_CODE     = "프로젝트 코드 (PK) (from project)"
F_ITEMS        = "재고 투입자재 (from pkg_task)"
F_ISSUED_QTY   = "출고수량 (from movement)"
F_RETURN_QTY   = "재고_리턴수량_count"
F_COORD        = "회수보관좌표"
F_DATE         = "임가공 예정일"
F_PLACE        = "임가공 장소"

DEFAULT_UPLOAD_FLD = ""   # pkg_schedule "리턴구분표_pdf" 필드 ID (운영 추가 후 입력)

WEEKDAY_KR = ["월", "화", "수", "목", "금", "토", "일"]

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


def _first(val):
    """lookup/rollup 반환값이 리스트면 첫 번째 원소, 아니면 str 변환"""
    if isinstance(val, list):
        return str(val[0]) if val else ""
    return str(val) if val is not None else ""


def _parse_items(raw) -> list[str]:
    """'PT4731-품목명 || 장소, PT4730-...; ' → ['PT4731-품목명', ...]"""
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
        p = part.strip()
        if p:
            result.append(p)
    return result


def _fit_fontsize(text: str, font: str, max_w: float, init: int = 48, min_: int = 18) -> int:
    fs = init
    while fs > min_ and pdfmetrics.stringWidth(text, font, fs) > max_w:
        fs -= 2
    return fs


def _split_name(name: str, font: str, fs: float, max_w: float) -> list[str]:
    lines, cur = [], ""
    for ch in name:
        if pdfmetrics.stringWidth(cur + ch, font, fs) <= max_w:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines or [""]


def _date_label(date_str: str) -> str:
    """'2026-05-05' → '2026-05-05 (월)'"""
    if not date_str or len(date_str) < 10:
        return date_str or "—"
    try:
        import datetime
        d = datetime.date.fromisoformat(date_str[:10])
        return f"{date_str[:10]} ({WEEKDAY_KR[d.weekday()]})"
    except Exception:
        return date_str[:10]


# ── 데이터 조회 ───────────────────────────────────────────────────────────────

def _record_to_dict(rec_id: str, f: dict) -> dict:
    return {
        "rec_id":      rec_id,
        "project":     _first(f.get(F_PROJECT_NAME, "")),
        "pna_code":    _first(f.get(F_PNA_CODE, "")),
        "items":       _parse_items(f.get(F_ITEMS, "")),
        "issued_qtys": _parse_qtys(f.get(F_ISSUED_QTY, "")),
        "return_qty":  _first(f.get(F_RETURN_QTY, "")),
        "coord":       _first(f.get(F_COORD, "")),
        "date":        _first(f.get(F_DATE, ""))[:10] if f.get(F_DATE) else "",
        "place":       _first(f.get(F_PLACE, "")),
    }


def fetch_record(record_id: str) -> dict:
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_PKG}/{record_id}"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    return _record_to_dict(record_id, data.get("fields", {}))


def fetch_records_by_date(date_str: str) -> list[dict]:
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_PKG}"
    formula = f"IS_SAME({{임가공 예정일}}, '{date_str}', 'day')"
    out, offset = [], None
    while True:
        params: dict = {"filterByFormula": formula, "pageSize": 100}
        if offset:
            params["offset"] = offset
        r = requests.get(url, headers=HEADERS, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        for rec in data.get("records", []):
            out.append(_record_to_dict(rec["id"], rec.get("fields", {})))
        offset = data.get("offset")
        if not offset:
            break
    return out


# ── PDF 드로잉 ────────────────────────────────────────────────────────────────

NAVY  = colors.HexColor("#0b2747")
TINT  = colors.HexColor("#eef3fa")
AMBER = colors.HexColor("#f59e0b")
AMBER_BG = colors.HexColor("#fffbeb")
LINE  = colors.HexColor("#d8d9dd")
INK   = colors.HexColor("#0f0f10")
INK2  = colors.HexColor("#3a3a3d")
GRAY  = colors.HexColor("#6b7280")

PAD = 12 * mm


def _draw_header(c, font_b: str, date_label: str):
    """NAVY 헤더 바 (y: PH-25mm ~ PH)"""
    c.setFillColor(NAVY)
    c.rect(0, PH - 22*mm, PW, 22*mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont(font_b, 16)
    c.drawString(PAD, PH - 14*mm, "■  임가공 리턴 자재 구분표")
    c.setFont(font_b, 10)
    c.drawRightString(PW - PAD, PH - 14*mm, date_label)


def _draw_meta(c, font: str, font_b: str, project: str, pna_code: str, place: str) -> float:
    """프로젝트 정보 박스 → 반환값: 박스 하단 y좌표"""
    top_y  = PH - 22*mm
    box_h  = 20*mm
    bot_y  = top_y - box_h

    c.setFillColor(TINT)
    c.rect(0, bot_y, PW, box_h, fill=1, stroke=0)
    c.setStrokeColor(LINE); c.setLineWidth(0.6)
    c.line(0, bot_y, PW, bot_y)

    # 프로젝트명 (좌)
    c.setFont(font_b, 13); c.setFillColor(NAVY)
    proj_text = (project or "—")[:36]
    c.drawString(PAD, bot_y + 13*mm, proj_text)

    # PNA 코드 (좌, 작게)
    if pna_code:
        c.setFont(font, 9); c.setFillColor(GRAY)
        c.drawString(PAD, bot_y + 6*mm, pna_code[:40])

    # 임가공 장소 (우)
    if place:
        c.setFont(font, 10); c.setFillColor(INK2)
        c.drawRightString(PW - PAD, bot_y + 13*mm, f"임가공: {place}")

    return bot_y


def _draw_coord_box(c, font: str, font_b: str, coord: str, top_y: float) -> float:
    """회수보관좌표 강조 박스 → 반환값: 박스 하단 y"""
    box_h = 18*mm
    bot_y = top_y - box_h

    c.setFillColor(AMBER_BG)
    c.rect(0, bot_y, PW, box_h, fill=1, stroke=0)
    c.setStrokeColor(AMBER); c.setLineWidth(1.2)
    c.rect(0, bot_y, PW, box_h, fill=0, stroke=1)

    c.setFont(font, 8); c.setFillColor(GRAY)
    c.drawString(PAD, bot_y + 13*mm, "▶  회수 보관 좌표")

    coord_text = coord if coord else "—"
    fs = _fit_fontsize(coord_text, font_b, PW - PAD * 4, init=24, min_=12)
    c.setFont(font_b, fs); c.setFillColor(AMBER if coord else GRAY)
    c.drawCentredString(PW / 2, bot_y + 4*mm, coord_text)

    return bot_y


def _draw_table(c, font: str, font_b: str, pairs: list[tuple],
                return_total: str, top_y: float) -> float:
    """자재 테이블 (품목 | 투입수량 | 리턴수량) → 반환값: 테이블 하단 y"""
    # 컬럼 정의 (mm 기준)
    COL_NO   = 10*mm
    COL_ITEM = 116*mm
    COL_ISS  = 25*mm
    COL_RET  = 35*mm
    TABLE_W  = COL_NO + COL_ITEM + COL_ISS + COL_RET

    x0 = PAD
    x1 = x0 + COL_NO
    x2 = x1 + COL_ITEM
    x3 = x2 + COL_ISS
    x4 = x3 + COL_RET

    HDR_H = 8*mm
    ROW_H = 9*mm
    FS    = 9.0
    ASCENT = FS * 0.72 * (25.4 / 72) * mm

    # 헤더 행
    hdr_top = top_y
    hdr_bot = hdr_top - HDR_H
    c.setFillColor(TINT)
    c.rect(x0, hdr_bot, TABLE_W, HDR_H, fill=1, stroke=0)
    c.setStrokeColor(LINE); c.setLineWidth(0.5)
    for x in [x0, x1, x2, x3, x4]:
        c.line(x, hdr_bot, x, hdr_top)
    c.line(x0, hdr_top, x4, hdr_top)
    c.line(x0, hdr_bot, x4, hdr_bot)

    c.setFont(font_b, 8.5); c.setFillColor(NAVY)
    c.drawCentredString(x0 + COL_NO/2,    hdr_bot + 2.5*mm, "#")
    c.drawString(         x1 + 2*mm,       hdr_bot + 2.5*mm, "품목명 (PT코드)")
    c.drawCentredString(x2 + COL_ISS/2,   hdr_bot + 2.5*mm, "투입수량")
    c.drawCentredString(x3 + COL_RET/2,   hdr_bot + 2.5*mm, "리턴수량")

    # 본문 행
    cur_y = hdr_bot
    for i, (name, issued) in enumerate(pairs):
        lines  = _split_name(name, font, FS, COL_ITEM - 4*mm)
        row_h  = max(ROW_H, len(lines) * FS * 1.35 * (25.4/72)*mm + 3*mm)
        ry_top = cur_y
        ry_bot = cur_y - row_h

        bg = colors.white if i % 2 == 0 else colors.HexColor("#f6f8fb")
        c.setFillColor(bg)
        c.rect(x0, ry_bot, TABLE_W, row_h, fill=1, stroke=0)
        c.setStrokeColor(LINE); c.setLineWidth(0.4)
        c.line(x0, ry_bot, x4, ry_bot)
        for x in [x0, x1, x2, x3, x4]:
            c.line(x, ry_bot, x, ry_top)

        text_y0 = ry_top - 3*mm - ASCENT
        c.setFont(font_b, FS); c.setFillColor(NAVY)
        c.drawCentredString(x0 + COL_NO/2, ry_bot + row_h/2 - ASCENT/2, str(i + 1))

        c.setFont(font, FS); c.setFillColor(INK)
        for j, ln in enumerate(lines):
            c.drawString(x1 + 2*mm, text_y0 - j * FS * 1.35 * (25.4/72)*mm, ln)

        mid_y = ry_bot + row_h/2 - ASCENT/2
        c.setFont(font_b, FS); c.setFillColor(INK2)
        c.drawCentredString(x2 + COL_ISS/2, mid_y, str(issued) if issued else "—")

        # 리턴수량: 마지막 행에만 총계 표시 (나머지는 빈칸)
        if i == len(pairs) - 1 and return_total:
            c.setFillColor(AMBER)
            c.drawCentredString(x3 + COL_RET/2, mid_y, f"합계: {return_total}")
        # else: 빈칸 (수기 기입용)

        cur_y = ry_bot

    # 테이블 외곽선
    c.setStrokeColor(NAVY); c.setLineWidth(0.8)
    c.rect(x0, cur_y, TABLE_W, hdr_top - cur_y, fill=0, stroke=1)

    return cur_y


def _draw_footer(c, font: str, font_b: str, bot_y: float):
    """담당자/확인일/서명란"""
    y = bot_y - 14*mm
    c.setFont(font, 9); c.setFillColor(INK2)
    labels = [("담당자", PAD), ("확인일", PW/2 - 30*mm), ("서명", PW - PAD - 60*mm)]
    for label, lx in labels:
        c.drawString(lx, y + 2*mm, f"{label}: ")
        uw = 50*mm if label != "서명" else 40*mm
        tx = lx + pdfmetrics.stringWidth(f"{label}: ", font, 9) + 2*mm
        c.setStrokeColor(INK2); c.setLineWidth(0.5)
        c.line(tx, y, tx + uw, y)


def _draw_cut_line(c, font: str, y: float):
    """절취선"""
    c.setDash(3, 3); c.setStrokeColor(GRAY); c.setLineWidth(0.6)
    c.line(8*mm, y, PW - 8*mm, y)
    c.setDash()
    c.setFont(font, 7.5); c.setFillColor(GRAY)
    c.drawCentredString(PW / 2, y - 3.5*mm, "✂  점선 이하를 절취하여 자재 바스켓에 부착하세요")


def _draw_basket_strip(c, font: str, font_b: str,
                       project: str, pna_code: str,
                       coord: str, date_label: str, place: str,
                       strip_top: float):
    """바스켓 부착용 스트립"""
    strip_bot = 8*mm
    strip_h   = strip_top - strip_bot

    # 외곽 테두리
    c.setStrokeColor(NAVY); c.setLineWidth(2)
    c.roundRect(8*mm, strip_bot, PW - 16*mm, strip_h, 4*mm, fill=0, stroke=1)

    # RETURN BASKET 소제목
    c.setFont(font_b, 8); c.setFillColor(GRAY)
    c.drawCentredString(PW / 2, strip_top - 7*mm, "RETURN BASKET")

    # 프로젝트명 (대형)
    proj_text = project or pna_code or "—"
    fs_proj = _fit_fontsize(proj_text, font_b, PW - 32*mm, init=40, min_=16)
    c.setFont(font_b, fs_proj); c.setFillColor(NAVY)
    c.drawCentredString(PW / 2, strip_bot + strip_h/2 - fs_proj * (25.4/72)*mm / 2 + 4*mm, proj_text)

    # 보관 좌표 (AMBER 강조)
    if coord:
        fs_coord = _fit_fontsize(f"보관좌표: {coord}", font_b, PW - 40*mm, init=20, min_=10)
        c.setFont(font_b, fs_coord); c.setFillColor(AMBER)
        c.drawCentredString(PW / 2, strip_bot + 14*mm, f"보관좌표: {coord}")

    # 하단 메타
    c.setFont(font, 8); c.setFillColor(GRAY)
    meta = f"임가공일: {date_label}  |  장소: {place or '—'}"
    c.drawCentredString(PW / 2, strip_bot + 6*mm, meta)


# ── PDF 생성 ─────────────────────────────────────────────────────────────────

def generate_pdf(rec: dict, output) -> int:
    font, font_b = register_fonts()
    c = rl_canvas.Canvas(output, pagesize=A4)

    items      = rec["items"]
    issued_qs  = rec["issued_qtys"]
    pairs      = [(items[i], issued_qs[i] if i < len(issued_qs) else "") for i in range(len(items))]
    project    = rec["project"]
    pna_code   = rec["pna_code"]
    coord      = rec["coord"]
    return_qty = rec["return_qty"]
    date_lbl   = _date_label(rec["date"])
    place      = rec["place"]

    # 자재가 없으면 빈 행 1개 삽입
    if not pairs:
        pairs = [("(자재 없음)", "")]

    STRIP_TOP    = 68*mm    # 절취선 위치
    FOOTER_BOT   = STRIP_TOP + 18*mm
    TABLE_TOP    = PH - 22*mm - 20*mm - 18*mm   # header + meta + coord 아래

    # 한 페이지 최대 행 수
    ROW_H  = 9*mm
    BODY_H = TABLE_TOP - FOOTER_BOT - 8*mm - 18*mm  # 테이블 헤더 포함
    MAX_ROWS = max(1, int(BODY_H / ROW_H))
    pages = [pairs[i:i + MAX_ROWS] for i in range(0, max(1, len(pairs)), MAX_ROWS)]

    for pi, page_pairs in enumerate(pages):
        if pi > 0:
            c.showPage()

        is_last = (pi == len(pages) - 1)

        _draw_header(c, font_b, date_lbl)
        meta_bot = _draw_meta(c, font, font_b, project, pna_code, place)
        coord_bot = _draw_coord_box(c, font, font_b, coord, meta_bot)

        # 다페이지 시 coord 박스는 첫 페이지만
        actual_table_top = coord_bot if pi == 0 else (PH - 22*mm - 20*mm)

        table_bot = _draw_table(c, font, font_b, page_pairs,
                                return_qty if is_last else "", actual_table_top)

        if is_last:
            _draw_footer(c, font, font_b, max(table_bot - 2*mm, FOOTER_BOT))
            _draw_cut_line(c, font, STRIP_TOP)
            _draw_basket_strip(c, font, font_b, project, pna_code, coord, date_lbl, place, STRIP_TOP)

    c.save()
    return len(pages)


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="임가공 리턴 자재 구분표 PDF 생성기")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--record-id", help="pkg_schedule record ID")
    group.add_argument("--date",      help="임가공 예정일 (YYYY-MM-DD) — 해당 날짜 전체")
    parser.add_argument("--upload-field", default=DEFAULT_UPLOAD_FLD,
                        help="업로드할 Airtable 필드 ID (미지정 시 outputs/ 저장)")
    args = parser.parse_args()

    if not PAT:
        print("[ERROR] AIRTABLE_SERPA_PAT 환경변수를 설정하세요")
        sys.exit(1)

    if args.record_id:
        recs = [fetch_record(args.record_id)]
    else:
        recs = fetch_records_by_date(args.date)
        print(f"▶ {args.date} 임가공 {len(recs)}건 조회됨")

    if not recs:
        print("ℹ 해당 날짜 임가공 레코드 없음")
        return

    out_dir = Path(os.getenv("PDF_OUTPUT_DIR", "outputs"))
    out_dir.mkdir(exist_ok=True)

    for rec in recs:
        print(f"\n▶ {rec['rec_id']} | {rec['project'] or '(이름없음)'}")
        print(f"   자재 {len(rec['items'])}종  투입수량:{len(rec['issued_qtys'])}건  "
              f"리턴:{rec['return_qty'] or '—'}  좌표:{rec['coord'] or '—'}")

        buf = BytesIO()
        pages = generate_pdf(rec, buf)
        pdf_bytes = buf.getvalue()

        proj_slug = re.sub(r"[^\w가-힣-]", "_", rec["project"] or rec["rec_id"])[:30]
        fname = f"리턴구분표_{proj_slug}_{rec['date'] or 'nodate'}.pdf"

        if args.upload_field:
            upload_pdf(rec["rec_id"], args.upload_field, fname, pdf_bytes)
        else:
            out_path = out_dir / fname
            out_path.write_bytes(pdf_bytes)
            print(f"  💾 저장: {out_path}  ({pages}페이지)")

    print("\n✅ 완료")


if __name__ == "__main__":
    main()
