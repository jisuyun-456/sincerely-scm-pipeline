# CBM Backbone P2b — MES·task·BOM hop 점등 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 미점등 hop 3개를 점등 — ① MES↔PT/굿즈코드 크로스워크(WMS_KeyCrosswalk INSERT), ② ⚡task 투입자재 vs WMS_BOM 검증(검증상태 이송→검증완료 승급), ③ kit-CBM 폴백 tier(굿즈 CBM 커버리지 46.2%→목표 ≥85%).

**Architecture:** P2a 패턴 동일 — 순수 함수는 `harness/backbone/`·`harness/dispatch/`(TDD, Airtable I/O 없음), fetch/write는 `scripts/backbone/`(dry-run 기본, `--write` 게이트, 10건 batch + 429/5xx 재시도). MES·⚡task는 read-only(write 0), 쓰기는 allowlist 테이블(WMS_KeyCrosswalk INSERT, WMS_BOM 검증상태 PATCH, TMS estimated_cbm — 기존 replay 경로)만.

**Tech Stack:** Python 3 + requests + python-dotenv, pytest (순수 함수만, mocking 없음), Airtable REST/Meta API.

---

## Schema 실사 결과 (2026-06-10 Meta API — P2a lesson 이행: 증거 먼저)

| 소스 | 테이블 | 키 필드 (실측) |
|---|---|---|
| MES (`appNSAPadsHbfaSHv`) | `[sync]파츠별_자재이동` `tbliMelPWs1epoMkK` | `파츠코드` [singleLineText] — PT hop 소스 |
| MES | `내부인쇄_제품 DB` `tblvaQeb5NTP0iFng` | `Name` + `굿즈코드(by DB)` [singleLineText] — 굿즈 hop 소스 |
| WMS | `⚡task` `tblsIiXQzrHMSPqH7` (415 fields) | `project_code` [multilineText], `생산공정_투입자재 (from order)` [singleLineText], `이전공정_투입자재` [singleLineText] |
| WMS | `WMS_BOM` `tblopHqepkx6mNEHL` | `검증상태` choices = **이송/검증완료/폐기** (승급: 이송→검증완료) |
| WMS | `WMS_KeyCrosswalk` `tblJK5eyQGGx5X1oH` | **`출처` 필드 없음** → Task 2에서 Meta API로 1회 추가 (rollback 마커) |
| WMS | `WMS_ItemMaster` `tbl5ZGY373D5SCONV` | `품목키`, `CBM_개당_m3`, `출처` choices = TMS_Product/박스유도/MES_제품DB/수기/미등록 |

설계 결정 (spec §4/§6 + 실사 반영):
- **kit confidence** = min(소품목 ItemMaster `출처` 신뢰도 매핑) × 0.9, **상한 0.8** — "자식 part CBM 신뢰도"의 데이터 근거를 ItemMaster.출처로 구현 (TMS_Product 1.0 / 박스유도 0.9 / MES_제품DB 0.8 / 수기 0.7 / 미등록 0.0).
- **완전 키트만**: 소품목 중 하나라도 CBM≤0·소요량≤0/None이면 해당 (프로젝트,굿즈) 폴백 제외 — 부분합 과소추정 가드.
- **이중계상 가드 (spec §6-2)**: Product direct join 성공 시 kit 폴백 미적용. partial_skip 게이트 불변.
- **kit lookup 키 = (PNA, 견적코드)** — BOM이 프로젝트별이므로 프로젝트 단위 조인 (모호성 제거).
- **YAGNI 가드 (spec §6-3)**: 키 해소·검증·폴백만. 집계·예측·BOM 신규행·MES 데이터 복제 금지.

## Validation Contract (P2b Gate, spec §5)

1. hop 키 해소율 매트릭스 보고 — MES 파츠 hop %, MES 굿즈 hop %, task→BOM 검증 %, kit 커버리지.
2. 굿즈 CBM 커버리지(direct+kit) ≥85% — 미달 시 측정치+원인 보고로 게이트 재협상.
3. 소스 write 0 — MES base·⚡task에 POST/PATCH 없음 (코드 검사로 증명).
4. WMS_BOM 신규 INSERT 0 — 검증상태 PATCH만.
5. 신규 스크립트 2개 dry-run 기본 + `--write` 게이트.
6. pytest green (기존 W1 1 fail 유지, 신규 테스트 포함).
7. feature-dev:code-reviewer + harness-validator 병행 PASS.

---

### Task 0: Pre-flight

**Files:** Modify: `.env` (git 미추적)

- [ ] **Step 0.1**: `.env`에 `AIRTABLE_MES_PAT=patPbRN0xwtcP0sGR...` 추가 (memory `reference_airtable_mes_pat`의 PAT). read-only 용도로만 사용.
- [ ] **Step 0.2**: `python -m pytest tests/ -q` → 예상 `280 passed, 1 failed` (기존 W1 — 건드리지 말 것).
- [ ] **Step 0.3**: P2a 잔여 모니터링 — `gh run list --workflow=wave_recommender.yml --limit 3` + 최근 run의 replay step 로그에서 PATCH 폭주 없음 확인.
- [ ] **Step 0.4**: master tracker P2b → 🔄 IN_PROGRESS (완료됨).

### Task 1: keys.py — `extract_pts` + `build_mes_crosswalk_rows` (2b.1 순수부)

**Files:**
- Modify: `harness/backbone/keys.py`
- Test: `tests/backbone/test_keys.py`

- [ ] **Step 1.1: failing tests 작성** — `tests/backbone/test_keys.py`에 append:

```python
class TestExtractPts:
    def test_multiple_unique_order_preserved(self):
        assert extract_pts("PT1234 외 PT5678, PT1234 재투입") == ["PT1234", "PT5678"]

    def test_empty_and_none(self):
        assert extract_pts("") == []
        assert extract_pts(None) == []

    def test_short_digits_not_matched(self):
        assert extract_pts("PT99 PT123456") == ["PT123456"]


class TestBuildMesCrosswalkRows:
    def test_part_in_wms(self):
        rows, stats = build_mes_crosswalk_rows(
            {"PT1234"}, {}, set(), {"PT1234"}, set())
        assert rows == [{
            "표준키": "PT1234", "키유형": "파츠", "TMS_견적코드": "",
            "WMS_아이템코드": "PT1234", "MES_파츠코드": "PT1234",
            "매칭방식": "정확", "매칭신뢰도": 1.0, "검증상태": "확정",
            "출처": "mes_crosswalk",
        }]
        assert stats["parts_in_wms"] == 1 and stats["parts_new"] == 1

    def test_part_not_in_wms_unverified(self):
        rows, _ = build_mes_crosswalk_rows({"PT777777"}, {}, set(), set(), set())
        assert rows[0]["WMS_아이템코드"] == "" and rows[0]["검증상태"] == "미검증"
        assert rows[0]["매칭신뢰도"] == 0.5

    def test_existing_key_skipped(self):
        rows, stats = build_mes_crosswalk_rows(
            {"PT1234"}, {"굿즈A": "AB-1"}, {"PT1234", "굿즈A"}, {"PT1234"}, {"ab-1"})
        assert rows == []
        assert stats["parts_already"] == 1 and stats["goods_already"] == 1

    def test_goods_code_in_tms(self):
        rows, stats = build_mes_crosswalk_rows(
            set(), {"굿즈A": "ab-1 "}, set(), set(), {"ab-1"})
        assert rows[0]["TMS_견적코드"] == "AB-1"
        assert rows[0]["검증상태"] == "확정" and rows[0]["매칭신뢰도"] == 1.0
        assert stats["goods_code_in_tms"] == 1

    def test_goods_code_not_in_tms_held(self):
        rows, _ = build_mes_crosswalk_rows(set(), {"굿즈B": "ZZ-9"}, set(), set(), set())
        assert rows[0]["검증상태"] == "보류" and rows[0]["매칭방식"] == "수기"

    def test_goods_without_code_skipped(self):
        rows, stats = build_mes_crosswalk_rows(set(), {"굿즈C": ""}, set(), set(), set())
        assert rows == [] and stats["goods_no_code"] == 1
```

- [ ] **Step 1.2**: `python -m pytest tests/backbone/test_keys.py -q` → FAIL (ImportError).
- [ ] **Step 1.3: 구현** — `harness/backbone/keys.py`에 append:

```python
def extract_pts(text) -> list[str]:
    """텍스트 내 모든 PT#### 코드 (중복 제거, 등장 순서 유지)."""
    if not text:
        return []
    return list(dict.fromkeys(PT_RE.findall(str(text))))


def build_mes_crosswalk_rows(
    mes_parts: set[str],
    mes_goods: dict[str, str],
    existing_keys: set[str],
    wms_item_keys: set[str],
    product_codes: set[str],
) -> tuple[list[dict], dict]:
    """MES 키 → WMS_KeyCrosswalk 신규행 + 매칭 stats. INSERT-only(기존 표준키 스킵).

    mes_goods: MES 제품명 → 굿즈코드(by DB). product_codes: TMS 견적코드(lower).
    행 출처='mes_crosswalk' 태깅 (rollback 식별 마커).
    """
    rows: list[dict] = []
    stats = {"parts_total": len(mes_parts), "parts_already": 0, "parts_in_wms": 0,
             "parts_new": 0, "goods_total": len(mes_goods), "goods_already": 0,
             "goods_no_code": 0, "goods_code_in_tms": 0, "goods_new": 0}
    for pt in sorted(mes_parts):
        if pt in existing_keys:
            stats["parts_already"] += 1
            continue
        in_wms = pt in wms_item_keys
        if in_wms:
            stats["parts_in_wms"] += 1
        stats["parts_new"] += 1
        rows.append({
            "표준키": pt, "키유형": "파츠", "TMS_견적코드": "",
            "WMS_아이템코드": pt if in_wms else "", "MES_파츠코드": pt,
            "매칭방식": "정확", "매칭신뢰도": 1.0 if in_wms else 0.5,
            "검증상태": "확정" if in_wms else "미검증", "출처": "mes_crosswalk",
        })
    for name in sorted(mes_goods):
        code = str(mes_goods[name] or "").strip().upper()
        if name in existing_keys:
            stats["goods_already"] += 1
            continue
        if not code:
            stats["goods_no_code"] += 1
            continue
        in_tms = code.lower() in product_codes
        if in_tms:
            stats["goods_code_in_tms"] += 1
        stats["goods_new"] += 1
        rows.append({
            "표준키": name, "키유형": "굿즈", "TMS_견적코드": code,
            "WMS_아이템코드": "", "MES_파츠코드": "",
            "매칭방식": "정확" if in_tms else "수기",
            "매칭신뢰도": 1.0 if in_tms else 0.5,
            "검증상태": "확정" if in_tms else "보류", "출처": "mes_crosswalk",
        })
    return rows, stats
```

(테스트 파일 상단 import에 `extract_pts, build_mes_crosswalk_rows` 추가)

- [ ] **Step 1.4**: `python -m pytest tests/backbone/test_keys.py -q` → PASS. `python -m pytest tests/ -q` → 기존 fail 1 외 green.
- [ ] **Step 1.5: Commit** — `git add harness/backbone/keys.py tests/backbone/test_keys.py && git commit -m "feat(backbone): extract_pts + MES crosswalk row builder (P2b Task 2b.1)"`

### Task 2: WMS_KeyCrosswalk `출처` 필드 + `scripts/backbone/mes_crosswalk.py` (2b.1 I/O부)

**Files:**
- Modify: `harness/backbone/schema_def.py` (출처 필드 스펙 추가)
- Create: `scripts/backbone/mes_crosswalk.py`

