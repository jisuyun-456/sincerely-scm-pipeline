"""
Sincerely WMS -- Monthly Inbound / QC / Material Report
Slack DM: previous calendar month
"""

import os, sys, json, time
from datetime import date, datetime, timedelta
from collections import defaultdict

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests

# ── Env ──────────────────────────────────────────────────────────────────────
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY_WMS") or os.environ.get("AIRTABLE_PAT", "")
WMS_BASE_ID      = os.environ.get("AIRTABLE_BASE_WMS_ID") or os.environ.get("AIRTABLE_BASE_ID", "appLui4ZR5HWcQRri")
SLACK_TOKEN      = os.environ.get("SLACK_BOT_TOKEN", "")
DM_USER_ID       = os.environ.get("SLACK_DM_USER_ID", "")

SKIP_DELAY = os.environ.get("SKIP_DELAY", "0") == "1"

# ── Airtable Table / Field IDs ───────────────────────────────────────────────
TABLE_MOVEMENT = "tblwq7Kj5Y9nVjlOw"
TABLE_MATERIAL = "tblaRpZstW10EwDlo"

F_PURPOSE    = "fldFRNxG1pNooEOC7"
F_IN_QTY     = "fldV8kVokQqMIsif0"
F_IN_DATE    = "flduN8khmYwdn7uVD"
F_IN_STATUS  = "fld4Yq9LYX46zC5m5"
F_STOCK_QTY  = "fldlJt3RPY6E8JB4G"
F_CARTON     = "fldnZzmXrg3zTOSVe"
F_QC_QTY     = "fldnrqmT56niE7O21"
F_DEFECT_S   = "fld3lQvblfrqTl4O8"
F_DEFECT_F   = "fldsTXzxUeerw4qw2"
F_QC_RES     = "fldKrjj58HnHKT4SJ"
F_CANCEL     = "fldwgaM8OnKubM8oE"

F_MAT_NAME   = "fld7Pfip5zbBTaTdR"
F_MAT_PHYS   = "fld5XQQv2P9YJZP6n"
F_MAT_SYS    = "fldAFkM4HtGJsitOk"
F_MAT_AVAIL  = "fldZ5qLZKp0yy28So"
F_MAT_LOC    = "fldsDSdkogmJ0qsVC"
F_MAT_CHECK  = "flddQhs9cuA6G8xmq"

MOVEMENT_FIELDS = [
    F_PURPOSE, F_IN_QTY, F_IN_DATE, F_IN_STATUS, F_STOCK_QTY,
    F_CARTON, F_QC_QTY, F_DEFECT_S, F_DEFECT_F, F_QC_RES, F_CANCEL
]
MATERIAL_FIELDS = [
    F_MAT_NAME, F_MAT_PHYS, F_MAT_SYS, F_MAT_AVAIL, F_MAT_LOC, F_MAT_CHECK
]

# ── 날짜 헬퍼 ────────────────────────────────────────────────────────────────
def prev_month_range():
    today = date.today()
    first_this = today.replace(day=1)
    last_prev  = first_this - timedelta(days=1)
    first_prev = last_prev.replace(day=1)
    return first_prev, last_prev

# ── Airtable 조회 ────────────────────────────────────────────────────────────
def _airtable_headers():
    return {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }

def fetch_movement(start: date, end: date) -> list:
    url = f"https://api.airtable.com/v0/{WMS_BASE_ID}/{TABLE_MOVEMENT}"
    formula = (
        f"AND("
        f"IS_AFTER({{{F_IN_DATE}}}, DATEADD('{start.isoformat()}', -1, 'days')), "
        f"IS_BEFORE({{{F_IN_DATE}}}, DATEADD('{end.isoformat()}', 1, 'days'))"
        f")"
    )
    field_params = "&".join(f"fields[]={fid}" for fid in MOVEMENT_FIELDS)
    all_records = []
    offset = None
    while True:
        params = {
            "filterByFormula": formula,
            "pageSize": "100",
            "returnFieldsByFieldId": "true",
        }
        if offset:
            params["offset"] = offset
        resp = requests.get(
            f"{url}?{field_params}",
            headers=_airtable_headers(),
            params=params,
            timeout=30,
        )
        if resp.status_code == 429:
            time.sleep(30)
            continue
        resp.raise_for_status()
        data = resp.json()
        all_records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        if not SKIP_DELAY:
            time.sleep(0.22)
    return all_records

