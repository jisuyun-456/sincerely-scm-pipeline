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
SESSION   = requests.Session()
SESSION.headers.update(HEADERS)

LABEL_W = 80 * mm
LABEL_H = 55 * mm

F_PROJECT       = "프로젝트명 (Short ver.)"
F_ITEMS         = "재고 투입자재 (from pkg_task)"
F_QTYS          = "출고수량 (from movement)"
DEFAULT_UPLOAD_FLD = "fldtcblsJJsQYFdWU"   # 투입자재_pdf

TBL_PKG_TASK    = "tblZvnacaeyCd8q2u"
TBL_MATERIAL    = "tblLlOjdPAqHnsWm8"   # material(parts-stock)
F_PKG_TASK_LINK = "pkg_task"
F_PT_ITEM       = "재고 투입자재 (from movement)"   # fldgcSfQQwxnrUbcL → returns material rec IDs
F_PT_QTY        = "출고수량 (from movement)"        # fldtdgwbRwdtSlBcI in pkg_task

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
            r = SESSION.post(
                url,
                headers={"Content-Type": "application/json"},
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


def _fetch_task_pairs(task_ids: list) -> list:
    """pkg_task + material 배치 조회 → (item_name, qty_str) 리스트.
    filterByFormula=OR(RECORD_ID()=...) 로 각 1회씩만 호출."""
    if not task_ids:
        return []

    # ── Step 1: pkg_task 배치 조회 ──────────────────────────────
    cond = ",".join(f"RECORD_ID()='{rid}'" for rid in task_ids)
    formula = f"OR({cond})" if len(task_ids) > 1 else f"RECORD_ID()='{task_ids[0]}'"
    try:
        r = SESSION.get(
            f"https://api.airtable.com/v0/{BASE_ID}/{TBL_PKG_TASK}",
            params=[("filterByFormula", formula),
                    ("fields[]", F_PT_ITEM), ("fields[]", F_PT_QTY)],
            timeout=60,
        )
        r.raise_for_status()
        task_map = {rec["id"]: rec["fields"] for rec in r.json().get("records", [])}
    except Exception:
        return []

    # ── Step 2: 유니크 material ID 수집 ────────────────────────
    all_mat_ids: list = []
    seen: set = set()
    for rid in task_ids:
        mids = task_map.get(rid, {}).get(F_PT_ITEM, [])
        if isinstance(mids, list) and mids:
            mid = mids[0]
            if mid not in seen:
                all_mat_ids.append(mid)
                seen.add(mid)

    # ── Step 3: material 배치 조회 ─────────────────────────────
    mat_names: dict = {}
    if all_mat_ids:
        mcond = ",".join(f"RECORD_ID()='{mid}'" for mid in all_mat_ids)
        mformula = f"OR({mcond})" if len(all_mat_ids) > 1 else f"RECORD_ID()='{all_mat_ids[0]}'"
        try:
            mr = SESSION.get(
                f"https://api.airtable.com/v0/{BASE_ID}/{TBL_MATERIAL}",
                params=[("filterByFormula", mformula), ("fields[]", "Name")],
                timeout=60,
            )
            mr.raise_for_status()
            for rec in mr.json().get("records", []):
                mat_names[rec["id"]] = rec["fields"].get("Name", rec["id"])
        except Exception:
            pass

    # ── Step 4: 원래 순서대로 pairs 빌드 ──────────────────────
    pairs = []
    for rec_id in task_ids:
        f = task_map.get(rec_id)
        if not f:
            continue

        mids = f.get(F_PT_ITEM, [])
        item = mat_names.get(mids[0], mids[0]) if isinstance(mids, list) and mids else ""

        qty_raw = f.get(F_PT_QTY, "")
        if isinstance(qty_raw, list):
            qty = str(int(float(qty_raw[0]))) if qty_raw and qty_raw[0] is not None else ""
        else:
            qty = str(int(float(qty_raw))) if qty_raw not in ("", None) else ""

        if item:
            pairs.append((item, qty))
    return pairs


def fetch_record(record_id: str) -> dict:
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_PKG}/{record_id}"
    r = SESSION.get(url, timeout=60)
    r.raise_for_status()
    f = r.json().get("fields", {})

    proj_raw = f.get(F_PROJECT, "")
    project  = (proj_raw[0] if isinstance(proj_raw, list) else proj_raw) or ""

    task_ids = f.get(F_PKG_TASK_LINK, [])
    if task_ids:
        pairs = _fetch_task_pairs(task_ids)
        items = [p[0] for p in pairs]
        qtys  = [p[1] for p in pairs]
    else:
        items = _parse_items(f.get(F_ITEMS, ""))
        qtys  = _parse_qtys(f.get(F_QTYS, ""))

    return {"rec_id": record_id, "project": str(project), "items": items, "qtys": qtys}


# ── PDF 드로잉 ────────────────────────────────────────────────────────────────

