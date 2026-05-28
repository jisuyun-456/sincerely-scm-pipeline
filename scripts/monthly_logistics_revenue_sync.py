"""
monthly_logistics_revenue_sync.py
----------------------------------
매월 1일 실행: 전월 TMS Shipment 레코드의 드랍박스링크(견적서 PDF)에서
라보 퀵 운임을 추출해 물류매출 필드에 자동 업데이트.

Usage:
  python scripts/monthly_logistics_revenue_sync.py                  # 전월 처리
  python scripts/monthly_logistics_revenue_sync.py --month 2026-03  # 지정 월
  python scripts/monthly_logistics_revenue_sync.py --month 2026-03 --dry-run
"""
from __future__ import annotations

import argparse
import io
import os
import re
import sys
import time
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import requests

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Field IDs (TMS Base) ────────────────────────────────────────────────────
TMS_BASE_ID = "app4x70a8mOrIKsMf"
SHIPMENT_TABLE_ID = "tbllg1JoHclGYer7m"

FIELD_SC_ID = "fldBUwhBlhOMsJZdv"          # formula – SC number
FIELD_PROJECT_CODE = "fldTs3FzaSdGYEiKX"   # rollup – PNA code
FIELD_LOGIS_REVENUE = "fldOFuvqBT0iXItcT"  # currency – 물류매출 (write target)
FIELD_DROPBOX_LINK = "fldIIMrga2dUNbVdd"   # lookupValues – 드랍박스링크
FIELD_SHIP_DATE = "fldQvmEwwzvQW95h9"      # date – 출하확정일

AIRTABLE_API = "https://api.airtable.com/v0"


# ── Data classes ───────────────────────────────────────────────────────────
@dataclass
class ShipmentRecord:
    record_id: str
    sc_id: str
    project_code: str | None
    dropbox_url: str | None
    current_revenue: float | None


@dataclass
class SyncResult:
    updated: list[str] = field(default_factory=list)
    skipped_no_link: list[str] = field(default_factory=list)
    skipped_has_value: list[str] = field(default_factory=list)
    skipped_no_amount: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"업데이트: {len(self.updated)}건 | "
            f"이미 값 있음: {len(self.skipped_has_value)}건 | "
            f"링크 없음: {len(self.skipped_no_link)}건 | "
            f"금액 추출 실패: {len(self.skipped_no_amount)}건 | "
            f"오류: {len(self.errors)}건"
        )


# ── Airtable helpers ───────────────────────────────────────────────────────
def _at_headers() -> dict:
    token = os.environ.get("AIRTABLE_PAT")
    if not token:
        raise RuntimeError("AIRTABLE_PAT 환경변수가 없습니다.")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _prev_month_range(month_str: str | None) -> tuple[str, str]:
    """Return (start, end) date strings for the target month."""
    if month_str:
        year, mo = map(int, month_str.split("-"))
    else:
        today = date.today()
        mo = today.month - 1 or 12
        year = today.year if today.month > 1 else today.year - 1
    start = f"{year:04d}-{mo:02d}-01"
    # last day of month
    import calendar
    last = calendar.monthrange(year, mo)[1]
    end = f"{year:04d}-{mo:02d}-{last:02d}"
    return start, end


def fetch_shipments(month_str: str | None) -> list[ShipmentRecord]:
    """Fetch Shipment records for the target month."""
    start, end = _prev_month_range(month_str)
    headers = _at_headers()
    records: list[ShipmentRecord] = []
    params: dict = {
        "filterByFormula": (
            f"AND("
            f"IS_AFTER({{출하확정일}}, DATEADD('{start}', -1, 'days')), "
            f"IS_BEFORE({{출하확정일}}, DATEADD('{end}', 1, 'days'))"
            f")"
        ),
        "fields[]": [
            FIELD_SC_ID,
            FIELD_PROJECT_CODE,
            FIELD_LOGIS_REVENUE,
            FIELD_DROPBOX_LINK,
            FIELD_SHIP_DATE,
        ],
        "pageSize": 100,
    }
    offset = None
    while True:
        if offset:
            params["offset"] = offset
        r = requests.get(
            f"{AIRTABLE_API}/{TMS_BASE_ID}/{SHIPMENT_TABLE_ID}",
            headers=headers,
            params=params,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        for rec in data.get("records", []):
            cells = rec.get("fields", {})
            # Extract Dropbox URL from lookupValues structure
            db_raw = cells.get(FIELD_DROPBOX_LINK)
            dropbox_url: str | None = None
            if isinstance(db_raw, list) and db_raw:
                dropbox_url = db_raw[0]
            elif isinstance(db_raw, dict):
                vals = db_raw.get("valuesByLinkedRecordId", {})
                for v in vals.values():
                    if v:
                        dropbox_url = v[0]
                        break

            records.append(ShipmentRecord(
                record_id=rec["id"],
                sc_id=cells.get(FIELD_SC_ID, ""),
                project_code=cells.get(FIELD_PROJECT_CODE),
                dropbox_url=dropbox_url,
                current_revenue=cells.get(FIELD_LOGIS_REVENUE),
            ))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.35)  # Airtable 3 req/s
    return records


