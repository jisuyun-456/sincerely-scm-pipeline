"""
probe_tms_diag_live.py
──────────────────────────────────────────────────────────────────────────────
TMS 베이스(app4x70a8mOrIKsMf) 읽기 전용 진단 스냅샷 — TMS 종합진단 리포트용.

GET 전용 (PATCH/POST/DELETE 코드 경로 없음). 14개 지표를 산출해 JSON 저장:
  _AutoResearch/SCM/outputs/tms_diag_live_YYYYMMDD.json

사용법:
  python scripts/probe_tms_diag_live.py [--as-of 2026-07-21] [--out PATH]

종료코드: 0=전부 ok / 1=일부 field_mismatch·needs_definition / 2=치명(인증 등)
"""

import argparse
import difflib
import json
import sys
import threading
import time
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

import os  # noqa: E402  (after load_dotenv for clarity)

ROOT = Path(__file__).parent.parent
OUT_DIR = ROOT / "_AutoResearch" / "SCM" / "outputs"

BASE_ID = "app4x70a8mOrIKsMf"
API = f"https://api.airtable.com/v0/{BASE_ID}"
META = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables"

T_SHIPMENT = "tbllg1JoHclGYer7m"
T_DISPATCH = "tbl0YCjOC7rYtyXHV"   # 배차 일지
T_OTIF     = "tbl4WfEuGLDlqCTQH"
T_RATE     = "tblQA1ev9fjbowUoP"   # 운임단가
T_SLA      = "tblbPC6z0AsbvcVxJ"   # 배송SLA
T_CLAIM    = "tblIZ9kco1QDpUz0u"   # 배송클레임
T_SETTLE   = "tblf0BClxZtnQfOJL"   # 정산관리
T_EVENT    = "tblQyuAW30yf21WEf"   # 배송이벤트
T_TRACK    = "tblonyqcHGa5V5zbj"   # 택배추적로그
T_PRODUCT  = "tblBNh6oGDlTKGrdQ"
T_PARTNER  = "tblI4ZXrte7WyhXyd"   # 배송파트너

# 내부 기사 판별 — harness/tms_settlement/config.py:45-49 (KNOWN_DRIVERS)
KNOWN_DRIVER_IDS = {"recyVExCkk2Lty0E9", "recPkgE4o3cs0krnR", "recXCfwVTqaoeQ9SS"}
# runner 호환 기준 — scripts/tms_weekly_runner.py:122 (물류팀 포함)
INTERNAL_KEYWORDS = ("이장훈", "조희선", "박종성", "물류팀")

# 테이블별 투영 필드 (필드명 기반 — returnFieldsByFieldId 병용 금지: 422 함정)
FIELDS = {
    T_SHIPMENT: {
        "pass_a": ["출하확정일", "POD_확인일시", "CBM_유효", "estimated_cbm", "Total_CBM"],
        "pass_b": ["출하확정일", "발송상태_TMS", "wave_recommendation", "wave_confidence",
                    "wave_locked", "wave_updated_at", "배송파트너", "배송 방식", "구간유형", "OTIF"],
    },
    T_DISPATCH: ["날짜"],
    T_OTIF: ["On_Time", "In_Full", "OTIF_Score", "실제배송일", "약속납기일", "미달성사유"],
    T_RATE: ["단가코드", "배송파트너", "구간유형", "CBM_최소", "CBM_최대", "기본운임",
             "CBM당_추가운임", "상하차비_포함", "유효시작일", "유효종료일", "비고"],
    T_SLA: ["SLA코드", "구간유형", "배송방식", "목표배송시간", "목표배송일수",
            "OTIF목표", "패널티조건", "유효시작일", "비고"],
    T_CLAIM: ["클레임유형", "발생일", "접수일", "처리상태", "피해금액", "보상금액", "완료일"],
    T_SETTLE: ["정산번호", "정산월", "정산상태", "물류매출", "총물류비", "Shipment"],
    T_EVENT: ["이벤트유형", "이벤트일시"],
    T_TRACK: ["추적상태", "추적일시"],
    T_PRODUCT: ["Name", "박스규격", "CBM", "박스 당 CBM", "박스사이즈", "단품/키트"],
    T_PARTNER: ["배송파트너", "wave_pattern", "contract_type", "autonomy_level",
                "lock_in_reason", "배송파트너_CBM", "daily_fixed_cost", "max_daily_orders",
                "work_hours_start", "work_hours_end", "residence", "Status"],
}

