# WMS 백필 + AutoResearch Iter 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** logistics_release 기반 Wave/PickingTask 백필, movement 기반 NCR 백필, WMS 재고 정확도 기준선 분석(Iter 1) 완료

**Architecture:** 3개의 독립 Python 스크립트(`wms/` 폴더) + 1개 AutoResearch 분석 출력. 각 스크립트는 Airtable REST API로 소스 테이블을 읽고 WMS 타겟 테이블에 INSERT-ONLY로 기록. AutoResearch는 현재 Ledger와 material 테이블을 교차 분석해 KPI를 Markdown으로 출력.

**Tech Stack:** Python 3, requests, Airtable REST API (WMS Base: appLui4ZR5HWcQRri)

---

## 공통 상수 참조

```python
# WMS Base
PAT    = "***REDACTED_PAT***"
BASE   = "appLui4ZR5HWcQRri"
HDRS   = {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}
API    = "https://api.airtable.com/v0"

# Table IDs
TBL_LR       = "tbler5LBLxh8lcEPv"   # ⚡logistics_release
TBL_MATERIAL = "tblaRpZstW10EwDlo"   # ⚡material(parts-stock)
TBL_MOVEMENT = "tblwq7Kj5Y9nVjlOw"   # ⚡movement
TBL_WAVE     = "tblZucobzQu3CFCrR"   # WMS_Wave
TBL_TASK     = "tblJpQcCJfIyB9Xf5"   # WMS_PickingTask
TBL_NCR      = "tblMODxFEWpkKWG4Y"   # WMS_NCR
TBL_LEDGER   = "tbl4DcXQRHJj921MN"   # WMS_InventoryLedger

# logistics_release 필드
F_LR_STATUS  = "fldqASGdE4wr2zOxG"   # 발송 상태 (singleSelect)
F_LR_DATE    = "fldd30xmwJZgneRmT"   # 출고 요청일 (date)
F_LR_ITEMS   = "flddjsAgwAYNtwOnI"   # 출고 품목 및 수량 (multilineText)
F_LR_NAME    = "fldV4FMACOiYCv088"   # 프로젝트명 (multilineText)
F_LR_COORD   = "fldmqLhLpuJbaLeeT"   # 출고 좌표 (multipleSelects)

# WMS_Wave 필드
F_WAV_ID     = "fldqOrsNaAqA0ttVb"
F_WAV_DATE   = "fldmTk2tlepvAzu42"
F_WAV_STATUS = "fldCwSRWdBEMvJEpk"
F_WAV_OCNT   = "fldAF5vlawqBc4Yf8"   # Order_Count
F_WAV_LINES  = "fldldYw6tmfxu70hk"   # Total_Lines
F_WAV_DONE   = "fldPTz5QyVWFDZmJp"   # Completed_Lines
F_WAV_REF    = "fldUyvsHfOLYaXm4J"   # Order_Ref
F_WAV_RATE   = "fldMb9S6CnjfZTQo5"   # Completion_Rate

# WMS_PickingTask 필드
F_TSK_ID     = "fld7oUeh7JTfBPutp"
F_TSK_WAVE   = "fldYkQ0W3lMEPEDEs"   # Wave_Link
F_TSK_MAT    = "fld3udgtMClXamgt1"   # Material
F_TSK_LOC    = "fldZkfusqTJ7J7Dy6"   # From_Location
F_TSK_RQTY   = "fldu9uAidbUMwVtYe"   # Required_Qty
F_TSK_PQTY   = "fldOnjDaEYQHbTVFb"   # Picked_Qty
F_TSK_STATUS = "fldkpOdJUUY4HUUXA"   # Status
F_TSK_METHOD = "fldnK5MEcV1VU2IkA"   # Pick_Method

# WMS_NCR 필드
F_NCR_ID     = "fld93Fagb87nX8koG"
F_NCR_MAT    = "fldCJ7kIxQWo5DYju"
F_NCR_CODE   = "fldywyXZbxkgY5FUR"   # Defect_Code
F_NCR_QTY    = "fldhBzrL7jx7TEbon"   # Defect_Qty
F_NCR_DATE   = "fldliElDm2UTh2QMm"   # Detection_Date
F_NCR_DISP   = "fld6w8QPuPER9pmvV"   # Disposition
F_NCR_STAT   = "fldI2sJOYXfVrwyds"   # Status
F_NCR_CAUSE  = "fldlDAIF5BcORPGMb"   # Root_Cause

# movement QC 필드
F_MV_ID      = "fldOhFtJFBYsxxre7"   # movement_id
F_MV_ITEMS   = "fldwZKCYZ4IFOigRp"   # 이동물품 (PT코드 추출)
F_MV_DATE    = "fldDXUAF4JOORLJ2v"   # 생성일자
F_MV_QC_CHK  = "fld9eE4YZZWTDsfUC"   # 품질 이슈 리포팅 (checkbox)
F_MV_QC_SMPL = "fld3lQvblfrqTl4O8"   # 불량수량_샘플링검수
F_MV_QC_FULL = "fldsTXzxUeerw4qw2"   # 불량수량_전수검수
F_MV_QC_NOTE = "fld0ZtsqLg4HIM4zg"   # 품질이슈내용
F_MV_QC_TYPE = "fldhah8PRdngeDvYY"   # 품질이슈내용구분 (singleSelect)

# material 필드
F_MAT_CODE   = "fldclYkWLmwrTzuF6"   # 파츠 코드
F_MAT_ELEC   = "fldAFkM4HtGJsitOk"   # 전산재고수량
F_MAT_PHYS   = "fld5XQQv2P9YJZP6n"   # 실물재고수량
F_MAT_AVAIL  = "fldZ5qLZKp0yy28So"   # 가용재고수량

# WMS_Location record IDs
LOC_BW_IB  = "recf2n4NG79Q8dh2E"   # BW01-IB-001
LOC_BW_ST  = "recN8X0ZsGL75xb0Q"   # BW01-ST-A01
LOC_BW_OB  = "recBoNW2ElQ3ndsQi"   # BW01-OB-001
LOC_A1_ST  = "recwIY0TxRPA6gNRz"   # A1-ST-A01
```

