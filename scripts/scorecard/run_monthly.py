"""Sub-Spec 5 월간 Scorecard 실행 스크립트.

Usage:
  python scripts/scorecard/run_monthly.py [--dry-run] [--month YYYY-MM]

--dry-run: Airtable 조회 후 Slack 발송 없이 메시지만 출력.
--month: 대상 월 지정 (기본: 직전 달).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
load_dotenv()

from harness.scorecard import CarrierScore
from harness.scorecard.calc import calc_all_carriers
from harness.scorecard.kpi_tracker import calc_kpi, load_history, append_snapshot, compute_deltas

KST = timezone(timedelta(hours=9))
HISTORY_PATH_DEFAULT = "scripts/scorecard/scorecard_history.jsonl"
WARN_THRESHOLD = 70.0


def _fmt_optional(val: float | None, fmt: str = ".1f") -> str:
    return f"{val:{fmt}}" if val is not None else "N/A"


def format_slack_message(
    scores: list[CarrierScore],
    kpi_deltas: dict,
    month_str: str,
) -> str:
    """상세형 B Slack DM 메시지 조립."""
    kst_now = datetime.now(KST).strftime("%Y-%m-%dT%H:%M KST")
    lines: list[str] = [
        f"📊 [{month_str}] Carrier Scorecard",
        f"대상 {len(scores)}개사 · 산출: {kst_now}",
        "",
    ]

    sorted_scores = sorted(scores, key=lambda s: s.total, reverse=True)
    warn: list[CarrierScore] = []

    for cs in sorted_scores:
        lines.append(f"── {cs.carrier_name} ({cs.total:.1f}/100) ──")
        lines.append(f"Cost        30% × {_fmt_optional(cs.cost)}pt = {_fmt_optional((cs.cost or 0)*0.30)}")
        lines.append(f"Reliability 35% × {_fmt_optional(cs.reliability)}pt = {_fmt_optional((cs.reliability or 0)*0.35)}")
        lines.append(f"Capacity    20% × {cs.capacity:.1f}pt = {cs.capacity*0.20:.1f}")
        lines.append(f"Damage      15% × {cs.damage:.1f}pt = {cs.damage*0.15:.1f}")
        lines.append(f"처리건수: {cs.shipment_count}건")
        lines.append("")
        if cs.total < WARN_THRESHOLD:
            warn.append(cs)

    if warn:
        lines.append("⚠️ 주의 (70점 미만)")
        for cs in warn:
            lines.append(f"  {cs.carrier_name} {cs.total:.1f}")
        lines.append("")

    lines.append("─" * 40)
    lines.append("KPI 상세 (전월 비교)")

    k1 = kpi_deltas["K_LC_1"]
    k2 = kpi_deltas["K_LC_2"]
    k3 = kpi_deltas["K_LC_3"]

    def _arrow(delta) -> str:
        if delta is None:
            return "← 첫 측정 (baseline)"
        return "↑" if delta > 0 else ("↓" if delta < 0 else "→")

    k1_pct = f"{k1['value']*100:.1f}%"
    k1_delta_str = f"({k1['delta']*100:+.1f}%p)" if k1["delta"] is not None else ""
    k1_target = f"[목표: {(k1['target'] or 0)*100:.1f}%]" if k1.get("target") else ""
    lines.append(f"K-LC-1 자체기사 활용도  {k1_pct} {k1_delta_str} {_arrow(k1['delta'])}  {k1_target}")

    k2_pct = f"{k2['value']*100:.1f}%"
    k2_delta_str = f"({k2['delta']*100:+.1f}%p)" if k2.get("delta") is not None else ""
    k2_ok = "✅" if k2["value"] >= 0.70 else "❌"
    lines.append(f"K-LC-2 Wave 자동화 비중 {k2_pct} {k2_delta_str} {k2_ok}  [목표: 70%]")

    k3_val = f"₩{k3['value']:,.0f}"
    k3_delta_str = f"({k3['delta_pct']*100:+.1f}%)" if k3.get("delta_pct") is not None else ""
    k3_target = f"[목표: ₩{k3['target']:,.0f}]" if k3.get("target") else ""
    lines.append(f"K-LC-3 Spillover 비용   {k3_val} {k3_delta_str}  {k3_target}")

    return "\n".join(lines)


def _send_slack(message: str) -> bool:
    import requests
    token = os.environ.get("SLACK_BOT_TOKEN")
    channel = os.environ.get("SLACK_DM_USER_ID")
    if not token or not channel:
        print("[WARN] SLACK_BOT_TOKEN / SLACK_DM_USER_ID 미설정 — Slack 발송 스킵", file=sys.stderr)
        return False
    resp = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {token}"},
        json={"channel": channel, "text": message},
        timeout=10,
    )
    data = resp.json()
    if data.get("ok"):
        print("Slack DM 발송 완료")
        return True
    print(f"[ERROR] Slack 발송 실패: {data.get('error')}", file=sys.stderr)
    return False


def _prev_month(ref: datetime) -> tuple[int, int]:
    """ref 기준 직전 달 (year, month) 반환."""
    first = ref.replace(day=1)
    prev = first - timedelta(days=1)
    return prev.year, prev.month


def main(dry_run: bool = False, month_override: str | None = None) -> None:
    now_kst = datetime.now(KST)

    if month_override:
        year, month = int(month_override[:4]), int(month_override[5:7])
    else:
        year, month = _prev_month(now_kst)

    month_str = f"{year:04d}-{month:02d}"
    print(f"[scorecard] 대상 월: {month_str}")

    history_path = __import__("pathlib").Path(HISTORY_PATH_DEFAULT)
    history = load_history(history_path)

    # 이전 달 처리건수 (Capacity 외주 추세용)
    prev_counts: dict[str, int] | None = None
    if history:
        last_snap = history[-1]
        prev_counts = {
            name: data.get("shipment_count", 0)
            for name, data in last_snap.get("carriers", {}).items()
        }

    print("[scorecard] Airtable 조회 중...")
    scores, shipments = calc_all_carriers(year, month, prev_counts)

    kpi_raw = calc_kpi(shipments)
    kpi_deltas = compute_deltas(kpi_raw, history)

    # JSONL 스냅샷 구성
    snapshot = {
        "month": month_str,
        "generated_at": now_kst.isoformat(),
        "carriers": {
            cs.carrier_name: {
                "cost": cs.cost,
                "reliability": cs.reliability,
                "capacity": cs.capacity,
                "damage": cs.damage,
                "total": cs.total,
                "shipment_count": cs.shipment_count,
            }
            for cs in scores
        },
        "kpi": kpi_deltas,
    }

    message = format_slack_message(scores, kpi_deltas, month_str)

    if dry_run:
        print("\n=== DRY RUN — Slack DM 미발송 ===")
        print(message)
        print("=== END ===")
    else:
        append_snapshot(history_path, snapshot)
        _send_slack(message)
        print(f"[scorecard] 스냅샷 저장: {history_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="월간 Scorecard 실행")
    parser.add_argument("--dry-run", action="store_true", help="Slack 발송 없이 메시지만 출력")
    parser.add_argument("--month", help="대상 월 (YYYY-MM). 기본: 직전 달")
    args = parser.parse_args()
    main(dry_run=args.dry_run, month_override=args.month)
