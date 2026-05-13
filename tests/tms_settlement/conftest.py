"""Shared record builder for tms_settlement calc tests.

All tests use raw dict records (no Airtable I/O).
"""
from __future__ import annotations

from harness.tms_settlement.config import (
    F_BOX_QTY,
    F_BOX_QTY_DIRECT,
    F_BOX_TEXT,
    F_DATE,
    F_DEST_ADDR,
    F_FARE,
    F_ITEMS_MFG,
    F_ORIGIN_ADDR,
    F_PARTNER,
    F_PRODUCT_FINAL,
    F_PROJECT_CODE,
    F_REQUEST_NOTE,
    F_SC_ID,
)

# Default origin text → resolves to ORIGINS["에이원지식산업센터"]
_ORIGIN_A1 = "서울 성동구 성수동 에이원지식산업센터"


def rec(
    rec_id: str,
    sc_id: str,
    date: str,
    driver_id: str,
    dest: str,
    *,
    origin: str = _ORIGIN_A1,
    fare_existing: int | None = None,
    project_code: str = "",
    request_note: str = "",
    box_text: str = "",
) -> dict:
    """Build a minimal fake Airtable Shipment record for unit tests."""
    return {
        "id": rec_id,
        "fields": {
            F_SC_ID:          sc_id,
            F_DATE:           date,
            F_PARTNER:        [driver_id],
            F_FARE:           fare_existing,
            F_ORIGIN_ADDR:    origin,
            F_DEST_ADDR:      dest,
            F_PROJECT_CODE:   project_code,
            F_REQUEST_NOTE:   request_note,
            F_BOX_TEXT:       box_text,
            F_BOX_QTY_DIRECT: None,
            F_BOX_QTY:        None,
            F_ITEMS_MFG:      None,
            F_PRODUCT_FINAL:  None,
        },
    }