---

## File Structure

```
wms/
  backfill_wave_pickingtask.py   ← Task 1 신규 생성
  backfill_ncr.py                ← Task 2 신규 생성

scripts/
  wms_autoResearch_iter1.py      ← Task 3 신규 생성

_AutoResearch/WMS/
  wiki/log.md                    ← Task 3 업데이트
  outputs/WMS-Iter1-YYYYMMDD.md  ← Task 3 생성
```

---

## Task 1: WMS_Wave + WMS_PickingTask 백필

**파일:** `wms/backfill_wave_pickingtask.py` (신규)

**로직:**
- logistics_release에서 `발송 상태 = "출하 완료"` 레코드 조회
- 레코드당 1개 Wave 생성 (Wave_Date = 출고 요청일, Status = COMPLETED)
- `출고 품목 및 수량` 파싱 → PT코드 추출 → material 테이블에서 record_id 조회 → PickingTask 생성
- Wave.WMS_PickingTask 필드는 linked field (read-only 방향) → Task에서 Wave_Link만 연결하면 자동 역연결

**주의:** `출고 품목 및 수량`은 자유 텍스트(multilineText). 형식이 일정하지 않을 수 있으므로 dry-run 먼저 실행.

- [ ] **Step 1: dry-run — logistics_release 출하 완료 건 조회 및 품목 필드 형식 파악**

```python
# 스크립트 상단에서 먼저 실행할 dry-run 블록
import sys, requests, time, re
sys.stdout.reconfigure(encoding="utf-8")

PAT  = "***REDACTED_PAT***"
BASE = "appLui4ZR5HWcQRri"
HDRS = {"Authorization": f"Bearer {PAT}"}

def paginate(tbl, params):
    records, offset = [], None
    while True:
        p = {**params, **({"offset": offset} if offset else {})}
        r = requests.get(f"https://api.airtable.com/v0/{BASE}/{tbl}", headers=HDRS, params=p)
        r.raise_for_status()
        d = r.json()
        records.extend(d.get("records", []))
        offset = d.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records

recs = paginate("tbler5LBLxh8lcEPv", {
    "filterByFormula": '{발송 상태}="출하 완료"',
    "returnFieldsByFieldId": "true",
    "fields[]": ["fldqASGdE4wr2zOxG", "fldd30xmwJZgneRmT",
                 "flddjsAgwAYNtwOnI", "fldV4FMACOiYCv088"],
    "pageSize": 100,
})
print(f"출하 완료 건: {len(recs)}")
for rec in recs[:5]:
    f = rec["fields"]
    print(f"  날짜={f.get('fldd30xmwJZgneRmT','')}  품목수량={repr(f.get('flddjsAgwAYNtwOnI',''))[:80]}")
```

실행: `python3 wms/backfill_wave_pickingtask.py --dry-run`
확인: 출하 완료 건 수 + `출고 품목 및 수량` 필드 실제 형식 출력

- [ ] **Step 2: PT코드 파서 작성**

`출고 품목 및 수량` 예시 형식:
```
PT1234 - 품목명 (10개)
PT5678 30개
```
정확한 형식은 dry-run 결과 보고 결정. 기본 파서:

```python
import re

PT_PATTERN = re.compile(r"(PT\d+)")
QTY_PATTERN = re.compile(r"(\d+)\s*(?:개|EA|ea|pcs)?")

def parse_line_items(text: str) -> list[dict]:
    """출고 품목 및 수량 multilineText → [{pt_code, qty}] 리스트
    PT코드 없는 줄은 무시. qty 파싱 실패 시 qty=0."""
    if not text:
        return []
    items = []
    for line in str(text).splitlines():
        line = line.strip()
        if not line:
            continue
        pt_match = PT_PATTERN.search(line)
        if not pt_match:
            continue
        pt_code = pt_match.group(1)
        # PT코드 뒤의 숫자를 수량으로
        after_pt = line[pt_match.end():]
        qty_match = QTY_PATTERN.search(after_pt)
        qty = int(qty_match.group(1)) if qty_match else 0
        items.append({"pt_code": pt_code, "qty": qty})
    return items
```

