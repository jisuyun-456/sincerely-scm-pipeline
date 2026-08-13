# 굿즈↔견적코드 결정론 크로스워크 P1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal (북극성):** **에이원·다영 출하 `CBM_유효` 완결율**을 올린다 — 분모=텍스트보유 출하 기준 다영 27.5% → ≥79%(필수)/~93%(목표), 에이원 28.3% → ≥83%(필수)/~91%(목표). 수단은 ① 결정론 크로스워크(1.5단) 구축·채우기와 ② **과거분 `estimated_cbm` 백필**이다. 단순 fuzzy→deterministic parity는 목표가 아니다.

⚠️ **두 기여를 분리해 읽을 것**: 백필 6,079건이 지배적 레버이고 브릿지 순증은 860건(약 1/7)이다. 그리고 `jaccard_norm` 760건은 이미 매칭되던 라인의 **결정론 전환이라 커버리지 중립**이다 — 커버리지 순증은 오직 현재 미매칭(<0.5 93건 + 미해소)을 확정행으로 등재하는 데서 나온다.

**Architecture:** 신규 파일 2개(로더 모듈, 후보 생성 스크립트) + 기존 리졸버에 1.5단 삽입. 크로스워크는 `data/crosswalk/goods_crosswalk.csv`(git 추적)를 SSOT로 하고 런타임에 캐시 로드한다. 파일이 없으면 로더가 빈 맵을 반환해 1.5단이 자동 무력화되므로 기존 1~4단 동작이 그대로 보존된다.

**Tech Stack:** Python 3.14, pytest, csv(표준 라이브러리), requests(후보 생성 시 읽기 전용)

**Spec:** `docs/superpowers/specs/2026-08-12-bridge-cbm-crosswalk-design.md`

## Global Constraints

- **Airtable 쓰기 절대 금지.** 본 계획은 git 파일 SSOT다. `create_records`/`patch_record`/`PATCH`/`POST` 추가 금지. 후보 생성 스크립트도 GET만 한다.
- **크로스워크에 CBM 값 저장 금지.** 신원(견적코드) 매핑만. Product가 CBM SSOT다.
- **P1은 `키유형=굿즈명` 행만 소비한다.** `코드`·`파츠` 행은 스키마에만 존재하고 로더가 필터로 제외한다.
- **`product_alias`의 ALIAS/SIZE_FAMILY/SYNTHETIC 딕셔너리를 건드리지 않는다.** 이관은 P2. `resolve_registered_code`는 `order_cascade` cron과 공유되므로 P1에서 변경 금지.
- **생성 스크립트는 기존 행을 절대 수정/삭제하지 않는다 (파일 수준 INSERT-only).** 신규 `표준키`만 append. 사람이 `미검증→확정`으로 바꾼 판정을 재실행이 되돌리면 거버넌스가 무너진다.
- **`검증상태=확정` 행만 결정론에 쓴다.** `미검증`·`보류`는 로더가 결정론 맵에 넣지 않는다.
- **정산 금액에 영향이 있다.** 1.5단이 기존 퍼지 결과를 다른 코드로 바꾸면 CBM·상하차비가 변하고, `tms_settlement.yml` cron(매일 KST 18:00)이 자동 PATCH한다. Task 5의 사용자 게이트 통과 전 main 병합 금지.
- **테스트 컨벤션**: `tests/` 이하는 순수 단위 테스트다. conftest.py·fixture·monkeypatch·네트워크 없이 평범한 inline dict/파일로 구성한다. 임시 CSV가 필요하면 pytest `tmp_path`를 쓴다(이 저장소에 선례는 없지만 표준 라이브러리 범위이며 네트워크·전역상태를 쓰지 않는다).
- **pytest는 레포 루트에서**: `python -m pytest <path> -v`

---

### Task 1: 크로스워크 로더 (`crosswalk_store.py`)

순수 함수 모듈부터 만든다. 리졸버 연결(Task 2)이 이 모듈에 의존한다.

**Files:**
- Create: `harness/backbone/crosswalk_store.py`
- Create: `tests/backbone/test_crosswalk_store.py`

**Interfaces:**
- Consumes: `harness.backbone.keys.normalize_goods(name) -> str` (기존)
- Produces:
  - `CROSSWALK_PATH: str` — 기본 경로 상수 `data/crosswalk/goods_crosswalk.csv` (리포 루트 기준)
  - `class CrosswalkConflictError(Exception)`
  - `crosswalk_key(raw: str) -> str` — `normalize_goods` → `strip` → `casefold`
  - `load_crosswalk(path: str | None = None, *, _cache: bool = True) -> dict[str, str]` — 정규화키 → 견적코드(upper). `확정 ∧ 굿즈명` 행만. 파일 없으면 `{}`.
  - `clear_cache() -> None` — 테스트용 캐시 무효화

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/backbone/test_crosswalk_store.py`:

```python
"""크로스워크 로더 — git-SSOT 결정론 계층 (spec §4.2·§4.3)."""
import pytest

from harness.backbone.crosswalk_store import (
    CrosswalkConflictError,
    clear_cache,
    crosswalk_key,
    load_crosswalk,
)

HEADER = "표준키,키유형,TMS_견적코드,매칭방식,매칭신뢰도,검증상태,근거\n"


def _write(tmp_path, rows):
    p = tmp_path / "goods_crosswalk.csv"
    p.write_text(HEADER + "".join(rows), encoding="utf-8")
    return str(p)


