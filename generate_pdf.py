"""
generate_pdf.py
출고확인서 PDF 자동 생성 스크립트
- Airtable Shipment 레코드 읽기 (+ Location, MM 링크 레코드 추가 조회)
- reportlab으로 출고확인서 PDF 생성
- 생성된 PDF를 Airtable Shipment 레코드 첨부파일로 업로드
"""

import argparse
import os
import io
import requests
from datetime import datetime

from pyairtable import Api
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable

# ── 고정값 ────────────────────────────────────────────────────────────────────
SENDER_NAME    = "신시어리"
SENDER_PERSON  = "신시어리 물류팀"
SENDER_PHONE   = "010-4979-1306"
SENDER_ADDRESS = "서울특별시 성동구 왕십리로 88 노벨빌딩 4층"

NOTICE_LINES = [
    "✓ 최초 공유된 하차 정보와 다른 경우 추가비용이 발생할 수 있습니다. "
    "(화물엘레베이터 및 주차장 유무, 수령지 정보 등)",
    "✓ 물품수령 후 7일 이내 제품 하자가 있으신 경우 신시어리 담당자에게 연락주세요. "
    "빠르게 대응하도록 하겠습니다.",
]

# ── 폰트 등록 ────────────────────────────────────────────────────────────────
def register_fonts():
    try:
        pdfmetrics.registerFont(TTFont("NanumGothic", "NanumGothic.ttf"))
        pdfmetrics.registerFont(TTFont("NanumGothicBold", "NanumGothicBold.ttf"))
        return "NanumGothic", "NanumGothicBold"
    except Exception:
        return "Helvetica", "Helvetica-Bold"

# ── 필드값 헬퍼 ───────────────────────────────────────────────────────────────
def get_field(f: dict, key: str, default: str = "") -> str:
    """Airtable 필드값이 리스트로 올 수 있어서 안전하게 문자열로 변환"""
    val = f.get(key, default)
    if isinstance(val, list):
        return ", ".join(str(v) for v in val) if val else default
    return str(val) if val else default

# ── Airtable 데이터 읽기 ──────────────────────────────────────────────────────
def fetch_shipment_record(api: Api, base_id: str, record_id: str) -> dict:
    table = api.table(base_id, "Shipment")
    record = table.get(record_id)
    return record["fields"]

def fetch_location_names(api: Api, base_id: str, location_ids: list) -> str:
    if not location_ids:
        return ""
    table = api.table(base_id, "Location")
    names = []
    for loc_id in location_ids:
        try:
            rec = table.get(loc_id)
            names.append(rec["fields"].get("Name", ""))
        except Exception:
            pass
    return ", ".join(names)

def fetch_mm_records(api: Api, base_id: str, mm_ids: list) -> list:
    if not mm_ids:
        return []
    table = api.table(base_id, "MM")
    rows = []
    for mm_id in mm_ids:
        try:
            rec = table.get(mm_id)
            f = rec["fields"]
            rows.append({
                "order_item":  get_field(f, "최종 출하 품목"),
                "actual_item": get_field(f, "최종 출고 품목 및 수량"),
            })
        except Exception:
            pass
    return rows

def build_data(api: Api, base_id: str, record_id: str) -> dict:
    f = fetch_shipment_record(api, base_id, record_id)

    location_ids = f.get("Location", [])
    if not isinstance(location_ids, list):
        location_ids = []
    location_str = fetch_location_names(api, base_id, location_ids)

    mm_ids = f.get("MM", [])
    if not isinstance(mm_ids, list):
        mm_ids = []
    mm_rows = fetch_mm_records(api, base_id, mm_ids)

    return {
        "to_no":           get_field(f, "TO Number"),
        "sc_id":           get_field(f, "SC id"),
        "location":        location_str,
        "ship_date":       format_date(get_field(f, "출하일자")),
        "delivery_type":   get_field(f, "배송 방식"),
        "delivery_time":   get_field(f, "배송시간"),
        "customer":        get_field(f, "고객사"),
        "recipient":       get_field(f, "수령인"),
        "unload_service":  get_field(f, "하차 서비스"),
        "recipient_phone": get_field(f, "수령인 연락처"),
        "delivery_addr":   get_field(f, "배송지"),
        "box_qty":         get_field(f, "최종 외박스 수량"),
        "mm_rows":         mm_rows,
    }

def format_date(raw: str) -> str:
    if not raw:
        return ""
    try:
        weekdays = ["월", "화", "수", "목", "금", "토", "일"]
        dt = datetime.fromisoformat(raw[:10])
        return f"{dt.month}/{dt.day} ({weekdays[dt.weekday()]})"
    except Exception:
        return raw