# ── Dropbox download ────────────────────────────────────────────────────────
def download_dropbox_zip(url: str, timeout: int = 60) -> bytes:
    """
    Download Dropbox shared folder as ZIP.
    Converts scl/fo/... ?dl=0  →  ?dl=1 for direct download.
    """
    dl_url = re.sub(r"[?&]dl=0", "", url)
    sep = "&" if "?" in dl_url else "?"
    dl_url = dl_url + sep + "dl=1"
    r = requests.get(dl_url, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    ct = r.headers.get("content-type", "")
    if "zip" not in ct and "octet" not in ct:
        # Single file link (not a folder) – return as-is
        return r.content
    return r.content


# ── PDF text extraction ─────────────────────────────────────────────────────
def _extract_pdf_text_stdlib(pdf_bytes: bytes) -> str:
    """
    Lightweight PDF text extractor using stdlib only (zlib + re).
    Works for FlateDecode streams from ReportLab-generated PDFs.
    Falls back gracefully if pdfplumber is available.
    """
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            return "\n".join(p.extract_text() or "" for p in pdf.pages)
    except ImportError:
        pass

    import zlib
    text_parts: list[str] = []
    # Find all FlateDecode streams
    stream_re = re.compile(
        rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL
    )
    for m in stream_re.finditer(pdf_bytes):
        raw = m.group(1)
        try:
            decompressed = zlib.decompress(raw)
        except Exception:
            try:
                decompressed = zlib.decompress(raw, -15)
            except Exception:
                continue
        # Extract text from BT...ET blocks
        bt_re = re.compile(rb"BT(.*?)ET", re.DOTALL)
        for bt_m in bt_re.finditer(decompressed):
            block = bt_m.group(1)
            # Extract string literals: (text) Tj  or [(text)] TJ
            for lit in re.findall(rb"\(((?:[^()\\]|\\.)*)\)\s*(?:Tj|TJ)", block):
                try:
                    text_parts.append(lit.decode("latin-1"))
                except Exception:
                    pass
    return " ".join(text_parts)


def extract_text_from_zip(zip_bytes: bytes, filename_hint: str = "견적서") -> str | None:
    """
    Open ZIP, find the 견적서 PDF, extract text.
    Returns None if no suitable PDF found.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        # Single PDF bytes (not a ZIP)
        return _extract_pdf_text_stdlib(zip_bytes)

    candidates: list[str] = []
    for name in zf.namelist():
        lower = name.lower()
        if lower.endswith(".pdf"):
            # Prefer files with 견적서 in name
            if filename_hint in name or "estimate" in lower or "quote" in lower:
                candidates.insert(0, name)
            else:
                candidates.append(name)

    if not candidates:
        return None

    pdf_bytes = zf.read(candidates[0])
    return _extract_pdf_text_stdlib(pdf_bytes)


# ── 라보 퀵 amount parser ───────────────────────────────────────────────────
def parse_labo_quick_amount(text: str) -> int | None:
    """
    Extract 라보 퀵 top-level amount from 견적서 서비스 견적 section.

    PDF layout (example):
      3 서비스 견적
      라보 퀵              1개  105,000 원  105,000 원   ← target (top-level)
        라보 퀵  거리 : 10km  1개   63,000 원   63,000 원  ← sub-row (skip)
        하차 지원 여부 : 지원   1개   42,000 원   42,000 원  ← sub-row (skip)
      키트 포장           100개    1,900 원  190,000 원
      서비스 견적 합계                        295,000 원

    Strategy: find the line containing "라보 퀵" that comes BEFORE
    any sub-items (identified by 거리, 하차, km).  Take the LAST
    currency pattern on that line as the 소계 (subtotal).
    """
    if not text:
        return None

    lines = text.split("\n")
    # Find 서비스 견적 section start
    section_start = -1
    for i, line in enumerate(lines):
        if "서비스 견적" in line and "합계" not in line:
            section_start = i
            break

    if section_start == -1:
        # Try without section header (some PDFs skip section titles)
        search_lines = lines
    else:
        # Limit search to reasonable range after section header
        search_lines = lines[section_start: section_start + 50]

    # Currency pattern: digits with optional commas, followed by 원
    currency_re = re.compile(r"([\d,]+)\s*원")

    SUB_ITEM_KEYWORDS = ("거리", "하차", "km", "Km", "KM", "도착지", "운전")

    for i, line in enumerate(search_lines):
        if "라보 퀵" not in line:
            continue

        # If the line contains sub-item keywords (no-newline PDF where rows are
        # concatenated), extract only the top-level 라보 퀵 segment.
        if any(k in line for k in SUB_ITEM_KEYWORDS):
            first = line.find("라보 퀵")
            # Find earliest sub-item keyword position after "라보 퀵"
            sub_start = len(line)
            for k in SUB_ITEM_KEYWORDS:
                pos = line.find(k, first + 1)
                if pos != -1 and pos < sub_start:
                    sub_start = pos
            segment = line[first:sub_start]
            # If isolated segment still has a sub-item keyword, truly skip
            if any(k in segment for k in SUB_ITEM_KEYWORDS):
                continue
            line = segment

        amounts = currency_re.findall(line)
        if not amounts:
            # Amount might span to next line in PDF text extraction
            if i + 1 < len(search_lines):
                combined = line + " " + search_lines[i + 1]
                amounts = currency_re.findall(combined)

        if amounts:
            # Last amount on the line = 소계 (subtotal column)
            raw = amounts[-1].replace(",", "")
            return int(raw)

    return None


# ── Split-delivery amount allocation ───────────────────────────────────────
def allocate_amounts(total: int, count: int) -> list[int]:
    """
    Divide total equally across `count` SC records.
    Remainder (total % count) goes to the first SC.
    Example: 105000 / 3 → [35000, 35000, 35000]
             100000 / 3 → [33334, 33333, 33333]
    """
    per = total // count
    remainder = total % count
    result = [per] * count
    result[0] += remainder
    return result


# ── Main sync ──────────────────────────────────────────────────────────────
def run_sync(
    month_str: str | None = None,
    dry_run: bool = False,
    verbose: bool = False,
) -> SyncResult:
    result = SyncResult()
    print(f"[sync] {'[DRY-RUN] ' if dry_run else ''}월 기준: {month_str or '전월'}")

    records = fetch_shipments(month_str)
    print(f"[sync] {len(records)}건 조회 완료")

    # Skip records that already have 물류매출 set
    to_process = []
    for rec in records:
        if rec.current_revenue is not None:
            result.skipped_has_value.append(rec.sc_id)
            continue
        if not rec.dropbox_url or not rec.project_code:
            result.skipped_no_link.append(rec.sc_id)
            continue
        if rec.project_code.startswith("FMS"):
            result.skipped_no_link.append(rec.sc_id)
            continue
        to_process.append(rec)

    # Group by unique Dropbox URL (same URL = same project = same 견적서)
    url_groups: dict[str, list[ShipmentRecord]] = defaultdict(list)
    for rec in to_process:
        url_groups[rec.dropbox_url].append(rec)

    print(f"[sync] 처리 대상: {len(to_process)}건 ({len(url_groups)}개 견적서)")

    headers = _at_headers()

    for url, group_recs in url_groups.items():
        sc_ids = [r.sc_id for r in group_recs]
        if verbose:
            print(f"  → {group_recs[0].project_code} ({len(group_recs)}개 SC): {sc_ids}")

        try:
            zip_bytes = download_dropbox_zip(url)
            text = extract_text_from_zip(zip_bytes)
            if not text:
                for rec in group_recs:
                    result.skipped_no_amount.append(rec.sc_id)
                continue

            amount = parse_labo_quick_amount(text)
            if amount is None:
                if verbose:
                    print(f"    ⚠ 라보 퀵 금액 없음 (라보 퀵 없는 견적서?): {sc_ids}")
                for rec in group_recs:
                    result.skipped_no_amount.append(rec.sc_id)
                continue

            # Allocate across group
            allocations = allocate_amounts(amount, len(group_recs))
            for rec, alloc in zip(group_recs, allocations):
                if verbose:
                    print(f"    ✓ {rec.sc_id}: ₩{alloc:,}")
                if not dry_run:
                    _patch_revenue(rec.record_id, alloc, headers)
                result.updated.append(rec.sc_id)

        except requests.HTTPError as e:
            for rec in group_recs:
                result.errors.append((rec.sc_id, str(e)))
        except Exception as e:
            for rec in group_recs:
                result.errors.append((rec.sc_id, str(e)))

    return result


def _patch_revenue(record_id: str, amount: int, headers: dict) -> None:
    import json
    r = requests.patch(
        f"{AIRTABLE_API}/{TMS_BASE_ID}/{SHIPMENT_TABLE_ID}/{record_id}",
        headers=headers,
        data=json.dumps({"fields": {FIELD_LOGIS_REVENUE: amount}}),
        timeout=15,
    )
    r.raise_for_status()
    time.sleep(0.35)


# ── PDF parsing unit tests ─────────────────────────────────────────────────
def _run_parser_tests() -> None:
    """
    Validate parse_labo_quick_amount with real-world PDF text patterns.
    Run with: python monthly_logistics_revenue_sync.py --test
    """
    cases = [
        # (description, text, expected_amount)
        (
            "기본 케이스 (스크린샷과 동일)",
            """
3 서비스 견적
항목  옵션  수량  단가  소계
라보 퀵              1개  105,000 원  105,000 원
  라보 퀵  거리 : 10km  1개  63,000 원  63,000 원
  하차 지원 여부 : 지원  1개  42,000 원  42,000 원
키트 포장           100개   1,900 원  190,000 원
서비스 견적 합계                        295,000 원
""",
            105000,
        ),
        (
            "라보 퀵 없음 (택배만)",
            """
3 서비스 견적
키트 포장           100개   1,900 원  190,000 원
서비스 견적 합계                        190,000 원
""",
            None,
        ),
        (
            "금액에 천만원대 쉼표",
            """
서비스 견적
라보 퀵  1개  1,050,000 원  1,050,000 원
  라보 퀵  거리 : 50km  1개  1,050,000 원  1,050,000 원
""",
            1050000,
        ),
        (
            "섹션 헤더 없이 바로 라보 퀵 라인",
            "라보 퀵  2개  52,000 원  104,000 원\n  거리 : 5km  2개  52,000 원  104,000 원",
            104000,
        ),
        (
            "줄바꿈 없이 붙어있는 텍스트",
            "3 서비스 견적 라보 퀵 1개 78,000 원 78,000 원 라보 퀵 거리:8km 1개 78,000 원 78,000 원",
            78000,
        ),
    ]

    passed = 0
    failed = 0
    for desc, text, expected in cases:
        got = parse_labo_quick_amount(text)
        ok = got == expected
        status = "✅" if ok else "❌"
        print(f"  {status} {desc}")
        if not ok:
            print(f"     expected={expected}, got={got}")
            failed += 1
        else:
            passed += 1

    print(f"\n파서 테스트: {passed}/{passed+failed} 통과")
    if failed:
        sys.exit(1)


# ── CLI ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description="Monthly logistics revenue sync")
    parser.add_argument("--month", help="YYYY-MM (default: 전월)")
    parser.add_argument("--dry-run", action="store_true", help="Airtable 업데이트 없이 시뮬레이션")
    parser.add_argument("--verbose", action="store_true", help="상세 로그")
    parser.add_argument("--test", action="store_true", help="PDF 파서 단위 테스트 실행")
    args = parser.parse_args()

    if args.test:
        print("=== PDF 파서 단위 테스트 ===")
        _run_parser_tests()
        sys.exit(0)

    result = run_sync(
        month_str=args.month,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )
    print(f"\n[결과] {result.summary()}")

    if result.errors:
        print("\n[오류 목록]")
        for sc, err in result.errors:
            print(f"  {sc}: {err}")
