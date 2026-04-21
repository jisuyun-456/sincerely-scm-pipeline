"""
barcode_label.py
────────────────────────────────────────────────────────────────────────────
Barcode 베이스 → 다영기획 이동 바코드 라벨 PDF 생성기

바코드 테이블(tbl0K3QP5PCd06Cxv)의 외박스 레코드 1건 = 라벨 1장
이동리스트(tblnxU0PlegXT7bYj)에서 PT코드 + 출고물품을 join해 표시

라벨 규격: 100mm × 70mm  (A4 페이지에 2×4 = 8장)

사용법:
  python scripts/barcode_label.py                        # 다영기획 미출력 전체
  python scripts/barcode_label.py --project PNA36435    # 프로젝트 필터
  python scripts/barcode_label.py --pks PKS017979       # 피킹리스트 번호 필터
  python scripts/barcode_label.py --dry-run             # 미리보기만
"""

import argparse, os, re, sys, time
from datetime import date
from io import BytesIO

import requests
from dotenv import load_dotenv
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
import barcode as bc_lib
from barcode.writer import ImageWriter
from PIL import Image

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

BASE_ID  = "app4LvuNIDiqTmhnv"
TBL_BC   = "tbl0K3QP5PCd06Cxv"   # 바코드 (외박스 단위)
TBL_IL   = "tblnxU0PlegXT7bYj"   # 이동리스트
PAT      = os.getenv("AIRTABLE_WMS_PAT") or os.getenv("AIRTABLE_PAT", "")
HEADERS  = {"Authorization": f"Bearer {PAT}"}

LABEL_W  = 100 * mm
LABEL_H  = 70  * mm
FONT_REG = r"C:\Windows\Fonts\malgun.ttf"
FONT_BLD = r"C:\Windows\Fonts\malgunbd.ttf"


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
    url     = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}"
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


def parse_int(v) -> int:
    try:
        return int(float(str(v).replace(",", ""))) if v else 0
    except Exception:
        return 0


# ────────────────────────────────────────────────────────────────────────────
# 데이터 조회
# ────────────────────────────────────────────────────────────────────────────
def fetch_labels(project_filter=None, pks_filter=None) -> list:
    """
    바코드 테이블에서 다영기획 미출력 레코드 조회,
    이동리스트와 join해 PT코드 + 품목명 완성
    """
    # ── 이동리스트 전체 → PT+품목명 매핑 ──────────────────────────────────
    il_recs = airtable_get(TBL_IL, {
        "fields[]": ["movement_id", "파츠코드", "출고물품", "출하장소",
                     "이동수량", "계획수량", "라벨 박스수량"],
        "pageSize": 100,
    })
    # record_id → {pt, name, qty, box_count}
    il_by_id: dict[str, dict] = {}
    for r in il_recs:
        f  = r.get("fields", {})
        pt = (f.get("파츠코드") or "").strip()
        nm = (f.get("출고물품") or "").strip()
        il_by_id[r["id"]] = {
            "pt":        pt,
            "name":      nm,
            "product":   f"{pt}-{nm}" if pt and nm else (pt or nm),
            "qty":       parse_int(f.get("이동수량") or f.get("계획수량")),
            "box_count": parse_int(f.get("라벨 박스수량")),
            "location":  (f.get("출하장소") or "").strip(),
        }

    # ── 바코드 테이블 조회 ─────────────────────────────────────────────────
    # Barcode 베이스 자체가 다영기획 전용 — 목적지 필터 불필요
    # project는 바코드 테이블에서 linked 배열 필드
    formula_parts = []
    if project_filter:
        formula_parts.append(f"FIND('{project_filter}', ARRAYJOIN({{project}}))")
    if pks_filter:
        formula_parts.append(f"FIND('{pks_filter}', ARRAYJOIN({{이동리스트}}))")

    formula = ("AND(" + ", ".join(formula_parts) + ")") if len(formula_parts) > 1 \
              else (formula_parts[0] if formula_parts else None)

    params = {
        "fields[]": ["Barcode_Number", "project", "출고물품",
                     "이동리스트", "이동수량", "임가공 예정일",
                     "파츠코드", "라벨 박스수량"],
        "pageSize": 100,
        "sort[0][field]": "ID",
        "sort[0][direction]": "asc",
    }
    if formula:
        params["filterByFormula"] = formula

    bc_recs = airtable_get(TBL_BC, params)

    result = []
    for r in bc_recs:
        f  = r.get("fields", {})
        bc_num  = str(f.get("Barcode_Number") or r["id"])
        # project: 바코드 테이블에서는 linked 배열 ["PNA36435-프로젝트명", ...]
        proj_raw = f.get("project") or ""
        if isinstance(proj_raw, list):
            project = (proj_raw[0] or "").strip() if proj_raw else ""
        else:
            project = str(proj_raw).strip()

        # 이동리스트 링크에서 PT+품목명 우선 합산
        linked_ids = f.get("이동리스트") or []
        products, total_qty = [], 0
        for lid in linked_ids:
            il = il_by_id.get(lid, {})
            if il.get("product"):
                products.append(il["product"])
            total_qty += il.get("qty", 0)

        # 폴백: 바코드 테이블 자체 필드
        if not products:
            pt  = (f.get("파츠코드") or "").strip()
            nm  = (f.get("출고물품") or f.get("출고자재") or "").strip()
            products = [f"{pt}-{nm}" if pt and nm else (pt or nm)]

        qty      = total_qty or parse_int(f.get("이동수량") or f.get("출고수량"))
        box_tot  = parse_int(f.get("라벨 박스수량")) or 1
        # 임가공 예정일: 바코드 테이블에서 linked rollup → 배열로 반환될 수 있음
        date_raw = f.get("임가공 예정일")
        if isinstance(date_raw, list):
            date_raw = date_raw[0] if date_raw else None
        move_dt  = str(date_raw)[:10] if date_raw else ""

        result.append({
            "rec_id":    r["id"],
            "bc_num":    bc_num,
            "project":   project,
            "products":  products,   # 리스트 (여러 품목)
            "qty":       qty,
            "box_count": box_tot,
            "move_date": move_dt,
        })

    return result