# ── PDF 생성 ──────────────────────────────────────────────────────────────────
def build_pdf(data: dict, font: str, font_bold: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=12*mm, bottomMargin=12*mm,
    )

    W = A4[0] - 30*mm
    story = []

    LIGHT_GRAY = colors.HexColor("#F5F5F5")
    BORDER     = colors.HexColor("#CCCCCC")

    def style(size=9, bold=False, align="LEFT", color=colors.black):
        return ParagraphStyle(
            "s",
            fontName=font_bold if bold else font,
            fontSize=size,
            textColor=color,
            alignment={"LEFT": 0, "CENTER": 1, "RIGHT": 2}[align],
            leading=size * 1.4,
        )

    cell_style = [
        ("FONTNAME",      (0, 0), (-1, -1), font),
        ("FONTSIZE",      (0, 0), (-1, -1), 8.5),
        ("GRID",          (0, 0), (-1, -1), 0.4, BORDER),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
    ]

    def label(text):
        return Paragraph(text, style(8.5, color=colors.HexColor("#555555")))

    def value(text, bold=False, size=9):
        return Paragraph(str(text) if text else "", style(size, bold=bold))

    # 로고 헤더
    header = Table([[value("Sincerely", bold=True, size=16)]], colWidths=[W])
    header.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(header)
    story.append(HRFlowable(width=W, thickness=0.5, color=BORDER))
    story.append(Spacer(1, 3*mm))

    # TO No. / SC id / 출고 대기 좌표
    row1 = Table(
        [[label("TO. No."), value(data["to_no"], bold=True),
          label("SC id"),   value(data["sc_id"]),
          label("출고 대기 좌표"), value(data["location"])]],
        colWidths=[18*mm, 40*mm, 18*mm, 36*mm, 24*mm, W - 136*mm],
    )
    row1.setStyle(TableStyle(cell_style + [
        ("BACKGROUND", (0, 0), (0, 0), LIGHT_GRAY),
        ("BACKGROUND", (2, 0), (2, 0), LIGHT_GRAY),
        ("BACKGROUND", (4, 0), (4, 0), LIGHT_GRAY),
    ]))
    story.append(row1)

    # 발송 정보
    row2 = Table(
        [[label("발송처"),  value(SENDER_NAME),   label("출하일자"),  value(data["ship_date"])],
         [label("발송인"),  value(SENDER_PERSON),  label("배송 방식"), value(data["delivery_type"])],
         [label("연락처"),  value(SENDER_PHONE),   label("배송시간"),  value(data["delivery_time"])]],
        colWidths=[18*mm, 70*mm, 22*mm, W - 110*mm],
    )
    row2.setStyle(TableStyle(cell_style + [
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GRAY),
        ("BACKGROUND", (2, 0), (2, -1), LIGHT_GRAY),
    ]))
    story.append(row2)

    row3 = Table([[label("발송지"), value(SENDER_ADDRESS)]], colWidths=[18*mm, W - 18*mm])
    row3.setStyle(TableStyle(cell_style + [("BACKGROUND", (0, 0), (0, 0), LIGHT_GRAY)]))
    story.append(row3)
    story.append(Spacer(1, 2*mm))

    # 수령 정보
    row4 = Table(
        [[label("고객사"),  value(data["customer"]),  label("하차 서비스"),   value(data["unload_service"])],
         [label("수령인"),  value(data["recipient"]), label("수령인 연락처"), value(data["recipient_phone"])]],
        colWidths=[18*mm, 60*mm, 24*mm, W - 102*mm],
    )
    row4.setStyle(TableStyle(cell_style + [
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GRAY),
        ("BACKGROUND", (2, 0), (2, -1), LIGHT_GRAY),
    ]))
    story.append(row4)

    row5 = Table([[label("배송지"), value(data["delivery_addr"], bold=True)]], colWidths=[18*mm, W - 18*mm])
    row5.setStyle(TableStyle(cell_style + [("BACKGROUND", (0, 0), (0, 0), LIGHT_GRAY)]))
    story.append(row5)
    story.append(Spacer(1, 4*mm))

    # 박스 수량
    story.append(Table(
        [[Paragraph("박스 수량", style(10, bold=True, align="CENTER"))]],
        colWidths=[W],
        style=TableStyle([
            ("BOX", (0,0), (-1,-1), 0.4, BORDER),
            ("BACKGROUND", (0,0), (-1,-1), LIGHT_GRAY),
            ("TOPPADDING", (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ])
    ))
    story.append(Table(
        [[Paragraph(data["box_qty"] or "", style(16, bold=True, align="CENTER"))]],
        colWidths=[W],
        style=TableStyle([
            ("BOX", (0,0), (-1,-1), 0.4, BORDER),
            ("TOPPADDING", (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ])
    ))

    # 서명란
    story.append(Table(
        [[Paragraph("상품 및 박스 수량 그리고 밑 유의사항 등을 확인하고 서명합니다.", style(9, bold=True)),
          Paragraph("(서명)", style(9, bold=True, align="RIGHT"))]],
        colWidths=[W * 0.78, W * 0.22],
        style=TableStyle([
            ("BOX", (0,0), (-1,-1), 0.4, BORDER),
            ("TOPPADDING", (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ("LEFTPADDING", (0,0), (-1,-1), 6),
            ("RIGHTPADDING", (0,0), (-1,-1), 6),
        ])
    ))

    # 유의사항
    story.append(Table(
        [[Paragraph(line, style(8, color=colors.HexColor("#444444")))] for line in NOTICE_LINES],
        colWidths=[W],
        style=TableStyle([
            ("BOX", (0,0), (-1,-1), 0.4, BORDER),
            ("LEFTPADDING", (0,0), (-1,-1), 6),
            ("RIGHTPADDING", (0,0), (-1,-1), 6),
            ("TOPPADDING", (0,0), (-1,-1), 3),
            ("BOTTOMPADDING", (0,0), (-1,-1), 3),
        ])
    ))
    story.append(Spacer(1, 3*mm))

    # 품목 비교표 헤더
    story.append(Table(
        [[Paragraph("고객 주문 품목 및 수량", style(9, bold=True, align="CENTER")),
          Paragraph("고객 출고 품목 및 수량", style(9, bold=True, align="CENTER"))]],
        colWidths=[W/2, W/2],
        style=TableStyle([
            ("GRID", (0,0), (-1,-1), 0.4, BORDER),
            ("BACKGROUND", (0,0), (-1,-1), LIGHT_GRAY),
            ("TOPPADDING", (0,0), (-1,-1), 5),
            ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ])
    ))

    # 품목 행
    mm_rows = data["mm_rows"] or [{"order_item": "", "actual_item": ""}]
    item_rows = [
        [Paragraph(r["order_item"], style(9)), Paragraph(r["actual_item"], style(9))]
        for r in mm_rows
    ]
    while len(item_rows) < 8:
        item_rows.append([Paragraph("", style(9)), Paragraph("", style(9))])

    story.append(Table(
        item_rows, colWidths=[W/2, W/2],
        style=TableStyle([
            ("GRID", (0,0), (-1,-1), 0.4, BORDER),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("LEFTPADDING", (0,0), (-1,-1), 6),
            ("TOPPADDING", (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ])
    ))

    doc.build(story)
    return buf.getvalue()

# ── Airtable 첨부파일 업로드 ──────────────────────────────────────────────────
def upload_pdf_to_airtable(api_key, base_id, record_id, pdf_bytes, to_no):
    filename = f"출고확인서_{to_no}.pdf"

    # 1단계: transfer.sh에 임시 업로드 → URL 획득
    print("  transfer.sh 업로드 중...")
    upload_resp = requests.put(
        f"https://transfer.sh/{filename}",
        data=pdf_bytes,
        headers={
            "Content-Type": "application/pdf",
            "Max-Days": "1",
        },
    )
    upload_resp.raise_for_status()
    file_url = upload_resp.text.strip()
    print(f"  임시 URL: {file_url}")

    # 2단계: Airtable에 URL로 attachment 등록
    url = f"https://api.airtable.com/v0/{base_id}/Shipment/{record_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "fields": {
            "출고확인서_python": [{"url": file_url, "filename": filename}]
        }
    }
    resp = requests.patch(url, headers=headers, json=payload)
    print(f"  Airtable status: {resp.status_code}")
    print(f"  Response: {resp.text[:300]}")
    resp.raise_for_status()
    print(f"✅ PDF 업로드 완료: {filename}")
# ── 메인 ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--record-id", required=True)
    args = parser.parse_args()

    api_key = os.environ["AIRTABLE_API_KEY"]
    base_id = os.environ["AIRTABLE_BASE_ID"]
    record_id = args.record_id

    print(f"▶ record_id: {record_id}")
    font, font_bold = register_fonts()

    api = Api(api_key)
    print("▶ Airtable 데이터 읽는 중...")
    data = build_data(api, base_id, record_id)
    print(f"  TO No.: {data['to_no']} / 수령인: {data['recipient']}")

    print("▶ PDF 생성 중...")
    pdf_bytes = build_pdf(data, font, font_bold)
    print(f"  PDF 크기: {len(pdf_bytes):,} bytes")

    print("▶ Airtable 업로드 중...")
    upload_pdf_to_airtable(api_key, base_id, record_id, pdf_bytes, data["to_no"])

if __name__ == "__main__":
    main()
