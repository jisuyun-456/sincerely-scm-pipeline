"""
출고확인서_tms.py
────────────────────────────────────────────────────────────────────────────
TMS Shipment 테이블 기반 고객용 출고확인서 PDF 생성기

사용법:
  python scripts/출고확인서_tms.py                        # 오늘 출하 전체
  python scripts/출고확인서_tms.py --date 2026-04-22      # 날짜 필터
  python scripts/출고확인서_tms.py --sc-id SC00027614     # 단건
  python scripts/출고확인서_tms.py --dry-run              # 미리보기만
  python scripts/출고확인서_tms.py --no-upload            # 로컬 저장만
"""

import argparse, base64, os, re, sys, time
from datetime import date, datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib.styles import ParagraphStyle

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

# ── 상수 ──────────────────────────────────────────────────────────────────────
BASE_ID           = "app4x70a8mOrIKsMf"
TBL_SHIP          = "tbllg1JoHclGYer7m"
ATTACH_FIELD_NAME = "출고확인서_python"

API_KEY  = os.getenv("AIRTABLE_PAT", "") or os.getenv("AIRTABLE_API_KEY", "")
HEADERS  = {"Authorization": f"Bearer {API_KEY}"}

FONT_REG = r"C:\Windows\Fonts\malgun.ttf"
FONT_BLD = r"C:\Windows\Fonts\malgunbd.ttf"
OUT_DIR  = Path(r"C:\Users\yjisu\Desktop\SCM_WORK")

SENDER_NAME    = "신시어리"
SENDER_PERSON  = "신시어리 물류팀"
SENDER_PHONE   = "010-4979-1306"
SENDER_ADDRESS = "서울특별시 성동구 왕십리로 88 노벨빌딩 4층"

NOTICE_LINES = [
    "✓ 최초 공유된 하차 정보와 다른 경우 추가비용이 발생할 수 있습니다."
    " (화물엘레베이터 및 주차장 유무, 수령지 정보 등)",
    "✓ 물품수령 후 7일 이내 제품 하자가 있으신 경우 신시어리 담당자에게 연락주세요."
    " 빠르게 대응하도록 하겠습니다.",
]

A4_W, A4_H = A4
MARGIN  = 15 * mm
INNER_W = A4_W - 2 * MARGIN

# ── 컬러 팔레트 ───────────────────────────────────────────────────────────────
COLOR_HEADER_BG = colors.HexColor("#1a3a5c")
COLOR_SENDER_BG = colors.HexColor("#EBF8FF")
COLOR_RECV_BG   = colors.HexColor("#F0FFF4")
COLOR_BOX_BG    = colors.HexColor("#FFFDE7")
COLOR_SECTION   = colors.HexColor("#2c5282")
COLOR_TBL_HDR   = colors.HexColor("#2d3748")
COLOR_TBL_ALT   = colors.HexColor("#F7FAFC")
COLOR_BORDER    = colors.HexColor("#CBD5E0")
COLOR_MUTED     = colors.HexColor("#4A5568")
COLOR_WHITE     = colors.white

# 캐시
_SCHEMA_CACHE: dict = {}
_ATTACH_FIELD_ID: str | None = None
_LOC_TABLE_ID: str | None = None

ITEM_RE      = re.compile(r"^(?P<name>.+?)\s+(?P<qty>\d+)(?:\+(?P<extra>\d+))?\s*$")
STOCK_ITEM_RE = re.compile(r"^(?P<pt>PT\S+?)-(?P<name>.+?)\s*\|\|\s*\S+\s+(?P<qty>\d+)개\s*$")


# ── 폰트 ──────────────────────────────────────────────────────────────────────
def register_fonts() -> tuple[str, str]:
    try:
        pdfmetrics.registerFont(TTFont("Malgun",     FONT_REG))
        pdfmetrics.registerFont(TTFont("MalgunBold", FONT_BLD))
        return "Malgun", "MalgunBold"
    except Exception:
        return "Helvetica", "Helvetica-Bold"


# ── Airtable REST 헬퍼 ────────────────────────────────────────────────────────
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


