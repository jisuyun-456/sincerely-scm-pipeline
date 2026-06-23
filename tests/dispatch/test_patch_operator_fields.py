"""운영자 소유 필드 보호 회귀 테스트 (2026-06-22).

#4: wave_locked 는 운영자 입력 — 추천기 PATCH 에 절대 포함 금지.
#8/#20: 배송슬롯은 잠금 안 됐고 현재 비어있을 때만 추천값 기입 (운영자 수정 덮어쓰기 금지).
"""
from harness.dispatch import wave_recommender as wr
from harness.dispatch.wave_assigner import WAVE_IDS, Shipment, WavePlan


def _plans(by_wave):
    plans = {w: WavePlan(w) for w in WAVE_IDS}
    for w, ships in by_wave.items():
        plans[w].shipments = list(ships)
    return plans


def _ship(sid, slot="오전", locked=False):
    return Shipment(sid, "PNA-A", slot, "tier1_seoul", 1.0,
                    slot_confidence=1.0, cbm_confidence=1.0, wave_locked=locked)


def _run(monkeypatch, plans, current_slots):
    monkeypatch.setattr(wr, "_patch_batch", lambda batch: None)
    return wr.patch_airtable(plans, {}, "2026-06-22T00:00:00+09:00", current_slots)


def test_wave_locked_never_in_payload(monkeypatch):
    s = _ship("rec1")
    diff = _run(monkeypatch, _plans({"W1": [s]}), {})
    assert all(wr.FLD_WAVE_LOCKED not in r["fields"] for r in diff)


def test_slot_written_when_current_empty_and_unlocked(monkeypatch):
    s = _ship("rec1", slot="오전", locked=False)
    diff = _run(monkeypatch, _plans({"W1": [s]}), {"rec1": None})
    assert diff[0]["fields"][wr.FLD_SLOT] == "오전"


def test_slot_not_overwritten_when_operator_set(monkeypatch):
    s = _ship("rec1", slot="오전", locked=False)
    diff = _run(monkeypatch, _plans({"W1": [s]}), {"rec1": "오후 1 (오후 2시 - 4시)"})
    assert wr.FLD_SLOT not in diff[0]["fields"]


def test_slot_not_written_when_locked(monkeypatch):
    s = _ship("rec1", slot="오전", locked=True)
    diff = _run(monkeypatch, _plans({"수동": [s]}), {"rec1": None})
    assert wr.FLD_SLOT not in diff[0]["fields"]


def test_recommendation_fields_always_present(monkeypatch):
    s = _ship("rec1")
    diff = _run(monkeypatch, _plans({"W1": [s]}), {})
    f = diff[0]["fields"]
    assert f[wr.FLD_WAVE_REC] == "이장훈 기사님"
    assert f[wr.FLD_WAVE_UPDATED] == "2026-06-22T00:00:00+09:00"
    assert wr.FLD_WAVE_CONF in f
