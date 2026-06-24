"""Chain C — 배차 재분배 overbook alert tests.

조희선(W2) 과적 감지 → 박종성(W3)/이장훈(W1) 동일일 흡수 여력 + 경기 surcharge 노출.
2026-06-24 진단(배차적재율-통합진단 / 조희선-차량적정성-평가)의 무비용 재분배 규칙을
read-only alert 로 코드화. 배차일지 33일 stale → dispatch-day reconstruction 기반.
"""
from __future__ import annotations

import pytest

from harness.dispatch.wave_assigner import Shipment
from scripts.dispatch.overbook_alert import compute_overbook, format_alert

# 라이브 차량한도 (utils/vehicle_util FALLBACK_CAP 과 동일, 2026-06-24 실측)
CAPS = {"이장훈": 4.5, "조희선": 7.616, "박종성": 9.486}


def _ship(sid, region, cbm, partner):
    return Shipment(sid, "PNA-X", "오전", region, cbm, assigned_partner=partner)


class TestComputeOverbook:
    def test_flags_cho_when_over_threshold(self):
        # 8.0 / 7.616 = 1.05 > 0.95 → flagged, not artifact
        by_date = {"2026-06-26": [_ship("A", "tier1_seoul", 8.0, "신시어리 (조희선)")]}
        res = compute_overbook(by_date, CAPS)
        assert len(res) == 1
        assert res[0]["date"] == "2026-06-26"
        assert res[0]["cho_util"] > 1.0
        assert res[0]["artifact"] is False

    def test_no_flag_when_under_threshold(self):
        # 6.0 / 7.616 = 0.79 < 0.95 → no alert
        by_date = {"2026-06-26": [_ship("A", "tier1_seoul", 6.0, "조희선")]}
        assert compute_overbook(by_date, CAPS) == []

    def test_artifact_when_util_exceeds_ceiling(self):
        # 40 / 7.616 = 5.25 > 2.0 ceiling → multi-run artifact (05-22 544% 부류)
        by_date = {"2026-05-22": [_ship("A", "tier1_seoul", 40.0, "조희선")]}
        res = compute_overbook(by_date, CAPS)
        assert len(res) == 1
        assert res[0]["artifact"] is True

    def test_overflow_and_park_absorbs(self):
        # overflow = 8.616 - 7.616 = 1.0 ; park spare 9.486-1.0 = 8.486 >= 1.0
        by_date = {"2026-06-26": [
            _ship("A", "tier1_seoul", 8.616, "조희선"),
            _ship("B", "tier1_seoul", 1.0, "박종성"),
        ]}
        res = compute_overbook(by_date, CAPS)
        assert res[0]["overflow_cbm"] == pytest.approx(1.0)
        assert res[0]["park_absorbs"] is True
        assert res[0]["partial_absorbs"] is False

    def test_partial_absorption_when_park_alone_insufficient(self):
        # overflow = 12 - 7.616 = 4.384 ; park spare 9.486-6 = 3.486 < 4.384
        # park+lee spare = 3.486 + 4.5 = 7.986 >= 4.384 → partial
        by_date = {"2026-06-26": [
            _ship("A", "tier1_seoul", 12.0, "조희선"),
            _ship("B", "tier1_seoul", 6.0, "박종성"),
        ]}
        res = compute_overbook(by_date, CAPS)
        assert res[0]["park_absorbs"] is False
        assert res[0]["partial_absorbs"] is True

    def test_surcharge_exposure_from_gyeonggi(self):
        # 3 경기건, load 8.5 > 7.616 ; exposure = (3-1) * 30000 = 60000
        by_date = {"2026-06-26": [
            _ship("A", "tier3_gyeonggi_etc", 3.0, "조희선"),
            _ship("B", "tier3_gyeonggi_etc", 3.0, "조희선"),
            _ship("C", "tier3_gyeonggi_etc", 2.5, "조희선"),
        ]}
        res = compute_overbook(by_date, CAPS)
        assert res[0]["cho_gyeonggi"] == 3
        assert res[0]["surcharge_exposure"] == 60_000

    def test_skips_unknown_drivers(self):
        # 외부 퀵(고고엑스)은 기사 부하 집계에서 제외
        by_date = {"2026-06-26": [
            _ship("A", "tier1_seoul", 8.0, "조희선"),
            _ship("X", "tier1_seoul", 5.0, "고고엑스"),
        ]}
        res = compute_overbook(by_date, CAPS)
        assert res[0]["cho_count"] == 1

    def test_uses_live_cap_map_not_fallback(self):
        # 라이브 차량한도가 작으면 그 값으로 util 산정 (SSOT 우선)
        caps = {"조희선": 5.0, "박종성": 9.486, "이장훈": 4.5}
        by_date = {"2026-06-26": [_ship("A", "tier1_seoul", 5.5, "조희선")]}
        res = compute_overbook(by_date, caps)
        assert res[0]["cho_cap"] == 5.0
        assert res[0]["cho_util"] == pytest.approx(1.1)

    def test_missing_cho_cap_falls_back(self):
        # cap_map 에 조희선 정원 부재 → FALLBACK_CAP(7.616) 사용
        caps = {"박종성": 9.486}
        by_date = {"2026-06-26": [_ship("A", "tier1_seoul", 8.0, "조희선")]}
        res = compute_overbook(by_date, caps)
        assert res[0]["cho_cap"] == pytest.approx(7.616)


