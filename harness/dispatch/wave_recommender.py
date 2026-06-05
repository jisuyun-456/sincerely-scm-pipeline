"""Sub-Spec 3 Main Entry — Wave 추천 엔진.

Pipeline:
1. fetch_auto_targets: Airtable Shipment → 자동 대상 필터 (project + 미발송 + 7일 rolling)
2. Stage A: decide_slot per shipment
3. Stage B+C+D: assign_waves (consolidation + priority + spillover + override)
4. Airtable PATCH (wave_recommendation + wave_confidence + wave_locked + 배송슬롯, batch 10)
5. Slack 다이제스트 (변경분 + quiet hours 준수)

DRY_RUN=true → PATCH 없이 log만 출력.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import date, datetime
from typing import Optional

from harness.dispatch.audit_log import log_event
from harness.dispatch.cbm_estimator import estimate_shipment_cbm
from harness.dispatch.change_detector import ChangeReport, detect
from harness.dispatch.otif_estimator import OtifResult, estimate_all, otif_summary_by_wave
from harness.dispatch.region_classifier import classify_region
from harness.dispatch.resource_loader import load_drivers, load_partners
from harness.dispatch.scheduling import is_quiet_hour, rolling_window_end
from harness.dispatch.slot_decider import decide_slot
from harness.dispatch.wave_assigner import Shipment, WavePlan, assign_waves, compute_utilization

# ─── Airtable config ──────────────────────────────────────────────────────────
BASE_ID = "app4x70a8mOrIKsMf"
SHIPMENT_TABLE = "tbllg1JoHclGYer7m"

# Field IDs (Shipment table — from schema_pin.json)
FLD_PROJECT_CODE = "fldTs3FzaSdGYEiKX"      # rollup
FLD_METHOD = "flduzH5tS7orqGG3o"            # rollup
FLD_SLOT = "fldcSrlxCngYQHtSV"              # singleSelect (배송슬롯)
FLD_ADDRESS = "fldyJHUh9gN44Ggnh"           # rollup (수령인주소)
FLD_HOPE_TIME = "fldFweNu3dASPv93N"         # rollup (고객 희망 수령 시간)
FLD_PARTNER = "fldHZ7yMT3KEu2gSj"          # lookup (배송파트너명)
FLD_STATUS = "fldOhibgxg6LIpRTi"            # singleSelect (발송상태_TMS)
FLD_SHIP_DATE = "fldQvmEwwzvQW95h9"         # date (출하확정일)
FLD_TOTAL_CBM = "fldJ9DHjwoRyeUEqE"         # number
FLD_EST_CBM = "fldaP8D9AM8CHEZ2o"           # number
FLD_EST_CONF = "fldUnFZ2ayjJbMW4I"          # number
FLD_WAVE_LOCKED = "fldfY2d54mffSHBEA"       # checkbox
FLD_WAVE_REC = "fld9hlDfnTS4frfR4"          # singleSelect (wave_recommendation)
FLD_WAVE_CONF = "fldkjKK1Fk1xsXj9Q"         # number (wave_confidence)
FLD_WAVE_UPDATED = "fld9YtjtpiOiZHJKu"      # dateTime (wave_updated_at)

# Statuses that indicate a shipment is already dispatched
SHIPPED_STATUSES = frozenset({"발송완료", "취소", "반품", "회수", "배달완료"})

DRY_RUN = os.environ.get("DRY_RUN", "").lower() in {"true", "1", "yes"}

SNAPSHOT_PATH = os.environ.get("SNAPSHOT_PATH", "")


def _load_snapshot() -> dict:
    if not SNAPSHOT_PATH or not os.path.exists(SNAPSHOT_PATH):
        return {}
    with open(SNAPSHOT_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_snapshot(snapshot: dict) -> None:
    if not SNAPSHOT_PATH:
        return
    import pathlib
    pathlib.Path(SNAPSHOT_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False)


# ─── Airtable helpers ─────────────────────────────────────────────────────────

def _airtable_headers() -> dict[str, str]:
    pat = os.environ.get("AIRTABLE_PAT", "")
    if not pat:
        raise RuntimeError("AIRTABLE_PAT 환경변수 필요")
    return {"Authorization": f"Bearer {pat}", "Content-Type": "application/json"}


def _get(url: str, params: dict) -> dict:
    qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
    full = f"{url}?{qs}" if qs else url
    req = urllib.request.Request(full, headers=_airtable_headers())
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _patch(url: str, payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=data, headers=_airtable_headers(), method="PATCH")
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()


import urllib.parse


def fetch_auto_targets(today_iso: str, rolling_days: int = 7) -> list[dict]:
    """Airtable Shipment → 자동 대상 필터링.

    필터:
    - project code NOT empty
    - 발송상태_TMS NOT IN SHIPPED_STATUSES
    - 출하확정일 설정됨 + within 7 business days (Python-side)
    """
    window_end = rolling_window_end(date.fromisoformat(today_iso), rolling_days)
    window_end_iso = window_end.isoformat()

    formula = (
        "AND("
        f"NOT({{{FLD_PROJECT_CODE}}}=''),"
        f"NOT({{{FLD_STATUS}}}='발송완료'),"
        f"NOT({{{FLD_STATUS}}}='취소'),"
        f"NOT({{{FLD_STATUS}}}='반품'),"
        f"NOT({{{FLD_STATUS}}}='회수'),"
        f"NOT({{{FLD_STATUS}}}='배달완료'),"
        f"{{{FLD_SHIP_DATE}}}!=''"
        ")"
    )

    url = f"https://api.airtable.com/v0/{BASE_ID}/{SHIPMENT_TABLE}"
    records: list[dict] = []
    offset = None

    while True:
        params: dict = {"pageSize": 100, "filterByFormula": formula, "returnFieldsByFieldId": "true"}
        if offset:
            params["offset"] = offset
        data = _get(url, params)
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break

    # Python-side: rolling window date filter
    result = []
    for rec in records:
        f = rec.get("fields", {})
        ship_date_raw = _first(f.get(FLD_SHIP_DATE)) or f.get(FLD_SHIP_DATE)
        if not ship_date_raw:
            continue
        ship_date = ship_date_raw[:10]  # YYYY-MM-DD
        if today_iso <= ship_date <= window_end_iso:
            result.append(rec)

    return result


def _first(val) -> Optional[str]:
    """multipleLookupValues or plain → first string value."""
    if isinstance(val, list):
        return val[0] if val else None
    return val


# ─── Shipment builder ─────────────────────────────────────────────────────────

def _build_shipment(rec: dict) -> Optional[Shipment]:
    """Airtable record → Shipment dataclass. None if skipped (wave_locked)."""
    f = rec.get("fields", {})
    record_id = rec.get("id", "")

    wave_locked = bool(f.get(FLD_WAVE_LOCKED))
    project_code = _first(f.get(FLD_PROJECT_CODE)) or ""
    method = _first(f.get(FLD_METHOD)) or ""
    hope_time = _first(f.get(FLD_HOPE_TIME)) or ""
    address = _first(f.get(FLD_ADDRESS)) or ""
    partner = _first(f.get(FLD_PARTNER)) or ""

    # CBM: Total_CBM (실측) > estimated_cbm (추정) > 0.5 (fallback)
    total_cbm = f.get(FLD_TOTAL_CBM) or 0.0
    est_cbm = f.get(FLD_EST_CBM) or 0.0
    est_conf = f.get(FLD_EST_CONF) or 0.0
    if total_cbm and total_cbm > 0:
        cbm, cbm_conf = float(total_cbm), 1.0
    elif est_cbm and est_cbm > 0:
        cbm, cbm_conf = float(est_cbm), float(est_conf) if est_conf else 0.7
    else:
        cbm, cbm_conf = 0.5, 0.3  # unknown fallback

    slot, slot_conf = decide_slot(method, hope_time)
    region = classify_region(address)

    return Shipment(
        id=record_id,
        project_code=project_code,
        slot=slot,
        region=region,
        cbm=cbm,
        cbm_confidence=cbm_conf,
        slot_confidence=slot_conf,
        assigned_partner=partner,
        wave_locked=wave_locked,
    )


# ─── Airtable PATCH ───────────────────────────────────────────────────────────

def _patch_batch(batch: list[dict]) -> None:
    """batch 10건 PATCH → Shipment table (wave 4 fields + 배송슬롯)."""
    if DRY_RUN:
        for rec in batch:
            print(f"  [DRY] PATCH {rec['id']}: {rec['fields']}")
        return
    url = f"https://api.airtable.com/v0/{BASE_ID}/{SHIPMENT_TABLE}"
    _patch(url, {"records": batch})


def patch_airtable(
    plans: dict[str, WavePlan],
    shipment_map: dict[str, Shipment],
    now_iso: str,
) -> list[dict]:
    """wave 4 fields + 배송슬롯 → Airtable PATCH (batch 10). Returns diff list."""
    records_to_patch: list[dict] = []

    for wave_id, plan in plans.items():
        for s in plan.shipments:
            rec = {
                "id": s.id,
                "fields": {
                    FLD_WAVE_REC: wave_id,
                    FLD_WAVE_CONF: round(s.slot_confidence * s.cbm_confidence, 2),
                    FLD_WAVE_LOCKED: s.wave_locked,
                    FLD_WAVE_UPDATED: now_iso,
                },
            }
            if s.slot:
                rec["fields"][FLD_SLOT] = s.slot
            records_to_patch.append(rec)

            if s.slot_confidence * s.cbm_confidence < 0.7:
                log_event("low_confidence_recommendation", {
                    "shipment_id": s.id,
                    "wave": wave_id,
                    "slot_conf": s.slot_confidence,
                    "cbm_conf": s.cbm_confidence,
                })

    # Batch 10
    for i in range(0, len(records_to_patch), 10):
        _patch_batch(records_to_patch[i:i + 10])

    return records_to_patch


# ─── Slack digest ─────────────────────────────────────────────────────────────

PENDING_DIGEST_PATH = "_AutoResearch/SCM/outputs/audit_log/pending_digest.json"


def _slack_post(text: str) -> None:
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    user = os.environ.get("SLACK_DM_USER_ID", "")
    if not token or not user:
        print("[WARN] SLACK_BOT_TOKEN or SLACK_DM_USER_ID not set — skipping Slack")
        return
    if DRY_RUN:
        print(f"[DRY] Slack → {user}: {text[:200]}")
        return
    data = json.dumps({"channel": user, "text": text}).encode()
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        r.read()


def _format_digest(
    plans: dict[str, WavePlan],
    diff: list[dict],
    today_iso: str,
    change_report: "ChangeReport | None" = None,
    otif_summary: "dict | None" = None,
) -> str:
    util = compute_utilization(plans)
    lines = [f"*Wave 추천 엔진 다이제스트 — {today_iso}*"]

    if change_report and (change_report.added or change_report.removed or change_report.critical_modified):
        parts = []
        if change_report.added:
            parts.append(f"🆕 신규 {len(change_report.added)}건")
        if change_report.removed:
            parts.append(f"🚫 완료/취소 {len(change_report.removed)}건")
        if change_report.critical_modified:
            parts.append(f"⚠️ 변경 {len(change_report.critical_modified)}건")
        lines.append("  " + " | ".join(parts))

    for wid in ("W1", "W2", "W3"):
        plan = plans[wid]
        u = util.get(wid, 0.0)
        line = f"  {wid}: {plan.count}건 / {plan.total_cbm:.2f} CBM ({u:.0%})"
        if otif_summary and wid in otif_summary:
            s = otif_summary[wid]
            line += f" — 납기 {s['on_time']}/{s['total']}건 ✅"
            if s["at_risk"]:
                line += f" / {s['at_risk']}건 ⚠️"
        lines.append(line)

    for wid in ("spillover_고고엑스", "spillover_로젠", "수동"):
        cnt = plans[wid].count
        if cnt:
            lines.append(f"  {wid}: {cnt}건")
    lines.append(f"  총 추천: {len(diff)}건")
    return "\n".join(lines)


def save_pending_digest(
    plans: dict[str, WavePlan],
    diff: list[dict],
    today_iso: str,
    change_report=None,
    otif_summary=None,
) -> None:
    import pathlib
    pathlib.Path(PENDING_DIGEST_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(PENDING_DIGEST_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {"date": today_iso,
             "text": _format_digest(plans, diff, today_iso, change_report, otif_summary)},
            f,
        )


def send_or_queue_digest(
    plans: dict[str, WavePlan],
    diff: list[dict],
    today_iso: str,
    change_report=None,
    otif_summary=None,
) -> None:
    now = datetime.now()
    if is_quiet_hour(now):
        save_pending_digest(plans, diff, today_iso, change_report, otif_summary)
        print(f"[INFO] quiet hours — digest queued for next cycle")
        return

    import pathlib
    pending = pathlib.Path(PENDING_DIGEST_PATH)
    if pending.exists():
        with open(pending, encoding="utf-8") as f:
            old = json.load(f)
        _slack_post(old.get("text", ""))
        pending.unlink()

    _slack_post(_format_digest(plans, diff, today_iso, change_report, otif_summary))


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    today = datetime.now()
    today_iso = today.isoformat()[:10]
    now_iso = today.isoformat()

    print(f"[wave_recommender] {today_iso} {'DRY_RUN' if DRY_RUN else 'LIVE'}")

    # Step 1: 스냅샷 로드
    snapshot = _load_snapshot()
    print(f"  snapshot loaded: {len(snapshot)} records")

    # Load partner autonomy map
    partners = load_partners()
    partner_autonomy = {
        p.get("배송파트너", ""): p.get("autonomy_level", "unknown")
        for p in partners
        if p.get("배송파트너")
    }

    # Stage 0: fetch auto targets
    raw_records = fetch_auto_targets(today_iso, rolling_days=10)
    print(f"  auto_targets fetched: {len(raw_records)}")

    # Step 2: Change Detection
    change_report, new_snapshot = detect(snapshot, raw_records)
    print(f"  changes: +{len(change_report.added)} ~{len(change_report.critical_modified)} -{len(change_report.removed)}")

    # Stage A: slot + region classification
    shipments: list[Shipment] = []
    for rec in raw_records:
        s = _build_shipment(rec)
        if s:
            shipments.append(s)

    print(f"  shipments built: {len(shipments)}")

    # Stage B+C+D: wave assignment
    plans = assign_waves(shipments, partner_autonomy, today_iso)

    # Summary
    util = compute_utilization(plans)
    for wid in ("W1", "W2", "W3"):
        plan = plans[wid]
        print(f"  {wid}: {plan.count}건 / {plan.total_cbm:.2f} CBM ({util.get(wid, 0):.0%})")
    for wid in ("spillover_고고엑스", "spillover_로젠", "locked-in", "수동"):
        cnt = plans[wid].count
        if cnt:
            print(f"  {wid}: {cnt}건")

    automation_count = sum(plans[w].count for w in ("W1", "W2", "W3"))
    total_count = len(shipments)
    print(f"  automation: {automation_count}/{total_count} ({automation_count/total_count:.0%})" if total_count else "  no shipments")

    # Stage: PATCH + Slack
    shipment_map = {s.id: s for s in shipments}
    diff = patch_airtable(plans, shipment_map, now_iso)

    # Step 3: 가정 OTIF 추정
    otif_results = estimate_all(raw_records)
    otif_summary = otif_summary_by_wave(otif_results, plans)

    # Step 4: Slack 다이제스트 (변경 또는 wave 변동 시)
    has_changes = (
        change_report.added
        or change_report.removed
        or change_report.critical_modified
    )
    if diff or has_changes:
        send_or_queue_digest(plans, diff, today_iso, change_report, otif_summary)
    else:
        print("  no changes to report")

    # Step 5: 스냅샷 저장
    _save_snapshot(new_snapshot)
    print(f"  snapshot saved: {len(new_snapshot)} records")


if __name__ == "__main__":
    main()