def test_key_normalizes_variants_to_same_key():
    # '(단품)'·'[2]'·'_재제작' 접미는 normalize_goods가 제거 → 같은 키
    assert crosswalk_key("데일리짐색(단품)") == crosswalk_key("데일리짐색")
    assert crosswalk_key("페이퍼샤쉐[2]") == crosswalk_key("페이퍼샤쉐")


def test_loads_only_confirmed_goods_rows(tmp_path):
    path = _write(tmp_path, [
        "데일리짐색(단품),굿즈명,DLYG,정확,1.0,확정,seed\n",
        "미검증굿즈,굿즈명,XXXX,유사,0.6,미검증,seed\n",
        "보류굿즈,굿즈명,YYYY,유사,0.3,보류,seed\n",
        "LOPU,코드,LSPO,정확,1.0,확정,alias\n",
    ])
    clear_cache()
    m = load_crosswalk(path, _cache=False)
    assert m == {crosswalk_key("데일리짐색(단품)"): "DLYG"}


def test_missing_file_returns_empty(tmp_path):
    clear_cache()
    assert load_crosswalk(str(tmp_path / "nope.csv"), _cache=False) == {}


def test_conflicting_confirmed_rows_raise(tmp_path):
    # 같은 정규화 키인데 견적코드가 다른 확정 행 2개 → 조용한 last-wins 금지
    path = _write(tmp_path, [
        "데일리짐색(단품),굿즈명,DLYG,정확,1.0,확정,seed\n",
        "데일리짐색(키트),굿즈명,ZZZZ,정확,1.0,확정,seed\n",
    ])
    clear_cache()
    with pytest.raises(CrosswalkConflictError) as exc:
        load_crosswalk(path, _cache=False)
    assert "데일리짐색" in str(exc.value)


def test_same_key_same_code_is_not_conflict(tmp_path):
    # 변형 2개가 같은 코드를 가리키는 것은 정상 (충돌 아님)
    path = _write(tmp_path, [
        "데일리짐색(단품),굿즈명,DLYG,정확,1.0,확정,seed\n",
        "데일리짐색(키트),굿즈명,DLYG,정확,1.0,확정,seed\n",
    ])
    clear_cache()
    assert load_crosswalk(path, _cache=False) == {crosswalk_key("데일리짐색"): "DLYG"}


def test_blank_fields_skipped(tmp_path):
    path = _write(tmp_path, [
        ",굿즈명,DLYG,정확,1.0,확정,빈표준키\n",
        "빈코드굿즈,굿즈명,,정확,1.0,확정,빈코드\n",
        "정상굿즈,굿즈명,GOOD,정확,1.0,확정,ok\n",
    ])
    clear_cache()
    assert load_crosswalk(path, _cache=False) == {crosswalk_key("정상굿즈"): "GOOD"}


def test_code_is_uppercased(tmp_path):
    path = _write(tmp_path, ["정상굿즈,굿즈명,dlyg,정확,1.0,확정,ok\n"])
    clear_cache()
    assert load_crosswalk(path, _cache=False) == {crosswalk_key("정상굿즈"): "DLYG"}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/backbone/test_crosswalk_store.py -v`
Expected: 전부 FAIL — `ModuleNotFoundError: No module named 'harness.backbone.crosswalk_store'`.

- [ ] **Step 3: 최소 구현**

`harness/backbone/crosswalk_store.py`:

```python
"""굿즈명↔견적코드 결정론 크로스워크 로더 (git-SSOT).

spec: docs/superpowers/specs/2026-08-12-bridge-cbm-crosswalk-design.md §4.2~4.3

SSOT = data/crosswalk/goods_crosswalk.csv (git 추적). 크로스워크는 **신원 매핑만**
보유하며 CBM 값을 저장하지 않는다 — CBM SSOT는 TMS Product다.

검증상태='확정' ∧ 키유형='굿즈명' 행만 결정론 맵에 적재한다. 같은 정규화 키에
서로 다른 견적코드를 가진 확정 행이 있으면 조용히 last-wins 하지 않고 loud 실패한다.
"""
from __future__ import annotations

import csv
import os

from harness.backbone.keys import normalize_goods

# 리포 루트 기준 기본 경로 (harness/backbone/ 에서 두 단계 위)
CROSSWALK_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "crosswalk", "goods_crosswalk.csv",
)

STATUS_CONFIRMED = "확정"
KEYTYPE_GOODS = "굿즈명"

_cache_store: dict[str, dict[str, str]] = {}


class CrosswalkConflictError(Exception):
    """같은 정규화 키에 서로 다른 견적코드를 가진 확정 행이 둘 이상."""


def crosswalk_key(raw: str) -> str:
    """조회 키 정규화 — normalize_goods 후 공백 제거·casefold."""
    return normalize_goods(raw or "").strip().casefold()


def clear_cache() -> None:
    _cache_store.clear()


