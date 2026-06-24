"""Chain C — 배차 재분배 overbook Alert (조희선 과적 → 박종성/이장훈 무비용 흡수).

2026-06-24 진단(`배차적재율-통합진단` / `조희선-차량적정성-평가`)의 권고
**'배차 재분배(무비용), 신규차량 부결'** 을 read-only Slack alert 로 코드화한다.

규칙: dispatch-day 별로 조희선(W2) 실적재율이 임계(기본 95%, D-TMS2 5% safety margin)를
넘고 박종성(W3)/이장훈(W1)에 동일일 흡수 여력이 있으면 알림. 경기 surcharge 노출도 표기.

무비용 근거(RATE_HISTORY): 이장훈 일정액(동일일 추가 stop 한계비용 ₩0), 조희선 경기 1건
초과당 ₩30k surcharge(이전 시 절감), 박종성 거리비례(부분 상쇄). → 동일일 재분배 ≈ 무비용.

데이터: 배차일지(tbl0YCjOC7rYtyXHV)가 33일+ stale → live Shipment 재구성 기반.
util>200%(util_ceiling)는 multi-run 합산 왜곡 아티팩트로 분리(05-21 224%·05-22 544% 부류).

Immutable Ledger: **읽기 전용** — Airtable PATCH / movement / mat_document 미작성.
재분배 결정은 운영자(human-in-the-loop). 배차일지 입력 재개 후 per-run 수치 재확정 필요.

Usage:
  python scripts/dispatch/overbook_alert.py [--days 14] [--threshold 0.95] [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
load_dotenv()

from harness.dispatch.wave_recommender import (  # noqa: E402
    FLD_SHIP_DATE,
    _build_shipment,
    _first,
    fetch_auto_targets,
)
from harness.tms_settlement.config import rates_for  # noqa: E402
from utils.vehicle_util import (  # noqa: E402
    FALLBACK_CAP,
    bare_driver,
    capacities_from_shipments,
    capacity_for,
)

KST = timezone(timedelta(hours=9))

DRIVER_CHO = "조희선"
DRIVER_PARK = "박종성"
DRIVER_LEE = "이장훈"

# region_classifier tier 중 경기 (cho_gyeonggi_surcharge 대상)
GYEONGGI_REGIONS = frozenset({"tier2_이장훈_gyeonggi", "tier3_gyeonggi_etc"})

DEFAULT_THRESHOLD = 0.95    # 조희선 과적 임계 (5% safety margin, D-TMS2 평가)
DEFAULT_CEILING = 2.0       # util>200% = multi-run 합산 아티팩트
DEFAULT_SURCHARGE = 30_000  # 경기 1건 초과당 (fallback; rates_for 가 권위)


def _match_driver(partner) -> str | None:
    """배송파트너 표기(어떤 형식이든) → 내부 3기사명. 외부 퀵·미상은 None(집계 제외)."""
    bare = bare_driver(partner)
    if not bare:
        return None
    for name in (DRIVER_CHO, DRIVER_PARK, DRIVER_LEE):
        if name in bare or bare in name:
            return name
    return None


def compute_overbook(by_date, cap_map, *, threshold=DEFAULT_THRESHOLD,
                     util_ceiling=DEFAULT_CEILING, surcharge=DEFAULT_SURCHARGE):
    """dispatch-day 별 조희선 과적 감지 → flagged-date dict 리스트.

    조희선 실적재율 > threshold 인 날만 반환. util > util_ceiling 은 artifact=True 태깅
    (multi-run 합산 왜곡 — 실행 액션 아님). 박종성/이장훈 동일일 흡수 여력 + 경기 surcharge
    노출 포함. 차량 정원은 cap_map(live SSOT) 우선, 부재 시 FALLBACK_CAP.

    주의: surcharge_exposure 의 경기 판정은 region tier(GYEONGGI_REGIONS) 기반 *추정*이다.
    정산 SSOT(calc.calc_cho)는 수령인주소에 '경기' 문자열로 판정하므로, 판교/분당 등
    경기 토큰 없는 랜드마크는 region_classifier 가 tier2(경기)로 보면 실제 청구보다 과대계상될
    수 있다. read-only 권고 수치(건당 ₩30k 한도)이므로 'region-tier 추정'으로 표기해 투명화.
    """
    cho_cap = capacity_for(DRIVER_CHO, cap_map) or FALLBACK_CAP[DRIVER_CHO]
    park_cap = capacity_for(DRIVER_PARK, cap_map) or FALLBACK_CAP[DRIVER_PARK]
    lee_cap = capacity_for(DRIVER_LEE, cap_map) or FALLBACK_CAP[DRIVER_LEE]

    results = []
    for d in sorted(by_date):
        load = {DRIVER_CHO: 0.0, DRIVER_PARK: 0.0, DRIVER_LEE: 0.0}
        count = {DRIVER_CHO: 0, DRIVER_PARK: 0, DRIVER_LEE: 0}
        gyeonggi = {DRIVER_CHO: 0, DRIVER_PARK: 0, DRIVER_LEE: 0}
        for s in by_date[d]:
            drv = _match_driver(s.assigned_partner)
            if drv is None:
                continue
            load[drv] += s.cbm
            count[drv] += 1
            if s.region in GYEONGGI_REGIONS:
                gyeonggi[drv] += 1

        cho_util = load[DRIVER_CHO] / cho_cap if cho_cap else 0.0
        if cho_util <= threshold:
            continue

        overflow = max(0.0, load[DRIVER_CHO] - cho_cap)
        park_spare = max(0.0, park_cap - load[DRIVER_PARK])
        lee_spare = max(0.0, lee_cap - load[DRIVER_LEE])
        exposure = max(0, gyeonggi[DRIVER_CHO] - 1) * surcharge

        results.append({
            "date": d,
            "cho_load": round(load[DRIVER_CHO], 3),
            "cho_cap": round(cho_cap, 3),
            "cho_util": round(cho_util, 3),
            "cho_count": count[DRIVER_CHO],
            "cho_gyeonggi": gyeonggi[DRIVER_CHO],
            "surcharge_exposure": exposure,
            "park_load": round(load[DRIVER_PARK], 3),
            "park_spare": round(park_spare, 3),
            "lee_load": round(load[DRIVER_LEE], 3),
            "lee_spare": round(lee_spare, 3),
            "overflow_cbm": round(overflow, 3),
            "park_absorbs": park_spare >= overflow,
            "partial_absorbs": park_spare < overflow and (park_spare + lee_spare) >= overflow,
            "artifact": cho_util > util_ceiling,
        })
    return results


def format_alert(results, days) -> list[str]:
    """compute_overbook 결과 → Slack/CLI 텍스트 라인. 아티팩트는 별도 분리 표기."""
    actionable = [r for r in results if not r["artifact"]]
    artifacts = [r for r in results if r["artifact"]]

    if not actionable and not artifacts:
        return [
            "*배차 재분배 Alert (Chain C)*",
            f"기준: 향후 {days}일 · 조희선 과적 임계 {DEFAULT_THRESHOLD * 100:.0f}%",
            "조희선 과적 징후 없음 — 이상 없음",
        ]

    lines = [
        "*배차 재분배 Alert (Chain C)* — 조희선 용량 임박/과적 → 박종성/이장훈 흡수 권고",
        f"기준: 향후 {days}일 · dispatch-day 재구성(배차일지 stale) · 임계 {DEFAULT_THRESHOLD * 100:.0f}%",
        "",
    ]
    for r in actionable:
        # >100% = 과적(초과분), 95~100% = 용량 임박(안전마진 잔여)
        if r["overflow_cbm"] > 0:
            status = f"과적 — 초과 {r['overflow_cbm']:.2f}m³"
        else:
            remain = max(0.0, r["cho_cap"] - r["cho_load"])
            status = f"용량 임박 — 잔여 {remain:.2f}m³"
        lines.append(
            f"⚠️ {r['date']}  조희선 {r['cho_load']:.2f}/{r['cho_cap']:.2f}m³ "
            f"({r['cho_util'] * 100:.0f}%, {r['cho_count']}건) — {status}"
        )
        # 흡수 권고: 이장훈 우선(flat daily → 동일일 추가 stop 한계비용 ₩0, 단 비경기·오전한정),
        # 부족분 박종성(전 지역·경기 가능, 단 거리비례 신규요금). 실여유>0인 기사만 표기.
        helpers = []
        if r["lee_spare"] > 0:
            helpers.append(f"이장훈 여유 {r['lee_spare']:.2f}m³ (비경기 한계비용 ₩0)")
        if r["park_spare"] > 0:
            helpers.append(f"박종성 여유 {r['park_spare']:.2f}m³ (경기 가능·거리비례 요금)")
        absorb = " → ".join(helpers) if helpers else "흡수 여력 부족 (외주 RFQ 검토)"
        lines.append(f"    흡수: {absorb}")
        if r["surcharge_exposure"] > 0:
            lines.append(
                f"    경기 {r['cho_gyeonggi']}건 (surcharge ₩{r['surcharge_exposure']:,} 노출, region-tier 추정) "
                f"→ 박종성 이전 시 surcharge 절감(거리요금과 상쇄), 비경기분은 이장훈 ₩0"
            )
    if artifacts:
        lines.append("")
        lines.append(
            "_아티팩트(util>200%, multi-run 합산 의심 — 실행 액션 아님): "
            + ", ".join(r["date"] for r in artifacts) + "_"
        )
    return lines


def shipments_by_date(records) -> dict:
    """live Shipment records → {ship_date: [Shipment]} (운영자 실배정 assigned_partner 보존)."""
    by_date: dict[str, list] = defaultdict(list)
    for rec in records:
        s = _build_shipment(rec)
        if s is None:
            continue
        f = rec.get("fields", {})
        raw = _first(f.get(FLD_SHIP_DATE)) or f.get(FLD_SHIP_DATE) or ""
        d = str(raw)[:10]
        if d:
            by_date[d].append(s)
    return dict(by_date)


def send_slack(text: str) -> None:
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    user = os.environ.get("SLACK_DM_USER_ID", "")
    if not token or not user:
        print("[WARN] SLACK_BOT_TOKEN/SLACK_DM_USER_ID 미설정 — alert 발송 생략")
        return
    r = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {token}"},
        json={"channel": user, "text": text},
        timeout=10,
    )
    ok = r.json().get("ok", False)
    print(f"[SLACK] overbook alert {'발송 완료' if ok else '실패: ' + r.text}")


def main() -> None:
    parser = argparse.ArgumentParser(description="배차 재분배 overbook Alert (Chain C)")
    parser.add_argument("--days", type=int, default=14, help="향후 조회 일수")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help="조희선 과적 임계 (default 0.95)")
    parser.add_argument("--dry-run", action="store_true", help="Slack 발송 생략")
    args = parser.parse_args()

    today_iso = datetime.now(KST).isoformat()[:10]
    print(f"로딩: Shipment 자동대상 (향후 {args.days}일)...", flush=True)
    records = fetch_auto_targets(today_iso, rolling_days=args.days)
    print(f"  {len(records)}건 fetch", flush=True)

    cap_map = capacities_from_shipments(records)
    surcharge = rates_for(today_iso).get("cho_gyeonggi_surcharge", DEFAULT_SURCHARGE)
    by_date = shipments_by_date(records)
    results = compute_overbook(by_date, cap_map, threshold=args.threshold, surcharge=surcharge)

    actionable = [r for r in results if not r["artifact"]]
    n_artifact = len(results) - len(actionable)
    print(f"\n=== 배차 재분배 Alert (임계 {args.threshold * 100:.0f}%) ===")
    print(f"조희선 과적일: actionable {len(actionable)}건 / 아티팩트 {n_artifact}건")

    text = "\n".join(format_alert(results, args.days))
    print(text)

    if not actionable:
        return
    if args.dry_run:
        print("\n[DRY-RUN] Slack 발송 생략")
    else:
        send_slack(text)


if __name__ == "__main__":
    main()
