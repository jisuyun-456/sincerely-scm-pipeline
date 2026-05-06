"""
WMS_NCR Backfill
-----------------
movement 테이블에서 '품질 이슈 리포팅' checkbox=TRUE인 건을 읽어
WMS_NCR 테이블에 NCR 레코드를 생성한다.

멱등성: 이미 존재하는 NCR_ID(NCR-YYYYMMDD-NNN)는 스킵한다.

Usage:
  python wms/backfill_ncr.py

Env: AIRTABLE_PAT (required)
"""

import sys, os, re, time
from datetime import datetime
import requests

sys.stdout.reconfigure(encoding="utf-8")

# ── Config ────────────────────────────────────────────────────────────────────
PAT     = os.environ["AIRTABLE_PAT"]
BASE_ID  = "appLui4ZR5HWcQRri"
HEADERS  = {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}
API_BASE = "https://api.airtable.com/v0"

# ── Table IDs ─────────────────────────────────────────────────────────────────
TBL_MV  = "tblwq7Kj5Y9nVjlOw"   # movement (소스)
TBL_MAT = "tblaRpZstW10EwDlo"   # material(parts-stock)
TBL_NCR = "tblMODxFEWpkKWG4Y"   # WMS_NCR (타겟)

# ── movement 필드 IDs ─────────────────────────────────────────────────────────
F_MV_ITEMS   = "fldwZKCYZ4IFOigRp"   # 이동물품 (PT코드 포함 텍스트)
F_MV_DATE    = "fldDXUAF4JOORLJ2v"   # 생성일자 (dateTime)
F_MV_QC_CHK  = "fld9eE4YZZWTDsfUC"   # 품질 이슈 리포팅 (checkbox)
F_MV_QC_SMPL = "fld3lQvblfrqTl4O8"   # 불량수량_샘플링검수 (number)
F_MV_QC_FULL = "fldsTXzxUeerw4qw2"   # 불량수량_전수검수 (number)
F_MV_QC_NOTE = "fld0ZtsqLg4HIM4zg"   # 품질이슈내용 (multilineText)
F_MV_QC_TYPE = "fldhah8PRdngeDvYY"   # 품질이슈내용구분 (singleSelect)

# ── WMS_NCR 필드 IDs ──────────────────────────────────────────────────────────
F_NCR_ID    = "fld93Fagb87nX8koG"   # NCR_ID (singleLineText)
F_NCR_MAT   = "fldCJ7kIxQWo5DYju"   # Material (multipleRecordLinks)
F_NCR_CODE  = "fldywyXZbxkgY5FUR"   # Defect_Code (singleSelect)
F_NCR_QTY   = "fldhBzrL7jx7TEbon"   # Defect_Qty (number)
F_NCR_DATE  = "fldliElDm2UTh2QMm"   # Detection_Date (date)
F_NCR_DISP  = "fld6w8QPuPER9pmvV"   # Disposition (singleSelect)
F_NCR_STAT  = "fldI2sJOYXfVrwyds"   # Status (singleSelect)
F_NCR_CAUSE = "fldlDAIF5BcORPGMb"   # Root_Cause (multilineText)

# ── material 필드 IDs ─────────────────────────────────────────────────────────
F_MAT_CODE  = "fldclYkWLmwrTzuF6"   # 파츠 코드

# ── Defect_Code 매핑 ──────────────────────────────────────────────────────────
DEFECT_MAP = {
    "수량":   "QC-001 수량부족",
    "외관":   "QC-002 외관불량",
    "규격":   "QC-003 규격불일치",
    "사이즈": "QC-003 규격불일치",
    "오염":   "QC-004 오염·이물",
    "이물":   "QC-004 오염·이물",
    "인쇄":   "QC-005 인쇄불량",
    "색상":   "QC-005 인쇄불량",
    "포장":   "QC-006 포장불량",
    "박스":   "QC-006 포장불량",
}
DEFECT_DEFAULT = "QC-007 기타"


# ── Helpers ───────────────────────────────────────────────────────────────────
def _get(table_id, params):
    url = f"{API_BASE}/{BASE_ID}/{table_id}"
    r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def paginate(table_id, fields, filter_formula=None):
    """테이블 전체 레코드를 페이지네이션하여 반환한다."""
    records = []
    params = {"fields[]": fields, "pageSize": 100}
    if filter_formula:
        params["filterByFormula"] = filter_formula

    while True:
        data = _get(table_id, params)
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        params["offset"] = offset
        time.sleep(0.2)
    return records