- [ ] **Step 2.1**: `schema_def.py` `TABLES["WMS_KeyCrosswalk"]` 끝에 추가:

```python
        {"name": "출처", "type": "singleSelect",
         "options": {"choices": [{"name": "mes_crosswalk"}]}},  # blank = P1 bootstrap
```

- [ ] **Step 2.2**: 1회 Meta API 필드 추가 (idempotent — 이미 있으면 422 무시):

```bash
python -c "
import os, json, urllib.request, urllib.error
from dotenv import load_dotenv; load_dotenv()
url = 'https://api.airtable.com/v0/meta/bases/appLui4ZR5HWcQRri/tables/tblJK5eyQGGx5X1oH/fields'
payload = {'name': '출처', 'type': 'singleSelect', 'options': {'choices': [{'name': 'mes_crosswalk'}]}}
req = urllib.request.Request(url, data=json.dumps(payload).encode(), method='POST',
    headers={'Authorization': 'Bearer ' + os.environ['AIRTABLE_WMS_PAT'], 'Content-Type': 'application/json'})
try:
    print(json.load(urllib.request.urlopen(req)))
except urllib.error.HTTPError as e:
    print('exists or error:', e.code, e.read()[:200])
"
```

- [ ] **Step 2.3**: `scripts/backbone/mes_crosswalk.py` 작성 (replay 패턴 — fetch/배치/재시도 동일):

```python
"""P2b Task 2b.1 — MES↔PT/굿즈코드 크로스워크.

MES read-only: [sync]파츠별_자재이동.파츠코드(PT hop) + 내부인쇄_제품 DB.Name/굿즈코드(by DB)(굿즈 hop)
→ WMS_KeyCrosswalk 신규 키 INSERT(출처='mes_crosswalk') + 매칭률 stdout 리포트.
dry-run 기본, --write 게이트. YAGNI 가드(spec §6-3): 키 해소만 — 집계·예측·MES 복제 금지. MES write 0.

Usage:
  python scripts/backbone/mes_crosswalk.py            # dry-run 매칭률 측정
  python scripts/backbone/mes_crosswalk.py --write    # 신규 키 INSERT
"""
import argparse
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.backbone.keys import extract_pts, build_mes_crosswalk_rows  # noqa: E402
from harness.settlement.cbm_calc import load_product_lookup  # noqa: E402

load_dotenv()
MP = os.environ["AIRTABLE_MES_PAT"]   # MES read-only
WP = os.environ["AIRTABLE_WMS_PAT"]
TP = os.environ["AIRTABLE_PAT"]
MES = "appNSAPadsHbfaSHv"
WMS = "appLui4ZR5HWcQRri"
MES_SYNC_PARTS = "tbliMelPWs1epoMkK"  # [sync]파츠별_자재이동 (read-only)
MES_PRINT_DB = "tblvaQeb5NTP0iFng"    # 내부인쇄_제품 DB (read-only)
XWALK = "tblJK5eyQGGx5X1oH"           # WMS_KeyCrosswalk (allowlist INSERT 대상)
ITEM = "tbl5ZGY373D5SCONV"            # WMS_ItemMaster


def fetch(base, tid, pat, fields):
    out, off = [], None
    while True:
        p = {"pageSize": 100, "fields[]": fields}
        if off:
            p["offset"] = off
        r = requests.get(
            f"https://api.airtable.com/v0/{base}/{tid}",
            headers={"Authorization": f"Bearer {pat}"}, params=p, timeout=60,
        )
        r.raise_for_status()
        d = r.json()
        out += d["records"]
        off = d.get("offset")
        if not off:
            break
    return out


def post_batch(url, headers, batch):
    """10건 이하 batch INSERT. Returns (ok, err)."""
    for attempt in range(3):
        try:
            r = requests.post(url, headers=headers,
                              json={"records": batch, "typecast": True}, timeout=30)
            time.sleep(0.25)
            if r.ok:
                return len(batch), 0
            if r.status_code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(30 * (attempt + 1))
                continue
            print(f"  ERROR {r.status_code}: {r.text[:120]}", flush=True)
            return 0, len(batch)
        except requests.exceptions.ConnectionError:
            if attempt < 2:
                time.sleep(30 * (attempt + 1))
            else:
                return 0, len(batch)
    return 0, len(batch)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="신규 키 INSERT (기본 dry-run)")
    args = ap.parse_args()

    print("MES [sync]파츠별_자재이동 로딩...", flush=True)
    mes_parts: set = set()
    for r in fetch(MES, MES_SYNC_PARTS, MP, ["파츠코드"]):
        mes_parts.update(extract_pts(r["fields"].get("파츠코드")))
    print(f"  MES 파츠(PT) {len(mes_parts)}종", flush=True)

    print("MES 내부인쇄_제품 DB 로딩...", flush=True)
    mes_goods = {}
    for r in fetch(MES, MES_PRINT_DB, MP, ["Name", "굿즈코드(by DB)"]):
        f = r["fields"]
        nm = str(f.get("Name") or "").strip()
        if nm:
            mes_goods[nm] = str(f.get("굿즈코드(by DB)") or "")
    print(f"  MES 굿즈 {len(mes_goods)}종", flush=True)

    existing_keys = {str(r["fields"].get("표준키") or "").strip()
                     for r in fetch(WMS, XWALK, WP, ["표준키"])}
    wms_item_keys = {str(r["fields"].get("품목키") or "").strip()
                     for r in fetch(WMS, ITEM, WP, ["품목키"])}
    lookup = load_product_lookup({"Authorization": f"Bearer {TP}"})
    rows, s = build_mes_crosswalk_rows(
        mes_parts, mes_goods, existing_keys, wms_item_keys,
        {str(k).lower() for k in lookup})

    pt_rate = s["parts_in_wms"] / s["parts_total"] * 100 if s["parts_total"] else 0.0
    gd_known = s["goods_total"] - s["goods_no_code"]
    gd_rate = s["goods_code_in_tms"] / gd_known * 100 if gd_known else 0.0
    print("\n=== MES 크로스워크 매칭률 (hop 해소율) ===", flush=True)
    print(f"  파츠 hop: MES PT {s['parts_total']}종 — WMS ItemMaster 해소 "
          f"{s['parts_in_wms']} ({pt_rate:.1f}%) / 기존 스킵 {s['parts_already']} "
          f"/ 신규 INSERT {s['parts_new']}", flush=True)
    print(f"  굿즈 hop: MES 굿즈 {s['goods_total']}종 — 코드없음 {s['goods_no_code']} "
          f"/ TMS Product 해소 {s['goods_code_in_tms']}/{gd_known} ({gd_rate:.1f}%) "
          f"/ 기존 스킵 {s['goods_already']} / 신규 INSERT {s['goods_new']}", flush=True)

    if not args.write:
        print(f"\n[DRY-RUN] INSERT 예정 {len(rows)}행 — 반영하려면 --write", flush=True)
        return
    headers = {"Authorization": f"Bearer {WP}", "Content-Type": "application/json"}
    url = f"https://api.airtable.com/v0/{WMS}/{XWALK}"
    ok = err = 0
    for i in range(0, len(rows), 10):
        o, e = post_batch(url, headers, [{"fields": r} for r in rows[i:i + 10]])
        ok += o
        err += e
        print(f"  INSERT {i + len(rows[i:i + 10])}/{len(rows)} (ok={ok} err={err})", flush=True)
    print(f"\n[WRITE] KeyCrosswalk inserted={ok} err={err} (출처='mes_crosswalk')", flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2.4**: dry-run 실행 `python scripts/backbone/mes_crosswalk.py` → 매칭률 리포트 검토 (오매칭 가드: 파츠 hop 해소율·굿즈 TMS 해소율이 0%이거나 INSERT 행이 수천 단위로 폭주하면 중단·원인 분석).
- [ ] **Step 2.5**: 리포트 정상 시 `python scripts/backbone/mes_crosswalk.py --write` → inserted/err 기록.
- [ ] **Step 2.6: Commit** — `git add harness/backbone/schema_def.py scripts/backbone/mes_crosswalk.py && git commit -m "feat(backbone): MES crosswalk script + 출처 field (P2b Task 2b.1)"`

### Task 3: `harness/backbone/task_verify.py` (2b.2 순수부)

**Files:**
- Create: `harness/backbone/task_verify.py`
- Test: `tests/backbone/test_task_verify.py`

- [ ] **Step 3.1: failing tests 작성** — `tests/backbone/test_task_verify.py`:

```python
from harness.backbone.task_verify import extract_task_pairs, select_bom_promotions


