"""
preview_hapojang.py
────────────────────────────────────────────────────────────────────────────
합포장 렌더링 미리보기 — Airtable 없이 mock 데이터로 PDF 생성

사용:
  python scripts/preview_hapojang.py
"""
import os, sys, platform
from io import BytesIO
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

# packing_list 모듈 경로 추가
sys.path.insert(0, str(Path(__file__).parent))

from packing_list import (
    register_fonts, draw_packing_list, consolidate_boxes,
    generate_packing_list,
)
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import A4

# ── mock 데이터: PNA51820-서울대학교약학대학 (TO00016424) ─────────────────────
# 실제 PDF 스크린샷 기반 재현
boxes_raw = [
    {"box_num": 1, "total_boxes": 5, "item": "Solid 스탠다드 G형박스 키트",  "qty": "50+5",  "size": "대",  "remainder_items": []},
    {"box_num": 2, "total_boxes": 5, "item": "웰컴페이퍼50+25+사각스티커50+25", "qty": "25",   "size": "중",  "remainder_items": []},
    {"box_num": 3, "total_boxes": 5, "item": "리맴버 탁상시계",               "qty": "50",   "size": "중",  "remainder_items": []},
    {"box_num": 4, "total_boxes": 5, "item": "올웨이즈 양우산",              "qty": "50+1", "size": "중대", "remainder_items": []},
    {"box_num": 5, "total_boxes": 5, "item": "슬림 터보선풍기",              "qty": "50+1", "size": "중대", "remainder_items": []},
]

mock_rec = {
    "rec_id":         "mock_preview",
    "to_num":         "TO00016424",
    "date":           "2026-05-15",
    "company":        "서울대학교약학대학",
    "box_sum":        "중2,중대2,대1 / 총5박스",
    "consignee_name": "김지헌",
    "consignee_addr": "서울특별시 관악구 관악로 1 21동 105호",
    "consignee_tel":  "010-3383-7059",
    "shipper_name":   "현동원",
    "shipper_addr":   "서울시 성동구 왕십리로88 노벨빌딩 4층 신시어리",
    "shipper_tel":    "['010-4683-1306']",
    "summary_lines": [
        "Solid 스탠다드 G형박스 50",
        "사각스티커50",
        "웰컴페이퍼 50",
        "올웨이즈 양우산 50",
        "슬림 터보선풍기 50",
        "리맴버 탁상시계 50",
    ],
    "boxes":  boxes_raw,
    "groups": consolidate_boxes(boxes_raw),
    "is_error": False,
}

# ── PDF 생성 ────────────────────────────────────────────────────────────────
buf = BytesIO()
generate_packing_list([mock_rec], buf)
pdf_bytes = buf.getvalue()

stamp = datetime.now().strftime("%Y%m%d_%H%M")
out = Path(os.getenv("PDF_OUTPUT_DIR", r"C:\Users\yjisu\Desktop")) / f"합포장_preview_{stamp}.pdf"
out.write_bytes(pdf_bytes)
print(f"✅ 미리보기 PDF 저장: {out}")

# 자동으로 열기 (Windows)
if platform.system() == "Windows":
    import subprocess
    subprocess.Popen(["start", "", str(out)], shell=True)
