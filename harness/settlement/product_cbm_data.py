"""
영업팀 CBM 마스터 데이터 — TMS Product 테이블 UPSERT 입력값.

박스명칭 singleSelect 옵션: 극소형 / 중형 / 중대형 / 대형 / 특대형
하차비 적용: 중대형(5개/5,000원) · 대형(3개/5,000원) · 특대형(3개/5,000원)

cbm: 박스 1개 기준 CBM(m³) — Airtable '박스 당 CBM' formula 에 입력되는 값.
qty_per_box: 한 박스에 들어가는 제품 수.

TODO: PDF 7페이지(~300 품목) 전체를 아래 리스트에 추가.
      견적코드(code)가 UPSERT 키이므로 정확하게 입력할 것.
"""

PRODUCTS: list[dict] = [
    # ── 예시 (PDF에서 확인된 항목) ──────────────────────────────────────────
    {"name": "굿이너프 비치타월",         "code": "BCTL",  "box_type": "대형",   "qty_per_box": 40,  "cbm": 0.060},
    {"name": "굿이너프 비치타월 (키트)",   "code": "BCTLK", "box_type": "대형",   "qty_per_box": 20,  "cbm": 0.060},
    {"name": "Solid G형박스 L",           "code": "SCGL",  "box_type": "특대형", "qty_per_box": 20,  "cbm": 0.100},
    {"name": "Tailored 스트랩박스",        "code": "TILD",  "box_type": "특대형", "qty_per_box": 7,   "cbm": 0.120},
    {"name": "액티브 스포츠타월",          "code": "SPTS",  "box_type": "중대형", "qty_per_box": 45,  "cbm": 0.045},
    # ── 이 아래에 나머지 ~295 품목 추가 ──────────────────────────────────
    # {"name": "...", "code": "...", "box_type": "...", "qty_per_box": N, "cbm": 0.000},
]
