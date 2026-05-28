"""Sub-Spec 4 Validation Contract C1~C5 자동 검증.

C1~C5: 단위 테스트로 검증 (pytest).
사용법: python scripts/verification/verify_subspec4_contract.py
"""
from __future__ import annotations

import subprocess
import sys


def _pytest(*args: str) -> list[str]:
    return [sys.executable, "-m", "pytest", *args]


def run_contract(label: str, cmd: list[str]) -> bool:
    result = subprocess.run(cmd, capture_output=True, text=True)
    passed = result.returncode == 0
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}  {label}")
    if not passed:
        print(result.stdout[-500:])
        print(result.stderr[-200:])
    return passed


def main() -> int:
    print("Sub-Spec 4 Validation Contract")
    print("=" * 40)
    results = [
        run_contract(
            "C1: 신규 TO 감지 (change_detector added)",
            [sys.executable, "-m", "pytest", "tests/dispatch/test_change_detector.py::TestAdded", "-q"],
        ),
        run_contract(
            "C2: 취소/Critical 변경 감지 (change_detector modified/removed)",
            [sys.executable, "-m", "pytest", "tests/dispatch/test_change_detector.py::TestRemovedAndModified", "-q"],
        ),
        run_contract(
            "C3: add_logen_days 일요일 skip",
            [sys.executable, "-m", "pytest", "tests/dispatch/test_logen_days.py", "-q"],
        ),
        run_contract(
            "C4: OTIF 4케이스 (퀵/택배/NULL납기/POD확인완료)",
            [sys.executable, "-m", "pytest", "tests/dispatch/test_otif_estimator.py::TestOtifCases", "-q"],
        ),
        run_contract(
            "C5: JSONL append-only (2회 호출 → 2줄)",
            [sys.executable, "-m", "pytest", "tests/dispatch/test_otif_estimator.py::TestJsonlAppend", "-q"],
        ),
    ]
    passed = sum(results)
    total = len(results)
    print("=" * 40)
    print(f"Contract: {passed}/{total} PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
