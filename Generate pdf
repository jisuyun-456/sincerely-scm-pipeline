"""
generate_pdf.py
출고확인서 PDF 자동 생성 스크립트
- Airtable TO 레코드 읽기 (+ Location, MM 링크 레코드 추가 조회)
- reportlab으로 출고확인서 PDF 생성
- 생성된 PDF를 Airtable TO 레코드 첨부파일로 업로드
"""

import argparse
import os
import io
import base64
import json
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

# ── 폰트 등록 (NanumGothic 없으면 기본 폰트 fallback) ────────────────────────
def register_fonts():
    """나눔고딕 또는 Helvetica fallback"""
    try:
        # GitHub Actions 환경에서 apt로 설치하거나 레포에 포함시킬 수 있음
        pdfmetrics.registerFont(TTFont("NanumGothic", "NanumGothic.ttf"))
        pdfmetrics.registerFont(TTFont("NanumGothicBold", "NanumGothicBold.ttf"))
        return "NanumGothic", "NanumGothicBold"
    except Exception:
        return "Helvetica", "Helvetica-Bold"

# ── Airtable 데이터 읽기 ──────────────────────────────────────────────────────
def fetch_to_record(api: Api, base_id: str, record_id: str) -> dict:
    table = api.table(base_id, "TO")        # 테이블 이름 또는 ID로 변경 가능
    record = table.get(record_id)
    return record["fields"]

def fetch_location_names(api: Api, base_id: str, location_ids: list) -> str:
    """Location linked record ID 배열 → 이름 join"""
    if not location_ids:
        return ""
    table = api.table(base_id, "Location")  # Location 테이블명 확인 필요
    names = []
    for loc_id in location_ids:
        rec = table.get(loc_id)
        names.append(rec["fields"].get("Name", ""))
    return ", ".join(names)

def fetch_mm_records(api: Api, base_id: str, mm_ids: list) -> list:
    """연결된 MM 레코드 목록 반환 (품목명 + 수량)"""
    if not mm_ids:
        return []
    table = api.table(base_id, "MM")        # MM 테이블명 확인 필요
    rows = []
    for mm_id in mm_ids:
        rec = table.get(mm_id)
        f = rec["fields"]
        rows.append({
            "order_item":  f.get("최종 출하 품목", ""),
            "actual_item": f.get("최종 출고 품목 및 수량", ""),
        })
    return rows

def build_data(api: Api, base_id: str, record_id: str) -> dict:
    """TO 레코드 + 연결 레코드 조합하여 PDF용 딕셔너리 반환"""
    f = fetch_to_record(api, base_id, record_id)

    # Location linked record → 이름 join
    location_ids = f.get("Location", [])
    location_str = fetch_location_names(api, base_id, location_ids)

    # MM linked record → 품목 리스트
    mm_ids = f.get("MM", [])               # TO에서 MM으로 연결된 필드명 확인 필요
    mm_rows = fetch_mm_records(api, base_id, mm_ids)

    # 출하일자 포매팅 (예: "2025-03-16" → "3/16 (월)")
    ship_date_raw = f.get("출하일자", "")
    ship_date_str = format_date(ship_date_raw)

    return {
        "to_no":           f.get("TO Number", ""),
        "sc_id":           f.get("SC id", ""),
        "location":        location_str,
        "ship_date":       ship_date_str,
        "delivery_type":   f.get("배송 방식", ""),
        "delivery_time":   f.get("배송시간", ""),
        "customer":        f.get("고객사", ""),
        "recipient":       f.get("수령인", ""),
        "unload_service":  f.get("하차 서비스", ""),
        "recipient_phone": f.get("수령인 연락처", ""),
        "delivery_addr":   f.get("배송지", ""),
        "box_qty":         f.get("최종 외박스 수량", ""),
        "mm_rows":         mm_rows,
    }

