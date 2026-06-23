"""AUDIT (2026-06-23) — _spillover_target 성수기/소형 라우팅 + _ensure_minimum_load 외부퀵 가드."""
from harness.dispatch.wave_assigner import (
    WAVE_IDS, Shipment, WavePlan, _ensure_minimum_load, _spillover_target,
)


def _plans(by):
    p = {w: WavePlan(w) for w in WAVE_IDS}
    for w, ships in by.items():
        p[w].shipments = list(ships)
    return p


class TestSpilloverTarget:
    def test_peak_small_nonquick_to_gogox(self):
        assert _spillover_target('tier1_seoul', [0.3], 'peak', method='택배(일반)') == 'spillover_고고엑스'

    def test_offpeak_small_to_logen(self):
        assert _spillover_target('tier1_seoul', [0.3], 'off-peak', method='택배(일반)') == 'spillover_로젠'

    def test_peak_large_to_logen(self):
        assert _spillover_target('tier1_seoul', [2.0], 'peak', method='택배(일반)') == 'spillover_로젠'

    def test_quick_always_gogox(self):
        assert _spillover_target('tier5_provincial', [5.0], 'off-peak', method='퀵(수도권)') == 'spillover_고고엑스'


class TestMinLoadQuickGuard:
    def test_external_quick_not_pulled_to_driver(self):
        # W1·W2 비어있고 donor(고고엑스)에 외부 퀵만 → 자체기사 트럭으로 끌어오지 않음
        q1 = Shipment('q1', 'P', '오전', 'tier1_seoul', 1.0, method='퀵(수도권)')
        q2 = Shipment('q2', 'P', '오전', 'tier1_seoul', 1.0, method='퀵(수도권)')
        out = _ensure_minimum_load(_plans({'spillover_고고엑스': [q1, q2]}))
        assert out['W1'].count == 0 and out['W2'].count == 0
        assert out['spillover_고고엑스'].count == 2

    def test_own_driver_cargo_still_redistributed(self):
        # '자체기사' 화물은 W3→W1/W2 재배치 정상 (가드가 막으면 안 됨)
        s1 = Shipment('s1', 'P', '오전', 'tier1_seoul', 1.0, method='자체기사')
        s2 = Shipment('s2', 'P', '오전', 'tier1_seoul', 1.0, method='자체기사')
        out = _ensure_minimum_load(_plans({'W3': [s1, s2]}))
        assert out['W1'].count >= 1 or out['W2'].count >= 1
