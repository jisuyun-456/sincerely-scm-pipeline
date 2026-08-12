# 출하 CBM — 정산 파서 통일 + 매칭 정규화 재시도 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 정산 경로의 출하 CBM 산출 가능 라인을 **2,828건 → 약 12,100건**으로 올린다 (실측 기준 CBM-able 14.5% → 약 58%).

**Architecture:** 신규 로직을 쓰지 않는다. 이미 존재하고 테스트된 자산 2개를 연결한다 — ① 정산 경로가 구형 파서 `parse_product_lines`(수량 77% 유실)를 쓰고 있으므로 이미 있는 `parse_product_lines_v2`로 교체, ② 공유 리졸버 `resolve_product_entry`의 이름 Jaccard 폴백에 `crosswalk.py:17-19`가 이미 쓰는 `normalize_goods` 재시도를 이식. 파일 2개, 함수 2개만 수정하며 Airtable 쓰기는 없다.

**Tech Stack:** Python 3.14, pytest, requests, Airtable REST API (읽기 전용)

**Spec:** `docs/superpowers/specs/2026-08-11-shipment-cbm-parse-match-design.md`

## Global Constraints

- **Airtable 쓰기 금지.** 본 계획의 모든 변경은 순수 계산 로직이다. `create_records`/`patch_record`/`PATCH`/`POST` 호출을 추가하지 않는다.
- **🚨 main 병합 = 배포.** `calc_from_products`의 `unload_fee`는 `tms_settlement/calc.py:241-242` → `write.py:130` `patch_record` → `.github/workflows/tms_settlement.yml` cron(`0 9 * * *` = 매일 KST 18:00)으로 **기사님 상하차비에 자동 반영**된다. Task 3의 사용자 게이트를 통과하기 전에는 **main에 병합하지 않는다.** feature 브랜치가 안전 경계다.
- **`parse_product_lines_v2` 로직 수정 금지.** 이미 테스트된 자산(`tests/dispatch/test_cbm_estimator.py`)을 *연결*만 한다. 새 파싱 규칙 추가 금지.
- **v1 `parse_product_lines` 삭제 금지.** 외부 호출자가 있을 수 있으므로 남겨둔다.
- **배차 `estimate_shipment_cbm`은 건드리지 않는다.** 리졸버 교체 시 `wave_recommender.yml` cron(KST 09/14/17)이 자동배차 confidence 밴드를 바꾸며 PATCH한다 — 별도 spec/plan으로 분리했다(spec §4-C).
- **기존 테스트 무회귀.** 특히 `tests/settlement/test_calc_from_products_resolver.py::test_without_name2code_preserves_current_jaccard_miss`는 계속 green이어야 한다.
- **순환 import 주의.** `harness/dispatch/cbm_estimator.py`가 이미 `harness/settlement/cbm_calc.py`의 `match_product`를 import 중이다. 역방향 import는 **반드시 함수 내부 지연 import**로 한다.
- **테스트 컨벤션**: `tests/` 이하는 순수 단위 테스트다. conftest.py·fixture·monkeypatch·네트워크 접근 없이 평범한 inline dict로 Airtable 레코드 모양을 흉내낸다. 테스트가 만드는 lookup dict에는 **테스트가 직접 넣은 키만** 존재한다(`load_product_lookup`의 무공백 alias 자동생성은 일어나지 않음).
- **pytest 실행은 레포 루트에서**: `python -m pytest <path> -v`

---

### Task 1: `resolve_product_entry` 에 `normalize_goods` Jaccard 재시도 추가

먼저 리졸버부터 고친다. Task 2(파서 교체)가 이 개선된 리졸버를 그대로 활용하므로 순서가 중요하다.

**Files:**
- Modify: `harness/backbone/product_alias.py:131-170` (`resolve_product_entry`)
- Test: `tests/backbone/test_product_alias.py` (기존 파일 끝에 추가)

**Interfaces:**
- Consumes: `harness.backbone.keys.normalize_goods(name) -> str` (기존), `harness.settlement.cbm_calc.match_product(name, lookup) -> tuple[str, dict|None, float]` (기존). 둘 다 이미 함수 상단에 지연 import 되어 있다 — **import 추가 불필요**.
- Produces: `resolve_product_entry(name, code, name2code, lookup) -> tuple[dict|None, str|None, str]` — 시그니처 불변. `method` 반환값에 **`'jaccard_norm'` 한 가지만 추가**된다. 기존 값 `'code'`·`'name2code'`·`'jaccard'`·`'unmatched'`는 그대로.

