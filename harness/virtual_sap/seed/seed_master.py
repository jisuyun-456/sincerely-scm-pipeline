"""One-shot master data seeder.

Usage:
    python -m harness.virtual_sap.cli seed [--dry-run]
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .. import supabase_client as db
from ..config import get_config

logger = logging.getLogger(__name__)

FIXTURES_PATH = Path(__file__).parent / "fixtures.json"

# Insertion order matters (FK dependencies)
SEED_ORDER = [
    "plant",
    "storage_location",
    "material",
    "business_partner",
    "gl_account",
]


def seed_all(dry_run: bool = False) -> dict[str, int]:
    """Insert all master data. Returns count per table."""
    with open(FIXTURES_PATH, encoding="utf-8") as f:
        fixtures: dict[str, list[dict]] = json.load(f)

    counts: dict[str, int] = {}
    for table in SEED_ORDER:
        rows = fixtures.get(table, [])
        if not rows:
            continue

        if dry_run:
            logger.info("[DRY-RUN] Would seed %d rows into sap.%s", len(rows), table)
            counts[table] = len(rows)
            continue

        # Upsert: skip if already exists (re-runnable)
        try:
            result = db.insert(table, rows, dry_run=False)
            counts[table] = len(result)
            logger.info("Seeded %d rows into sap.%s", len(result), table)
        except Exception as exc:
            # If duplicate key — master data already seeded, skip
            if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
                logger.info("sap.%s already seeded (skipping): %s", table, exc)
                counts[table] = 0
            else:
                raise

    # Seed initial period_close for current month
    from datetime import date
    period = date.today().strftime("%Y%m")
    try:
        db.insert("period_close", {"period": period, "status": "open"}, dry_run=dry_run)
        logger.info("Opened period %s", period)
    except Exception as exc:
        if "duplicate" in str(exc).lower():
            pass
        else:
            raise

    return counts


def verify_seed() -> bool:
    """Check that all required master data tables have rows."""
    ok = True
    for table in SEED_ORDER:
        rows = db.select(table, limit=1)
        if not rows:
            logger.error("sap.%s is empty — seed may have failed", table)
            ok = False
        else:
            logger.info("sap.%s ✓ (has rows)", table)
    return ok