- [ ] **Step 3: material PT코드 → record_id 맵 빌드**

```python
def build_material_map() -> dict:
    """PT코드 → material record_id 매핑"""
    recs = paginate("tblaRpZstW10EwDlo", {
        "returnFieldsByFieldId": "true",
        "fields[]": ["fldclYkWLmwrTzuF6"],  # 파츠 코드
        "pageSize": 100,
    })
    pt_map = {}
    for r in recs:
        code = r["fields"].get("fldclYkWLmwrTzuF6", "")
        if code and re.match(r"^PT\d+", str(code)):
            pt_map[str(code).split("-")[0].strip()] = r["id"]
    print(f"  material PT맵: {len(pt_map)}건")
    return pt_map
```

- [ ] **Step 4: Wave + PickingTask 생성 함수 작성 및 전체 스크립트 완성**

파일: `wms/backfill_wave_pickingtask.py`

```python
#!/usr/bin/env python3
"""
WMS_Wave + WMS_PickingTask 백필
logistics_release에서 발송 상태="출하 완료" 건 → Wave 1개 + PickingTask N개 생성
"""
import sys, requests, time, re, argparse
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8")

PAT    = "***REDACTED_PAT***"
BASE   = "appLui4ZR5HWcQRri"
HDRS   = {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}

TBL_LR   = "tbler5LBLxh8lcEPv"
TBL_MAT  = "tblaRpZstW10EwDlo"
TBL_WAVE = "tblZucobzQu3CFCrR"
TBL_TASK = "tblJpQcCJfIyB9Xf5"

F_LR_STATUS = "fldqASGdE4wr2zOxG"
F_LR_DATE   = "fldd30xmwJZgneRmT"
F_LR_ITEMS  = "flddjsAgwAYNtwOnI"
F_LR_NAME   = "fldV4FMACOiYCv088"

F_WAV_ID    = "fldqOrsNaAqA0ttVb"
F_WAV_DATE  = "fldmTk2tlepvAzu42"
F_WAV_STAT  = "fldCwSRWdBEMvJEpk"
F_WAV_OCNT  = "fldAF5vlawqBc4Yf8"
F_WAV_LINES = "fldldYw6tmfxu70hk"
F_WAV_DONE  = "fldPTz5QyVWFDZmJp"
F_WAV_REF   = "fldUyvsHfOLYaXm4J"
F_WAV_RATE  = "fldMb9S6CnjfZTQo5"

F_TSK_ID    = "fld7oUeh7JTfBPutp"
F_TSK_WAVE  = "fldYkQ0W3lMEPEDEs"
F_TSK_MAT   = "fld3udgtMClXamgt1"
F_TSK_LOC   = "fldZkfusqTJ7J7Dy6"
F_TSK_RQTY  = "fldu9uAidbUMwVtYe"
F_TSK_PQTY  = "fldOnjDaEYQHbTVFb"
F_TSK_STAT  = "fldkpOdJUUY4HUUXA"
F_TSK_METH  = "fldnK5MEcV1VU2IkA"

LOC_BW_OB  = "recBoNW2ElQ3ndsQi"   # BW01-OB-001 (출고 기본 위치)
F_MAT_CODE = "fldclYkWLmwrTzuF6"

PT_RE  = re.compile(r"(PT\d+)")
QTY_RE = re.compile(r"(\d+)")


def paginate(tbl, params):
    records, offset = [], None
    while True:
        p = {**params, **({"offset": offset} if offset else {})}
        r = requests.get(f"https://api.airtable.com/v0/{BASE}/{tbl}",
                         headers={"Authorization": f"Bearer {PAT}"}, params=p)
        r.raise_for_status()
        d = r.json()
        records.extend(d.get("records", []))
        offset = d.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records


def batch_post(tbl, rows):
    url = f"https://api.airtable.com/v0/{BASE}/{tbl}"
    ok, created_ids = 0, []
    for i in range(0, len(rows), 10):
        chunk = rows[i:i+10]
        r = requests.post(url, headers=HDRS, json={"records": [{"fields": row} for row in chunk]})
        if r.ok:
            ok += len(chunk)
            created_ids.extend([rec["id"] for rec in r.json().get("records", [])])
        else:
            print(f"  !! POST 실패: {r.status_code} {r.text[:200]}")
        time.sleep(0.25)
    return ok, created_ids


def parse_items(text: str) -> list:
    if not text:
        return []
    items = []
    for line in str(text).splitlines():
        line = line.strip()
        if not line:
            continue
        pt_m = PT_RE.search(line)
        if not pt_m:
            continue
        pt_code = pt_m.group(1)
        after = line[pt_m.end():]
        qty_m = QTY_RE.search(after)
        qty = int(qty_m.group(1)) if qty_m else 1
        items.append({"pt_code": pt_code, "qty": qty})
    return items


def build_material_map() -> dict:
    recs = paginate(TBL_MAT, {
        "returnFieldsByFieldId": "true",
        "fields[]": [F_MAT_CODE],
        "pageSize": 100,
    })
    pt_map = {}
    for r in recs:
        code = str(r["fields"].get(F_MAT_CODE, "") or "").strip()
        if re.match(r"^PT\d+", code):
            pt_map[code.split("-")[0].strip()] = r["id"]
    return pt_map


def main(dry_run=False):
    print("=" * 60)
    print("WMS_Wave + WMS_PickingTask 백필")
    print(f"Mode: {'DRY-RUN' if dry_run else 'LIVE'}")
    print("=" * 60)

    # 1. logistics_release 출하 완료 건 조회
    print("\n[1] logistics_release 출하 완료 조회...")
    lr_recs = paginate(TBL_LR, {
        "filterByFormula": '{발송 상태}="출하 완료"',
        "returnFieldsByFieldId": "true",
        "fields[]": [F_LR_STATUS, F_LR_DATE, F_LR_ITEMS, F_LR_NAME],
        "pageSize": 100,
    })
    print(f"  대상: {len(lr_recs)}건")

    # dry-run: 품목 필드 형식 출력
    if dry_run:
        print("\n  [DRY] 샘플 품목 필드 형식:")
        for rec in lr_recs[:10]:
            items_txt = rec["fields"].get(F_LR_ITEMS, "")
            parsed = parse_items(items_txt)
            print(f"  날짜={rec['fields'].get(F_LR_DATE,'?')} | "
                  f"raw={repr(items_txt)[:60]} | parsed={parsed}")
        return

    # 2. material 맵 빌드
    print("\n[2] material PT맵 빌드...")
    pt_map = build_material_map()
    print(f"  PT코드 {len(pt_map)}건")

    # 3. Wave + PickingTask 생성
    print("\n[3] Wave + PickingTask 생성...")
    date_counter = defaultdict(int)
    task_counter = defaultdict(int)
    total_waves = total_tasks = 0
    skipped = 0

    for rec in lr_recs:
        f = rec["fields"]
        lr_date = f.get(F_LR_DATE, "")
        if not lr_date:
            skipped += 1
            continue

        dk = lr_date.replace("-", "")
        date_counter[dk] += 1
        wave_id = f"WAV-{dk}-{date_counter[dk]:03d}"

        items_txt = f.get(F_LR_ITEMS, "")
        line_items = parse_items(items_txt)
        n_lines = len(line_items)

        wave_row = {
            F_WAV_ID:    wave_id,
            F_WAV_DATE:  lr_date,
            F_WAV_STAT:  "COMPLETED",
            F_WAV_OCNT:  1,
            F_WAV_LINES: n_lines,
            F_WAV_DONE:  n_lines,
            F_WAV_REF:   rec["id"],
            F_WAV_RATE:  100.0 if n_lines > 0 else 0.0,
        }
        _, wave_ids = batch_post(TBL_WAVE, [wave_row])
        if not wave_ids:
            print(f"  !! Wave 생성 실패: {wave_id}")
            continue
        wave_rec_id = wave_ids[0]
        total_waves += 1

        # PickingTask 생성
        task_rows = []
        for item in line_items:
            task_counter[dk] += 1
            task_id = f"TSK-{dk}-{task_counter[dk]:03d}"
            mat_id = pt_map.get(item["pt_code"])
            row = {
                F_TSK_ID:   task_id,
                F_TSK_WAVE: [wave_rec_id],
                F_TSK_LOC:  [LOC_BW_OB],
                F_TSK_RQTY: item["qty"],
                F_TSK_PQTY: item["qty"],
                F_TSK_STAT: "COMPLETED",
                F_TSK_METH: "FIFO",
            }
            if mat_id:
                row[F_TSK_MAT] = [mat_id]
            task_rows.append(row)

        if task_rows:
            ok, _ = batch_post(TBL_TASK, task_rows)
            total_tasks += ok

    print(f"\n완료: Wave {total_waves}건 | PickingTask {total_tasks}건 | 스킵 {skipped}건")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
```

