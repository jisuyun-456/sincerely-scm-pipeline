"""Sub-Spec 3 Validation Contract C1~C8 self-check.

Runs all verifiable contracts and prints a summary.
C1·C2·C5 require AIRTABLE_PAT. C3·C4·C6·C7·C8 are pytest-based (offline).

Usage:
    python scripts/verification/verify_subspec3_contract.py [--skip-airtable]
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional


@dataclass
class ContractResult:
    id: str
    description: str
    passed: Optional[bool]
    detail: str = ""


def run_pytest(test_path: str, description: str) -> ContractResult:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", test_path, "-q", "--tb=short"],
        capture_output=True, text=True
    )
    passed = result.returncode == 0
    output = (result.stdout + result.stderr).strip()
    # Extract pass line
    for line in output.splitlines():
        if "passed" in line or "failed" in line or "error" in line:
            detail = line.strip()
            break
    else:
        detail = output[-200:] if output else "(no output)"
    return ContractResult(id="", description=description, passed=passed, detail=detail)


def run_script(script: str, description: str) -> ContractResult:
    result = subprocess.run(
        [sys.executable, script],
        capture_output=True, text=True
    )
    passed = result.returncode == 0
    output = (result.stdout + result.stderr).strip()
    last_lines = "\n".join(output.splitlines()[-4:])
    return ContractResult(id="", description=description, passed=passed, detail=last_lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-airtable", action="store_true",
                        help="Skip contracts requiring Airtable API (C1·C2·C5)")
    args = parser.parse_args()

    results: list[tuple[str, ContractResult]] = []

    # C1 — 자동 대상 필터 (Airtable)
    if args.skip_airtable:
        results.append(("C1", ContractResult("C1", "자동 대상 필터 sample 50건 100% 일치", None, "SKIPPED (--skip-airtable)")))
    else:
        r = run_script("scripts/verification/verify_c1_filter.py", "자동 대상 필터 sample 100% 일치")
        results.append(("C1", r))

    # C2 — 배송슬롯 정확도 ≥ 80% (Airtable)
    if args.skip_airtable:
        results.append(("C2", ContractResult("C2", "배송슬롯 자동 결정 정확도 ≥ 80%", None, "SKIPPED (--skip-airtable)")))
    else:
        r = run_script("scripts/verification/verify_c2_slot.py", "배송슬롯 자동 결정 정확도 ≥ 80%")
        results.append(("C2", r))

    # C3 — Multi-PNA consolidation 10 case
    r = run_pytest("tests/dispatch/test_consolidation.py", "Multi-PNA consolidation 10 case")
    results.append(("C3", r))

    # C4 — capacity 초과 0건
    r = run_pytest("tests/dispatch/test_capacity.py", "자체 기사 capacity 초과 0건")
    results.append(("C4", r))

    # C5 — locked-in override 0건 (Airtable)
    if args.skip_airtable:
        results.append(("C5", ContractResult("C5", "locked-in override 0건", None, "SKIPPED (--skip-airtable)")))
    else:
        r = run_script("scripts/verification/verify_c5_lockin.py", "locked-in override 0건")
        results.append(("C5", r))

    # C6 — quiet hours 발송 0건
    r = run_pytest("tests/dispatch/test_quiet_hours.py", "Slack quiet hours 22:00~07:00 발송 0건")
    results.append(("C6", r))

    # C7 — wave_locked override skip
    r = run_pytest("tests/dispatch/test_override.py", "wave_locked=True override 다음 cycle skip")
    results.append(("C7", r))

    # C8 — 7일 rolling 영업일 기준
    r = run_pytest("tests/dispatch/test_rolling_window.py", "7일 rolling 영업일 기준 정확")
    results.append(("C8", r))

    # ─── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Sub-Spec 3 Validation Contract — C1~C8")
    print("=" * 60)

    passed_count = 0
    skipped_count = 0
    failed_ids = []

    for cid, r in results:
        if r.passed is None:
            icon = "⏭️ "
            skipped_count += 1
        elif r.passed:
            icon = "✅"
            passed_count += 1
        else:
            icon = "❌"
            failed_ids.append(cid)
        print(f"{icon} {cid} {r.description}")
        if r.detail:
            for line in r.detail.splitlines():
                print(f"     {line}")

    print()
    total_required = len(results) - skipped_count
    if not failed_ids:
        print(f"All Contracts PASS ({passed_count}/{total_required}){' — skipped: ' + str(skipped_count) if skipped_count else ''}")
        if skipped_count == 0:
            print("→ production ready.")
        else:
            print("→ run without --skip-airtable for full verification.")
        sys.exit(0)
    else:
        print(f"FAIL — {len(failed_ids)} contracts: {', '.join(failed_ids)}")
        print("→ production deploy BLOCKED. Fix before shipping.")
        sys.exit(1)


if __name__ == "__main__":
    main()