def load_crosswalk(path: str | None = None, *, _cache: bool = True) -> dict[str, str]:
    """정규화키 → 견적코드(upper). 확정·굿즈명 행만. 파일 없으면 {}.

    파일 부재를 정상으로 취급하는 것은 의도적이다 — 크로스워크 미배포 환경에서
    1.5단이 자동 무력화되고 기존 1~4단 동작이 그대로 유지된다(spec §4.3, §10).
    """
    p = path or CROSSWALK_PATH
    if _cache and p in _cache_store:
        return _cache_store[p]

    out: dict[str, str] = {}
    if os.path.exists(p):
        with open(p, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                if (row.get("검증상태") or "").strip() != STATUS_CONFIRMED:
                    continue
                if (row.get("키유형") or "").strip() != KEYTYPE_GOODS:
                    continue
                raw = (row.get("표준키") or "").strip()
                code = (row.get("TMS_견적코드") or "").strip().upper()
                if not raw or not code:
                    continue
                key = crosswalk_key(raw)
                if not key:
                    continue
                prev = out.get(key)
                if prev is not None and prev != code:
                    raise CrosswalkConflictError(
                        f"크로스워크 충돌: 정규화키 {key!r} 가 {prev!r} 와 {code!r} 둘 다 가리킴 "
                        f"(표준키 {raw!r}). 확정 행 중 하나를 정정하거나 보류로 내려야 한다."
                    )
                out[key] = code

    if _cache:
        _cache_store[p] = out
    return out
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/backbone/test_crosswalk_store.py -v`
Expected: 7개 전부 PASS.

- [ ] **Step 5: 커밋**

```bash
git add harness/backbone/crosswalk_store.py tests/backbone/test_crosswalk_store.py
git commit -m "feat(crosswalk): git-SSOT 크로스워크 로더 + 충돌 검출

확정·굿즈명 행만 결정론 맵에 적재. 같은 정규화 키에 다른 견적코드를 가진
확정 행이 있으면 CrosswalkConflictError 로 loud 실패 — 조용한 last-wins 금지.
파일 부재는 정상({}) → 1.5단 자동 무력화로 기존 동작 보존."
```

---

### Task 2: 리졸버 1.5단 삽입

**Files:**
- Modify: `harness/backbone/product_alias.py` (`resolve_product_entry`, 1단 직후)
- Test: `tests/backbone/test_product_alias.py` (기존 파일 끝에 추가)

**Interfaces:**
- Consumes: Task 1의 `load_crosswalk`, `crosswalk_key`
- Produces: `resolve_product_entry(...)` 시그니처 불변. `method`에 `'crosswalk'` **한 가지 추가**. 기존 5종(`code`·`name2code`·`jaccard`·`jaccard_norm`·`unmatched`) 불변.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/backbone/test_product_alias.py` 끝에 추가:

```python
# ── 1.5단 크로스워크 결정론 계층 (spec §4.1) ──────────────────────────────
def _cw_lookup():
    e = {"rec_id": "rC", "name": "로고스트랩 파우치", "code": "LSPO",
         "box_type": "대형", "qty_per_box": 100, "cbm_per_box": 0.1066}
    other = {"rec_id": "rD", "name": "다른 굿즈", "code": "OTHR",
             "box_type": "중형", "qty_per_box": 50, "cbm_per_box": 0.0201}
    return {"로고스트랩 파우치": e, "lspo": e, "다른 굿즈": other, "othr": other}


def test_crosswalk_stage_resolves_before_name2code(monkeypatch):
    # 크로스워크 확정행이 sync_item(name2code)보다 우선 — 사람 판정 우선
    import harness.backbone.product_alias as pa
    from harness.backbone.crosswalk_store import crosswalk_key
    monkeypatch.setattr(pa, "load_crosswalk",
                        lambda: {crosswalk_key("로고스트랩파우치(단품)"): "LSPO"})
    entry, code, method = pa.resolve_product_entry(
        "로고스트랩파우치(단품)", None, {"로고스트랩파우치": "OTHR"}, _cw_lookup())
    assert code == "LSPO"
    assert method == "crosswalk"


def test_crosswalk_miss_falls_through_to_existing_stages(monkeypatch):
    import harness.backbone.product_alias as pa
    monkeypatch.setattr(pa, "load_crosswalk", lambda: {})
    entry, code, method = pa.resolve_product_entry(
        "로고스트랩 파우치", None, None, _cw_lookup())
    assert entry is not None
    assert method == "jaccard"


def test_crosswalk_pointing_at_cbmless_product_falls_through(monkeypatch):
    # 확정행이 CBM 0 Product를 가리키면 0짜리 entry 반환 금지 → 퍼지로 통과 (spec §4.4)
    import harness.backbone.product_alias as pa
    from harness.backbone.crosswalk_store import crosswalk_key
    lk = {"제로박스": {"rec_id": "rZ", "name": "제로박스", "code": "ZERO",
                    "box_type": "", "qty_per_box": 1, "cbm_per_box": 0.0},
          "zero": {"rec_id": "rZ", "name": "제로박스", "code": "ZERO",
                   "box_type": "", "qty_per_box": 1, "cbm_per_box": 0.0}}
    monkeypatch.setattr(pa, "load_crosswalk",
                        lambda: {crosswalk_key("제로박스"): "ZERO"})
    entry, code, method = pa.resolve_product_entry("제로박스", None, None, lk)
    assert method != "crosswalk"


def test_crosswalk_not_used_when_code_given(monkeypatch):
    # 1단(code 직접)이 1.5단보다 우선
    import harness.backbone.product_alias as pa
    from harness.backbone.crosswalk_store import crosswalk_key
    monkeypatch.setattr(pa, "load_crosswalk",
                        lambda: {crosswalk_key("로고스트랩 파우치"): "OTHR"})
    entry, code, method = pa.resolve_product_entry(
        "로고스트랩 파우치", "LSPO", None, _cw_lookup())
    assert code == "LSPO"
    assert method == "code"
```

> 이 테스트들은 `monkeypatch`를 쓴다 — 저장소의 기존 순수-dict 컨벤션에서 벗어나지만,
> 로더가 리포 루트의 실제 SSOT 파일을 읽으므로 그 파일 상태에 테스트가 의존하지 않게
> 하려면 주입이 필요하다. 네트워크·전역 파일 쓰기는 없다.

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/backbone/test_product_alias.py -v -k crosswalk`
Expected: FAIL — `AttributeError: module 'harness.backbone.product_alias' has no attribute 'load_crosswalk'` (monkeypatch 대상 부재).

- [ ] **Step 3: 최소 구현**

`harness/backbone/product_alias.py` 최상단 import 블록에 추가 (`keys`와 마찬가지로 순수 모듈이라 순환 없음):

```python
from harness.backbone.crosswalk_store import crosswalk_key, load_crosswalk
```

그다음 `resolve_product_entry` 안에서, 1단 `if code:` 블록 **직후**·2단 `# 2) 이름 → sync_item` **직전**에 삽입:

```python
    # 1.5) 크로스워크 결정론 계층 — 확정·굿즈명 행만 (spec §4.1).
    #      사람이 검증한 판정이므로 자동 매핑인 sync_item(2단)보다 우선한다.
    #      확정행이 CBM 0 Product를 가리키면 반환하지 않고 통과시킨다(1·2단과 동일 가드).
    if name:
        cw = load_crosswalk()
        if cw:
            rc = cw.get(crosswalk_key(name))
            if rc:
                e = lookup.get(str(rc).lower())
                if e is not None and e.get("cbm_per_box", 0) > 0:
                    return e, rc, "crosswalk"
```

docstring의 우선순위 목록에 한 줄 추가(1단과 2단 사이):

```python
      1.5) 크로스워크 결정론              — 확정·굿즈명 행 (git-SSOT, 사람 검증)
```

그리고 `method` 설명 줄 교체:

```python
      method: 'code' | 'crosswalk' | 'name2code' | 'jaccard' | 'jaccard_norm' | 'unmatched'.
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/backbone/test_product_alias.py -v`
Expected: 신규 4개 포함 전부 PASS.

- [ ] **Step 5: 무회귀 + 파일 부재 안전 확인**

Run: `python -m pytest tests/ -q`
Expected: 전부 PASS. 이 시점에 `data/crosswalk/goods_crosswalk.csv`는 아직 없으므로, 로더가 `{}`를 반환해 1.5단이 무력화되고 기존 동작이 유지된다는 것이 전체 스위트로 증명된다.

- [ ] **Step 6: 커밋**

```bash
git add harness/backbone/product_alias.py tests/backbone/test_product_alias.py
git commit -m "feat(crosswalk): resolve_product_entry 1.5단 결정론 계층 삽입

확정 크로스워크 행을 sync_item(2단)보다 우선 적용 — 사람 검증 판정 우선.
CBM 0 Product 를 가리키는 확정행은 반환하지 않고 퍼지로 통과(1·2단 가드 동일).
크로스워크 파일 부재 시 완전 무동작 → 기존 1~4단 동작 보존."
```

---

### Task 3: 후보 생성 스크립트 (INSERT-only)

**Files:**
- Create: `scripts/crosswalk/build_candidates.py`
- Create: `tests/backbone/test_crosswalk_candidates.py`

**Interfaces:**
- Consumes: `harness.backbone.crosswalk_store.crosswalk_key`, `resolve_product_entry`, `calc_from_products`, `load_product_lookup`, `load_name2code`, `match_product`
- Produces (순수 함수 — 테스트 대상):
  - `merge_rows(existing: list[dict], candidates: list[dict]) -> tuple[list[dict], int]` — 기존 행 무수정 보존, 신규 `표준키`만 append. `(merged, n_added)` 반환. 정렬은 `키유형` → `표준키`.
  - `classify(score: float, matched: bool) -> tuple[str, str]` — `(검증상태, 매칭방식)`. spec §6.2 규칙.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/backbone/test_crosswalk_candidates.py`:

```python
"""후보 생성 — INSERT-only 병합 + 승급 규칙 (spec §6.2·§6.3)."""
from scripts.crosswalk.build_candidates import classify, merge_rows


def _row(key, code, status="미검증", ktype="굿즈명"):
    return {"표준키": key, "키유형": ktype, "TMS_견적코드": code,
            "매칭방식": "유사", "매칭신뢰도": "0.8", "검증상태": status, "근거": "t"}


def test_classify_exact_is_auto_confirmed():
    # score 1.0 = 정규화 후 exact → 철자변형일 뿐이므로 자동 확정 (D2)
    assert classify(1.0, True) == ("확정", "정확")


def test_classify_fuzzy_needs_human():
    assert classify(0.82, True) == ("미검증", "유사")


def test_classify_low_score_is_pending_spec():
    assert classify(0.42, True) == ("보류", "유사")


def test_classify_unmatched_is_pending_spec():
    assert classify(0.0, False) == ("보류", "수기")


def test_merge_preserves_human_decisions():
    # 사람이 미검증→확정으로 올린 행을 재실행이 되돌리면 안 된다 (§6.3)
    existing = [_row("데일리짐색(단품)", "DLYG", status="확정")]
    candidates = [_row("데일리짐색(단품)", "ZZZZ", status="미검증")]
    merged, added = merge_rows(existing, candidates)
    assert added == 0
    assert len(merged) == 1
    assert merged[0]["검증상태"] == "확정"
    assert merged[0]["TMS_견적코드"] == "DLYG"


def test_merge_appends_only_new_keys():
    existing = [_row("기존굿즈", "AAAA", status="확정")]
    candidates = [_row("기존굿즈", "BBBB"), _row("신규굿즈", "CCCC")]
    merged, added = merge_rows(existing, candidates)
    assert added == 1
    assert {r["표준키"] for r in merged} == {"기존굿즈", "신규굿즈"}


def test_merge_is_idempotent():
    existing = [_row("가", "AAAA", status="확정")]
    cands = [_row("나", "BBBB")]
    once, _ = merge_rows(existing, cands)
    twice, added2 = merge_rows(once, cands)
    assert added2 == 0
    assert once == twice


def test_merge_sorts_deterministically():
    merged, _ = merge_rows([], [_row("나", "B"), _row("가", "A"),
                               _row("코드행", "C", ktype="코드")])
    assert [r["표준키"] for r in merged] == ["가", "나", "코드행"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/backbone/test_crosswalk_candidates.py -v`
Expected: 전부 FAIL — `ModuleNotFoundError: No module named 'scripts.crosswalk'`.

- [ ] **Step 3: 최소 구현**

디렉터리만 만든다. **`__init__.py`는 만들지 않는다** — 이 저장소의 `scripts/` 이하에는
`__init__.py`가 하나도 없고(namespace package), `tests/backbone/test_goods_code_audit.py:7`의
`from scripts.backbone.goods_code_audit import ...`가 그대로 동작하는 선례가 있다.

```bash
mkdir -p scripts/crosswalk
```

`scripts/crosswalk/build_candidates.py`:

```python
"""크로스워크 후보 생성 — 실측 시드에서 초기 채우기 (읽기 전용).

spec: docs/superpowers/specs/2026-08-12-bridge-cbm-crosswalk-design.md §6

Airtable 은 GET 만 한다. 산출물은 git 파일 2개:
  data/crosswalk/goods_crosswalk.csv  — SSOT (확정 + 미검증)
  data/crosswalk/pending_specs.csv    — 보류 = 규격요청 리스트 (품질혁신파트 전달)

⚠️ INSERT-only: 기존 행은 어떤 컬럼도 수정하지 않는다. 신규 표준키만 append.
   사람이 미검증→확정으로 올린 판정을 재실행이 되돌리면 거버넌스가 무너진다.

실행: python scripts/crosswalk/build_candidates.py [--write]
필요 env: AIRTABLE_PAT (TMS), AIRTABLE_WMS_PAT (sync_item)
"""
from __future__ import annotations

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

COLUMNS = ["표준키", "키유형", "TMS_견적코드", "매칭방식",
           "매칭신뢰도", "검증상태", "근거"]

CROSSWALK_CSV = os.path.join("data", "crosswalk", "goods_crosswalk.csv")
PENDING_CSV = os.path.join("data", "crosswalk", "pending_specs.csv")

AUTO_CONFIRM_SCORE = 1.0    # 정규화 후 exact — 철자변형일 뿐 (spec D2)
PENDING_SCORE = 0.5         # 미만이면 규격요청 대상 (spec §6.2)


def classify(score: float, matched: bool) -> tuple[str, str]:
    """(검증상태, 매칭방식) — spec §6.2 진입 규칙."""
    if not matched:
        return "보류", "수기"
    if score >= AUTO_CONFIRM_SCORE:
        return "확정", "정확"
    if score < PENDING_SCORE:
        return "보류", "유사"
    return "미검증", "유사"


def merge_rows(existing: list[dict], candidates: list[dict]) -> tuple[list[dict], int]:
    """INSERT-only 병합 — 기존 행 무수정, 신규 표준키만 append (spec §6.3).

    정렬: 키유형 → 표준키. diff 안정성이 리뷰게이트의 전제다.
    """
    seen = {(r.get("표준키") or "").strip() for r in existing}
    added = 0
    out = list(existing)
    for c in candidates:
        k = (c.get("표준키") or "").strip()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(c)
        added += 1
    out.sort(key=lambda r: ((r.get("키유형") or ""), (r.get("표준키") or "")))
    return out, added


def read_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: str, rows: list[dict], *, bom: bool = False) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    enc = "utf-8-sig" if bom else "utf-8"
    with open(path, "w", encoding=enc, newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})


