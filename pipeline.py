"""
Sincerely SCM — Airtable → Supabase 스냅샷 파이프라인
Usage:
    python pipeline.py                    # 오늘 날짜로 전체 스냅샷
    python pipeline.py --date 2026-01-01  # 특정 날짜 태그
    python pipeline.py --table material   # 특정 테이블만
    python pipeline.py --dry-run          # DB 저장 없이 추출만 테스트
"""

import os, sys, json, time, argparse, logging
from datetime import date, datetime
from typing import Any

# .env 파일 로드 (로컬 개발용)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests
import psycopg2
from psycopg2.extras import execute_values

sys.path.insert(0, os.path.dirname(__file__))
try:
    from config.field_mapping import ALL_TABLES, MATERIAL_TABLE, MOVEMENT_TABLE, ORDER_TABLE, PROJECT_TABLE
except ImportError:
    ALL_TABLES = []

# ── 설정 ──
AIRTABLE_TOKEN = os.getenv("AIRTABLE_PAT") or os.getenv("AIRTABLE_TOKEN") or ""
AIRTABLE_BASE_ID = "appLui4ZR5HWcQRri"
AIRTABLE_API_URL = "https://api.airtable.com/v0"

SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL", "").strip().replace('"', '').replace("'", "")

PAGE_SIZE = 100
RATE_LIMIT_DELAY = 0.22

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("scm-pipeline")


# ── Airtable 추출 ──
class AirtableExtractor:
    def __init__(self, token: str, base_id: str):
        self.token = token
        self.base_id = base_id
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    def fetch_all_records(self, table_id: str, field_ids: list[str]) -> list[dict]:
        url = f"{AIRTABLE_API_URL}/{self.base_id}/{table_id}"
        all_records = []
        offset = None
        page = 0

        while True:
            params = {
                "pageSize": PAGE_SIZE,
                "returnFieldsByFieldId": "true",
            }
            if offset:
                params["offset"] = offset

            field_params = "&".join(f"fields%5B%5D={fid}" for fid in field_ids)
            request_url = f"{url}?{field_params}"

            resp = requests.get(
                request_url,
                headers=self.headers,
                params=params
            )

            if resp.status_code == 429:
                log.warning("Rate limited, waiting 30s...")
                time.sleep(30)
                continue

            # ── 수정 1: 422 상세 로깅 ──
            if resp.status_code == 422:
                log.error(f"422 에러 상세: {resp.text}")

            if resp.status_code == 401:
                log.error("Airtable 인증 실패(401). 토큰 권한이나 값을 확인하세요.")

            resp.raise_for_status()
            data = resp.json()

            records = data.get("records", [])
            all_records.extend(records)
            page += 1

            log.info(f"  Page {page}: +{len(records)} records (total: {len(all_records)})")

            offset = data.get("offset")
            if not offset:
                break

            time.sleep(RATE_LIMIT_DELAY)

        return all_records


# ── 데이터 변환 ──
def transform_record(record: dict, field_mapping: dict) -> dict:
    row = {"airtable_record_id": record["id"]}
    fields = record.get("fields", {})

    for airtable_fid, config in field_mapping.items():
        col_name = config["col"]
        col_type = config["type"]
        raw_value = fields.get(airtable_fid)

        if raw_value is None:
            row[col_name] = None
            continue

        if isinstance(raw_value, dict) and "name" in raw_value:
            row[col_name] = raw_value["name"]
        elif isinstance(raw_value, list) and raw_value and isinstance(raw_value[0], dict):
            row[col_name] = [item.get("name", str(item)) for item in raw_value]
        elif isinstance(raw_value, list) and raw_value and isinstance(raw_value[0], str):
            if col_type == "text[]":
                row[col_name] = raw_value
            else:
                row[col_name] = ", ".join(raw_value)
        elif col_type == "int":
            try:
                row[col_name] = int(raw_value) if raw_value else 0
            except (ValueError, TypeError):
                row[col_name] = 0
        else:
            row[col_name] = raw_value

    return row


