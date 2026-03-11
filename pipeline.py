"""
sincerely-scm Airtable → Supabase 재고 동기화 파이프라인
---------------------------------------------------------
대상 테이블:
  - sync_parts  (tblzJh0V4hdo4Xbvx) → parts_snapshot
  - movement    (tblwq7Kj5Y9nVjlOw) → movement_log
실행 방식:
  - GitHub Actions (매일 09:00 KST) 또는 로컬 수동 실행
  - python pipeline.py
환경 변수 (.env 또는 GitHub Secrets):
  AIRTABLE_TOKEN   - Airtable Personal Access Token
  AIRTABLE_BASE_ID - appLui4ZR5HWcQRri
  SUPABASE_URL     - https://aigykrijhgjxqludjqed.supabase.co
  SUPABASE_KEY     - Supabase service_role key (anon key도 가능하나 service_role 권장)
"""

import os
import sys
import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

# ── 로깅 설정 ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── 환경 변수 ─────────────────────────────────────────────────────────────────
AIRTABLE_TOKEN   = os.environ["AIRTABLE_TOKEN"]
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "appLui4ZR5HWcQRri")
SUPABASE_URL     = os.environ["SUPABASE_URL"]
SUPABASE_KEY     = os.environ["SUPABASE_KEY"]

# ── Airtable 테이블/필드 ID ───────────────────────────────────────────────────
SYNC_PARTS_TABLE  = "tblzJh0V4hdo4Xbvx"
MOVEMENT_TABLE    = "tblwq7Kj5Y9nVjlOw"

# sync_parts 필드 매핑 (field_id → python key)
PARTS_FIELDS = {
    "fldl9H11lWgz2l3Yp": "part_name",       # 파츠명
    "fldGznckkukCMo2Rw": "qty_available",    # 판매가능수량
    "fldbpekGL2urp29qn": "qty_physical_raw", # 실재고 수량 (text)
    "fld4PrxICvbPMQ4D1": "qty_reserved",     # 확보예정 수량
    "fldaGX8DpArGed5tW": "part_type",        # 파츠 유형
    "fldfnFIHpm8vWPXdN": "stock_status_raw", # 재고 분류
    "fldXlbEApr3iBNfSg": "location_summary", # 재고위치별 수량
    "fldHcLCy3MacuMcXD": "risk_level",       # 품절 위험도
}

# movement 필드 매핑
MOVEMENT_FIELDS = {
    "fldOhFtJFBYsxxre7": "movement_id",   # movement_id
    "fldwZKCYZ4IFOigRp": "item_desc",     # 이동물품
    "fldFRNxG1pNooEOC7": "movement_type", # 이동목적 (singleSelect)
    "fld8i5WLz1UNmzvvB": "qty_move",      # 이동수량
    "fldV8kVokQqMIsif0": "qty_in",        # 입하수량
    "fld0XSbknPnJfOYOT": "qty_out",       # 출고수량
    "flduN8khmYwdn7uVD": "actual_date",   # 실제입하일
}

# ── Airtable API 헬퍼 ─────────────────────────────────────────────────────────
def airtable_get_all(table_id: str, field_ids: list[str]) -> list[dict]:
    """Airtable 테이블 전체 레코드 조회 (페이지네이션 처리)"""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_id}"
    headers = {"Authorization": f"Bearer {AIRTABLE_TOKEN}"}
    params = {
        "fields[]": field_ids,
        "pageSize": 100,
    }
    records = []
    offset = None

    while True:
        if offset:
            params["offset"] = offset
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break

    log.info(f"Airtable [{table_id}] 조회 완료: {len(records)}건")
    return records


def airtable_get_since(table_id: str, field_ids: list[str], since_date: str) -> list[dict]:
    """movement 테이블: 특정 날짜 이후 신규 레코드만 조회"""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{table_id}"
    headers = {"Authorization": f"Bearer {AIRTABLE_TOKEN}"}
    # 실제입하일(flduN8khmYwdn7uVD) 기준 필터
    params = {
        "fields[]": field_ids,
        "pageSize": 100,
        "filterByFormula": f"IS_AFTER({{실제입하일}}, '{since_date}')",
    }
    records = []
    offset = None

    while True:
        if offset:
            params["offset"] = offset
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break

    log.info(f"Airtable movement [{since_date} 이후] 조회: {len(records)}건")
    return records


# ── Supabase API 헬퍼 ─────────────────────────────────────────────────────────
def supabase_upsert(table: str, rows: list[dict], on_conflict: str) -> dict:
    """Supabase REST API upsert (중복 시 업데이트)"""
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": f"resolution=merge-duplicates,return=minimal",
    }
    params = {"on_conflict": on_conflict}
    resp = requests.post(url, headers=headers, params=params, json=rows, timeout=60)
    resp.raise_for_status()
    return {"inserted": len(rows)}