def fetch_by_ids(table_id: str, record_ids: list[str], batch_size: int = 30) -> list[dict]:
    if not record_ids:
        return []
    result = []
    for i in range(0, len(record_ids), batch_size):
        batch = record_ids[i:i + batch_size]
        formula = "OR(" + ",".join(f'RECORD_ID()="{rid}"' for rid in batch) + ")"
        recs = airtable_get(table_id, {"filterByFormula": formula, "pageSize": 100})
        result.extend(recs)
        if i + batch_size < len(record_ids):
            time.sleep(0.2)
    return result


def get_table_schema(base_id: str) -> list[dict]:
    if base_id in _SCHEMA_CACHE:
        return _SCHEMA_CACHE[base_id]
    url = f"https://api.airtable.com/v0/meta/bases/{base_id}/tables"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    tables = r.json().get("tables", [])
    _SCHEMA_CACHE[base_id] = tables
    return tables


def resolve_attach_field_id() -> str | None:
    global _ATTACH_FIELD_ID
    if _ATTACH_FIELD_ID:
        return _ATTACH_FIELD_ID
    for tbl in get_table_schema(BASE_ID):
        if tbl["id"] == TBL_SHIP:
            for fld in tbl.get("fields", []):
                if fld["name"] == ATTACH_FIELD_NAME:
                    _ATTACH_FIELD_ID = fld["id"]
                    return _ATTACH_FIELD_ID
    return None


def resolve_location_table_id() -> str | None:
    global _LOC_TABLE_ID
    if _LOC_TABLE_ID:
        return _LOC_TABLE_ID
    for tbl in get_table_schema(BASE_ID):
        if tbl["id"] == TBL_SHIP:
            for fld in tbl.get("fields", []):
                if fld["name"] == "Location":
                    linked = fld.get("options", {}).get("linkedTableId")
                    if linked:
                        _LOC_TABLE_ID = linked
                        return linked
    return None


# ── 필드 헬퍼 ────────────────────────────────────────────────────────────────
def get_field(f: dict, key: str, default: str = "") -> str:
    val = f.get(key, default)
    if val is None:
        return default
    if isinstance(val, list):
        items = [str(v) for v in val if v is not None]
        return ", ".join(items) if items else default
    if isinstance(val, dict):
        return str(val.get("name", "")) if val else default
    return str(val) if val else default


def get_lookup_first(f: dict, key: str) -> str:
    val = f.get(key)
    if not val:
        return ""
    if isinstance(val, dict):
        for record_values in val.get("valuesByLinkedRecordId", {}).values():
            if record_values:
                return str(record_values[0])
        return ""
    if isinstance(val, list):
        return str(val[0]) if val else ""
    return str(val)


def parse_ship_date(raw: str) -> str:
    if not raw:
        return ""
    try:
        weekdays = ["월", "화", "수", "목", "금", "토", "일"]
        dt = datetime.fromisoformat(raw[:10])
        return f"{dt.year}-{dt.month:02d}-{dt.day:02d} ({weekdays[dt.weekday()]})"
    except Exception:
        return raw[:10] if raw else ""


def extract_item_name(s: str) -> str:
    return re.sub(r"\s+\d+(\+\d+)?\s*$", "", s.strip()).strip()


def split_order_items(order_raw: str, actual_list: list[str]) -> list[str]:
    if not actual_list or not order_raw:
        return [order_raw] if order_raw else [""]
    item_names = [extract_item_name(a) for a in actual_list]
    result, remaining = [], order_raw.strip()
    for i, name in enumerate(item_names):
        if not name or name not in remaining:
            result.append("")
            continue
        idx = remaining.find(name)
        if idx == -1:
            result.append("")
            continue
        from_here = remaining[idx:]
        if i + 1 < len(item_names) and item_names[i + 1] and item_names[i + 1] in from_here:
            next_idx = from_here.find(item_names[i + 1])
            chunk = from_here[:next_idx].strip()
            remaining = from_here[next_idx:]
        else:
            chunk = from_here.strip()
            remaining = ""
        result.append(chunk)
    return result if result else [order_raw]


