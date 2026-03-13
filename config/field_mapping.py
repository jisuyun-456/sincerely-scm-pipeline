"""
Airtable → Supabase 필드 매핑 설정
재고 로직 분석 결과 기반 — 재고 관련 핵심 필드만 추출

Base ID: appLui4ZR5HWcQRri (자재테스트_지수)
"""

# ── 1. material(parts-stock) — 재고 원장 ──
MATERIAL_TABLE = {
    "airtable_table_id": "tblaRpZstW10EwDlo",
    "supabase_table": "material_stock",
    "fields": {
        # 식별자
        "fld7Pfip5zbBTaTdR": {"col": "name", "type": "text"},               # Name (PK: 파츠명 || 위치)
        "fldFskNydX5lNT1L0": {"col": "location", "type": "text"},           # 재고위치
        "fldsDSdkogmJ0qsVC": {"col": "coordinates", "type": "text[]"},      # 좌표
        "fldCbavd7b27UQWEJ": {"col": "created_at", "type": "timestamptz"},  # Created

        # 핵심 재고 수량
        "fld5XQQv2P9YJZP6n": {"col": "physical_qty", "type": "int"},        # 실물재고수량
        "fldAFkM4HtGJsitOk": {"col": "system_qty", "type": "int"},          # 전산재고수량
        "fldZ5qLZKp0yy28So": {"col": "available_qty", "type": "int"},        # 가용재고수량
        "fldY0R7JWRErJK41C": {"col": "sellable_qty", "type": "int"},         # 판매가능수량

        # 재고 구성 요소 (전산재고 공식)
        "fldxmYmBg2xGiwKaN": {"col": "initial_stock", "type": "int"},        # 기초재고
        "fld22BWHuEwoAgOBG": {"col": "procurement_qty", "type": "int"},      # 구매조달완료수량
        "fldU3Wa1s2rTnNuEZ": {"col": "production_output_qty", "type": "int"},# 생산산출완료수량
        "fldisAX1ePMB68cBA": {"col": "assembly_output_qty", "type": "int"},  # 조립산출완료수량
        "fld1VXE5oi9GXjzrg": {"col": "assembly_input_qty", "type": "int"},   # 조립투입완료수량
        "fldzFhfS0WUyRI0Qs": {"col": "transfer_in_qty", "type": "int"},     # 이동입고완료수량
        "fldKV6IzZqXVpr2uH": {"col": "transfer_out_qty", "type": "int"},    # 이동출고완료수량
        "fldsafVcWTQRNHDUZ": {"col": "production_input_qty", "type": "int"}, # 생산투입완료수량
        "fldtfRTsavXxrKoSd": {"col": "customer_delivery_qty", "type": "int"},# 고객주문납품수량
        "fldoNB3txlNh68emD": {"col": "adj_in_qty", "type": "int"},          # 재고조정수량(입고)
        "fld2LgOBPmmposjnh": {"col": "adj_out_qty", "type": "int"},         # 재고조정수량(출고)

        # 예정 수량 (가용재고 차감 요소)
        "fldBTGdPsCDoiQu84": {"col": "wip_qty", "type": "int"},             # 생산투입재공수량
        "fld0Q37bCLGanWWJs": {"col": "assembly_planned_qty", "type": "int"}, # 조립투입예정수량
        "fldAdYeBtREYoPJQc": {"col": "outbound_request_qty", "type": "int"}, # 출고신청수량
        "fldOeY6xnfI8GlK4b": {"col": "production_planned_qty", "type": "int"},# 생산투입예정수량
        "fldZZjo6folH8Mw4t": {"col": "reserved_qty", "type": "int"},        # 재고예약수량
        "fldNrhMNCzQ6ZydA1": {"col": "procurement_planned_qty", "type": "int"},# 구매조달예정수량
        "fldbkh6uR9DwEQTSI": {"col": "secured_pipeline_qty", "type": "int"},# 확보예정재고
        "fldN495vU3kkatCfS": {"col": "customer_order_planned_qty", "type": "int"},# 고객주문예정수량

        # 실사 관련
        "fldBnRCCFZtJs3NtY": {"col": "physical_check_qty", "type": "int"},   # 실재고 체크 수량(직접입력)
        "fldeBjSTxYQauJd9R": {"col": "last_check_at", "type": "timestamptz"},# 마지막 실재고 체크 완료 일시
        "fldNLw3Vu6BNsVBRR": {"col": "physical_system_diff", "type": "int"}, # 실물수량-전산수량차이
        "fld3RiB6tuwbmFyHa": {"col": "audit_qty_2412", "type": "text"},      # 실사수량(24년12월)
        "fldIR8J3i3zuxbIfg": {"col": "closing_qty_2412", "type": "int"},     # 24년 12월 31일 기말재고수량
        "fldvqXPQOVsUfXREh": {"col": "closing_qty_2025", "type": "int"},     # 2025 기말재고

        # 자재 이동 참조
        "fldY43e0lCMwaLGFB": {"col": "inbound_movement_ids", "type": "text[]"},# 입고자재_movement
        "fldeMpOPbfDRwxeGT": {"col": "outbound_movement_ids", "type": "text"},# 출고자재_movement
    }
}

