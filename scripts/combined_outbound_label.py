"""
combined_outbound_label.py
────────────────────────────────────────────────────────────────────────────
logistics_release → 쉬핑마크 + 외박스 라벨 통합 PDF (150mm × 100mm)

카톤 1개당 2페이지 (쉬핑마크 → 외박스 라벨) 순서로 인쇄:
  Page 1: Shipping Mark (Box 1)
  Page 2: Carton Label  (Box 1)
  Page 3: Shipping Mark (Box 2)
  Page 4: Carton Label  (Box 2)
  ...

사용법:
  python scripts/combined_outbound_label.py --lr-id recXXXXXX
  python scripts/combined_outbound_label.py --to-num TO00016184
  python scripts/combined_outbound_label.py --date 2026-05-07
  python scripts/combined_outbound_label.py --lr-id recXXX --upload-field fldXXX
  python scripts/combined_outbound_label.py --lr-id recXXX --dry-run
"""

import argparse, base64, os, platform, re, sys, time
from datetime import datetime
from io import BytesIO

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

BASE_ID     = os.getenv("SERPA_BASE_ID", "appkRWtF2j99XgBTq")
TBL_LR      = os.getenv("SERPA_LR_TABLE_ID", "tblj53ZBaJBpScNNI")
PROJECT_TBL = os.getenv("SERPA_PROJECT_TABLE_ID", "tblcw5sagkDlgAtJN")
PAT = (os.getenv("AIRTABLE_SERPA_PAT")
       or os.getenv("AIRTABLE_WMS_PAT")
       or os.getenv("AIRTABLE_PAT")
       or os.getenv("AIRTABLE_API_KEY", ""))
HEADERS = {"Authorization": f"Bearer {PAT}"}

LABEL_W = 150 * mm
LABEL_H = 100 * mm

# V3140 라벨지: A4 2×2, 각 셀 98.73 × 139 mm
CELL_W  = 98.73 * mm
CELL_H  = 139.0 * mm
_PW, _PH = A4                          # 210 × 297 mm
_LM = (_PW - 2 * CELL_W) / 2          # 좌우 여백 ~6.27 mm
_BM = (_PH - 2 * CELL_H) / 2          # 상하 여백 ~9.5 mm
# 셀 좌하단 좌표 (ReportLab: y=0 이 하단)
CELL_ORIGINS = [
    (_LM,            _BM + CELL_H),    # 0: 상단-좌
    (_LM + CELL_W,   _BM + CELL_H),    # 1: 상단-우
    (_LM,            _BM),             # 2: 하단-좌
    (_LM + CELL_W,   _BM),             # 3: 하단-우
]

if platform.system() == "Windows":
    FONT_REG = r"C:\Windows\Fonts\malgun.ttf"
    FONT_BLD = r"C:\Windows\Fonts\malgunbd.ttf"
else:
    FONT_REG = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
    FONT_BLD = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"


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


# ────────────────────────────────────────────────────────────────────────────
# 파싱 (packing_list.py와 동일 패턴 — 공백 허용)
# ────────────────────────────────────────────────────────────────────────────
_BOX_ROW         = re.compile(r"^(\d+)(\s*\+\s*[^\s*]+(?:\([^)]*\))*)?\s*\*\s*(\d+)\s*(.+?)\s*$")
_BOX_ROW_INLINE  = re.compile(r"^(.+?)\s+(\d+(?:[+][^\s*]+)?)\s*\*\s*(\d+)\s+([대중소]형?)\s*$")
_BOX_ROW_COMPACT = re.compile(r"^(.+?)(\d+)\s*\*\s*(\d+)\s+(\S+(?:\s*\([^)]*\))?)\s*$")


def _check_box_sum_internal(box_sum_str: str) -> tuple[bool, int, int]:
    """외박스 수량 필드 내부 정합성 검사: '극소2,대5 / 총8박스' → size_sum=7 ≠ 8 → inconsistent.
    Returns (is_inconsistent, size_sum, field_total). Only fires when '/' separator exists."""
    total_m = re.search(r'총(\d+)박스', box_sum_str)
    if not total_m or '/' not in box_sum_str:
        return False, 0, 0
    field_total = int(total_m.group(1))
    before_slash = box_sum_str.split('/')[0]
    size_counts = re.findall(r'(?:극소|소형?|중형?|대형?|특대형?)(\d+)', before_slash)
    if not size_counts:
        return False, 0, field_total
    size_sum = sum(int(x) for x in size_counts)
    return size_sum != field_total, size_sum, field_total


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
                    "box_num":         box_num,
                    "size":            m.group(4).strip(),
                    "item":            _clean_item_name(current_item),
                    "qty":             qty_str,
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
                        "box_num":         box_num,
                        "size":            mi.group(4).strip(),
                        "item":            _clean_item_name(current_item),
                        "qty":             qty_str,
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