class TestFormatAlert:
    def test_empty_results_returns_ok_message(self):
        lines = format_alert([], days=7)
        text = "\n".join(lines)
        assert "이상 없음" in text

    def test_flagged_date_in_output(self):
        results = [{
            "date": "2026-06-26", "cho_load": 8.0, "cho_cap": 7.616, "cho_util": 1.05,
            "cho_count": 5, "cho_gyeonggi": 3, "surcharge_exposure": 60000,
            "park_spare": 8.0, "lee_spare": 2.0, "overflow_cbm": 0.384,
            "park_absorbs": True, "partial_absorbs": False, "artifact": False,
        }]
        text = "\n".join(format_alert(results, days=7))
        assert "조희선" in text
        assert "2026-06-26" in text
        assert "박종성" in text

    def test_near_capacity_labeled_distinctly_from_overbook(self):
        # 95~100% = 용량 임박(잔여 표시), >100% = 과적(초과 표시)
        near = [{"date": "2026-06-25", "cho_load": 7.57, "cho_cap": 7.62, "cho_util": 0.99,
                 "cho_count": 2, "cho_gyeonggi": 0, "surcharge_exposure": 0,
                 "park_spare": 8.99, "lee_spare": 0.0, "overflow_cbm": 0.0,
                 "park_absorbs": True, "partial_absorbs": False, "artifact": False}]
        text = "\n".join(format_alert(near, days=14))
        assert "용량 임박" in text and "잔여" in text
        assert "초과" not in text

        over = [{"date": "2026-06-26", "cho_load": 8.5, "cho_cap": 7.62, "cho_util": 1.12,
                 "cho_count": 3, "cho_gyeonggi": 2, "surcharge_exposure": 30000,
                 "park_spare": 5.0, "lee_spare": 2.0, "overflow_cbm": 0.88,
                 "park_absorbs": True, "partial_absorbs": False, "artifact": False}]
        text2 = "\n".join(format_alert(over, days=14))
        assert "초과 0.88m³" in text2

    def test_prioritizes_lee_zero_marginal_over_park(self):
        # 이장훈(flat daily, 동일일 추가 ₩0) 우선 표기 → 박종성(거리비례 요금). ₩0은 이장훈에만.
        res = [{"date": "2026-06-26", "cho_load": 8.5, "cho_cap": 7.62, "cho_util": 1.12,
                "cho_count": 3, "cho_gyeonggi": 2, "surcharge_exposure": 30000,
                "park_spare": 5.0, "lee_spare": 2.0, "overflow_cbm": 0.88,
                "park_absorbs": True, "partial_absorbs": False, "artifact": False}]
        text = "\n".join(format_alert(res, days=14))
        assert "이장훈 여유 2.00m³ (비경기 한계비용 ₩0) → 박종성 여유 5.00m³" in text
        # 박종성에 ₩0 한계비용을 잘못 부여하던 문구 제거 확인
        assert "박종성 이전 시 절감 (동일일 한계비용 ₩0)" not in text

    def test_no_absorb_capacity_when_both_helpers_full(self):
        # 용량 임박(overflow=0)인데 박종성·이장훈 둘 다 여유 0 → '흡수 여력 부족' (오인 방지)
        res = [{"date": "2026-06-25", "cho_load": 7.57, "cho_cap": 7.62, "cho_util": 0.99,
                "cho_count": 2, "cho_gyeonggi": 0, "surcharge_exposure": 0,
                "park_spare": 0.0, "lee_spare": 0.0, "overflow_cbm": 0.0,
                "park_absorbs": True, "partial_absorbs": False, "artifact": False}]
        text = "\n".join(format_alert(res, days=14))
        assert "흡수 여력 부족" in text
        assert "박종성 단독 흡수 가능" not in text

    def test_artifact_segregated_from_actionable(self):
        results = [
            {"date": "2026-06-26", "cho_load": 8.0, "cho_cap": 7.616, "cho_util": 1.05,
             "cho_count": 5, "cho_gyeonggi": 1, "surcharge_exposure": 0,
             "park_spare": 8.0, "lee_spare": 2.0, "overflow_cbm": 0.384,
             "park_absorbs": True, "partial_absorbs": False, "artifact": False},
            {"date": "2026-05-22", "cho_load": 40.0, "cho_cap": 7.616, "cho_util": 5.25,
             "cho_count": 9, "cho_gyeonggi": 4, "surcharge_exposure": 90000,
             "park_spare": 1.0, "lee_spare": 0.0, "overflow_cbm": 32.0,
             "park_absorbs": False, "partial_absorbs": False, "artifact": True},
        ]
        text = "\n".join(format_alert(results, days=30))
        # 아티팩트는 별도 라벨로 분리 표기 (실행 액션 아님)
        assert "아티팩트" in text or "artifact" in text.lower()
        assert "2026-05-22" in text