- [ ] **Step 5: dry-run 실행 → 품목 필드 형식 확인**

```bash
cd c:/Users/yjisu/Desktop/SCM_WORK
python3 wms/backfill_wave_pickingtask.py --dry-run
```

기대 출력: 출하 완료 건 수 + 품목 필드 raw 형식 샘플 10건
→ PT_RE, QTY_RE 파서가 올바르게 파싱하는지 확인
→ 파싱 실패 시 parse_items() 정규식 수정 후 재실행

- [ ] **Step 6: live 실행**

```bash
python3 wms/backfill_wave_pickingtask.py
```

기대: Wave N건 + PickingTask M건 생성 완료 출력

- [ ] **Step 7: Airtable 확인 + 커밋**

Airtable WMS_Wave 테이블에서 WAV-* 레코드 확인
WMS_PickingTask에서 TSK-* 레코드 + Wave_Link 연결 확인

```bash
git add wms/backfill_wave_pickingtask.py
git commit -m "feat: WMS_Wave + WMS_PickingTask 백필 (logistics_release 출하완료 기반)"
```

---

## Task 2: WMS_NCR 백필

**파일:** `wms/backfill_ncr.py` (신규)

**로직:**
- movement에서 `품질 이슈 리포팅` checkbox = TRUE 건 조회
- 불량수량 = 불량수량_전수검수 or 불량수량_샘플링검수 (전수 우선)
- Defect_Code 매핑: 품질이슈내용구분 singleSelect → QC-001~007
- PT코드 추출 → material 연결
- Disposition = ACCEPT_AS_IS (기본), Status = CLOSED