# ────────────────────────────────────────────────────────────────────────────
# 데이터 조회
# ────────────────────────────────────────────────────────────────────────────
FIELDS = [
    "프로젝트명 (출고)", "출고 요청일", "외박스 포장 내역", "외박스 수량",
    "진행현황 (from Packaging_Schedule)",
    "기업명(알림톡2)", "회사명", "project",
    "프로젝트명 (Short ver.) (from project)",
    "수령인(성함)", "수령인(주소)",
]


def _fetch_project_names(project_ids: list[str]) -> dict[str, str]:
    if not project_ids:
        return {}
    results: dict[str, str] = {}
    for i in range(0, len(project_ids), 10):
        batch = project_ids[i:i + 10]
        parts   = [f'RECORD_ID()="{pid}"' for pid in batch]
        formula = f"OR({','.join(parts)})"
        try:
            recs = airtable_get(PROJECT_TBL, {
                "fields[]":        ["Name"],
                "filterByFormula": formula,
                "pageSize":        100,
            })
            for r in recs:
                results[r["id"]] = r["fields"].get("Name", "")
        except Exception:
            pass
    return results


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

    proj_id_map: dict[str, str] = {}
    for r in recs:
        linked = r.get("fields", {}).get("project", [])
        if linked:
            proj_id_map[r["id"]] = linked[0]
    proj_name_map = _fetch_project_names(list(set(proj_id_map.values())))

    result = []
    for r in recs:
        f = r.get("fields", {})
        packing_text = f.get("외박스 포장 내역", "")
        to_num = f.get("프로젝트명 (출고)", r["id"])
        if not packing_text:
            print(f"  ⚠  {to_num} — 외박스 포장 내역 없음, 에러 라벨 생성")
            result.append({
                "rec_id": r["id"], "to_num": to_num,
                "date": (f.get("출고 요청일") or "")[:10],
                "is_error": True, "error_title": "외박스 포장 내역 없음",
                "error_text": "(포장 내역이 입력되지 않았습니다.)",
                "company": f.get("기업명(알림톡2)") or f.get("회사명", ""),
                "consignee_name": f.get("수령인(성함)", ""),
                "consignee_addr": f.get("수령인(주소)", ""),
                "boxes": [],
            })
            continue
        boxes = parse_packing_detail(packing_text)
        if not boxes:
            print(f"  ⚠  {to_num} — 포장 내역 파싱 실패, 에러 라벨 생성")
            result.append({
                "rec_id": r["id"], "to_num": to_num,
                "date": (f.get("출고 요청일") or "")[:10],
                "is_error": True, "error_title": "포장 내역 파싱 실패",
                "error_text": packing_text or "(포장 내역 없음)",
                "company": f.get("기업명(알림톡2)") or f.get("회사명", ""),
                "consignee_name": f.get("수령인(성함)", ""),
                "consignee_addr": f.get("수령인(주소)", ""),
                "boxes": [],
            })
            continue
        total = len(boxes)
        box_sum_str = str(f.get("외박스 수량") or "")

        # Check 1: internal consistency of 외박스 수량 field (규격별 합 vs 총N박스)
        _ic, _size_sum, _ic_total = _check_box_sum_internal(box_sum_str)
        if _ic:
            print(f"  ⚠  {to_num} — 수량 필드 내부 불일치: 규격합={_size_sum} 총표기={_ic_total}, 에러 라벨 생성")
            result.append({
                "rec_id": r["id"], "to_num": to_num,
                "date": (f.get("출고 요청일") or "")[:10],
                "is_error": True, "error_title": "외박스 수량 필드 불일치",
                "error_text": (
                    f"외박스 수량 필드: {box_sum_str}\n"
                    f"규격별 합계: {_size_sum}박스 / 총 표기: {_ic_total}박스\n\n"
                    "--- 포장 내역 원문 ---\n" + packing_text[:120]
                ),
                "company": f.get("기업명(알림톡2)") or f.get("회사명", ""),
                "consignee_name": f.get("수령인(성함)", ""),
                "consignee_addr": f.get("수령인(주소)", ""),
                "boxes": [],
            })
            continue

        # Check 2: 총N박스 field value vs parsed box count from packing text
        _tm = re.search(r'총(\d+)박스', box_sum_str) or re.match(r'(\d+)', box_sum_str)
        if _tm and int(_tm.group(1)) != total:
            field_total = int(_tm.group(1))
            print(f"  ⚠  {to_num} — 수량 불일치: 필드={field_total} 파싱={total}, 에러 라벨 생성")
            result.append({
                "rec_id": r["id"], "to_num": to_num,
                "date": (f.get("출고 요청일") or "")[:10],
                "is_error": True, "error_title": "외박스 수량 불일치",
                "error_text": (
                    f"외박스 수량 필드: {box_sum_str}\n"
                    f"포장 내역 파싱: {total}박스\n\n"
                    "--- 포장 내역 원문 ---\n" + packing_text[:120]
                ),
                "company": f.get("기업명(알림톡2)") or f.get("회사명", ""),
                "consignee_name": f.get("수령인(성함)", ""),
                "consignee_addr": f.get("수령인(주소)", ""),
                "boxes": [],
            })
            continue

        for b in boxes:
            b["total_boxes"] = total

        _pna = f.get("프로젝트명 (Short ver.) (from project)", "")
        pna_short = (_pna[0] if isinstance(_pna, list) else _pna) or ""
        company = str(pna_short or f.get("기업명(알림톡2)") or f.get("회사명") or "")

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
# 쉬핑마크 (150×100mm) — shipping_mark.py와 동일 디자인
# ────────────────────────────────────────────────────────────────────────────
def draw_shipping_mark(c: rl_canvas.Canvas, x: float, y: float,
                       box: dict, to_num: str, date_str: str,
                       company: str, consignee_name: str, consignee_addr: str,
                       font: str, font_bold: str):
    W, H  = LABEL_W, LABEL_H
    PAD   = 5 * mm
    NAVY  = colors.HexColor("#0b2747")
    INK   = colors.HexColor("#0f0f10")
    INK2  = colors.HexColor("#3a3a3d")
    MUTED = colors.HexColor("#7c7c82")
    LINE2 = colors.HexColor("#eef0f4")

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

    FTR_H = 12 * mm
    c.setStrokeColor(LINE2); c.setLineWidth(1.1)
    c.line(x, y + FTR_H, x + W, y + FTR_H)
    c.setFont(font, 8); c.setFillColor(INK2)
    c.drawCentredString(x + W / 2, y + 8.5 * mm, f"SIZE  {box['size']}형")
    c.setFont(font_bold, 8.5); c.setFillColor(NAVY)
    c.drawCentredString(x + W / 2, y + 5.5 * mm, "MADE IN KOREA")
    c.setFont(font, 6); c.setFillColor(MUTED)
    c.drawCentredString(x + W / 2, y + 2.5 * mm, f"SHIP DATE  {date_str}")

    def hsep(ypos: float):
        c.setStrokeColor(LINE2); c.setLineWidth(0.7)
        c.line(x, ypos, x + W, ypos)

    def row_label(label_en: str, label_ko: str, ypos: float):
        c.setFont(font_bold, 6.5); c.setFillColor(NAVY)
        c.drawString(x + PAD, ypos, label_en)
        en_w = c.stringWidth(label_en, font_bold, 6.5)
        c.setFont(font, 6.5); c.setFillColor(MUTED)
        c.drawString(x + PAD + en_w + 2, ypos, "  " + label_ko)

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

    R2_TOP = R1_BOT - 2.6 * mm
    row_label("SHIPPING REF.", "/ 출고번호", R2_TOP)
    c.setFont(font_bold, 13); c.setFillColor(INK)
    c.drawString(x + PAD, R2_TOP - 7 * mm, to_num)
    R2_BOT = R2_TOP - 13 * mm
    hsep(R2_BOT)

    R3_TOP = R2_BOT - 2.8 * mm
    c.setFont(font_bold, 6.5); c.setFillColor(NAVY)
    c.drawString(x + PAD, R3_TOP, "CARTON NO.")
    c.setFont(font, 6.5); c.setFillColor(MUTED)
    c.drawString(x + PAD, R3_TOP - 4 * mm, "/ 박스 번호")
    c.setFont(font_bold, 32); c.setFillColor(INK)
    c.drawString(x + PAD, R3_TOP - 17 * mm,
                 f"C/No. {box['box_num']} / {box['total_boxes']}")

    c.setStrokeColor(colors.HexColor("#333333")); c.setLineWidth(1.0)
    c.rect(x, y, W, H, stroke=1, fill=0)