def fetch_material() -> list:
    url = f"https://api.airtable.com/v0/{WMS_BASE_ID}/{TABLE_MATERIAL}"
    field_params = "&".join(f"fields[]={fid}" for fid in MATERIAL_FIELDS)
    all_records = []
    offset = None
    while True:
        params = {"pageSize": "100", "returnFieldsByFieldId": "true"}
        if offset:
            params["offset"] = offset
        resp = requests.get(
            f"{url}?{field_params}",
            headers=_airtable_headers(),
            params=params,
            timeout=30,
        )
        if resp.status_code == 429:
            time.sleep(30)
            continue
        resp.raise_for_status()
        data = resp.json()
        all_records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        if not SKIP_DELAY:
            time.sleep(0.22)
    return all_records

# ── 분석 함수 ────────────────────────────────────────────────────────────────
def _select_name(val):
    if isinstance(val, dict):
        return val.get("name", "")
    return str(val) if val else ""

def analyze_inbound(records: list) -> dict:
    total_cnt      = len(records)
    total_in_qty   = 0
    total_stock_qty = 0
    completed      = 0
    unconfirmed    = 0
    by_week        = defaultdict(lambda: {"cnt": 0, "in_qty": 0})
    by_purpose     = defaultdict(lambda: {"cnt": 0, "qty": 0})

    for r in records:
        c = r.get("cellValuesByFieldId", {})
        in_qty    = c.get(F_IN_QTY) or 0
        stock_qty = c.get(F_STOCK_QTY) or 0
        date_val  = c.get(F_IN_DATE, "")
        stat      = _select_name(c.get(F_IN_STATUS, {}))
        purpose   = _select_name(c.get(F_PURPOSE, {})) or "미분류"

        total_in_qty   += in_qty
        total_stock_qty += stock_qty

        if stat == "입하완료":
            completed += 1
        elif not stat:
            unconfirmed += 1

        if date_val:
            try:
                d = datetime.strptime(date_val, "%Y-%m-%d")
                w = d.isocalendar()[1]
                week_key = f"{d.year}-W{w:02d} ({d.strftime('%m/%d')}~)"
            except Exception:
                week_key = "기타"
            by_week[week_key]["cnt"]    += 1
            by_week[week_key]["in_qty"] += in_qty

        by_purpose[purpose]["cnt"] += 1
        by_purpose[purpose]["qty"] += in_qty

    return {
        "total_cnt":       total_cnt,
        "total_in_qty":    total_in_qty,
        "total_stock_qty": total_stock_qty,
        "completed":       completed,
        "unconfirmed":     unconfirmed,
        "completion_rate": round(completed / total_cnt * 100, 1) if total_cnt else 0,
        "by_week":         dict(sorted(by_week.items())),
        "by_purpose":      dict(sorted(by_purpose.items(), key=lambda x: -x[1]["cnt"])),
    }

