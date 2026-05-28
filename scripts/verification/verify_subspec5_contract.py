"""Sub-Spec 5 Validation Contract C1~C4 자동 검증."""
from __future__ import annotations
import subprocess
import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

PASS = "✅ PASS"
FAIL = "❌ FAIL"
results = []


def check(label: str, ok: bool, detail: str = "") -> None:
    status = PASS if ok else FAIL
    print(f"{status} {label}" + (f" — {detail}" if detail else ""))
    results.append(ok)


# Change to project root for path checks
os.chdir(Path(__file__).parent.parent.parent)

# C1: scorecard.yml 존재 + cron 설정 포함
yml_path = Path(".github/workflows/scorecard.yml")
c1 = yml_path.exists() and "cron" in yml_path.read_text()
check("C1: scorecard.yml cron 설정 존재", c1)

# C2: test_calc.py 모든 테스트 PASS
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/scorecard/test_calc.py", "-q"],
    capture_output=True, text=True
)
c2 = result.returncode == 0
check("C2: 4축 점수 함수 단위 테스트 PASS", c2, result.stdout.strip().split("\n")[-1])

# C3: test_kpi_tracker.py 모든 테스트 PASS
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/scorecard/test_kpi_tracker.py", "-q"],
    capture_output=True, text=True
)
c3 = result.returncode == 0
check("C3: KPI 계산 + JSONL 2-run 시나리오 PASS", c3, result.stdout.strip().split("\n")[-1])

# C4: run_monthly.py --dry-run import 가능 + format_slack_message 실행
try:
    from scripts.scorecard.run_monthly import format_slack_message
    from harness.scorecard import CarrierScore
    from harness.scorecard.kpi_tracker import compute_deltas
    mock_scores = [
        CarrierScore("r1", "이장훈", cost=90.0, reliability=85.0, capacity=80.0, damage=100.0, total=88.0, shipment_count=30),
        CarrierScore("r2", "로젠", cost=None, reliability=70.0, capacity=50.0, damage=95.0, total=65.0, shipment_count=50),
    ]
    mock_kpi = compute_deltas({"K_LC_1": 0.6, "K_LC_2": 0.8, "K_LC_3": 500000.0}, [])
    msg = format_slack_message(mock_scores, mock_kpi, "2026-05")
    c4_ok = "⚠️ 주의" in msg and "K-LC-1" in msg and "K-LC-2" in msg and "K-LC-3" in msg
    check("C4: Slack 포맷 상세형 B (⚠️ 주의 + KPI 3종 포함)", c4_ok)
except Exception as e:
    check("C4: Slack 포맷 상세형 B", False, str(e))

print()
total = sum(results)
print(f"Contract: {total}/{len(results)} PASS")
sys.exit(0 if all(results) else 1)