# ────────────────────────────────────────────────────────────────────────────
# 외박스 라벨 글로벌 스타일 (150×100mm) — outer_box_label.py와 동일 디자인
# ────────────────────────────────────────────────────────────────────────────
def draw_carton_label(c: rl_canvas.Canvas, x: float, y: float,
                      box: dict, to_num: str, date_str: str, company: str,
                      font: str, font_bold: str):
    W, H   = LABEL_W, LABEL_H
    PAD    = 5.5 * mm
    NAVY   = colors.HexColor("#0b2747")
    INK    = colors.HexColor("#0f0f10")
    INK2   = colors.HexColor("#3a3a3d")
    MUTED  = colors.HexColor("#7c7c82")
    MUTED2 = colors.HexColor("#9aa0a8")
    LINE   = colors.HexColor("#d8d9dd")

    HDR_H = 10.5 * mm
    HDR_Y = y + H - HDR_H
    c.setFillColor(NAVY)
    c.rect(x, HDR_Y, W, HDR_H, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont(font_bold, 8.5)
    c.drawString(x + PAD, HDR_Y + 3.5 * mm, "■  CARTON LABEL")
    c.setFont(font_bold, 9.1)
    c.drawRightString(x + W - PAD, HDR_Y + 3.5 * mm, "SINCERELY")

    META_H = 22 * mm
    META_Y = HDR_Y - META_H
    DIV_X  = x + W - 28 * mm

    c.setStrokeColor(LINE); c.setLineWidth(0.85)
    c.line(x, META_Y, x + W, META_Y)
    c.line(DIV_X, META_Y, DIV_X, HDR_Y)

    for i, (k, v) in enumerate([
        ("TO",  to_num),
        ("PO",  (company or "")[:28]),
        ("BOX", f"{box['box_num']} / {box['total_boxes']}"),
    ]):
        ry = HDR_Y - (5 * mm + i * 6.5 * mm)
        c.setFont(font_bold, 7.4); c.setFillColor(MUTED)
        c.drawString(x + PAD, ry, k)
        c.setFont(font_bold, 9.1); c.setFillColor(INK)
        c.drawString(x + PAD + 14 * mm, ry, v)

    c.setFont(font_bold, 7.4); c.setFillColor(MUTED)
    c.drawRightString(x + W - PAD, HDR_Y - 5 * mm, "SIZE")
    c.setFont(font_bold, 15.3); c.setFillColor(INK)
    c.drawRightString(x + W - PAD, HDR_Y - 14 * mm, f"{box['size']}형")

    FTR_H       = 8.5 * mm
    CONT_LBL_Y  = META_Y - 11 * mm
    CONT_TXT_Y  = META_Y - 22 * mm
    QTY_LBL_Y   = META_Y - 29 * mm
    QTY_TXT_Y   = META_Y - 41 * mm

    c.setFont(font_bold, 7.4); c.setFillColor(MUTED)
    c.drawString(x + PAD, CONT_LBL_Y, "CONTENTS")
    c.setFont(font_bold, 25.5); c.setFillColor(INK)
    c.drawString(x + PAD, CONT_TXT_Y, box["item"][:18])

    c.setFont(font_bold, 7.4); c.setFillColor(MUTED)
    c.drawString(x + PAD, QTY_LBL_Y, "QTY")

    m_qty = re.match(r"^(\d+)(?:\+(\d+))?", box["qty"])
    main  = m_qty.group(1) if m_qty else box["qty"]
    extra = m_qty.group(2) if m_qty else None

    c.setFont(font_bold, 31.2); c.setFillColor(INK)
    c.drawString(x + PAD, QTY_TXT_Y, main)
    cur_x = x + PAD + c.stringWidth(main, font_bold, 31.2)

    if extra:
        c.setFont(font_bold, 9); c.setFillColor(MUTED2)
        c.drawString(cur_x + 1 * mm, QTY_TXT_Y + 4 * mm, "+")
        cur_x += 1 * mm + c.stringWidth("+", font_bold, 9)
        c.setFont(font_bold, 22.7); c.setFillColor(INK2)
        c.drawString(cur_x + 1 * mm, QTY_TXT_Y + 1 * mm, extra)
        cur_x += 1 * mm + c.stringWidth(extra, font_bold, 22.7)

    c.setFont(font_bold, 17); c.setFillColor(INK2)
    c.drawString(cur_x + 2 * mm, QTY_TXT_Y + 1 * mm, "EA")

    remainders = box.get("remainder_items", [])
    if remainders:
        REM_Y = QTY_TXT_Y - 8 * mm
        rem_text = "+  " + "   ".join(
            f"{r['name']} {r['qty']}" if r['qty'] else r['name']
            for r in remainders
        )
        c.setFont(font, 7.4); c.setFillColor(MUTED)
        c.drawString(x + PAD, REM_Y, rem_text[:60])

    c.setFillColor(colors.HexColor("#fafbfd"))
    c.rect(x, y, W, FTR_H, fill=1, stroke=0)
    c.setStrokeColor(LINE); c.setLineWidth(0.85)
    c.line(x, y + FTR_H, x + W, y + FTR_H)

    c.setFont(font_bold, 6.8); c.setFillColor(MUTED)
    c.drawString(x + PAD, y + 4.5 * mm, "SHIP")
    ship_kw = c.stringWidth("SHIP  ", font_bold, 6.8)
    c.setFont(font_bold, 7.9); c.setFillColor(INK2)
    c.drawString(x + PAD + ship_kw, y + 4.5 * mm, date_str)

    div1_x = x + PAD + ship_kw + c.stringWidth(date_str, font_bold, 7.9) + 4 * mm
    c.setStrokeColor(LINE); c.setLineWidth(0.85)
    c.line(div1_x, y + 1.5 * mm, div1_x, y + 6 * mm)

    c.setFont(font_bold, 6.8); c.setFillColor(MUTED)
    c.drawString(div1_x + 3 * mm, y + 4.5 * mm, "ORIGIN")
    orig_kw = c.stringWidth("ORIGIN  ", font_bold, 6.8)
    c.setFont(font_bold, 7.9); c.setFillColor(INK2)
    c.drawString(div1_x + 3 * mm + orig_kw, y + 4.5 * mm, "KOR")

    c.setFont(font_bold, 7.9); c.setFillColor(NAVY)
    c.drawRightString(x + W - PAD, y + 4.5 * mm, "SINCERELY Co.")

    c.setStrokeColor(colors.HexColor("#333333"))
    c.setLineWidth(1.0)
    c.rect(x, y, W, H, stroke=1, fill=0)


# ────────────────────────────────────────────────────────────────────────────
# PDF 생성 (쉬핑마크 + 외박스 라벨 교차)
# ────────────────────────────────────────────────────────────────────────────
def generate_combined_pdf(records: list, output) -> int:
    font, font_bold = register_fonts()
    c = rl_canvas.Canvas(output, pagesize=(LABEL_W, LABEL_H))
    count = 0
    for rec in records:
        for box in rec["boxes"]:
            draw_shipping_mark(
                c, 0, 0, box, rec["to_num"], rec["date"],
                rec["company"], rec["consignee_name"], rec["consignee_addr"],
                font, font_bold,
            )
            c.showPage()
            draw_carton_label(
                c, 0, 0, box, rec["to_num"], rec["date"],
                rec["company"], font, font_bold,
            )
            c.showPage()
            count += 2
    c.save()
    return count


# ────────────────────────────────────────────────────────────────────────────
# V3140 통합 라벨 (98.73 × 139 mm, portrait) — MECE: 한 장에 모든 정보
#
# 레이아웃 (위→아래):
#   Header  13mm  SINCERELY(좌) | C/No. X/Y + SIZE(우)
#   Meta    24mm  TO / PO / ORIGIN 3행
#   ─────────────────────────────
#   Consignee 22mm  수취인 회사명 + 주소 + 담당자
#   ─────────────────────────────
#   Contents  18mm  CONTENTS 레이블 + 품목명
#   ─────────────────────────────
#   QTY area  ~42mm  QTY + 수량 + 잔여분 (나머지 공간 활용)
#   Footer    10mm  SHIP DATE | MADE IN KOREA | SINCERELY Co.
# ────────────────────────────────────────────────────────────────────────────
def draw_unified_label_v3140(c: rl_canvas.Canvas, x: float, y: float,
                              box: dict, to_num: str, date_str: str,
                              company: str, consignee_name: str, consignee_addr: str,
                              font: str, font_bold: str):
    W, H   = CELL_W, CELL_H
    PAD    = 5 * mm
    NAVY   = colors.HexColor("#0b2747")
    INK    = colors.HexColor("#0f0f10")
    INK2   = colors.HexColor("#3a3a3d")
    MUTED  = colors.HexColor("#7c7c82")
    MUTED2 = colors.HexColor("#9aa0a8")
    LINE   = colors.HexColor("#d8d9dd")

    def sep(ypos: float):
        c.setStrokeColor(LINE); c.setLineWidth(0.65)
        c.line(x, ypos, x + W, ypos)

    # ── 헤더 (navy, 13mm): SINCERELY 좌 | C/No. + SIZE 우 ─────────────────
    HDR_H = 13 * mm
    HDR_Y = y + H - HDR_H
    c.setFillColor(NAVY)
    c.rect(x, HDR_Y, W, HDR_H, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont(font_bold, 13)
    c.drawString(x + PAD, HDR_Y + 7 * mm, "SINCERELY")
    c.setFont(font, 5.5)
    c.setFillColor(colors.HexColor("#9cc0e8"))
    c.drawString(x + PAD, HDR_Y + 2.5 * mm, "신시어리  ·  Seoul, Korea")

    # 우측: C/No. 크게, SIZE 작게
    cno = f"C/No. {box['box_num']} / {box['total_boxes']}"
    cno_fs = 14
    while c.stringWidth(cno, font_bold, cno_fs) > W / 2 - PAD and cno_fs > 9:
        cno_fs -= 1
    c.setFont(font_bold, cno_fs); c.setFillColor(colors.white)
    c.drawRightString(x + W - PAD, HDR_Y + 7 * mm, cno)
    c.setFont(font, 6); c.setFillColor(colors.HexColor("#9cc0e8"))
    c.drawRightString(x + W - PAD, HDR_Y + 2.5 * mm, f"SIZE  {box['size']}형")

    # ── Meta (24mm): TO / PO / ORIGIN 3행 ─────────────────────────────────
    META_H = 24 * mm
    META_Y = HDR_Y - META_H
    sep(META_Y)

    for i, (k, v) in enumerate([
        ("TO",     to_num),
        ("PO",     (company or "")[:24]),
        ("ORIGIN", "KOREA"),
    ]):
        ry = HDR_Y - (6 * mm + i * 7 * mm)
        c.setFont(font_bold, 6.5); c.setFillColor(MUTED)
        c.drawString(x + PAD, ry, k)
        c.setFont(font_bold, 8); c.setFillColor(INK)
        c.drawString(x + PAD + 14 * mm, ry, v)

    # ── Consignee (22mm): 수취인 회사명 + 주소 + 담당자 ────────────────────
    CONS_H = 22 * mm
    CONS_Y = META_Y - CONS_H
    sep(CONS_Y)

    consignee_label = company.split("-", 1)[-1] if "-" in company else company
    C_TOP = META_Y - 3 * mm
    c.setFont(font_bold, 5.5); c.setFillColor(MUTED)
    c.drawString(x + PAD, C_TOP, "CONSIGNEE  /  수취인")
    c.setFont(font_bold, 12); c.setFillColor(INK)
    c.drawString(x + PAD, C_TOP - 7.5 * mm, (consignee_label or "—")[:18])
    if consignee_addr:
        c.setFont(font, 6); c.setFillColor(MUTED)
        c.drawString(x + PAD, C_TOP - 13.5 * mm, consignee_addr[:32])
    if consignee_name:
        c.setFont(font_bold, 7); c.setFillColor(INK2)
        c.drawString(x + PAD, C_TOP - 18.5 * mm, f"담당  {consignee_name}")

    # ── Contents (18mm): 품목명 ─────────────────────────────────────────────
    CONT_H = 18 * mm
    CONT_Y = CONS_Y - CONT_H
    sep(CONT_Y)

    CONT_TOP = CONS_Y - 4 * mm
    c.setFont(font_bold, 6.5); c.setFillColor(MUTED)
    c.drawString(x + PAD, CONT_TOP, "CONTENTS")

    item_text = box["item"]
    item_fs = 20
    while c.stringWidth(item_text, font_bold, item_fs) > W - 2 * PAD and item_fs > 11:
        item_fs -= 1
    c.setFont(font_bold, item_fs); c.setFillColor(INK)
    c.drawString(x + PAD, CONT_TOP - 10 * mm, item_text)

    # ── QTY + 잔여분 (나머지 공간 전부) ────────────────────────────────────
    FTR_H     = 10 * mm
    QTY_LBL_Y = CONT_Y - 8 * mm
    QTY_NUM_Y = CONT_Y - 24 * mm   # 30pt 수량 baseline

    c.setFont(font_bold, 6.5); c.setFillColor(MUTED)
    c.drawString(x + PAD, QTY_LBL_Y, "QTY")

    m_qty    = re.match(r"^(\d+)(?:\+(\d+))?", box["qty"])
    main_qty = m_qty.group(1) if m_qty else box["qty"]
    extra    = m_qty.group(2) if m_qty else None

    c.setFont(font_bold, 30); c.setFillColor(INK)
    c.drawString(x + PAD, QTY_NUM_Y, main_qty)
    cur_x = x + PAD + c.stringWidth(main_qty, font_bold, 30)

    if extra:
        c.setFont(font_bold, 9); c.setFillColor(MUTED2)
        c.drawString(cur_x + 1 * mm, QTY_NUM_Y + 4 * mm, "+")
        cur_x += 1 * mm + c.stringWidth("+", font_bold, 9)
        c.setFont(font_bold, 20); c.setFillColor(INK2)
        c.drawString(cur_x + 1 * mm, QTY_NUM_Y + 1 * mm, extra)
        cur_x += 1 * mm + c.stringWidth(extra, font_bold, 20)

    c.setFont(font_bold, 16); c.setFillColor(INK2)
    c.drawString(cur_x + 2 * mm, QTY_NUM_Y + 1 * mm, "EA")

    remainders = box.get("remainder_items", [])
    if remainders:
        REM_Y = QTY_NUM_Y - 10 * mm
        rem_text = "+  " + "   ".join(
            f"{r['name']} {r['qty']}" if r['qty'] else r['name']
            for r in remainders
        )
        c.setFont(font, 6.5); c.setFillColor(MUTED)
        c.drawString(x + PAD, REM_Y, rem_text[:55])

    # ── 푸터 (10mm): SHIP DATE | MADE IN KOREA | SINCERELY Co. ────────────
    c.setFillColor(colors.HexColor("#fafbfd"))
    c.rect(x, y, W, FTR_H, fill=1, stroke=0)
    sep(y + FTR_H)

    c.setFont(font_bold, 6.5); c.setFillColor(MUTED)
    c.drawString(x + PAD, y + 3.5 * mm, "SHIP")
    skw = c.stringWidth("SHIP  ", font_bold, 6.5)
    c.setFont(font_bold, 7); c.setFillColor(INK2)
    c.drawString(x + PAD + skw, y + 3.5 * mm, date_str)

    c.setFont(font_bold, 7); c.setFillColor(NAVY)
    c.drawCentredString(x + W / 2, y + 3.5 * mm, "MADE IN KOREA")

    c.setFont(font_bold, 7); c.setFillColor(NAVY)
    c.drawRightString(x + W - PAD, y + 3.5 * mm, "SINCERELY Co.")

    # ── 외곽선 ──────────────────────────────────────────────────────────────
    c.setStrokeColor(colors.HexColor("#333333")); c.setLineWidth(0.8)
    c.rect(x, y, W, H, stroke=1, fill=0)


# ────────────────────────────────────────────────────────────────────────────
# 에러 페이지 (전체 A4 — 데이터 오류 시)
# ────────────────────────────────────────────────────────────────────────────
def _draw_error_page(c: rl_canvas.Canvas, rec: dict, font: str, font_bold: str):
    PW, PH = A4
    M = 15 * mm
    RED    = colors.HexColor("#C0392B")
    ORANGE = colors.HexColor("#E67E22")
    INK    = colors.HexColor("#0f0f10")
    MUTED  = colors.HexColor("#7c7c82")
    LGRAY  = colors.HexColor("#F2F2F2")

    HDR_H = 22 * mm
    y = PH - M

    c.setFillColor(RED)
    c.rect(0, y - HDR_H, PW, HDR_H, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont(font_bold, 28)
    c.drawString(M, y - 17 * mm, "데이터 오류")
    c.setFont(font_bold, 10)
    c.drawRightString(PW - M, y - 11 * mm, rec.get("date", ""))
    c.drawRightString(PW - M, y - 18 * mm, rec.get("to_num", ""))
    y -= HDR_H + 10 * mm

    c.setFont(font_bold, 13); c.setFillColor(RED)
    c.drawString(M, y, rec.get("error_title", "포장 내역 파싱 실패"))
    y -= 8 * mm
    c.setFont(font, 10); c.setFillColor(INK)
    c.drawString(M, y, "아래 포장 내역 내용을 확인하고 올바른 형식으로 재입력해 주세요.")
    y -= 5 * mm
    c.setFont(font, 9); c.setFillColor(MUTED)
    c.drawString(M, y, "형식 예시:  품목명  수량 * 박스수  규격  (예: 15 * 6 중대)")
    y -= 10 * mm

    c.setStrokeColor(ORANGE); c.setLineWidth(1.5)
    c.line(M, y, PW - M, y)
    y -= 7 * mm

    c.setFont(font_bold, 8.5); c.setFillColor(MUTED)
    c.drawString(M, y, "현재 입력된 외박스 포장 내역:")
    y -= 6 * mm

    c.setFillColor(LGRAY)
    txt_lines = (rec.get("error_text") or "").splitlines()
    BOX_H = min(len(txt_lines) + 2, 22) * 5.5 * mm + 6 * mm
    c.rect(M, y - BOX_H, PW - 2 * M, BOX_H, fill=1, stroke=0)
    c.setStrokeColor(colors.HexColor("#DDDDDD")); c.setLineWidth(0.8)
    c.rect(M, y - BOX_H, PW - 2 * M, BOX_H, fill=0, stroke=1)

    ty = y - 5 * mm
    c.setFont(font, 9); c.setFillColor(INK)
    for line in txt_lines[:20]:
        c.drawString(M + 4 * mm, ty, line[:70])
        ty -= 5.5 * mm
    if len(txt_lines) > 20:
        c.setFont(font, 8); c.setFillColor(MUTED)
        c.drawString(M + 4 * mm, ty, f"... (+ {len(txt_lines) - 20}줄 생략)")

    c.setFillColor(MUTED); c.setFont(font, 7.5)
    c.drawCentredString(PW / 2, M / 2,
                        f"SINCERELY Co., Ltd.  ·  데이터 오류  ·  {rec.get('to_num', '')}")


# ────────────────────────────────────────────────────────────────────────────
# V3140 A4 4-up PDF: 카톤 1개 = 통합 라벨 1장 → 4카톤/페이지
# ────────────────────────────────────────────────────────────────────────────
def generate_v3140_pdf(records: list, output) -> int:
    font, font_bold = register_fonts()
    c = rl_canvas.Canvas(output, pagesize=A4)
    pages = 0

    for rec in records:
        if rec.get("is_error"):
            _draw_error_page(c, rec, font, font_bold)
            c.showPage()
            pages += 1
            continue
        boxes = rec["boxes"]
        for i in range(0, len(boxes), 4):
            chunk = boxes[i:i + 4]
            for slot, box in enumerate(chunk):
                cx, cy = CELL_ORIGINS[slot]
                draw_unified_label_v3140(
                    c, cx, cy, box, rec["to_num"], rec["date"],
                    rec["company"], rec["consignee_name"], rec["consignee_addr"],
                    font, font_bold,
                )
            c.showPage()
            pages += 1

    c.save()
    return pages


# ────────────────────────────────────────────────────────────────────────────
def _demo_records() -> list:
    """Airtable 없이 테스트용 샘플 데이터 (PNA51270-펄어비스 기준)"""
    boxes = []
    for i in range(1, 21):
        boxes.append({"box_num": i, "total_boxes": 21, "item": "Solid 커스텀 G형박스 키트",
                       "qty": "12", "size": "대", "remainder_items": []})
    boxes.append({
        "box_num": 21, "total_boxes": 21,
        "item": "Solid 커스텀 G형박스 키트",
        "qty": "10+잔여분(디자이너 노트10,스탠드업 칫솔2,스펙트럼 컬러펜2,슬로건 다이어리3)",
        "size": "대",
        "remainder_items": [
            {"name": "디자이너 노트",  "qty": "10"},
            {"name": "스탠드업 칫솔", "qty": "2"},
            {"name": "스펙트럼 컬러펜","qty": "2"},
            {"name": "슬로건 다이어리","qty": "3"},
        ],
    })
    return [{
        "rec_id":         "recDEMO",
        "to_num":         "TO00016184",
        "date":           "2026-05-07",
        "company":        "PNA51270-펄어비스",
        "consignee_name": "조연하",
        "consignee_addr": "경기도 과천시 과천대로2길 48 펄어비스 지하1층",
        "boxes":          boxes,
    }]


def main():
    parser = argparse.ArgumentParser(description="쉬핑마크 + 외박스 라벨 통합 PDF 생성기")
    parser.add_argument("--lr-id",        help="logistics_release record ID")
    parser.add_argument("--to-num",       help="TO번호 (예: TO00016184)")
    parser.add_argument("--date",         help="출고 요청일 필터 (예: 2026-05-07)")
    parser.add_argument("--upload-field", help="업로드할 Airtable 필드 ID")
    parser.add_argument("--paper",        choices=["150x100", "v3140"], default="v3140",
                        help="라벨지 규격: 150x100(기본 낱장) / v3140(A4 4-up, 기본)")
    parser.add_argument("--dry-run",      action="store_true", help="데이터 출력만, PDF 미생성")
    parser.add_argument("--demo",         action="store_true", help="Airtable 없이 샘플 데이터로 테스트")
    args = parser.parse_args()

    if args.demo:
        records = _demo_records()
        print(f"[DEMO] 샘플 데이터 {len(records[0]['boxes'])}카톤 사용")
    else:
        if not PAT:
            print("[ERROR] AIRTABLE_SERPA_PAT 환경변수를 설정하세요")
            sys.exit(1)
        lr_id  = getattr(args, "lr_id", None)
        to_num = getattr(args, "to_num", None)
        print("▶ logistics_release 조회 중…")
        records = fetch_records(lr_id=lr_id, to_num=to_num, date_str=args.date)
        if not records:
            print("조회 결과 없음")
            return

    for r in records:
        n_boxes = len(r["boxes"])
        if args.paper == "v3140":
            import math
            pages = math.ceil(n_boxes / 4)
            print(f"  • {r['to_num']}  {r['date']}  {r['company']}  → {n_boxes}카톤 ({pages}장 A4)")
        else:
            print(f"  • {r['to_num']}  {r['date']}  {r['company']}  → {n_boxes}카톤 ({n_boxes*2}페이지)")
        for b in r["boxes"]:
            rem_str = f"  [{', '.join(x['name'] for x in b['remainder_items'])}]" \
                      if b["remainder_items"] else ""
            print(f"      박스{b['box_num']:>2}/{b['total_boxes']}  [{b['size']:4}형]  "
                  f"{b['item'][:25]:<25}  {b['qty']}개{rem_str}")

    if args.dry_run:
        print("\n[dry-run] PDF 생성 건너뜀")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    if args.demo:
        suffix = "_DEMO"
    elif getattr(args, "lr_id", None):
        suffix = f"_{args.lr_id[:8]}"
    elif getattr(args, "to_num", None):
        suffix = f"_{args.to_num}"
    elif getattr(args, "date", None):
        suffix = f"_{args.date}"
    else:
        suffix = ""

    paper_tag = "_v3140" if args.paper == "v3140" else ""
    filename = f"통합라벨{paper_tag}{suffix}_{stamp}.pdf"

    buf = BytesIO()
    if args.paper == "v3140":
        n = generate_v3140_pdf(records, buf)
        print(f"\n  규격: V3140 (A4 4-up, {CELL_W/mm:.2f}×{CELL_H/mm:.2f}mm × 4셀)")
    else:
        n = generate_combined_pdf(records, buf)
        print(f"\n  규격: 150×100mm 낱장 ({n}페이지)")
    pdf_bytes = buf.getvalue()

    upload_field = getattr(args, "upload_field", None)
    if upload_field and not args.demo and len(records) == 1:
        print(f"▶ {filename} 업로드 중…")
        clear_attachment_field(records[0]["rec_id"], upload_field)
        upload_via_content_api(records[0]["rec_id"], upload_field, filename, pdf_bytes)
    else:
        from pathlib import Path
        out = Path(os.getenv("PDF_OUTPUT_DIR", r"C:\Users\yjisu\Desktop")) / filename
        out.write_bytes(pdf_bytes)
        print(f"✅ 완료 — {n}장 저장: {out}")


if __name__ == "__main__":
    main()
