"""Fingerprint test — detects accidental changes to fare constants.

If this test fails, RATE_HISTORY (or WITHHOLDING_RATE / MAX_BLOCKED_RATIO) was
modified. Before updating the fingerprint, confirm the change is intentional:
  - Fare rate change: Slack approval from ops lead + re-verify golden tests
  - WITHHOLDING_RATE: tax accountant sign-off required (T0-1 blocker)
  - MAX_BLOCKED_RATIO: ops + engineering sign-off

To regenerate _RATE_FINGERPRINT after an approved change:
  python -c "
  import hashlib, json
  from harness.tms_settlement.config import RATE_HISTORY
  s = json.dumps(RATE_HISTORY, sort_keys=True, ensure_ascii=False)
  print(hashlib.sha256(s.encode()).hexdigest())
  "
"""
from __future__ import annotations

import hashlib
import json

from harness.tms_settlement.config import MAX_BLOCKED_RATIO, RATE_HISTORY, WITHHOLDING_RATE

_RATE_FINGERPRINT = "9008df20993e6e7f4338326ab5a3e2b9e9b5e781cc94d929eca5c452d3d88624"


def test_rate_history_fingerprint():
    s = json.dumps(RATE_HISTORY, sort_keys=True, ensure_ascii=False)
    got = hashlib.sha256(s.encode()).hexdigest()
    assert got == _RATE_FINGERPRINT, (
        f"RATE_HISTORY fingerprint mismatch — was the change intentional?\n"
        f"  expected: {_RATE_FINGERPRINT}\n"
        f"  got:      {got}\n"
        "Run the regeneration command in this file's docstring after approval."
    )


def test_withholding_rate_is_zero_until_t01_resolved():
    assert WITHHOLDING_RATE == 0.0, (
        "T0-1 not resolved — do not change WITHHOLDING_RATE until the tax "
        "accountant confirms 3.3% applicability. Update this assertion after sign-off."
    )


def test_max_blocked_ratio_sentinel():
    assert MAX_BLOCKED_RATIO == 0.10
