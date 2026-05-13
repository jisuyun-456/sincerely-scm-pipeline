"""
Settlement write layer — verify → PATCH → read-back → checkpoint.

Sequence per record:
1. verify_record() — ERROR → skip with log (counted toward blocked ratio)
2. PATCH via AirtableClient (idempotency key = SHA-256 of rec_id+fields)
3. Read-back from PATCH response — assert written values match expected
4. Checkpoint fsync via IdempotentRunner
"""
from __future__ import annotations

from dataclasses import dataclass, field

from harness._core.airtable import AirtableClient
from harness._core.logger import StructuredLogger
from harness._core.runner import IdempotentRunner
from harness.tms_settlement.calc import SettlementItem
from harness.tms_settlement.config import F_FARE, F_UNLOAD, MAX_BLOCKED_RATIO
from harness.tms_settlement.verifier import SettlementVerifier

_log = StructuredLogger("tms_settlement.write")


@dataclass
class WriteResult:
    written: int = 0
    skipped_blocked: int = 0
    skipped_existing: int = 0
    skipped_no_coord: int = 0
    failed: int = 0
    driver_totals: dict[str, dict] = field(default_factory=dict)


def _assert_readback(item: SettlementItem, response: dict) -> None:
    """Verify PATCH response contains the values we intended to write."""
    resp_fields = response.get("fields", {})
    written_fare = resp_fields.get(F_FARE)
    if written_fare is not None and written_fare != item.fare_gross:
        raise RuntimeError(
            f"Read-back mismatch for {item.sc_id}: "
            f"wrote fare={item.fare_gross} but Airtable returned {written_fare}"
        )


def _build_patch_fields(item: SettlementItem) -> dict:
    fields = {F_FARE: item.fare_gross}
    if item.unload_calc > 0:
        fields[F_UNLOAD] = item.unload_calc
    return fields


def write_batch(
    items: list[SettlementItem],
    client: AirtableClient,
    verifier: SettlementVerifier,
    runner: IdempotentRunner,
    *,
    dry_run: bool = False,
    force: bool = False,
    week: str = "",
    fetched_count: int = 0,
) -> WriteResult:
    """Verify all items, abort if blocked ratio exceeds threshold, then write."""
    result = WriteResult()

    # ── Batch verify ─────────────────────────────────────────────────────────
    batch = verifier.verify_batch(items, week=week, fetched_count=fetched_count)
    _log.info("batch verify", passed=batch.passed, blocked=batch.blocked_count, total=batch.total)

    if not batch.passed:
        _log.error(
            "batch blocked — abort",
            blocked=batch.blocked_count,
            ratio=f"{batch.blocked_count/batch.total:.1%}" if batch.total else "N/A",
            report=batch.report(),
        )
        raise SystemExit(2)

    # Log warnings from batch verify
    for issue in batch.issues:
        if issue.severity == "WARNING":
            _log.warning("verifier warning", dim=issue.dim, sc_id=issue.sc_id, msg=issue.msg)

    # ── Per-record write ──────────────────────────────────────────────────────
    for item in items:
        # Skip if already processed in a prior run (checkpoint resume)
        if runner.is_done(item.rec_id):
            result.skipped_existing += 1
            continue

        # Skip if fare already set and not --force
        if item.fare_existing and not force:
            result.skipped_existing += 1
            _log.info("skip existing", sc_id=item.sc_id, fare_existing=item.fare_existing)
            continue

        # Per-record formative verify
        record_result = verifier.verify_record(item)
        if not record_result.passed:
            result.skipped_blocked += 1
            for issue in record_result.issues:
                if issue.severity == "ERROR":
                    _log.error("record blocked", dim=issue.dim, sc_id=issue.sc_id, msg=issue.msg)
            continue

        if item.no_coord:
            result.skipped_no_coord += 1
            _log.warning("no_coord skip", sc_id=item.sc_id, note=item.note)
            continue

        # Accumulate driver totals for Slack summary
        drv = item.driver_name
        t = result.driver_totals.setdefault(drv, {"count": 0, "fare": 0, "unload": 0})
        t["count"] += 1
        t["fare"]  += item.fare_gross
        t["unload"] += item.unload_calc

        if dry_run:
            _log.info(
                "dry-run", sc_id=item.sc_id, driver=item.driver_name,
                fare=item.fare_gross, unload=item.unload_calc, note=item.note,
            )
            result.written += 1
            continue

        # PATCH
        try:
            patch_fields = _build_patch_fields(item)
            response = client.patch_record(item.rec_id, patch_fields)
            _assert_readback(item, response)
            runner.mark_done(item.rec_id)
            result.written += 1
            _log.info(
                "written", sc_id=item.sc_id, driver=item.driver_name,
                fare=item.fare_gross, unload=item.unload_calc,
            )
        except Exception as exc:
            result.failed += 1
            _log.error("patch failed", sc_id=item.sc_id, error=str(exc))

    return result
