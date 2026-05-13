"""Phase C — 배차 추천 에이전트 (Dispatch Advisor).

Runs daily at 08:00 KST. Looks at GI-posted deliveries without a shipment yet
and recommends carrier allocation based on CBM + customer delivery distance.

Carrier roster:
  In-house drivers (신시어리, 수도권, max 7.6 m³/run):
    CA-0002  이장훈 기사 (자차)
    CA-0003  박종성 기사 (자차)
    CA-0004  김민준 기사 (자차)

  TMS partners:
    CA-0005  퀵서비스 바로고   (수도권, < 0.3 m³, ~20km, flat ₩15,000/건)
    CA-0001  로젠택배          (전국, ₩12,000/CBM)

Routing rules (priority order):
  1. region=수도권 AND cbm < 0.3  → 퀵 (CA-0005)
  2. region=수도권 AND cbm ≤ 7.6  → in-house driver (round-robin, fill to 7.6 m³)
  3. else (지방 or cbm > 7.6)    → 로젠택배 (CA-0001)

Distance lookup by region:
  수도권(서울/경기/인천): 20 km
  충청/강원:             200 km
  경상/전라/제주:         400 km
  기타:                  150 km
"""
from __future__ import annotations

import logging
import os
import sys
import json
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

if __name__ == "__main__" and __package__ is None:
    import pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))
    __package__ = "harness.virtual_sap.agents"

from .. import supabase_client as db
from ..config import get_config

logger = logging.getLogger(__name__)

AGENT_NAME = "배차추천"

# In-house driver config: (carrier_id, display_name, max_cbm_per_run)
INHOUSE_DRIVERS = [
    ("CA-0002", "이장훈", 7.6),
    ("CA-0003", "박종성", 7.6),
    ("CA-0004", "김민준", 7.6),
]

QUICK_CARRIER = ("CA-0005", "퀵(바로고)", 0.3)   # max CBM for quick
PARCEL_CARRIER = ("CA-0001", "로젠택배", float("inf"))

QUICK_FLAT_FARE = 15_000    # KRW per shipment
PARCEL_FARE_PER_CBM = 12_000

METRO_REGIONS = {"서울", "Seoul", "경기", "Gyeonggi", "인천", "Incheon", "수도권"}


def _estimate_distance_km(region: str) -> int:
    """Rough km estimate from warehouse to delivery region."""
    r = region.strip()
    if r in METRO_REGIONS:
        return 20
    if any(k in r for k in ("충청", "강원", "Chungcheong", "Gangwon")):
        return 200
    if any(k in r for k in ("경상", "전라", "제주", "Gyeongsang", "Jeolla", "Jeju")):
        return 400
    return 150


def _is_metro(region: str) -> bool:
    return region.strip() in METRO_REGIONS


@dataclass
class DriverLoad:
    carrier_id: str
    name: str
    max_cbm: float
    assigned_cbm: float = 0.0
    deliveries: list[str] = field(default_factory=list)

    @property
    def remaining_cbm(self) -> float:
        return self.max_cbm - self.assigned_cbm

    def can_take(self, cbm: float) -> bool:
        return cbm <= self.remaining_cbm


@dataclass
class Allocation:
    dlv_id: str
    so_id: str
    cbm: float
    region: str
    distance_km: int
    carrier_id: str
    carrier_name: str
    reason: str


def _allocate(pending: list[dict], customer_regions: dict[str, str]) -> list[Allocation]:
    """Allocate deliveries to carriers using CBM+distance rules."""
    drivers = [DriverLoad(cid, name, cap) for cid, name, cap in INHOUSE_DRIVERS]
    allocations: list[Allocation] = []

    # Sort: metro small CBM first (prefer in-house), then the rest
    def sort_key(d: dict) -> tuple:
        region = customer_regions.get(d["so_id"], "")
        cbm = float(d.get("total_cbm") or 0.0)
        metro = 0 if _is_metro(region) else 1
        return (metro, cbm)

    for dlv in sorted(pending, key=sort_key):
        dlv_id = dlv["dlv_id"]
        so_id = dlv["so_id"]
        cbm = float(dlv.get("total_cbm") or 0.0)
        region = customer_regions.get(so_id, "")
        distance_km = _estimate_distance_km(region)
        metro = _is_metro(region)

        # Rule 1: Quick for metro tiny packages
        if metro and cbm < QUICK_CARRIER[2]:
            allocations.append(Allocation(
                dlv_id=dlv_id, so_id=so_id, cbm=cbm,
                region=region, distance_km=distance_km,
                carrier_id=QUICK_CARRIER[0], carrier_name=QUICK_CARRIER[1],
                reason=f"수도권 소형({cbm:.3f}m³<{QUICK_CARRIER[2]}m³) → 퀵",
            ))
            continue

        # Rule 2: In-house driver for metro ≤ 7.6 m³
        if metro:
            assigned = False
            for driver in drivers:
                if driver.can_take(cbm):
                    driver.assigned_cbm += cbm
                    driver.deliveries.append(dlv_id)
                    allocations.append(Allocation(
                        dlv_id=dlv_id, so_id=so_id, cbm=cbm,
                        region=region, distance_km=distance_km,
                        carrier_id=driver.carrier_id, carrier_name=driver.name,
                        reason=f"수도권 자차({cbm:.3f}m³) → {driver.name}",
                    ))
                    assigned = True
                    break
            if assigned:
                continue

        # Rule 3: Parcel (로젠택배) — fallback for 지방 or overflow
        reason = (
            f"지방({region}, {distance_km}km)"
            if not metro
            else f"자차 용량 초과({cbm:.3f}m³) → 로젠"
        )
        allocations.append(Allocation(
            dlv_id=dlv_id, so_id=so_id, cbm=cbm,
            region=region, distance_km=distance_km,
            carrier_id=PARCEL_CARRIER[0], carrier_name=PARCEL_CARRIER[1],
            reason=reason,
        ))

    return allocations


