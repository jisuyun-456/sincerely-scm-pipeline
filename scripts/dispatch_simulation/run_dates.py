"""Read-only 자동배차 진단 드라이버 — 특정 출하확정일에 대한 wave 배정 결과를 확인.

wave_recommender 의 fetch/build/assign 파이프라인을 그대로 재사용하되 Airtable PATCH·
Slack·snapshot 저장은 일절 하지 않는다 (순수 read-only). 각 날짜별로 wave 배정 결과 +
수동(manual) 라우팅 사유를 출력해 자동배차 정확도/취약점을 눈으로 검증하기 위한 용도.

Usage:
  python -m scripts.dispatch_simulation.run_dates 2026-06-29 2026-06-30
"""
from __future__ import annotations

import sys
from collections import defaultdict

from dotenv import load_dotenv

load_dotenv()  # AIRTABLE_PAT from .env

from harness.dispatch.wave_assigner import (
    CONFIDENCE_FLOOR, DRIVER_LIMITS, TIER_TO_CANDIDATES, Shipment, assign_waves,
    compute_utilization, _slot_filter_w1,
)
from harness.dispatch.resource_loader import load_partners
from harness.dispatch import wave_recommender as wr


def _manual_reason(s: Shipment) -> str:
    """수동/스킵 사유 추정 (assign_waves_greedy 분기 순서 그대로)."""
    if s.wave_locked:
        return "wave_locked (사용자 잠금)"
    if s.slot_confidence * s.cbm_confidence < CONFIDENCE_FLOOR:
        return f"low_confidence ({s.slot_confidence:.2f}×{s.cbm_confidence:.2f}={s.slot_confidence*s.cbm_confidence:.2f} < {CONFIDENCE_FLOOR})"
    if s.slot is None:
        return "slot=None (배송슬롯 결정 실패)"
    cands = _slot_filter_w1(TIER_TO_CANDIDATES.get(s.region, []), s.slot)
    if not cands:
        return f"region={s.region} → 후보 wave 없음"
    if s.cbm > DRIVER_LIMITS['W3']['max_cbm']:
        return f"cbm={s.cbm:.2f} > W3 max {DRIVER_LIMITS['W3']['max_cbm']} (용차 필요)"
    return "capacity 부족 → spillover 예상"


def run(target_dates: list[str]) -> None:
    # 넉넉한 rolling window 로 fetch 후 정확히 대상 날짜만 필터
    today_iso = min(target_dates)
    raw = wr.fetch_auto_targets(today_iso, rolling_days=20)
    print(f"[fetch] today={today_iso} rolling=20 → {len(raw)} records")

    targets = set(target_dates)
    by_date: dict[str, list[dict]] = defaultdict(list)
    for rec in raw:
        f = rec.get("fields", {})
        sd_raw = wr._first(f.get(wr.FLD_SHIP_DATE)) or f.get(wr.FLD_SHIP_DATE) or ""
        sd = sd_raw[:10]
        if sd in targets:
            by_date[sd].append(rec)

    partners = load_partners()
    partner_autonomy = {
        p.get("배송파트너", ""): p.get("autonomy_level", "unknown")
        for p in partners if p.get("배송파트너")
    }
    print(f"[partners] {len(partners)} external partners, autonomy keys={list(partner_autonomy)[:5]}")

    for sd in sorted(targets):
        recs = by_date.get(sd, [])
        print("\n" + "=" * 72)
        print(f"  {sd}  —  {len(recs)} 대상 shipment")
        print("=" * 72)
        if not recs:
            print("  (대상 없음)")
            continue

        ships = [s for s in (wr._build_shipment(r) for r in recs) if s]
        # 입력 shipment 전체 테이블
        print(f"  {'id':<18} {'project':<12} {'slot':<8} {'region':<22} {'cbm':>6} {'s_cf':>5} {'c_cf':>5} {'conf':>5}")
        for s in ships:
            conf = s.slot_confidence * s.cbm_confidence
            print(f"  {s.id:<18} {(s.project_code or '-'):<12} {str(s.slot):<8} {s.region:<22} "
                  f"{s.cbm:>6.2f} {s.slot_confidence:>5.2f} {s.cbm_confidence:>5.2f} {conf:>5.2f}")

        plans = assign_waves(ships, partner_autonomy, sd, confidence_floor=CONFIDENCE_FLOOR)
        util = compute_utilization(plans)

        print(f"\n  --- 배정 결과 ---")
        for wid in ("W1", "W2", "W3"):
            p = plans[wid]
            lim = DRIVER_LIMITS[wid]
            print(f"  {wid} {lim['name']:<6}: {p.count}/{lim['max_count']}건  "
                  f"{p.total_cbm:.2f}/{lim['max_cbm']} CBM  ({util.get(wid,0):.0%})")
            for s in p.shipments:
                print(f"       └ {s.id}  {s.region}  slot={s.slot}  cbm={s.cbm:.2f}")
        for wid in ("spillover_로젠", "spillover_고고엑스", "locked-in"):
            if plans[wid].count:
                print(f"  {wid}: {plans[wid].count}건")
                for s in plans[wid].shipments:
                    print(f"       └ {s.id}  {s.region}  cbm={s.cbm:.2f}  method={s.method}")

        manual = plans["수동"]
        print(f"\n  수동(검토 필요): {manual.count}건")
        for s in manual.shipments:
            print(f"       └ {s.id}  {_manual_reason(s)}")

        auto = sum(plans[w].count for w in ("W1", "W2", "W3"))
        total = len(ships)
        print(f"\n  자동화율: {auto}/{total} ({auto/total:.0%})" if total else "  (shipment 없음)")


if __name__ == "__main__":
    dates = sys.argv[1:] or ["2026-06-29", "2026-06-30"]
    run(dates)