def collect_candidates() -> tuple[list[dict], list[dict], dict]:
    """Shipment 텍스트 전수 → (crosswalk 후보, 규격요청 후보, stats). Airtable GET only."""
    import collections

    import requests
    from dotenv import load_dotenv

    from harness.backbone.keys import is_service
    from harness.backbone.product_alias import inject_synthetic, resolve_product_entry
    from harness.dispatch.cbm_estimator import parse_product_lines_v2
    from harness.settlement.cbm_calc import load_product_lookup, match_product
    from harness.tms_settlement.fetch import load_name2code

    load_dotenv()
    tp = os.environ["AIRTABLE_PAT"]
    headers = {"Authorization": f"Bearer {tp}"}
    lookup = load_product_lookup(headers)
    inject_synthetic(lookup)
    name2code = load_name2code(os.environ.get("AIRTABLE_WMS_PAT"))

    url = "https://api.airtable.com/v0/app4x70a8mOrIKsMf/tbllg1JoHclGYer7m"
    recs, cursor = [], None
    while True:
        params = {"pageSize": 100, "returnFieldsByFieldId": "true",
                  "fields[]": ["fldXXnGOXkm90snKn", "fldgSupj5XLjJXYQo"]}
        if cursor:
            params["offset"] = cursor
        r = requests.get(url, headers=headers, params=params, timeout=30)
        r.raise_for_status()
        d = r.json()
        recs.extend(d.get("records", []))
        cursor = d.get("offset")
        if not cursor:
            break

    freq: collections.Counter = collections.Counter()
    best: dict[str, tuple[float, str, str]] = {}   # name → (score, code, method)
    for rec in recs:
        f = rec["fields"]
        text = f.get("fldXXnGOXkm90snKn") or f.get("fldgSupj5XLjJXYQo") or ""
        if not text:
            continue
        for nm, _q, _x in parse_product_lines_v2(str(text)):
            if not nm or is_service(nm):
                continue
            freq[nm] += 1
            if nm in best:
                continue
            entry, code, method = resolve_product_entry(nm, None, name2code, lookup)
            if entry is None:
                best[nm] = (0.0, "", method)
                continue
            if method in ("code", "crosswalk", "name2code"):
                score = 1.0
            else:
                _k, e, s = match_product(nm, lookup)
                if e is None:
                    from harness.backbone.keys import normalize_goods
                    _k, e, s = match_product(normalize_goods(nm), lookup)
                score = s if e is not None else 0.0
            best[nm] = (score, code or "", method)

    cross, pending = [], []
    stats = collections.Counter()
    for nm, (score, code, method) in best.items():
        status, how = classify(score, bool(code))
        row = {"표준키": nm, "키유형": "굿즈명", "TMS_견적코드": code,
               "매칭방식": how, "매칭신뢰도": f"{score:.2f}",
               "검증상태": status,
               "근거": f"{method} score={score:.2f} freq={freq[nm]}"}
        stats[status] += 1
        (pending if status == "보류" else cross).append(row)

    # 규격요청은 빈도 내림차순 — 무엇부터 요청할지 우선순위
    pending.sort(key=lambda r: -freq.get(r["표준키"], 0))
    return cross, pending, dict(stats)


