"""Tests for otif_estimator — Contract C4 (OTIF 4케이스) / C5 (JSONL append)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from harness.dispatch.otif_estimator import OtifResult, estimate_all, otif_summary_by_wave


# ─── 헬퍼 ─────────────────────────────────────────────────────────────────────

def _rec(
    id_: str,
    ship_date: str | None = "2026-06-02",   # 월요일
    promise_date: str | None = "2026-06-05",
    method: str | None = "택배",
    pod_confirmed: str | None = None,
) -> dict:
    fields: dict = {}
    if ship_date:
        fields["fldQvmEwwzvQW95h9"] = ship_date
    if promise_date:
        fields["fldyYIfBhhu7sEX1P"] = promise_date
    if method:
        fields["flduzH5tS7orqGG3o"] = [method]
    if pod_confirmed:
        fields["fldNPH5xLdYevknfZ"] = pod_confirmed
    return {"id": id_, "fields": fields}


# ─── C4: OTIF 4케이스 ─────────────────────────────────────────────────────────

class TestOtifCases:
    """Contract C4 — 배송방식별 가정 OTIF."""

    def test_quick_on_time(self, tmp_path):
        # 퀵: assumed_pod = 출하확정일 당일
        # 출하 06-02 ≤ 약속 06-05 → on_time=True
        recs = [_rec("rec001", ship_date="2026-06-02", promise_date="2026-06-05", method="퀵")]
        results = estimate_all(recs, log_path=tmp_path / "otif.jsonl")
        assert len(results) == 1
        r = results[0]
        assert r.on_time is True
        assert r.assumed_pod == date(2026, 6, 2)
        assert r.method == "당일"

    def test_logen_on_time(self, tmp_path):
        # 택배: 월(06-02) +3 일요일skip → 목(06-05) ≤ 약속(06-05) → True
        recs = [_rec("rec001", ship_date="2026-06-02", promise_date="2026-06-05", method="택배")]
        results = estimate_all(recs, log_path=tmp_path / "otif.jsonl")
        r = results[0]
        assert r.on_time is True
        assert r.assumed_pod == date(2026, 6, 5)
        assert r.method == "로젠+3일"

    def test_logen_at_risk(self, tmp_path):
        # 택배: 월(06-02) +3 → 목(06-05) > 약속(06-04) → False
        recs = [_rec("rec001", ship_date="2026-06-02", promise_date="2026-06-04", method="택배")]
        results = estimate_all(recs, log_path=tmp_path / "otif.jsonl")
        r = results[0]
        assert r.on_time is False

    def test_skip_if_pod_confirmed(self, tmp_path):
        recs = [_rec("rec001", pod_confirmed="2026-06-03T14:00:00.000Z")]
        results = estimate_all(recs, log_path=tmp_path / "otif.jsonl")
        r = results[0]
        assert r.on_time is None
        assert r.method == "POD확인완료"

    def test_null_promise_date(self, tmp_path):
        recs = [_rec("rec001", promise_date=None)]
        results = estimate_all(recs, log_path=tmp_path / "otif.jsonl")
        r = results[0]
        assert r.on_time is None
        assert r.method == "측정불가"

    def test_null_method(self, tmp_path):
        recs = [_rec("rec001", method=None)]
        results = estimate_all(recs, log_path=tmp_path / "otif.jsonl")
        r = results[0]
        assert r.on_time is None
        assert r.method == "측정불가"


# ─── 실제 접미사 배송방식 값 (2026-06-22 substring-match fix) ──────────────────

class TestSuffixedMethods:
    """실제 Airtable 값은 '퀵(수도권)'·'택배(일반)' 등 접미사 포함 — 정확일치였다면 전부 측정불가."""

    @pytest.mark.parametrize("method", ["퀵(수도권)", "퀵(지방)", "고객직접퀵배차", "신시어리퀵", "자체기사", "바로고"])
    def test_quick_variants_are_same_day(self, tmp_path, method):
        recs = [_rec("r", ship_date="2026-06-02", promise_date="2026-06-05", method=method)]
        r = estimate_all(recs, log_path=tmp_path / "otif.jsonl")[0]
        assert r.method == "당일"
        assert r.assumed_pod == date(2026, 6, 2)

    @pytest.mark.parametrize("method", ["택배(일반)", "택배(제주산간)", "신시어리택배"])
    def test_parcel_variants_are_logen(self, tmp_path, method):
        recs = [_rec("r", ship_date="2026-06-02", promise_date="2026-06-05", method=method)]
        r = estimate_all(recs, log_path=tmp_path / "otif.jsonl")[0]
        assert r.method == "로젠+3일"

    def test_self_pickup_unmeasurable(self, tmp_path):
        recs = [_rec("r", method="고객직접수령")]
        r = estimate_all(recs, log_path=tmp_path / "otif.jsonl")[0]
        assert r.method == "측정불가"


# ─── C5: JSONL append-only ────────────────────────────────────────────────────

class TestJsonlAppend:
    """Contract C5 — JSONL append-only, 2회 호출 시 2배 줄수."""

    def test_appends_one_line_per_shipment(self, tmp_path):
        log = tmp_path / "otif.jsonl"
        recs = [_rec("rec001"), _rec("rec002")]
        estimate_all(recs, log_path=log)
        lines = log.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2

    def test_second_call_appends(self, tmp_path):
        log = tmp_path / "otif.jsonl"
        recs = [_rec("rec001")]
        estimate_all(recs, log_path=log)
        estimate_all(recs, log_path=log)
        lines = log.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2

    def test_jsonl_valid_json(self, tmp_path):
        log = tmp_path / "otif.jsonl"
        recs = [_rec("rec001", method="퀵")]
        estimate_all(recs, log_path=log)
        for line in log.read_text(encoding="utf-8").strip().splitlines():
            obj = json.loads(line)
            assert "ts" in obj
            assert "record_id" in obj
            assert "method" in obj


# ─── otif_summary_by_wave ─────────────────────────────────────────────────────

class TestOtifSummary:
    def test_summary_groups_by_wave(self):
        from harness.dispatch.wave_assigner import Shipment, WavePlan
        results = [
            OtifResult(record_id="r1", on_time=True, assumed_pod=date(2026, 6, 5), method="당일"),
            OtifResult(record_id="r2", on_time=False, assumed_pod=date(2026, 6, 6), method="로젠+3일"),
            OtifResult(record_id="r3", on_time=None, assumed_pod=None, method="측정불가"),
        ]
        w1 = WavePlan("W1")
        w1.shipments = [Shipment(id="r1", project_code="P1", slot="오전", region="tier1_seoul", cbm=1.0)]
        w2 = WavePlan("W2")
        w2.shipments = [Shipment(id="r2", project_code="P2", slot="오전", region="tier1_seoul", cbm=1.0)]
        manual = WavePlan("수동")
        manual.shipments = [Shipment(id="r3", project_code="P3", slot=None, region="tier1_seoul", cbm=0.5)]
        plans = {"W1": w1, "W2": w2, "수동": manual}

        summary = otif_summary_by_wave(results, plans)
        assert summary["W1"] == {"total": 1, "on_time": 1, "at_risk": 0}
        assert summary["W2"] == {"total": 1, "on_time": 0, "at_risk": 1}
        assert "수동" not in summary
