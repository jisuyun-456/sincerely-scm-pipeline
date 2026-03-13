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
# field_mapping 모듈이 정상적으로 존재하는지 확인 필요
try:
    from config.field_mapping import ALL_TABLES, MATERIAL_TABLE, MOVEMENT_TABLE, ORDER_TABLE, PROJECT_TABLE
except ImportError:
    # 모듈이 없을 경우를 대비한 최소한의 방어 로직 (사용자 환경에 맞게 유지)
    ALL_TABLES = []

# ── 설정 ──
# GitHub Secrets의 AIRTABLE_PAT를 우선적으로 가져옵니다.
AIRTABLE_TOKEN = os.getenv("AIRTABLE_PAT") or os.getenv("AIRTABLE_TOKEN") or ""
AIRTABLE_BASE_ID = "appLui4ZR5HWcQRri"
AIRTABLE_API_URL = "https://api.airtable.com/v0"

# DB URL에서 발생할 수 있는 양 끝 공백이나 따옴표를 제거합니다.
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

            # 필드 파라미터 구성
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

            # 여기서 401 에러가 나면 토큰 문제임이 확실함
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
        if not rows: return

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
    
    # 함수 내부에서 전역 변수를 다시 한번 확인하여 최신화
    current_token = AIRTABLE_TOKEN or os.getenv("AIRTABLE_PAT")
    
    # Airtable 추출기
    extractor = AirtableExtractor(current_token, AIRTABLE_BASE_ID)

    loader = None
    snapshot_id = None
    if not dry_run:
        loader = SupabaseLoader(SUPABASE_DB_URL)
        snapshot_id = loader.create_snapshot(snapshot_date, list(table_configs.keys()))
        log.info(f"Snapshot ID: {snapshot_id}")

    record_counts = {}
    try:
        for table_key, table_config in table_configs.items():
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

        duration = time.time() - start_time
        if not dry_run:
            loader.update_snapshot_status(snapshot_id, "completed", record_counts, duration)
        log.info(f"\n=== 파이프라인 종료 (소요시간: {duration:.1f}초) ===")

    except Exception as e:
        duration = time.time() - start_time
        log.error(f"파이프라인 실패: {e}", exc_info=True)
        if not dry_run and loader and snapshot_id:
            loader.update_snapshot_status(snapshot_id, "failed", record_counts, duration, str(e))
        raise
    finally:
        if loader: loader.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=str, default=None)
    parser.add_argument("--table", type=str, nargs="+", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    snap_date = date.fromisoformat(args.date) if args.date else date.today()

    # 실행 전 최종 환경 변수 점검
    if not (AIRTABLE_TOKEN or os.getenv("AIRTABLE_PAT")):
        log.error("에러: AIRTABLE_PAT 환경 변수가 설정되지 않았습니다.")
        sys.exit(1)
        
    run_pipeline(snap_date, args.table, args.dry_run)
