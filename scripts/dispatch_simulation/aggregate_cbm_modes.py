"""B — 자동배차 수동 사유를 표본 전체로 집계 (읽기 전용).

dispatch 가 읽는 estimated_cbm 은 cascade S5 와 동일 함수. 이 스크립트는 출하확정일 윈도우
전체에 대해 각 건의 CBM 해소 모드 + 자동/수동 판정을 집계하고, 특히 partial_skip(다차 출하)
중 '과거 출하완료가 카운트를 부풀린 가짜'(active 출하 ≤1)와 '진짜 다차(active >1)'를 구분한다.
→ 레버 1(active-only 카운트)이 몇 건을 즉시 복구하는지 정량화.

Usage:
  python -m scripts.dispatch_simulation.aggregate_cbm_modes [date_from] [date_to]
  (기본 윈도우: 2026-06-23 ~ 2026-09-30 — 향후 출하 = dispatch 모집단)
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter, defaultdict

from dotenv import load_dotenv
load_dotenv()

import scripts.backbone.replay_outbound_cbm as rp
from harness.dispatch.cbm_estimator import (
    SERVICE_CODES, estimate_shipment_cbm_deterministic,
)
from harness.dispatch.slot_decider import decide_slot

PNA = re.compile(r"PNA\d+")
PAT = os.environ["AIRTABLE_PAT"]
TMS = "app4x70a8mOrIKsMf"; SHIP = "tbllg1JoHclGYer7m"
F_DATE = "fldQvmEwwzvQW95h9"; F_PROJ = "fldTs3FzaSdGYEiKX"; F_METHOD = "flduzH5tS7orqGG3o"
F_HOPE = "fldFweNu3dASPv93N"; F_TOTCBM = "fldJ9DHjwoRyeUEqE"; F_STATUS = "fldOhibgxg6LIpRTi"
TERMINAL = {"출하 완료", "진행 취소"}


def first(v):
    return (v[0] if v else None) if isinstance(v, list) else v


def _paged(params):
    url = f"https://api.airtable.com/v0/{TMS}/{SHIP}"
    out, offset = [], None
    while True:
        p = dict(params)
        if offset:
            p["offset"] = offset
        # fields[] needs repeated key; build manually
        parts = []
        for k, v in p.items():
            if k == "fields[]":
                for fv in v:
                    parts.append(f"fields%5B%5D={urllib.parse.quote(fv)}")
            else:
                parts.append(f"{k}={urllib.parse.quote(str(v))}")
        req = urllib.request.Request(url + "?" + "&".join(parts),
                                     headers={"Authorization": f"Bearer {PAT}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
        out += d.get("records", [])
        offset = d.get("offset")
        if not offset:
            break
    return out


def active_counts() -> tuple[dict, dict]:
    """전체 shipment → PNA별 (total_count, active_count). active = status ∉ TERMINAL."""
    recs = _paged({"pageSize": 100, "fields[]": [F_PROJ, F_STATUS], "returnFieldsByFieldId": "true"})
    total = Counter(); active = Counter()
    for rec in recs:
        f = rec.get("fields", {})
        m = PNA.search(str(first(f.get(F_PROJ)) or ""))
        if not m:
            continue
        pna = m.group(0)
        total[pna] += 1
        if str(first(f.get(F_STATUS)) or "") not in TERMINAL:
            active[pna] += 1
    return dict(total), dict(active)


def window_targets(d_from: str, d_to: str):
    formula = f"AND(IS_AFTER({{{F_DATE}}},'{d_from}'),IS_BEFORE({{{F_DATE}}},'{d_to}'))"
    return _paged({"pageSize": 100, "filterByFormula": formula, "returnFieldsByFieldId": "true"})


def main():
    d_from = sys.argv[1] if len(sys.argv) > 1 else "2026-06-23"
    d_to = sys.argv[2] if len(sys.argv) > 2 else "2026-09-30"
    print(f"build_inputs() 로딩 (수 분)...", flush=True)
    lk, obp, scount, _ships, kit = rp.build_inputs()
    print("active 카운트 집계 (status fetch)...", flush=True)
    total_cnt, active_cnt = active_counts()
    print(f"  PNA {len(total_cnt)}개. 윈도우 fetch {d_from}~{d_to}...", flush=True)
    recs = window_targets(d_from, d_to)
    print(f"  대상 {len(recs)}건\n", flush=True)

    mode_tally = Counter(); disp = Counter()
    manual_cause = Counter()
    ps_recoverable = 0; ps_genuine = 0
    for rec in recs:
        f = rec.get("fields", {})
        proj = str(first(f.get(F_PROJ)) or "")
        m = PNA.search(proj)
        pna = m.group(0) if m else None
        tot = rp.n(f.get(F_TOTCBM))
        det = (estimate_shipment_cbm_deterministic(pna, obp, lk, scount, kit_lookup=kit,
               service_codes=SERVICE_CODES) if pna else
               {"mode": "blank_proj", "estimated_cbm": 0.0, "confidence": 0.0})
        mode_tally[det["mode"] if tot <= 0 else "실측"] += 1

        if tot > 0:
            cbm_conf = 1.0
        elif det["estimated_cbm"] > 0:
            cbm_conf = det["confidence"]
        else:
            cbm_conf = 0.3
        slot, slot_conf = decide_slot(str(first(f.get(F_METHOD)) or ""),
                                      str(first(f.get(F_HOPE)) or "") or None)
        conf = slot_conf * cbm_conf
        is_auto = slot is not None and conf >= 0.8
        disp["AUTO" if is_auto else "수동"] += 1
        if is_auto:
            continue
        # 수동 사유 분류 (우선순위: 슬롯 > CBM)
        if slot is None:
            manual_cause["slot_none(자가수령 등)"] += 1
        elif det["mode"] == "partial_skip":
            manual_cause["partial_skip(다차출하)"] += 1
            act = active_cnt.get(pna, 0)
            if act <= 1:
                ps_recoverable += 1
            else:
                ps_genuine += 1
        elif det["estimated_cbm"] > 0 and cbm_conf < 0.8:
            manual_cause["부분매칭 conf0.7"] += 1
        elif det["estimated_cbm"] <= 0 and slot_conf >= 0.8:
            manual_cause["CBM 미해소(unmatched/no_order)"] += 1
        else:
            manual_cause["슬롯 신뢰도<floor"] += 1

    print("=" * 56)
    print(f"[mode 분포]  {dict(mode_tally)}")
    print(f"[dispatch]   {dict(disp)}  자동화율={disp['AUTO']/max(sum(disp.values()),1)*100:.0f}%")
    print(f"[수동 사유]")
    for k, v in manual_cause.most_common():
        print(f"   {v:>3}  {k}")
    print("-" * 56)
    print(f"partial_skip 중 → active≤1(가짜, 레버1로 즉시복구): {ps_recoverable}건 "
          f"/ active>1(진짜 다차): {ps_genuine}건")
    print("=" * 56)


if __name__ == "__main__":
    main()