def _draw_header(c, font, font_bold, project: str):
    W, H = LABEL_W, LABEL_H
    PAD  = 3.5 * mm
    NAVY = colors.HexColor("#0b2747")

    HDR_H = 14 * mm   # 13pt PNA 2줄 수용
    HDR_Y = H - HDR_H

    c.setFillColor(NAVY)
    c.rect(0, HDR_Y, W, HDR_H, fill=1, stroke=0)
    c.setFillColor(colors.white)

    # 우측: "PICKING SLIP" — 수직 중앙 정렬
    FS_SLIP    = 7
    ASC_SLIP   = FS_SLIP * 0.72 * (25.4 / 72) * mm
    SLIP_W     = pdfmetrics.stringWidth("PICKING SLIP", font_bold, FS_SLIP)
    slip_y     = HDR_Y + HDR_H / 2 - ASC_SLIP / 2
    c.setFont(font_bold, FS_SLIP)
    c.drawRightString(W - PAD, slip_y, "PICKING SLIP")

    # 좌측: PNA 프로젝트명 — 13pt bold, 최대 2줄, 수직 중앙 정렬
    FS_P     = 13
    ASCENT_P = FS_P * 0.72 * (25.4 / 72) * mm
    LH_P     = FS_P * 1.35 * (25.4 / 72) * mm
    pna_max_w    = W - PAD * 2 - SLIP_W - 2 * mm
    proj_lines   = _split_name(project or "—", font_bold, FS_P, pna_max_w)[:2]
    text_block_h = ASCENT_P + (len(proj_lines) - 1) * LH_P
    y0 = HDR_Y + (HDR_H + text_block_h) / 2 - ASCENT_P
    c.setFont(font_bold, FS_P)
    for idx, ln in enumerate(proj_lines):
        c.drawString(PAD, y0 - idx * LH_P, ln)

    return HDR_Y   # 아이템 시작 Y (틴트 바 제거)


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
                    font_size: float = 7.5, v_pad: float = 1.5):
    """80×55mm 1장 그리기. pairs = [(name, qty), ...], v_pad은 mm 단위"""
    W, H   = LABEL_W, LABEL_H
    PAD    = 3.5 * mm
    INK    = colors.HexColor("#0f0f10")
    INK2   = colors.HexColor("#3a3a3d")
    LINE   = colors.HexColor("#d8d9dd")
    QTY_W  = 16 * mm
    FS     = font_size
    LINE_H = FS * 1.35 * (25.4 / 72) * mm
    V_PAD  = v_pad * mm
    ASCENT = FS * 0.72 * (25.4 / 72) * mm
    TEXT_W = W - QTY_W - PAD - 1.5 * mm

    PROJ_Y = _draw_header(c, font, font_bold, project)
    cur_y  = PROJ_Y - 0.5 * mm

    for i, (name, qty) in enumerate(pairs):
        lines = _split_name(name, font, FS, TEXT_W)
        row_h = len(lines) * LINE_H + V_PAD * 2

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


def generate_pdf(rec: dict, output, fit_page: bool = True) -> int:
    font, font_bold = register_fonts()
    c = rl_canvas.Canvas(output, pagesize=(LABEL_W, LABEL_H))

    items = rec["items"]
    qtys  = rec["qtys"]
    pairs = [(items[i], qtys[i] if i < len(qtys) else "") for i in range(len(items))]
    project = rec["project"]

    # 상수 (draw_label_page와 동기; HDR_H=14mm, 틴트 바 제거)
    QTY_W  = 16 * mm
    PAD    = 3.5 * mm
    BODY_H = LABEL_H - 14 * mm - 0.5 * mm  # ≈ 40.5mm

    def _row_h(name: str, fs: float, vp_mm: float) -> float:
        lh = fs * 1.35 * (25.4 / 72) * mm
        tw = LABEL_W - QTY_W - PAD - 1.5 * mm
        return len(_split_name(name, font, fs, tw)) * lh + vp_mm * mm * 2

    if fit_page:
        # V_PAD=0으로 최대한 압축, 폰트 7.5→4.5pt 탐색
        fs_used = 4.5
        for fs_10 in range(75, 44, -5):
            fs = fs_10 / 10
            if sum(_row_h(n, fs, 0) for n, _ in pairs) <= BODY_H:
                fs_used = fs
                break
        draw_label_page(c, font, font_bold, project, pairs,
                        font_size=fs_used, v_pad=0)
        n_pages = 1
    else:
        # Option 2 (기본): 실제 행 높이 기반 멀티 페이지
        page_list, cur_page, cur_h = [], [], 0.0
        for pair in pairs:
            rh = _row_h(pair[0], 7.5, 1.5)
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
    parser.add_argument("--multi-page", action="store_true",
                        help="멀티 페이지 모드 (기본: 단일 페이지 맞춤)")
    args = parser.parse_args()

    if not PAT:
        print("[ERROR] AIRTABLE_SERPA_PAT 환경변수를 설정하세요")
        sys.exit(1)

    print(f"▶ 조회: {args.record_id}")
    rec = fetch_record(args.record_id)
    print(f"  프로젝트: {rec['project']}")
    print(f"  품목 {len(rec['items'])}개")

    buf = BytesIO()
    pages = generate_pdf(rec, buf, fit_page=not args.multi_page)
    pdf_bytes = buf.getvalue()

    fname = f"투입자재_{rec['project'] or args.record_id}.pdf"
    upload_pdf(rec["rec_id"], args.upload_field, fname, pdf_bytes)
    print(f"✅ 완료 ({pages}페이지)")


if __name__ == "__main__":
    main()