# ── 2. movement — 재고 이동 트랜잭션 ──
MOVEMENT_TABLE = {
    "airtable_table_id": "tblwq7Kj5Y9nVjlOw",
    "supabase_table": "movement",
    "fields": {
        # 식별자
        "fldOhFtJFBYsxxre7": {"col": "movement_id", "type": "text"},          # movement_id
        "fldwZKCYZ4IFOigRp": {"col": "item_description", "type": "text"},     # 이동물품
        "fldFRNxG1pNooEOC7": {"col": "movement_purpose", "type": "text"},     # 이동목적 (singleSelect)
        "fldiAT4WXaDtlwZuf": {"col": "movement_type", "type": "text"},        # 이동유형

        # 수량
        "fld8i5WLz1UNmzvvB": {"col": "movement_qty", "type": "int"},          # 이동수량(변경)
        "fldV8kVokQqMIsif0": {"col": "receiving_qty", "type": "int"},         # 입하수량
        "fld0XSbknPnJfOYOT": {"col": "shipping_qty", "type": "int"},          # 출고수량
        "fldlJt3RPY6E8JB4G": {"col": "inbound_qty", "type": "int"},          # 입고수량
        "fldYlBFySiGpiyjlX": {"col": "return_out_qty", "type": "int"},       # 반출수량
        "fldjQX03iIsT1UATv": {"col": "return_in_qty", "type": "int"},        # 반입수량
        "fldxDcWx26sJdYjCJ": {"col": "return_qty", "type": "int"},           # 리턴수량
        "fldD8QTNmeop8WVD3": {"col": "planned_qty", "type": "int"},          # 계획수량
        "fldnrqmT56niE7O21": {"col": "inspection_qty", "type": "int"},       # 검수수량
        "fld3lQvblfrqTl4O8": {"col": "defect_sampling_qty", "type": "int"},  # 불량수량_샘플링검수
        "fldsTXzxUeerw4qw2": {"col": "defect_full_qty", "type": "int"},      # 불량수량_전수검수
        "fldwF3dD1txSWtRiO": {"col": "disposal_qty", "type": "int"},         # 폐기_수량

        # 자재 참조
        "fldzk1YgndVo2lgCd": {"col": "inbound_material", "type": "text"},     # 입고자재
        "fldQevLGnuqIuFRVO": {"col": "outbound_material", "type": "text"},    # 출고자재
        "fldws6Ohz68i3GBPR": {"col": "inbound_item", "type": "text"},         # 입고물품

        # 위치
        "fldgEi6LVSzrtQQ4o": {"col": "inbound_location", "type": "text"},    # 입고자재장소
        "fldeCc7UZmRbOIGBP": {"col": "outbound_location", "type": "text"},   # 출고자재장소
        "fldLCHFvGULtH8YPY": {"col": "coordinate", "type": "text"},          # 좌표

        # 일자
        "flduN8khmYwdn7uVD": {"col": "actual_receiving_date", "type": "date"},# 실제입하일
        "fldE1A3lhHA9sCoq0": {"col": "planned_move_date", "type": "date"},   # 이동예정일
        "fldBoBHFJGNmofInm": {"col": "stock_adj_date", "type": "date"},      # 재고조정일자

        # 상태
        "fldo5g7aHTGsZnFtM": {"col": "shipping_status", "type": "text"},     # 출고상태
        "fldKrjj58HnHKT4SJ": {"col": "qty_inspection_result", "type": "text"},# 수량검수결과
        "fld4D4eLx3YCIzamV": {"col": "move_request_completed", "type": "text"},# 이동신청완료여부

        # 프리징
        "fldM9wgxiYzlc5qZN": {"col": "frozen_qty", "type": "int"},           # 프리징된 이동 수량
        "fldMWKOPoUNPPsEeb": {"col": "frozen_item", "type": "text"},          # 프리징된 이동물품

        # 실사
        "fldEWUap1CLreP0E5": {"col": "audit_basket_qty", "type": "int"},      # 실사수량_바스켓
        "fldpdiusWlOkyXlIg": {"col": "physical_pre_adj_qty", "type": "int"},  # 실물수량(조정전)
        "fld4hd4xNkPktnocd": {"col": "adj_qty_check", "type": "int"},         # 조정수량(실재고체크용)

        # 프로젝트 연결
        "fldh2SAAq7u7tZUkG": {"col": "pkg_task", "type": "text"},            # pkg_task
        "fld2shN0SAXLxAO4L": {"col": "material_input_order", "type": "text"},# 자재투입이동_order
    }
}

