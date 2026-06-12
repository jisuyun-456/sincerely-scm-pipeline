"""P6b Slack digest 빌더 — 순수 함수만 (발송 IO는 scripts/backbone/order_cascade.py).

spec §3.2: 신규 주문 ≥1건인 tick만 digest (주문 수·부족자재 top·창고 경고).
P6a 학습 1: 부분 216의 주인은 데이터 — top-N 부족자재만 노출, 부분 나열 금지.
입력 = run_unit 결과 리스트 (row 텍스트 필드 파싱 — 포맷은 cascade.shortage_text·
staging_projection이 핀, 변경 시 본 모듈 테스트가 깨져 동기화 강제).
"""
from __future__ import annotations

import re

_SHORTAGE_RE = re.compile(r"^([\w\-]+)×([\d.]+)\(재고 ")   # PT코드 — × 미포함 보장
_STAGING_RE = re.compile(r"^staging [\d.]+%→([\d.]+)% ")
_ACTIONABLE = ("new", "changed")


def aggregate_shortages(results: list[dict]) -> list[tuple[str, float]]:
    """new/changed 행의 부족자재_요약 → PT별 부족분 합산, 내림차순."""
    by_pt: dict[str, float] = {}
    for r in results:
        if r["action"] not in _ACTIONABLE:
            continue
        for line in str(r["row"].get("부족자재_요약") or "").splitlines():
            m = _SHORTAGE_RE.match(line.strip())
            if m:
                by_pt[m.group(1)] = by_pt.get(m.group(1), 0.0) + float(m.group(2))
    return sorted(by_pt.items(), key=lambda kv: (-kv[1], kv[0]))


def staging_warnings(results: list[dict]) -> list[tuple[str, float]]:
    """new/changed 행 중 입하 후 staging 적재율 100% 초과 예상 (전파ID, after%)."""
    out = []
    for r in results:
        if r["action"] not in _ACTIONABLE:
            continue
        m = _STAGING_RE.match(str(r["row"].get("창고적재_예상") or ""))
        if m and float(m.group(1)) > 100.0:
            out.append((str(r["row"].get("전파ID") or ""), float(m.group(1))))
    return out


def build_digest(results: list[dict], totals: dict, run_id: str,
                 window_days: int, top_n: int = 5) -> str | None:
    """tick digest 텍스트. 신규 주문 0이면 None (발송 안 함 — spec §3.2)."""
    if totals.get("new", 0) < 1:
        return None
    lines = [
        f"📦 Order Cascade {run_id} (윈도우 {window_days}d)",
        f"신규 {totals['new']} / 변경 {totals['changed']} / "
        f"변동없음 {totals['unchanged']} · "
        f"완결 {totals['완결']} / 부분 {totals['부분']} / 끊김 {totals['끊김']}",
    ]
    shortages = aggregate_shortages(results)
    if shortages:
        lines.append(f"부족자재 top {min(top_n, len(shortages))}:")
        lines += [f"  · {pt}×{qty:g}" for pt, qty in shortages[:top_n]]
    warns = staging_warnings(results)
    if warns:
        lines.append("⚠ 입하장 적재 경고 (입하 후 >100%):")
        lines += [f"  · {pid}: {pct:.1f}%" for pid, pct in warns]
    return "\n".join(lines)