- [ ] **Step 1: movement QC 건 수 확인**

```python
import sys, requests
sys.stdout.reconfigure(encoding="utf-8")
PAT  = "***REDACTED_PAT***"
BASE = "appLui4ZR5HWcQRri"
HDRS = {"Authorization": f"Bearer {PAT}"}

# checkbox=TRUE 필터 (Airtable formula에서 checkbox는 값 자체가 true/1)
r = requests.get(f"https://api.airtable.com/v0/{BASE}/tblwq7Kj5Y9nVjlOw",
    headers=HDRS,
    params={
        "filterByFormula": "{품질 이슈 리포팅}",   # checkbox TRUE 조건
        "returnFieldsByFieldId": "true",
        "fields[]": ["fld9eE4YZZWTDsfUC", "fld0ZtsqLg4HIM4zg", "fldhah8PRdngeDvYY"],
        "pageSize": 5,
    })
recs = r.json().get("records", [])
print(f"QC 이슈 건 (샘플): {len(recs)}")
for rec in recs:
    print(f"  {rec['fields']}")
```

실행해서 건수 확인. 0이면 필터 공식 수정:
- 대안 1: `"filterByFormula": '{품질 이슈 리포팅}=TRUE()'`
- 대안 2: `"filterByFormula": '{품질 이슈 리포팅}=1'`

- [ ] **Step 2: 전체 스크립트 작성**

파일: `wms/backfill_ncr.py`