def batch_post(table_id, rows, batch_size=10):
    """rows(dict 리스트)를 batch_size 단위로 POST한다. 생성 건수 반환."""
    url = f"{API_BASE}/{BASE_ID}/{table_id}"
    created = 0
    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        payload = {"records": [{"fields": r} for r in chunk]}
        resp = requests.post(url, headers=HEADERS, json=payload, timeout=30)
        if not resp.ok:
            print(f"  [ERROR] batch {i // batch_size + 1}: {resp.text[:300]}")
        else:
            created += len(chunk)
        time.sleep(0.25)
    return created


def extract_pt_code(text):
    """이동물품 텍스트에서 PT\\d+ 패턴을 추출한다."""
    if not text:
        return None
    m = re.search(r"PT\d+", str(text))
    return m.group(0) if m else None


def map_defect_code(issue_type_str, issue_note_str):
    """품질이슈내용구분 + 품질이슈내용으로 Defect_Code를 결정한다."""
    combined = str(issue_type_str or "") + str(issue_note_str or "")
    for keyword, code in DEFECT_MAP.items():
        if keyword in combined:
            return code
    return DEFECT_DEFAULT


# ── Step 1: material PT코드 → record_id 맵 빌드 ──────────────────────────────
def build_material_map():
    """PT코드 → record_id 맵을 반환한다.

    Airtable API는 fields[] 파라미터에 field ID를 넣어도
    응답 dict key는 필드명(한글)으로 반환하므로,
    필드 ID 대신 응답의 첫 번째 값을 사용하거나 values()로 순회한다.
    """
    print("Loading material table...")
    recs = paginate(TBL_MAT, fields=[F_MAT_CODE])
    pt_map = {}
    for r in recs:
        flds = r["fields"]
        # 필드 ID 직접 접근 시도, 없으면 values() 에서 첫 번째 문자열 취득
        code = flds.get(F_MAT_CODE) or next(
            (v for v in flds.values() if isinstance(v, str)), ""
        )
        if code and re.match(r"^PT\d+", str(code)):
            pt_map[str(code)] = r["id"]
    print(f"  {len(pt_map)} PT codes loaded")
    return pt_map


# ── Step 2: WMS_NCR 기존 NCR_ID 수집 (멱등성) ────────────────────────────────
def load_existing_ncr_ids():
    """기존 WMS_NCR 레코드의 NCR_ID 집합을 반환한다.

    Airtable API 응답 key는 field ID가 아닌 필드명이므로
    F_NCR_ID로 직접 접근 실패 시 values()에서 NCR- 패턴 값을 찾는다.
    """
    print("Loading existing WMS_NCR records...")
    recs = paginate(TBL_NCR, fields=[F_NCR_ID])
    existing = set()
    for r in recs:
        flds = r["fields"]
        ncr_id = flds.get(F_NCR_ID) or next(
            (v for v in flds.values() if isinstance(v, str) and v.startswith("NCR-")),
            "",
        )
        if ncr_id:
            existing.add(ncr_id)
    print(f"  {len(existing)} existing NCR_IDs found")
    return existing


# ── Step 3: movement에서 QC 이슈 건 조회 ─────────────────────────────────────
def load_qc_movements():
    """품질 이슈 리포팅=TRUE인 movement 레코드를 반환한다.

    Airtable checkbox filter는 버전에 따라 동작이 달라
    3가지 공식을 순차적으로 시도한다.
    """
    fields = [
        F_MV_ITEMS,    # 이동물품
        F_MV_DATE,     # 생성일자
        F_MV_QC_CHK,   # 품질 이슈 리포팅
        F_MV_QC_SMPL,  # 불량수량_샘플링검수
        F_MV_QC_FULL,  # 불량수량_전수검수
        F_MV_QC_NOTE,  # 품질이슈내용
        F_MV_QC_TYPE,  # 품질이슈내용구분
    ]

    formulas = [
        "{품질 이슈 리포팅}",           # checkbox TRUE (표준)
        "{품질 이슈 리포팅}=1",          # 일부 버전
        "{품질 이슈 리포팅}=TRUE()",     # 함수 형태
    ]

    for formula in formulas:
        print(f"  Trying filter: {formula}")
        recs = paginate(TBL_MV, fields=fields, filter_formula=formula)
        if recs:
            print(f"  {len(recs)} QC-issue movement records found")
            return recs
        print(f"  0건 → 다음 공식 시도")

    print("  [WARN] 모든 필터 공식에서 0건. 필드명/ID를 확인하세요.")
    return []