def analyze_qc(records: list) -> dict:
    qc_records = [
        r for r in records
        if (r.get("cellValuesByFieldId", {}).get(F_QC_QTY) or 0) > 0
        or r.get("cellValuesByFieldId", {}).get(F_QC_RES)
    ]
    total_qc_qty   = 0
    total_defect   = 0
    qc_result_dist = defaultdict(int)
    by_week_defect = defaultdict(lambda: {"qc": 0, "defect": 0})

    for r in qc_records:
        c = r.get("cellValuesByFieldId", {})
        qc_qty   = c.get(F_QC_QTY) or 0
        defect_s = c.get(F_DEFECT_S) or 0
        defect_f = c.get(F_DEFECT_F) or 0
        defect   = defect_s + defect_f
        res      = _select_name(c.get(F_QC_RES, {}))
        date_val = c.get(F_IN_DATE, "")

        total_qc_qty += qc_qty
        total_defect += defect
        if res:
            qc_result_dist[res] += 1

        if date_val:
            try:
                d = datetime.strptime(date_val, "%Y-%m-%d")
                w = d.isocalendar()[1]
                week_key = f"W{w:02d}"
            except Exception:
                week_key = "기타"
            by_week_defect[week_key]["qc"]     += qc_qty
            by_week_defect[week_key]["defect"] += defect

    defect_rate = round(total_defect / total_qc_qty * 100, 2) if total_qc_qty else 0.0

    return {
        "qc_cnt":         len(qc_records),
        "total_qc_qty":   total_qc_qty,
        "total_defect":   total_defect,
        "defect_rate":    defect_rate,
        "result_dist":    dict(qc_result_dist),
        "by_week_defect": dict(sorted(by_week_defect.items())),
        "target_met":     defect_rate <= 1.0,
    }

def analyze_material(records: list) -> dict:
    has_stock = [
        r for r in records
        if (r.get("cellValuesByFieldId", {}).get(F_MAT_PHYS) or 0) > 0
    ]
    total       = len(has_stock)
    match       = 0
    mismatch_list = []
    neg_avail   = 0
    check_done  = 0
    total_phys  = 0
    total_avail = 0

    for r in has_stock:
        c = r.get("cellValuesByFieldId", {})
        name  = c.get(F_MAT_NAME, "")
        phys  = c.get(F_MAT_PHYS) or 0
        sys_  = c.get(F_MAT_SYS) or 0
        avail = c.get(F_MAT_AVAIL) or 0
        loc   = c.get(F_MAT_LOC, "")
        chk   = _select_name(c.get(F_MAT_CHECK, {}))

        total_phys  += phys
        total_avail += avail

        if phys == sys_:
            match += 1
        else:
            diff = phys - sys_
            mismatch_list.append((abs(diff), name, phys, sys_, diff, str(loc)[:12]))

        if avail < 0:
            neg_avail += 1
        if chk:
            check_done += 1

    mismatch_list.sort(reverse=True)
    accuracy = round(match / total * 100, 1) if total else 0.0

    return {
        "total":        total,
        "accuracy":     accuracy,
        "mismatch":     len(mismatch_list),
        "neg_avail":    neg_avail,
        "check_done":   check_done,
        "total_phys":   total_phys,
        "total_avail":  total_avail,
        "top_mismatch": mismatch_list[:5],
    }

# ── Slack Block 빌더 ─────────────────────────────────────────────────────────
def _bar(value: int, max_val: int, width: int = 12) -> str:
    if max_val == 0:
        return "-" * width
    filled = round(value / max_val * width)
    return "[" + "#" * filled + "-" * (width - filled) + "]"

def _num(n) -> str:
    if n is None:
        return "0"
    return f"{int(n):,}"

