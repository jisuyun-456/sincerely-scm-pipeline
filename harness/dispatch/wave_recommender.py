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
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
from typing import Optional

from harness.dispatch.audit_log import log_event
from harness.dispatch.cbm_estimator import estimate_shipment_cbm
from harness.dispatch.change_detector import ChangeReport, detect
from harness.dispatch.otif_estimator import OtifResult, estimate_all, otif_summary_by_wave
from harness.dispatch.region_classifier import classify_region
from harness.dispatch.resource_loader import load_drivers, load_partners
from harness.dispatch.scheduling import is_quiet_hour, rolling_window_end
from harness.dispatch.slot_decider import decide_slot
from harness.dispatch.wave_assigner import (
    WAVE_IDS, Shipment, WavePlan, assign_waves, compute_utilization, CONFIDENCE_FLOOR,
)

# ─── Airtable config ──────────────────────────────────────────────────────────
BASE_ID = "app4x70a8mOrIKsMf"
SHIPMENT_TABLE = "tbllg1JoHclGYer7m"

# Field IDs (Shipment table — from schema_pin.json)
FLD_PROJECT_CODE = "fldTs3FzaSdGYEiKX"      # rollup
FLD_METHOD = "flduzH5tS7orqGG3o"            # rollup
FLD_SLOT = "fldcSrlxCngYQHtSV"              # singleSelect (배송슬롯)
FLD_ADDRESS = "fldyJHUh9gN44Ggnh"           # rollup (수령인주소)
FLD_HOPE_TIME = "fldFweNu3dASPv93N"         # rollup (고객 희망 수령 시간)
FLD_RECEIPT_CATEGORY = "fldqHPpgLRSIf7Aic"  # rollup (수령 시간 — CX 선택 singleSelect)
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

WAVE_DISPLAY = {
    "W1": "이장훈 기사님",
    "W2": "조희선 기사님",
    "W3": "박종성 기사님",
}

SNAPSHOT_PATH = os.environ.get("SNAPSHOT_PATH", "")


def _load_snapshot() -> dict:
    if not SNAPSHOT_PATH or not os.path.exists(SNAPSHOT_PATH):
        return {}
    with open(SNAPSHOT_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_snapshot(snapshot: dict) -> None:
    if DRY_RUN:
        return  # dry run 은 baseline 스냅샷을 오염시키지 않음 (다음 LIVE 가 신규건을 정상 감지)
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


def _patch(url: str, payload: dict, *, retries: int = 3) -> bool:
    """PATCH with 429/5xx 백오프 재시도. 성공 True / 영구실패 False (예외로 run 을 죽이지 않음)."""
    data = json.dumps(payload, ensure_ascii=False).encode()
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=_airtable_headers(), method="PATCH")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                r.read()
            return True
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read()[:200].decode("utf-8", "replace")
            except Exception:
                pass
            if e.code in (429, 500, 502, 503) and attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            print(f"[ERROR] PATCH {e.code}: {body}")
            return False
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            print(f"[ERROR] PATCH URLError: {e}")
            return False
    return False


import urllib.parse


def fetch_auto_targets(today_iso: str, rolling_days: int = 7) -> list[dict]:
    """Airtable Shipment → 자동 대상 필터링.

    필터:
    - project code NOT empty
    - 발송상태_TMS NOT IN 종료상태 ('출하 완료'·'진행 취소')
    - 출하확정일 설정됨 + [today, window_end] 영업일 rolling window (서버사이드 + Python 재확인)

    NOTE(2026-06-22): 발송상태_TMS 실제 옵션은 '출하 대기'·'출하 완료'·'진행 취소'·'이슈 발생'·
    'EMPTY'·'베스트원'. 과거 코드는 존재하지 않는 '발송완료/취소/반품/회수/배달완료'를 제외하려 해
    필터가 무효화 → 전체 이력(9900+건)을 매 실행 스캔하고 종료건도 재배차했다. 종료상태 2종만 제외하고
    날짜창을 서버사이드(IS_AFTER/IS_BEFORE, Airtable formula 는 field ID 지원)로 좁혀 수정.
    """
    window_end = rolling_window_end(date.fromisoformat(today_iso), rolling_days)
    window_end_iso = window_end.isoformat()

    formula = (
        "AND("
        f"NOT({{{FLD_PROJECT_CODE}}}=''),"
        f"NOT({{{FLD_STATUS}}}='출하 완료'),"
        f"NOT({{{FLD_STATUS}}}='진행 취소'),"
        f"{{{FLD_SHIP_DATE}}}!='',"
        f"IS_AFTER({{{FLD_SHIP_DATE}}}, DATEADD('{today_iso}', -1, 'days')),"
        f"IS_BEFORE({{{FLD_SHIP_DATE}}}, DATEADD('{window_end_iso}', 1, 'days'))"
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
    receipt_category = _first(f.get(FLD_RECEIPT_CATEGORY)) or ""
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

    slot, slot_conf = decide_slot(method, hope_time, receipt_category)
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
        method=method,
    )


