"""Import smoke — A3가 tms_weekly_runner에서 삭제한 TRUCK_CAPACITY_M3를 재export로
후방 importer(tms_iter7/iter8_analyzer)가 깨지지 않도록 보호 (P2 review fix)."""
import importlib


def test_tms_weekly_runner_reexports_truck_capacity():
    twr = importlib.import_module("scripts.tms_weekly_runner")
    # 라이브 차량한도 실측 fallback (구 하드코딩 7.6/7.6/9.5 아님)
    assert twr.TRUCK_CAPACITY_M3 == {"이장훈": 4.5, "조희선": 7.616, "박종성": 9.486}


def test_iter7_iter8_import_without_error():
    importlib.import_module("scripts.tms_iter7_analyzer")
    importlib.import_module("scripts.tms_iter8_analyzer")
