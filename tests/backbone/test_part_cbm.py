"""part_cbm — PT→치수→m³ + QC버킷 + tier 사다리 테스트 (P3' T1)."""
from harness.backbone.part_cbm import (
    QC_BUCKET_MEDIAN_M3,
    QC_TERTILE_T1_M3,
    QC_TERTILE_T2_M3,
    calc_cbm,
    classify_qc_bucket,
    parse_dims_mm,
    part_cbm_for_pt,
    qc_bucket_cbm,
)


# ── parse_dims_mm ────────────────────────────────────────────────────────────
def test_parse_3axis():
    assert parse_dims_mm("248*190*33") == (248.0, 190.0, 33.0)
    assert parse_dims_mm("88x88x163") == (88.0, 88.0, 163.0)


def test_parse_2axis_min_thickness():
    assert parse_dims_mm("200x300") == (200.0, 300.0, 3.0)


def test_parse_strips_unfolded_tail():
    # '펼침' 뒤 치수는 무시
    assert parse_dims_mm("55x160mm 펼침 124*160") == (55.0, 160.0, 3.0)


def test_parse_unparseable():
    assert parse_dims_mm("규격 미정") is None
    assert parse_dims_mm("") is None


def test_parse_axis_over_5000mm_rejected():
    assert parse_dims_mm("6000x100x100") is None


def test_parse_axis_under_1mm_rejected():
    assert parse_dims_mm("0.5x100x100") is None


def test_parse_film_explicit_thin_thickness():
    # 필름 두께(3축)는 1mm 미만 허용 — W/H는 정상이므로 통째 거부 금지
    assert parse_dims_mm("135x195x0.04") == (135.0, 195.0, 0.04)


def test_parse_pouch_thin_thickness():
    assert parse_dims_mm("200x300x0.1") == (200.0, 300.0, 0.1)


def test_parse_thickness_below_floor_rejected():
    # 두께 0.005 < MIN_THICKNESS_FLOOR_MM(0.01) = 진짜 노이즈 → 거부
    assert parse_dims_mm("100x100x0.005") is None


def test_parse_wh_under_1mm_still_rejected():
    # 두께 하한 완화가 W/H 축에는 영향 없음 (0.5는 W축이라 여전히 거부)
    assert parse_dims_mm("0.5x100x100") is None


# ── calc_cbm ─────────────────────────────────────────────────────────────────
def test_calc_cbm_basic():
    cbm, ok = calc_cbm("480*380*270", 1)
    assert ok and abs(cbm - 0.049248) < 1e-6


def test_calc_cbm_zero_qty():
    assert calc_cbm("480*380*270", 0) == (0.0, False)


def test_calc_cbm_unit_over_5m3_rejected():
    # 2000*2000*2000mm = 8 m³ > MAX_UNIT_CBM 5 m³
    assert calc_cbm("2000*2000*2000", 1) == (0.0, False)


def test_calc_cbm_film_value():
    # 135x195x0.04mm = 1.053e-06 m³ (6자리 반올림 → 1e-06), 핵심은 ok=True
    cbm, ok = calc_cbm("135x195x0.04", 1)
    assert ok and cbm > 0 and abs(cbm - 1e-06) < 1e-9


# ── QC 버킷 ──────────────────────────────────────────────────────────────────
def test_classify_qc_bucket_boundaries():
    assert classify_qc_bucket(QC_TERTILE_T1_M3 / 2) == "소"
    assert classify_qc_bucket(QC_TERTILE_T1_M3) == "소"          # <= t1
    assert classify_qc_bucket((QC_TERTILE_T1_M3 + QC_TERTILE_T2_M3) / 2) == "중"
    assert classify_qc_bucket(QC_TERTILE_T2_M3) == "중"          # <= t2
    assert classify_qc_bucket(QC_TERTILE_T2_M3 * 2) == "대"


def test_qc_bucket_cbm_returns_median():
    for bucket in ("소", "중", "대"):
        assert qc_bucket_cbm(bucket) == QC_BUCKET_MEDIAN_M3[bucket]
    assert qc_bucket_cbm("없는버킷") is None


# ── part_cbm_for_pt tier 사다리 ──────────────────────────────────────────────
_ITEM_MASTER = {"PT0001": (0.0025, "TMS_Product")}
_SP_LOOKUP = {"PT0002": "100x100x100", "PT0003": "", "PT0006": "글자만있음"}
_MOV_SPEC = {"PT0003": "200*100*50"}
_QC_BUCKET = {"PT0004": "중"}


def test_tier0_existing_item_master_wins():
    # 기존 ItemMaster CBM 불가침 — sp_lookup에 있어도 기존 값 유지
    cbm, conf, tier = part_cbm_for_pt(
        "PT0001", _ITEM_MASTER, {"PT0001": "999x999x999"}, _MOV_SPEC, _QC_BUCKET)
    assert (cbm, conf, tier) == (0.0025, 1.0, "기존")


def test_tier1_sync_parts_dims():
    cbm, conf, tier = part_cbm_for_pt("PT0002", _ITEM_MASTER, _SP_LOOKUP, _MOV_SPEC, _QC_BUCKET)
    assert abs(cbm - 0.001) < 1e-9
    assert (conf, tier) == (0.55, "치수파싱")


def test_tier3_movement_spec_fallback():
    # sp 규격 blank → movement 제품규격으로 산출
    cbm, conf, tier = part_cbm_for_pt("PT0003", _ITEM_MASTER, _SP_LOOKUP, _MOV_SPEC, _QC_BUCKET)
    assert abs(cbm - 0.001) < 1e-9
    assert (conf, tier) == (0.55, "치수파싱")


def test_tier4_qc_bucket_fallback():
    cbm, conf, tier = part_cbm_for_pt("PT0004", _ITEM_MASTER, _SP_LOOKUP, _MOV_SPEC, _QC_BUCKET)
    assert cbm == QC_BUCKET_MEDIAN_M3["중"]
    assert (conf, tier) == (0.40, "QC버킷")


def test_no_source_unresolved():
    cbm, conf, tier = part_cbm_for_pt("PT0005", _ITEM_MASTER, _SP_LOOKUP, _MOV_SPEC, _QC_BUCKET)
    assert (cbm, conf, tier) == (0.0, 0.0, "미산출")


def test_unparseable_spec_falls_through_to_qc():
    # 규격이 있어도 파싱 불가면 다음 tier로
    qc = {"PT0006": "소"}
    cbm, conf, tier = part_cbm_for_pt("PT0006", _ITEM_MASTER, _SP_LOOKUP, {}, qc)
    assert cbm == QC_BUCKET_MEDIAN_M3["소"]
    assert (conf, tier) == (0.40, "QC버킷")


def test_optional_maps_default_none():
    cbm, conf, tier = part_cbm_for_pt("PT0002", _ITEM_MASTER, _SP_LOOKUP)
    assert (conf, tier) == (0.55, "치수파싱")
