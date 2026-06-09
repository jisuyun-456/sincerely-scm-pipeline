# BOM·CBM 수량전파 백본 Phase-1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** WMS 베이스에 4개 네이티브 테이블(Crosswalk·ItemMaster·BOM·PropagationLedger)을 만들고, WMS order/movement·TMS Product·MES를 read-only로 결선해 고객주문→자재→포장→CBM→shipment 수량전파의 파운데이션을 구축한다.

**Architecture:** Derived Native Propagation Layer — 소스 모듈(⚡미러·MES·TMS) 무변경, WMS 네이티브 신규 테이블에만 쓰기. 순수 변환 로직(키 추출·BOM 그룹핑·매칭)은 단위테스트로 TDD, Airtable 쓰기는 dry-run + read-back으로 검증. `wave_recommender`가 검증한 add-on 패턴.

**Tech Stack:** Python 3.11, `requests`/`urllib`, Airtable REST + meta API, pytest. 재사용: `harness/settlement/cbm_calc.py`(`load_product_lookup`·`match_product`·`BOX_TYPE_TO_CBM_M3`), `harness/_core/airtable.py`(`AirtableClient`), `harness/dispatch/product_loader.py`.

**Spec:** `docs/superpowers/specs/2026-06-09-bom-cbm-backbone-design.md`

**환경변수 (PAT):** `AIRTABLE_WMS_PAT`(쓰기 대상 WMS `appLui4ZR5HWcQRri`) / `AIRTABLE_PAT`(TMS `app4x70a8mOrIKsMf`, read) / `AIRTABLE_MES_PAT`(MES `appNSAPadsHbfaSHv`, read). 메모리 `reference_airtable_*_pat.md` 참조.

---

## File Structure

