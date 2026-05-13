"""Apply SQL migrations to Supabase via direct Postgres connection.

Usage:
    python -m harness.virtual_sap.sql.run_migrations

Requires VSAP_DB_URL in .env:
    VSAP_DB_URL=postgresql://postgres.aigykrijhgjxqludjqed:<password>@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres

Get the password from:
    Supabase Dashboard → proejc-jisu-test → Settings → Database → Connection string
"""
from __future__ import annotations

import os
import sys
import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
MIGRATION_FILES = [
    "0001_initial_schema.sql",
    "0002_helpers.sql",
]


def run():
    db_url = os.environ.get("VSAP_DB_URL")
    if not db_url:
        logger.error(
            "VSAP_DB_URL not set.\n"
            "Add to .env:\n"
            "  VSAP_DB_URL=postgresql://postgres.aigykrijhgjxqludjqed:<password>"
            "@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres\n\n"
            "Get the password from:\n"
            "  Supabase Dashboard → proejc-jisu-test → Settings → Database\n\n"
            "Alternatively, apply migrations manually in the SQL editor:\n"
            "  https://supabase.com/dashboard/project/aigykrijhgjxqludjqed/sql/new"
        )
        sys.exit(1)

    try:
        import psycopg2
    except ImportError:
        logger.error("psycopg2 not installed. Run: uv pip install --python .venv-vsap psycopg2-binary")
        sys.exit(1)

    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    cur = conn.cursor()

    for filename in MIGRATION_FILES:
        path = MIGRATIONS_DIR / filename
        sql = path.read_text(encoding="utf-8")
        logger.info("Applying %s ...", filename)
        cur.execute(sql)
        logger.info("  ✓ %s applied", filename)

    cur.close()
    conn.close()
    logger.info("All migrations applied successfully.")


if __name__ == "__main__":
    run()
