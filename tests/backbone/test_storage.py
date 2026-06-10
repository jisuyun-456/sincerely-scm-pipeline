"""storage — 보관 occupied CBM 분자 집계 테스트 (P3' T3)."""
from harness.backbone.storage import aggregate_occupied, parse_pt_from_ledger_key


# ── parse_pt_from_ledger_key ─────────────────────────────────────────────────
def test_parse_ledger_key_basic():
    assert parse_pt_from_ledger_key("PT0510|BW01-ST-A01|UNRESTRICTED") == "PT0510"


def test_parse_ledger_key_bare_pt():
    assert parse_pt_from_ledger_key("PT0510") == "PT0510"


def test_parse_ledger_key_non_pt():
    assert parse_pt_from_ledger_key("굿즈명|BIN|TYPE") is None
    assert parse_pt_from_ledger_key("") is None


# ── aggregate_occupied ───────────────────────────────────────────────────────
_ROWS = [
    {"pt": "PT0001", "stock": 100, "warehouse": "베스트원", "zone_type": "STORAGE",
     "stock_type": "UNRESTRICTED"},
    {"pt": "PT0002", "stock": 50, "warehouse": "베스트원", "zone_type": "STORAGE",
     "stock_type": "UNRESTRICTED"},
    {"pt": "PT0003", "stock": 10, "warehouse": "에이원센터", "zone_type": "STORAGE",
     "stock_type": "UNRESTRICTED"},
    # 필터 제외 대상
    {"pt": "PT0004", "stock": 99, "warehouse": "베스트원", "zone_type": "INBOUND_STAGING",
     "stock_type": "UNRESTRICTED"},
    {"pt": "PT0005", "stock": 99, "warehouse": "베스트원", "zone_type": "STORAGE",
     "stock_type": "QC_HOLD"},
]
_CBM = {"PT0001": 0.001, "PT0003": 0.01}   # PT0002 미해소


def test_aggregate_by_warehouse():
    out = aggregate_occupied(_ROWS, _CBM)
    bw = out["by_warehouse"]["베스트원"]
    assert abs(bw["occupied_cbm"] - 0.1) < 1e-9       # 100 × 0.001
    assert bw["pt_covered"] == 1 and bw["pt_uncovered"] == 1
    assert bw["stock_uncovered"] == 50
    a1 = out["by_warehouse"]["에이원센터"]
    assert abs(a1["occupied_cbm"] - 0.1) < 1e-9       # 10 × 0.01
    assert a1["pt_uncovered"] == 0


def test_aggregate_filters_zone_and_stock_type():
    out = aggregate_occupied(_ROWS, _CBM)
    # PT0004(INBOUND_STAGING)·PT0005(QC_HOLD)는 전체 집계에서 제외
    assert out["n_rows_filtered"] == 3
    assert "PT0004" not in out["uncovered_pts"] and "PT0005" not in out["uncovered_pts"]


def test_aggregate_totals_and_coverage():
    out = aggregate_occupied(_ROWS, _CBM)
    assert abs(out["total_occupied_cbm"] - 0.2) < 1e-9
    assert out["pt_coverage_pct"] == 66.7              # 2/3 distinct PT
    assert out["uncovered_pts"] == ["PT0002"]


def test_aggregate_empty():
    out = aggregate_occupied([], {})
    assert out["total_occupied_cbm"] == 0.0
    assert out["by_warehouse"] == {}
    assert out["pt_coverage_pct"] == 0.0