def parse_stock_items(raw: str) -> list[dict]:
    """
    '재고 출하 품목' 필드 파싱.
    형식: "PT2854-배송용외박스(스탠다드)(S-280) || 베스트원 30개\n..."
    """
    rows = []
    for i, line in enumerate(str(raw or "").split("\n"), 1):
        line = line.strip()
        if not line:
            continue
        m = STOCK_ITEM_RE.match(line)
        if m:
            rows.append({
                "no":   i,
                "pt":   m.group("pt"),
                "name": m.group("name").strip(),
                "qty":  m.group("qty"),
            })
        else:
            # fallback: || 구분자로만 나눠서 처리
            parts = line.split("||")
            name_part = parts[0].strip()
            qty_str   = ""
            if len(parts) > 1:
                qty_m = re.search(r"(\d+)개", parts[1])
                qty_str = qty_m.group(1) if qty_m else ""
            # PT코드 분리
            pt_m = re.match(r"(PT\S+?)-(.+)", name_part)
            pt   = pt_m.group(1) if pt_m else ""
            name = pt_m.group(2).strip() if pt_m else name_part
            rows.append({"no": i, "pt": pt, "name": name, "qty": qty_str})
    return rows


def parse_items(actual_raw: str, order_raw: str) -> list[dict]:
    """레거시 호환용 — 현재는 parse_stock_items 사용"""
    actual_lines = [x.strip() for x in str(actual_raw or "").split("\n") if x.strip()]
    order_list   = split_order_items(order_raw or "", actual_lines)

    rows = []
    max_len = max(len(actual_lines), len(order_list), 1)
    for i in range(max_len):
        actual_str = actual_lines[i] if i < len(actual_lines) else ""
        order_str  = order_list[i]   if i < len(order_list)   else ""

        m = ITEM_RE.match(actual_str)
        if m:
            name        = m.group("name").strip()
            shipped_qty = m.group("qty")
            extra       = m.group("extra") or ""
        else:
            name        = actual_str or order_str
            shipped_qty = ""
            extra       = ""

        om = ITEM_RE.match(order_str)
        ordered_qty = om.group("qty") if om else ""

        rows.append({
            "no":          i + 1,
            "pt":          "",
            "name":        name,
            "qty":         f"{shipped_qty} (+{extra})" if extra else shipped_qty,
        })
    return rows