def _estimate_fare(alloc: Allocation) -> float:
    if alloc.carrier_id == QUICK_CARRIER[0]:
        return float(QUICK_FLAT_FARE)
    return round(alloc.cbm * PARCEL_FARE_PER_CBM, 2)


def _log_agent_event(target_id: str | None, status: str, message: str,
                     dry_run: bool) -> None:
    db.insert("sim_agent_event", {
        "agent_name": AGENT_NAME,
        "target_id": target_id,
        "status": status,
        "message": message,
        "sim_run_id": None,
    }, dry_run=dry_run)


def _slack_notify(text: str) -> None:
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    user = os.environ.get("SLACK_DM_USER_ID", "")
    if not token or not user:
        return
    body = json.dumps({"channel": user, "text": text}).encode()
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
        if not result.get("ok"):
            logger.warning("Slack error: %s", result.get("error"))
    except Exception as exc:
        logger.warning("Slack notify failed: %s", exc)


def run() -> int:
    """Generate dispatch recommendations. Returns count of deliveries allocated."""
    cfg = get_config()
    dry_run = cfg.dry_run

    # GI-posted deliveries that don't have a shipment yet
    posted_dlvs = db.select(
        "outbound_delivery",
        {"goods_issue_status": "posted"},
        columns="dlv_id, so_id, total_cbm",
    )
    if not posted_dlvs:
        logger.info("%s: no GI-posted deliveries", AGENT_NAME)
        return 0

    linked = db.select("shipment_delivery_link", columns="dlv_id")
    already_shipped = {row["dlv_id"] for row in linked}
    pending = [d for d in posted_dlvs if d["dlv_id"] not in already_shipped]

    if not pending:
        logger.info("%s: all GI deliveries already have shipments", AGENT_NAME)
        return 0

    # Already recommended (avoid duplicate advice)
    prior = db.select(
        "sim_agent_event",
        {"agent_name": AGENT_NAME},
        columns="target_id",
    )
    already_recommended = {row["target_id"] for row in prior if row.get("target_id")}
    pending = [d for d in pending if d["dlv_id"] not in already_recommended]

    if not pending:
        logger.info("%s: all pending deliveries already have recommendations", AGENT_NAME)
        return 0

    # Lookup customer region for each SO
    so_ids = list({d["so_id"] for d in pending})
    customer_regions: dict[str, str] = {}
    for so_id in so_ids:
        so_rows = db.select("sales_order", {"so_id": so_id},
                            columns="so_id, customer_id", limit=1)
        if so_rows:
            cust_id = so_rows[0]["customer_id"]
            bp_rows = db.select("business_partner", {"bp_id": cust_id},
                                columns="region", limit=1)
            region = bp_rows[0].get("region", "") if bp_rows else ""
            customer_regions[so_id] = region

    allocations = _allocate(pending, customer_regions)

    # Summarize by carrier
    by_carrier: dict[str, list[Allocation]] = {}
    for a in allocations:
        by_carrier.setdefault(a.carrier_name, []).append(a)

    # Log and record
    lines: list[str] = []
    total_fare = 0.0

    for carrier_name, allocs in sorted(by_carrier.items()):
        count = len(allocs)
        cbm_total = sum(a.cbm for a in allocs)
        fare_total = sum(_estimate_fare(a) for a in allocs)
        total_fare += fare_total
        line = (f"{carrier_name}: {count}건 ({cbm_total:.3f}m³) "
                f"≈ ₩{fare_total:,.0f}")
        lines.append(line)
        logger.info("[%s] %s", AGENT_NAME, line)

        for a in allocs:
            _log_agent_event(
                target_id=a.dlv_id,
                status="ok",
                message=(
                    f"DLV {a.dlv_id} → {a.carrier_name} | "
                    f"{a.cbm:.4f}m³ | {a.distance_km}km | {a.reason}"
                ),
                dry_run=dry_run,
            )

    # Summary event
    _log_agent_event(
        target_id=None,
        status="ok",
        message=(
            f"배차추천 완료: {len(allocations)}건 총 {sum(a.cbm for a in allocations):.3f}m³ "
            f"≈ ₩{total_fare:,.0f} | " + " / ".join(lines)
        ),
        dry_run=dry_run,
    )

    # Slack DM
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    _slack_notify(
        f"🚛 *배차 추천* ({ts})\n"
        + "\n".join(f"  • {ln}" for ln in lines)
        + f"\n  *총 ≈ ₩{total_fare:,.0f}* / {len(allocations)}건"
    )

    return len(allocations)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    count = run()
    print(f"{AGENT_NAME}: {count} allocation(s) recommended")
    sys.exit(0)
