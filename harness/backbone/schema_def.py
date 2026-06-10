"""WMS 네이티브 4테이블 필드 스펙 (Airtable meta API 생성용).

create_tables.py가 이 스펙으로 테이블을 idempotent 생성한다.
링크 필드는 모든 테이블 생성 후 2차 패스로 추가(LINK_FIELDS).
"""
from __future__ import annotations

WMS_BASE = "appLui4ZR5HWcQRri"

# 1차: 스칼라 필드만 (링크 제외). primary 필드는 fields[0].
TABLES: dict[str, list[dict]] = {
    "WMS_KeyCrosswalk": [
        {"name": "표준키", "type": "singleLineText"},          # primary (굿즈명 or PT####)
        {"name": "키유형", "type": "singleSelect",
         "options": {"choices": [{"name": "굿즈"}, {"name": "파츠"}]}},
        {"name": "TMS_견적코드", "type": "singleLineText"},
        {"name": "WMS_아이템코드", "type": "singleLineText"},
        {"name": "MES_파츠코드", "type": "singleLineText"},
        {"name": "매칭방식", "type": "singleSelect",
         "options": {"choices": [{"name": "정확"}, {"name": "유사"}, {"name": "수기"}]}},
        {"name": "매칭신뢰도", "type": "number", "options": {"precision": 2}},
        {"name": "검증상태", "type": "singleSelect",
         "options": {"choices": [{"name": "미검증"}, {"name": "확정"}, {"name": "보류"}]}},
        {"name": "출처", "type": "singleSelect",
         "options": {"choices": [{"name": "mes_crosswalk"}]}},  # blank = P1 bootstrap
    ],
    "WMS_ItemMaster": [
        {"name": "품목키", "type": "singleLineText"},           # primary (PT#### or 굿즈명)
        {"name": "품목명", "type": "singleLineText"},
        {"name": "품목유형", "type": "singleSelect",
         "options": {"choices": [{"name": "완제품"}, {"name": "키트"}, {"name": "단품"},
                                 {"name": "부자재"}, {"name": "포장재"}]}},
        {"name": "CBM_개당_m3", "type": "number", "options": {"precision": 6}},
        {"name": "박스규격", "type": "singleLineText"},
        {"name": "박스당_제품수", "type": "number", "options": {"precision": 0}},
        {"name": "박스당_CBM_m3", "type": "number", "options": {"precision": 4}},
        {"name": "출처", "type": "singleSelect",
         "options": {"choices": [{"name": "TMS_Product"}, {"name": "박스유도"},
                                 {"name": "MES_제품DB"}, {"name": "수기"}]}},
    ],
    "WMS_BOM": [
        {"name": "BOM_ID", "type": "singleLineText"},          # primary (project_굿즈_PT)
        {"name": "프로젝트코드", "type": "singleLineText"},
        {"name": "모품목_굿즈명", "type": "singleLineText"},
        {"name": "소품목_PT", "type": "singleLineText"},
        {"name": "소요량_개당", "type": "number", "options": {"precision": 4}},
        {"name": "구성유형", "type": "singleSelect",
         "options": {"choices": [{"name": "키트"}, {"name": "임가공"},
                                 {"name": "포장재"}, {"name": "원부자재"}]}},
        {"name": "신뢰도", "type": "number", "options": {"precision": 2}},
        {"name": "검증상태", "type": "singleSelect",
         "options": {"choices": [{"name": "이송"}, {"name": "검증완료"}, {"name": "폐기"}]}},
        {"name": "출처", "type": "singleSelect",
         "options": {"choices": [{"name": "order그룹핑"}, {"name": "MES보강"},
                                 {"name": "movement보강"}, {"name": "수기"}]}},
    ],
    "WMS_PropagationLedger": [
        {"name": "전파ID", "type": "singleLineText"},          # primary (project_굿즈)
        {"name": "프로젝트코드", "type": "singleLineText"},
        {"name": "굿즈명", "type": "singleLineText"},
        {"name": "고객주문수량", "type": "number", "options": {"precision": 0}},
        {"name": "자재소요_요약", "type": "multilineText"},
        {"name": "포장소요_요약", "type": "multilineText"},
        {"name": "추정_CBM_m3", "type": "number", "options": {"precision": 4}},
        {"name": "shipment_id", "type": "singleLineText"},
        {"name": "전파상태", "type": "singleSelect",
         "options": {"choices": [{"name": "완결"}, {"name": "부분"}, {"name": "끊김"}]}},
        {"name": "생성시각", "type": "dateTime",
         "options": {"dateFormat": {"name": "iso"}, "timeFormat": {"name": "24hour"},
                     "timeZone": "Asia/Seoul"}},
    ],
}

# 2차: 링크 필드 (대상 테이블 존재 후 추가). (테이블명, 필드명, 링크대상 테이블명)
LINK_FIELDS: list[tuple[str, str, str]] = [
    ("WMS_ItemMaster", "BOM_상위", "WMS_BOM"),
    ("WMS_ItemMaster", "Crosswalk", "WMS_KeyCrosswalk"),
    ("WMS_BOM", "모품목_link", "WMS_ItemMaster"),
    ("WMS_BOM", "소품목_link", "WMS_ItemMaster"),
]