def build_blocks(inbound: dict, qc: dict, mat: dict, month_label: str) -> list:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M KST")
    blocks = []

    # ── 1. 헤더 ──
    blocks.append({
        "type": "header",
        "text": {"type": "plain_text", "text": f"WMS 월간 리포트  {month_label}"}
    })
    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": f"생성: {now_str}"}]
    })
    blocks.append({"type": "divider"})

    # ── 2. 입고 월간 요약 ──
    compl_rate = inbound["completion_rate"]
    compl_icon = "✅" if compl_rate >= 95 else ("⚠️" if compl_rate >= 80 else "❌")

    purpose_lines = []
    for p, v in list(inbound["by_purpose"].items())[:6]:
        purpose_lines.append(f"  • {p}: {_num(v['cnt'])}건 / {_num(v['qty'])}개")
    purpose_text = "\n".join(purpose_lines) or "  (데이터 없음)"

    # 주차별 바 차트
    by_week = inbound["by_week"]
    max_qty  = max((v["in_qty"] for v in by_week.values()), default=1)
    week_lines = []
    for wk, v in sorted(by_week.items()):
        bar = _bar(v["in_qty"], max_qty, 10)
        week_lines.append(f"  {wk[:8]}  {bar}  {_num(v['in_qty'])}개 ({v['cnt']}건)")
    week_chart = "\n".join(week_lines) or "  (입하 없음)"

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": (
            f"*📦 입고 월간 현황*\n"
            f"  총 입하건수: *{_num(inbound['total_cnt'])}건*   "
            f"총 입하수량: *{_num(inbound['total_in_qty'])}개*\n"
            f"  입고수량: {_num(inbound['total_stock_qty'])}개   "
            f"입하완료율: {compl_icon} {compl_rate}%   "
            f"미확인: {inbound['unconfirmed']}건\n\n"
            f"*이동목적별*\n{purpose_text}\n\n"
            f"*주차별 입하수량 추이*\n{week_chart}"
        )}
    })
    blocks.append({"type": "divider"})

    # ── 3. 검수 월간 요약 ──
    defect_rate = qc["defect_rate"]
    defect_icon = "✅" if defect_rate <= 1.0 else ("⚠️" if defect_rate <= 3.0 else "❌")

    # 주차별 불량 추이
    week_defect_lines = []
    for wk, v in sorted(qc["by_week_defect"].items()):
        rate = round(v["defect"] / v["qc"] * 100, 1) if v["qc"] > 0 else 0
        flag = "✅" if rate <= 1.0 else ("⚠️" if rate <= 3.0 else "❌")
        week_defect_lines.append(
            f"  {wk}  검수:{_num(v['qc'])}개  불량:{_num(v['defect'])}개  ({rate}%) {flag}"
        )
    week_defect_text = "\n".join(week_defect_lines) or "  (검수 데이터 없음)"

    result_lines = "\n".join(
        f"  • {k}: {v}건" for k, v in qc["result_dist"].items()
    ) or "  (데이터 없음)"

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": (
            f"*🔍 검수 월간 현황*\n"
            f"  검수 건수: *{_num(qc['qc_cnt'])}건*   "
            f"검수 수량: {_num(qc['total_qc_qty'])}개\n"
            f"  불량 수량: {_num(qc['total_defect'])}개   "
            f"불량률: {defect_icon} *{defect_rate}%*  (목표 ≤1.0%)\n\n"
            f"*주차별 불량 추이*\n{week_defect_text}\n\n"
            f"*수량검수결과 분포*\n{result_lines}"
        )}
    })
    blocks.append({"type": "divider"})

    # ── 4. 자재 재고 ──
    acc_icon  = "✅" if mat["accuracy"] >= 99.5 else ("⚠️" if mat["accuracy"] >= 95 else "❌")
    avail_icon = "✅" if mat["neg_avail"] == 0 else "⚠️"
    mismatch_lines = []
    for _, name, phys, sys_, diff, loc in mat["top_mismatch"]:
        sign = "+" if diff > 0 else ""
        mismatch_lines.append(
            f"  • {str(name)[:18]:18s}  실물:{_num(phys)} / 전산:{_num(sys_)}  ({sign}{diff})  [{loc}]"
        )
    mismatch_text = "\n".join(mismatch_lines) or "  불일치 없음"

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": (
            f"*📦 자재 재고 현황 (스냅샷)*\n"
            f"  재고 있는 자재: *{_num(mat['total'])}종*   "
            f"실물 합계: {_num(mat['total_phys'])}개\n"
            f"  재고 정확도: {acc_icon} *{mat['accuracy']}%*  (목표 ≥99.5%)\n"
            f"  불일치 항목: {mat['mismatch']}종   "
            f"가용재고 음수: {avail_icon} {mat['neg_avail']}종   "
            f"체크 완료: {mat['check_done']}종\n\n"
            f"*불일치 Top 5*\n{mismatch_text}"
        )}
    })
    blocks.append({"type": "divider"})

    # ── 5. 월간 이슈 요약 ──
    issues = []
    if inbound["unconfirmed"] > 0:
        issues.append(f"⚠️ 입하여부 미확인 {inbound['unconfirmed']}건")
    if not qc["target_met"] and qc["qc_cnt"] > 0:
        issues.append(f"❌ 불량률 {defect_rate}% — 목표(1.0%) 초과")
    if mat["neg_avail"] > 0:
        issues.append(f"⚠️ 가용재고 음수 {mat['neg_avail']}종")
    if mat["mismatch"] > 0:
        issues.append(f"📋 재고 불일치 {mat['mismatch']}종 — 실사 필요")

    issue_text = "\n".join(issues) or "✅ 특이사항 없음"
    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": f"*⚡ 월간 이슈 요약*\n{issue_text}"}
    })

    return blocks

