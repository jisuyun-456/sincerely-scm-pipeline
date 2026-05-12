"""
영업팀 CBM 마스터 데이터 — TMS Product 테이블 UPSERT 입력값.

박스명칭 singleSelect 옵션: 극소형 / 중형 / 중대형 / 대형 / 특대형
하차비 적용: 중대형(5개/5,000원) · 대형(3개/5,000원) · 특대형(3개/5,000원)

스키마:
  name         — Product.Name (primary)
  code         — Product.견적코드 (UPSERT 키, uppercase)
  box_type     — Product.박스명칭 (singleSelect 5종)
  qty_per_box  — Product.박스당 제품수 (number)
  cbm          — Product.CBM (multilineText, PDF 'CBM' 컬럼 값 = per-unit CBM)
  box_size     — Product.박스사이즈 (singleSelect '480*380*270' 등) — Airtable formula
                 '박스 당 CBM' 의 입력. 신규 INSERT 시 함께 set.

* 기존 328건은 이 리스트로 손대지 않음 — 박스사이즈 backfill 은 별도 스크립트
  (backfill_box_size.py) 가 박스명칭→박스사이즈 매핑으로 일괄 처리.
"""

PRODUCTS: list[dict] = [
    # 2026-05-12 신규 추가 (PDF 7페이지) — 모두 견적코드 기준 TMS Product 에 없음 확인됨
    {"name": "심볼 NFC 키링",             "code": "NFCA",  "box_type": "중형",   "qty_per_box": 150, "cbm": 0.000134, "box_size": "350*250*230"},
    {"name": "아트워크 타월",              "code": "AWTW",  "box_type": "중대형", "qty_per_box": 20,  "cbm": 0.002462, "box_size": "480*380*270"},
    {"name": "아트워크 타월",              "code": "SOLE",  "box_type": "중대형", "qty_per_box": 20,  "cbm": 0.002462, "box_size": "480*380*270"},
    {"name": "솔리드 레디백",              "code": "SORB",  "box_type": "특대형", "qty_per_box": 3,   "cbm": 0.055402, "box_size": "560*530*560"},
    {"name": "스탠바이 빅팬선풍기",        "code": "FANB",  "box_type": "중대형", "qty_per_box": 18,  "cbm": 0.002736, "box_size": "480*380*270"},
    {"name": "슬림 터보 선풍기",           "code": "FANC",  "box_type": "중대형", "qty_per_box": 50,  "cbm": 0.000985, "box_size": "480*380*270"},
    {"name": "어반 스텐 런치박스",         "code": "USLB",  "box_type": "중대형", "qty_per_box": 18,  "cbm": 0.002736, "box_size": "480*380*270"},
    {"name": "하우스 핸드타월",            "code": "HHTW",  "box_type": "중대형", "qty_per_box": 50,  "cbm": 0.000985, "box_size": "480*380*270"},
    {"name": "하우스 핸드타월 (키트)",     "code": "HHTK",  "box_type": "중대형", "qty_per_box": 17,  "cbm": 0.002897, "box_size": "480*380*270"},
    {"name": "어텐션 스포츠 보틀",         "code": "ATSS",  "box_type": "대형",   "qty_per_box": 36,  "cbm": 0.002962, "box_size": "510*510*410"},
]