> ⚠️ **2단(name2code)에는 재시도를 추가하지 않는다.** `product_alias.py:157`이 이미
> `c = name2code.get(normalize_goods(name))`로 *정규화한 키*를 조회하기 때문이다. 현행 코드에서
> `resolve_product_entry("데일리짐색(단품)", None, {"데일리짐색":"DLYG"}, lookup)`는 **이미**
> `('DLYG', 'name2code')`를 반환한다(실행 확인). 2단 재시도 블록은 동일 키·동일 가드의
> 도달 불가 死코드가 되므로 만들지 않는다.

- [ ] **Step 1: 기준 SHA 기록** (Task 3의 baseline 비교에 필요 — 지금 해야 정확하다)

```bash
git rev-parse HEAD > .git/cbm-baseline-sha && cat .git/cbm-baseline-sha
```

`.git/` 안에 두면 워킹트리를 더럽히지 않고 워크트리 생성에도 영향이 없다.

- [ ] **Step 2: 테스트 작성**

`tests/backbone/test_product_alias.py` 파일 끝에 추가:

```python
def _norm_lookup():
    """'데일리 짐색' 룩업 — '데일리짐색(단품)'은 정규화해야 해소된다.

    ⚠️ 무공백 alias 키('데일리짐색')를 **명시적으로** 넣어야 한다. 운영에서는
    load_product_lookup(cbm_calc.py:114-123)이 자동 생성하지만, 테스트는 dict를
    손으로 만들므로 자동 생성이 일어나지 않는다. 없으면 정규화 후에도
    Jaccard가 0.0(토큰 '데일리짐색' vs {'데일리','짐색'})이라 재시도가 실패한다.
    """
    e = {"rec_id": "r9", "name": "데일리 짐색", "code": "DLYG",
         "box_type": "대형", "qty_per_box": 101, "cbm_per_box": 0.1066}
    return {"데일리 짐색": e, "dlyg": e, "데일리짐색": e}


def test_normalize_retry_resolves_paren_suffix():
    # '(단품)' 접미 때문에 직접 Jaccard 실패 → normalize_goods로 괄호 제거 후 해소.
    from harness.backbone.product_alias import resolve_product_entry
    entry, code, method = resolve_product_entry(
        "데일리짐색(단품)", None, None, _norm_lookup())
    assert entry is not None
    assert code == "DLYG"
    assert method == "jaccard_norm"


def test_name2code_already_normalizes_so_no_retry_needed():
    # 회귀 가드: 2단이 name2code.get(normalize_goods(name))이므로 '(단품)'은 이미 해소된다.
    # 4단 재시도가 2단을 중복하지 않음을 고정한다.
    from harness.backbone.product_alias import resolve_product_entry
    entry, code, method = resolve_product_entry(
        "데일리짐색(단품)", None, {"데일리짐색": "DLYG"}, _norm_lookup())
    assert entry is not None
    assert code == "DLYG"
    assert method == "name2code"


def test_normalize_retry_not_used_when_direct_match_works():
    # 직접 매칭이 되면 재시도하지 않는다 — method는 기존 값 그대로.
    from harness.backbone.product_alias import resolve_product_entry
    entry, code, method = resolve_product_entry(
        "데일리 짐색", None, None, _norm_lookup())
    assert entry is not None
    assert method == "jaccard"


def test_normalize_retry_still_unmatched_returns_unmatched():
    # 정규화해도 못 찾으면 기존대로 unmatched.
    from harness.backbone.product_alias import resolve_product_entry
    entry, code, method = resolve_product_entry(
        "존재하지않는물건(단품)", None, None, _norm_lookup())
    assert entry is None
    assert code is None
    assert method == "unmatched"
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `python -m pytest tests/backbone/test_product_alias.py -v -k "normalize_retry or already_normalizes"`
Expected: **`1 failed, 3 passed`** — `test_normalize_retry_resolves_paren_suffix`만 `method == 'unmatched'`로 실패한다(재시도 로직 미구현). 나머지 3개는 기존 동작을 고정하는 회귀 가드이므로 처음부터 green이 정상이다.

- [ ] **Step 4: 최소 구현**

`harness/backbone/product_alias.py`의 `resolve_product_entry` 끝부분을 교체한다. 현재:

```python
    # 3) 이름 Jaccard 폴백 (현행 정산 동작)
    if name:
        _k, e, _score = match_product(name, lookup)
        if e is not None:
            return e, (str(e.get("code") or "").upper() or None), "jaccard"

    return None, None, "unmatched"