# ── Step 4: NCR_ID 생성 헬퍼 (날짜별 시퀀스) ─────────────────────────────────
def build_ncr_ids(movements, existing_ids):
    """각 movement에 NCR_ID를 할당한다.

    - 날짜별 시퀀스(NNN)는 기존 existing_ids를 포함하여 계산한다.
    - 이미 존재하는 NCR_ID와 충돌하면 해당 movement는 스킵한다.
    """
    # 기존 날짜별 최대 시퀀스 파악
    date_seq: dict[str, int] = {}
    for ncr_id in existing_ids:
        m = re.match(r"NCR-(\d{8})-(\d+)", ncr_id)
        if m:
            date_key = m.group(1)
            seq = int(m.group(2))
            date_seq[date_key] = max(date_seq.get(date_key, 0), seq)

    assignments = []  # (movement, ncr_id)
    skipped_ids = []  # 이미 존재하는 NCR_ID (skip)

    for r in movements:
        f = r["fields"]
        raw_date = str(f.get(F_MV_DATE, ""))[:10]  # YYYY-MM-DD
        date_key = raw_date.replace("-", "")        # YYYYMMDD

        # 날짜 유효성 체크
        if not re.match(r"^\d{8}$", date_key):
            date_key = datetime.now().strftime("%Y%m%d")

        # 시퀀스 할당
        date_seq[date_key] = date_seq.get(date_key, 0) + 1
        ncr_id = f"NCR-{date_key}-{date_seq[date_key]:03d}"

        if ncr_id in existing_ids:
            skipped_ids.append(ncr_id)
        else:
            assignments.append((r, ncr_id))

    return assignments, skipped_ids


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not PAT:
        raise SystemExit("ERROR: AIRTABLE_PAT env var not set")

    print("=" * 60)
    print("WMS_NCR Backfill")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # 1) material PT코드 맵
    pt_map = build_material_map()

    # 2) 기존 NCR_ID 수집
    existing_ids = load_existing_ncr_ids()

    # 3) QC 이슈 movement 조회
    print("\nLoading QC-issue movements...")
    qc_movements = load_qc_movements()
    total_qc = len(qc_movements)

    if total_qc == 0:
        print("\nQC 이슈 movement 0건 — 스크립트 종료")
        print("\nSTATUS: DONE")
        print(f"QC 이슈 movement 건수: 0건")
        print(f"NCR 생성: 0건")
        print(f"스킵: 0건")
        print(f"PT코드 매칭: 0건")
        return

    # 4) NCR_ID 할당 (멱등성)
    assignments, skipped_ids = build_ncr_ids(qc_movements, existing_ids)
    skip_count = len(skipped_ids)
    if skipped_ids:
        print(f"\n스킵 (기존 NCR_ID): {skip_count}건 — {skipped_ids[:5]}{'...' if skip_count > 5 else ''}")

    # 5) NCR 레코드 빌드
    to_create = []
    pt_matched = 0

    for r, ncr_id in assignments:
        f = r["fields"]

        # 이동물품에서 PT코드 추출 → material 연결
        items_text = f.get(F_MV_ITEMS, "")
        pt_code = extract_pt_code(items_text)
        mat_rec_id = pt_map.get(pt_code) if pt_code else None
        if mat_rec_id:
            pt_matched += 1

        # 불량수량: 전수검수 우선, 없으면 샘플링검수, 둘 다 없으면 0
        defect_qty = f.get(F_MV_QC_FULL) or f.get(F_MV_QC_SMPL) or 0

        # Detection_Date: 생성일자 앞 10자리
        detect_date = str(f.get(F_MV_DATE, ""))[:10]

        # Defect_Code 매핑
        issue_type_obj = f.get(F_MV_QC_TYPE, {})
        issue_type = (
            issue_type_obj.get("name")
            if isinstance(issue_type_obj, dict)
            else str(issue_type_obj or "")
        )
        issue_note = f.get(F_MV_QC_NOTE, "")
        defect_code = map_defect_code(issue_type, issue_note)

        row = {
            F_NCR_ID:   ncr_id,
            F_NCR_CODE: defect_code,
            F_NCR_QTY:  defect_qty,
            F_NCR_DATE: detect_date,
            F_NCR_DISP: "ACCEPT_AS_IS",
            F_NCR_STAT: "CLOSED",
            F_NCR_CAUSE: str(issue_note)[:500],
        }
        if mat_rec_id:
            row[F_NCR_MAT] = [mat_rec_id]

        to_create.append(row)

    # 6) 배치 POST
    print(f"\n신규 NCR 레코드 {len(to_create)}건 생성 중...")
    created = batch_post(TBL_NCR, to_create)

    # 7) 결과 요약
    print("\n" + "=" * 60)
    print("STATUS: DONE")
    print(f"QC 이슈 movement 건수: {total_qc}건")
    print(f"NCR 생성: {created}건")
    print(f"스킵: {skip_count}건")
    print(f"PT코드 매칭: {pt_matched}건")
    if created < len(to_create):
        print(f"특이사항: {len(to_create) - created}건 생성 실패 (위 ERROR 로그 확인)")


if __name__ == "__main__":
    main()
