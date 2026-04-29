#!/usr/bin/env python3
"""
WMS AutoResearch Iter 1 — 재고 정확도 기준선
WMS_InventoryLedger vs material(parts-stock) 전산재고 비교
"""
import sys
import os
import time
from datetime import date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

import requests

# ── 인증 / 기본 설정 ─────────────────────────────────────────────────────
PAT     = os.environ.get("AIRTABLE_WMS_PAT") or \
          "***REDACTED_PAT***"
BASE_ID = "appLui4ZR5HWcQRri"
HDRS    = {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}

# ── 테이블 IDs ───────────────────────────────────────────────────────────
TBL_LEDGER = "tbl4DcXQRHJj921MN"   # WMS_InventoryLedger
TBL_MAT    = "tblaRpZstW10EwDlo"   # material(parts-stock)

# ── WMS_InventoryLedger 필드 IDs ─────────────────────────────────────────
F_LED_KEY   = "fldUxFrOMgWewhwuv"   # Ledger_Key
F_LED_MAT   = "fldOD1BqKtTKNGstu"   # Material (multipleRecordLinks)
F_LED_STOCK = "fldrYLzhViYk9xc4P"   # Current_Stock
F_LED_OPEN  = "flde9K3lpJMl3piBN"   # Opening_Qty
F_LED_IN    = "fldMCNFaUBRWgiPQc"   # Total_In
F_LED_OUT   = "fldzeUfyVlEPaaqYf"   # Total_Out
F_LED_WEEK  = "fldK0ivn2inlOaIZU"   # Snapshot_Week

# ── material 필드 IDs ────────────────────────────────────────────────────
F_MAT_CODE  = "fldclYkWLmwrTzuF6"   # 파츠 코드
F_MAT_ELEC  = "fldAFkM4HtGJsitOk"   # 전산재고수량
F_MAT_PHYS  = "fld5XQQv2P9YJZP6n"   # 실물재고수량
F_MAT_AVAIL = "fldZ5qLZKp0yy28So"   # 가용재고수량

# ── 출력 경로 ────────────────────────────────────────────────────────────
TODAY       = date.today().strftime("%Y%m%d")
TODAY_DASH  = date.today().strftime("%Y-%m-%d")
OUT_DIR     = Path("c:/Users/yjisu/Desktop/SCM_WORK/_AutoResearch/WMS/outputs")
LOG_PATH    = Path("c:/Users/yjisu/Desktop/SCM_WORK/_AutoResearch/WMS/wiki/log.md")
REPORT_PATH = OUT_DIR / f"WMS-Iter1-{TODAY}.md"


# ── 유틸: 페이지네이션 ────────────────────────────────────────────────────
def paginate(table_id: str, fields: list[str]) -> list[dict]:
    """Airtable offset 기반 전체 페이지 조회 (returnFieldsByFieldId=true)"""
    url    = f"https://api.airtable.com/v0/{BASE_ID}/{table_id}"
    params = {
        "returnFieldsByFieldId": "true",
        "fields[]": fields,
        "pageSize": 100,
    }
    records = []
    offset  = None
    while True:
        if offset:
            params["offset"] = offset
        resp = requests.get(url, headers=HDRS, params=params)
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        time.sleep(0.2)   # rate-limit 여유
    return records


# ── 데이터 조회 ──────────────────────────────────────────────────────────
def fetch_ledger() -> list[dict]:
    """WMS_InventoryLedger 전체 레코드 조회"""
    print("[fetch_ledger] 조회 중...", flush=True)
    fields = [F_LED_KEY, F_LED_MAT, F_LED_STOCK, F_LED_OPEN,
              F_LED_IN, F_LED_OUT, F_LED_WEEK]
    rows = paginate(TBL_LEDGER, fields)
    print(f"  → {len(rows)}건 수신", flush=True)
    return rows


def fetch_material() -> dict:
    """material 전체 조회 → {record_id: {code, elec, phys, avail}}"""
    print("[fetch_material] 조회 중...", flush=True)
    fields = [F_MAT_CODE, F_MAT_ELEC, F_MAT_PHYS, F_MAT_AVAIL]
    rows   = paginate(TBL_MAT, fields)
    mat_map: dict = {}
    for r in rows:
        f = r.get("fields", {})
        mat_map[r["id"]] = {
            "code":  f.get(F_MAT_CODE, ""),
            "elec":  f.get(F_MAT_ELEC) or 0,
            "phys":  f.get(F_MAT_PHYS) or 0,
            "avail": f.get(F_MAT_AVAIL) or 0,
        }
    print(f"  → {len(mat_map)}건 수신", flush=True)
    return mat_map


# ── 분석 ─────────────────────────────────────────────────────────────────
def analyze(ledger_rows: list, mat_map: dict) -> dict:
    total       = len(ledger_rows)
    neg_stock   = 0
    zero_stock  = 0
    matched     = 0
    mismatch    = 0
    no_mat_link = 0
    deltas      = []   # [{code, ledger, elec, diff}]

    for r in ledger_rows:
        f     = r.get("fields", {})
        stock = f.get(F_LED_STOCK) or 0
        links = f.get(F_LED_MAT, [])   # list of record IDs

        if stock < 0:
            neg_stock += 1
        if stock == 0:
            zero_stock += 1

        if not links:
            no_mat_link += 1
            continue

        mat_id = links[0]
        mat    = mat_map.get(mat_id)
        if mat is None:
            no_mat_link += 1
            continue

        elec = mat["elec"]
        diff = abs(stock - elec)

        if diff == 0:
            matched += 1
        else:
            mismatch += 1
            deltas.append({
                "code":   mat["code"] or mat_id,
                "ledger": stock,
                "elec":   elec,
                "diff":   diff,
            })

    comparable = total - no_mat_link
    accuracy   = round(matched / comparable * 100, 1) if comparable > 0 else 0.0

    top_deltas = sorted(deltas, key=lambda x: x["diff"], reverse=True)[:10]

    return {
        "total":        total,
        "neg_stock":    neg_stock,
        "zero_stock":   zero_stock,
        "matched":      matched,
        "mismatch":     mismatch,
        "no_mat_link":  no_mat_link,
        "accuracy_pct": accuracy,
        "top_deltas":   top_deltas,
    }