# ── Supabase 로드 ──
class SupabaseLoader:
    def __init__(self, db_url: str):
        try:
            self.conn = psycopg2.connect(db_url)
            self.conn.autocommit = False
        except Exception as e:
            log.error(f"데이터베이스 연결 실패: {e}")
            raise

    def create_snapshot(self, snapshot_date: date, tables: list[str]) -> int:
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO snapshot_log (snapshot_date, tables_synced, status)
            VALUES (%s, %s, 'running')
            RETURNING id
        """, (snapshot_date, tables))
        snapshot_id = cur.fetchone()[0]
        self.conn.commit()
        return snapshot_id

    def bulk_insert(self, table_name: str, rows: list[dict], snapshot_id: int, snapshot_date: date):
        if not rows:
            return

        for row in rows:
            row["snapshot_id"] = snapshot_id
            row["snapshot_date"] = snapshot_date

        columns = list(rows[0].keys())
        col_str = ", ".join(columns)
        insert_sql = f"INSERT INTO {table_name} ({col_str}) VALUES %s"

        cur = self.conn.cursor()
        values = [tuple(row.get(c) for c in columns) for row in rows]

        execute_values(cur, insert_sql, values, page_size=500)
        self.conn.commit()
        log.info(f"  → {table_name}: {len(rows)} rows inserted")

    def update_snapshot_status(self, snapshot_id: int, status: str,
                                record_counts: dict, duration: float,
                                error_msg: str = None):
        cur = self.conn.cursor()
        cur.execute("""
            UPDATE snapshot_log
            SET status = %s, record_counts = %s, duration_sec = %s, error_message = %s
            WHERE id = %s
        """, (status, json.dumps(record_counts), duration, error_msg, snapshot_id))
        self.conn.commit()

    def close(self):
        if hasattr(self, 'conn'):
            self.conn.close()


# ── 메인 파이프라인 ──
def run_pipeline(snapshot_date: date, target_tables: list[str] = None, dry_run: bool = False):
    start_time = time.time()
    table_configs = {
        "material": MATERIAL_TABLE,
        "movement": MOVEMENT_TABLE,
        "order": ORDER_TABLE,
        "project": PROJECT_TABLE,
    }

    if target_tables:
        table_configs = {k: v for k, v in table_configs.items() if k in target_tables}

    log.info(f"=== SCM 스냅샷 파이프라인 시작 ===")

    current_token = AIRTABLE_TOKEN or os.getenv("AIRTABLE_PAT")
    extractor = AirtableExtractor(current_token, AIRTABLE_BASE_ID)

    loader = None
    snapshot_id = None
    if not dry_run:
        loader = SupabaseLoader(SUPABASE_DB_URL)
        snapshot_id = loader.create_snapshot(snapshot_date, list(table_configs.keys()))
        log.info(f"Snapshot ID: {snapshot_id}")

    record_counts = {}
    has_error = False

    # ── 수정 2: 테이블별 예외처리 (하나 실패해도 나머지 계속 진행) ──
    for table_key, table_config in table_configs.items():
        try:
            table_id = table_config["airtable_table_id"]
            supabase_table = table_config["supabase_table"]
            field_mapping = table_config["fields"]
            field_ids = list(field_mapping.keys())

            log.info(f"\n── {table_key} ({table_id}) → {supabase_table} ──")

            records = extractor.fetch_all_records(table_id, field_ids)
            rows = [transform_record(r, field_mapping) for r in records]
            record_counts[table_key] = len(rows)

            if not dry_run:
                loader.bulk_insert(supabase_table, rows, snapshot_id, snapshot_date)

        except Exception as e:
            log.error(f"  {table_key} 실패, 스킵: {e}")
            record_counts[table_key] = f"ERROR: {str(e)[:100]}"
            has_error = True
            continue

    duration = time.time() - start_time
    final_status = "completed_with_errors" if has_error else "completed"

    if not dry_run:
        loader.update_snapshot_status(snapshot_id, final_status, record_counts, duration)
        loader.close()

    log.info(f"\n=== 파이프라인 종료 (상태: {final_status}, 소요시간: {duration:.1f}초) ===")
    log.info(f"레코드 수: {record_counts}")


# ── 수정 3: __main__ 블록 정리 ──
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=str, default=None)
    parser.add_argument("--table", type=str, nargs="+", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    snap_date = date.fromisoformat(args.date) if args.date else date.today()

    if not (AIRTABLE_TOKEN or os.getenv("AIRTABLE_PAT")):
        log.error("에러: AIRTABLE_PAT 환경 변수가 설정되지 않았습니다.")
        sys.exit(1)

    run_pipeline(snap_date, args.table, args.dry_run)