SELECT_CAPTURE = {  # pre-flight에서 라이브 선택지 수집
    T_SHIPMENT: ["발송상태_TMS", "wave_recommendation"],
    T_CLAIM: ["처리상태"],
    T_SETTLE: ["정산상태"],
    T_PARTNER: ["wave_pattern", "contract_type", "autonomy_level"],
}

MAX_PAGES = 400


class RateLimiter:
    """4 rps sliding-window (한도 5 rps/base 대비 여유) — harness/_core/airtable.py 차용."""

    def __init__(self, max_rps: float = 4.0) -> None:
        self._max = int(max_rps)
        self._ts: deque = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            while self._ts and now - self._ts[0] >= 1.0:
                self._ts.popleft()
            if len(self._ts) >= self._max:
                wait = 1.0 - (now - self._ts[0])
                if wait > 0:
                    time.sleep(wait)
            self._ts.append(time.monotonic())


LIMITER = RateLimiter()
SESSION = requests.Session()
SESSION.headers.update({"Authorization": f"Bearer {os.environ.get('AIRTABLE_PAT', '')}"})
REQ_COUNT = {"n": 0}
REQ_LOCK = threading.Lock()


def _get(url: str, params=None) -> dict:
    """Rate-limited GET, 429→30s 재시도(최대3), 5xx→2/4/8s 백오프."""
    for attempt in range(4):
        LIMITER.acquire()
        with REQ_LOCK:
            REQ_COUNT["n"] += 1
        resp = SESSION.get(url, params=params, timeout=60)
        if resp.status_code == 429:
            time.sleep(30)
            continue
        if resp.status_code >= 500 and attempt < 3:
            time.sleep(2 ** (attempt + 1))
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()
    return {}


def fetch(table_id: str, fields: list, formula: str | None = None,
          sort_field: str | None = None, sort_dir: str = "desc",
          max_records: int | None = None) -> list:
    records, offset, pages = [], None, 0
    while True:
        params = [("pageSize", "100")] + [("fields[]", f) for f in fields]
        if formula:
            params.append(("filterByFormula", formula))
        if sort_field:
            params += [("sort[0][field]", sort_field), ("sort[0][direction]", sort_dir)]
        if max_records:
            params.append(("maxRecords", str(max_records)))
        if offset:
            params.append(("offset", offset))
        data = _get(f"{API}/{table_id}", params=params)
        records.extend(data.get("records", []))
        offset = data.get("offset")
        pages += 1
        if not offset or pages >= MAX_PAGES or (max_records and len(records) >= max_records):
            break
    return records


# ── pre-flight ────────────────────────────────────────────────────────────────

def preflight() -> dict:
    """Meta API 1회 → 모든 투영 필드명 라이브 검증. 불일치는 보고만, 추측 금지."""
    data = _get(META)
    live: dict[str, dict] = {}
    select_opts: dict[str, list] = {}
    for t in data.get("tables", []):
        fmap = {}
        for f in t.get("fields", []):
            fmap[f["name"]] = f["type"]
            cap_list = SELECT_CAPTURE.get(t["id"], [])
            if f["name"] in cap_list and f["type"] in ("singleSelect", "multipleSelects"):
                choices = (f.get("options") or {}).get("choices") or []
                select_opts[f"{t['id']}:{f['name']}"] = [c["name"] for c in choices]
        live[t["id"]] = {"name": t["name"], "fields": fmap}

    mismatches = []
    for tid, spec in FIELDS.items():
        wanted = (spec["pass_a"] + spec["pass_b"]) if isinstance(spec, dict) else spec
        live_names = list(live.get(tid, {}).get("fields", {}).keys())
        for name in set(wanted):
            if name not in live_names:
                mismatches.append({
                    "table": tid,
                    "table_name": live.get(tid, {}).get("name"),
                    "expected_field": name,
                    "closest_live_names": difflib.get_close_matches(name, live_names, n=3),
                })
    return {"live": live, "mismatches": mismatches, "select_options_live": select_opts}