# ── 리포트 작성 ───────────────────────────────────────────────────────────
def write_report(res: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    top_rows = ""
    for d in res["top_deltas"]:
        top_rows += f"| {d['code']} | {d['ledger']:,} | {d['elec']:,} | {d['diff']:,} |\n"

    if not top_rows:
        top_rows = "| (불일치 없음) | - | - | - |\n"

    content = f"""# WMS AutoResearch Iter 1 — 재고 정확도 기준선

> 분석일: {TODAY_DASH}  |  스냅샷 기준: WMS_InventoryLedger

## KPI 요약

| 지표 | 값 | 목표 |
|------|-----|------|
| 전체 Ledger 레코드 | {res['total']:,}건 | - |
| 재고 정확도 (Ledger vs 전산) | **{res['accuracy_pct']}%** | ≥95% |
| 음수재고 품목 | {res['neg_stock']:,}건 | 0건 |
| 0재고 품목 | {res['zero_stock']:,}건 | - |
| 일치 품목 | {res['matched']:,}건 | - |
| 불일치 품목 | {res['mismatch']:,}건 | 0건 |
| Material 링크 없음 | {res['no_mat_link']:,}건 | 0건 |

## 불일치 Top 10 (Ledger vs 전산재고)

| PT코드 | Ledger Current | 전산재고 | 차이 |
|--------|---------------|---------|------|
{top_rows}
## 다음 Iter 포커스

- Iter 2: 음수재고 {res['neg_stock']}건 원인 분석 (movement 역추적)
- Iter 3: 불일치 상위 품목 현장 실사 대조
- Iter 4: Wave/PickingTask 피킹 정확도 분석
"""

    REPORT_PATH.write_text(content, encoding="utf-8")
    print(f"[report] 저장 완료: {REPORT_PATH}", flush=True)


# ── 로그 업데이트 ─────────────────────────────────────────────────────────
def update_log(res: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    entry = f"""## [{TODAY_DASH}] ITER1 | 재고 정확도 기준선

**상태:** 완료

### KPI 스냅샷
- 재고 정확도: {res['accuracy_pct']}% (목표 ≥95%)
- 음수재고: {res['neg_stock']}건
- 불일치: {res['mismatch']}건
- 전체 Ledger: {res['total']}건

### 산출물
- [WMS-Iter1-{TODAY}.md](../outputs/WMS-Iter1-{TODAY}.md)

### 다음 포커스
- 음수재고 원인 분석 (Iter 2)

"""

    if LOG_PATH.exists():
        existing = LOG_PATH.read_text(encoding="utf-8")
        today_header = f"## [{TODAY_DASH}] ITER1"
        if today_header in existing:
            print(f"  log.md: 오늘({TODAY_DASH}) 항목 이미 존재 → 스킵", flush=True)
            return
        LOG_PATH.write_text(existing + entry, encoding="utf-8")
    else:
        LOG_PATH.write_text(
            "# WMS AutoResearch — Session Log\n\n" + entry,
            encoding="utf-8",
        )
    print(f"[log] 업데이트 완료: {LOG_PATH}", flush=True)


# ── 메인 ─────────────────────────────────────────────────────────────────
def main() -> None:
    print("=" * 60, flush=True)
    print("WMS AutoResearch Iter 1 — 재고 정확도 기준선", flush=True)
    print("=" * 60, flush=True)

    ledger_rows = fetch_ledger()
    mat_map     = fetch_material()

    print("[analyze] 분석 중...", flush=True)
    res = analyze(ledger_rows, mat_map)

    write_report(res)
    update_log(res)

    # ── 콘솔 KPI 요약 ────────────────────────────────────────────────────
    print("\n" + "=" * 60, flush=True)
    print("KPI 요약", flush=True)
    print("=" * 60, flush=True)
    print(f"  전체 Ledger 레코드 : {res['total']:,}건", flush=True)
    print(f"  재고 정확도        : {res['accuracy_pct']}%  (목표 ≥95%)", flush=True)
    print(f"  음수재고 품목      : {res['neg_stock']:,}건", flush=True)
    print(f"  0재고 품목         : {res['zero_stock']:,}건", flush=True)
    print(f"  일치 품목          : {res['matched']:,}건", flush=True)
    print(f"  불일치 품목        : {res['mismatch']:,}건", flush=True)
    print(f"  Material 링크 없음 : {res['no_mat_link']:,}건", flush=True)

    if res["top_deltas"]:
        top1 = res["top_deltas"][0]
        print(f"\n  불일치 Top1: {top1['code']}  "
              f"Ledger={top1['ledger']:,}  전산={top1['elec']:,}  차이={top1['diff']:,}", flush=True)

    print(f"\n  리포트: {REPORT_PATH}", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    main()
