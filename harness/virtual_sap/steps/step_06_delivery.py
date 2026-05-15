"""Step 06 — TMS Shipment creation + POD simulation.

For each posted outbound_delivery without a shipment yet:
  - Group by customer region (Seoul/Gyeonggi → CA-0002 이장훈, others → CA-0001 로젠택배)
  - Create sap.shipment + sap.shipment_delivery_link
  - Simulate POD: 80% same-day delivered, 15% next-day, 5% exception
  - Insert shipment_event records (pickup + delivered/exception)
  - total_fare = total_cbm * 12000 KRW/CBM

Continuous mode: time gate outbound_delivery must be >30min old,
                 DLV_EXCEPTION (5% rate) recorded to sim_issue.

Inserts into: sap.shipment, sap.shipment_delivery_link, sap.shipment_event
"""
from __future__ import annotations

import random
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import TypedDict

from .. import supabase_client as db
from ..id_gen import next_id
from ..config import get_config
from .issue_injector import record_issue

logger = logging.getLogger(__name__)

SEOUL_GYEONGGI_REGIONS = {"Seoul", "서울", "Gyeonggi", "경기"}
CARRIER_REGIONAL = "CA-0002"   # 이장훈
CARRIER_DEFAULT = "CA-0001"    # 로젠택배

FARE_RATE_KRW_PER_CBM = 12_000


class SimContext(TypedDict):
    sim_run_id: str
    now_date: str
    now_ts: str
    is_continuous: bool
    dry_run: bool
    orders_count: int


@dataclass
class StepResult:
    step_name: str
    status: str
    docs_created: int
    issues: list[str] = field(default_factory=list)


def _get_carrier(customer_id: str) -> str:
    rows = db.select("business_partner", {"bp_id": customer_id}, columns="region", limit=1)
    if rows:
        region = rows[0].get("region", "")
        if region in SEOUL_GYEONGGI_REGIONS:
            return CARRIER_REGIONAL
    return CARRIER_DEFAULT


def run(sim_run_id: str, ctx: SimContext) -> StepResult:
    dry_run = get_config().dry_run
    now_date = date.fromisoformat(ctx["now_date"])
    issues: list[str] = []
    docs_created = 0

    seed = hash(sim_run_id + ctx["now_date"] + "delivery") & 0x7FFFFFFF
    rng = random.Random(seed)

    try:
        posted_dlvs = db.select(
            "outbound_delivery",
            {"goods_issue_status": "posted"},
            columns="dlv_id,so_id,total_cbm,created_at",
        )
        if not posted_dlvs:
            return StepResult("step_06_delivery", "skipped", 0, issues)

        # Continuous mode: time gate outbound must be > 30min old
        if ctx.get("is_continuous"):
            now_utc = datetime.fromisoformat(ctx["now_ts"])
            posted_dlvs = [
                d for d in posted_dlvs
                if d.get("created_at") and (
                    now_utc - datetime.fromisoformat(
                        d["created_at"].replace("Z", "+00:00")
                    )
                ) >= timedelta(minutes=30)
            ]
            if not posted_dlvs:
                logger.info("step_06_delivery: no outbound deliveries older than 30min")
                return StepResult("step_06_delivery", "skipped", 0, issues)

        linked = db.select("shipment_delivery_link", columns="dlv_id")
        already_linked = {row["dlv_id"] for row in linked}

        for dlv in posted_dlvs:
            dlv_id = dlv["dlv_id"]
            if dlv_id in already_linked:
                continue

            so_id = dlv["so_id"]
            total_cbm = float(dlv.get("total_cbm") or 0.0)

            so_rows = db.select("sales_order", {"so_id": so_id}, columns="customer_id", limit=1)
            customer_id = so_rows[0]["customer_id"] if so_rows else ""
            carrier_id = _get_carrier(customer_id)

            total_fare = round(total_cbm * FARE_RATE_KRW_PER_CBM, 2)

            roll = rng.random()
            if roll < 0.80:
                pod_outcome = "delivered"
                actual_delivery = now_date
            elif roll < 0.95:
                pod_outcome = "delivered"
                actual_delivery = now_date + timedelta(days=1)
            else:
                pod_outcome = "exception"
                actual_delivery = now_date + timedelta(days=1)
                msg = f"DLV_EXCEPTION: SH for DLV {dlv_id} — delivery exception, pod_status=exception"
                record_issue(db, sim_run_id, "ERROR", msg, dry_run, dim="D5")
                issues.append(msg)

            ship_id = next_id("SH", now_date, dry_run=dry_run)

            db.insert("shipment", {
                "ship_id": ship_id,
                "carrier_id": carrier_id,
                "planned_pickup": f"{now_date.isoformat()}T02:00:00",
                "actual_pickup": f"{now_date.isoformat()}T03:00:00",
                "actual_delivery": actual_delivery.isoformat(),
                "total_cbm": total_cbm,
                "total_fare": total_fare,
                "pod_status": pod_outcome,
                "sim_run_id": sim_run_id,
            }, dry_run=dry_run)

            db.insert("shipment_delivery_link", {
                "ship_id": ship_id,
                "dlv_id": dlv_id,
            }, dry_run=dry_run)

            db.insert("shipment_event", [
                {
                    "ship_id": ship_id,
                    "event_type": "pickup",
                    "event_ts": f"{now_date.isoformat()}T03:00:00",
                    "note": f"sim_run={sim_run_id}",
                },
                {
                    "ship_id": ship_id,
                    "event_type": pod_outcome,
                    "event_ts": actual_delivery.isoformat(),
                    "note": f"sim_run={sim_run_id}",
                },
            ], dry_run=dry_run)

            docs_created += 1
            logger.info("SH %s | DLV %s | carrier %s | pod=%s | fare=₩%.0f",
                        ship_id, dlv_id, carrier_id, pod_outcome, total_fare)

    except Exception as exc:
        issues.append(f"step_06_delivery failed: {exc}")
        logger.exception("step_06_delivery error")
        return StepResult("step_06_delivery", "failed", docs_created, issues)

    return StepResult("step_06_delivery", "ok", docs_created, issues)