```

교체 후:

```python
    # 3) 이름 Jaccard 폴백 (현행 정산 동작)
    if name:
        _k, e, _score = match_product(name, lookup)
        if e is not None:
            return e, (str(e.get("code") or "").upper() or None), "jaccard"

    # 4) 정규화 재시도 — '(단품)'·'[2]'·'_재제작' 등 변형 접미 제거 후 3단(Jaccard)만 반복.
    #    2단(name2code)은 이미 normalize_goods 키로 조회하므로 재시도 대상이 아니다.
    #    crosswalk.build_crosswalk(:17-19)이 쓰는 검증된 패턴과 동일.
    if name:
        nm = normalize_goods(name)
        if nm and nm != name:
            _k, e, _score = match_product(nm, lookup)
            if e is not None:
                return e, (str(e.get("code") or "").upper() or None), "jaccard_norm"

    return None, None, "unmatched"
```

이어서 같은 함수의 docstring 두 곳을 갱신한다. 우선순위 목록에 4단을 추가:

```python
      4) 정규화 재시도                    — 변형 접미('(단품)'·'[2]'·'_재제작') 제거 후 3단 반복
```

`method` 설명 줄을 교체:

```python
      method: 'code' | 'name2code' | 'jaccard' | 'jaccard_norm' | 'unmatched'.
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest tests/backbone/test_product_alias.py -v`
Expected: 신규 4개 포함 전부 PASS.

- [ ] **Step 6: 무회귀 확인**

Run: `python -m pytest tests/backbone/ tests/settlement/ tests/dispatch/ -q`
Expected: 전부 PASS. 특히 `test_calc_from_products_resolver.py::test_without_name2code_preserves_current_jaccard_miss`가 green이어야 한다 — `normalize_goods("데스크테리어 매트")`는 괄호·대괄호·언더스코어가 없어 불변이므로 4단 재시도가 발동하지 않는다(`nm != name` 가드).

- [ ] **Step 7: 커밋**

```bash
git add harness/backbone/product_alias.py tests/backbone/test_product_alias.py
git commit -m "feat(cbm): resolve_product_entry 정규화 Jaccard 재시도 (변형 접미 해소)

crosswalk.py의 검증된 normalize_goods 재시도 패턴을 공유 리졸버 4단에 이식.
'데일리짐색(단품)'·'페이퍼샤쉐[2]'·'로고스트랩파우치(단품)_2차재제작' 류
변형 접미 굿즈명을 해소. method에 jaccard_norm 추가 — 해소 경로 관측 유지.

2단(name2code)은 이미 normalize_goods 키로 조회하므로 재시도 대상이 아니다
(회귀 가드 테스트로 고정)."
```

---

### Task 2: 정산 `calc_from_products` 를 v2 파서로 전환

**Files:**
- Modify: `harness/settlement/cbm_calc.py:208-273` (`calc_from_products`)
- Test: `tests/settlement/test_calc_from_products_resolver.py` (기존 파일 끝에 추가)

**Interfaces:**
- Consumes: `harness.dispatch.cbm_estimator.parse_product_lines_v2(text) -> list[tuple[str, int, int]]` — `(품목명, 총수량, 여분)`. 총수량은 본수량+여분. Task 1의 `resolve_product_entry`.
- Produces: `calc_from_products(product_text, lookup, qty_hint=0, name2code=None) -> dict` — 시그니처·반환 키(`unload_fee`·`total_cbm`·`matched`·`unmatched`) 불변. `matched[]` 원소에 `"extra"` 키가 **추가**된다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/settlement/test_calc_from_products_resolver.py` 파일 끝에 추가:

```python
def _box_lookup():
    # 무공백 키를 명시적으로 넣는다 — 테스트는 lookup을 손으로 만들므로
    # load_product_lookup의 alias 자동생성이 일어나지 않는다.
    e = {"name": "프라임 폴더블 멀티충전기", "code": "PFMC", "box_type": "대형",
         "qty_per_box": 10, "cbm_per_box": 0.1066, "rec_id": "r2"}
    return {"프라임 폴더블 멀티충전기": e, "pfmc": e, "프라임폴더블멀티충전기": e}


def test_bonus_qty_notation_counts_total():
    # '50+1' = 본 50 + 여분 1 = 51 → ceil(51/10) = 6박스. v1 파서는 수량을 통째로 유실했다.
    out = calc_from_products("프라임폴더블멀티충전기 50+1", _box_lookup())
    assert out["matched"], "보너스 수량 표기가 매칭을 깨뜨리면 안 된다"
    m = out["matched"][0]
    assert m["qty"] == 51
    assert m["extra"] == 1
    assert m["n_boxes"] == 6


def test_bracket_index_stripped_from_name():
    # '[1]' 인덱스 표기가 붙어도 매칭돼야 한다 (v2가 이름에서 제거).
    out = calc_from_products("프라임폴더블멀티충전기[1] 20", _box_lookup())
    assert out["matched"]
    assert out["matched"][0]["qty"] == 20
    assert out["matched"][0]["n_boxes"] == 2


def test_qty_hint_still_applies_when_no_qty_parsed():
    # 수량이 전혀 없는 텍스트에서는 기존 qty_hint 폴백이 그대로 동작해야 한다.
    out = calc_from_products("프라임폴더블멀티충전기", _box_lookup(), qty_hint=30)
    assert out["matched"]
    assert out["matched"][0]["qty"] == 30
    assert out["matched"][0]["n_boxes"] == 3
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/settlement/test_calc_from_products_resolver.py -v -k "bonus_qty or bracket_index"`
Expected: FAIL — `test_bonus_qty_notation_counts_total`이 `out["matched"]`가 비어 실패한다 (v1이 `"프라임폴더블멀티충전기 50+1"`을 통째로 품목명 취급 → 매칭 실패).

- [ ] **Step 3: 최소 구현**

`harness/settlement/cbm_calc.py`의 `calc_from_products` 본문 앞부분을 수정한다. 현재:

```python
    from harness.backbone.product_alias import resolve_product_entry

    lines = parse_product_lines(product_text)
    if not lines:
        return {"unload_fee": 0, "total_cbm": 0.0, "matched": [], "unmatched": []}

    if qty_hint > 0 and all(q == 0 for _, q in lines):
        lines = [(p, qty_hint if i == 0 else 0) for i, (p, _) in enumerate(lines)]
```

교체 후 (`cbm_estimator`는 지연 import — 모듈 최상위로 올리면 순환 import 발생):

```python
    from harness.backbone.product_alias import resolve_product_entry
    from harness.dispatch.cbm_estimator import parse_product_lines_v2

    # v2 파서: 보너스 수량('100+1')·'[N]' 인덱스·천단위 콤마·무공백 수량을 처리한다.
    # v1은 '100+1'에서 수량을 유실해 n_boxes=1로 CBM을 과소계상했다(실측 5,583 라인).
    lines = parse_product_lines_v2(product_text)
    if not lines:
        return {"unload_fee": 0, "total_cbm": 0.0, "matched": [], "unmatched": []}

    if qty_hint > 0 and all(q == 0 for _, q, _x in lines):
        lines = [(p, qty_hint if i == 0 else 0, x)
                 for i, (p, _q, x) in enumerate(lines)]
```

이어서 루프 헤더를 3-tuple 대응으로 바꾼다. 현재:

```python
    for prod_name, qty in lines:
```

교체 후:

```python
    for prod_name, qty, extra in lines:
```

그리고 `matched_list.append({...})` 딕셔너리의 `"qty": qty,` 바로 뒤에 한 줄 추가:

```python
            "extra":       extra,
```

마지막으로 `calc_from_products` docstring 본문에 파서 언급 한 줄을 추가한다 (첫 요약줄 아래):

```python
    파싱은 parse_product_lines_v2 (보너스 수량 '100+1' · '[N]' 인덱스 · 천단위 콤마 처리).
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/settlement/ -v`
Expected: 신규 3개 포함 전부 PASS.