# ────────────────────────────────────────────────────────────────────────────
# 바코드 이미지
# ────────────────────────────────────────────────────────────────────────────
def make_barcode_buf(value: str) -> BytesIO:
    safe = re.sub(r"[^\x20-\x7E]", "", str(value))[:30] or "NOCODE"
    writer = ImageWriter()
    buf = BytesIO()
    b = bc_lib.get("code128", safe, writer=writer)
    b.write(buf, options={
        "module_width": 0.3, "module_height": 8.0,
        "quiet_zone": 2.0, "font_size": 6, "text_distance": 3.0,
        "background": "white", "foreground": "black",
        "write_text": True, "dpi": 150,
    })
    buf.seek(0)
    return buf


# ────────────────────────────────────────────────────────────────────────────
# 라벨 1장 그리기
# ────────────────────────────────────────────────────────────────────────────
def draw_label(c: rl_canvas.Canvas, x: float, y: float,
               rec: dict, box_num: int, font: str, font_bold: str):
    W, H  = LABEL_W, LABEL_H
    PAD   = 3 * mm
    DARK  = colors.HexColor("#2E4057")
    GRAY  = colors.HexColor("#F0F4F8")
    LGRAY = colors.HexColor("#CCCCCC")

    # 테두리
    c.setStrokeColor(colors.HexColor("#333333"))
    c.setLineWidth(0.8)
    c.rect(x, y, W, H)

    # ── 헤더 띠 ─────────────────────────────────────────────────────────────
    HDR_H = 8.5 * mm
    c.setFillColor(DARK)
    c.rect(x, y + H - HDR_H, W, HDR_H, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont(font_bold, 7.5)
    c.drawString(x + PAD, y + H - HDR_H + 2.8*mm, "에이원지식산업센터  →  다영기획")
    dt = rec["move_date"] or date.today().strftime("%Y-%m-%d")
    c.setFont(font, 7)
    c.drawRightString(x + W - PAD, y + H - HDR_H + 2.8*mm, dt)

    # ── 프로젝트명 ─────────────────────────────────────────────────────────
    proj = (rec["project"] or "-")[:40]
    c.setFillColor(DARK)
    c.setFont(font_bold, 8.5)
    c.drawString(x + PAD, y + H - HDR_H - 5.5*mm, proj)

    # 구분선
    c.setStrokeColor(LGRAY)
    c.setLineWidth(0.4)
    c.line(x + PAD, y + H - HDR_H - 7.5*mm,
           x + W - PAD, y + H - HDR_H - 7.5*mm)

    # ── 품목 목록 (최대 3개) ────────────────────────────────────────────────
    c.setFillColor(colors.black)
    products = rec["products"][:3]
    LINE_H   = 4.5 * mm
    start_y  = y + H - HDR_H - 12*mm
    for i, prod in enumerate(products):
        # PT코드 강조
        dash_pos = prod.find("-")
        if dash_pos > 0:
            pt_part   = prod[:dash_pos]
            name_part = prod[dash_pos+1:]
            # PT코드 (작게, 회색)
            c.setFont(font, 6.5)
            c.setFillColor(colors.HexColor("#555555"))
            c.drawString(x + PAD, start_y - i * LINE_H, pt_part + "  ")
            pt_w = c.stringWidth(pt_part + "  ", font, 6.5)
            # 품목명 (굵게, 검정)
            c.setFont(font_bold if i == 0 else font, 8 if i == 0 else 7)
            c.setFillColor(colors.black)
            max_w = int((W - 2*PAD - pt_w) / c.stringWidth("가", font_bold if i==0 else font, 8 if i==0 else 7)) + 2
            c.drawString(x + PAD + pt_w, start_y - i * LINE_H,
                         name_part[:max_w])
        else:
            c.setFont(font_bold if i == 0 else font, 8 if i == 0 else 7)
            c.setFillColor(colors.black)
            c.drawString(x + PAD, start_y - i * LINE_H, prod[:38])

    if len(rec["products"]) > 3:
        c.setFont(font, 6)
        c.setFillColor(colors.HexColor("#888888"))
        c.drawString(x + PAD, start_y - 3 * LINE_H,
                     f"외 {len(rec['products'])-3}개 품목")

    # ── 수량 / 박스 (2단) ──────────────────────────────────────────────────
    MID_Y = y + 22 * mm
    c.setFillColor(GRAY)
    c.rect(x, MID_Y, W/2, 10*mm, fill=1, stroke=0)
    c.rect(x + W/2, MID_Y, W/2, 10*mm, fill=1, stroke=0)

    c.setFillColor(colors.HexColor("#666666"))
    c.setFont(font, 6.5)
    c.drawString(x + PAD,       MID_Y + 6.5*mm, "수   량")
    c.drawString(x + W/2 + PAD, MID_Y + 6.5*mm, "박   스")

    c.setFillColor(DARK)
    c.setFont(font_bold, 11)
    qty_str = f"{rec['qty']:,}개" if rec["qty"] else "-"
    box_str = f"{box_num} / {rec['box_count']}"
    c.drawString(x + PAD,       MID_Y + 2*mm, qty_str)
    c.drawString(x + W/2 + PAD, MID_Y + 2*mm, box_str)

    c.setStrokeColor(colors.HexColor("#AAAAAA"))
    c.setLineWidth(0.3)
    c.line(x + W/2, MID_Y, x + W/2, MID_Y + 10*mm)

    # ── 바코드 ─────────────────────────────────────────────────────────────
    BAR_H = 18 * mm
    BAR_Y = y + 2 * mm
    try:
        buf = make_barcode_buf(rec["bc_num"])
        img = Image.open(buf)
        img_buf = BytesIO()
        img.save(img_buf, format="PNG")
        img_buf.seek(0)
        c.drawImage(
            rl_canvas.ImageReader(img_buf),
            x + PAD, BAR_Y, width=W - 2*PAD, height=BAR_H,
            preserveAspectRatio=True, anchor="c",
        )
    except Exception:
        c.setFillColor(colors.black)
        c.setFont(font, 7)
        c.drawCentredString(x + W/2, BAR_Y + BAR_H/2, rec["bc_num"][:25])


# ────────────────────────────────────────────────────────────────────────────
# PDF 생성 (A4, 2×4 레이아웃)
# ────────────────────────────────────────────────────────────────────────────
def generate_pdf(records: list, output_path: str) -> int:
    font, font_bold = register_fonts()
    PAGE_W, PAGE_H  = A4
    COLS, ROWS      = 2, 4
    MX = (PAGE_W - COLS * LABEL_W) / 2
    MY = (PAGE_H - ROWS * LABEL_H) / 2

    # 박스 수만큼 라벨 복제
    label_list = []
    for rec in records:
        for i in range(1, max(1, rec["box_count"]) + 1):
            label_list.append((rec, i))

    c       = rl_canvas.Canvas(output_path, pagesize=A4)
    per_pg  = COLS * ROWS

    for pg in range(0, len(label_list), per_pg):
        batch = label_list[pg: pg + per_pg]
        for idx, (rec, box_num) in enumerate(batch):
            col = idx % COLS
            row = idx // COLS
            lx  = MX + col * LABEL_W
            ly  = PAGE_H - MY - (row + 1) * LABEL_H
            draw_label(c, lx, ly, rec, box_num, font, font_bold)
        c.showPage()

    c.save()
    return len(label_list)


# ────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="다영기획 이동 바코드 라벨 PDF")
    parser.add_argument("--project", help="프로젝트 필터 (예: PNA36435)")
    parser.add_argument("--pks",     help="피킹리스트 번호 (예: PKS017979)")
    parser.add_argument("--dry-run", action="store_true", help="미리보기만")
    args = parser.parse_args()

    if not PAT:
        print("[ERROR] AIRTABLE_WMS_PAT 환경변수를 .env에 설정하세요")
        sys.exit(1)

    print("▶ Barcode 베이스 조회 중…")
    records = fetch_labels(project_filter=args.project, pks_filter=args.pks)

    if not records:
        print("조회 결과 없음 (다영기획 이동 예정 레코드가 없거나 필터 확인)")
        return

    total_labels = sum(max(1, r["box_count"]) for r in records)
    print(f"  {len(records)}건 조회 → 총 {total_labels}장 라벨")
    print()
    for r in records:
        prods = " / ".join(r["products"][:2])
        print(f"  • {r['bc_num']:<8}  {r['project'][:25]:<25}  {prods[:40]:<40}  {r['qty']:>5}개  {r['box_count']}박스")

    if args.dry_run:
        print("\n[dry-run] PDF 생성 건너뜀")
        return

    today    = date.today().strftime("%Y-%m-%d")
    suffix   = f"_{args.project}" if args.project else (f"_{args.pks}" if args.pks else "")
    out_path = rf"C:\Users\yjisu\Desktop\SCM_WORK\바코드라벨{suffix}_{today}.pdf"

    print(f"\n▶ PDF 생성 중… → {out_path}")
    n = generate_pdf(records, out_path)
    print(f"✅ 완료 — {n}장 라벨 ({out_path})")


if __name__ == "__main__":
    main()
