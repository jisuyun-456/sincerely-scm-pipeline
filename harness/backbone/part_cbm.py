"""part_cbm — PT 파츠 단위 CBM 산출 (보관·입하 공용, P3').

치수 파싱의 단일 소스. utils/cbm_utils.py·scripts/cbm_inbound_check.py의
중복 파서를 이 모듈로 통합한다(기존 호출자는 re-export shim으로 무파손).

tier 사다리 (spec 2026-06-09 §6 정렬):
  기존(ItemMaster CBM>0, 불가침) > 치수파싱(sync_parts 규격 → movement 제품규격) 0.55
  > QC버킷(소/중/대 median) 0.40 > 미산출 0.0
"""
from __future__ import annotations

# ── 파싱 sanity bounds ───────────────────────────────────────────────────────
MIN_AXIS_MM = 1.0        # W/H 축 sub-mm 노이즈 거부
MAX_AXIS_MM = 5000.0     # 5m 초과 축 = 파싱 사고로 간주
MIN_THICKNESS_MM = 3.0   # 2D 무두께 규격(스티커 등) 기본 두께
MIN_THICKNESS_FLOOR_MM = 0.01  # 필름/봉투 두께 하한 — 실물 0.02~0.3mm 허용, 노이즈(0.001) 거부
MAX_UNIT_CBM = 5.0       # 개당 5 m³ 초과 = 이상치 격리

# ── QC 버킷 상수 (sync_parts 규격 파싱 가능 모집단 n=726 tertile, 2026-06-10 산출) ──
QC_TERTILE_T1_M3 = 2.635e-05    # 소/중 경계
QC_TERTILE_T2_M3 = 2.8653e-04   # 중/대 경계
QC_BUCKET_MEDIAN_M3 = {"소": 1.34e-05, "중": 8.1e-05, "대": 1.4e-03}

# 기존 ItemMaster 출처 → 신뢰도 (cbm_estimator._KIT_SRC_CONF와 동일 값)
_EXISTING_SRC_CONF = {
    "TMS_Product": 1.0, "박스유도": 0.9, "MES_제품DB": 0.8, "수기": 0.7, "미등록": 0.0,
}

CONF_DIMS_PARSE = 0.55   # spec §6 "2축치수 0.55" — 3축/2축/movement 동일 rung
CONF_QC_BUCKET = 0.40    # spec §6 "QC버킷 0.40"


def parse_dims_mm(raw: str) -> tuple[float, float, float] | None:
    """'88x88x163', '248*190*33', '200x300', '135x195x0.04', '55x160mm 펼침...' 파싱.

    Returns (W, H, D) mm, or None. W/H는 [MIN_AXIS_MM, MAX_AXIS_MM],
    두께(3축, positional)는 [MIN_THICKNESS_FLOOR_MM, MAX_AXIS_MM] 밖이면 None.
    필름/봉투 두께(예 0.04mm)는 두께 축에 한해 1mm 미만 허용.
    """
    import re

    cleaned = re.split(r"펼침", raw)[0]
    cleaned = re.sub(r"mm", "", cleaned, flags=re.IGNORECASE)
    nums = [float(n) for n in re.findall(r"[\d.]+", cleaned) if float(n) > 0]
    if len(nums) >= 3:
        dims = (nums[0], nums[1], nums[2])
    elif len(nums) == 2:
        dims = (nums[0], nums[1], MIN_THICKNESS_MM)
    else:
        return None
    w, h, t = dims
    if not (MIN_AXIS_MM <= w <= MAX_AXIS_MM and MIN_AXIS_MM <= h <= MAX_AXIS_MM):
        return None
    if not (MIN_THICKNESS_FLOOR_MM <= t <= MAX_AXIS_MM):
        return None
    return dims


def calc_cbm(spec: str, qty: float) -> tuple[float, bool]:
    """치수 문자열 × 수량 → CBM (m³). Returns (cbm, ok).

    개당 CBM이 MAX_UNIT_CBM 초과면 이상치로 거부.
    """
    dims = parse_dims_mm(spec)
    if dims is None or qty <= 0:
        return 0.0, False
    w, h, d = dims
    unit_cbm = (w / 1000) * (h / 1000) * (d / 1000)
    if unit_cbm > MAX_UNIT_CBM:
        return 0.0, False
    return round(unit_cbm * qty, 6), True


def classify_qc_bucket(unit_cbm: float) -> str:
    """개당 CBM → 소/중/대 (tertile 경계, 경계값 포함=하위 버킷)."""
    if unit_cbm <= QC_TERTILE_T1_M3:
        return "소"
    if unit_cbm <= QC_TERTILE_T2_M3:
        return "중"
    return "대"


def qc_bucket_cbm(bucket: str) -> float | None:
    """버킷 → median 개당 CBM. 미정의 버킷은 None."""
    return QC_BUCKET_MEDIAN_M3.get(bucket)


def part_cbm_for_pt(
    pt: str,
    item_master: dict[str, tuple[float, str]],
    sp_lookup: dict[str, str],
    mov_spec_by_pt: dict[str, str] | None = None,
    qc_bucket_by_pt: dict[str, str] | None = None,
) -> tuple[float, float, str]:
    """PT 개당 CBM 산출. Returns (cbm_m3, confidence, tier).

    tier: '기존'(ItemMaster 불가침) / '치수파싱' / 'QC버킷' / '미산출'
    """
    existing = item_master.get(pt)
    if existing and existing[0] > 0:
        cbm, src = existing
        return cbm, _EXISTING_SRC_CONF.get(src, 0.7), "기존"

    spec = (sp_lookup.get(pt) or "").strip()
    if spec:
        cbm, ok = calc_cbm(spec, 1)
        if ok:
            return cbm, CONF_DIMS_PARSE, "치수파싱"

    mov_spec = ((mov_spec_by_pt or {}).get(pt) or "").strip()
    if mov_spec:
        cbm, ok = calc_cbm(mov_spec, 1)
        if ok:
            return cbm, CONF_DIMS_PARSE, "치수파싱"

    bucket = (qc_bucket_by_pt or {}).get(pt)
    if bucket:
        median = qc_bucket_cbm(bucket)
        if median is not None:
            return median, CONF_QC_BUCKET, "QC버킷"

    return 0.0, 0.0, "미산출"