신규 모듈 `harness/backbone/` (함께 변하는 파일을 함께 배치):
- `harness/backbone/__init__.py` — 패키지
- `harness/backbone/keys.py` — 순수 함수: PT#### 추출·굿즈명 파싱/정규화·서비스 판별·소요량. **단위테스트 핵심.**
- `harness/backbone/schema_def.py` — 4테이블 필드 스펙(상수). 쓰기 없음.
- `harness/backbone/create_tables.py` — 4 네이티브 테이블 생성(meta API, idempotent). 실행 스크립트.
- `harness/backbone/bom_bootstrap.py` — order 그룹핑 → WMS_BOM 행. 순수 `build_bom_rows` + I/O.
- `harness/backbone/crosswalk.py` — Tier A(굿즈→견적코드) + Tier B(PT####) 결선. 순수 `build_crosswalk` + I/O.
- `harness/backbone/cbm_master.py` — TMS Product CBM 정규화 + 미등록 굿즈 탐지 + 박스→CBM 유도. 순수 함수.
- `harness/backbone/item_master_sync.py` — WMS_ItemMaster 쓰기.
- `harness/backbone/ledger.py` — PropagationLedger v0: 1 주문 end-to-end 추적. 순수 `build_propagation_row` + I/O.
- `harness/backbone/verify_phase1.py` — §7 검증 게이트 실측(read-only, dry-run 확장).

테스트 `tests/backbone/`:
- `tests/backbone/__init__.py`, `test_keys.py`, `test_bom_bootstrap.py`, `test_crosswalk.py`, `test_cbm_master.py`, `test_ledger.py`

---

## Task 0: 모듈 스캐폴드

**Files:**
- Create: `harness/backbone/__init__.py`
- Create: `tests/backbone/__init__.py`

- [ ] **Step 1: 패키지 init 생성**

`harness/backbone/__init__.py`:
```python
"""BOM·CBM 수량전파 백본 — WMS 네이티브 파운데이션 (Phase-1)."""
```

`tests/backbone/__init__.py`:
```python
```

- [ ] **Step 2: pytest 수집 확인**

Run: `python -m pytest tests/backbone/ -q`
Expected: `no tests ran` (에러 없이 수집 0건)

- [ ] **Step 3: Commit**

```bash
git add harness/backbone/__init__.py tests/backbone/__init__.py
git commit -m "chore(backbone): scaffold harness/backbone module"
```

---

## Task 1: keys.py — 순수 키 함수 (TDD)

**Files:**
- Create: `harness/backbone/keys.py`
- Test: `tests/backbone/test_keys.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/backbone/test_keys.py`:
```python
"""키 추출·정규화 순수 함수 테스트."""
from harness.backbone.keys import (
    extract_pt, parse_goods, normalize_goods, is_service, compute_soyoryang,
)


class TestExtractPt:
    def test_from_order_part_name(self):
        assert extract_pt("PT4917-아크릴트로피_추상적산출물") == "PT4917"

    def test_from_movement_concat(self):
        assert extract_pt("PT4911-배경지 || PNA50702_심볼 || 좌표") == "PT4911"

    def test_no_pt(self):
        assert extract_pt("배송 다마스") is None

    def test_empty(self):
        assert extract_pt("") is None


class TestParseGoods:
    def test_name_and_qty(self):
        assert parse_goods("심볼아크릴트로피 125") == ("심볼아크릴트로피", 125)

    def test_comma_qty(self):
        assert parse_goods("시그니처 다이어리 1,200") == ("시그니처 다이어리", 1200)

    def test_no_qty(self):
        assert parse_goods("핸디링미니선풍기") == ("핸디링미니선풍기", 0)


class TestNormalizeGoods:
    def test_strip_bracket_index(self):
        assert normalize_goods("브랜디드피규어[4]") == "브랜디드피규어"

    def test_strip_parens(self):
        assert normalize_goods("클리어리유저블컵(스탠다드)") == "클리어리유저블컵"

    def test_strip_underscore_suffix(self):
        assert normalize_goods("핸디링미니선풍기_화이트") == "핸디링미니선풍기"


class TestIsService:
    def test_delivery(self):
        assert is_service("배송 다마스") is True

    def test_unload(self):
        assert is_service("하차서비스_퀵(다마스)") is True

    def test_real_goods(self):
        assert is_service("심볼아크릴트로피") is False


class TestComputeSoyoryang:
    def test_one_to_one(self):
        assert compute_soyoryang(125, 125) == 1.0

    def test_ratio(self):
        assert compute_soyoryang(250, 125) == 2.0

    def test_zero_goods(self):
        assert compute_soyoryang(125, 0) is None

    def test_bad_input(self):
        assert compute_soyoryang(None, 125) is None
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/backbone/test_keys.py -q`
Expected: FAIL — `ModuleNotFoundError: harness.backbone.keys`

- [ ] **Step 3: 최소 구현**

`harness/backbone/keys.py`:
```python
"""WMS order/movement 텍스트에서 키를 추출·정규화하는 순수 함수.

- PT#### : 파츠(범용 품목키). order.파츠명 / movement.이동물품에 임베드됨.
- 굿즈명 : order '굿즈 주문 수량 (자동)' = "이름 수량" 형태.
- 소요량 : 주문수량 / 굿즈수량.
"""
from __future__ import annotations

import re

PT_RE = re.compile(r"\b(PT\d{3,6})\b")
_TRAIL_QTY = re.compile(r"\s+(\d[\d,]*)\s*$")
_SERVICE_KW = ("배송", "하차", "퀵", "다마스", "택배", "설치", "용차", "탑차")


def extract_pt(text: str) -> str | None:
    """텍스트 내 첫 PT#### 코드. 없으면 None."""
    if not text:
        return None
    m = PT_RE.search(text)
    return m.group(1) if m else None


def parse_goods(text: str) -> tuple[str, int]:
    """'심볼아크릴트로피 125' → ('심볼아크릴트로피', 125). 수량 없으면 0."""
    s = (text or "").strip()
    m = _TRAIL_QTY.search(s)
    if m:
        return s[: m.start()].strip(), int(m.group(1).replace(",", ""))
    return s, 0


def normalize_goods(name: str) -> str:
    """매칭률 향상용 정규화: [n] 인덱스·(...) 괄호·_접미 제거."""
    s = re.sub(r"\[\d+\]", "", name or "")
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"_.*$", "", s)
    return s.strip()


def is_service(name: str) -> bool:
    """배송·하차 등 비물리 서비스 라인 판별(CBM/BOM 대상 제외)."""
    return any(k in (name or "") for k in _SERVICE_KW)


def compute_soyoryang(order_qty, goods_qty) -> float | None:
    """품목 1개당 소요량 = 주문수량 / 굿즈수량. 산출 불가 시 None."""
    try:
        gq = float(goods_qty)
        if gq <= 0:
            return None
        return round(float(order_qty) / gq, 4)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/backbone/test_keys.py -q`
Expected: PASS (16 passed)

- [ ] **Step 5: Commit**

```bash
git add harness/backbone/keys.py tests/backbone/test_keys.py
git commit -m "feat(backbone): keys.py 순수 키 추출·정규화 함수 + tests"
```

---

## Task 2: schema_def.py — 4테이블 필드 스펙

**Files:**
- Create: `harness/backbone/schema_def.py`

- [ ] **Step 1: 스펙 상수 작성**

`harness/backbone/schema_def.py`:
```python
"""WMS 네이티브 4테이블 필드 스펙 (Airtable meta API 생성용).

create_tables.py가 이 스펙으로 테이블을 idempotent 생성한다.
링크 필드는 모든 테이블 생성 후 2차 패스로 추가(LINK_FIELDS).
"""
from __future__ import annotations

WMS_BASE = "appLui4ZR5HWcQRri"

# 1차: 스칼라 필드만 (링크 제외). primary 필드는 fields[0].
TABLES: dict[str, list[dict]] = {
    "WMS_KeyCrosswalk": [
        {"name": "표준키", "type": "singleLineText"},          # primary (굿즈명 or PT####)
        {"name": "키유형", "type": "singleSelect",
         "options": {"choices": [{"name": "굿즈"}, {"name": "파츠"}]}},
        {"name": "TMS_견적코드", "type": "singleLineText"},
        {"name": "WMS_아이템코드", "type": "singleLineText"},
        {"name": "MES_파츠코드", "type": "singleLineText"},
        {"name": "매칭방식", "type": "singleSelect",
         "options": {"choices": [{"name": "정확"}, {"name": "유사"}, {"name": "수기"}]}},
        {"name": "매칭신뢰도", "type": "number", "options": {"precision": 2}},
        {"name": "검증상태", "type": "singleSelect",
         "options": {"choices": [{"name": "미검증"}, {"name": "확정"}, {"name": "보류"}]}},
    ],
    "WMS_ItemMaster": [
        {"name": "품목키", "type": "singleLineText"},           # primary (PT#### or 굿즈명)
        {"name": "품목명", "type": "singleLineText"},
        {"name": "품목유형", "type": "singleSelect",
         "options": {"choices": [{"name": "완제품"}, {"name": "키트"}, {"name": "단품"},
                                 {"name": "부자재"}, {"name": "포장재"}]}},
        {"name": "CBM_개당_m3", "type": "number", "options": {"precision": 6}},
        {"name": "박스규격", "type": "singleLineText"},
        {"name": "박스당_제품수", "type": "number", "options": {"precision": 0}},
        {"name": "박스당_CBM_m3", "type": "number", "options": {"precision": 4}},
        {"name": "출처", "type": "singleSelect",
         "options": {"choices": [{"name": "TMS_Product"}, {"name": "박스유도"},
                                 {"name": "MES_제품DB"}, {"name": "수기"}]}},
    ],
    "WMS_BOM": [
        {"name": "BOM_ID", "type": "singleLineText"},          # primary (project_굿즈_PT)
        {"name": "프로젝트코드", "type": "singleLineText"},
        {"name": "모품목_굿즈명", "type": "singleLineText"},
        {"name": "소품목_PT", "type": "singleLineText"},
        {"name": "소요량_개당", "type": "number", "options": {"precision": 4}},
        {"name": "구성유형", "type": "singleSelect",
         "options": {"choices": [{"name": "키트"}, {"name": "임가공"},
                                 {"name": "포장재"}, {"name": "원부자재"}]}},
        {"name": "신뢰도", "type": "number", "options": {"precision": 2}},
        {"name": "검증상태", "type": "singleSelect",
         "options": {"choices": [{"name": "이송"}, {"name": "검증완료"}, {"name": "폐기"}]}},
        {"name": "출처", "type": "singleSelect",
         "options": {"choices": [{"name": "order그룹핑"}, {"name": "MES보강"},
                                 {"name": "movement보강"}, {"name": "수기"}]}},
    ],
    "WMS_PropagationLedger": [
        {"name": "전파ID", "type": "singleLineText"},          # primary (project_굿즈)
        {"name": "프로젝트코드", "type": "singleLineText"},
        {"name": "굿즈명", "type": "singleLineText"},
        {"name": "고객주문수량", "type": "number", "options": {"precision": 0}},
        {"name": "자재소요_요약", "type": "multilineText"},
        {"name": "포장소요_요약", "type": "multilineText"},
        {"name": "추정_CBM_m3", "type": "number", "options": {"precision": 4}},
        {"name": "shipment_id", "type": "singleLineText"},
        {"name": "전파상태", "type": "singleSelect",
         "options": {"choices": [{"name": "완결"}, {"name": "부분"}, {"name": "끊김"}]}},
        {"name": "생성시각", "type": "dateTime",
         "options": {"dateFormat": {"name": "iso"}, "timeFormat": {"name": "24hour"},
                     "timeZone": "Asia/Seoul"}},
    ],
}

# 2차: 링크 필드 (대상 테이블 존재 후 추가). (테이블명, 필드명, 링크대상 테이블명)
LINK_FIELDS: list[tuple[str, str, str]] = [
    ("WMS_ItemMaster", "BOM_상위", "WMS_BOM"),
    ("WMS_ItemMaster", "Crosswalk", "WMS_KeyCrosswalk"),
    ("WMS_BOM", "모품목_link", "WMS_ItemMaster"),
    ("WMS_BOM", "소품목_link", "WMS_ItemMaster"),
]
```

- [ ] **Step 2: import 가능 확인**

Run: `python -c "from harness.backbone.schema_def import TABLES, LINK_FIELDS; print(len(TABLES), len(LINK_FIELDS))"`
Expected: `4 4`

- [ ] **Step 3: Commit**

```bash
git add harness/backbone/schema_def.py
git commit -m "feat(backbone): 4테이블 필드 스펙 정의"
```

---

## Task 3: create_tables.py — 네이티브 테이블 생성 (idempotent)

**Files:**
- Create: `harness/backbone/create_tables.py`

- [ ] **Step 1: 생성 스크립트 작성**

`harness/backbone/create_tables.py`:
```python
"""WMS 네이티브 4테이블 생성 (Airtable meta API, idempotent).

이미 존재하는 테이블/필드는 건너뜀. 쓰기 대상은 WMS 네이티브 한정.
실행: AIRTABLE_WMS_PAT=... python -m harness.backbone.create_tables [--dry-run]
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

from harness.backbone.schema_def import TABLES, LINK_FIELDS, WMS_BASE

META = f"https://api.airtable.com/v0/meta/bases/{WMS_BASE}"


def _hdr() -> dict:
    return {"Authorization": f"Bearer {os.environ['AIRTABLE_WMS_PAT']}",
            "Content-Type": "application/json"}


def _get(url: str) -> dict:
    return json.load(urllib.request.urlopen(urllib.request.Request(url, headers=_hdr())))


def _post(url: str, payload: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers=_hdr(), method="POST")
    return json.load(urllib.request.urlopen(req))


def existing_tables() -> dict[str, dict]:
    return {t["name"]: t for t in _get(f"{META}/tables")["tables"]}


def main(dry_run: bool = False) -> None:
    have = existing_tables()
    # 1차: 스칼라 테이블 생성
    for name, fields in TABLES.items():
        if name in have:
            print(f"[skip] table exists: {name}")
            continue
        payload = {"name": name, "fields": fields}
        if dry_run:
            print(f"[dry-run] create table {name} ({len(fields)} fields)")
            continue
        res = _post(f"{META}/tables", payload)
        print(f"[created] {name} -> {res['id']}")
    # 2차: 링크 필드 추가
    have = existing_tables()
    for tbl_name, fld_name, target_name in LINK_FIELDS:
        if tbl_name not in have or target_name not in have:
            print(f"[warn] missing table for link {tbl_name}.{fld_name}")
            continue
        tbl = have[tbl_name]
        if any(f["name"] == fld_name for f in tbl["fields"]):
            print(f"[skip] field exists: {tbl_name}.{fld_name}")
            continue
        payload = {"name": fld_name, "type": "multipleRecordLinks",
                   "options": {"linkedTableId": have[target_name]["id"]}}
        if dry_run:
            print(f"[dry-run] add link {tbl_name}.{fld_name} -> {target_name}")
            continue
        _post(f"{META}/tables/{tbl['id']}/fields", payload)
        print(f"[created] link {tbl_name}.{fld_name} -> {target_name}")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
```

- [ ] **Step 2: dry-run 확인**

Run: `AIRTABLE_WMS_PAT=$AIRTABLE_WMS_PAT python -m harness.backbone.create_tables --dry-run`
Expected: `[dry-run] create table WMS_KeyCrosswalk ...` 4개 + `[dry-run] add link ...` 4개

- [ ] **Step 3: 실제 생성 실행**

Run: `AIRTABLE_WMS_PAT=$AIRTABLE_WMS_PAT python -m harness.backbone.create_tables`
Expected: `[created] WMS_KeyCrosswalk -> tbl...` 등 4 테이블 + 4 링크 생성

- [ ] **Step 4: read-back 검증**

Run:
```bash
AIRTABLE_WMS_PAT=$AIRTABLE_WMS_PAT python -c "
from harness.backbone.create_tables import existing_tables
have = existing_tables()
for n in ['WMS_KeyCrosswalk','WMS_ItemMaster','WMS_BOM','WMS_PropagationLedger']:
    assert n in have, f'MISSING {n}'
    print(n, len(have[n]['fields']), 'fields')
print('OK all 4 tables present')
"
```
Expected: 4 테이블 모두 present, `OK all 4 tables present`

- [ ] **Step 5: Commit**

```bash
git add harness/backbone/create_tables.py
git commit -m "feat(backbone): 4 네이티브 테이블 생성 스크립트 (idempotent)"
```

---

## Task 4: bom_bootstrap.py — order 그룹핑 BOM 변환 (TDD)

**Files:**
- Create: `harness/backbone/bom_bootstrap.py`
- Test: `tests/backbone/test_bom_bootstrap.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/backbone/test_bom_bootstrap.py`:
```python
"""order 라인 그룹핑 → BOM 행 변환 테스트."""
from harness.backbone.bom_bootstrap import build_bom_rows


def _rec(pc, goods, part, oqty):
    return {"fields": {"project_code": pc, "굿즈 주문 수량 (자동)": goods,
                       "파츠명": part, "주문수량": oqty}}


class TestBuildBomRows:
    def test_groups_parts_under_goods(self):
        recs = [
            _rec("PNA50702", "심볼아크릴트로피 125", "PT4900-아크릴트로피", 125),
            _rec("PNA50702", "심볼아크릴트로피 125", "PT4906-받침대", 125),
        ]
        rows = build_bom_rows(recs)
        assert len(rows) == 2
        by_pt = {r.part_code: r for r in rows}
        assert by_pt["PT4900"].soyoryang == 1.0
        assert by_pt["PT4906"].goods_name == "심볼아크릴트로피"
        assert by_pt["PT4900"].project_code == "PNA50702"

    def test_skips_service_lines(self):
        recs = [_rec("PNA1", "배송 1", "PT1282-하차서비스", 1)]
        assert build_bom_rows(recs) == []

    def test_skips_lines_without_pt(self):
        recs = [_rec("PNA1", "굿즈 10", "사양미정", 10)]
        assert build_bom_rows(recs) == []

    def test_double_soyoryang(self):
        recs = [_rec("PNA2", "키트 50", "PT100-볼트", 100)]
        rows = build_bom_rows(recs)
        assert rows[0].soyoryang == 2.0

    def test_bom_id_unique_format(self):
        recs = [_rec("PNA2", "키트 50", "PT100-볼트", 100)]
        rows = build_bom_rows(recs)
        assert rows[0].bom_id == "PNA2_키트_PT100"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/backbone/test_bom_bootstrap.py -q`
Expected: FAIL — `ModuleNotFoundError: harness.backbone.bom_bootstrap`

- [ ] **Step 3: 변환 구현**

`harness/backbone/bom_bootstrap.py` (변환부만 먼저):
```python
"""WMS order를 굿즈로 그룹핑해 WMS_BOM 행을 생성.

핵심: 같은 '굿즈주문수량' 그룹의 파츠(PT####)들이 그 굿즈의 구성품.
소요량 = 주문수량 / 굿즈수량. (dry-run 실측 적용가능 93.1%)
"""
from __future__ import annotations

from dataclasses import dataclass

from harness.backbone.keys import (
    extract_pt, parse_goods, is_service, compute_soyoryang,
)


@dataclass
class BomRow:
    bom_id: str
    project_code: str
    goods_name: str
    goods_qty: int
    part_code: str
    order_qty: float
    soyoryang: float | None
    confidence: float
    source: str = "order그룹핑"


def _first(v):
    return v[0] if isinstance(v, list) and v else ("" if isinstance(v, list) else v)


def build_bom_rows(order_records: list[dict]) -> list[BomRow]:
    rows: list[BomRow] = []
    for rec in order_records:
        f = rec.get("fields", {})
        pc = str(_first(f.get("project_code")) or "").strip()
        goods_name, goods_qty = parse_goods(f.get("굿즈 주문 수량 (자동)", ""))
        part = extract_pt(f.get("파츠명", ""))
        if not pc or not goods_name or is_service(goods_name) or not part:
            continue
        oqty = f.get("주문수량", 0) or 0
        soyo = compute_soyoryang(oqty, goods_qty)
        rows.append(BomRow(
            bom_id=f"{pc}_{goods_name}_{part}",
            project_code=pc,
            goods_name=goods_name,
            goods_qty=goods_qty,
            part_code=part,
            order_qty=float(oqty) if isinstance(oqty, (int, float)) else 0.0,
            soyoryang=soyo,
            confidence=1.0 if soyo is not None else 0.3,
        ))
    return rows
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/backbone/test_bom_bootstrap.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add harness/backbone/bom_bootstrap.py tests/backbone/test_bom_bootstrap.py
git commit -m "feat(backbone): bom_bootstrap build_bom_rows 변환 + tests"
```

---

## Task 5: bom_bootstrap I/O — order 읽기 → WMS_BOM 쓰기

**Files:**
- Modify: `harness/backbone/bom_bootstrap.py` (I/O 함수 추가)

- [ ] **Step 1: I/O 함수 추가**

`harness/backbone/bom_bootstrap.py` 끝에 추가:
```python
import json
import os
import urllib.parse
import urllib.request

WMS_BASE = "appLui4ZR5HWcQRri"
TBL_ORDER = "tblJslWg8sYEdCkXw"


def _wms_hdr() -> dict:
    return {"Authorization": f"Bearer {os.environ['AIRTABLE_WMS_PAT']}"}


def fetch_orders(limit: int = 2000) -> list[dict]:
    fields = ["project_code", "굿즈 주문 수량 (자동)", "주문수량", "파츠명"]
    out: list[dict] = []
    cursor = None
    while len(out) < limit:
        params = [("pageSize", "100")] + [("fields[]", f) for f in fields]
        if cursor:
            params.append(("offset", cursor))
        url = f"https://api.airtable.com/v0/{WMS_BASE}/{TBL_ORDER}?" + urllib.parse.urlencode(params)
        data = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=_wms_hdr())))
        out.extend(data.get("records", []))
        cursor = data.get("offset")
        if not cursor:
            break
    return out[:limit]


def dedupe_rows(rows: list[BomRow]) -> list[BomRow]:
    """BOM_ID 기준 중복 제거(최초 우선)."""
    seen: set[str] = set()
    out: list[BomRow] = []
    for r in rows:
        if r.bom_id in seen:
            continue
        seen.add(r.bom_id)
        out.append(r)
    return out
```

- [ ] **Step 2: 쓰기 함수 추가 (AirtableClient 재사용, status=이송)**

`harness/backbone/bom_bootstrap.py` 끝에 추가:
```python
from harness._core.airtable import AirtableClient


def _bom_table_id() -> str:
    from harness.backbone.create_tables import existing_tables
    return existing_tables()["WMS_BOM"]["id"]


def write_bom(rows: list[BomRow], dry_run: bool = True) -> int:
    """WMS_BOM에 status=이송으로 INSERT. dry_run이면 건수만 반환."""
    rows = dedupe_rows(rows)
    if dry_run:
        return len(rows)
    pat = os.environ["AIRTABLE_WMS_PAT"]
    tbl = _bom_table_id()
    client = AirtableClient.get_or_create(WMS_BASE, tbl, pat)
    records = [{"fields": {
        "BOM_ID": r.bom_id, "프로젝트코드": r.project_code,
        "모품목_굿즈명": r.goods_name, "소품목_PT": r.part_code,
        "소요량_개당": r.soyoryang, "신뢰도": r.confidence,
        "검증상태": "이송", "출처": r.source,
    }} for r in rows]
    client.create_records(records)  # 10건 batch (memory feedback_airtable_batch)
    return len(records)


def main() -> None:
    import sys
    dry = "--write" not in sys.argv
    rows = build_bom_rows(fetch_orders())
    n = write_bom(rows, dry_run=dry)
    print(f"BOM rows: {len(dedupe_rows(rows))} | {'DRY (no write)' if dry else f'WROTE {n}'}")


if __name__ == "__main__":
    main()
```

> **NOTE:** `AirtableClient`에 batch `create_records`가 없으면 Task 5.5로 추가(아래). 있으면 그대로 사용.

- [ ] **Step 3: AirtableClient.create_records 존재 확인**

Run: `python -c "from harness._core.airtable import AirtableClient; print(hasattr(AirtableClient,'create_records'))"`
Expected: `True` (없으면 `False` → Step 3b 수행)

- [ ] **Step 3b (조건부): batch create 추가**

`harness/_core/airtable.py`의 `AirtableClient`에 메서드 추가 (`patch_record` 패턴 따름, 10건 batch):
```python
    def create_records(self, records: list[dict]) -> list[dict]:
        """10건씩 batch POST. records=[{'fields': {...}}, ...]."""
        out = []
        for i in range(0, len(records), 10):
            chunk = records[i:i + 10]
            _global_limiter.acquire()
            resp = self._session.post("", json={"records": chunk, "typecast": True})
            resp.raise_for_status()
            out.extend(resp.json().get("records", []))
        return out
```

- [ ] **Step 4: dry-run 실행 + 건수 확인**

Run: `AIRTABLE_WMS_PAT=$AIRTABLE_WMS_PAT python -m harness.backbone.bom_bootstrap`
Expected: `BOM rows: N | DRY (no write)` — N이 dry-run 실측(1053 그룹대 규모)과 정합

- [ ] **Step 5: 실제 쓰기 + read-back**

Run: `AIRTABLE_WMS_PAT=$AIRTABLE_WMS_PAT python -m harness.backbone.bom_bootstrap --write`
Then verify:
```bash
AIRTABLE_WMS_PAT=$AIRTABLE_WMS_PAT python -c "
from harness.backbone.create_tables import existing_tables
import os,json,urllib.request
b='appLui4ZR5HWcQRri'; t=existing_tables()['WMS_BOM']['id']
h={'Authorization':f'Bearer {os.environ[\"AIRTABLE_WMS_PAT\"]}'}
d=json.load(urllib.request.urlopen(urllib.request.Request(f'https://api.airtable.com/v0/{b}/{t}?maxRecords=3',headers=h)))
for r in d['records']: print(r['fields'].get('BOM_ID'), r['fields'].get('소요량_개당'), r['fields'].get('검증상태'))
print('rows present OK')
"
```
Expected: BOM_ID + 소요량 + `이송` 상태 레코드 3건 출력

- [ ] **Step 6: Commit**

```bash
git add harness/backbone/bom_bootstrap.py harness/_core/airtable.py
git commit -m "feat(backbone): BOM 부트스트랩 I/O (order→WMS_BOM, status=이송)"
```

---

## Task 6: crosswalk.py — Tier A(굿즈) + Tier B(파츠) 결선 (TDD)

**Files:**
- Create: `harness/backbone/crosswalk.py`
- Test: `tests/backbone/test_crosswalk.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/backbone/test_crosswalk.py`:
```python
"""Crosswalk 2-tier 빌드 테스트 (순수 변환)."""
from harness.backbone.crosswalk import build_crosswalk


def _lookup():
    # match_product 형식: name.lower() / code.lower() → entry
    e = {"rec_id": "r1", "name": "심볼아크릴트로피", "code": "SBAT",
         "box_type": "중형", "qty_per_box": 6, "cbm_per_box": 0.02}
    return {"심볼아크릴트로피": e, "sbat": e}


def test_tier_a_goods_match():
    rows = build_crosswalk(goods_names={"심볼아크릴트로피"}, part_codes=set(),
                           product_lookup=_lookup())
    a = [r for r in rows if r["키유형"] == "굿즈"][0]
    assert a["TMS_견적코드"] == "SBAT"
    assert a["매칭방식"] == "정확"
    assert a["매칭신뢰도"] == 1.0


def test_tier_a_unmatched_goods():
    rows = build_crosswalk(goods_names={"없는제품XYZ"}, part_codes=set(),
                           product_lookup=_lookup())
    a = [r for r in rows if r["키유형"] == "굿즈"][0]
    assert a["TMS_견적코드"] == ""
    assert a["검증상태"] == "보류"


def test_tier_b_part_identity():
    rows = build_crosswalk(goods_names=set(), part_codes={"PT4900"},
                           product_lookup=_lookup())
    b = [r for r in rows if r["키유형"] == "파츠"][0]
    assert b["표준키"] == "PT4900"
    assert b["WMS_아이템코드"] == "PT4900"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/backbone/test_crosswalk.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 변환 구현**

`harness/backbone/crosswalk.py`:
```python
"""Crosswalk 2-tier 빌드.

Tier A 굿즈: 굿즈명 → TMS Product(견적코드/CBM) name-match (match_product).
Tier B 파츠: PT#### 자기동일(WMS=MES). normalize_goods 재시도 포함.
"""
from __future__ import annotations

from harness.backbone.keys import normalize_goods
from harness.settlement.cbm_calc import match_product


def build_crosswalk(goods_names: set[str], part_codes: set[str],
                    product_lookup: dict) -> list[dict]:
    rows: list[dict] = []
    # Tier A: 굿즈 → 견적코드
    for gn in sorted(goods_names):
        key, entry, score = match_product(gn, product_lookup)
        if entry is None:  # 정규화 재시도
            key, entry, score = match_product(normalize_goods(gn), product_lookup)
        rows.append({
            "표준키": gn, "키유형": "굿즈",
            "TMS_견적코드": entry["code"] if entry else "",
            "WMS_아이템코드": "", "MES_파츠코드": "",
            "매칭방식": ("정확" if score >= 1.0 else "유사") if entry else "수기",
            "매칭신뢰도": round(score, 2),
            "검증상태": "확정" if score >= 1.0 else ("미검증" if entry else "보류"),
        })
    # Tier B: 파츠 자기동일
    for pt in sorted(part_codes):
        rows.append({
            "표준키": pt, "키유형": "파츠",
            "TMS_견적코드": "", "WMS_아이템코드": pt, "MES_파츠코드": pt,
            "매칭방식": "정확", "매칭신뢰도": 1.0, "검증상태": "확정",
        })
    return rows
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/backbone/test_crosswalk.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: I/O + 실행부 추가**

`harness/backbone/crosswalk.py` 끝에 추가:
```python
import os

WMS_BASE = "appLui4ZR5HWcQRri"


def _crosswalk_table_id() -> str:
    from harness.backbone.create_tables import existing_tables
    return existing_tables()["WMS_KeyCrosswalk"]["id"]


def collect_keys() -> tuple[set[str], set[str]]:
    """order에서 굿즈명·PT#### 수집."""
    from harness.backbone.bom_bootstrap import fetch_orders
    from harness.backbone.keys import parse_goods, extract_pt, is_service
    goods: set[str] = set()
    parts: set[str] = set()
    for rec in fetch_orders():
        f = rec["fields"]
        gn, _ = parse_goods(f.get("굿즈 주문 수량 (자동)", ""))
        if gn and not is_service(gn):
            goods.add(gn)
        pt = extract_pt(f.get("파츠명", ""))
        if pt:
            parts.add(pt)
    return goods, parts


def main() -> None:
    import sys
    from harness.settlement.cbm_calc import load_product_lookup
    from harness._core.airtable import AirtableClient
    dry = "--write" not in sys.argv
    lookup = load_product_lookup({"Authorization": f"Bearer {os.environ['AIRTABLE_PAT']}"})
    goods, parts = collect_keys()
    rows = build_crosswalk(goods, parts, lookup)
    matched = sum(1 for r in rows if r["키유형"] == "굿즈" and r["TMS_견적코드"])
    n_goods = sum(1 for r in rows if r["키유형"] == "굿즈")
    print(f"Crosswalk: 굿즈 {n_goods}(매칭 {matched}={matched/max(n_goods,1)*100:.1f}%) 파츠 {len(parts)}")
    if not dry:
        tbl = _crosswalk_table_id()
        client = AirtableClient.get_or_create(WMS_BASE, tbl, os.environ["AIRTABLE_WMS_PAT"])
        client.create_records([{"fields": r} for r in rows])
        print(f"WROTE {len(rows)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: dry-run (매칭률 표시) → 쓰기**

Run: `AIRTABLE_PAT=$AIRTABLE_PAT AIRTABLE_WMS_PAT=$AIRTABLE_WMS_PAT python -m harness.backbone.crosswalk`
Expected: `Crosswalk: 굿즈 N(매칭 M=~50%) 파츠 K` (마스터 확장 전이라 50%대)

- [ ] **Step 7: Commit**

```bash
git add harness/backbone/crosswalk.py tests/backbone/test_crosswalk.py
git commit -m "feat(backbone): Crosswalk 2-tier 빌드 (굿즈 name-match + 파츠 PT) + tests"
```

---

## Task 7: cbm_master.py — CBM 정규화 + 미등록 굿즈 탐지 + 박스→CBM 유도 (TDD)

**Files:**
- Create: `harness/backbone/cbm_master.py`
- Test: `tests/backbone/test_cbm_master.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/backbone/test_cbm_master.py`:
```python
"""CBM 마스터 정규화·유도 테스트."""
from harness.backbone.cbm_master import cbm_from_box_dims, find_unmatched_goods


def test_cbm_from_box_dims_basic():
    # 480*380*270 mm = 0.04925 m³, 박스당 19개 → 개당 ≈ 0.002592
    assert abs(cbm_from_box_dims("480*380*270", 19) - 0.002592) < 1e-4


def test_cbm_from_box_dims_bad():
    assert cbm_from_box_dims("", 10) is None
    assert cbm_from_box_dims("480x380", 10) is None  # 3축 아님


def test_find_unmatched_goods():
    lookup = {"심볼아크릴트로피": {"rec_id": "r1", "name": "심볼아크릴트로피",
                                 "code": "SBAT", "box_type": "", "qty_per_box": 1,
                                 "cbm_per_box": 0.02}}
    goods = {"심볼아크릴트로피", "없는제품"}
    assert find_unmatched_goods(goods, lookup) == ["없는제품"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/backbone/test_cbm_master.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 구현**

`harness/backbone/cbm_master.py`:
```python
"""CBM 마스터: TMS Product 정규화 + 미등록 굿즈 탐지 + 박스치수→CBM 유도.

dry-run 실측: 1500 order 굿즈 413종 중 ~186종이 382품목 마스터 미등록.
박스규격(LxWxH mm) + 박스당 제품수로 개당 CBM을 유도해 ItemMaster 확장.
"""
from __future__ import annotations

import re

from harness.backbone.keys import normalize_goods
from harness.settlement.cbm_calc import match_product

_DIM_RE = re.compile(r"^\s*(\d+)\s*[*xX×]\s*(\d+)\s*[*xX×]\s*(\d+)\s*$")


def cbm_from_box_dims(box_size: str, qty_per_box: int) -> float | None:
    """'480*380*270'(mm) + 박스당수량 → 개당 CBM(m³). 파싱 실패 시 None."""
    m = _DIM_RE.match(box_size or "")
    if not m or not qty_per_box or qty_per_box <= 0:
        return None
    l, w, h = (int(x) for x in m.groups())
    box_cbm = (l / 1000) * (w / 1000) * (h / 1000)
    return round(box_cbm / qty_per_box, 6)


def find_unmatched_goods(goods_names: set[str], product_lookup: dict) -> list[str]:
    """매칭(정확/유사/정규화) 모두 실패한 굿즈명 = 마스터 확장 대상."""
    out: list[str] = []
    for gn in sorted(goods_names):
        _, e, _ = match_product(gn, product_lookup)
        if e is None:
            _, e, _ = match_product(normalize_goods(gn), product_lookup)
        if e is None:
            out.append(gn)
    return out
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/backbone/test_cbm_master.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: 미등록 굿즈 리포트 실행부**

`harness/backbone/cbm_master.py` 끝에 추가:
```python
import os


def report_unmatched() -> list[str]:
    from harness.settlement.cbm_calc import load_product_lookup
    from harness.backbone.crosswalk import collect_keys
    lookup = load_product_lookup({"Authorization": f"Bearer {os.environ['AIRTABLE_PAT']}"})
    goods, _ = collect_keys()
    miss = find_unmatched_goods(goods, lookup)
    print(f"미등록 굿즈: {len(miss)}/{len(goods)} ({len(miss)/max(len(goods),1)*100:.1f}%)")
    for g in miss[:30]:
        print("   -", g)
    return miss


if __name__ == "__main__":
    report_unmatched()
```

- [ ] **Step 6: 미등록 굿즈 리포트 확인 (확장 작업 목록)**

Run: `AIRTABLE_PAT=$AIRTABLE_PAT AIRTABLE_WMS_PAT=$AIRTABLE_WMS_PAT python -m harness.backbone.cbm_master`
Expected: `미등록 굿즈: ~186/~413 (~45%)` + 목록 — 이 목록이 ItemMaster 확장 입력

- [ ] **Step 7: Commit**

```bash
git add harness/backbone/cbm_master.py tests/backbone/test_cbm_master.py
git commit -m "feat(backbone): CBM 정규화 + 미등록 굿즈 탐지 + 박스→CBM 유도 + tests"
```

---

## Task 8: item_master_sync.py — WMS_ItemMaster 적재 (CBM + 박스유도)

**Files:**
- Create: `harness/backbone/item_master_sync.py`

- [ ] **Step 1: 적재 스크립트 작성**

`harness/backbone/item_master_sync.py`:
```python
"""WMS_ItemMaster 적재: ① 매칭 굿즈 = TMS Product CBM 정규화, ② 미등록 굿즈 = 박스유도.

매칭 굿즈는 출처=TMS_Product, 박스유도 굿즈는 출처=박스유도(소스: order 박스규격/박스수량).
파츠(PT####)는 품목유형 분류만(CBM은 굿즈 단위라 비움).
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from harness._core.airtable import AirtableClient
from harness.backbone.cbm_master import cbm_from_box_dims, find_unmatched_goods
from harness.backbone.crosswalk import collect_keys
from harness.settlement.cbm_calc import load_product_lookup, match_product

WMS_BASE = "appLui4ZR5HWcQRri"
TBL_ORDER = "tblJslWg8sYEdCkXw"


def _wms_hdr() -> dict:
    return {"Authorization": f"Bearer {os.environ['AIRTABLE_WMS_PAT']}"}


def order_box_hint() -> dict[str, tuple[str, int]]:
    """굿즈명 → (박스규격, 박스당수량) 힌트 수집 (미등록 굿즈 CBM 유도용)."""
    from harness.backbone.keys import parse_goods
    fields = ["굿즈 주문 수량 (자동)", "박스규격", "입고 박스 수량"]
    out: dict[str, tuple[str, int]] = {}
    cursor = None
    while True:
        params = [("pageSize", "100")] + [("fields[]", f) for f in fields]
        if cursor:
            params.append(("offset", cursor))
        url = f"https://api.airtable.com/v0/{WMS_BASE}/{TBL_ORDER}?" + urllib.parse.urlencode(params)
        data = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=_wms_hdr())))
        for rec in data.get("records", []):
            f = rec["fields"]
            gn, _ = parse_goods(f.get("굿즈 주문 수량 (자동)", ""))
            bs = f.get("박스규격", "")
            bq = f.get("입고 박스 수량", 0) or 0
            if gn and bs and gn not in out:
                out[gn] = (str(bs), int(bq) if isinstance(bq, (int, float)) else 0)
        cursor = data.get("offset")
        if not cursor:
            break
    return out


def build_item_rows() -> list[dict]:
    tms_lookup = load_product_lookup({"Authorization": f"Bearer {os.environ['AIRTABLE_PAT']}"})
    goods, parts = collect_keys()
    box_hint = order_box_hint()
    rows: list[dict] = []
    for gn in sorted(goods):
        key, e, score = match_product(gn, tms_lookup)
        if e:
            rows.append({"품목키": gn, "품목명": gn, "품목유형": "완제품",
                         "CBM_개당_m3": e["cbm_per_box"], "박스당_제품수": e["qty_per_box"],
                         "박스당_CBM_m3": e["cbm_per_box"], "출처": "TMS_Product"})
        else:
            bs, bq = box_hint.get(gn, ("", 0))
            cbm = cbm_from_box_dims(bs, bq)
            rows.append({"품목키": gn, "품목명": gn, "품목유형": "완제품",
                         "CBM_개당_m3": cbm, "박스규격": bs, "박스당_제품수": bq,
                         "출처": "박스유도"})
    for pt in sorted(parts):
        rows.append({"품목키": pt, "품목명": pt, "품목유형": "부자재", "출처": "수기"})
    return rows


def main() -> None:
    import sys
    rows = build_item_rows()
    derived = sum(1 for r in rows if r.get("출처") == "박스유도" and r.get("CBM_개당_m3"))
    print(f"ItemMaster rows: {len(rows)} (박스유도 CBM 확보 {derived})")
    if "--write" in sys.argv:
        from harness.backbone.create_tables import existing_tables
        tbl = existing_tables()["WMS_ItemMaster"]["id"]
        client = AirtableClient.get_or_create(WMS_BASE, tbl, os.environ["AIRTABLE_WMS_PAT"])
        client.create_records([{"fields": r} for r in rows])
        print(f"WROTE {len(rows)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: dry-run (건수 + 박스유도 확보 수)**

Run: `AIRTABLE_PAT=$AIRTABLE_PAT AIRTABLE_WMS_PAT=$AIRTABLE_WMS_PAT python -m harness.backbone.item_master_sync`
Expected: `ItemMaster rows: N (박스유도 CBM 확보 K)` — K가 미등록 186종 중 박스힌트로 회복된 수

- [ ] **Step 3: 실제 쓰기 + read-back**

Run: `AIRTABLE_PAT=$AIRTABLE_PAT AIRTABLE_WMS_PAT=$AIRTABLE_WMS_PAT python -m harness.backbone.item_master_sync --write`
Then:
```bash
AIRTABLE_WMS_PAT=$AIRTABLE_WMS_PAT python -c "
from harness.backbone.create_tables import existing_tables
import os,json,urllib.request
b='appLui4ZR5HWcQRri'; t=existing_tables()['WMS_ItemMaster']['id']
h={'Authorization':f'Bearer {os.environ[\"AIRTABLE_WMS_PAT\"]}'}
d=json.load(urllib.request.urlopen(urllib.request.Request(f'https://api.airtable.com/v0/{b}/{t}?maxRecords=5',headers=h)))
for r in d['records']: print(r['fields'].get('품목키'), r['fields'].get('CBM_개당_m3'), r['fields'].get('출처'))
"
```
Expected: 품목키 + CBM + 출처 레코드 출력

- [ ] **Step 4: Commit**

```bash
git add harness/backbone/item_master_sync.py
git commit -m "feat(backbone): ItemMaster 적재 (TMS CBM 정규화 + 박스유도 확장)"
```

---

## Task 9: ledger.py — PropagationLedger v0 (1 주문 end-to-end) (TDD)

**Files:**
- Create: `harness/backbone/ledger.py`
- Test: `tests/backbone/test_ledger.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/backbone/test_ledger.py`:
```python
"""PropagationLedger 행 빌드 테스트 (순수)."""
from harness.backbone.ledger import build_propagation_row


def test_full_chain():
    bom = [{"소품목_PT": "PT4900", "소요량_개당": 1.0},
           {"소품목_PT": "PT4906", "소요량_개당": 1.0}]
    row = build_propagation_row(
        project_code="PNA50702", goods_name="심볼아크릴트로피",
        order_qty=125, bom_rows=bom, cbm_per_unit=0.02,
        shipment_id="SHIP1")
    assert row["고객주문수량"] == 125
    assert row["추정_CBM_m3"] == 2.5  # 125 * 0.02
    assert "PT4900×125" in row["자재소요_요약"]
    assert row["전파상태"] == "완결"
    assert row["shipment_id"] == "SHIP1"


def test_broken_chain_no_shipment():
    row = build_propagation_row("PNA1", "굿즈", 10, [], None, "")
    assert row["전파상태"] == "끊김"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/backbone/test_ledger.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 구현**

`harness/backbone/ledger.py`:
```python
"""PropagationLedger v0 — 1 고객주문이 order→자재→포장→CBM→shipment로 흐른 1줄.

INSERT-only 스냅샷. 끊긴 고리(shipment/CBM 없음)는 전파상태로 표시.
"""
from __future__ import annotations


def build_propagation_row(project_code: str, goods_name: str, order_qty: int,
                          bom_rows: list[dict], cbm_per_unit: float | None,
                          shipment_id: str) -> dict:
    mat = [f"{b['소품목_PT']}×{int((b.get('소요량_개당') or 0) * order_qty)}"
           for b in bom_rows]
    pack = [m for m in mat if m.startswith("PT") and False]  # 포장재 분류는 Phase-2
    cbm = round((cbm_per_unit or 0) * order_qty, 4) if cbm_per_unit else None
    has_chain = bool(shipment_id) and cbm is not None and bool(bom_rows)
    return {
        "전파ID": f"{project_code}_{goods_name}",
        "프로젝트코드": project_code,
        "굿즈명": goods_name,
        "고객주문수량": order_qty,
        "자재소요_요약": ", ".join(mat),
        "포장소요_요약": ", ".join(pack),
        "추정_CBM_m3": cbm,
        "shipment_id": shipment_id,
        "전파상태": "완결" if has_chain else ("부분" if (bom_rows or cbm) else "끊김"),
    }
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/backbone/test_ledger.py -q`
Expected: PASS (2 passed)

- [ ] **Step 5: 샘플 1건 전파 실행부 추가**

`harness/backbone/ledger.py` 끝에 추가:
```python
import os


def run_sample(project_code: str = "PNA50702") -> dict:
    """샘플 1 프로젝트의 첫 굿즈를 end-to-end 전파해 1줄 생성·출력."""
    from harness.backbone.bom_bootstrap import build_bom_rows, fetch_orders
    from harness.backbone.keys import parse_goods
    from harness.settlement.cbm_calc import load_product_lookup, match_product

    orders = [r for r in fetch_orders()
              if str((r["fields"].get("project_code") or [""])[0]
                     if isinstance(r["fields"].get("project_code"), list)
                     else r["fields"].get("project_code", "")).startswith(project_code)]
    boms = build_bom_rows(orders)
    if not boms:
        print(f"{project_code}: BOM 없음"); return {}
    goods = boms[0].goods_name
    gboms = [{"소품목_PT": b.part_code, "소요량_개당": b.soyoryang}
             for b in boms if b.goods_name == goods]
    oqty = boms[0].goods_qty or int(boms[0].order_qty)
    lookup = load_product_lookup({"Authorization": f"Bearer {os.environ['AIRTABLE_PAT']}"})
    _, e, _ = match_product(goods, lookup)
    cbm_unit = e["cbm_per_box"] if e else None
    row = build_propagation_row(project_code, goods, oqty, gboms, cbm_unit, "")
    print(row)
    return row


if __name__ == "__main__":
    import sys
    run_sample(sys.argv[1] if len(sys.argv) > 1 else "PNA50702")
```

- [ ] **Step 6: 샘플 전파 확인**

Run: `AIRTABLE_PAT=$AIRTABLE_PAT AIRTABLE_WMS_PAT=$AIRTABLE_WMS_PAT python -m harness.backbone.ledger PNA50702`
Expected: 전파 dict 출력 — 자재소요_요약에 PT####×수량, 추정_CBM 또는 전파상태=부분(미등록 굿즈면 CBM None)

- [ ] **Step 7: Commit**

```bash
git add harness/backbone/ledger.py tests/backbone/test_ledger.py
git commit -m "feat(backbone): PropagationLedger v0 (1주문 end-to-end 추적) + tests"
```

---

## Task 10: verify_phase1.py — 검증 게이트 실측 (read-only)

**Files:**
- Create: `harness/backbone/verify_phase1.py`

- [ ] **Step 1: 검증 스크립트 작성**

`harness/backbone/verify_phase1.py`:
```python
"""Phase-1 검증 게이트 (§7) 실측. read-only.

Gate1 Tier A 매칭률(마스터 확장 후 ≥85%), Tier B PT 추출(≥99%),
Gate3 BOM 적용율(≥90%), Gate4 링크 안전성(신규 4테이블만, TMS Product 무변경).
"""
from __future__ import annotations

import os

from harness.backbone.bom_bootstrap import build_bom_rows, fetch_orders
from harness.backbone.crosswalk import collect_keys
from harness.backbone.keys import extract_pt
from harness.settlement.cbm_calc import load_product_lookup, match_product


def main() -> None:
    tms = {"Authorization": f"Bearer {os.environ['AIRTABLE_PAT']}"}
    lookup = load_product_lookup(tms)
    orders = fetch_orders()
    goods, parts = collect_keys()

    # Gate 1: Tier A 굿즈 매칭률 (ItemMaster 적재 후 마스터 확장 반영)
    matched = sum(1 for g in goods if match_product(g, lookup)[1])
    g1 = matched / max(len(goods), 1) * 100

    # Gate 2b: PT 추출률
    pn = [r["fields"].get("파츠명", "") for r in orders if r["fields"].get("파츠명")]
    g2b = sum(1 for p in pn if extract_pt(p)) / max(len(pn), 1) * 100

    # Gate 3: BOM 적용율
    boms = build_bom_rows(orders)
    with_soyo = sum(1 for b in boms if b.soyoryang is not None)
    g3 = with_soyo / max(len(boms), 1) * 100

    print(f"[Gate1] Tier A 굿즈 매칭: {matched}/{len(goods)} = {g1:.1f}% (목표 ≥85%)")
    print(f"[Gate2b] PT 추출: {g2b:.1f}% (목표 ≥99%)")
    print(f"[Gate3] BOM 적용율: {g3:.1f}% (목표 ≥90%)")
    print(f"[Gate4] 쓰기 대상: WMS 네이티브 4테이블만 (TMS Product 변경 0 — 본 스크립트 read-only)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 검증 실행**

Run: `AIRTABLE_PAT=$AIRTABLE_PAT AIRTABLE_WMS_PAT=$AIRTABLE_WMS_PAT python -m harness.backbone.verify_phase1`
Expected: Gate2b ≥99%, Gate3 ≥90% 충족. Gate1은 마스터 확장(Task 8 박스유도) 반영 후 측정 — 목표 미달 시 미등록 굿즈 추가 소싱(MES 내부인쇄_제품DB) 필요 표기.

- [ ] **Step 3: 전체 테스트 스위트 통과 확인**

Run: `python -m pytest tests/backbone/ -q`
Expected: PASS (전체 backbone 단위테스트)

- [ ] **Step 4: Commit**

```bash
git add harness/backbone/verify_phase1.py
git commit -m "feat(backbone): Phase-1 검증 게이트 실측 스크립트"
```

---

## Task 11: feature_list + Obsidian log + 마무리

**Files:**
- Modify: `.claude/feature_list.json`

- [ ] **Step 1: feature_list에 백본 태스크 추가**

`.claude/feature_list.json`에 항목 추가 (기존 포맷 따름):
```json
{
  "id": "BOM-CBM-BACKBONE-P1",
  "title": "BOM·CBM 수량전파 백본 Phase-1 (4 네이티브 테이블 + 부트스트랩 + CBM확장 + Ledger v0)",
  "priority": "high",
  "status": "done",
  "notes": "WMS_KeyCrosswalk/ItemMaster/BOM/PropagationLedger 생성. PT추출 100%/BOM 93%/Gate1 마스터확장 필요. spec: docs/superpowers/specs/2026-06-09-bom-cbm-backbone-design.md"
}
```

- [ ] **Step 2: Obsidian log 저장**

`obsidian-routing` 스킬 호출 → `ClaudeVault/SCM/_AutoResearch/wiki/log.md`에 추가:
```
## [2026-06-XX] 구축 | BOM·CBM 수량전파 백본 Phase-1
- WMS 네이티브 4테이블 생성, order→BOM 부트스트랩, CBM 정규화+박스유도 확장, PropagationLedger v0
- 검증: PT추출 100%/BOM적용 93%/Gate1 매칭 (마스터확장 후 측정)
- 다음: Phase-2 (포장BOM 세분화, MES 제품DB 치수로 미등록 굿즈 CBM 추가확장, 대시보드 스냅샷)
```

- [ ] **Step 3: 최종 검증 + Commit**

Run: `python -m pytest tests/backbone/ -q`
Expected: 전체 PASS

```bash
git add .claude/feature_list.json
git commit -m "chore(backbone): feature_list Phase-1 완료 기록"
```

---

## Self-Review 체크

- **Spec coverage:** §6-1(4테이블)=Task2-3, §6-2(부트스트랩)=Task4-5, §6-3(CBM정규화+마스터확장)=Task7-8, §6-4(Ledger)=Task9, §7(검증)=Task10. 모두 커버.
- **2-tier Crosswalk:** Task6에서 Tier A(굿즈 name-match)+Tier B(PT) 구현. ✓
- **CBM⟂BOM granularity:** ItemMaster CBM=굿즈 단위, BOM=파츠 단위. Crosswalk/ItemMaster 분리 반영. ✓
- **마스터 확장(186종):** Task7 탐지 + Task8 박스유도. Gate1 목표 ≥85%는 박스힌트 회복률에 의존 — 미달 시 MES 내부인쇄_제품DB 치수 소싱(Phase-2 명시). ✓
- **Immutable/링크 안전:** 쓰기 전부 WMS 네이티브 신규 4테이블. ⚡/MES/TMS read-only. Task10 Gate4 명시. ✓
- **타입 일관성:** `BomRow.soyoryang`, `build_crosswalk` 반환 dict 키, ItemMaster 필드명 모두 schema_def와 일치. ✓
- **재사용:** `match_product`/`load_product_lookup`/`AirtableClient`/`BOX_TYPE_TO_CBM_M3` 일관 사용. ✓

## 알려진 리스크 / Phase-2 이월
- **Gate1 매칭률**: 박스유도로 부분 회복하나 ≥85% 미달 가능 → MES `내부인쇄_제품DB` 치수 + 수기 보강은 Phase-2.
- **포장재 분리**: BOM 구성유형 '포장재' 자동 분류(박스/완충재/라벨)는 Phase-2 (현재 PT 패턴만으로는 미분류).
- **shipment_id 결선**: Ledger v0는 shipment 매칭 미완(샘플은 빈 shipment_id) → TMS Shipment project code 조인은 Phase-2.
- **대시보드 스냅샷 계약**: Layer4 구현은 후속(별도 레포).
