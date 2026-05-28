"""Tests for change_detector — Contract C1 (신규 감지) / C2 (변경 감지)."""
from __future__ import annotations

from harness.dispatch.change_detector import ChangeReport, detect


# ─── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _rec(
    id_: str,
    ship_date: str = "2026-06-01",
    method: str = "택배",
    address: str = "서울 강남구",
    status: str = "배송준비",
    cbm: float = 1.5,
) -> dict:
    return {
        "id": id_,
        "fields": {
            "fldQvmEwwzvQW95h9": ship_date,
            "flduzH5tS7orqGG3o": [method],
            "fldyJHUh9gN44Ggnh": [address],
            "fldOhibgxg6LIpRTi": status,
            "fldaP8D9AM8CHEZ2o": cbm,
        },
    }


# ─── C1: 신규 TO 감지 ─────────────────────────────────────────────────────────

class TestAdded:
    """Contract C1 — 신규 TO 감지."""

    def test_empty_snapshot_all_added(self):
        recs = [_rec("rec001"), _rec("rec002")]
        report, _ = detect({}, recs)
        assert set(report.added) == {"rec001", "rec002"}
        assert report.removed == []
        assert report.critical_modified == []

    def test_new_id_detected(self):
        snapshot = {"rec001": {"출하확정일": "2026-06-01", "배송방식": "택배",
                                "주소": "서울 강남구", "발송상태": "배송준비", "cbm": 1.5}}
        recs = [_rec("rec001"), _rec("rec002")]
        report, _ = detect(snapshot, recs)
        assert report.added == ["rec002"]
        assert report.removed == []

    def test_no_change_no_added(self):
        snapshot = {"rec001": {"출하확정일": "2026-06-01", "배송방식": "택배",
                                "주소": "서울 강남구", "발송상태": "배송준비", "cbm": 1.5}}
        recs = [_rec("rec001")]
        report, _ = detect(snapshot, recs)
        assert report.added == []


# ─── C2: 취소 / Critical 변경 감지 ───────────────────────────────────────────

class TestRemovedAndModified:
    """Contract C2 — 취소 및 Critical 필드 변경 감지."""

    def test_removed_when_id_disappears(self):
        snapshot = {
            "rec001": {"출하확정일": "2026-06-01", "배송방식": "택배",
                        "주소": "서울 강남구", "발송상태": "배송준비", "cbm": 1.5},
            "rec002": {"출하확정일": "2026-06-02", "배송방식": "퀵",
                        "주소": "경기 성남시", "발송상태": "배송준비", "cbm": 0.8},
        }
        recs = [_rec("rec001")]  # rec002 사라짐
        report, _ = detect(snapshot, recs)
        assert report.removed == ["rec002"]

    def test_critical_ship_date_change(self):
        snapshot = {"rec001": {"출하확정일": "2026-06-01", "배송방식": "택배",
                                "주소": "서울 강남구", "발송상태": "배송준비", "cbm": 1.5}}
        recs = [_rec("rec001", ship_date="2026-06-05")]
        report, _ = detect(snapshot, recs)
        assert len(report.critical_modified) == 1
        assert report.critical_modified[0]["id"] == "rec001"
        assert report.critical_modified[0]["field"] == "출하확정일"

    def test_critical_method_change(self):
        snapshot = {"rec001": {"출하확정일": "2026-06-01", "배송방식": "택배",
                                "주소": "서울 강남구", "발송상태": "배송준비", "cbm": 1.5}}
        recs = [_rec("rec001", method="퀵")]
        report, _ = detect(snapshot, recs)
        assert any(m["field"] == "배송방식" for m in report.critical_modified)

    def test_critical_address_change(self):
        snapshot = {"rec001": {"출하확정일": "2026-06-01", "배송방식": "택배",
                                "주소": "서울 강남구", "발송상태": "배송준비", "cbm": 1.5}}
        recs = [_rec("rec001", address="부산 해운대구")]
        report, _ = detect(snapshot, recs)
        assert any(m["field"] == "주소" for m in report.critical_modified)

    def test_minor_cbm_change_not_critical(self):
        snapshot = {"rec001": {"출하확정일": "2026-06-01", "배송방식": "택배",
                                "주소": "서울 강남구", "발송상태": "배송준비", "cbm": 1.5}}
        recs = [_rec("rec001", cbm=2.0)]
        report, _ = detect(snapshot, recs)
        assert report.critical_modified == []
        assert len(report.minor_modified) == 1

    def test_new_snapshot_reflects_current(self):
        recs = [_rec("rec001", ship_date="2026-06-03")]
        _, new_snap = detect({}, recs)
        assert "rec001" in new_snap
        assert new_snap["rec001"]["출하확정일"] == "2026-06-03"