# ── 값 정규화 헬퍼 ─────────────────────────────────────────────────────────────

def norm_rollup(v):
    """배송 방식 rollup: list-or-str → str (tms_weekly_runner.py:187-195 패턴)."""
    if isinstance(v, list) and v:
        first = v[0]
        return first.get("value", "") if isinstance(first, dict) else str(first)
    if isinstance(v, str):
        return v
    return ""


def val_hist(rows, field) -> dict:
    """formula 필드의 원시 값-형태 히스토그램 (타입:값 상위 12)."""
    c = Counter()
    for r in rows:
        v = r["fields"].get(field)
        c[f"{type(v).__name__}:{v!r}"[:60]] += 1
    return dict(c.most_common(12))


def truthy_rate(rows, field):
    """1/0·bool·'1'/'0'만 깨끗하면 (rate, n_valid) 반환, 아니면 (None, 0)."""
    num = valid = 0
    for r in rows:
        v = r["fields"].get(field)
        if isinstance(v, list) and len(v) == 1:
            v = v[0]
        if isinstance(v, bool):
            valid += 1
            num += int(v)
        elif isinstance(v, (int, float)) and v in (0, 1):
            valid += 1
            num += int(v)
        elif isinstance(v, str) and v.strip() in ("0", "1", "TRUE", "FALSE", "True", "False"):
            valid += 1
            num += int(v.strip() in ("1", "TRUE", "True"))
    if valid == 0:
        return None, 0
    return num / valid, valid


def nonblank(v) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, list):
        return len(v) > 0
    return True


def as_number(v):
    if isinstance(v, list) and len(v) == 1:
        v = v[0]
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(",", "").strip())
        except ValueError:
            return None
    return None