def main() -> None:
    write = "--write" in sys.argv
    cross, pending, stats = collect_candidates()
    existing = read_csv(CROSSWALK_CSV)
    merged, added = merge_rows(existing, cross)
    pend_existing = read_csv(PENDING_CSV)
    pend_merged, pend_added = merge_rows(pend_existing, pending)

    print(f"후보: crosswalk {len(cross)} (신규 {added}) / 규격요청 {len(pending)} "
          f"(신규 {pend_added})")
    print(f"진입 분포: {stats}")
    if not write:
        print("DRY-RUN — 쓰려면 --write")
        return
    write_csv(CROSSWALK_CSV, merged)
    write_csv(PENDING_CSV, pend_merged, bom=True)
    print(f"WROTE {CROSSWALK_CSV} ({len(merged)}행) / {PENDING_CSV} ({len(pend_merged)}행)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/backbone/test_crosswalk_candidates.py -v`
Expected: 8개 전부 PASS.

- [ ] **Step 5: 커밋**

```bash
git add scripts/crosswalk/ tests/backbone/test_crosswalk_candidates.py
git commit -m "feat(crosswalk): 후보 생성 스크립트 (INSERT-only 병합 + 승급 규칙)

score 1.0 자동확정 / 0.5~1.0 미검증(사람 승급) / <0.5·미매칭 보류(규격요청).
merge_rows 는 기존 행을 절대 수정하지 않고 신규 표준키만 append —
사람이 올린 확정 판정을 재실행이 되돌리지 않는다. Airtable GET only."
```

---

### Task 4: 초기 채우기 실행 + 리뷰게이트 제출

**Files:**
- Create: `data/crosswalk/goods_crosswalk.csv` (생성물)
- Create: `data/crosswalk/pending_specs.csv` (생성물)

**Interfaces:** Task 3의 스크립트를 실행할 뿐, 새 인터페이스 없음.

- [ ] **Step 1: dry-run으로 분포 확인**

Run: `python scripts/crosswalk/build_candidates.py`
Expected: `진입 분포`에 `확정`/`미검증`/`보류` 건수가 출력된다. 전수 Shipment 조회라 수 분 걸린다(약 16.8k건) — 멈춘 것이 아니므로 타임아웃을 넉넉히(1800000ms) 준다.

Sanity check: `확정 + 미검증 + 보류` 합이 파싱된 고유 굿즈명 수와 같아야 한다. `확정`이 0이면 `classify` 또는 score 재계산이 잘못된 것이므로 중단하고 원인을 찾는다.

- [ ] **Step 2: 실제 생성**

Run: `python scripts/crosswalk/build_candidates.py --write`
Expected: 두 CSV가 생성된다.

- [ ] **Step 3: 충돌 검출 통과 확인 (spec §4.2의 실전 검증)**

```bash
python -c "
from harness.backbone.crosswalk_store import validate_crosswalk, load_crosswalk, clear_cache
clear_cache()
m = load_crosswalk(_cache=False)
print(f'확정 결정론 엔트리: {len(m)}')
validate_crosswalk()   # 충돌 시 raise
print('검증 통과 — 충돌 없음')
"
```
Expected: 엔트리 수 출력 후 `검증 통과`.

**`CrosswalkConflictError`가 발생하면 그것은 버그가 아니라 발견이다** — 같은 정규화 키에 서로 다른 견적코드를 자동 배정한 실제 충돌이다(FGPS 류). 이 경우 해당 행들의 `검증상태`를 `보류`로 내리고 `근거`에 충돌 사실을 적은 뒤 재확인한다. **자동으로 한쪽을 고르지 말 것.**

참고: 런타임(`load_crosswalk`)은 충돌 키를 양쪽 다 제외하고 넘어가므로 정산 크론이 죽지는 않는다(spec §4.2 개정). 그래도 해당 굿즈명은 결정론을 못 받고 퍼지로 흐르므로, 충돌은 반드시 해소해야 한다.

- [ ] **Step 4: 커밋 (리뷰게이트 제출)**

```bash
git add data/crosswalk/goods_crosswalk.csv data/crosswalk/pending_specs.csv
git commit -m "data(crosswalk): 초기 채우기 — 실측 시드에서 후보 생성

score 1.0 자동확정 / 나머지 미검증·보류. 미검증→확정 승급은 사람이
이 파일을 직접 수정해 커밋한다 — PR diff 가 리뷰 산출물."
```

- [ ] **Step 5: 사람 리뷰 대상 요약 보고**

다음을 사용자에게 보고한다 (승급 작업은 사용자 몫이므로 자동 진행 금지):
1. 진입 분포 — 확정 / 미검증 / 보류 각 건수
2. `미검증` 중 상위 20건 (승급 검토 대상)
3. `보류` 상위 20건 (빈도순 = 규격요청 우선순위)
4. 충돌이 있었다면 그 목록과 조치

---

### Task 5: 과거분 estimated_cbm 백필 (북극성의 지배적 레버)

크로스워크만으로는 `CBM_유효`가 움직이지 않는다 — 저장된 `estimated_cbm`을 읽기 때문이다. 두 쓰기 경로가 모두 7일 롤링 윈도우라 과거 출하분은 기록된 적이 없다. **이 태스크가 북극성 상승분의 약 7/8을 만든다** (백필 6,079건 vs 브릿지 860건).

**Files:** 없음 — 기존 `scripts/backbone/replay_outbound_cbm.py`를 인자만 바꿔 실행한다. **스크립트를 수정하지 말 것.**

**Interfaces:** Task 2의 1.5단이 이미 리졸버에 들어가 있으므로, 이 백필은 크로스워크 확정행까지 반영된 추정치를 기록한다. 따라서 **Task 4 이후에 실행해야** 브릿지 기여분이 함께 반영된다.

- [ ] **Step 1: dry-run — 쓰기 대상 규모 확인**

Run: `python scripts/backbone/replay_outbound_cbm.py`
(`--recent` 없이 = 전 기간. 16.8k건 조회라 수 분 걸린다. 타임아웃 1800000ms.)

Expected: 쓰기 대상 건수가 출력된다. `fuzzy_write_decision`의 `FUZZY_MIN_CONF=0.5` 게이트를 통과한 건만 대상이므로 **6,079보다 작을 수 있다** — 이는 정상이며, 실제 수치를 Step 3 보고에 쓴다.

- [ ] **Step 2: 백필 전 북극성 기준선 측정**

Run: `python scripts/crosswalk/measure_northstar.py` (Task 6에서 만든다 — 순서상 Task 6을 먼저 하거나, 이 단계에서 만들어 쓴다)

⚠️ 순서 주의: 북극성 측정 스크립트(Task 6)가 이 태스크의 전/후 비교에 필요하다. **Task 6을 Task 5보다 먼저 실행해도 무방하며**, 그 편이 기준선 확보에 유리하다.

- [ ] **Step 3: 사용자 게이트 — 백필 실행 승인 (자동 실행 금지)**

`--write`는 **과거 출하 수천 건의 `estimated_cbm`·`estimation_confidence`를 PATCH**한다. 영향 범위를 보고하고 승인받는다:
1. 쓰기 대상 건수 (Step 1 dry-run 결과)
2. 영향 지표 — `CBM_유효`는 배차일지 **차량이용률** rollup과 주간리포트 **출하단가(원/CBM)**의 소스다. 두 KPI의 과거 수치가 바뀐다.
3. 원장 아님 — `estimated_cbm`은 파생 계산 필드이지 거래 원장이 아니므로 Immutable Ledger 위반이 아니다. 다만 되돌리려면 재실행이 아니라 필드 초기화가 필요하다.

- [ ] **Step 4: 백필 실행**

Run: `python scripts/backbone/replay_outbound_cbm.py --write`
Expected: dry-run에서 예고한 건수만큼 PATCH된다.

---

### Task 6: 북극성 측정 + 최종 사용자 게이트

**Files:**
- Create: `scripts/crosswalk/measure_northstar.py`

**Interfaces:**
- Produces: 거점별(`다영`/`에이원`) `CBM_유효` 완결율. 분모 = **품목 텍스트 보유 출하**.

- [ ] **Step 1: 측정 스크립트 작성**

거점 판정은 `harness/tms_settlement/calc.py`와 동일 규칙을 쓴다 — 출고지 주소(`fldb24I9EQ2KPXv6S`)에 `성남` 또는 `다영`이 있으면 `다영`, 그 외 주소 보유 건은 `에이원`.

필드: `Total_CBM`=`fldJ9DHjwoRyeUEqE`, `estimated_cbm`=`fldaP8D9AM8CHEZ2o`, 품목텍스트=`fldXXnGOXkm90snKn` 우선 `fldgSupj5XLjJXYQo` 폴백.

`CBM_유효 보유` = `Total_CBM > 0 or estimated_cbm > 0`.
분모 = `parse_product_lines_v2`로 파싱했을 때 비서비스 라인이 1개 이상인 출하.

출력: 거점별 `보유/분모 = %`, 그리고 미보유 건을 ① 라인 해소됨(백필 미반영) ② 브릿지 등재 가능 ③ 마스터 부재로 분해. **Airtable GET only.**

- [ ] **Step 2: 백필 전후 비교 실행**

Task 5 실행 전후로 각각 돌려 두 수치를 확보한다.

- [ ] **Step 3: 최종 사용자 게이트 (main 병합 금지)**

**게이트 판정 기준 (spec §1.1):**

| 거점 | 기준선 | **필수** | 목표 |
|---|---:|---:|---:|
| 다영 (분모 739) | 27.5% | **≥ 79%** | ~93% |
| 에이원 (분모 10,264) | 28.3% | **≥ 83%** | ~91% |

보고 항목:
1. 거점별 완결율 — 기준선 → 백필 후 → (브릿지 승급 반영 후)
2. **백필 기여분과 브릿지 기여분을 분리**해 제시 (둘을 섞으면 브릿지 효과를 오판한다)
3. `crosswalk` 경로로 해소된 라인 수 = 결정론 전환 규모 (커버리지 중립 — 안정성 지표)
4. 정산 상하차비: ₩3,760,000 → 실측값, 차액 (`measure_cbm_coverage.py`)
5. 1.5단 도입으로 **코드가 바뀐** 라인 표본 — 있다면 육안 확인
6. 잔여 마스터 부재 건수 → P2 규격요청 인계 규모

목표 미달은 실패가 아니다 — 브릿지 기여분은 사람의 확정 승급 속도에 종속되고, 잔여 7~9%는 Product 마스터 부재(P2) 몫이다. **필수 기준 미달이면** 백필이 정상 반영되지 않은 것이므로 중단하고 조사한다.

---

## 자체 검토 결과 (Self-Review)

**Spec 커버리지:**

| Spec 항목 | 담당 |
|---|---|
| §4.1 1.5단 삽입 위치·`method='crosswalk'` | Task 2 |
| §4.2 정규화 키 + 충돌 검출 hard error | Task 1 (구현·테스트), Task 4 Step 3 (실전) |
| §4.3 로더 계약 (확정∧굿즈명 필터·캐시·파일부재 안전) | Task 1 |
| §4.4 CBM 가드 (`cbm_per_box > 0`) | Task 2 Step 1 세 번째 테스트 |
| §5 데이터 모델 7컬럼·정렬 | Task 3 (`COLUMNS`, `merge_rows` 정렬) |
| §6.1 산출물 2개·인코딩 | Task 3 (`write_csv` bom 인자) |
| §6.2 진입 규칙 | Task 3 `classify` |
| §6.3 INSERT-only 멱등성 | Task 3 `merge_rows` + 멱등성 테스트 |
| §6.4 리뷰게이트 | Task 4 Step 4·5 |
| §7-1 결정론 | Task 1 (같은 입력→같은 맵), Task 2 |
| §7-2 충돌 검출 | Task 1 `test_conflicting_confirmed_rows_raise` |
| §7-3 확정만 결정론 | Task 1 `test_loads_only_confirmed_goods_rows` |
| §7-4 파일 부재 안전 | Task 1 `test_missing_file_returns_empty`, Task 2 Step 5 |
| §7-5 CBM 가드 | Task 2 |
| §1.1 북극성 게이트 (다영 ≥79% / 에이원 ≥83%) | Task 6 Step 3 |
| §1.1 백필 없이는 지표 불변 → P1에 백필 포함 | Task 5 |
| §7-6 북극성 완결율 측정 | Task 6 Step 1·2 |
| §7-7 멱등성 | Task 3 `test_merge_is_idempotent` |
| §7-8 이관 parity 골든 | **미포함** — 아래 참조 |
| §9 정산 금액 영향 게이트 | Task 5 Step 3 |

**§7-8(이관 parity 골든) 의도적 제외**: 이 골든은 P2의 ALIAS 이관이 동일성을 증명하기 위한 것이다. P1은 ALIAS를 건드리지 않으므로(D1) 지금 골든을 만들어도 검증할 대상이 없다. P2 계획의 첫 태스크로 넘긴다.

**타입 일관성:** `crosswalk_key`는 Task 1이 정의하고 Task 2·3이 동일 import로 쓴다. `load_crosswalk()`는 `dict[str,str]`(정규화키→코드 upper)이며 Task 2의 `cw.get(crosswalk_key(name))` → `lookup.get(str(rc).lower())` 조회와 맞는다. `merge_rows`/`classify` 시그니처는 Task 3 테스트와 본문이 일치한다. `method='crosswalk'`는 Task 2가 만들고 Task 3의 `("code","crosswalk","name2code")` score=1.0 분기에서 참조된다.

**알려진 이탈:** Task 2 테스트가 `monkeypatch`를 쓴다(저장소 컨벤션은 순수 dict). 로더가 리포 루트의 실제 SSOT를 읽으므로 파일 상태 독립성을 위해 필요하며, 네트워크·전역 쓰기는 없다.