# ── 데이터 조립 ───────────────────────────────────────────────────────────────
def fetch_shipments(filter_date: str | None, sc_id: str | None) -> list[dict]:
    if sc_id:
        formula = f'{{SC id}}="{sc_id}"'
    else:
        d = filter_date or date.today().strftime("%Y-%m-%d")
        # IS_SAME은 datetime 타입에 따라 미동작 → IS_AFTER/IS_BEFORE로 날짜 범위 처리
        from datetime import datetime, timedelta
        prev = (datetime.strptime(d, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        next_ = (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        formula = f'AND(IS_AFTER({{출하확정일}},"{prev}"),IS_BEFORE({{출하확정일}},"{next_}"))'

    params = {
        "pageSize": 100,
        "filterByFormula": formula,
    }
    return airtable_get(TBL_SHIP, params)


def fetch_locations(loc_ids: list[str]) -> dict[str, str]:
    if not loc_ids:
        return {}
    loc_tbl = resolve_location_table_id()
    if not loc_tbl:
        return {}
    recs = fetch_by_ids(loc_tbl, loc_ids)
    result = {}
    for r in recs:
        f = r.get("fields", {})
        name = f.get("Name") or f.get("이름") or f.get("name") or ""
        result[r["id"]] = str(name)
    return result


def build_doc(rec: dict, loc_map: dict) -> dict:
    f = rec["fields"]

    # 출고 대기 좌표 — 롤업 필드 우선, 없으면 linked 조회 결과 사용
    location_str = get_field(f, "Location 명칭")
    if not location_str:
        loc_ids = f.get("Location") or []
        if isinstance(loc_ids, list):
            location_str = ", ".join(loc_map.get(lid, "") for lid in loc_ids if loc_map.get(lid))

    # 배송요청 번호 — 리스트 join (최대 3개)
    to_list = f.get("배송요청_lookup") or []
    if isinstance(to_list, list):
        to_str = ", ".join(str(x) for x in to_list[:3] if x)
        if len(to_list) > 3:
            to_str += f" 외 {len(to_list)-3}건"
    else:
        to_str = get_lookup_first(f, "배송요청_lookup")

    # 품목 — 재고 출하 품목 필드 우선 (실제 데이터)
    stock_raw = get_field(f, "재고 출하 품목")
    if stock_raw.strip():
        items = parse_stock_items(stock_raw)
    else:
        actual_raw = f.get("최종 출고 품목 및 수량") or ""
        order_raw  = get_field(f, "최종 출하 품목")
        items      = parse_items(actual_raw, order_raw)

    # 수신처 정보 — 리스트 래핑 필드 처리
    customer = get_field(f, "회사명") or get_field(f, "입하장소")
    recipient      = get_field(f, "수령인")
    recipient_phone = get_field(f, "수령인(연락처)")
    delivery_addr  = get_field(f, "수령인(주소)")

    # 박스 수량 — 직접 필드 없으면 아이템 수량 합계 표기 생략
    box_qty = get_field(f, "최종 외박스 수량 값") or get_field(f, "Total_CBM")

    return {
        "record_id":      rec["id"],
        "sc_id":          get_field(f, "SC id"),
        "to_no":          to_str,
        "location":       location_str,
        "ship_date":      parse_ship_date(get_field(f, "출하확정일")),
        "delivery_type":  get_field(f, "배송 방식"),
        "delivery_time":  get_field(f, "배송슬롯"),
        "customer":       customer,
        "recipient":      recipient,
        "recipient_phone": recipient_phone,
        "delivery_addr":  delivery_addr,
        "unload_service": get_field(f, "하차 서비스"),
        "box_qty":        box_qty,
        "items":          items,
    }


# ── PDF 드로잉 헬퍼 ──────────────────────────────────────────────────────────
def _para(text: str, font: str, size: float, color=colors.black,
          align: str = "LEFT") -> Paragraph:
    align_map = {"LEFT": 0, "CENTER": 1, "RIGHT": 2}
    st = ParagraphStyle(
        "s", fontName=font, fontSize=size, textColor=color,
        leading=size * 1.4, alignment=align_map.get(align, 0),
    )
    return Paragraph(str(text) if text else "", st)


def _draw_table(c: rl_canvas.Canvas, tbl: Table, x: float, y: float,
                max_w: float, max_h: float) -> float:
    _, h = tbl.wrapOn(c, max_w, max_h)
    tbl.drawOn(c, x, y - h)
    return h


def _cell_style_base(font: str, font_bold: str) -> list:
    return [
        ("FONTNAME",      (0, 0), (-1, -1), font),
        ("FONTSIZE",      (0, 0), (-1, -1), 8.5),
        ("GRID",          (0, 0), (-1, -1), 0.4, COLOR_BORDER),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
    ]


# ── PDF 섹션 드로어 ──────────────────────────────────────────────────────────
def _draw_banner(c: rl_canvas.Canvas, y: float, doc: dict,
                 font: str, font_bold: str) -> float:
    BH = 14 * mm
    c.setFillColor(COLOR_HEADER_BG)
    c.rect(MARGIN, y - BH, INNER_W, BH, fill=1, stroke=0)
    c.setFillColor(COLOR_WHITE)
    c.setFont(font_bold, 16)
    c.drawCentredString(A4_W / 2, y - BH + 4 * mm, "출  고  확  인  서")
    c.setFont(font, 8)
    right_info = f"{doc['sc_id']}   {doc['ship_date']}"
    c.drawRightString(MARGIN + INNER_W - 3 * mm, y - BH + 4 * mm, right_info)
    return y - BH - 2 * mm


def _draw_summary_row(c: rl_canvas.Canvas, y: float, doc: dict,
                      font: str, font_bold: str) -> float:
    LIGHT = colors.HexColor("#F5F5F5")
    col1 = 60 * mm
    col2 = 60 * mm
    col3 = INNER_W - col1 - col2

    def lbl(t): return _para(t, font, 8, COLOR_MUTED)
    def val(t, bold=False): return _para(t, font_bold if bold else font, 8.5)

    tbl = Table(
        [[lbl("TO. No."), val(doc["to_no"], bold=True),
          lbl("SC id"),   val(doc["sc_id"]),
          lbl("출고 대기 좌표"), val(doc["location"])]],
        colWidths=[18*mm, col1-18*mm, 16*mm, col2-16*mm, 24*mm, col3-24*mm],
    )
    cs = _cell_style_base(font, font_bold)
    cs += [
        ("BACKGROUND", (0, 0), (0, 0), LIGHT),
        ("BACKGROUND", (2, 0), (2, 0), LIGHT),
        ("BACKGROUND", (4, 0), (4, 0), LIGHT),
    ]
    tbl.setStyle(TableStyle(cs))
    h = _draw_table(c, tbl, MARGIN, y, INNER_W, 20 * mm)
    return y - h - 3 * mm


def _draw_info_block(c: rl_canvas.Canvas, y: float, doc: dict,
                     font: str, font_bold: str) -> float:
    HALF = (INNER_W - 2 * mm) / 2
    LBL_W = 22 * mm
    VAL_W = HALF - LBL_W

    def lbl(t): return _para(t, font, 8, COLOR_MUTED)
    def val(t, bold=False): return _para(t, font_bold if bold else font, 8.5)

    sender_rows = [
        [lbl("발송처"),   val(SENDER_NAME)],
        [lbl("발송인"),   val(SENDER_PERSON)],
        [lbl("연락처"),   val(SENDER_PHONE)],
        [lbl("발송지"),   _para(SENDER_ADDRESS, font, 8)],
        [lbl("출하일자"), val(doc["ship_date"])],
        [lbl("배송 방식"), val(doc["delivery_type"])],
        [lbl("배송시간"), val(doc["delivery_time"])],
    ]
    recv_rows = [
        [lbl("고객사"),    val(doc["customer"])],
        [lbl("수령인"),    val(doc["recipient"])],
        [lbl("연락처"),    val(doc["recipient_phone"])],
        [lbl("배송지"),    _para(doc["delivery_addr"], font, 8)],
        [lbl("하차 서비스"), val(doc["unload_service"])],
        [lbl(""), val("")],
        [lbl(""), val("")],
    ]

    def make_side(rows, bg, header_text) -> Table:
        # 섹션 헤더 행 삽입
        header_row = [_para(header_text, font_bold, 9, COLOR_SECTION, "LEFT"), ""]
        all_rows   = [header_row] + rows
        t = Table(all_rows, colWidths=[LBL_W, VAL_W])
        cs = _cell_style_base(font, font_bold)
        cs += [
            ("BACKGROUND",  (0, 0), (-1,  0), colors.HexColor("#DBEAFE") if bg == COLOR_SENDER_BG else colors.HexColor("#DCFCE7")),
            ("BACKGROUND",  (0, 1), (-1, -1), bg),
            ("FONTNAME",    (0, 0), (-1,  0), font_bold),
            ("SPAN",        (0, 0), ( 1,  0)),
            ("BACKGROUND",  (0, 1), (0,  -1), bg),
        ]
        t.setStyle(TableStyle(cs))
        return t

    tbl_send = make_side(sender_rows, COLOR_SENDER_BG, "▌ 발송 정보")
    tbl_recv = make_side(recv_rows,   COLOR_RECV_BG,   "▌ 수령 정보")

    _, hs = tbl_send.wrapOn(c, HALF, 60 * mm)
    _, hr = tbl_recv.wrapOn(c, HALF, 60 * mm)
    block_h = max(hs, hr)

    tbl_send.drawOn(c, MARGIN, y - block_h)
    tbl_recv.drawOn(c, MARGIN + HALF + 2 * mm, y - block_h)
    return y - block_h - 3 * mm


def _draw_box_block(c: rl_canvas.Canvas, y: float, doc: dict,
                    font: str, font_bold: str) -> float:
    box_qty = doc["box_qty"] or "—"
    tbl = Table(
        [[_para("총 박스 수량", font_bold, 10, COLOR_SECTION, "CENTER")],
         [_para(f"{box_qty} 박스", font_bold, 18, colors.black, "CENTER")]],
        colWidths=[INNER_W],
    )
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), COLOR_BOX_BG),
        ("BOX",           (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    h = _draw_table(c, tbl, MARGIN, y, INNER_W, 20 * mm)
    return y - h - 2 * mm


def _draw_signature_block(c: rl_canvas.Canvas, y: float,
                          font: str, font_bold: str) -> float:
    tbl = Table(
        [[_para("상품 및 박스 수량을 확인하고 서명합니다.", font_bold, 9),
          _para("(서명)  _________________", font, 9, align="RIGHT")]],
        colWidths=[INNER_W * 0.72, INNER_W * 0.28],
    )
    tbl.setStyle(TableStyle([
        ("BOX",           (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("GRID",          (0, 0), (-1, -1), 0.4, COLOR_BORDER),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
    ]))
    h = _draw_table(c, tbl, MARGIN, y, INNER_W, 15 * mm)
    return y - h - 3 * mm


def _draw_items_table(c: rl_canvas.Canvas, y: float, doc: dict,
                      font: str, font_bold: str) -> float:
    items = list(doc["items"] or [])

    # 최소 6행 보장
    while len(items) < 6:
        items.append({"no": len(items) + 1, "pt": "", "name": "", "qty": ""})

    # 헤더: No | PT코드 | 품목명 | 수량 | 확인□
    COL_W = [10*mm, 28*mm, 86*mm, 26*mm, 30*mm]
    header = [
        _para("No",     font_bold, 8.5, COLOR_WHITE, "CENTER"),
        _para("PT코드",  font_bold, 8.5, COLOR_WHITE, "CENTER"),
        _para("품목명",  font_bold, 8.5, COLOR_WHITE, "CENTER"),
        _para("수량",    font_bold, 8.5, COLOR_WHITE, "CENTER"),
        _para("확인 □",  font_bold, 8.5, COLOR_WHITE, "CENTER"),
    ]

    rows = [header]
    for itm in items:
        rows.append([
            _para(str(itm["no"]) if itm.get("name") else "", font, 8, align="CENTER"),
            _para(itm.get("pt", ""), font, 7.5, align="CENTER"),
            _para(itm.get("name", ""), font, 8.5),
            _para(itm.get("qty", ""), font, 8.5, align="CENTER"),
            _para("□" if itm.get("name") else "", font, 9, align="CENTER"),
        ])

    tbl = Table(rows, colWidths=COL_W)
    cs  = [
        ("BACKGROUND",    (0, 0), (-1, 0),  COLOR_TBL_HDR),
        ("FONTNAME",      (0, 0), (-1, 0),  font_bold),
        ("FONTSIZE",      (0, 0), (-1, 0),  8.5),
        ("ALIGN",         (0, 0), (-1, 0),  "CENTER"),
        ("FONTNAME",      (0, 1), (-1, -1), font),
        ("FONTSIZE",      (0, 1), (-1, -1), 8.5),
        ("GRID",          (0, 0), (-1, -1), 0.4, COLOR_BORDER),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, COLOR_TBL_ALT]),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
    ]
    tbl.setStyle(TableStyle(cs))
    h = _draw_table(c, tbl, MARGIN, y, INNER_W, A4_H)
    return y - h - 3 * mm


def _draw_notice(c: rl_canvas.Canvas, y: float, font: str) -> float:
    rows = [[_para(line, font, 8, COLOR_MUTED)] for line in NOTICE_LINES]
    tbl  = Table(rows, colWidths=[INNER_W])
    tbl.setStyle(TableStyle([
        ("BOX",           (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
    ]))
    h = _draw_table(c, tbl, MARGIN, y, INNER_W, 25 * mm)
    return y - h


# ── 페이지 그리기 ─────────────────────────────────────────────────────────────
def draw_confirmation(c: rl_canvas.Canvas, doc: dict, font: str, font_bold: str) -> None:
    c.setPageSize(A4)
    c.saveState()
    y = A4_H - MARGIN

    y = _draw_banner(c, y, doc, font, font_bold)
    y = _draw_summary_row(c, y, doc, font, font_bold)
    y = _draw_info_block(c, y, doc, font, font_bold)
    y = _draw_box_block(c, y, doc, font, font_bold)
    y = _draw_signature_block(c, y, font, font_bold)
    y = _draw_items_table(c, y, doc, font, font_bold)
    _draw_notice(c, y, font)

    # 푸터
    c.setFont(font, 7)
    c.setFillColor(COLOR_MUTED)
    today_str = date.today().strftime("%Y-%m-%d")
    c.drawRightString(MARGIN + INNER_W, MARGIN - 4 * mm,
                      f"발행: 신시어리 웨일즈 물류팀   출력: {today_str}")
    c.restoreState()


# ── Airtable Content API 업로드 ───────────────────────────────────────────────
def upload_via_content_api(record_id: str, field_id: str,
                            filename: str, pdf_bytes: bytes) -> bool:
    url = (f"https://content.airtable.com/v0/{BASE_ID}"
           f"/{record_id}/{field_id}/uploadAttachment")
    payload = {
        "contentType": "application/pdf",
        "filename":    filename,
        "file":        base64.b64encode(pdf_bytes).decode("ascii"),
    }
    try:
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        if r.status_code == 429:
            retry_after = int(r.headers.get("Retry-After", 10))
            print(f"  429 rate-limit, {retry_after}s 대기 후 재시도…")
            time.sleep(retry_after)
            r = requests.post(url, headers={"Authorization": f"Bearer {API_KEY}",
                                             "Content-Type": "application/json"},
                              json=payload, timeout=60)
        r.raise_for_status()
        print(f"  ✅ 업로드 완료: {filename}")
        return True
    except requests.HTTPError as e:
        print(f"  ❌ 업로드 실패 HTTP {e.response.status_code}: {e.response.text[:200]}")
        return False
    except Exception as e:
        print(f"  ❌ 업로드 실패: {e}")
        return False


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="출고확인서 TMS PDF 생성")
    parser.add_argument("--date",      help="출하일자 필터 (YYYY-MM-DD)")
    parser.add_argument("--sc-id",     help="SC id 단건 (예: SC00027614)")
    parser.add_argument("--dry-run",   action="store_true", help="미리보기만 (PDF 미생성)")
    parser.add_argument("--no-upload", action="store_true", help="로컬 저장만, Airtable 업로드 안 함")
    args = parser.parse_args()

    if not API_KEY:
        print("❌ AIRTABLE_PAT 환경변수 없음")
        sys.exit(1)

    font, font_bold = register_fonts()

    # ── 스키마 사전 로드 (업로드 필요 시) ─────────────────────────────────────
    field_id = None
    if not args.dry_run and not args.no_upload:
        print("▶ 첨부 필드 ID 조회 중…")
        field_id = resolve_attach_field_id()
        if field_id:
            print(f"  출고확인서_python field_id = {field_id}")
        else:
            print("  ⚠️  field_id 해결 실패 — 로컬 저장만 진행")
            args.no_upload = True

    # ── Shipment 조회 ─────────────────────────────────────────────────────────
    print("▶ Shipment 조회 중…")
    recs = fetch_shipments(args.date, args.sc_id)
    print(f"  {len(recs)}건 조회")
    if not recs:
        print("  조회 결과 없음")
        return

    # ── Location 일괄 조회 ────────────────────────────────────────────────────
    all_loc_ids: list[str] = []
    for rec in recs:
        loc = rec["fields"].get("Location") or []
        if isinstance(loc, list):
            all_loc_ids.extend(loc)
    all_loc_ids = list(set(all_loc_ids))
    loc_map: dict[str, str] = {}
    if all_loc_ids:
        print(f"  Location {len(all_loc_ids)}건 조회 중…")
        loc_map = fetch_locations(all_loc_ids)

    # ── 문서 조립 ─────────────────────────────────────────────────────────────
    docs = [build_doc(rec, loc_map) for rec in recs]

    if args.dry_run:
        print("\n── 미리보기 ──────────────────────────────────────────────────────")
        for d in docs:
            print(f"  {d['sc_id']}  |  TO: {d['to_no']}  |  {d['ship_date']}"
                  f"  |  {d['customer']}  |  박스: {d['box_qty']}  |  품목 {len(d['items'])}건")
        return

    # ── PDF 생성 ──────────────────────────────────────────────────────────────
    import io
    ok_count = fail_count = 0
    today_stamp = date.today().strftime("%Y%m%d")

    for doc in docs:
        sc_id = doc["sc_id"] or doc["record_id"]
        filename = f"출고확인서_{sc_id}_{today_stamp}.pdf"
        out_path = OUT_DIR / filename

        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=A4)
        draw_confirmation(c, doc, font, font_bold)
        c.showPage()
        c.save()
        pdf_bytes = buf.getvalue()

        # 로컬 저장
        out_path.write_bytes(pdf_bytes)
        print(f"  📄 저장: {out_path.name}  ({len(pdf_bytes):,} bytes)")

        # Airtable 업로드
        if not args.no_upload and field_id:
            success = upload_via_content_api(doc["record_id"], field_id, filename, pdf_bytes)
            if success:
                ok_count += 1
            else:
                fail_count += 1

    total = len(docs)
    if args.no_upload:
        print(f"\n✅ 완료 — {total}건 PDF 로컬 저장 (업로드 스킵)")
    else:
        print(f"\n✅ 완료 — {total}건 처리 | 업로드 성공: {ok_count} / 실패: {fail_count}")


if __name__ == "__main__":
    main()