- [ ] **Step 5: 순환 import 스모크 확인**

Run: `python -m pytest tests/test_import_smoke.py -v && python -c "from harness.settlement.cbm_calc import calc_from_products; print(calc_from_products('티셔츠 100+2', {}))"`
Expected: import 에러 없이 PASS, 두 번째 명령이 `{'unload_fee': 0, 'total_cbm': 0.0, 'matched': [], 'unmatched': ['티셔츠']}` 출력 (빈 lookup이므로 unmatched가 정상).

- [ ] **Step 6: 전체 무회귀**

Run: `python -m pytest tests/ -q`
Expected: 전부 PASS.

- [ ] **Step 7: 커밋**

```bash
git add harness/settlement/cbm_calc.py tests/settlement/test_calc_from_products_resolver.py
git commit -m "fix(cbm): 정산 파서를 parse_product_lines_v2로 통일

v1 파서의 수량 정규식이 한국식 보너스 표기 '100+1'을 못 잡아
수량 0(→n_boxes=1)으로 CBM을 과소계상하고 품목명에 ' 100+1'이 남아
매칭까지 동시 실패했다. 실측 5,583 라인 영향.

이미 테스트된 dispatch의 v2 파서를 연결만 한다(로직 신규 작성 없음).
순환 import 회피를 위해 함수 내부 지연 import.

⚠️ unload_fee 변경 → tms_settlement cron(KST 18:00)이 기사님 상하차비로
자동 PATCH. Task 3 게이트 통과 전 main 병합 금지."
```

---

### Task 3: 전수 재측정 + 정산 금액 delta 리포트 + 사용자 게이트

Spec §6·§7이 요구하는 **금액 영향 검증**. 이 태스크의 게이트를 통과하기 전에는 main에 병합하지 않는다.

**Files:**
- Create: `scripts/settlement/measure_cbm_coverage.py` (디렉터리 신규)
- Test: 없음 (측정 스크립트 — 읽기 전용, 산출물이 곧 검증 증거)

**Interfaces:**
- Consumes: `calc_from_products` (Task 2 후), `match_product`·`load_product_lookup` (`cbm_calc`), `harness.tms_settlement.fetch.load_name2code(wms_pat) -> dict`, `harness.backbone.keys.is_service`
- Produces: stdout 리포트 + `outputs/cbm-coverage-<날짜>.json` (**gitignored — 커밋하지 않는다**)

- [ ] **Step 1: 측정 스크립트 작성**

```bash
mkdir -p scripts/settlement
```

`scripts/settlement/measure_cbm_coverage.py` 생성:

```python
"""출하 CBM 커버리지 전수 측정 + 정산 금액 delta 리포트 (읽기 전용).

Spec: docs/superpowers/specs/2026-08-11-shipment-cbm-parse-match-design.md §7

실행: python scripts/settlement/measure_cbm_coverage.py
필요 env: AIRTABLE_PAT (TMS), AIRTABLE_WMS_PAT (sync_item name2code)
"""
from __future__ import annotations

import collections
import json
import os
import sys
from datetime import date

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
load_dotenv()

from harness.backbone.keys import is_service
from harness.settlement.cbm_calc import (calc_from_products, load_product_lookup,
                                         match_product)
from harness.tms_settlement.fetch import load_name2code

TMS_BASE = "app4x70a8mOrIKsMf"
TBL_SHIP = "tbllg1JoHclGYer7m"
FLD_OUT = "fldgSupj5XLjJXYQo"    # 최종 출하 품목
FLD_POST = "fldXXnGOXkm90snKn"   # 최종 출고 품목 및 수량
FLD_SC = "fldBUwhBlhOMsJZdv"     # SC ID


def fetch_shipments(headers: dict) -> list[dict]:
    url = f"https://api.airtable.com/v0/{TMS_BASE}/{TBL_SHIP}"
    out: list[dict] = []
    cursor = None
    while True:
        params = {"pageSize": 100, "returnFieldsByFieldId": "true",
                  "fields[]": [FLD_OUT, FLD_POST, FLD_SC]}
        if cursor:
            params["offset"] = cursor
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        d = r.json()
        out.extend(d.get("records", []))
        cursor = d.get("offset")
        if not cursor:
            return out


def main() -> None:
    tp = os.environ["AIRTABLE_PAT"]
    headers = {"Authorization": f"Bearer {tp}"}
    lookup = load_product_lookup(headers)
    name2code = load_name2code(os.environ.get("AIRTABLE_WMS_PAT"))
    recs = fetch_shipments(headers)
    print(f"shipments: {len(recs)} / product lookup: {len(lookup)} / "
          f"name2code: {len(name2code)}")

    # method='jaccard'는 exact 히트(score 1.0)에도 붙는다(cbm_calc.py:153-157의 정확·무공백
    # alias 경로). matched[]에는 score가 없으므로 위험 구간(0.4~0.5)을 보려면 재계산해야
    # 한다. 동일 굿즈명이 수천 건 반복되므로 이름 단위로 캐시한다.
    score_cache: dict[str, float] = {}

    def name_score(nm: str) -> float:
        if nm not in score_cache:
            _k, e, s = match_product(nm, lookup)
            if e is None:      # jaccard_norm 경로 — 정규화한 이름으로 재계산
                from harness.backbone.keys import normalize_goods
                _k, e, s = match_product(normalize_goods(nm), lookup)
            score_cache[nm] = s if e is not None else 0.0
        return score_cache[nm]

    lines = matched = cbm_able = 0
    by_method: collections.Counter = collections.Counter()
    score_hist: collections.Counter = collections.Counter()
    fuzzy: list[dict] = []
    per_ship: list[dict] = []

    for rec in recs:
        f = rec["fields"]
        text = f.get(FLD_POST) or f.get(FLD_OUT) or ""
        if not text:
            continue
        out = calc_from_products(str(text), lookup, name2code=name2code)
        for m in out["matched"]:
            if is_service(m["name"]):
                continue
            lines += 1
            matched += 1
            by_method[m.get("method", "?")] += 1
            if m["qty"] > 0 and m["cbm_per_box"] > 0:
                cbm_able += 1
            if m.get("method") in ("jaccard", "jaccard_norm"):
                sc = name_score(m["name"])
                score_hist[f"{int(sc * 10) / 10:.1f}"] += 1
                if sc < 1.0:          # exact 히트는 위험 구간이 아니다
                    fuzzy.append({"name": m["name"], "key": m["matched_key"],
                                  "method": m["method"], "score": round(sc, 3),
                                  "qty": m["qty"]})
        for u in out["unmatched"]:
            if not is_service(u):
                lines += 1
        per_ship.append({
            "sc": f.get(FLD_SC), "total_cbm": out["total_cbm"],
            "unload_fee": out["unload_fee"],
            "n_matched": len(out["matched"]),
            "n_unmatched": len(out["unmatched"]),
        })

    print(f"\n=== coverage ===")
    print(f"  분모(파싱된 비서비스 라인) : {lines}")
    print(f"  matched                    : {matched} = {matched / max(lines, 1) * 100:.1f}%")
    print(f"  CBM-able (주 지표, 절대건수): {cbm_able} = "
          f"{cbm_able / max(lines, 1) * 100:.1f}%")
    print(f"  ※ 분모는 파서에 따라 달라진다(v1 19,547 / v2 19,709). % 가 아니라")
    print(f"    CBM-able 절대건수를 baseline 과 비교한다 (기준선 2,828 → 목표 ~12,100).")

    print(f"\n=== 해소 경로 분포 ===")
    for k, v in by_method.most_common():
        print(f"  {k:<16} {v}")

    print(f"\n=== 이름매칭 score 분포 (jaccard 계열) ===")
    for k in sorted(score_hist):
        print(f"  {k}~ : {score_hist[k]}")

    tot_fee = sum(p["unload_fee"] for p in per_ship)
    tot_cbm = sum(p["total_cbm"] for p in per_ship)
    print(f"\n=== 정산 총계 ===")
    print(f"  상하차비 합계 : {tot_fee:,}원")
    print(f"  CBM 합계      : {tot_cbm:,.2f} m3")

    top = sorted(per_ship, key=lambda p: p["unload_fee"], reverse=True)[:20]
    print(f"\n=== 상하차비 상위 20건 (표본 확인용) ===")
    for p in top:
        print(f"  {p['sc']}: {p['unload_fee']:,}원 / {p['total_cbm']:.3f} m3 "
              f"(매칭 {p['n_matched']} 미매칭 {p['n_unmatched']})")

    fuzzy.sort(key=lambda x: x["score"])
    print(f"\n=== 위험 구간 매칭 표본 (score<1.0, 낮은 순 20건 — 오매칭 육안 확인) ===")
    for s in fuzzy[:20]:
        print(f"  [{s['method']} {s['score']}] {s['name']!r} -> {s['key']} x{s['qty']}")

    os.makedirs("outputs", exist_ok=True)
    dest = f"outputs/cbm-coverage-{date.today().isoformat()}.json"
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump({"lines": lines, "matched": matched, "cbm_able": cbm_able,
                   "by_method": dict(by_method), "score_hist": dict(score_hist),
                   "total_unload_fee": tot_fee, "total_cbm": round(tot_cbm, 3),
                   "fuzzy_samples": fuzzy[:100], "per_shipment": per_ship},
                  fh, ensure_ascii=False, indent=2)
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 변경 후 측정 실행**

Run: `python scripts/settlement/measure_cbm_coverage.py`
Expected: `CBM-able` 절대건수가 **12,000 근방** (라이브 데이터 드리프트로 ±5% 허용). 3,000 근방이면 Task 2가 반영되지 않은 것이므로 중단하고 원인을 찾는다.

- [ ] **Step 3: 변경 전 기준선 측정**

변경 전 코드로 같은 스크립트를 돌려 대조군을 만든다. 워크트리를 레포 내부 `.worktrees/`에 만들면 `load_dotenv()`의 상향 탐색이 `SCM_WORK/.env`를 그대로 찾으므로 **PAT 복사가 불필요**하다(`.worktrees/`는 `.gitignore`에 이미 있다).

```bash
BASE=$(cat .git/cbm-baseline-sha)
git worktree add .worktrees/scm-baseline "$BASE"