# ── Slack 발송 ────────────────────────────────────────────────────────────────
def _slack_api(endpoint: str, payload: dict) -> dict:
    resp = requests.post(
        f"https://slack.com/api/{endpoint}",
        headers={
            "Authorization": f"Bearer {SLACK_TOKEN}",
            "Content-Type": "application/json; charset=utf-8",
        },
        json=payload,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Slack API error [{endpoint}]: {data.get('error')}")
    return data

def send_dm(blocks: list, fallback_text: str):
    ch_data = _slack_api("conversations.open", {"users": DM_USER_ID})
    channel = ch_data["channel"]["id"]
    _slack_api("chat.postMessage", {
        "channel":      channel,
        "text":         fallback_text,
        "blocks":       blocks,
        "unfurl_links": False,
    })

# ── 메인 ─────────────────────────────────────────────────────────────────────
def main():
    if not SKIP_DELAY:
        import random
        delay = random.randint(0, 1800)
        print(f"[WMS Monthly] Sleeping {delay}s before start...")
        time.sleep(delay)

    start, end = prev_month_range()
    month_label = start.strftime("%Y년 %m월")
    print(f"[WMS Monthly] 기간: {start} ~ {end}")

    print("[WMS Monthly] movement 조회 중...")
    movement_records = fetch_movement(start, end)
    print(f"[WMS Monthly] movement: {len(movement_records)}건")

    print("[WMS Monthly] material 조회 중...")
    material_records = fetch_material()
    print(f"[WMS Monthly] material: {len(material_records)}건")

    inbound = analyze_inbound(movement_records)
    qc      = analyze_qc(movement_records)
    mat     = analyze_material(material_records)

    print(f"[WMS Monthly] 입고 {inbound['total_cnt']}건 / 불량률 {qc['defect_rate']}% / 재고 정확도 {mat['accuracy']}%")

    # JSON 아티팩트
    report_data = {
        "generated_at": datetime.now().isoformat(),
        "month":        start.strftime("%Y-%m"),
        "inbound":      inbound,
        "qc":           qc,
        "material":     {k: v for k, v in mat.items() if k != "top_mismatch"},
    }
    artifact_path = f"wms_monthly_report_{start.strftime('%Y-%m')}.json"
    with open(artifact_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2, default=str)
    print(f"[WMS Monthly] artifact: {artifact_path}")

    blocks = build_blocks(inbound, qc, mat, month_label)
    send_dm(blocks, f"[WMS 월간 리포트] {month_label}")
    print("[WMS Monthly] Slack DM 발송 완료")

if __name__ == "__main__":
    if not AIRTABLE_API_KEY:
        print("ERROR: AIRTABLE_PAT 환경변수 없음", file=sys.stderr)
        sys.exit(1)
    if not SLACK_TOKEN or not DM_USER_ID:
        print("ERROR: SLACK_BOT_TOKEN / SLACK_DM_USER_ID 환경변수 없음", file=sys.stderr)
        sys.exit(1)
    main()
