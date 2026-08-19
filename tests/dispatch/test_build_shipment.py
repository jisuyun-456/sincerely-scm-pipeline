"""_build_shipment wires 수령 시간(카테고리) into decide_slot (2026-08-19)."""
from harness.dispatch import wave_recommender as wr


def _rec(method="퀵(수도권)", hope_time=None, receipt_category=None, wave_locked=False):
    fields = {wr.FLD_METHOD: [method] if method else []}
    if hope_time is not None:
        fields[wr.FLD_HOPE_TIME] = [hope_time]
    if receipt_category is not None:
        fields[wr.FLD_RECEIPT_CATEGORY] = [receipt_category]
    if wave_locked:
        fields[wr.FLD_WAVE_LOCKED] = True
    return {"id": "rec1", "fields": fields}


def test_receipt_category_field_read_and_passed_through():
    # 카테고리가 명확하면(오전) 넓은 split 텍스트보다 우선해야 함 (Task 2 로직 재확인)
    rec = _rec(hope_time="09:00 ~ 11:00 / 13:00 ~ 16:00", receipt_category="오전")
    s = wr._build_shipment(rec)
    assert s is not None
    assert s.slot == "오전"
    assert s.slot_confidence == 0.95


def test_missing_receipt_category_falls_back_to_text_parse():
    rec = _rec(hope_time="14:00~16:00", receipt_category=None)
    s = wr._build_shipment(rec)
    assert s.slot == "오후 1 (오후 2시 - 4시)"
    assert s.slot_confidence == 0.9