# 기준 SHA 에는 scripts/settlement/ 가 없다 (이 계획이 처음 만드는 디렉터리) — 먼저 생성 후 복사
mkdir -p .worktrees/scm-baseline/scripts/settlement
cp scripts/settlement/measure_cbm_coverage.py .worktrees/scm-baseline/scripts/settlement/

(cd .worktrees/scm-baseline && python scripts/settlement/measure_cbm_coverage.py)

# 산출물은 워크트리 안에 쓰인다 — remove 전에 꺼낸다
mkdir -p outputs
cp .worktrees/scm-baseline/outputs/cbm-coverage-*.json \
   "outputs/cbm-coverage-$(date +%F)-baseline.json"

# 복사한 미추적 스크립트가 있으므로 --force 필요
git worktree remove --force .worktrees/scm-baseline
```

Expected: baseline 쪽 `CBM-able` 절대건수가 **2,800 근방**. 두 JSON의 `total_unload_fee`·`total_cbm` 차이가 곧 금액 영향이다.

- [ ] **Step 4: 커밋**

`outputs/`는 `.gitignore:30`으로 제외돼 있고, `per_shipment`에 SC·상하차비가 담기므로 **커밋하지 않는다**(`-f`도 쓰지 않는다).

```bash
git add scripts/settlement/measure_cbm_coverage.py
git commit -m "test(cbm): 출하 CBM 커버리지 전수 측정 + 정산 금액 delta 리포트