def metric(claim_id, value, num=None, den=None, window=None, definition="",
           status="ok", raw=None):
    return {"claim_id": claim_id, "status": status, "value": value,
            "numerator": num, "denominator": den, "window": window,
            "definition": definition, "raw": raw or {}}


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default="2026-07-21")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    as_of = date.fromisoformat(args.as_of)
    d90 = (as_of - timedelta(days=90)).isoformat()   # 2026-04-22
    d30 = (as_of - timedelta(days=30)).isoformat()   # 2026-06-21
    d28 = (as_of - timedelta(days=28)).isoformat()   # 2026-06-23 (구간 시작 exclusive → 06-24부터)
    out_path = Path(args.out) if args.out else \
        OUT_DIR / f"tms_diag_live_{as_of.strftime('%Y%m%d')}.json"

    if not os.environ.get("AIRTABLE_PAT"):
        print("FATAL: AIRTABLE_PAT not set", file=sys.stderr)
        return 2

    t0 = time.time()
    print("[preflight] Meta API 스키마 검증...")
    try:
        pf = preflight()
    except requests.HTTPError as e:
        print(f"FATAL: meta fetch failed — {e}", file=sys.stderr)
        return 2
    mismatched_fields = {(m["table"], m["expected_field"]) for m in pf["mismatches"]}
    if pf["mismatches"]:
        print(f"[preflight] 필드명 불일치 {len(pf['mismatches'])}건:")
        for m in pf["mismatches"]:
            print(f"  - {m['table_name']}:{m['expected_field']} → 후보 {m['closest_live_names']}")
    else:
        print("[preflight] 전 필드명 일치 ✓")

    def ok_fields(tid, names):
        return [n for n in names if (tid, n) not in mismatched_fields]

    # ── 병렬 조회 ──
    results: dict[str, list] = {}

    def run_fetch(key, tid, fields, **kw):
        fields = ok_fields(tid, fields)
        try:
            results[key] = fetch(tid, fields, **kw)
            print(f"[fetch] {key}: {len(results[key])} rows")
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else "?"
            if code == 422 and kw.get("formula"):
                # formula 필드 필터 거부 → 전체 조회 fallback (클라이언트 필터링)
                print(f"[fetch] {key}: 422 on formula → full-scan fallback")
                kw2 = {k: v for k, v in kw.items() if k not in ("formula", "sort_field", "sort_dir")}
                results[key] = fetch(tid, fields, **kw2)
                results[f"{key}__fallback"] = [True]
            else:
                print(f"[fetch] {key}: FAILED {code} — {e}")
                results[key] = []
                results[f"{key}__error"] = [str(e)]

    jobs = [
        ("ship_a", T_SHIPMENT, FIELDS[T_SHIPMENT]["pass_a"], {}),
        ("ship_b", T_SHIPMENT, FIELDS[T_SHIPMENT]["pass_b"],
         {"formula": f"IS_AFTER({{출하확정일}}, '{(date.fromisoformat(d90) - timedelta(days=1)).isoformat()}')"}),
        ("dispatch", T_DISPATCH, FIELDS[T_DISPATCH], {}),
        ("otif", T_OTIF, FIELDS[T_OTIF],
         {"formula": f"IS_AFTER({{실제배송일}}, '{(date.fromisoformat(d90) - timedelta(days=1)).isoformat()}')"}),
        ("rate", T_RATE, FIELDS[T_RATE], {}),
        ("sla", T_SLA, FIELDS[T_SLA], {}),
        ("claim", T_CLAIM, FIELDS[T_CLAIM], {}),
        ("settle", T_SETTLE, FIELDS[T_SETTLE], {}),
        ("event_30d", T_EVENT, FIELDS[T_EVENT],
         {"formula": f"IS_AFTER({{이벤트일시}}, '{d30}')"}),
        ("event_latest", T_EVENT, FIELDS[T_EVENT],
         {"sort_field": "이벤트일시", "max_records": 1}),
        ("track_30d", T_TRACK, FIELDS[T_TRACK],
         {"formula": f"IS_AFTER({{추적일시}}, '{d30}')"}),
        ("track_latest", T_TRACK, FIELDS[T_TRACK],
         {"sort_field": "추적일시", "max_records": 1}),
        ("product", T_PRODUCT, FIELDS[T_PRODUCT], {}),
        ("partner", T_PARTNER, FIELDS[T_PARTNER], {}),
    ]
    print(f"[fetch] {len(jobs)}개 작업 병렬 시작 (4 workers, 4 rps)...")
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(run_fetch, k, t, f, **kw) for k, t, f, kw in jobs]
        for f in futs:
            f.result()

    ship_a = results.get("ship_a", [])
    ship_b = results.get("ship_b", [])
    M: dict[str, dict] = {}

    def W(frm, basis):
        return {"from": frm, "to": as_of.isoformat(), "basis_field": basis}

    # ① 배차일지 staleness
    ddates = sorted(r["fields"].get("날짜") for r in results.get("dispatch", [])
                    if r["fields"].get("날짜"))
    weekly = Counter()
    for ds in ddates:
        if ds >= "2026-05-01":
            y, w, _ = date.fromisoformat(ds).isocalendar()
            weekly[f"{y}-W{w:02d}"] += 1
    latest_d = ddates[-1] if ddates else None
    M["dispatch_staleness_days"] = metric(
        1, (as_of - date.fromisoformat(latest_d)).days if latest_d else None,
        window=W(None, "날짜"),
        definition="as_of − max(배차일지.날짜) 일수",
        status="ok" if latest_d else "needs_definition",
        raw={"latest_date": latest_d, "total_rows": len(ddates),
             "weekly_counts_since_may": dict(sorted(weekly.items()))})

    # ② POD 캡처율
    a_90 = [r for r in ship_a if (r["fields"].get("출하확정일") or "") >= d90]
    a_dated = [r for r in ship_a if r["fields"].get("출하확정일")]
    pod_90 = sum(1 for r in a_90 if nonblank(r["fields"].get("POD_확인일시")))
    pod_all = sum(1 for r in a_dated if nonblank(r["fields"].get("POD_확인일시")))
    M["pod_capture_90d"] = metric(
        2, round(pod_90 / len(a_90), 4) if a_90 else None, pod_90, len(a_90),
        W(d90, "출하확정일"), "POD_확인일시 non-null 비율 (최근 90일 출하)")
    M["pod_capture_alltime"] = metric(
        2, round(pod_all / len(a_dated), 4) if a_dated else None, pod_all, len(a_dated),
        W(None, "출하확정일"), "POD_확인일시 non-null 비율 (출하확정일 있는 전체)",
        raw={"rows_no_ship_date": len(ship_a) - len(a_dated)})

    # ③ CBM 커버리지 12셀 매트릭스
    cbm_matrix = {}
    for fld in ("CBM_유효", "estimated_cbm", "Total_CBM"):
        for wname, rows in (("alltime", a_dated), ("90d", a_90)):
            nn = sum(1 for r in rows if nonblank(r["fields"].get(fld)))
            nz = sum(1 for r in rows
                     if (as_number(r["fields"].get(fld)) or 0) > 0)
            n = len(rows)
            cbm_matrix[f"{fld}|{wname}"] = {
                "non_null": nn, "non_zero": nz, "n": n,
                "non_null_pct": round(nn / n, 4) if n else None,
                "non_zero_pct": round(nz / n, 4) if n else None}
    M["cbm_coverage_matrix"] = metric(
        3, cbm_matrix[f"CBM_유효|90d"]["non_zero_pct"],
        cbm_matrix[f"CBM_유효|90d"]["non_zero"], cbm_matrix[f"CBM_유효|90d"]["n"],
        W(d90, "출하확정일"),
        "헤드라인=CBM_유효 non-zero 90일; raw에 3필드×2윈도우×2정의 전체 매트릭스",
        raw={"matrix": cbm_matrix, "cbm_유효_value_shapes": val_hist(a_90[:2000], "CBM_유효")})

    # ④ OTIF
    otif_rows = results.get("otif", [])
    if results.get("otif__fallback"):
        otif_rows = [r for r in otif_rows
                     if str(r["fields"].get("실제배송일") or "") >= d90]
    ot_rate, ot_valid = truthy_rate(otif_rows, "On_Time")
    if_rate, if_valid = truthy_rate(otif_rows, "In_Full")
    b_total = len(ship_b)
    otif_link = sum(1 for r in ship_b if nonblank(r["fields"].get("OTIF")))
    M["otif_coverage_90d"] = metric(
        4, round(otif_link / b_total, 4) if b_total else None, otif_link, b_total,
        W(d90, "출하확정일"), "Shipment(90d) 중 OTIF 링크 보유 비율",
        status="fallback_full_scan" if results.get("otif__fallback") else "ok",
        raw={"otif_rows_90d": len(otif_rows),
             "on_time_rate": round(ot_rate, 4) if ot_rate is not None else None,
             "on_time_valid_n": ot_valid,
             "in_full_rate": round(if_rate, 4) if if_rate is not None else None,
             "in_full_valid_n": if_valid,
             "on_time_value_shapes": val_hist(otif_rows[:1500], "On_Time"),
             "latest_실제배송일": max((str(r["fields"].get("실제배송일") or "")
                                      for r in otif_rows), default=None),
             "미달성사유_hist": dict(Counter(
                 str(r["fields"].get("미달성사유")) for r in otif_rows).most_common(8)),
             "caveat": "약속납기일은 runner가 출하확정일+SLA로 역산 백필 — 순환성은 베이스에서 측정 불가"})

    # ⑤ 운임단가 만료 점검
    rate_rows = results.get("rate", [])
    expired, expiring, open_ended = [], [], []
    for r in rate_rows:
        f = r["fields"]
        end = f.get("유효종료일")
        code = f.get("단가코드") or r["id"]
        if not end:
            open_ended.append(code)
        elif end < as_of.isoformat():
            expired.append(f"{code}({end})")
        elif end <= (as_of + timedelta(days=30)).isoformat():
            expiring.append(f"{code}({end})")
    M["rate_card"] = metric(
        5, len(rate_rows), len(expired), len(rate_rows), W(None, "유효종료일"),
        "value=총 단가 수; numerator=만료 건수",
        raw={"expired": expired, "expiring_30d": expiring, "open_ended": open_ended})

    # ⑥ 배송SLA 실입력
    sla_rows = results.get("sla", [])
    sla_fill = {fld: sum(1 for r in sla_rows if nonblank(r["fields"].get(fld)))
                for fld in FIELDS[T_SLA]}
    M["sla_population"] = metric(
        6, len(sla_rows), window=W(None, None),
        definition="배송SLA 레코드 수 + 필드별 채움 수",
        raw={"fill_counts": sla_fill,
             "rows": [r["fields"] for r in sla_rows][:20]})

    # ⑦ 배송클레임
    claim_rows = results.get("claim", [])
    c_90 = [r for r in claim_rows if (r["fields"].get("발생일") or "") >= d90]
    M["claims_usage"] = metric(
        7, len(claim_rows), len(c_90), len(claim_rows), W(d90, "발생일"),
        "value=전체 클레임 수; numerator=최근 90일",
        raw={"latest_발생일": max((r["fields"].get("발생일") or "" for r in claim_rows),
                                default=None) or None,
             "처리상태_hist_all": dict(Counter(
                 str(r["fields"].get("처리상태")) for r in claim_rows).most_common()),
             "처리상태_hist_90d": dict(Counter(
                 str(r["fields"].get("처리상태")) for r in c_90).most_common())})

    # ⑧ 정산관리
    settle_rows = results.get("settle", [])
    months_raw = Counter(str(r["fields"].get("정산월") or "(blank)") for r in settle_rows)
    import re
    def month_match(s, mm):
        return bool(re.search(rf"2026[-./년\s]*0?{mm}\b", s))
    recent_months = {f"2026-0{m}": sum(1 for r in settle_rows
                                       if month_match(str(r["fields"].get("정산월") or ""), m))
                     for m in (5, 6, 7)}
    M["settlement_usage"] = metric(
        8, len(settle_rows), window=W(None, "정산월"),
        definition="정산관리 레코드 수; raw에 정산월 원본 분포 + 5/6/7월 매칭",
        status="ok" if settle_rows else "needs_definition",
        raw={"정산월_raw_hist": dict(months_raw.most_common(15)),
             "months_2026_05_07": recent_months,
             "정산상태_hist": dict(Counter(
                 str(r["fields"].get("정산상태")) for r in settle_rows).most_common()),
             "linked_shipments_total": sum(len(r["fields"].get("Shipment") or [])
                                           for r in settle_rows)})

    # ⑨ 이벤트·추적 최신성
    def liveness(key_30d, key_latest, dt_field, type_field):
        rows30 = results.get(key_30d, [])
        latest = results.get(key_latest, [])
        latest_ts = latest[0]["fields"].get(dt_field) if latest else None
        return {"latest": latest_ts, "count_30d": len(rows30),
                "type_hist_30d": dict(Counter(
                    str(r["fields"].get(type_field)) for r in rows30).most_common(8))}
    ev = liveness("event_30d", "event_latest", "이벤트일시", "이벤트유형")
    tr = liveness("track_30d", "track_latest", "추적일시", "추적상태")
    M["event_liveness"] = metric(
        9, ev["count_30d"], window=W(d30, "이벤트일시"),
        definition="배송이벤트 최근 30일 건수 + 최신 일시 (UTC/KST ±9h 오차 허용)",
        raw={"배송이벤트": ev, "택배추적로그": tr})

    # ⑩ Product CBM 마스터
    prod_rows = results.get("product", [])
    pn = len(prod_rows)
    prod_fill = {}
    for fld in ("박스규격", "CBM", "박스사이즈"):
        prod_fill[fld] = sum(1 for r in prod_rows if nonblank(r["fields"].get(fld)))
    bpc_nz = sum(1 for r in prod_rows
                 if (as_number(r["fields"].get("박스 당 CBM")) or 0) > 0)
    M["product_cbm_master"] = metric(
        10, round(bpc_nz / pn, 4) if pn else None, bpc_nz, pn, W(None, None),
        "박스 당 CBM > 0 비율; raw에 필드별 채움",
        raw={"fill_counts": prod_fill, "n": pn,
             "박스당CBM_value_shapes": val_hist(prod_rows[:400], "박스 당 CBM")})

    # ⑪ 배송파트너 정책 필드
    partner_rows = results.get("partner", [])
    pid2name = {r["id"]: r["fields"].get("배송파트너", "") for r in partner_rows}
    policy_fields = ["wave_pattern", "contract_type", "autonomy_level", "lock_in_reason",
                     "배송파트너_CBM", "daily_fixed_cost", "max_daily_orders",
                     "work_hours_start", "work_hours_end"]
    pf_fill = {fld: sum(1 for r in partner_rows if nonblank(r["fields"].get(fld)))
               for fld in policy_fields}
    missing_any = [r["fields"].get("배송파트너", r["id"]) for r in partner_rows
                   if any(not nonblank(r["fields"].get(f)) for f in policy_fields)]
    driver_id_drift = [i for i in KNOWN_DRIVER_IDS if i not in pid2name]
    M["partner_policy"] = metric(
        11, len(partner_rows), window=W(None, None),
        definition="배송파트너 레코드 수 + 정책 필드 9종 채움",
        raw={"fill_counts": pf_fill, "partners_missing_any": missing_any,
             "driver_id_drift": driver_id_drift})

    # ⑫ wave 채택 (최근 30일 출하)
    b_30 = [r for r in ship_b if (r["fields"].get("출하확정일") or "") >= d30]
    wave_nn = sum(1 for r in b_30 if nonblank(r["fields"].get("wave_recommendation")))
    M["wave_adoption_30d"] = metric(
        12, round(wave_nn / len(b_30), 4) if b_30 else None, wave_nn, len(b_30),
        W(d30, "출하확정일"),
        "wave_recommendation non-null 비율 — 추천 커버리지 (실준수 여부는 실배정 필드 부재로 측정 불가)",
        raw={"wave_hist": dict(Counter(
                 str(r["fields"].get("wave_recommendation")) for r in b_30).most_common(10)),
             "wave_locked_n": sum(1 for r in b_30 if r["fields"].get("wave_locked")),
             "발송상태_hist": dict(Counter(
                 str(r["fields"].get("발송상태_TMS")) for r in b_30).most_common(10)),
             "engine_last_update": max((str(r["fields"].get("wave_updated_at") or "")
                                        for r in ship_b), default=None)})

    # ⑬ 내부소화율 (최근 28일)
    b_28 = [r for r in ship_b if (r["fields"].get("출하확정일") or "") > d28]
    def absorption(rows):
        with_partner = [r for r in rows if nonblank(r["fields"].get("배송파트너"))]
        strict = kw_based = 0
        for r in with_partner:
            ids = r["fields"].get("배송파트너") or []
            names = [pid2name.get(i, "") for i in ids]
            if any(i in KNOWN_DRIVER_IDS for i in ids):
                strict += 1
            if any(any(k in n for k in INTERNAL_KEYWORDS) for n in names):
                kw_based += 1
        return strict, kw_based, len(with_partner)
    s28, k28, n28 = absorption(b_28)
    weekly_abs = {}
    for r in b_28:
        ds = r["fields"].get("출하확정일")
        y, w, _ = date.fromisoformat(ds).isocalendar()
        weekly_abs.setdefault(f"{y}-W{w:02d}", []).append(r)
    weekly_out = {}
    for wk, rows in sorted(weekly_abs.items()):
        s, k, n = absorption(rows)
        weekly_out[wk] = {"strict": round(s / n, 4) if n else None, "n": n}
    M["internal_absorption_28d"] = metric(
        13, round(s28 / n28, 4) if n28 else None, s28, n28,
        {"from": (date.fromisoformat(d28) + timedelta(days=1)).isoformat(),
         "to": as_of.isoformat(), "basis_field": "출하확정일"},
        "3기사 record-ID 엄격 기준; raw에 runner 호환(물류팀 포함) 변형 + 주별 추세",
        raw={"runner_compatible_rate": round(k28 / n28, 4) if n28 else None,
             "weekly": weekly_out,
             "no_partner_rows": len(b_28) - n28})

    # ⑭ 월별 물량
    monthly = Counter()
    for r in a_dated:
        m = r["fields"]["출하확정일"][:7]
        if "2026-04" <= m <= "2026-07":
            monthly[m] += 1
    M["monthly_volume"] = metric(
        14, dict(sorted(monthly.items())), window=W("2026-04-01", "출하확정일"),
        definition="월별 출하확정 건수 (2026-07은 21일까지 부분)",
        raw={"blank_ship_date_rows": len(ship_a) - len(a_dated),
             "shipment_total_rows": len(ship_a)})

    # 상태 전파: 필드 불일치가 있으면 해당 테이블 지표 status 표기
    for m in pf["mismatches"]:
        tid = m["table"]
        affected = {T_DISPATCH: ["dispatch_staleness_days"], T_OTIF: ["otif_coverage_90d"],
                    T_RATE: ["rate_card"], T_SLA: ["sla_population"],
                    T_CLAIM: ["claims_usage"], T_SETTLE: ["settlement_usage"],
                    T_EVENT: ["event_liveness"], T_TRACK: ["event_liveness"],
                    T_PRODUCT: ["product_cbm_master"], T_PARTNER: ["partner_policy"],
                    T_SHIPMENT: ["pod_capture_90d", "cbm_coverage_matrix",
                                 "wave_adoption_30d", "internal_absorption_28d"]}.get(tid, [])
        for key in affected:
            if key in M:
                M[key]["status"] = "field_mismatch"

    out = {
        "schema_version": 1,
        "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "as_of_date": as_of.isoformat(),
        "base_id": BASE_ID,
        "schema_validation": {
            "mismatches": pf["mismatches"],
            "select_options_live": pf["select_options_live"],
        },
        "request_stats": {
            "total_requests": REQ_COUNT["n"],
            "duration_s": round(time.time() - t0, 1),
            "records_fetched": {k: len(v) for k, v in results.items()
                                if not k.endswith("__fallback") and not k.endswith("__error")},
        },
        "metrics": M,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'지표':<28} {'값':<20} {'분자/분모':<16} status")
    for k, v in M.items():
        val = v["value"]
        vs = json.dumps(val, ensure_ascii=False) if isinstance(val, dict) else str(val)
        print(f"{k:<28} {vs[:20]:<20} {str(v['numerator'])+'/'+str(v['denominator']):<16} {v['status']}")
    print(f"\n[done] {out_path}  ({REQ_COUNT['n']} req, {out['request_stats']['duration_s']}s)")

    bad = [k for k, v in M.items() if v["status"] in ("field_mismatch", "needs_definition")]
    if bad:
        print(f"[warn] 비정상 status 지표: {bad}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