# ── 3. order — 주문/발주 관리 ──
ORDER_TABLE = {
    "airtable_table_id": "tblJslWg8sYEdCkXw",
    "supabase_table": "orders",
    "fields": {
        # 식별자
        "fldmspypDdRUddatK": {"col": "order_id", "type": "text"},            # order_id
        "fldSDkjnxNPA440m5": {"col": "parts_name", "type": "text"},          # 파츠명
        "fldAwBcB4TqnIB5FF": {"col": "project_name", "type": "text"},        # 프로젝트명
        "fldgXFrvBimnCcZjC": {"col": "order_created_date", "type": "date"},  # Created time (구. 발주 신청일)
        "fldth8caK5QWRKogG": {"col": "created_time", "type": "date"},        # Created time

        # 수량
        "fldv9L49ZnrygSQAB": {"col": "order_qty", "type": "int"},            # 주문수량
        "fldF6gGoxfRh8wZkP": {"col": "po_qty", "type": "int"},              # 발주수량
        "fldM0esUw0gAOHrAh": {"col": "stock_out_qty", "type": "int"},       # 재고반출 수량 [Out]
        "fldytJlqnCJV3TOEf": {"col": "stock_in_qty", "type": "int"},        # 재고반입 수량 [IN]
        "fldC7is60MElWvn0J": {"col": "return_out_qty", "type": "int"},       # 반출 수량
        "fldrZ1gB32S5E1GZm": {"col": "return_in_qty", "type": "int"},       # 반입 수량
        "fldFmW2GITXBCMnhU": {"col": "stock_deduct_qty", "type": "int"},    # 재고 차감 수량
        "fld6KGgkMlda2EXZ5": {"col": "purchase_qty", "type": "int"},        # 매입 수량
        "fld30Qi7eiVUyQOV6": {"col": "return_in_func_qty", "type": "int"},  # 반입 수량 (기능)

        # 상태/분류
        "fldBlcddggQhkp7dm": {"col": "po_stage", "type": "text"},           # 발주단계
        "fldYpILSfwe4L6g5c": {"col": "stock_usage_purpose", "type": "text"},# 재고사용 목적
        "fld1HKC7VThMmNTML": {"col": "stock_production_status", "type": "text"},# 재고 생산 현황
        "fldk9aiUgvPnpk4Pd": {"col": "is_stock_item", "type": "text"},      # 재고 item 여부
        "fldOqcS3vSRAhSMbq": {"col": "managed_stock_flag", "type": "text[]"},# 관리재고 여부

        # 일자
        "fldIKSdgfBtY2582E": {"col": "inbound_date", "type": "date"},       # 입고일(종합)
        "fldgQAPO7hB06YfTk": {"col": "outbound_date", "type": "text"},      # 출고일
        "fld3k4voPiEOUSzyN": {"col": "separate_outbound_date", "type": "date"},# 별도 출고일
        "fldNeMqU5r8sYGGT1": {"col": "last_outbound_date", "type": "date"}, # 최종 출고일

        # 재고 위치
        "fldDGrQowO4ozHOlF": {"col": "stock_coordinates", "type": "text[]"},# 재고좌표
        "fldVjBjJH9BizAhKJ": {"col": "stock_location", "type": "text"},     # 재고위치
        "fldvfECAdrMYsKinD": {"col": "inbound_location", "type": "text"},    # 입고 위치
        "fldjdyMvh75wGiaTB": {"col": "outbound_location", "type": "text"},   # 출고 위치

        # 실사 관련
        "fld38084WoeebejmV": {"col": "audit_basket1_qty", "type": "int"},     # 실사수량_바스켓1
        "fldLy48odPSCL0jrf": {"col": "audit_basket2_qty", "type": "int"},     # 실사수량_바스켓2
        "fld6Fo3B4yNYI4HMu": {"col": "audit_basket3_qty", "type": "int"},     # 실사수량_바스켓3
        "fldHoxisBydUhJMBU": {"col": "audit_basket4_qty", "type": "int"},     # 실사수량_바스켓4
        "fldcnKHkImIv0cETB": {"col": "adj_qty", "type": "int"},              # 조정수량
        "fldYTUP7wlNYsy5pM": {"col": "physical_qty", "type": "int"},         # 실물수량
        "fld5uMGnlcUnM5RmC": {"col": "physical_pre_adj_qty", "type": "int"}, # 실물수량(조정전)
    }
}