```python
#!/usr/bin/env python3
"""
WMS_NCR 백필
movement 테이블의 품질이슈 건 → WMS_NCR 레코드 생성
"""
import sys, requests, time, re
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8")

PAT    = "***REDACTED_PAT***"
BASE   = "appLui4ZR5HWcQRri"
HDRS   = {"Authorization": f"Bearer {PAT}", "Content-Type": "application/json"}

TBL_MV  = "tblwq7Kj5Y9nVjlOw"
TBL_MAT = "tblaRpZstW10EwDlo"
TBL_NCR = "tblMODxFEWpkKWG4Y"

F_MV_ITEMS   = "fldwZKCYZ4IFOigRp"
F_MV_DATE    = "fldDXUAF4JOORLJ2v"
F_MV_QC_CHK  = "fld9eE4YZZWTDsfUC"
F_MV_QC_SMPL = "fld3lQvblfrqTl4O8"
F_MV_QC_FULL = "fldsTXzxUeerw4qw2"
F_MV_QC_NOTE = "fld0ZtsqLg4HIM4zg"
F_MV_QC_TYPE = "fldhah8PRdngeDvYY"

F_NCR_ID    = "fld93Fagb87nX8koG"
F_NCR_MAT   = "fldCJ7kIxQWo5DYju"
F_NCR_CODE  = "fldywyXZbxkgY5FUR"
F_NCR_QTY   = "fldhBzrL7jx7TEbon"
F_NCR_DATE  = "fldliElDm2UTh2QMm"
F_NCR_DISP  = "fld6w8QPuPER9pmvV"
F_NCR_STAT  = "fldI2sJOYXfVrwyds"
F_NCR_CAUSE = "fldlDAIF5BcORPGMb"

F_MAT_CODE  = "fldclYkWLmwrTzuF6"
PT_RE = re.compile(r"(PT\d+)")

# 품질이슈내용구분 → Defect_Code 매핑
DEFECT_MAP = {
    "수량":   "QC-001 수량부족",
    "외관":   "QC-002 외관불량",
    "규격":   "QC-003 규격불일치",
    "오염":   "QC-004 오염·이물",
    "이물":   "QC-004 오염·이물",
    "인쇄":   "QC-005 인쇄불량",
    "색상":   "QC-005 인쇄불량",
    "포장":   "QC-006 포장불량",
    "박스":   "QC-006 포장불량",
}

def map_defect(type_val, note_val) -> str:
    combined = f"{type_val or ''} {note_val or ''}"
    for key, code in DEFECT_MAP.items():
        if key in combined:
            return code
    return "QC-007 기타"


def paginate(tbl, params):
    records, offset = [], None
    while True:
        p = {**params, **({"offset": offset} if offset else {})}
        r = requests.get(f"https://api.airtable.com/v0/{BASE}/{tbl}",
                         headers={"Authorization": f"Bearer {PAT}"}, params=p)
        r.raise_for_status()
        d = r.json()
        records.extend(d.get("records", []))
        offset = d.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records


def batch_post(tbl, rows):
    url = f"https://api.airtable.com/v0/{BASE}/{tbl}"
    ok = 0
    for i in range(0, len(rows), 10):
        chunk = rows[i:i+10]
        r = requests.post(url, headers=HDRS, json={"records": [{"fields": row} for row in chunk]})
        if r.ok:
            ok += len(chunk)
        else:
            print(f"  !! POST 실패: {r.status_code} {r.text[:200]}")
        time.sleep(0.25)
    return ok


def build_material_map() -> dict:
    recs = paginate(TBL_MAT, {
        "returnFieldsByFieldId": "true",
        "fields[]": [F_MAT_CODE],
        "pageSize": 100,
    })
    return {
        str(r["fields"].get(F_MAT_CODE, "")).split("-")[0].strip(): r["id"]
        for r in recs
        if re.match(r"^PT\d+", str(r["fields"].get(F_MAT_CODE, "") or ""))
    }


def main():
    print("=" * 60)
    print("WMS_NCR 백필")
    print("=" * 60)

    # 1. QC 이슈 movement 조회
    print("\n[1] 품질이슈 movement 조회...")
    qc_recs = paginate(TBL_MV, {
        "filterByFormula": "{품질 이슈 리포팅}",
        "returnFieldsByFieldId": "true",
        "fields[]": [F_MV_ITEMS, F_MV_DATE, F_MV_QC_CHK,
                     F_MV_QC_SMPL, F_MV_QC_FULL, F_MV_QC_NOTE, F_MV_QC_TYPE],
        "pageSize": 100,
    })
    print(f"  QC 이슈 건: {len(qc_recs)}건")

    if not qc_recs:
        print("  대상 없음 — 종료")
        return

    # 2. material 맵
    print("\n[2] material PT맵 빌드...")
    pt_map = build_material_map()

    # 3. NCR 생성
    print("\n[3] NCR 레코드 생성...")
    date_counter = defaultdict(int)
    rows = []
    skipped = 0

    for rec in qc_recs:
        f = rec["fields"]
        created_at = str(f.get(F_MV_DATE, "") or "")[:10]
        if not created_at:
            skipped += 1
            continue

        dk = created_at.replace("-", "")
        date_counter[dk] += 1
        ncr_id = f"NCR-{dk}-{date_counter[dk]:04d}"

        defect_qty = (f.get(F_MV_QC_FULL) or f.get(F_MV_QC_SMPL) or 0)
        type_val = f.get(F_MV_QC_TYPE, "")
        if isinstance(type_val, dict):
            type_val = type_val.get("name", "")
        note_val = f.get(F_MV_QC_NOTE, "")

        pt_text = str(f.get(F_MV_ITEMS, "") or "")
        pt_m = PT_RE.search(pt_text)
        pt_code = pt_m.group(1) if pt_m else None
        mat_id = pt_map.get(pt_code) if pt_code else None

        row = {
            F_NCR_ID:    ncr_id,
            F_NCR_CODE:  map_defect(type_val, note_val),
            F_NCR_QTY:   defect_qty,
            F_NCR_DATE:  created_at,
            F_NCR_DISP:  "ACCEPT_AS_IS",
            F_NCR_STAT:  "CLOSED",
            F_NCR_CAUSE: str(note_val)[:500],
        }
        if mat_id:
            row[F_NCR_MAT] = [mat_id]
        rows.append(row)

    print(f"  생성 예정: {len(rows)}건 | 스킵: {skipped}건")
    ok = batch_post(TBL_NCR, rows)
    print(f"  완료: {ok}/{len(rows)}건")
    print("=" * 60)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 실행**

```bash
python3 wms/backfill_ncr.py
```

기대: NCR N건 생성 완료
→ 0건이면 filterByFormula를 `{품질 이슈 리포팅}=1` 또는 `{품질 이슈 리포팅}=TRUE()`로 변경 후 재실행

- [ ] **Step 4: 커밋**

```bash
git add wms/backfill_ncr.py
git commit -m "feat: WMS_NCR 백필 (movement QC 이슈 건 기반)"
```

---

## Task 3: AutoResearch WMS Iter 1 — 재고 정확도 기준선

**파일:** `scripts/wms_autoResearch_iter1.py` (신규)

**분석 범위:**
- WMS_InventoryLedger 현재 재고(Current_Stock) vs material 전산재고수량 비교
- KPI: 재고 정확도 %, 음수재고 건수, 불일치 건수, 0재고 품목
- 출력: `_AutoResearch/WMS/outputs/WMS-Iter1-YYYYMMDD.md`
- log.md 업데이트

**사전 준비 (최초 1회):**
```bash
mkdir -p "_AutoResearch/WMS/wiki"
mkdir -p "_AutoResearch/WMS/outputs"
```

- [ ] **Step 1: Ledger + material 데이터 조회 함수 작성**

파일: `scripts/wms_autoResearch_iter1.py`

```python
#!/usr/bin/env python3
"""
WMS AutoResearch Iter 1 — 재고 정확도 기준선 분석
WMS_InventoryLedger Current_Stock vs material 전산/실물재고 비교
"""
import sys, requests, time, re
from datetime import date, datetime
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")

