"""
Settlement verifier — VerifierBase subclass with D1-D6 dimensions.

D1 Scope             — driver_id is in KNOWN_DRIVERS
D2 Integrity         — no overwrite (fare_existing == 0 unless --force)
D3 Coverage          — all fetched records have a calc result (no silent drop)
D4 Outlier           — 박종성 tolerance flag (WARNING, not ERROR)
D5 BizRule           — no_coord records must not be PATCHed
D6 OptimisticConcur  — fare_net > 0 for non-outsource (zero-fare gate)
"""
from __future__ import annotations

from typing import ClassVar

from harness._core.verifier import (
    BatchResult,
    DimScore,
    FormativeResult,
    Issue,
    VerifierBase,
)
from harness.tms_settlement.calc import SettlementItem
from harness.tms_settlement.config import KNOWN_DRIVERS, MAX_BLOCKED_RATIO


class SettlementVerifier(VerifierBase):
    _DIMS: ClassVar[tuple[str, ...]] = ("D1", "D2", "D3", "D4", "D5", "D6")

    def __init__(self, force: bool = False) -> None:
        self._force = force

    # ── Per-dimension checks ──────────────────────────────────────────────────

    def _check_d1(self, item: SettlementItem) -> list[Issue]:
        if item.driver_id not in KNOWN_DRIVERS:
            return [Issue(
                sc_id=item.sc_id, dim="D1", severity="ERROR",
                msg=f"Unknown driver_id={item.driver_id!r}",
            )]
        return []

    def _check_d2(self, item: SettlementItem) -> list[Issue]:
        if item.fare_existing and not self._force:
            return [Issue(
                sc_id=item.sc_id, dim="D2", severity="ERROR",
                msg=f"fare_existing={item.fare_existing:,} — use --force to overwrite",
            )]
        return []

    def _check_d3(self, item: SettlementItem) -> list[Issue]:
        # Checked at batch level (fetched count vs calc'd count) — always passes per-record
        return []

    def _check_d4(self, item: SettlementItem) -> list[Issue]:
        # Park tolerance flag is embedded in item.note; emit WARNING if flagged
        if "FLAG" in item.note:
            return [Issue(
                sc_id=item.sc_id, dim="D4", severity="WARNING",
                msg=f"Park fare deviates >tolerance: {item.note}",
            )]
        return []

    def _check_d5(self, item: SettlementItem) -> list[Issue]:
        if item.no_coord:
            return [Issue(
                sc_id=item.sc_id, dim="D5", severity="ERROR",
                msg=f"NO_COORD — cannot determine fare: {item.note}",
            )]
        return []

    def _check_d6(self, item: SettlementItem) -> list[Issue]:
        if item.fare_gross == 0 and not item.no_coord:
            return [Issue(
                sc_id=item.sc_id, dim="D6", severity="ERROR",
                msg="fare_gross=0 with valid coordinate — calc error",
            )]
        return []

    # ── VerifierBase interface ────────────────────────────────────────────────

    def verify_record(self, item: SettlementItem, **kwargs: object) -> FormativeResult:  # type: ignore[override]
        issues: list[Issue] = []
        for dim in self._DIMS:
            issues.extend(getattr(self, f"_check_{dim.lower()}")(item))
        has_error = any(i.severity == "ERROR" for i in issues)
        return FormativeResult(sc_id=item.sc_id, passed=not has_error, issues=issues)

    def verify_batch(
        self,
        items: list[SettlementItem],  # type: ignore[override]
        week: str = "",
        fetched_count: int = 0,
    ) -> BatchResult:
        all_issues: list[Issue] = []
        blocked = 0
        dim_errors: dict[str, int] = {d: 0 for d in self._DIMS}
        dim_warns:  dict[str, int] = {d: 0 for d in self._DIMS}

        for item in items:
            result = self.verify_record(item)
            all_issues.extend(result.issues)
            if not result.passed:
                blocked += 1
            for issue in result.issues:
                if issue.severity == "ERROR":
                    dim_errors[issue.dim] = dim_errors.get(issue.dim, 0) + 1
                elif issue.severity == "WARNING":
                    dim_warns[issue.dim] = dim_warns.get(issue.dim, 0) + 1

        # D3 batch-level: calc'd count must equal fetched count
        if fetched_count and len(items) != fetched_count:
            gap = fetched_count - len(items)
            all_issues.append(Issue(
                sc_id="BATCH", dim="D3", severity="ERROR",
                msg=f"Coverage gap: fetched={fetched_count} calc'd={len(items)} (missing={gap})",
            ))
            blocked += 1

        total = len(items)
        blocked_ratio = blocked / total if total else 0.0
        batch_ok = blocked_ratio <= MAX_BLOCKED_RATIO

        dims: dict[str, DimScore] = {}
        for d in self._DIMS:
            errs = dim_errors.get(d, 0)
            warns = dim_warns.get(d, 0)
            dims[d] = DimScore(
                name=d,
                passed=(errs == 0),
                rate=1.0 - (errs / total if total else 0),
                detail=f"{errs} errors, {warns} warnings",
            )

        return BatchResult(
            week=week,
            total=total,
            passed=batch_ok,
            dims=dims,
            issues=all_issues,
            blocked_count=blocked,
        )