Spec §7 검증 산출물. 읽기 전용(Airtable 쓰기 없음).
변경 전/후 두 번 실행해 상하차비·CBM 합계 delta를 대조한다.
측정 JSON 은 outputs/(gitignored) 에만 남긴다 — 정산 금액 성격."
```

- [ ] **Step 5: 사용자 확인 요청 (게이트 — 자동 진행·병합 금지)**

다음을 사용자에게 보고하고 **명시적 승인 전까지 main 병합을 진행하지 않는다.** cron은 main에서 돌므로 병합이 곧 배포다.

1. CBM-able 절대건수: baseline → 변경 후 (기준선 ~2,828 → 목표 ~12,100)
2. 상하차비 합계: baseline → 변경 후, **차액**
3. 상하차비 상위 20건 표본
4. score<1.0 위험구간 매칭 20건 표본 — 오매칭 여부 육안 확인
   (특히 `Solid스탠다드G형박스(...)` → `Solid 커스텀 G형박스(...)` 류 score 0.4 경계 매칭)
5. score 분포 히스토그램 — 0.4~0.5 구간 건수

---

## 후속 과제 (본 계획 범위 밖)

- **배차 `estimate_shipment_cbm` 리졸버 전환** (+4.0pp, 57.5%→61.5%) — `wave_recommender.yml` cron(KST 09/14/17)이 `estimated_cbm`·`estimation_confidence`를 자동 PATCH하고 `fuzzy_write_decision`의 0.7/0.8 게이트가 자동배차를 좌우하므로, confidence-band delta 계측과 별도 사용자 게이트가 필요하다. 별도 spec/plan으로 진행.
- **잔여 hard-unmatched 해소** — `프리미엄스트링후드집업(F`(93건, `/` 분할로 괄호 절단), `잔여분(...)`, `펜1`, `쇼핑백` 등. Product 마스터 부재 또는 원천 텍스트 품질 문제로 분류 필요.
- **chain P2** — Product 마스터 정리(FGPS 코드재사용·dup/junk).

---

## 자체 검토 결과 (Self-Review)

**Spec 커버리지 확인:**

| Spec 항목 | 담당 |
|---|---|
| §4-A 정산 파서 v2 전환 + 지연 import | Task 2 |
| §4-B `resolve_product_entry` 정규화 Jaccard 재시도 + `jaccard_norm` | Task 1 |
| §4-C 배차 리졸버 전환 | **의도적 제외** — 후속 과제 섹션에 근거와 함께 기록 |
| §6 정산 금액 자동 PATCH 리스크 | Global Constraints + Task 2 Step 7 커밋 메시지 + Task 3 Step 5 게이트 |
| §6 Jaccard 오매칭 리스크 (score 분포 + 0.4~0.5 표본) | Task 3 Step 1 `name_score`·`score_hist`·`fuzzy`, Step 5 항목 4·5 |
| §6 순환 import | Task 2 Step 5 |
| §6 분모 이동 | Task 3 Step 1 출력 문구 + Step 2·3 절대건수 게이트 |
| §7-1 단위 테스트 (TDD) | Task 1 Step 2·4, Task 2 Step 1·3 |
| §7-2 기존 테스트 무회귀 | Task 1 Step 6, Task 2 Step 6 |
| §7-3 전수 재측정 | Task 3 Step 2·3 |
| §7-4 금액 delta + 표본 확인 | Task 3 Step 3·5 |
| §8 롤백 (git revert) | Airtable 쓰기 없음 — Global Constraints |

**타입 일관성:** `parse_product_lines_v2`는 3-tuple `(name, total_qty, extra)`을 반환하며 Task 2의 언패킹(`for prod_name, qty, extra in lines`)과 `qty_hint` 폴백(`(p, qty_hint if i == 0 else 0, x)`)이 모두 3-tuple로 일치한다. `resolve_product_entry`는 Task 1 전후 모두 3-tuple `(entry, code, method)`이며 기존 호출자(`calc_from_products`의 `entry, key, _method`)와 호환된다. Task 1이 추가하는 `method` 값은 `'jaccard_norm'` 하나뿐이며, Task 3 스크립트의 `("jaccard", "jaccard_norm")` 필터에서 동일 문자열로 참조된다. `name2code_norm`은 도달 불가여서 **어디에도 등장하지 않는다**.

**적용된 레드팀 지적:** ① `name2code_norm` 도달 불가 → 제거하고 회귀 가드 테스트로 대체 ② 배차 리졸버 전환이 cron 자동 PATCH·자동배차 밴드를 바꿈 → 본 계획에서 분리 ③ `method='jaccard'`가 exact 히트에도 붙어 위험구간 표본이 불가능 → 측정 스크립트에서 score 재계산(이름 캐시) ④ 워크트리 baseline 실패(디렉터리 부재·`.env` 부재·산출물 소실) → 레포 내부 `.worktrees/` + `mkdir -p` + 산출물 선반출 + `--force` ⑤ `git add outputs/` 실패(gitignored) → 커밋 대상에서 제외 ⑥ 분모 이동으로 % 게이트 재현 불가 → 절대건수 게이트.