class TestExtractTaskPairs:
    def test_pairs_from_both_fields(self):
        rows = [{"project_code": "PNA12345_고객A",
                 "생산공정_투입자재 (from order)": "PT1234 투입",
                 "이전공정_투입자재": "PT5678, PT1234"}]
        assert extract_task_pairs(rows) == {("PNA12345", "PT1234"), ("PNA12345", "PT5678")}

    def test_no_project_skipped(self):
        assert extract_task_pairs([{"이전공정_투입자재": "PT1234"}]) == set()

    def test_list_wrapped_lookup_fields(self):
        rows = [{"project_code": ["PNA777"],
                 "생산공정_투입자재 (from order)": ["PT111222"]}]
        assert extract_task_pairs(rows) == {("PNA777", "PT111222")}


class TestSelectBomPromotions:
    BOM = [
        {"id": "rec1", "fields": {"프로젝트코드": "PNA12345_x", "소품목_PT": "PT1234", "검증상태": "이송"}},
        {"id": "rec2", "fields": {"프로젝트코드": "PNA12345_x", "소품목_PT": "PT9999", "검증상태": "이송"}},
        {"id": "rec3", "fields": {"프로젝트코드": "PNA12345_x", "소품목_PT": "PT1234", "검증상태": "검증완료"}},
        {"id": "rec4", "fields": {"프로젝트코드": "", "소품목_PT": "PT1234", "검증상태": "이송"}},
    ]

    def test_only_isong_matching_promoted(self):
        ids, stats = select_bom_promotions(self.BOM, {("PNA12345", "PT1234")})
        assert ids == ["rec1"]
        assert stats == {"total": 4, "not_isong": 1, "no_key": 1,
                         "matched": 1, "unmatched": 1}
```

- [ ] **Step 3.2**: `python -m pytest tests/backbone/test_task_verify.py -q` → FAIL (ModuleNotFoundError).
- [ ] **Step 3.3: 구현** — `harness/backbone/task_verify.py`:

```python
"""⚡task 투입자재 vs WMS_BOM 검증 순수 로직 (P2b Task 2b.2).

⚡task의 (PNA, PT) 쌍 = 생산이 실제 그 자재로 실행된 증거 →
order그룹핑으로 부트스트랩된 WMS_BOM 행(검증상태='이송')을 '검증완료'로 승급.
신규 BOM INSERT 금지 — 승급 대상 record id 선별만.
"""
from __future__ import annotations

from harness.backbone.keys import PNA_RE, extract_pts

TASK_MATERIAL_FIELDS = ("생산공정_투입자재 (from order)", "이전공정_투입자재")


def _text(v) -> str:
    if isinstance(v, list):
        return " ".join(str(x) for x in v)
    return str(v or "")


def extract_task_pairs(task_fields_iter) -> set[tuple[str, str]]:
    """⚡task fields dicts → {(PNA, PT)}. lookup 필드 list 언랩."""
    pairs: set[tuple[str, str]] = set()
    for f in task_fields_iter:
        m = PNA_RE.search(_text(f.get("project_code")))
        if not m:
            continue
        for field in TASK_MATERIAL_FIELDS:
            for pt in extract_pts(_text(f.get(field))):
                pairs.add((m.group(0), pt))
    return pairs


