#!/usr/bin/env python3
"""
TMS Shipment 데이터에서 배송이벤트 + 택배추적로그 배치 생성 준비
"""
import json, re

# 새 쿼리에서 받은 전체 데이터 (3페이지)
# Page 1: 200건 (rec01w... ~ recS9U1...)
# Page 2: 200건 (recSDU9... ~ recrSIex...)
# Page 3: 71건 (recrX7Il... ~ reczs0o...)

NEW_QUERY_RECORDS_RAW = [
    # == PAGE 1 ==
    {"id": "rec01wO7RHxWihfDw", "date": "2026-03-17", "tracking": None},
    {"id": "rec02twUYG2ImZ4Tp", "date": "2026-03-24", "tracking": "PT2856-배송용외박스"},
    {"id": "rec03G9E8JmQO3Qlc", "date": "2026-03-03", "tracking": None},
    {"id": "rec04hez7M70wFsch", "date": "2026-03-04", "tracking": None},
    {"id": "rec05sqnALQV8d7wF", "date": "2026-03-04", "tracking": None},
    {"id": "rec0F5MwzryAFwTfI", "date": "2026-03-17", "tracking": None},
    {"id": "rec0LMTuEJdUkkWzS", "date": "2026-03-03", "tracking": "43905603685"},
    {"id": "rec0UsAJx1enZonjt", "date": "2026-04-06", "tracking": None},  # out of range
    {"id": "rec0V5Ur5OIAk5Acp", "date": "2026-04-09", "tracking": None},  # out of range
    {"id": "rec0YM3daLOZIt4p6", "date": "2026-03-11", "tracking": None},
]

# 실제로는 전체 471건을 처리해야 하므로, 아래 함수로 처리
# 이 파일은 테스트용이므로 실제 데이터는 직접 처리

print("Script ready. Use actual MCP data for processing.")