PAT    = "***REDACTED_PAT***"
BASE   = "appLui4ZR5HWcQRri"
HDRS   = {"Authorization": f"Bearer {PAT}"}

TBL_LEDGER = "tbl4DcXQRHJj921MN"
TBL_MAT    = "tblaRpZstW10EwDlo"

# WMS_InventoryLedger 필드
F_LED_KEY   = "fldUxFrOMgWewhwuv"   # Ledger_Key
F_LED_MAT   = "fldOD1BqKtTKNGstu"   # Material (link)
F_LED_STOCK = "fldrYLzhViYk9xc4P"   # Current_Stock
F_LED_OPEN  = "flde9K3lpJMl3piBN"   # Opening_Qty
F_LED_IN    = "fldMCNFaUBRWgiPQc"   # Total_In
F_LED_OUT   = "fldzeUfyVlEPaaqYf"   # Total_Out
F_LED_WEEK  = "fldK0ivn2inlOaIZU"   # Snapshot_Week

# material 필드
F_MAT_CODE  = "fldclYkWLmwrTzuF6"
F_MAT_ELEC  = "fldAFkM4HtGJsitOk"   # 전산재고수량
F_MAT_PHYS  = "fld5XQQv2P9YJZP6n"   # 실물재고수량
F_MAT_AVAIL = "fldZ5qLZKp0yy28So"   # 가용재고수량

OUTPUT_DIR = Path("_AutoResearch/WMS/outputs")
LOG_FILE   = Path("_AutoResearch/WMS/wiki/log.md")


def paginate(tbl, params):
    records, offset = [], None
    while True:
        p = {**params, **({"offset": offset} if offset else {})}
        r = requests.get(f"https://api.airtable.com/v0/{BASE}/{tbl}", headers=HDRS, params=p)
        r.raise_for_status()
        d = r.json()
        records.extend(d.get("records", []))
        offset = d.get("offset")
        if not offset:
            break
        time.sleep(0.2)
    return records


def fetch_ledger():
    recs = paginate(TBL_LEDGER, {
        "returnFieldsByFieldId": "true",
        "fields[]": [F_LED_KEY, F_LED_MAT, F_LED_STOCK, F_LED_OPEN, F_LED_IN, F_LED_OUT, F_LED_WEEK],
        "pageSize": 100,
    })
    return [{"id": r["id"], **r["fields"]} for r in recs]


def fetch_material():
    recs = paginate(TBL_MAT, {
        "returnFieldsByFieldId": "true",
        "fields[]": [F_MAT_CODE, F_MAT_ELEC, F_MAT_PHYS, F_MAT_AVAIL],
        "pageSize": 100,
    })
    result = {}
    for r in recs:
        code = str(r["fields"].get(F_MAT_CODE, "") or "").split("-")[0].strip()
        if re.match(r"^PT\d+", code):
            result[r["id"]] = {
                "code":  code,
                "elec":  r["fields"].get(F_MAT_ELEC, 0) or 0,
                "phys":  r["fields"].get(F_MAT_PHYS, 0) or 0,
                "avail": r["fields"].get(F_MAT_AVAIL, 0) or 0,
            }
    return result


def analyze(ledger_rows, mat_map):
    total = len(ledger_rows)
    neg_stock = 0
    zero_stock = 0
    matched = 0
    mismatch = 0
    no_mat_link = 0
    deltas = []

    for row in ledger_rows:
        current = row.get(F_LED_STOCK, 0) or 0
        if current < 0:
            neg_stock += 1
        if current == 0:
            zero_stock += 1

        mat_links = row.get(F_LED_MAT, [])
        if not mat_links:
            no_mat_link += 1
            continue

        mat_id = mat_links[0] if isinstance(mat_links, list) else mat_links
        mat = mat_map.get(mat_id)
        if not mat:
            no_mat_link += 1
            continue

        elec = mat["elec"]
        diff = abs(current - elec)
        if diff == 0:
            matched += 1
        else:
            mismatch += 1
            deltas.append({"code": mat["code"], "ledger": current, "elec": elec, "diff": diff})

    accuracy = round(matched / max(total - no_mat_link, 1) * 100, 1)
    deltas.sort(key=lambda x: x["diff"], reverse=True)

    return {
        "total":        total,
        "neg_stock":    neg_stock,
        "zero_stock":   zero_stock,
        "matched":      matched,
        "mismatch":     mismatch,
        "no_mat_link":  no_mat_link,
        "accuracy_pct": accuracy,
        "top_deltas":   deltas[:10],
    }