# ─── Airtable PATCH ───────────────────────────────────────────────────────────

def _patch_batch(batch: list[dict]) -> bool:
    """batch 10건 PATCH → Shipment table. 성공 True / 실패 False."""
    if DRY_RUN:
        for rec in batch:
            print(f"  [DRY] PATCH {rec['id']}: {rec['fields']}")
        return True
    url = f"https://api.airtable.com/v0/{BASE_ID}/{SHIPMENT_TABLE}"
    return _patch(url, {"records": batch})


def patch_airtable(
    plans: dict[str, WavePlan],
    shipment_map: dict[str, Shipment],
    now_iso: str,
    current_slots: dict[str, Optional[str]] | None = None,
) -> list[dict]:
    """wave 추천 필드 + (조건부) 배송슬롯 → Airtable PATCH (batch 10). Returns diff list.

    운영자 소유 필드 보호 (2026-06-22):
    - wave_locked 는 운영자 *입력* 이므로 추천기가 절대 되쓰지 않는다 (PATCH 미포함).
    - 배송슬롯은 잠금 안 됐고 현재 셀이 비어있을 때만 추천값을 기입 — 운영자 수동 수정/잠금을
      매 cron 이 덮어쓰지 않도록. current_slots: {record_id: 현재 배송슬롯값}.
    """
    current_slots = current_slots or {}
    records_to_patch: list[dict] = []

    for wave_id, plan in plans.items():
        for s in plan.shipments:
            fields: dict = {
                FLD_WAVE_REC: WAVE_DISPLAY.get(wave_id, wave_id),
                FLD_WAVE_CONF: round(s.slot_confidence * s.cbm_confidence, 2),
                FLD_WAVE_UPDATED: now_iso,
            }
            if s.slot and not s.wave_locked and not current_slots.get(s.id):
                fields[FLD_SLOT] = s.slot
            rec = {"id": s.id, "fields": fields}
            records_to_patch.append(rec)

            if s.slot_confidence * s.cbm_confidence < CONFIDENCE_FLOOR:
                log_event("low_confidence_recommendation", {
                    "shipment_id": s.id,
                    "wave": wave_id,
                    "slot_conf": s.slot_confidence,
                    "cbm_conf": s.cbm_confidence,
                })

    # Batch 10 — 한 배치 실패가 나머지를 막지 않도록 (PATCH 는 매 cron 멱등 재시도되므로 자가복구).
    failures = 0
    for i in range(0, len(records_to_patch), 10):
        if not _patch_batch(records_to_patch[i:i + 10]):
            failures += 1
    if failures:
        print(f"[WARN] {failures}개 배치 PATCH 실패 — 다음 cron 에서 재시도(멱등)")

    return records_to_patch


# ─── Slack digest ─────────────────────────────────────────────────────────────

PENDING_DIGEST_PATH = "_AutoResearch/SCM/outputs/audit_log/pending_digest.json"


def _slack_post(text: str) -> bool:
    """Slack DM 발송. ok=False(만료토큰 등)는 HTTP 200 이라 body 의 ok 를 확인. 성공 True."""
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    user = os.environ.get("SLACK_DM_USER_ID", "")
    if not token or not user:
        print("[WARN] SLACK_BOT_TOKEN or SLACK_DM_USER_ID not set — skipping Slack")
        return False
    if DRY_RUN:
        print(f"[DRY] Slack → {user}: {text[:200]}")
        return True
    data = json.dumps({"channel": user, "text": text}).encode()
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            resp = json.loads(r.read() or b"{}")
    except Exception as e:
        print(f"[ERROR] Slack post 예외: {e}")
        return False
    if not resp.get("ok"):
        print(f"[ERROR] Slack post 실패: {resp.get('error')}")
        return False
    return True