def supabase_insert(table: str, rows: list[dict]) -> dict:
    """Supabase REST API insert"""
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    resp = requests.post(url, headers=headers, json=rows, timeout=60)
    resp.raise_for_status()
    return {"inserted": len(rows)}


def supabase_log_run(source: str, fetched: int, inserted: int, skipped: int,
                     status: str, error: Optional[str] = None):
    """sync_meta 테이블에 실행 이력 기록"""
    try:
        supabase_insert("sync_meta", [{
            "source_table": source,
            "records_fetched": fetched,
            "records_inserted": inserted,
            "records_skipped": skipped,
            "status": status,
            "error_msg": error,
        }])
    except Exception as e:
        log.warning(f"sync_meta 기록 실패: {e}")


# ── 데이터 변환 ───────────────────────────────────────────────────────────────
def parse_qty(raw) -> Optional[int]:
    """숫자 또는 문자열을 int로 변환"""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    try:
        return int(str(raw).strip().replace(",", ""))
    except ValueError:
        return None


def transform_parts_record(rec: dict, today: str) -> dict:
    """Airtable sync_parts 레코드 → parts_snapshot row"""
    f = rec.get("fields", {})

    # part_code: 파츠명에서 PT코드 추출, 없으면 record_id 사용
    part_name_raw = f.get("fldl9H11lWgz2l3Yp", "") or ""
    part_name_raw = part_name_raw.strip()

    # "PT1234-상품명" 형식에서 코드 추출
    part_code = rec["id"]  # 기본값: Airtable record ID
    if "-" in part_name_raw:
        maybe_code = part_name_raw.split("-")[0].strip()
        if maybe_code.startswith("PT") or maybe_code.startswith("pk"):
            part_code = maybe_code

    # singleSelect는 object로 올 수 있음
    part_type_raw = f.get("fldaGX8DpArGed5tW")
    part_type = part_type_raw.get("name") if isinstance(part_type_raw, dict) else part_type_raw

    stock_status_raw = f.get("fldfnFIHpm8vWPXdN")
    stock_status = stock_status_raw.get("name") if isinstance(stock_status_raw, dict) else stock_status_raw

    qty_physical_str = f.get("fldbpekGL2urp29qn", "")
    qty_physical = parse_qty(qty_physical_str)

    return {
        "snapshot_date":    today,
        "airtable_rec_id":  rec["id"],
        "part_code":        part_code,
        "part_name":        part_name_raw,
        "part_type":        part_type,
        "qty_available":    parse_qty(f.get("fldGznckkukCMo2Rw")),
        "qty_physical":     qty_physical,
        "qty_reserved":     parse_qty(f.get("fld4PrxICvbPMQ4D1")),
        "stock_status":     stock_status,
        "location_summary": str(f.get("fldXlbEApr3iBNfSg", ""))[:500] or None,
    }


def transform_movement_record(rec: dict) -> dict:
    """Airtable movement 레코드 → movement_log row"""
    f = rec.get("fields", {})

    movement_type_raw = f.get("fldFRNxG1pNooEOC7")
    movement_type = movement_type_raw.get("name") if isinstance(movement_type_raw, dict) else movement_type_raw

    return {
        "airtable_rec_id": rec["id"],
        "movement_id":     str(f.get("fldOhFtJFBYsxxre7", "") or "").strip() or None,
        "movement_type":   movement_type,
        "item_desc":       str(f.get("fldwZKCYZ4IFOigRp", "") or "").strip()[:500] or None,
        "qty_in":          parse_qty(f.get("fldV8kVokQqMIsif0")),
        "qty_out":         parse_qty(f.get("fld0XSbknPnJfOYOT")),
        "qty_move":        parse_qty(f.get("fld8i5WLz1UNmzvvB")),
        "actual_date":     f.get("flduN8khmYwdn7uVD"),  # "YYYY-MM-DD"
        "location_to":     None,  # movement 테이블에 별도 컬럼 없음
    }


