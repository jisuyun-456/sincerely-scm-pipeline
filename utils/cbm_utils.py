"""
utils/cbm_utils.py
─────────────────────────────────────────────────────────────────────────────
WMS 입하 CBM 산출 공용 유틸리티.

cbm_inbound_check.py, wms_cbm_ledger.py, wms_weekly_runner.py에서 공용 import.
"""

import os
import re
import time
from datetime import date

import requests
from dotenv import load_dotenv

load_dotenv()

# ── WMS Airtable 상수 ─────────────────────────────────────────────────────────
WMS_BASE_ID = "appLui4ZR5HWcQRri"
TBL_MOV     = "tblwq7Kj5Y9nVjlOw"   # movement
TBL_SP      = "tblzJh0V4hdo4Xbvx"   # sync_parts

# movement 필드 ID
FLD_MOV_ID       = "fldOhFtJFBYsxxre7"
FLD_MOV_ITEM     = "fldwZKCYZ4IFOigRp"   # 이동물품
FLD_MOV_PURPOSE  = "fldFRNxG1pNooEOC7"   # 이동목적
FLD_MOV_EXP_DATE = "fldlpGxylH72YPs7V"   # 입하예상일
FLD_MOV_ACT_DATE = "flduN8khmYwdn7uVD"   # 실제입하일
FLD_MOV_IN_QTY   = "fldV8kVokQqMIsif0"   # 입하수량
FLD_MOV_SPEC     = "fldiYU7b6Ogf0zm2D"   # 제품 규격
FLD_MOV_SUPPLIER = "fldqGAjPo0SHxx2qW"   # (파트너)발주협력사명

# sync_parts 필드 ID
FLD_SP_CODE = "fld8gjySjm4XkCpMc"
FLD_SP_SPEC = "fldRseOMNseg15D6R"

# CBM 산출 상수
MIN_THICKNESS_MM = 3.0   # 2D 규격(스티커 등) 기본 두께

AIRTABLE_PAT = os.environ.get("AIRTABLE_WMS_PAT", os.environ.get("AIRTABLE_PAT", ""))


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {AIRTABLE_PAT}",
        "Content-Type": "application/json",
    }