# ── 4. project — 프로젝트 마스터 ──
PROJECT_TABLE = {
    "airtable_table_id": "tblMc5HLfMqe4g4pE",
    "supabase_table": "project",
    "fields": {
        "fldnUgnHtKkvdDQuE": {"col": "name", "type": "text"},
        "fldXAiGJ2AqfCJlIB": {"col": "project_status", "type": "text"},
        "fldFZfi69FwM2nui7": {"col": "customer_company", "type": "text"},
        "fldSYwUQeiqKfZd4M": {"col": "first_outbound_date", "type": "date"},
        "fldLg485uQYtiZpx9": {"col": "last_outbound_date", "type": "date"},
        "fldSxLVVzPWJVB6by": {"col": "outbound_days", "type": "int"},
        "fldWRcIIbiJBx4Xpd": {"col": "po_items", "type": "text"},
        "fldnPNbD1cYJWk4Sb": {"col": "logistics_new", "type": "text"},
        "flddkmvXH5Kp8Y1pz": {"col": "po_request_date", "type": "date"},
        "fldN1ZRWXJBz9mT0i": {"col": "fulfillment_leadtime", "type": "int"},
    }
}

# ── 전체 테이블 목록 ──
ALL_TABLES = [MATERIAL_TABLE, MOVEMENT_TABLE, ORDER_TABLE, PROJECT_TABLE]