def select_bom_promotions(bom_records, task_pairs) -> tuple[list[str], dict]:
    """검증상태='이송' BOM record 중 (PNA, 소품목_PT) ∈ task_pairs → 승급 대상 id + stats."""
    ids: list[str] = []
    stats = {"total": 0, "not_isong": 0, "no_key": 0, "matched": 0, "unmatched": 0}
    for rec in bom_records:
        f = rec.get("fields", {})
        stats["total"] += 1
        if f.get("검증상태") != "이송":
            stats["not_isong"] += 1
            continue
        m = PNA_RE.search(_text(f.get("프로젝트코드")))
        pt = _text(f.get("소품목_PT")).strip()
        if not m or not pt:
            stats["no_key"] += 1
            continue
        if (m.group(0), pt) in task_pairs:
            ids.append(rec["id"])
            stats["matched"] += 1
        else:
            stats["unmatched"] += 1
    return ids, stats
```

- [ ] **Step 3.4**: `python -m pytest tests/backbone/test_task_verify.py -q` → PASS.
- [ ] **Step 3.5: Commit** — `git add harness/backbone/task_verify.py tests/backbone/test_task_verify.py && git commit -m "feat(backbone): task↔BOM verification pure logic (P2b Task 2b.2)"`

### Task 4: `scripts/backbone/task_bom_verify.py` (2b.2 I/O부)

**Files:** Create: `scripts/backbone/task_bom_verify.py`

- [ ] **Step 4.1**: 스크립트 작성:

```python
"""P2b Task 2b.2 — ⚡task 투입자재 vs WMS_BOM 검증·승급.

⚡task read-only → (PNA, PT) 쌍 추출 → WMS_BOM(검증상태='이송') 대조 →
일치 row '검증완료' PATCH + 검증률 stdout 리포트. WMS_BOM 신규 INSERT 0.
dry-run 기본, --write 게이트.

Usage:
  python scripts/backbone/task_bom_verify.py            # dry-run 검증률 측정
  python scripts/backbone/task_bom_verify.py --write    # 검증상태 승급 PATCH
"""
import argparse
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.backbone.task_verify import (  # noqa: E402
    TASK_MATERIAL_FIELDS, extract_task_pairs, select_bom_promotions,
)

load_dotenv()
WP = os.environ["AIRTABLE_WMS_PAT"]
WMS = "appLui4ZR5HWcQRri"
TASK = "tblsIiXQzrHMSPqH7"   # ⚡task (read-only)
BOM = "tblopHqepkx6mNEHL"    # WMS_BOM (검증상태 PATCH만 — INSERT 금지)


def fetch(base, tid, pat, fields):
    out, off = [], None
    while True:
        p = {"pageSize": 100, "fields[]": fields}
        if off:
            p["offset"] = off
        r = requests.get(
            f"https://api.airtable.com/v0/{base}/{tid}",
            headers={"Authorization": f"Bearer {pat}"}, params=p, timeout=60,
        )
        r.raise_for_status()
        d = r.json()
        out += d["records"]
        off = d.get("offset")
        if not off:
            break
    return out


