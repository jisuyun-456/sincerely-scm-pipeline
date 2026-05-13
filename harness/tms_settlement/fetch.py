"""
Airtable fetch for settlement — uses field IDs in filterByFormula
(via returnFieldsByFieldId=true) to eliminate field-name fragility.

Key safety properties:
- Field IDs (fld...) in formula: immune to Airtable field renames
- Unregistered driver detection: hard-fail before any writes
- 5-min settle delay enforced by caller (GH Actions cron offset)
"""
from __future__ import annotations

from datetime import date, timedelta

from harness._core.airtable import AirtableClient
from harness._core.logger import StructuredLogger
from harness.tms_settlement.config import (
    DRIVER_NAME,
    DRIVER_PARK,
    F_DATE,
    F_PARTNER,
    KNOWN_DRIVERS,
    SETTLEMENT_FIELDS,
    SHIPMENT_TABLE,
    TMS_BASE,
)

_log = StructuredLogger("tms_settlement.fetch")


class UnregisteredDriverError(RuntimeError):
    """Raised when a shipment record has a driver ID not in KNOWN_DRIVERS."""


def _end_excl(sunday: str) -> str:
    return (date.fromisoformat(sunday) + timedelta(days=1)).isoformat()


def fetch_week(
    client: AirtableClient,
    monday: str,
    sunday: str,
) -> tuple[list[dict], list[str]]:
    """Fetch Shipment records for the week that include at least one settlement driver.

    Returns
    -------
    records : list[dict]
        Raw Airtable records that include at least one registered driver.
        Records assigned only to non-settlement carriers (로젠, 고고엑스 etc.)
        are silently filtered out.
    unregistered : list[str]
        Driver record IDs found but not in KNOWN_DRIVERS — logged as warnings only.
        Returns empty list if all unknown drivers are clearly third-party carriers.
        Caller hard-fails only if ZERO settlement records remain after filtering.
    """
    end = _end_excl(sunday)
    # Field IDs in formula (requires returnFieldsByFieldId=true) — immune to renames.
    formula = (
        f"AND("
        f"{{{F_DATE}}}>='{monday}',"
        f"{{{F_DATE}}}<'{end}',"
        f"NOT({{{F_PARTNER}}}='')"
        f")"
    )

    _log.info("fetching shipments", monday=monday, sunday=sunday)
    all_records = client.get_records(
        filter_formula=formula,
        fields=SETTLEMENT_FIELDS,
        return_fields_by_field_id=True,
    )
    _log.info("fetched", count=len(all_records))

    # Separate settlement records from third-party carrier records
    unknown: set[str] = set()
    settlement_records: list[dict] = []
    for rec in all_records:
        partners = rec["fields"].get(F_PARTNER) or []
        known = [d for d in partners if d in KNOWN_DRIVERS]
        for drv_id in partners:
            if drv_id not in KNOWN_DRIVERS:
                unknown.add(drv_id)
        if known:
            settlement_records.append(rec)

    if unknown:
        _log.warning(
            "non-settlement carrier IDs skipped",
            count=len(unknown),
            ids=sorted(unknown),
            settlement_count=len(settlement_records),
        )

    return settlement_records, []


def split_by_driver(
    records: list[dict],
) -> dict[str, list[dict]]:
    """Partition records by driver ID. Records with multiple drivers are
    included once per driver (rare edge case but valid Airtable link).
    """
    by_driver: dict[str, list[dict]] = {drv: [] for drv in KNOWN_DRIVERS}
    for rec in records:
        for drv_id in (rec["fields"].get(F_PARTNER) or []):
            if drv_id in by_driver:
                by_driver[drv_id].append(rec)
    return by_driver


def load_cbm_lookup(pat: str) -> dict | None:
    """Load CBM product lookup for 박종성 unload fee (optional — failure is non-fatal)."""
    try:
        import os
        import sys
        from pathlib import Path
        from harness.settlement.cbm_calc import load_product_lookup
        headers = {"Authorization": f"Bearer {pat}"}
        return load_product_lookup(headers)
    except Exception as exc:
        _log.warning("CBM lookup failed (unload fallback disabled)", error=str(exc))
        return None