# ── 불일치 감지 ───────────────────────────────────────────────────────────────
def detect_discrepancies(parts_rows: list[dict]) -> list[dict]:
    """음수 재고 또는 큰 불일치 파츠 → discrepancy_log 생성"""
    discrepancies = []
    for row in parts_rows:
        qty_avail = row.get("qty_available")
        qty_phys  = row.get("qty_physical")

        if qty_avail is not None and qty_avail < 0:
            discrepancies.append({
                "part_code":    row["part_code"],
                "part_name":    row["part_name"],
                "qty_system":   qty_avail,
                "qty_physical": qty_phys,
                "source":       "daily_sync_negative",
                "status":       "open",
                "note":         f"판매가능수량 음수 감지: {qty_avail}",
            })
        elif qty_avail is not None and qty_phys is not None:
            diff = abs(qty_avail - qty_phys)
            # 10% 이상 or 100개 이상 차이
            threshold = max(100, qty_phys * 0.1) if qty_phys > 0 else 100
            if diff >= threshold:
                discrepancies.append({
                    "part_code":    row["part_code"],
                    "part_name":    row["part_name"],
                    "qty_system":   qty_avail,
                    "qty_physical": qty_phys,
                    "source":       "daily_sync_mismatch",
                    "status":       "open",
                    "note":         f"전산({qty_avail}) vs 실재고({qty_phys}) 차이: {diff}",
                })
    return discrepancies


# ── 배치 분할 ─────────────────────────────────────────────────────────────────
def chunked(lst: list, size: int):
    """리스트를 size 단위로 나눔"""
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


# ── 메인 파이프라인 ───────────────────────────────────────────────────────────
def run_parts_snapshot():
    """Step 1: sync_parts → parts_snapshot (오늘 날짜 스냅샷)"""
    today = date.today().isoformat()
    log.info(f"=== [1/3] parts_snapshot 시작 ({today}) ===")

    field_ids = list(PARTS_FIELDS.keys())
    try:
        records = airtable_get_all(SYNC_PARTS_TABLE, field_ids)
    except Exception as e:
        supabase_log_run("sync_parts", 0, 0, 0, "error", str(e))
        raise

    rows = [transform_parts_record(r, today) for r in records]

    inserted = 0
    skipped = 0
    for batch in chunked(rows, 500):
        try:
            supabase_upsert("parts_snapshot", batch, "snapshot_date,airtable_rec_id")
            inserted += len(batch)
        except Exception as e:
            log.error(f"parts_snapshot upsert 실패: {e}")
            skipped += len(batch)

    log.info(f"parts_snapshot 완료: {inserted}건 저장, {skipped}건 스킵")
    supabase_log_run("sync_parts", len(records), inserted, skipped, "success")
    return rows


def run_movement_sync():
    """Step 2: movement → movement_log (어제 이후 신규 건)"""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    log.info(f"=== [2/3] movement_log 시작 ({yesterday} 이후) ===")

    field_ids = list(MOVEMENT_FIELDS.keys())
    try:
        records = airtable_get_since(MOVEMENT_TABLE, field_ids, yesterday)
    except Exception as e:
        supabase_log_run("movement", 0, 0, 0, "error", str(e))
        raise

    if not records:
        log.info("movement: 신규 레코드 없음")
        supabase_log_run("movement", 0, 0, 0, "success")
        return

    rows = [transform_movement_record(r) for r in records]

    inserted = 0
    skipped = 0
    for batch in chunked(rows, 500):
        try:
            supabase_upsert("movement_log", batch, "airtable_rec_id")
            inserted += len(batch)
        except Exception as e:
            log.error(f"movement_log upsert 실패: {e}")
            skipped += len(batch)

    log.info(f"movement_log 완료: {inserted}건 저장, {skipped}건 스킵")
    supabase_log_run("movement", len(records), inserted, skipped, "success")


def run_discrepancy_check(parts_rows: list[dict]):
    """Step 3: 불일치 감지 → discrepancy_log"""
    log.info("=== [3/3] discrepancy_log 시작 ===")

    discrepancies = detect_discrepancies(parts_rows)
    if not discrepancies:
        log.info("불일치 없음")
        return

    log.warning(f"불일치 감지: {len(discrepancies)}건")
    for d in discrepancies:
        log.warning(f"  ⚠ {d['part_code']} | {d['note']}")

    try:
        for batch in chunked(discrepancies, 500):
            supabase_insert("discrepancy_log", batch)
        log.info(f"discrepancy_log {len(discrepancies)}건 기록 완료")
    except Exception as e:
        log.error(f"discrepancy_log 저장 실패: {e}")
        supabase_log_run("discrepancy", len(discrepancies), 0, len(discrepancies), "error", str(e))


def main():
    log.info("=" * 60)
    log.info("sincerely-scm 재고 동기화 파이프라인 시작")
    log.info(f"실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)

    try:
        parts_rows = run_parts_snapshot()
        run_movement_sync()
        run_discrepancy_check(parts_rows)
        log.info("✅ 파이프라인 완료")
    except Exception as e:
        log.error(f"❌ 파이프라인 실패: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