def patch_batch(url, headers, batch):
    """10건 이하 batch PATCH. Returns (ok, err)."""
    for attempt in range(3):
        try:
            r = requests.patch(url, headers=headers, json={"records": batch}, timeout=30)
            time.sleep(0.25)
            if r.ok:
                return len(batch), 0
            if r.status_code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(30 * (attempt + 1))
                continue
            print(f"  ERROR {r.status_code}: {r.text[:120]}", flush=True)
            return 0, len(batch)
        except requests.exceptions.ConnectionError:
            if attempt < 2:
                time.sleep(30 * (attempt + 1))
            else:
                return 0, len(batch)
    return 0, len(batch)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="검증상태 승급 PATCH (기본 dry-run)")
    args = ap.parse_args()

    print("⚡task 로딩 (read-only)...", flush=True)
    tasks = fetch(WMS, TASK, WP, ["project_code", *TASK_MATERIAL_FIELDS])
    pairs = extract_task_pairs(r["fields"] for r in tasks)
    print(f"  task {len(tasks)}행 → (PNA, PT) 쌍 {len(pairs)}종", flush=True)

    print("WMS_BOM 로딩...", flush=True)
    bom = fetch(WMS, BOM, WP, ["프로젝트코드", "소품목_PT", "검증상태"])
    ids, s = select_bom_promotions(bom, pairs)
    isong = s["matched"] + s["unmatched"]
    rate = s["matched"] / isong * 100 if isong else 0.0
    print("\n=== task↔BOM 검증률 (hop 해소율) ===", flush=True)
    print(f"  BOM {s['total']}행: 이송 {isong} / 비대상(검증완료·폐기 등) {s['not_isong']} "
          f"/ 키없음 {s['no_key']}", flush=True)
    print(f"  task 일치 → 승급 대상: {s['matched']}/{isong} ({rate:.1f}%) "
          f"/ 미일치 {s['unmatched']}", flush=True)

    if not args.write:
        print(f"\n[DRY-RUN] 검증완료 승급 예정 {len(ids)}행 — 반영하려면 --write", flush=True)
        return
    headers = {"Authorization": f"Bearer {WP}", "Content-Type": "application/json"}
    url = f"https://api.airtable.com/v0/{WMS}/{BOM}"
    ok = err = 0
    for i in range(0, len(ids), 10):
        batch = [{"id": rid, "fields": {"검증상태": "검증완료"}} for rid in ids[i:i + 10]]
        o, e = patch_batch(url, headers, batch)
        ok += o
        err += e
        print(f"  PATCH {i + len(batch)}/{len(ids)} (ok={ok} err={err})", flush=True)
    print(f"\n[WRITE] BOM 검증상태 승급={ok} err={err}. INSERT 0.", flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4.2**: dry-run 실행 → 검증률 리포트 검토 (승급 0건이거나 100%면 조인 키 의심 — 원인 분석 후 진행).
- [ ] **Step 4.3**: 정상 시 `--write` 실행 → ok/err 기록.
- [ ] **Step 4.4: Commit** — `git add scripts/backbone/task_bom_verify.py && git commit -m "feat(backbone): task↔BOM verify script + 검증상태 승급 (P2b Task 2b.2)"`

### Task 5: `cbm_estimator.py` kit-CBM 폴백 tier (2b.3 순수부)

**Files:**
- Modify: `harness/dispatch/cbm_estimator.py`
- Test: `tests/dispatch/test_cbm_estimator.py`

- [ ] **Step 5.1**: 기존 `tests/dispatch/test_cbm_estimator.py`의 deterministic 테스트가 반환 dict 전체 `==` 비교인지 확인 — 그렇다면 기대 dict에 `"kit_used": []` 추가가 필요해짐 (backward-compat 확인 포인트).
- [ ] **Step 5.2: failing tests 작성** — append:

```python
from harness.dispatch.cbm_estimator import build_kit_cbm_lookup

_BOM_FIELDS = [
    {"프로젝트코드": "PNA100_x", "모품목_굿즈명": "키트A", "소품목_PT": "PT1111", "소요량_개당": 2},
    {"프로젝트코드": "PNA100_x", "모품목_굿즈명": "키트A", "소품목_PT": "PT2222", "소요량_개당": 1},
    {"프로젝트코드": "PNA100_x", "모품목_굿즈명": "불완전", "소품목_PT": "PT3333", "소요량_개당": 1},
    {"프로젝트코드": "PNA100_x", "모품목_굿즈명": "소요량없음", "소품목_PT": "PT1111", "소요량_개당": None},
]
_ITEM_MASTER = {
    "PT1111": (0.001, "TMS_Product"),
    "PT2222": (0.002, "박스유도"),
    # PT3333: CBM 없음 → '불완전' 그룹 제외
}
_NAME2CODE = {"키트A": "KIT-A", "불완전": "X-1", "소요량없음": "X-2"}


class TestBuildKitCbmLookup:
    def test_complete_kit_only(self):
        kit = build_kit_cbm_lookup(_BOM_FIELDS, _ITEM_MASTER, _NAME2CODE)
        assert set(kit) == {("PNA100", "KIT-A")}
        cbm, conf = kit[("PNA100", "KIT-A")]
        assert abs(cbm - (2 * 0.001 + 1 * 0.002)) < 1e-9
        # min(1.0, 0.9) * 0.9 = 0.81 → 상한 0.8
        assert conf == 0.8

    def test_confidence_below_cap(self):
        bom = [{"프로젝트코드": "PNA200", "모품목_굿즈명": "g", "소품목_PT": "PT1", "소요량_개당": 1}]
        kit = build_kit_cbm_lookup(bom, {"PT1": (0.005, "수기")}, {"g": "G-1"})
        assert kit[("PNA200", "G-1")][1] == 0.63  # 0.7 * 0.9

    def test_unknown_goods_code_skipped(self):
        bom = [{"프로젝트코드": "PNA300", "모품목_굿즈명": "미등록굿즈", "소품목_PT": "PT1", "소요량_개당": 1}]
        assert build_kit_cbm_lookup(bom, {"PT1": (0.005, "TMS_Product")}, {}) == {}


_DET_KIT_LOOKUP = {("PNA100", "KIT-A"): (0.004, 0.8)}


class TestDeterministicKitFallback:
    def test_kit_fallback_applied_when_product_missing(self):
        res = estimate_shipment_cbm_deterministic(
            "PNA100", {"PNA100": [("KIT-A", 10)]}, {}, {"PNA100": 1},
            kit_lookup=_DET_KIT_LOOKUP)
        assert res["estimated_cbm"] == 0.04   # 10 * 0.004 (박스 패킹 없음)
        assert res["confidence"] == 0.8
        assert res["kit_used"] == ["KIT-A"]

    def test_product_direct_wins_over_kit(self):
        lookup = {"kit-a": {"code": "KIT-A", "qty_per_box": 10, "cbm_per_box": 0.05}}
        res = estimate_shipment_cbm_deterministic(
            "PNA100", {"PNA100": [("KIT-A", 10)]}, lookup, {"PNA100": 1},
            kit_lookup=_DET_KIT_LOOKUP)
        assert res["estimated_cbm"] == 0.05   # 이중계상 가드: direct 우선
        assert res["kit_used"] == [] and res["confidence"] == 1.0

    def test_backward_compat_without_kit_lookup(self):
        res = estimate_shipment_cbm_deterministic(
            "PNA100", {"PNA100": [("KIT-A", 10)]}, {}, {"PNA100": 1})
        assert res["estimated_cbm"] == 0.0 and res["unmatched"] == ["KIT-A"]
```

- [ ] **Step 5.3**: `python -m pytest tests/dispatch/test_cbm_estimator.py -q` → FAIL.
- [ ] **Step 5.4: 구현** — `cbm_estimator.py`:

상단 import에 추가:
```python
from harness.backbone.keys import PNA_RE, normalize_goods
```

모듈 상수 추가:
```python
# kit-CBM 폴백 (P2b Task 2b.3): ItemMaster.출처 → 자식 part CBM 신뢰도
_KIT_SRC_CONF = {"TMS_Product": 1.0, "박스유도": 0.9, "MES_제품DB": 0.8, "수기": 0.7, "미등록": 0.0}
KIT_CONF_CAP = 0.8  # Product 직접조인(0.9~1.0)보다 항상 낮게 — 신뢰도 사다리 정렬 (spec §6-2)
```

새 함수:
```python
def build_kit_cbm_lookup(
    bom_fields, item_master: dict, name_to_code: dict
) -> dict[tuple[str, str], tuple[float, float]]:
    """{(PNA, 견적코드): (kit_cbm_per_unit, confidence)} — kit-CBM 폴백 룩업.

    bom_fields: WMS_BOM fields dicts. item_master: {PT: (CBM_개당_m3, 출처)}.
    name_to_code: normalize_goods(굿즈명) → 견적코드 (sync_item 브릿지).
    완전 키트만(전 소품목 CBM>0·소요량>0). conf = min(출처 신뢰도)*0.9, 상한 0.8.
    """
    groups: dict[tuple[str, str], list] = {}
    for f in bom_fields:
        m = PNA_RE.search(str(f.get("프로젝트코드") or ""))
        gname = str(f.get("모품목_굿즈명") or "").strip()
        pt = str(f.get("소품목_PT") or "").strip()
        if not m or not gname or not pt:
            continue
        groups.setdefault((m.group(0), gname), []).append((pt, f.get("소요량_개당")))
    out: dict[tuple[str, str], tuple[float, float]] = {}
    for (pna, gname) in sorted(groups):
        code = name_to_code.get(normalize_goods(gname))
        if not code:
            continue
        key = (pna, str(code).strip().upper())
        if key in out:
            continue
        total, confs, complete = 0.0, [], True
        for pt, soyo in groups[(pna, gname)]:
            entry = item_master.get(pt)
            try:
                s = float(soyo)
            except (TypeError, ValueError):
                s = 0.0
            if not entry or entry[0] <= 0 or s <= 0:
                complete = False
                break
            total += s * entry[0]
            confs.append(_KIT_SRC_CONF.get(entry[1], 0.7))
        if complete and total > 0:
            out[key] = (round(total, 6), round(min(min(confs) * 0.9, KIT_CONF_CAP), 2))
    return out
```

`estimate_shipment_cbm_deterministic` 수정 (`kit_lookup=None` 파라미터 + kit 분기 + 모든 return에 `kit_used` 키):
```python
def estimate_shipment_cbm_deterministic(
    project_code: str,
    order_by_project: dict[str, list[tuple[str, float]]],
    lookup: dict,
    shipment_count: dict[str, int],
    kit_lookup: dict | None = None,
) -> dict:
    """결정론 출고 CBM. order.굿즈코드→Product[견적코드]→ceil(qty/qpb)*cbm. 퍼지 없음.

    다차 출하 프로젝트(95% 예외)는 partial_skip(중복합산 방지) — 1출하 프로젝트만 기록.
    blank project_code/no order는 호출측에서 기존 퍼지 estimate_shipment_cbm 폴백.
    kit_lookup: {(PNA, 견적코드): (kit_cbm_per_unit, conf)} — Product CBM 부재 시만 적용
    (이중계상 가드: direct 우선). kit 사용 시 confidence ≤ 0.8.
    Returns dict: {estimated_cbm, confidence, mode, matched, unmatched, kit_used}.
    """
    if shipment_count.get(project_code, 0) > 1:
        return {"estimated_cbm": 0.0, "confidence": 0.0, "mode": "partial_skip",
                "matched": [], "unmatched": [], "kit_used": []}
    lines = order_by_project.get(project_code)
    if not lines:
        return {"estimated_cbm": 0.0, "confidence": 0.0, "mode": "no_order",
                "matched": [], "unmatched": [], "kit_used": []}
    total = 0.0
    matched: list[str] = []
    unmatched: list[str] = []
    kit_used: list[str] = []
    kit_confs: list[float] = []
    for code, qty in lines:
        e = lookup.get(str(code).lower())
        if e and e["cbm_per_box"] > 0 and qty > 0:
            total += math.ceil(qty / e["qty_per_box"]) * e["cbm_per_box"]
            matched.append(code)
            continue
        k = (kit_lookup or {}).get((project_code, str(code).upper()))
        if k and qty > 0:
            total += qty * k[0]
            matched.append(code)
            kit_used.append(code)
            kit_confs.append(k[1])
        else:
            unmatched.append(code)
    conf = 1.0 if matched and not unmatched else (0.7 if matched else 0.0)
    if kit_confs:
        conf = min(conf, min(kit_confs))
    return {"estimated_cbm": round(total, 4), "confidence": conf,
            "mode": "deterministic", "matched": matched, "unmatched": unmatched,
            "kit_used": kit_used}
```

- [ ] **Step 5.5**: `python -m pytest tests/dispatch/ tests/backbone/ -q` → PASS. `python -m pytest tests/ -q` → 기존 fail 1 외 green.
- [ ] **Step 5.6: Commit** — `git add harness/dispatch/cbm_estimator.py tests/dispatch/test_cbm_estimator.py && git commit -m "feat(dispatch): kit-CBM fallback tier — BOM×ItemMaster, conf cap 0.8 (P2b Task 2b.3)"`

### Task 6: replay에 kit lookup 통합 + 커버리지 리포트 (2b.3 I/O부)

**Files:** Modify: `scripts/backbone/replay_outbound_cbm.py`

- [ ] **Step 6.1**: 테이블 상수 추가 + `build_pkg_fallback`이 `name2code`도 반환하도록 수정 + kit 로더 추가:

```python
BOM_TBL = "tblopHqepkx6mNEHL"    # WMS_BOM (kit-CBM 폴백 소스)
ITEM_TBL = "tbl5ZGY373D5SCONV"   # WMS_ItemMaster
```

`build_pkg_fallback` 마지막 줄 `return pkg_map` → `return pkg_map, name2code`.

```python
def build_kit_lookup(name2code):
    """WMS_BOM × ItemMaster → {(PNA, 견적코드): (kit_cbm, conf)} (P2b kit-CBM 폴백)."""
    print("WMS_BOM·ItemMaster 로딩 (kit-CBM 폴백)...", flush=True)
    bom = fetch(WMS, BOM_TBL, WP, ["프로젝트코드", "모품목_굿즈명", "소품목_PT", "소요량_개당"])
    items = fetch(WMS, ITEM_TBL, WP, ["품목키", "CBM_개당_m3", "출처"])
    item_master = {}
    for r in items:
        f = r["fields"]
        k = str(f.get("품목키") or "").strip()
        if k:
            item_master[k] = (n(f.get("CBM_개당_m3")), str(f.get("출처") or ""))
    kit = build_kit_cbm_lookup((r["fields"] for r in bom), item_master, name2code)
    print(f"  kit 폴백: {len(kit)} (프로젝트,굿즈코드) 엔트리 (BOM {len(bom)}행)", flush=True)
    return kit
```

import에 `build_kit_cbm_lookup` 추가 (`from harness.dispatch.cbm_estimator import ...`).

- [ ] **Step 6.2**: `build_inputs()` 수정 — `pkg_map, name2code = build_pkg_fallback()`; `kit = build_kit_lookup(name2code)`; return에 `kit` 추가. `main()`의 호출부 `lk, obp, scount, ships = build_inputs()` → `lk, obp, scount, ships, kit = build_inputs()`, `estimate_shipment_cbm_deterministic(m.group(0), obp, lk, scount)` → `estimate_shipment_cbm_deterministic(m.group(0), obp, lk, scount, kit_lookup=kit)`. kit 사용 건수 카운터 추가:

```python
kit_adds = 0   # main() 카운터 초기화부에
...
elif res["estimated_cbm"] > 0:
    det_est = res["estimated_cbm"]
    if res["kit_used"]:
        kit_adds += 1
    ...
```

- [ ] **Step 6.3**: `build_inputs()` 끝에 굿즈 CBM 커버리지 측정·출력 (gate 분모: order에 등장한 고유 굿즈코드):

```python
    codes = {c for lines in order_by_project.values() for c, _ in lines}
    direct = {c for c in codes
              if (lk.get(str(c).lower()) or {}).get("cbm_per_box", 0) > 0}
    kit_codes = {c for _, c in kit} & codes
    covered = direct | kit_codes
    print(f"  굿즈 CBM 커버리지: direct {len(direct)}/{len(codes)} "
          f"({len(direct)/max(len(codes),1)*100:.1f}%) → +kit "
          f"{len(covered)}/{len(codes)} ({len(covered)/max(len(codes),1)*100:.1f}%) "
          f"[Gate ≥85%]", flush=True)
```

main 리포트 블록에 kit 라인 추가:
```python
    print(f"  kit-CBM 폴백 적용(결정론 내)     : {kit_adds:>6} ({kit_adds/total*100:5.1f}%)")
```

- [ ] **Step 6.4**: `python scripts/backbone/replay_outbound_cbm.py` (dry-run, 전수) → 커버리지·kit 적용 건수·forward 75% 유지 확인. `--recent 90`으로 forward도 측정.
- [ ] **Step 6.5**: `python -m pytest tests/ -q` → green 유지 (replay는 테스트 무관, smoke는 dry-run이 대신).
- [ ] **Step 6.6: Commit** — `git add scripts/backbone/replay_outbound_cbm.py && git commit -m "feat(backbone): replay kit-CBM lookup 통합 + 굿즈 커버리지 리포트 (P2b Task 2b.3)"`

> cron(wave_recommender.yml)은 이미 `replay --recent 7 --write`를 호출하므로 별도 배선 불필요 — 커밋 즉시 다음 run부터 kit 폴백이 흐름 (conf≥0.7 게이트로 수기/미등록 키트는 자동 제외).

### Task 7: Gate 측정·검토·보고

- [ ] **Step 7.1**: hop 키 해소율 매트릭스 작성 — Task 2 dry-run(MES 파츠/굿즈 hop) + Task 4 dry-run(task→BOM) + Task 6 dry-run(kit 커버리지) 수치 취합.
- [ ] **Step 7.2**: 소스 write 0 증명 — `grep -n "requests.post\|requests.patch\|create_records\|patch_record" scripts/backbone/mes_crosswalk.py scripts/backbone/task_bom_verify.py` → POST/PATCH URL이 WMS allowlist 테이블(XWALK/BOM)만 가리킴 확인. MES base ID로의 쓰기 호출 0.
- [ ] **Step 7.3**: `feature-dev:code-reviewer` + `harness-validator` 병행 호출 → PASS 확인 (지적 시 수정 커밋).
- [ ] **Step 7.4**: 커버리지 ≥85% 판정. 미달 시 측정치+원인(완전키트 비율, sync_item 브릿지 한계 등) 보고 — 게이트 재협상 조항 발동.
- [ ] **Step 7.5**: `.claude/feature_list.json` 갱신 + 최종 결과 보고. `/chain done`은 사용자 확인 후.

## Rollback

- 2b.1: `WMS_KeyCrosswalk`에서 `출처='mes_crosswalk'` 행 일괄 삭제 (필드 마커로 식별) + 커밋 revert.
- 2b.2: 승급 PATCH 역방향 — stdout 로그의 record id로 `검증상태='이송'` 복원 (스크립트 재실행으로 동일 id 산출 가능, 결정론).
- 2b.3: `cbm_estimator.py`·`replay_outbound_cbm.py` 2커밋 revert → cron 즉시 kit 폴백 중단. 이미 쓰인 estimated_cbm은 다음 replay가 결정론 값으로 idempotent 갱신.

## Out of Scope (P2b)

- partial_skip 32.3%·blank project 12.5% (P5/P3'), Max_CBM 주입·movement 입하 CBM (P3'), 과거 order 소스 (P5), MES 납기일 forecast·규격 보강 (P3'), WMS_BOM 신규행 (금지).