def _format_digest(
    plans: dict[str, WavePlan],
    diff: list[dict],
    today_iso: str,
    change_report: "ChangeReport | None" = None,
    otif_summary: "dict | None" = None,
    n_dates: int = 1,
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
        display = WAVE_DISPLAY.get(wid, wid)
        u_total = util.get(wid, 0.0)
        if n_dates > 1:
            u_daily = u_total / n_dates
            cbm_label = f"{plan.total_cbm:.2f} CBM — 일평균 {u_daily:.0%} ({n_dates}일)"
        else:
            cbm_label = f"{plan.total_cbm:.2f} CBM ({u_total:.0%})"
        line = f"  {display}: {plan.count}건 / {cbm_label}"
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
    n_dates: int = 1,
) -> None:
    import pathlib
    pathlib.Path(PENDING_DIGEST_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(PENDING_DIGEST_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {"date": today_iso,
             "text": _format_digest(plans, diff, today_iso, change_report, otif_summary, n_dates)},
            f,
        )


def send_or_queue_digest(
    plans: dict[str, WavePlan],
    diff: list[dict],
    today_iso: str,
    change_report=None,
    otif_summary=None,
    n_dates: int = 1,
) -> None:
    now = datetime.now(KST)
    if is_quiet_hour(now):
        save_pending_digest(plans, diff, today_iso, change_report, otif_summary, n_dates)
        print(f"[INFO] quiet hours — digest queued for next cycle")
        return

    import pathlib
    pending = pathlib.Path(PENDING_DIGEST_PATH)
    if pending.exists():
        with open(pending, encoding="utf-8") as f:
            old = json.load(f)
        # 큐된 다이제스트는 *전송 성공* 시에만 삭제 (실패 시 다음 cycle 재시도 — 알림 유실 방지)
        if _slack_post(old.get("text", "")):
            pending.unlink()

    _slack_post(_format_digest(plans, diff, today_iso, change_report, otif_summary, n_dates))


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    today = datetime.now(KST)
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

    # Stage A: slot + region classification — group by ship_date
    date_to_shipments: dict[str, list[Shipment]] = defaultdict(list)
    for rec in raw_records:
        s = _build_shipment(rec)
        if not s:
            continue
        f = rec.get("fields", {})
        ship_date_raw = _first(f.get(FLD_SHIP_DATE)) or f.get(FLD_SHIP_DATE) or ""
        ship_date = ship_date_raw[:10]
        date_to_shipments[ship_date].append(s)

    shipments = [s for sl in date_to_shipments.values() for s in sl]
    print(f"  shipments built: {len(shipments)} across {len(date_to_shipments)} dates")

    # Stage B+C+D: wave assignment PER DATE (각 날짜 독립적으로 기사 용량 배정)
    plans: dict[str, WavePlan] = {wid: WavePlan(wid) for wid in WAVE_IDS}
    for ship_date in sorted(date_to_shipments):
        date_plans = assign_waves(date_to_shipments[ship_date], partner_autonomy, ship_date,
                                  confidence_floor=CONFIDENCE_FLOOR)
        for wid, plan in date_plans.items():
            plans[wid].shipments.extend(plan.shipments)

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
    # 분모 = 자동화 가능 모수 (autonomous 파트너로 드롭된 건 제외) = 전 plan 버킷 합.
    total_count = sum(p.count for p in plans.values())
    print(f"  automation: {automation_count}/{total_count} ({automation_count/total_count:.0%})" if total_count else "  no shipments")

    # Stage: PATCH + Slack
    shipment_map = {s.id: s for s in shipments}
    # 현재 배송슬롯값 — 비어있을 때만 추천값 기입 (운영자 수정 보호)
    current_slots = {rec["id"]: _first(rec.get("fields", {}).get(FLD_SLOT)) for rec in raw_records}
    diff = patch_airtable(plans, shipment_map, now_iso, current_slots)

    # Step 3: 가정 OTIF 추정
    otif_results = estimate_all(raw_records)
    otif_summary = otif_summary_by_wave(otif_results, plans)

    # Step 4: Slack 다이제스트 (변경 또는 wave 변동 시)
    has_changes = (
        change_report.added
        or change_report.removed
        or change_report.critical_modified
    )
    n_dates = max(1, len(date_to_shipments))
    if diff or has_changes:
        send_or_queue_digest(plans, diff, today_iso, change_report, otif_summary, n_dates)
    else:
        print("  no changes to report")

    # Step 5: 스냅샷 저장
    _save_snapshot(new_snapshot)
    print(f"  snapshot saved: {len(new_snapshot)} records")


if __name__ == "__main__":
    main()
