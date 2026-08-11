"""프리패키징 M/H 추정 백필 — PT별 평균근사 rate + 보수적 ELS 보정으로 미입력 추정.

방법론(2026-08-11): 프리패키징은 글로벌 표준 부재(mh 표준문서 F표) → 자체 ELS 구축.
  est_min = (SETUP + rate × 수량 × fatigue(수량)) × PFD
  - rate  = PT별 Σ(실측소요×인원)/Σ출고수량  (1인 기준 person-min/개, 실측)
  - PFD   = ×1.15  (Personal+Fatigue+Delay — 기존 mh_calculator와 동일)
  - SETUP = 배치 준비 최소분 (소량 record 하한)
  - fatigue(수량) = 대량배치 피로·유휴·재작업 가중 (수량↑ → 페이스↓)
  보수적 방향(계획용). 추정은 `프리패키징_추정=true` 마커로 실측과 구분.
  소요시간·인원수만 씀(MH·MH_1인당 formula 자동). movement 원장(수량/유형/날짜) 미터치.

Usage:
  python scripts/backbone/prepack_mh_backfill.py            # dry-run 측정
  python scripts/backbone/prepack_mh_backfill.py --write     # live PATCH (필드추가 후)
"""
import argparse
import os
import re
import time
from collections import defaultdict

import requests
from dotenv import load_dotenv

load_dotenv()
PAT = os.environ["AIRTABLE_WMS_PAT"]
BASE = "appLui4ZR5HWcQRri"
MOV = "tblwq7Kj5Y9nVjlOw"
VIEW = "프리패키징 M/H"
H = {"Authorization": f"Bearer {PAT}"}
HW = {**H, "Content-Type": "application/json"}
F_SO = "프리패키징_소요시간(분)"
F_IN = "프리패키징_인원수"
F_QTY = "출고수량"
F_ITEM = "이동물품"
F_EST = "프리패키징_추정"   # checkbox (신규 마커)
PT_RE = re.compile(r"PT\d+")

# ── 보수적 ELS 상수 (mh_calculator.py PFD_ALLOWANCE 정합) ──
PFD = 1.15            # Personal+Fatigue+Delay (기존 M/H 계산기와 동일)
SETUP_MIN = 1.5       # 배치 준비 최소분 (자재 셋업) — 소량 record 하한
FATIGUE_KNEE = 200    # 이 출고수량 초과부터 피로 가중 시작
FATIGUE_FULL = 600    # 이 출고수량에서 최대 가중 도달
FATIGUE_MAX = 1.20    # 대량배치 최대 +20% (피로·유휴·재작업)


def fatigue(qty):
    """대량배치 페이스 저하 가중 — knee 이하 1.0, full 이상 FATIGUE_MAX."""
    if qty <= FATIGUE_KNEE:
        return 1.0
    frac = min(1.0, (qty - FATIGUE_KNEE) / (FATIGUE_FULL - FATIGUE_KNEE))
    return 1.0 + (FATIGUE_MAX - 1.0) * frac


def num(x):
    try:
        return float(str(x).replace(",", "") or 0)
    except (ValueError, TypeError):
        return 0.0


def fetch():
    out, off = [], None
    while True:
        p = {"pageSize": 100, "view": VIEW, "fields[]": [F_SO, F_IN, F_QTY, F_ITEM, F_EST]}
        if off:
            p["offset"] = off
        r = requests.get(f"https://api.airtable.com/v0/{BASE}/{MOV}", headers=H, params=p, timeout=90)
        r.raise_for_status()
        d = r.json()
        out += d["records"]
        off = d.get("offset")
        if not off:
            break
    return out


def patch_batch(batch):
    for attempt in range(3):
        try:
            r = requests.patch(f"https://api.airtable.com/v0/{BASE}/{MOV}",
                               headers=HW, json={"records": batch}, timeout=30)
            time.sleep(0.25)
            if r.ok:
                return len(batch), 0
            if r.status_code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(20 * (attempt + 1))
                continue
            print(f"  ERR {r.status_code}: {r.text[:200]}")
            return 0, len(batch)
        except requests.exceptions.ConnectionError:
            if attempt < 2:
                time.sleep(20 * (attempt + 1))
            else:
                return 0, len(batch)
    return 0, len(batch)


def build_patches(recs):
    by_pt = defaultdict(lambda: {"filled": [], "empty": []})
    for r in recs:
        f = r["fields"]
        m = PT_RE.search(str(f.get(F_ITEM) or ""))
        if not m:
            continue
        so, inn, qty = num(f.get(F_SO)), num(f.get(F_IN)), num(f.get(F_QTY))
        is_est = bool(f.get(F_EST))
        rec = {"id": r["id"], "so": so, "inn": inn, "qty": qty}
        if so > 0 and inn > 0 and not is_est:
            by_pt[m.group(0)]["filled"].append(rec)   # 실측만 rate 소스
        elif so <= 0 or is_est:
            by_pt[m.group(0)]["empty"].append(rec)     # 미입력 OR 기존추정 → 재추정
    patches, never = [], 0
    for pt, d in by_pt.items():
        if not d["filled"]:
            never += len(d["empty"])
            continue
        q = sum(x["qty"] for x in d["filled"])
        if q <= 0:
            continue
        rate = sum(x["so"] * x["inn"] for x in d["filled"]) / q   # person-min/개 (1인 기준, 실측)
        for e in d["empty"]:
            op = rate * e["qty"] * fatigue(e["qty"])               # 운영시간 + 대량 피로가중
            est = round((SETUP_MIN + op) * PFD, 2)                 # + 셋업하한, × PFD (보수적)
            if est <= 0:
                continue
            patches.append({"id": e["id"], "fields": {F_SO: est, F_IN: 1, F_EST: True}})
    return patches, never


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="live PATCH (필드추가 후)")
    args = ap.parse_args()
    recs = fetch()
    patches, never = build_patches(recs)
    print(f"프리패키징 M/H 뷰 {len(recs)}건 · 추정 백필 대상 {len(patches)}건 · never-measured {never}건")

    if not args.write:
        print("\n샘플(상위 8):")
        for p in patches[:8]:
            print(f"  {p['id']}  소요={p['fields'][F_SO]:>7}분  인원=1  추정=✓")
        print("\n[DRY-RUN] 쓰기 0. 필드 '프리패키징_추정'(checkbox) 추가 후 --write 로 실행.")
        return

    ok = err = 0
    for i in range(0, len(patches), 10):
        o, e = patch_batch(patches[i:i + 10])
        ok += o
        err += e
        print(f"  patched {ok}/{len(patches)} (err {err})", flush=True)
    print(f"\n[WRITE] 추정 {ok}건 · err {err}. 소요시간·인원만 기록, MH formula 자동계산, 원장 미터치.")


if __name__ == "__main__":
    main()
