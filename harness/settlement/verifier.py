"""
harness/settlement/verifier.py — Harness 5차원 정산 검증기

5 Dimensions:
  D1 범위검사   (Scope)    — 출하확정일 범위, 드라이버 유효성
  D2 무결성     (Integrity)— 박종성 상하차비용 0건 비율
  D3 커버리지   (Coverage) — 좌표/품목 매칭률 ≥ COVERAGE_MIN
  D4 이상치     (Outlier)  — 운임 calc vs existing 편차 > FARE_OUTLIER_RATIO
  D5 비즈니스룰 (BizRule)  — CBM ≤ 트럭 적재용량, 운임 ≤ MAX_FARE

Modes:
  Formative (건별 빠른 체크)   — verify_record(item)  → FormativeResult
  Summative (전체 완료 후 게이트) — verify_batch(items)  → SummaryResult

Input record shape (from settlement_calc calc_* outputs):
  {
    sc_id: str, date: str, driver: str,
    fare_calc: int, unload_calc: int, fare_existing: int,
    note: str,
    cbm: float | None,   # optional Total_CBM (m³) for D5
  }

Usage:
  from verifier import verify_record, verify_batch

  r = verify_record(item)         # Formative
  s = verify_batch(items, week)   # Summative
  print(s.report())
"""
from __future__ import annotations

import dataclasses
from typing import Optional

# ── Thresholds ────────────────────────────────────────────────────────────────
COVERAGE_MIN        = 0.30   # D3: 좌표 매칭 비율이 이 값 미만이면 FAIL
FARE_OUTLIER_RATIO  = 0.30   # D4: |calc-existing|/existing > 30% → 이상치
UNLOAD_ZERO_LIMIT   = 0.50   # D2: 박종성 하차비=0 비율이 이 값 이상이면 FAIL
MAX_FARE            = 500_000  # D5: 단건 운임 상한 (원)

# 드라이버별 트럭 적재 용량 (m³) — 기사 용량 마스터 확정 2026-05-12
TRUCK_CBM: dict[str, float] = {
    "이장훈": 7.6,
    "조희선": 7.6,
    "박종성": 9.5,
}
KNOWN_DRIVERS = set(TRUCK_CBM)


# ── Data classes ──────────────────────────────────────────────────────────────
@dataclasses.dataclass
class Issue:
    sc_id: str
    dim: str       # "D1" | "D2" | "D3" | "D4" | "D5"
    severity: str  # "ERROR" | "WARN"
    msg: str

    def __str__(self) -> str:
        return f"[{self.severity}][{self.dim}] {self.sc_id}: {self.msg}"


@dataclasses.dataclass
class FormativeResult:
    sc_id: str
    passed: bool    # False only when at least one ERROR exists
    issues: list[Issue]

    def __bool__(self) -> bool:
        return self.passed

    def summary(self) -> str:
        if not self.issues:
            return f"{self.sc_id}: OK"
        return f"{self.sc_id}: {'; '.join(str(i) for i in self.issues)}"


@dataclasses.dataclass
class DimScore:
    name: str
    passed: bool
    rate: float    # 0.0 ~ 1.0  (1.0 = perfect)
    detail: str


@dataclasses.dataclass
class SummaryResult:
    week: str
    total: int
    passed: bool
    dims: dict[str, DimScore]   # keys: "D1" … "D5"
    issues: list[Issue]

    def report(self, max_issues: int = 20) -> str:
        lines = [
            "=" * 62,
            f"HARNESS VERIFIER - {self.week}  ({self.total} records)",
            f"Overall: {'PASS [OK]' if self.passed else 'FAIL [NG]'}",
            "=" * 62,
        ]
        for key, dim in self.dims.items():
            status = "PASS" if dim.passed else "FAIL"
            lines.append(f"  {key} {dim.name:<12} [{status}]  {dim.detail}")
        if self.issues:
            lines.append(f"\n{len(self.issues)} issues (showing up to {max_issues}):")
            errors   = [i for i in self.issues if i.severity == "ERROR"]
            warnings = [i for i in self.issues if i.severity == "WARN"]
            shown = 0
            for iss in errors + warnings:
                if shown >= max_issues:
                    remaining = len(self.issues) - max_issues
                    lines.append(f"  ... +{remaining} more")
                    break
                lines.append(f"  {iss}")
                shown += 1
        return "\n".join(lines)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _has_no_coord(note: str) -> bool:
    return "NO_COORD" in (note or "")


def _unload_is_zero(item: dict) -> bool:
    return (item.get("unload_calc") or 0) == 0


