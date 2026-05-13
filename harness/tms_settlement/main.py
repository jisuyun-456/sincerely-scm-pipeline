"""
TMS Settlement — thin CLI orchestrator.

Usage:
  py -m harness.tms_settlement.main --week 2026-05-04    # weekly batch
  py -m harness.tms_settlement.main                      # defaults to last Monday
  py -m harness.tms_settlement.main --dry-run            # no writes
  py -m harness.tms_settlement.main --force              # overwrite existing fare
  py -m harness.tms_settlement.main --mode fresh         # ignore checkpoint

Exit codes:
  0 — success
  1 — configuration or fetch error
  2 — batch verify failed (blocked ratio > 10%)
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import date, timedelta

from harness._core.airtable import AirtableClient
from harness._core.calendar import assert_week_in_window, today_kst, week_range
from harness._core.logger import StructuredLogger
from harness._core.notifier import Notifier
from harness._core.runner import IdempotentRunner
from harness._core.supabase_sink import SupabaseSink
from harness.tms_settlement import DOMAIN
from harness.tms_settlement.calc import calc_cho, calc_lee, calc_park
from harness.tms_settlement.config import (
    DRIVER_CHO,
    DRIVER_LEE,
    DRIVER_PARK,
    SHIPMENT_TABLE,
    TMS_BASE,
    SettlementConfig,
)
from harness.tms_settlement.fetch import (
    UnregisteredDriverError,
    fetch_week,
    load_cbm_lookup,
    split_by_driver,
)
from harness.tms_settlement.verifier import SettlementVerifier
from harness.tms_settlement.write import write_batch

_log = StructuredLogger(DOMAIN)


def _last_monday() -> date:
    today = today_kst()
    return today - timedelta(days=today.weekday() + 7)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="기사님 운임비 정산 자동화 (tms_settlement)")
    p.add_argument("--week", help="Week start date YYYY-MM-DD (Monday). Default: last Monday.")
    p.add_argument("--dry-run", action="store_true", help="Preview only — no Airtable writes.")
    p.add_argument("--force", action="store_true", help="Overwrite existing fare values.")
    p.add_argument(
        "--mode", choices=["resume", "reconcile", "fresh"], default="resume",
        help="Checkpoint mode (default: resume).",
    )
    p.add_argument("--auto-confirm", action="store_true", help="Skip interactive confirm (CI).")
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    # ── 1. Config & env validation ────────────────────────────────────────────
    try:
        cfg = SettlementConfig.from_env()
    except Exception as exc:
        _log.error("config validation failed", error=str(exc))
        sys.exit(1)

    sink = SupabaseSink.from_env()
    t0 = time.monotonic()

    # ── 2. Determine date range ───────────────────────────────────────────────
    if args.week:
        monday_d = date.fromisoformat(args.week)
    else:
        monday_d = _last_monday()

    try:
        assert_week_in_window(monday_d)
    except Exception as exc:
        _log.error("week out of allowed window", error=str(exc))
        sys.exit(1)

    monday, sunday = monday_d.isoformat(), (monday_d + timedelta(days=6)).isoformat()
    _log.info("settlement start", monday=monday, sunday=sunday, dry_run=args.dry_run)
    if sink:
        sink.log_event(source="harness", agent_id=DOMAIN, domain="TMS",
                       week=monday, status="started")

    # ── 3. Airtable client ────────────────────────────────────────────────────
    client = AirtableClient.get_or_create(TMS_BASE, SHIPMENT_TABLE, cfg.pat)
    client.check_schema_drift()

    notifier = Notifier(cfg)

    # ── 4. Fetch ──────────────────────────────────────────────────────────────
    try:
        records, unregistered = fetch_week(client, monday, sunday)
    except Exception as exc:
        _log.error("fetch failed", error=str(exc))
        notifier.notify(f"Settlement fetch failed: {exc}", severity="CRITICAL", domain=DOMAIN)
        if sink:
            sink.log_event(source="harness", agent_id=DOMAIN, domain="TMS",
                           week=monday, status="failed", summary=f"fetch failed: {exc}")
        sys.exit(1)

    if unregistered:
        msg = f"Unregistered driver IDs: {unregistered} - aborting (P0/D1)"
        _log.error(msg)
        notifier.notify(msg, severity="CRITICAL", domain=DOMAIN)
        if sink:
            sink.log_event(source="harness", agent_id=DOMAIN, domain="TMS",
                           week=monday, status="failed", summary=msg)
        sys.exit(2)

    if not records:
        _log.info("no shipments for this week — done")
        sys.exit(0)

    by_driver = split_by_driver(records)
    _log.info(
        "driver split",
        lee=len(by_driver[DRIVER_LEE]),
        cho=len(by_driver[DRIVER_CHO]),
        park=len(by_driver[DRIVER_PARK]),
    )

    # ── 5. CBM lookup (optional, 박종성 unload fallback) ─────────────────────
    product_lookup: dict | None = None
    if by_driver[DRIVER_PARK]:
        product_lookup = load_cbm_lookup(cfg.pat)

    # ── 6. Calculate ──────────────────────────────────────────────────────────
    settlement = (
        calc_lee(by_driver[DRIVER_LEE], DRIVER_LEE)
        + calc_cho(by_driver[DRIVER_CHO], DRIVER_CHO)
        + calc_park(by_driver[DRIVER_PARK], DRIVER_PARK, product_lookup=product_lookup)
    )

    if not settlement:
        _log.info("no settlement items after calc — done")
        sys.exit(0)

    # ── 7. Interactive confirm (skipped in CI / dry-run) ──────────────────────
    if not args.dry_run and not args.auto_confirm:
        print(f"\nSettlement preview: {len(settlement)} records  ({monday} ~ {sunday})")
        for item in settlement:
            u = f"  unload={item.unload_calc:,}" if item.unload_calc else ""
            flag = "  [NO_COORD]" if item.no_coord else ""
            print(f"  {item.sc_id:<13} {item.date:<11} {item.driver_name:<8} "
                  f"fare={item.fare_gross:>8,}{u}{flag}  {item.note}")
        resp = input("\nProceed with writing to Airtable? [y/N] ").strip().lower()
        if resp != "y":
            _log.info("aborted by user")
            sys.exit(0)

    # ── 8. Write (with IdempotentRunner checkpoint) ───────────────────────────
    verifier = SettlementVerifier(force=args.force)

    with IdempotentRunner(DOMAIN, monday, mode=args.mode) as runner:
        try:
            result = write_batch(
                settlement, client, verifier, runner,
                dry_run=args.dry_run,
                force=args.force,
                week=monday,
                fetched_count=len(records),
            )
        except SystemExit:
            notifier.notify(
                f"Settlement batch blocked >10% — manual review required ({monday})",
                severity="CRITICAL", domain=DOMAIN,
            )
            raise

    # ── 9. Notify ─────────────────────────────────────────────────────────────
    label = "[DRY-RUN] " if args.dry_run else ""
    lines = [
        f"{label}*정산 완료* {monday} ~ {sunday}",
        f"Written={result.written}  Skipped={result.skipped_existing}  "
        f"Blocked={result.skipped_blocked}  NoCoord={result.skipped_no_coord}  "
        f"Failed={result.failed}",
    ]
    for drv, t in result.driver_totals.items():
        u_str = f"  unload={t['unload']:,}" if t["unload"] else ""
        lines.append(f"  {drv}: {t['count']}건  fare={t['fare']:,}{u_str}")

    summary = "\n".join(lines)
    _log.info("settlement complete", written=result.written, failed=result.failed)
    notifier.notify(summary, severity="INFO", domain=DOMAIN)
    if sink:
        sink.log_event(
            source="harness", agent_id=DOMAIN, domain="TMS", week=monday,
            status="failed" if result.failed else "completed",
            duration_ms=int((time.monotonic() - t0) * 1000),
            summary=f"written={result.written} failed={result.failed} skipped={result.skipped_existing}",
            meta={"written": result.written, "failed": result.failed,
                  "skipped": result.skipped_existing, "dry_run": args.dry_run},
        )

    if result.failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
