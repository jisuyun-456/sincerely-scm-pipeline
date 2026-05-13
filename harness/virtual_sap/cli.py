"""CLI entry point: python -m harness.virtual_sap.cli <subcommand>"""
from __future__ import annotations

import argparse
import logging
import os
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Virtual SAP Simulation CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # seed
    p_seed = sub.add_parser("seed", help="Load master data into Supabase")
    p_seed.add_argument("--dry-run", action="store_true")

    # tick
    p_tick = sub.add_parser("tick", help="Run one simulation tick")
    p_tick.add_argument(
        "--mode", choices=["manual", "daily", "backfill"], default="manual"
    )
    p_tick.add_argument(
        "--orders", type=int, default=2, help="Orders to generate per tick"
    )
    p_tick.add_argument("--dry-run", action="store_true")

    # verify
    p_verify = sub.add_parser("verify", help="Re-run verifiers on a past run")
    p_verify.add_argument("--run-id", required=True)

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    # Propagate --dry-run to env so config picks it up
    if getattr(args, "dry_run", False):
        os.environ["VSAP_DRY_RUN"] = "true"

    if args.cmd == "seed":
        from .seed.seed_master import seed_all, verify_seed

        counts = seed_all(dry_run=args.dry_run)
        print("Seed complete:", counts)
        if not args.dry_run:
            ok = verify_seed()
            sys.exit(0 if ok else 1)

    elif args.cmd == "tick":
        from .engine import run_tick

        result = run_tick(mode=args.mode, orders_count=args.orders)
        print(f"Tick {result['status']}: {result['docs_created']} docs created")
        sys.exit(0 if result["status"] == "ok" else 1)

    elif args.cmd == "verify":
        from .verifier import inventory_verifier, doc_verifier, flow_verifier, ledger_verifier

        all_passed = True
        for vm in [inventory_verifier, doc_verifier, flow_verifier, ledger_verifier]:
            r = vm.verify(args.run_id)
            status = "PASS" if r.passed else "FAIL"
            print(f"{vm.__name__}: {status} ({len(r.issues)} issues)")
            for issue in r.issues:
                print(f"  {issue}")
            all_passed = all_passed and r.passed
        sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