# ── Formative: per-record check ───────────────────────────────────────────────
def verify_record(
    item: dict,
    week_start: Optional[str] = None,
    week_end: Optional[str] = None,
) -> FormativeResult:
    """
    Per-record fast check (Formative).
    Call this immediately after computing each settlement record.

    week_start / week_end: "YYYY-MM-DD" boundaries (inclusive). Optional.
    """
    sc_id  = item.get("sc_id", "?")
    driver = item.get("driver", "")
    note   = item.get("note", "") or ""
    issues: list[Issue] = []

    # D1 범위검사 ──────────────────────────────────────────────────────────────
    if driver not in KNOWN_DRIVERS:
        issues.append(Issue(sc_id, "D1", "ERROR", f"알 수 없는 드라이버 '{driver}'"))
    rec_date = (item.get("date") or "")[:10]
    if week_start and week_end and rec_date:
        if not (week_start <= rec_date <= week_end):
            issues.append(Issue(sc_id, "D1", "WARN",
                                f"날짜 범위 이탈 {rec_date} ∉ [{week_start}…{week_end}]"))

    # D2 무결성 ────────────────────────────────────────────────────────────────
    # 박종성 건에서 하차비=0 이면서 좌표 매칭은 됐을 때 → 박스 데이터 누락 경고
    if driver == "박종성" and _unload_is_zero(item) and not _has_no_coord(note):
        issues.append(Issue(sc_id, "D2", "WARN",
                            "상하차비용=0 — 박스 데이터 없음 (수동 확인 필요)"))

    # D4 이상치 ────────────────────────────────────────────────────────────────
    fare_calc     = item.get("fare_calc", 0) or 0
    fare_existing = item.get("fare_existing", 0) or 0
    if fare_calc > 0 and fare_existing > 0:
        delta = abs(fare_calc - fare_existing) / fare_existing
        if delta > FARE_OUTLIER_RATIO:
            issues.append(Issue(sc_id, "D4", "WARN",
                                f"운임 편차 {delta:.0%}  calc={fare_calc:,}  existing={fare_existing:,}"))

    # D5 비즈니스룰 ────────────────────────────────────────────────────────────
    if fare_calc > MAX_FARE:
        issues.append(Issue(sc_id, "D5", "WARN",
                            f"운임 상한 초과 {fare_calc:,} > {MAX_FARE:,}원"))
    cbm = item.get("cbm")
    if cbm is not None and driver in TRUCK_CBM:
        cap = TRUCK_CBM[driver]
        if cbm > cap:
            issues.append(Issue(sc_id, "D5", "ERROR",
                                f"CBM 초과 {cbm:.3f}m³ > {cap}m³ ({driver})"))

    has_error = any(i.severity == "ERROR" for i in issues)
    return FormativeResult(sc_id=sc_id, passed=not has_error, issues=issues)