def write_report(kpi: dict):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().strftime("%Y%m%d")
    out_file = OUTPUT_DIR / f"WMS-Iter1-{today}.md"

    lines = [
        f"# WMS AutoResearch Iter 1 — 재고 정확도 기준선",
        f"",
        f"> 분석일: {date.today().isoformat()}  |  스냅샷 기준: WMS_InventoryLedger",
        f"",
        f"## KPI 요약",
        f"",
        f"| 지표 | 값 | 목표 |",
        f"|------|-----|------|",
        f"| 전체 Ledger 레코드 | {kpi['total']}건 | - |",
        f"| 재고 정확도 (Ledger vs 전산) | **{kpi['accuracy_pct']}%** | ≥95% |",
        f"| 음수재고 품목 | {kpi['neg_stock']}건 | 0건 |",
        f"| 0재고 품목 | {kpi['zero_stock']}건 | - |",
        f"| 일치 품목 | {kpi['matched']}건 | - |",
        f"| 불일치 품목 | {kpi['mismatch']}건 | 0건 |",
        f"| Material 링크 없음 | {kpi['no_mat_link']}건 | 0건 |",
        f"",
        f"## 불일치 Top 10 (Ledger vs 전산재고)",
        f"",
        f"| PT코드 | Ledger Current | 전산재고 | 차이 |",
        f"|--------|---------------|---------|------|",
    ]
    for d in kpi["top_deltas"]:
        lines.append(f"| {d['code']} | {d['ledger']} | {d['elec']} | {d['diff']} |")

    lines += [
        f"",
        f"## 다음 Iter 포커스",
        f"",
        f"- Iter 2: 음수재고 {kpi['neg_stock']}건 원인 분석 (movement 역추적)",
        f"- Iter 3: 불일치 상위 품목 현장 실사 대조",
        f"- Iter 4: Wave/PickingTask 피킹 정확도 분석",
    ]

    out_file.write_text("\n".join(lines), encoding="utf-8")
    print(f"  리포트 저장: {out_file}")
    return out_file, today


def update_log(kpi: dict, out_file: Path, today: str):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = f"""
## [{today[:4]}-{today[4:6]}-{today[6:]}] ITER1 | 재고 정확도 기준선

**상태:** 완료

### KPI 스냅샷
- 재고 정확도: {kpi['accuracy_pct']}% (목표 ≥95%)
- 음수재고: {kpi['neg_stock']}건
- 불일치: {kpi['mismatch']}건
- 전체 Ledger: {kpi['total']}건

### 산출물
- [{out_file.name}](../outputs/{out_file.name})

### 다음 포커스
- 음수재고 원인 분석 (Iter 2)
"""
    if LOG_FILE.exists():
        existing = LOG_FILE.read_text(encoding="utf-8")
        LOG_FILE.write_text(existing + entry, encoding="utf-8")
    else:
        LOG_FILE.write_text("# WMS AutoResearch — Session Log\n" + entry, encoding="utf-8")
    print(f"  log.md 업데이트: {LOG_FILE}")


def main():
    print("=" * 60)
    print("WMS AutoResearch Iter 1 — 재고 정확도 기준선")
    print("=" * 60)

    print("\n[1] WMS_InventoryLedger 조회...")
    ledger = fetch_ledger()
    print(f"  Ledger 레코드: {len(ledger)}건")

    print("\n[2] material(parts-stock) 조회...")
    mat_map = fetch_material()
    print(f"  material PT코드: {len(mat_map)}건")

    print("\n[3] 분석...")
    kpi = analyze(ledger, mat_map)

    print(f"\n  === KPI ===")
    print(f"  재고 정확도: {kpi['accuracy_pct']}%")
    print(f"  음수재고: {kpi['neg_stock']}건")
    print(f"  불일치: {kpi['mismatch']}건")
    print(f"  0재고: {kpi['zero_stock']}건")

    print("\n[4] 리포트 저장...")
    out_file, today = write_report(kpi)

    print("\n[5] log.md 업데이트...")
    update_log(kpi, out_file, today)

    print("\n완료")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실행**

```bash
python3 scripts/wms_autoResearch_iter1.py
```

기대 출력:
```
Ledger 레코드: N건
material PT코드: M건
재고 정확도: X%
음수재고: N건
리포트 저장: _AutoResearch/WMS/outputs/WMS-Iter1-YYYYMMDD.md
log.md 업데이트 완료
```

- [ ] **Step 3: 리포트 내용 검토**

```bash
cat "_AutoResearch/WMS/outputs/WMS-Iter1-$(date +%Y%m%d).md"
```

불일치 Top 10 확인 → 특이사항 있으면 Obsidian log.md에 추가 메모

- [ ] **Step 4: 커밋**

```bash
git add scripts/wms_autoResearch_iter1.py \
        "_AutoResearch/WMS/wiki/log.md" \
        "_AutoResearch/WMS/outputs/"
git commit -m "feat: WMS AutoResearch Iter 1 — 재고 정확도 기준선 분석"
```

---

## 실행 순서

```
Task 1 (Wave/PickingTask) → Task 2 (NCR) → Task 3 (AutoResearch)
```

Task 1, 2는 독립적으로 병렬 실행 가능. Task 3는 Wave/NCR 생성 후 실행 권장 (Ledger 데이터 최신 상태 반영).
