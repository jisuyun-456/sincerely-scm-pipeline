"""mes_forecast — MES 납기일 → 입하 CBM forecast 테스트 (P3' T6)."""
from datetime import date

from harness.backbone.mes_forecast import build_inbound_forecast

_TODAY = date(2026, 6, 10)
_NAME2CODE = {"골프공": "GOLF", "어댑터": "ADPT"}
_PRODUCT = {"GOLF": (10, 0.05), "ADPT": (1, 0.002)}   # code -> (qty_per_box, cbm_per_box)


def _row(goods, due, qty, status="대기"):
    f = {}
    if goods is not None:
        f["굿즈"] = [goods]
    if due is not None:
        f["납기일"] = [due]
    if qty is not None:
        f["계획수량"] = [qty]
    if status is not None:
        f["작업 상태"] = status
    return f


def test_horizon_bucketing_cumulative():
    rows = [
        _row("골프공", "2026-06-13", 20),   # +3d → 7d·14d 포함, ceil(20/10)*0.05=0.1
        _row("어댑터", "2026-06-20", 5),    # +10d → 14d만, 5*0.002=0.01
        _row("골프공", "2026-07-10", 10),   # +30d → 범위 외
    ]
    out = build_inbound_forecast(rows, _NAME2CODE, _PRODUCT, _TODAY)
    assert abs(out["by_horizon"][7] - 0.1) < 1e-9
    assert abs(out["by_horizon"][14] - 0.11) < 1e-9
    # n_joined = join 성공 전체 (horizon 밖 +30d 포함 — join rate KPI)
    assert out["n_joined"] == 3
    assert "2026-07-10" in out["by_date"]


def test_completed_status_excluded():
    rows = [_row("골프공", "2026-06-13", 20, status="완료")]
    out = build_inbound_forecast(rows, _NAME2CODE, _PRODUCT, _TODAY)
    assert out["n_excluded_status"] == 1
    assert out["by_horizon"][7] == 0.0


def test_blank_status_included():
    rows = [_row("골프공", "2026-06-13", 20, status=None)]
    out = build_inbound_forecast(rows, _NAME2CODE, _PRODUCT, _TODAY)
    assert out["n_joined"] == 1


def test_missing_date_and_unmatched_counted():
    rows = [
        _row("골프공", None, 20),          # 납기일 없음
        _row("미지굿즈", "2026-06-13", 5),  # crosswalk 미스
        _row(None, "2026-06-13", 5),       # 굿즈 없음
    ]
    out = build_inbound_forecast(rows, _NAME2CODE, _PRODUCT, _TODAY)
    assert out["n_no_date"] == 1
    assert out["n_unmatched_code"] == 2


def test_goods_name_normalized_for_join():
    # 크로스워크 join은 normalize_goods 적용 — '[2]' 인덱스 등 제거
    rows = [_row("골프공 [2]", "2026-06-13", 10)]
    out = build_inbound_forecast(rows, _NAME2CODE, _PRODUCT, _TODAY)
    assert out["n_joined"] == 1


def test_past_due_not_in_horizon():
    rows = [_row("골프공", "2026-06-01", 10)]   # 과거 납기 → horizon 제외, 별도 카운트
    out = build_inbound_forecast(rows, _NAME2CODE, _PRODUCT, _TODAY)
    assert out["by_horizon"][7] == 0.0
    assert out["n_past_due"] == 1