# ── Airtable 조회 ─────────────────────────────────────────────────────────────
def get_all_records(
    base_id: str,
    table_id: str,
    fields: list[str],
    formula: str | None = None,
    max_records: int | None = None,
) -> list[dict]:
    records, offset = [], None
    while True:
        params: dict = {
            "fields[]": fields,
            "pageSize": 100,
            "returnFieldsByFieldId": "true",
        }
        if offset:
            params["offset"] = offset
        if formula:
            params["filterByFormula"] = formula
        if max_records:
            params["maxRecords"] = max_records
        resp = requests.get(
            f"https://api.airtable.com/v0/{base_id}/{table_id}",
            headers=_headers(),
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset or (max_records and len(records) >= max_records):
            break
        time.sleep(0.2)
    return records


# ── sync_parts 룩업 ───────────────────────────────────────────────────────────
def load_sync_parts_lookup() -> dict[str, str]:
    """PT코드 → 규격 문자열 매핑."""
    records = get_all_records(WMS_BASE_ID, TBL_SP, [FLD_SP_CODE, FLD_SP_SPEC])
    lookup: dict[str, str] = {}
    for rec in records:
        f = rec.get("fields", {})
        code = str(f.get(FLD_SP_CODE) or "").strip()
        spec = str(f.get(FLD_SP_SPEC) or "").strip()
        if code:
            lookup[code] = spec
    return lookup


# ── 치수 파싱 + CBM 계산 ──────────────────────────────────────────────────────
def parse_dims_mm(raw: str) -> tuple[float, float, float] | None:
    """
    '88x88x163', '248*190*33', '200x300', '55x160mm 펼침...' 파싱.
    Returns (W, H, D) mm, or None.
    """
    cleaned = re.split(r"펼침", raw)[0]
    cleaned = re.sub(r"mm", "", cleaned, flags=re.IGNORECASE)
    nums = [float(n) for n in re.findall(r"[\d.]+", cleaned) if float(n) > 0]
    if len(nums) >= 3:
        return (nums[0], nums[1], nums[2])
    if len(nums) == 2:
        return (nums[0], nums[1], MIN_THICKNESS_MM)
    return None


def calc_cbm(spec: str, qty: float) -> tuple[float, bool]:
    """치수 문자열 × 수량 → CBM (m³). Returns (cbm, ok)."""
    dims = parse_dims_mm(spec)
    if dims is None or qty <= 0:
        return 0.0, False
    w, h, d = dims
    unit_cbm = (w / 1000) * (h / 1000) * (d / 1000)
    return round(unit_cbm * qty, 6), True


# ── 이동물품 파싱 ─────────────────────────────────────────────────────────────
def parse_inbound_item(raw: str | None) -> dict:
    """
    '이동물품' 필드 파싱.
    형식: "PT3137-사각스티커_화이트 || PNA35889_어텐션스포츠보틀 || 에이원지식산업센터"
    """
    if not raw:
        return {"parts_code": "", "parts_name": "", "project_code": "", "project_name": "", "center": ""}

    parts = [p.strip() for p in raw.split(" || ")]
    parts_full = parts[0] if parts else ""
    dash_idx = parts_full.find("-")
    if dash_idx != -1:
        parts_code = parts_full[:dash_idx]
        parts_name = parts_full[dash_idx + 1:]
    else:
        parts_code, parts_name = parts_full, ""

    project_full = parts[1] if len(parts) > 1 else ""
    under_idx = project_full.find("_")
    if under_idx != -1:
        project_code = project_full[:under_idx]
        project_name = project_full[under_idx + 1:]
    else:
        project_code, project_name = project_full, ""

    return {
        "parts_code":   parts_code,
        "parts_name":   parts_name,
        "project_code": project_code,
        "project_name": project_name,
        "center":       parts[2] if len(parts) > 2 else "",
    }


def parse_date(val: str | None) -> date | None:
    if not val:
        return None
    try:
        return date.fromisoformat(val[:10])
    except ValueError:
        return None


# ── 핵심 계산: 기간 입하 CBM 집계 ────────────────────────────────────────────
def fetch_inbound_cbm(
    sp_lookup: dict[str, str],
    since: date | None = None,
    until: date | None = None,
    week_str: str | None = None,
) -> dict:
    """
    movement(이동목적=생산산출) 조회 → CBM 집계.
    since/until: 입하예상일 범위 (inclusive).
    week_str: '2026-W21' 형식이면 since/until 자동 계산.

    Returns:
      total_cbm: float
      by_date: {date_str: {"cbm": float, "cnt": int, "supplier": str}}
      by_supplier: {supplier_name: {"cbm": float, "cnt": int}}
      n_matched: int
      n_unmatched: int
      records: list[dict]  (row-level 데이터)
    """
    from datetime import datetime, timedelta

    if week_str:
        year, wnum = week_str.split("-W")
        monday = datetime.strptime(f"{year}-W{int(wnum):02d}-1", "%G-W%V-%u").date()
        since = monday
        until = monday + timedelta(days=6)

    formula = '{이동목적}="생산산출"'
    if since and until:
        formula = (
            f"AND({formula}, "
            f"IS_AFTER({{입하예상일}}, DATEADD('{since.isoformat()}', -1, 'days')), "
            f"IS_BEFORE({{입하예상일}}, DATEADD('{until.isoformat()}', 1, 'days')))"
        )

    recs = get_all_records(
        WMS_BASE_ID, TBL_MOV,
        fields=[FLD_MOV_ID, FLD_MOV_ITEM, FLD_MOV_PURPOSE,
                FLD_MOV_EXP_DATE, FLD_MOV_IN_QTY, FLD_MOV_SPEC, FLD_MOV_SUPPLIER],
        formula=formula,
    )

    from collections import defaultdict
    by_date: dict[str, dict] = defaultdict(lambda: {"cbm": 0.0, "cnt": 0})
    by_supplier: dict[str, dict] = defaultdict(lambda: {"cbm": 0.0, "cnt": 0})
    rows, n_matched, n_unmatched = [], 0, 0

    for rec in recs:
        f = rec.get("fields", {})
        in_qty    = float(f.get(FLD_MOV_IN_QTY) or 0)
        mov_spec  = str(f.get(FLD_MOV_SPEC) or "").strip()
        exp_date  = parse_date(f.get(FLD_MOV_EXP_DATE))
        supplier  = str(f.get(FLD_MOV_SUPPLIER) or "미기재").strip() or "미기재"
        parsed    = parse_inbound_item(f.get(FLD_MOV_ITEM))
        parts_code = parsed["parts_code"]

        # CBM 계산 (mov_spec 우선, sp_lookup fallback)
        cbm, ok, src = 0.0, False, "none"
        if mov_spec:
            cbm, ok = calc_cbm(mov_spec, in_qty)
            if ok:
                src = "mov"
        if not ok and parts_code:
            sp_spec = sp_lookup.get(parts_code, "")
            if sp_spec:
                cbm, ok = calc_cbm(sp_spec, in_qty)
                if ok:
                    src = "sp"

        if ok:
            n_matched += 1
        else:
            n_unmatched += 1

        d_key = exp_date.isoformat() if exp_date else "날짜없음"
        by_date[d_key]["cbm"] += cbm
        by_date[d_key]["cnt"] += 1
        by_supplier[supplier]["cbm"] += cbm
        by_supplier[supplier]["cnt"] += 1

        rows.append({
            "parts_code": parts_code,
            "parts_name": parsed["parts_name"],
            "supplier":   supplier,
            "exp_date":   d_key,
            "in_qty":     in_qty,
            "spec_src":   src,
            "cbm":        cbm,
        })

    total_cbm = sum(r["cbm"] for r in rows)

    return {
        "total_cbm":   round(total_cbm, 4),
        "by_date":     dict(by_date),
        "by_supplier": dict(sorted(by_supplier.items(), key=lambda x: -x[1]["cbm"])),
        "n_matched":   n_matched,
        "n_unmatched": n_unmatched,
        "records":     rows,
    }