def format_date(raw: str) -> str:
    """ISO 날짜 → "M/D (요일)" 형식"""
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
        buf,
        pagesize=A4,
        leftMargin=15*mm,
        rightMargin=15*mm,
        topMargin=12*mm,
        bottomMargin=12*mm,
    )

    W = A4[0] - 30*mm   # 사용 가능한 너비
    story = []

    # 스타일
    def style(size=9, bold=False, align="LEFT", color=colors.black):
        return ParagraphStyle(
            "s",
            fontName=font_bold if bold else font,
            fontSize=size,
            textColor=color,
            alignment={"LEFT": 0, "CENTER": 1, "RIGHT": 2}[align],
            leading=size * 1.4,
        )

    LIGHT_GRAY = colors.HexColor("#F5F5F5")
    BORDER     = colors.HexColor("#CCCCCC")
    cell_style = [
        ("FONTNAME",    (0, 0), (-1, -1), font),
        ("FONTSIZE",    (0, 0), (-1, -1), 8.5),
        ("GRID",        (0, 0), (-1, -1), 0.4, BORDER),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]

    def label(text):
        return Paragraph(text, style(8.5, color=colors.HexColor("#555555")))

    def value(text, bold=False, size=9):
        return Paragraph(str(text) if text else "", style(size, bold=bold))

    # ── 로고 헤더 ─────────────────────────────────────────────────────────────
    header = Table(
        [[value("Sincerely", bold=True, size=16)]],
        colWidths=[W],
    )
    header.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(header)
    story.append(HRFlowable(width=W, thickness=0.5, color=BORDER))
    story.append(Spacer(1, 3*mm))

    # ── TO No. / SC id / 출고 대기 좌표 ──────────────────────────────────────
    row1 = Table(
        [[
            label("TO. No."), value(f"{data['to_no']}", bold=True),
            label("SC id"),   value(data["sc_id"]),
            label("출고 대기 좌표"), value(data["location"]),
        ]],
        colWidths=[18*mm, 40*mm, 18*mm, 36*mm, 24*mm, W - 136*mm],
    )
    row1.setStyle(TableStyle(cell_style + [
        ("BACKGROUND", (0, 0), (0, 0), LIGHT_GRAY),
        ("BACKGROUND", (2, 0), (2, 0), LIGHT_GRAY),
        ("BACKGROUND", (4, 0), (4, 0), LIGHT_GRAY),
    ]))
    story.append(row1)

    # ── 발송 정보 ─────────────────────────────────────────────────────────────
    row2 = Table(
        [[
            label("발송처"),  value(SENDER_NAME),
            label("출하일자"), value(data["ship_date"]),
        ],
        [
            label("발송인"),  value(SENDER_PERSON),
            label("배송 방식"), value(data["delivery_type"]),
        ],
        [
            label("연락처"),  value(SENDER_PHONE),
            label("배송시간"), value(data["delivery_time"]),
        ]],
        colWidths=[18*mm, 70*mm, 22*mm, W - 110*mm],
    )
    row2.setStyle(TableStyle(cell_style + [
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GRAY),
        ("BACKGROUND", (2, 0), (2, -1), LIGHT_GRAY),
    ]))
    story.append(row2)

    # 발송지 (full width)
    row3 = Table(
        [[label("발송지"), value(SENDER_ADDRESS)]],
        colWidths=[18*mm, W - 18*mm],
    )
    row3.setStyle(TableStyle(cell_style + [
        ("BACKGROUND", (0, 0), (0, 0), LIGHT_GRAY),
    ]))
    story.append(row3)

    story.append(Spacer(1, 2*mm))

    # ── 수령 정보 ─────────────────────────────────────────────────────────────
    row4 = Table(
        [[
            label("고객사"),  value(data["customer"]),
            label("하차 서비스"), value(data["unload_service"]),
        ],
        [
            label("수령인"),  value(data["recipient"]),
            label("수령인 연락처"), value(data["recipient_phone"]),
        ]],
        colWidths=[18*mm, 60*mm, 24*mm, W - 102*mm],
    )
    row4.setStyle(TableStyle(cell_style + [
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GRAY),
        ("BACKGROUND", (2, 0), (2, -1), LIGHT_GRAY),
    ]))
    story.append(row4)

    # 배송지 (full width)
    row5 = Table(
        [[label("배송지"), value(data["delivery_addr"], bold=True)]],
        colWidths=[18*mm, W - 18*mm],
    )
    row5.setStyle(TableStyle(cell_style + [
        ("BACKGROUND", (0, 0), (0, 0), LIGHT_GRAY),
    ]))
    story.append(row5)

    story.append(Spacer(1, 4*mm))

    # ── 박스 수량 ─────────────────────────────────────────────────────────────
    box_section = Table(
        [[Paragraph("박스 수량", style(10, bold=True, align="CENTER"))]],
        colWidths=[W],
    )
    box_section.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.4, BORDER),
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GRAY),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(box_section)

    box_val = Table(
        [[Paragraph(data["box_qty"], style(16, bold=True, align="CENTER"))]],
        colWidths=[W],
    )
    box_val.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.4, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(box_val)

    # ── 서명란 ────────────────────────────────────────────────────────────────
    sign_text = "상품 및 박스 수량 그리고 밑 유의사항 등을 확인하고 서명합니다."
    sign_row = Table(
        [[
            Paragraph(sign_text, style(9, bold=True)),
            Paragraph("(서명)", style(9, bold=True, align="RIGHT")),
        ]],
        colWidths=[W * 0.78, W * 0.22],
    )
    sign_row.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.4, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(sign_row)

    # ── 유의사항 ──────────────────────────────────────────────────────────────
    notice_paras = [Paragraph(line, style(8, color=colors.HexColor("#444444")))
                    for line in NOTICE_LINES]
    notice_table = Table(
        [[p] for p in notice_paras],
        colWidths=[W],
    )
    notice_table.setStyle(TableStyle([
        ("BOX",          (0, 0), (-1, -1), 0.4, BORDER),
        ("LEFTPADDING",  (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
    ]))
    story.append(notice_table)

    story.append(Spacer(1, 3*mm))

    # ── 품목 수량 비교표 ──────────────────────────────────────────────────────
    item_header = Table(
        [[
            Paragraph("고객 주문 품목 및 수량", style(9, bold=True, align="CENTER")),
            Paragraph("고객 출고 품목 및 수량", style(9, bold=True, align="CENTER")),
        ]],
        colWidths=[W / 2, W / 2],
    )
    item_header.setStyle(TableStyle([
        ("GRID",          (0, 0), (-1, -1), 0.4, BORDER),
        ("BACKGROUND",    (0, 0), (-1, -1), LIGHT_GRAY),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(item_header)

    # 품목 행 구성
    mm_rows = data["mm_rows"]
    if not mm_rows:
        mm_rows = [{"order_item": "", "actual_item": ""}]

    item_rows = []
    for row in mm_rows:
        item_rows.append([
            Paragraph(row["order_item"],  style(9)),
            Paragraph(row["actual_item"], style(9)),
        ])

    # 최소 8행 확보 (여백 느낌)
    while len(item_rows) < 8:
        item_rows.append([Paragraph("", style(9)), Paragraph("", style(9))])

    item_body = Table(item_rows, colWidths=[W / 2, W / 2])
    item_body.setStyle(TableStyle([
        ("GRID",          (0, 0), (-1, -1), 0.4, BORDER),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(item_body)

    doc.build(story)
    return buf.getvalue()

# ── Airtable 첨부파일 업로드 ──────────────────────────────────────────────────
def upload_pdf_to_airtable(
    api_key: str,
    base_id: str,
    record_id: str,
    pdf_bytes: bytes,
    to_no: str,
):
    """
    Airtable REST API로 PDF를 TO 레코드 첨부파일 필드에 업로드
    필드명: "출고확인서" (없으면 Airtable에 Attachment 필드 추가 필요)
    """
    # base64 인코딩
    b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    filename = f"출고확인서_{to_no}.pdf"

    url = f"https://api.airtable.com/v0/{base_id}/TO/{record_id}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "fields": {
            "출고확인서": [          # ← Airtable Attachment 필드명 확인 필요
                {
                    "filename": filename,
                    "contentType": "application/pdf",
                    "data": b64,    # base64 직접 업로드 (Airtable API v0 지원)
                }
            ]
        }
    }
    resp = requests.patch(url, headers=headers, json=payload)
    resp.raise_for_status()
    print(f"✅ PDF 업로드 완료: {filename}")

# ── 메인 ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--record-id", required=True, help="Airtable TO record ID")
    args = parser.parse_args()

    api_key = os.environ["AIRTABLE_API_KEY"]
    base_id = os.environ["AIRTABLE_BASE_ID"]
    record_id = args.record_id

    print(f"▶ record_id: {record_id}")

    # 1. 폰트 등록
    font, font_bold = register_fonts()

    # 2. Airtable 데이터 읽기
    api = Api(api_key)
    print("▶ Airtable 데이터 읽는 중...")
    data = build_data(api, base_id, record_id)
    print(f"  TO No.: {data['to_no']} / 수령인: {data['recipient']}")

    # 3. PDF 생성
    print("▶ PDF 생성 중...")
    pdf_bytes = build_pdf(data, font, font_bold)
    print(f"  PDF 크기: {len(pdf_bytes):,} bytes")

    # 4. Airtable 업로드
    print("▶ Airtable 업로드 중...")
    upload_pdf_to_airtable(api_key, base_id, record_id, pdf_bytes, data["to_no"])

if __name__ == "__main__":
    main()