# ── Summative: full-batch gate ────────────────────────────────────────────────
def verify_batch(items: list[dict], week: str = "") -> SummaryResult:
    """
    Full-batch gate (Summative). Call after all records are computed.
    Returns SummaryResult with per-dimension scores and overall pass/fail.
    """
    all_issues: list[Issue] = []
    total = len(items)
    if total == 0:
        empty_dim = DimScore("(N/A)", passed=True, rate=1.0, detail="records=0")
        return SummaryResult(
            week=week, total=0, passed=True,
            dims={k: empty_dim for k in ("D1", "D2", "D3", "D4", "D5")},
            issues=[],
        )

    # ── D1 범위검사 ────────────────────────────────────────────────────────────
    unknown_driver = [i for i in items if i.get("driver", "") not in KNOWN_DRIVERS]
    for item in unknown_driver:
        all_issues.append(Issue(item.get("sc_id", "?"), "D1", "ERROR",
                                f"미등록 드라이버 '{item.get('driver')}'"))
    d1 = DimScore(
        name="범위검사",
        passed=len(unknown_driver) == 0,
        rate=1.0 - len(unknown_driver) / total,
        detail=f"미등록 드라이버 {len(unknown_driver)}건 / {total}건",
    )

    # ── D2 무결성 ──────────────────────────────────────────────────────────────
    park_items = [i for i in items if i.get("driver") == "박종성"]
    park_zero  = [
        i for i in park_items
        if _unload_is_zero(i) and not _has_no_coord(i.get("note") or "")
    ]
    for item in park_zero:
        all_issues.append(Issue(item.get("sc_id", "?"), "D2", "WARN",
                                "박종성 상하차비용=0 (박스 데이터 없음)"))
    zero_rate = len(park_zero) / len(park_items) if park_items else 0.0
    d2 = DimScore(
        name="무결성",
        passed=zero_rate < UNLOAD_ZERO_LIMIT,
        rate=1.0 - zero_rate,
        detail=(
            f"박종성 하차비=0: {len(park_zero)}/{len(park_items)}건"
            f"  ({zero_rate:.0%}  임계={UNLOAD_ZERO_LIMIT:.0%})"
        ),
    )

    # ── D3 커버리지 ────────────────────────────────────────────────────────────
    park_no_coord = [i for i in park_items if _has_no_coord(i.get("note") or "")]
    coverage = 1.0 - len(park_no_coord) / len(park_items) if park_items else 1.0
    for item in park_no_coord:
        all_issues.append(Issue(item.get("sc_id", "?"), "D3", "WARN",
                                f"좌표 미매칭: {(item.get('note') or '')[:50]}"))
    d3 = DimScore(
        name="커버리지",
        passed=coverage >= COVERAGE_MIN,
        rate=coverage,
        detail=f"좌표 매칭률 {coverage:.0%}  (미매칭 {len(park_no_coord)}건, 임계≥{COVERAGE_MIN:.0%})",
    )

    # ── D4 이상치 ──────────────────────────────────────────────────────────────
    outliers = []
    for item in items:
        fc = item.get("fare_calc", 0) or 0
        fe = item.get("fare_existing", 0) or 0
        if fc > 0 and fe > 0 and abs(fc - fe) / fe > FARE_OUTLIER_RATIO:
            outliers.append(item)
            delta = abs(fc - fe) / fe
            all_issues.append(Issue(item.get("sc_id", "?"), "D4", "WARN",
                                    f"운임 편차 {delta:.0%}  calc={fc:,}  existing={fe:,}"))
    outlier_rate = len(outliers) / total
    d4 = DimScore(
        name="이상치",
        passed=outlier_rate < 0.20,
        rate=1.0 - outlier_rate,
        detail=f"이상치 {len(outliers)}/{total}건  ({outlier_rate:.0%}, 임계<20%)",
    )

    # ── D5 비즈니스룰 ──────────────────────────────────────────────────────────
    biz_fail = []
    for item in items:
        driver    = item.get("driver", "")
        fare_calc = item.get("fare_calc", 0) or 0
        cbm       = item.get("cbm")
        sc_id     = item.get("sc_id", "?")
        if fare_calc > MAX_FARE:
            biz_fail.append(item)
            all_issues.append(Issue(sc_id, "D5", "WARN",
                                    f"운임 상한 초과 {fare_calc:,}원"))
        if cbm is not None and driver in TRUCK_CBM and cbm > TRUCK_CBM[driver]:
            biz_fail.append(item)
            all_issues.append(Issue(sc_id, "D5", "ERROR",
                                    f"CBM 초과 {cbm:.3f}m³ > {TRUCK_CBM[driver]}m³"))
    d5_has_error = any(i.dim == "D5" and i.severity == "ERROR" for i in all_issues)
    d5 = DimScore(
        name="비즈니스룰",
        passed=not d5_has_error,
        rate=1.0 - len(biz_fail) / total if total else 1.0,
        detail=f"룰 위반 {len(biz_fail)}건  (운임상한≤{MAX_FARE//1000}K, CBM≤용량)",
    )

    dims = {"D1": d1, "D2": d2, "D3": d3, "D4": d4, "D5": d5}
    overall = all(d.passed for d in dims.values())
    return SummaryResult(
        week=week,
        total=total,
        passed=overall,
        dims=dims,
        issues=all_issues,
    )


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    import json
    import os
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Harness Settlement Verifier")
    parser.add_argument("--week", default="", help="주 레이블 (YYYY-MM-DD ~ YYYY-MM-DD)")
    parser.add_argument("--log", required=True,
                        help="settlement log JSON (state/settlement_YYYY-MM-DD.json)")
    args = parser.parse_args()

    log_path = Path(args.log)
    if not log_path.exists():
        print(f"ERROR: {log_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(log_path, encoding="utf-8") as f:
        data = json.load(f)

    records = data.get("records", [])
    week_label = args.week or data.get("week", {})
    if isinstance(week_label, dict):
        week_label = f"{week_label.get('monday','')} ~ {week_label.get('sunday','')}"

    summary = verify_batch(records, week=week_label)
    print(summary.report())

    # Exit non-zero if any ERROR-level issue
    if any(i.severity == "ERROR" for i in summary.issues):
        sys.exit(2)
