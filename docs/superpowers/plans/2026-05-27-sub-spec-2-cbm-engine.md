# Sub-Spec 2: CBM 추정 엔진 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans`. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Design doc:** `_AutoResearch/SCM/outputs/2026-05-27-sub-spec-2-cbm-engine-design.md`
> **Master Roadmap:** `docs/superpowers/plans/2026-05-27-lane-strategy-master-roadmap-v3.md` §2
> **Dependency:** Sub-Spec 1 완료 (commit 0363050 — `resource_loader.py` + `harness/dispatch/__init__.py` 존재)
> **Estimated effort:** 2~3주 (11 Task)
> **No git commit during this plan** — 사용자가 Task별 검토 후 batch commit

**Goal:** Shipment의 출하 품목 텍스트를 Product 테이블(344 records)과 매칭해 *예상 CBM*을 산출하고, 임가공 완료 시점에 Total_CBM 실측과 비교·재계산하는 *2단계 hybrid 엔진* 구현.

**Architecture:**

```
Airtable Shipment (D-7~D-1)
   │
   │ ① Total_CBM 존재? → 실측 사용 (confidence=1.0)
   ↓
   │ ② 최종 출고 품목 및 수량 (임가공 후 텍스트)
   │ ③ 최종 출하 품목 (임가공 전 텍스트)
   ↓
[harness/dispatch/cbm_estimator.py]
   ↓
parse_product_lines_v2()  ── Q1+Q2 확장
   ↓ [(품목명, 수량, extra), ...]
match_product()  ── 기존 cbm_calc.py 재사용 (Jaccard ≥ 0.4)
   ↓
Product 캐시 (24h TTL, in-memory)
   ↓ [harness/dispatch/product_loader.py]
estimated_cbm + confidence
   ↓
Airtable Shipment 3 필드 update
  (estimated_cbm, estimation_confidence, estimation_updated_at)
   ↓
Sub-Spec 3 Wave 추천 → Sub-Spec 4 polling 시 re-estimate
```

**Tech Stack:**
- Python 3.11+ (requests, pytest, dataclasses)
- Airtable MCP (`mcp__claude_ai_Airtable__create_field`, `update_records_for_table`)
- 기존 `harness/settlement/cbm_calc.py` import (재구현 X)
- `harness/_core/airtable.py` (rate-limited client) 또는 `requests`
- pytest + harness-validator

---

## Validation Contract (C1~C4)

> 본 Contract은 Master Roadmap §6 통합 Validation Contract 22건 중 4건.

### C1 — Product 캐시 적재

**Definition:** `harness.dispatch.product_loader.load()` 호출 시 Product 테이블 전체 records가 캐시에 적재. NULL 박스 사이즈는 `BOX_TYPE_TO_CBM_M3` fallback.

**Pass criteria (quantitative):**
- `len(cache.entries) ≥ 327` AND `≤ 361` (344 ± 5%)
- `entries[i].cbm_per_box > 0` 비율 ≥ 95%
- name·code 양방향 lookup OK

**Verification command:**
```bash
pytest tests/dispatch/test_product_loader.py::test_load_full_count -v
pytest tests/dispatch/test_product_loader.py::test_cbm_fallback -v
```

**Failure mode:** count 부족 → Airtable PAT·rate limit 점검 / cbm 0 비율 > 5% → 박스명칭 NULL records dump → 사용자 수동 입력 요청

### C2 — parse_product_lines() 정확도

**Definition:** Golden 100-sample shipment 텍스트 입력 시 *수량 추출 정확도* ≥ 95%.

**Pass criteria (quantitative):**
- 수량 오류 < 5건 / 100건 (5% 이하)
- Golden set: `tests/dispatch/fixtures/cbm_golden_100.yaml`
- 오류 정의: (추출 수량 ≠ 정답) OR (라인 수 불일치)

**Verification command:**
```bash
pytest tests/dispatch/test_cbm_estimator.py::test_parse_golden_100 -v
```

**Failure mode:** 실패 패턴 dump → 정규식 패턴 추가 → 재테스트. Golden set 자체 오류면 사용자 검토.

### C3 — 전체 매칭률

**Definition:** Backtest 1,640건 (또는 가용 sample 300+건) 실행 시 라인 단위 Jaccard ≥ 0.4 비율.

**Pass criteria (quantitative):**
- 라인 단위 매칭률 ≥ **70%**
- Shipment confidence ≥ 0.7 비율 ≥ 60%
- Total_CBM 보유 케이스: median(|estimated − actual| / actual) < 30%

**Verification command:**
```bash
python harness/dispatch/cbm_estimator.py --backtest --since 2026-01-01 \
  --out _AutoResearch/SCM/outputs/cbm-backtest-report.md
```
보고서에서 위 3개 지표 확인.

**Failure mode:** < 70% → 미매칭 dump 분석 → Product 등록 보완 OR 정규식 강화. **< 50% → Kill criteria 발동** (Master Roadmap §2): 자동 추정 비활성화 + 사용자 수동 입력만 운영.

### C4 — 임가공 trigger 재계산

**Definition:** `Total_CBM`이 NULL→number 또는 number→다른 number 전이 시, 다음 polling cycle(≤5h) 안에 `estimated_cbm = Total_CBM` AND `confidence = 1.0`.

**Pass criteria (quantitative):**
- 테스트 shipment 1건: `Total_CBM` 수동 update → 다음 polling 후 `estimated_cbm == Total_CBM`
- Audit log `audit_log/cbm_transitions.jsonl`에 transition entry 1건 기록
- 시간 차 ≤ 5h (= 다음 polling cycle 도달)

**Verification command:**
```bash
pytest tests/dispatch/test_cbm_estimator.py::test_repolling_trigger -v
# 추가 수동 E2E:
python harness/dispatch/cbm_estimator.py --self-check
```

**Failure mode:** snapshot 파일 권한·경로 점검 / polling cron 로그 확인 / >5h 지연 시 polling 빈도 증가 검토

---

## File Structure

| 파일 | 책임 | 신규/수정 |
|------|------|---------|
| Airtable `Shipment` (테이블) | 3 신규 필드 추가 (`estimated_cbm`, `estimation_confidence`, `estimation_updated_at`) | ✏️ 수정 (필드 추가) |
| `harness/_core/schema_pin.json` | Shipment 항목에 3개 신규 필드 ID 추가 | ✏️ 수정 |
| `harness/dispatch/product_loader.py` | Product 캐시 (24h TTL, stale-while-revalidate) | 🆕 신규 |
| `harness/dispatch/cbm_estimator.py` | CBM 추정 엔진 (parse_v2 + match + branch + estimate + write-back) | 🆕 신규 |
| `tests/dispatch/test_product_loader.py` | C1 검증 | 🆕 신규 |
| `tests/dispatch/test_cbm_estimator.py` | C2·C3·C4 검증 + 8~10 pytest | 🆕 신규 |
| `tests/dispatch/fixtures/cbm_golden_100.yaml` | Golden 100 sample | 🆕 신규 |
| `scripts/dispatch/run_cbm_polling.py` | Polling 진입점 (Sub-Spec 4와 공유 예정) | 🆕 신규 |
| `audit_log/cbm_transitions.jsonl` | 이상값·임가공 transition 로그 | 🆕 신규 (디렉터리만) |
| `.claude/feature_list.json` | SCM-LANE-SUBSPEC-2 상태 갱신 | ✏️ 수정 |

**기존 파일 import만 (수정 X):** `harness/settlement/cbm_calc.py` (Karpathy Surgical Changes 원칙)

---

## Task 0: Pre-flight (백업 + Product 표본 분석)

**Files:**
- Read: `harness/_core/schema_pin.json`
- Read: `harness/settlement/cbm_calc.py` (재사용 함수 확인)
- Backup: `harness/_core/schema_pin.json`

**Scope:** 실행 전 상태 보존 + Product 테이블 sample 30건으로 매칭 가능성 사전 검증.

**Dependencies:** Sub-Spec 1 완료

- [ ] **Step 1: schema_pin.json 백업**
  ```bash
  cp harness/_core/schema_pin.json harness/_core/schema_pin.json.bak.subspec2.2026-05-27
  ```

- [ ] **Step 2: Product 테이블 sample 30건 직접 조회 (MCP)**
  `mcp__claude_ai_Airtable__list_records_for_table` (baseId=`app4x70a8mOrIKsMf`, tableId=`tblBNh6oGDlTKGrdQ`, max=30)
  - 박스명칭 NULL records 카운트
  - `(키트)` 접미사 records 카운트
  - cbm_per_box=0 비율 산정 (BOX_TYPE_TO_CBM_M3 fallback 대상)

- [ ] **Step 3: Sample 30건 추정 dry-run**
  최근 Shipment 30건 `최종 출하 품목` 텍스트로 기존 `cbm_calc.parse_product_lines + match_product` 실행 → 라인 매칭률 측정 (사전 baseline)
  결과 dump: `_AutoResearch/SCM/outputs/cbm-preflight-sample30.md`

**Verification command:**
```bash
ls -la harness/_core/schema_pin.json.bak.subspec2.2026-05-27
cat _AutoResearch/SCM/outputs/cbm-preflight-sample30.md | head -50
```

---

## Task 1: Shipment 테이블에 3 신규 필드 추가

**Files:**
- Airtable `Shipment` (tbllg1JoHclGYer7m): 3 필드 추가
- `harness/_core/schema_pin.json`: field IDs 추가

**Scope:** `estimated_cbm`, `estimation_confidence`, `estimation_updated_at` 신규 필드 — *immutable ledger 원칙*에 따라 기존 `Total_CBM` 분리 보관.

**Dependencies:** Task 0

- [ ] **Step 1: `estimated_cbm` 필드 생성 (MCP)**
  ```
  mcp__claude_ai_Airtable__create_field
  baseId: app4x70a8mOrIKsMf
  tableId: tbllg1JoHclGYer7m
  name: estimated_cbm
  type: number
  options: { precision: 4 }
  ```

- [ ] **Step 2: `estimation_confidence` 필드 생성**
  ```
  name: estimation_confidence
  type: number
  options: { precision: 2 }
  ```

- [ ] **Step 3: `estimation_updated_at` 필드 생성**
  ```
  name: estimation_updated_at
  type: dateTime
  options: { dateFormat: { name: "iso" }, timeFormat: { name: "24hour" }, timeZone: "Asia/Seoul" }
  ```
  (대안: `lastModifiedTime` 필드 — 자동 갱신. 단 *어느 필드 수정 시*인지 watch list 지정 필요)

- [ ] **Step 4: schema_pin.json 갱신**
  반환된 field ID 3개를 `schema_pin.json` Shipment 섹션에 추가.

**Verification command:**
```bash
python -c "import json; pin = json.load(open('harness/_core/schema_pin.json')); ship = pin['tables']['Shipment']['fields']; assert 'estimated_cbm' in [v['name'] for v in ship.values()]; print('OK')"
```

---

## Task 2: `harness/dispatch/product_loader.py` 신규 (Product 캐시)

**Files:**
- 신규: `harness/dispatch/product_loader.py`

**Scope:** Q7 결정 반영 — 24h TTL in-memory 캐시 + stale-while-revalidate. 기존 `cbm_calc.load_product_lookup()` thin wrapper.

**Dependencies:** Task 1

- [ ] **Step 1: 스켈레톤 작성**
  ```python
  # harness/dispatch/product_loader.py
  import time
  from dataclasses import dataclass, field
  from harness.settlement.cbm_calc import load_product_lookup

  @dataclass
  class ProductCache:
      lookup: dict = field(default_factory=dict)
      loaded_at: float = 0.0
      ttl_sec: int = 86400  # 24h

      def is_stale(self) -> bool:
          return time.time() - self.loaded_at > self.ttl_sec

  _CACHE = ProductCache()

  def load(headers: dict, force: bool = False) -> ProductCache:
      """Load Product cache. Stale-while-revalidate on fetch failure."""
      if not force and not _CACHE.is_stale() and _CACHE.lookup:
          return _CACHE
      try:
          _CACHE.lookup = load_product_lookup(headers)
          _CACHE.loaded_at = time.time()
      except Exception as e:
          if _CACHE.lookup:
              print(f"WARN: Product fetch failed, using stale cache: {e}")
          else:
              raise
      return _CACHE

  def invalidate() -> None:
      _CACHE.loaded_at = 0.0
  ```

- [ ] **Step 2: __init__.py에 export 추가**
  `harness/dispatch/__init__.py`에 `from .product_loader import load as load_products, invalidate`

**Verification command:**
```bash
python -c "from harness.dispatch.product_loader import load; import os; from dotenv import load_dotenv; load_dotenv(); h = {'Authorization': f'Bearer {os.environ[\"AIRTABLE_PAT\"]}'}; c = load(h); print(f'Loaded {len(c.lookup)} keys (name+code), {len({v[\"rec_id\"] for v in c.lookup.values()})} unique entries')"
```
**Expected:** Unique entries ≥ 327 (C1 첫 번째 조건)

---

## Task 3: `harness/dispatch/cbm_estimator.py` 신규 (parse + match + estimate)

**Files:**
- 신규: `harness/dispatch/cbm_estimator.py`

**Scope:** CBM 추정 엔진 본체. 시점 분기 + parse_v2 (Q1+Q2) + match + Shipment write-back.

**Dependencies:** Task 2

- [ ] **Step 1: parse_product_lines_v2() — Q1+Q2 확장**
  기존 `cbm_calc.parse_product_lines`를 1차 시도 → 실패 시 확장 패턴 시도.
  ```python
  import re
  from harness.settlement.cbm_calc import parse_product_lines as _parse_v1

  _QTY_PATTERNS = [
      re.compile(r"[×xX*]\s*(\d+)\s*$"),                    # ×40
      re.compile(r"(\d+)\s*(?:개|EA|ea|set|SET|박스)\s*$"),  # 40개, 40 set
      re.compile(r"\s+(\d+)\s*$"),                          # trailing N
  ]
  _EXTRA_PATTERN = re.compile(r"(?:\+여분\s*|여분\s*포함\s*|\(\s*여분\s*)(\d+)")

  def parse_product_lines_v2(text: str) -> list[tuple[str, int, int]]:
      """Returns [(product_name, total_qty, extra), ...]
      total_qty 는 본수량 + 여분."""
      # 1차: 기존 _parse_v1 사용 (기본 패턴)
      lines = _parse_v1(text)
      results = []
      for prod, qty in lines:
          # 여분 추출 시도
          extra_match = _EXTRA_PATTERN.search(prod)
          extra = 0
          if extra_match:
              extra = int(extra_match.group(1))
              prod = _EXTRA_PATTERN.sub("", prod).strip()
          # 1차 실패 (qty=0) 시 확장 패턴 시도
          if qty == 0:
              for p in _QTY_PATTERNS:
                  m = p.search(prod)
                  if m:
                      qty = int(m.group(1))
                      prod = prod[:m.start()].strip()
                      break
          if prod:
              # 여분 휴리스틱: extra > qty*0.2 면 의심 → 0으로 reset
              if extra > qty * 0.2 and qty > 0:
                  extra = 0
              results.append((prod, qty + extra, extra))
      return results
  ```

- [ ] **Step 2: estimate_shipment_cbm() — 메인 추정 함수**
  ```python
  import math
  from harness.settlement.cbm_calc import match_product

  def estimate_shipment_cbm(shipment: dict, cache) -> dict:
      """Returns: {estimated_cbm, confidence, mode, matched, unmatched}"""
      f = shipment.get("fields", shipment)
      total_cbm = f.get("Total_CBM") or 0
      try:
          total_cbm = float(total_cbm)
      except (TypeError, ValueError):
          total_cbm = 0.0
      if total_cbm > 0:
          return {"estimated_cbm": round(total_cbm, 4), "confidence": 1.0,
                  "mode": "실측", "matched": [], "unmatched": []}

      text = f.get("최종 출고 품목 및 수량") or ""
      mode = "임가공_후_추정" if text else "임가공_전_추정"
      if not text:
          text = f.get("최종 출하 품목", "")
      lines = parse_product_lines_v2(text)
      if not lines:
          return {"estimated_cbm": 0.0, "confidence": 0.0,
                  "mode": "no_match", "matched": [], "unmatched": []}

      total = 0.0
      matched, unmatched, scores = [], [], []
      for name, qty, extra in lines:
          if qty == 0:
              scores.append(0.0); unmatched.append(name); continue
          key, entry, score = match_product(name, cache.lookup)
          if entry is None:
              scores.append(0.0); unmatched.append(name); continue
          n_boxes = math.ceil(qty / entry["qty_per_box"])
          total += n_boxes * entry["cbm_per_box"]
          scores.append(score)
          matched.append({"name": name, "matched_key": key, "score": score,
                          "qty": qty, "extra": extra, "n_boxes": n_boxes})
      matched_count = sum(1 for s in scores if s >= 0.4)
      confidence = matched_count / len(lines)
      return {"estimated_cbm": round(total, 4),
              "confidence": round(confidence, 2),
              "mode": mode, "matched": matched, "unmatched": unmatched}
  ```

- [ ] **Step 3: write_back_to_airtable() — 결과를 3 신규 필드에 PATCH**
  10건 batch PATCH (`memory:reference_airtable_perf.md` 패턴).

- [ ] **Step 4: CLI 진입점 (`--backtest`, `--self-check`)**
  ```python
  if __name__ == "__main__":
      import argparse
      ap = argparse.ArgumentParser()
      ap.add_argument("--backtest", action="store_true")
      ap.add_argument("--self-check", action="store_true")
      ap.add_argument("--since", default="2026-01-01")
      ap.add_argument("--out", default=None)
      args = ap.parse_args()
      # ... dispatch
  ```

**Verification command:**
```bash
python -c "from harness.dispatch.cbm_estimator import parse_product_lines_v2; print(parse_product_lines_v2('굿이너프 비치타월×40+여분 5, Solid G형 L 20개'))"
```
**Expected:** `[('굿이너프 비치타월', 45, 5), ('Solid G형 L', 20, 0)]`

---

## Task 4: 기존 `cbm_calc.py` 함수 import 확인 (마이그레이션 X)

**Files:**
- 수정 X — *import 경로만 점검*

**Scope:** Karpathy "Surgical Changes" 원칙. 기존 `cbm_calc.py`는 `tms_settlement` 정산 파이프라인이 사용 중 → **이동·리네이밍 금지**. Sub-Spec 2는 *import 전용*.

**Dependencies:** Task 3

- [ ] **Step 1: Import 경로 일관성 확인**
  `harness/dispatch/product_loader.py`와 `harness/dispatch/cbm_estimator.py` 모두 다음 경로 사용:
  ```python
  from harness.settlement.cbm_calc import (
      load_product_lookup,
      match_product,
      parse_product_lines as _parse_v1,
  )
  ```

- [ ] **Step 2: 기존 사용처 회귀 무영향 확인**
  ```bash
  grep -rn "from cbm_calc\|from harness.settlement.cbm_calc\|from settlement.cbm_calc" harness/ scripts/ tests/
  ```
  결과 dump를 plan 실행 노트에 첨부. 어떤 import도 변경 X.

- [ ] **Step 3: README 또는 docstring 추가 (`harness/settlement/cbm_calc.py` 최상단)**
  *현재 운영 중인 의존성을 docstring에 명시*. 코드 변경 X, 주석만.
  → 단 docstring 추가는 *surgical*. 만약 사용자가 "주석 추가도 금지"로 보면 skip.

**Verification command:**
```bash
pytest tests/settlement/ -v  # 기존 cbm_calc 회귀 테스트 통과 확인
```

---

## Task 5: `tests/dispatch/test_product_loader.py` (3~4 pytest)

**Files:**
- 신규: `tests/dispatch/test_product_loader.py`

**Scope:** C1 검증.

**Dependencies:** Task 2

- [ ] **Step 1: `test_load_full_count`**
  ```python
  def test_load_full_count():
      cache = load(_headers())
      unique_ids = {v["rec_id"] for v in cache.lookup.values()}
      assert 327 <= len(unique_ids) <= 361, f"Expected 344±5%, got {len(unique_ids)}"
  ```

- [ ] **Step 2: `test_cbm_fallback`**
  ```python
  def test_cbm_fallback():
      cache = load(_headers())
      unique = {v["rec_id"]: v for v in cache.lookup.values()}
      with_cbm = sum(1 for e in unique.values() if e["cbm_per_box"] > 0)
      ratio = with_cbm / len(unique)
      assert ratio >= 0.95, f"cbm > 0 ratio {ratio:.2%} < 95%"
  ```

- [ ] **Step 3: `test_name_and_code_lookup`**
  Sample entry 1개 골라 `lookup["name_lower"]`와 `lookup["code_lower"]` 양쪽 매칭 확인.

- [ ] **Step 4: `test_cache_ttl_and_invalidate`**
  Mock time → invalidate 후 fresh fetch / TTL 내 cached 사용.

**Verification command:**
```bash
pytest tests/dispatch/test_product_loader.py -v
```

---

## Task 6: `tests/dispatch/test_cbm_estimator.py` (8~10 pytest + Golden set)

**Files:**
- 신규: `tests/dispatch/test_cbm_estimator.py`
- 신규: `tests/dispatch/fixtures/cbm_golden_100.yaml`

**Scope:** C2·C3·C4 검증.

**Dependencies:** Task 3

- [ ] **Step 1: Golden 100-sample 생성**
  ```bash
  python scripts/dispatch/build_golden_set.py --n 100 --out tests/dispatch/fixtures/cbm_golden_100.yaml
  ```
  스크립트는 최근 Shipment 100건 `최종 출하 품목` 텍스트를 가져와 *사용자 검증 답안*과 함께 YAML로 저장. (Task 6.5에서 사용자 답안 추가)

- [ ] **Step 2: 사용자 답안 보강** (manual 1회)
  Golden YAML 각 line별 `expected_lines: [{name: ..., qty: ..., extra: ...}, ...]`

- [ ] **Step 3: `test_parse_golden_100` — C2 핵심**
  ```python
  @pytest.mark.parametrize("case", load_golden())
  def test_parse_golden_100_individual(case):
      result = parse_product_lines_v2(case["input"])
      assert len(result) == len(case["expected_lines"])
      for (name, qty, extra), exp in zip(result, case["expected_lines"]):
          assert qty == exp["qty"], f"qty mismatch on '{case['input']}'"
  ```
  Aggregate: error count ≤ 5 → C2 통과.

- [ ] **Step 4: `test_parse_extra_여분`** (Q2)
  ```python
  cases = [
      ("티셔츠 100+여분 5", [("티셔츠", 105, 5)]),
      ("티셔츠 100+2", [("티셔츠", 102, 2)]),
      ("티셔츠 (여분 5) 100", [("티셔츠", 105, 5)]),  # 또는 적절히
  ]
  ```

- [ ] **Step 5: `test_parse_qty_patterns`** (Q1)
  `×40`, `40개`, `40set`, `40박스`, `40 EA` 각각 정상 추출.

- [ ] **Step 6: `test_estimate_branch_실측`** (시점 분기)
  Total_CBM > 0 → mode=실측, confidence=1.0.

- [ ] **Step 7: `test_estimate_branch_임가공후`**
  Total_CBM=0 + 최종 출고 품목 및 수량 존재 → mode=임가공_후_추정.

- [ ] **Step 8: `test_estimate_branch_임가공전`**
  Total_CBM=0 + 최종 출고 NULL + 최종 출하 품목 존재 → mode=임가공_전_추정.

- [ ] **Step 9: `test_confidence_threshold`** (Q4)
  Mock 4 lines / 3 매칭 ≥ 0.4 → confidence=0.75. < 0.7 review flag.

- [ ] **Step 10: `test_repolling_trigger`** (C4)
  Mock shipment Total_CBM `NULL → 1.234` transition → re-estimate 호출 → audit_log에 1건 추가, confidence=1.0.

**Verification command:**
```bash
pytest tests/dispatch/test_cbm_estimator.py -v --tb=short
```
**Pass criteria:** 모든 test PASS + `test_parse_golden_100` 오류 ≤ 5건.

---

## Task 7: Polling integration — Total_CBM diff 감지

**Files:**
- 신규: `scripts/dispatch/run_cbm_polling.py`
- 신규: `state/cbm_last_snapshot.json` (런타임 생성)

**Scope:** Sub-Spec 4 polling cron(09·14·17시 KST)과 공유. *현재는 standalone 스크립트로 작성, Sub-Spec 4에서 호출 통합.*

**Dependencies:** Task 3, Task 6

- [ ] **Step 1: snapshot diff 로직**
  ```python
  # scripts/dispatch/run_cbm_polling.py
  def detect_transitions(current, previous):
      transitions = []
      for sh in current:
          prev = previous.get(sh["id"], {})
          old = prev.get("Total_CBM", 0) or 0
          new = sh["fields"].get("Total_CBM", 0) or 0
          if (old == 0 and new > 0) or (old != new and new > 0):
              transitions.append((sh, old, new))
      return transitions
  ```

- [ ] **Step 2: 모든 active shipment에 추정 실행**
  자동 대상 필터: project IS NOT NULL AND 이동목적 ∈ {고객납품, 생산샘플} AND 출하확정일 BETWEEN today AND today+7

- [ ] **Step 3: estimated_cbm + confidence + updated_at PATCH**
  10건 batch PATCH (Airtable batch 패턴).

- [ ] **Step 4: snapshot 저장**
  `state/cbm_last_snapshot.json`에 다음 polling을 위해 저장.

- [ ] **Step 5: 수동 dry-run**
  ```bash
  python scripts/dispatch/run_cbm_polling.py --dry-run --limit 10
  ```

**Verification command:**
```bash
python scripts/dispatch/run_cbm_polling.py --dry-run --limit 10
# Expected: "Would PATCH N records" 형식 출력, 실제 PATCH 없음
```

---

## Task 8: Audit logging (이상값 탐지)

**Files:**
- 신규: `audit_log/` 디렉터리
- 신규: `harness/dispatch/audit.py`
- 신규: `audit_log/cbm_transitions.jsonl` (런타임 append)
- 신규: `audit_log/cbm_anomalies.jsonl` (런타임 append)

**Scope:** Q6 결정 반영. 이상값 + transition 별도 jsonl.

**Dependencies:** Task 7

- [ ] **Step 1: `harness/dispatch/audit.py`**
  ```python
  import json, os
  from datetime import datetime, timezone

  AUDIT_DIR = "audit_log"

  def _append(filename: str, entry: dict) -> None:
      os.makedirs(AUDIT_DIR, exist_ok=True)
      entry["timestamp"] = datetime.now(timezone.utc).isoformat()
      with open(os.path.join(AUDIT_DIR, filename), "a", encoding="utf-8") as f:
          f.write(json.dumps(entry, ensure_ascii=False) + "\n")

  def log_transition(sc_id, prev, new, estimate_before, confidence_after):
      _append("cbm_transitions.jsonl", {
          "type": "transition", "sc_id": sc_id, "prev": prev, "new": new,
          "estimate_before": estimate_before, "confidence_after": confidence_after,
      })

  def log_anomaly(sc_id, estimated, actual, matched, unmatched):
      diff = abs(estimated - actual)
      diff_ratio = diff / actual if actual > 0 else 0
      if diff_ratio > 0.5 and actual > 0.1:
          _append("cbm_anomalies.jsonl", {
              "type": "anomaly", "sc_id": sc_id,
              "estimated": estimated, "actual": actual,
              "diff": diff, "diff_ratio": diff_ratio,
              "matched": matched, "unmatched": unmatched,
          })
          return True
      return False
  ```

- [ ] **Step 2: `cbm_estimator.py`에 audit hook 추가**
  실측 모드 진입 시 `log_anomaly` 호출 (직전 estimate vs 새 actual).
  transition 시 `log_transition` 호출.

- [ ] **Step 3: 일 1회 요약 Slack 알림 (선택)**
  `harness/_core/notifier.py` 활용 — 24h 누적 anomaly 개수 + 상위 5건 SC_id.

**Verification command:**
```bash
python -c "from harness.dispatch.audit import log_anomaly; r = log_anomaly('SC-TEST', 1.0, 2.5, [], ['T']); print(f'logged: {r}')"
ls -la audit_log/
```

---

## Task 9: Validation Contract C1~C4 self-check 스크립트

**Files:**
- 신규: `scripts/dispatch/validate_subspec2_contracts.py`

**Scope:** C1~C4 4건을 단일 명령으로 자동 검증 + 보고서 생성.

**Dependencies:** Task 5, Task 6, Task 7

- [ ] **Step 1: 스크립트 작성**
  ```python
  # scripts/dispatch/validate_subspec2_contracts.py
  def check_c1(): # call test_load_full_count + test_cbm_fallback
  def check_c2(): # run pytest test_parse_golden_100, parse aggregate
  def check_c3(): # run --backtest 1640 records, measure 매칭률·median diff
  def check_c4(): # run test_repolling_trigger + manual E2E hint

  if __name__ == "__main__":
      results = {"C1": check_c1(), "C2": check_c2(), "C3": check_c3(), "C4": check_c4()}
      print(json.dumps(results, indent=2, ensure_ascii=False))
      sys.exit(0 if all(r["pass"] for r in results.values()) else 1)
  ```

- [ ] **Step 2: 실행**
  ```bash
  python scripts/dispatch/validate_subspec2_contracts.py
  ```
  **Expected output:**
  ```json
  {
    "C1": {"pass": true, "entries": 344, "cbm_ratio": 0.97},
    "C2": {"pass": true, "errors": 3, "total": 100},
    "C3": {"pass": true, "match_rate": 0.74, "median_diff": 0.21},
    "C4": {"pass": true, "transition_logged": true}
  }
  ```

**Verification command:** 위 명령 + exit code 0.

---

## Task 10: feature_list + Obsidian log + handoff

**Files:**
- 수정: `.claude/feature_list.json`
- 신규/추가: `ClaudeVault/SCM/_AutoResearch/wiki/log.md` (append)
- 신규: `_AutoResearch/SCM/outputs/cbm-backtest-report.md` (Task 9 산출 mirror)

**Scope:** Sub-Spec 2 종료 의식 + 다음 단계(Sub-Spec 3) handoff 정리.

**Dependencies:** Task 9

- [ ] **Step 1: feature_list.json 업데이트**
  ```json
  {"id": "SCM-LANE-SUBSPEC-2", "status": "done", "completed_at": "2026-06-XX",
   "validation": "C1·C2·C3·C4 all pass", "doc": "docs/superpowers/plans/2026-05-27-sub-spec-2-cbm-engine.md"}
  ```

- [ ] **Step 2: Obsidian log 추가**
  `ClaudeVault/SCM/_AutoResearch/wiki/log.md`에 다음 양식 append:
  ```
  ## [2026-06-XX] 완료 | Sub-Spec 2 CBM 추정 엔진
  - C1 344 entries / C2 97/100 / C3 매칭률 74% / C4 transition OK
  - 다음: Sub-Spec 3 Wave 추천 엔진 진입
  ```

- [ ] **Step 3: harness-validator 호출 + 코드 리뷰**
  - `feature-dev:code-reviewer` Agent 호출 — `harness/dispatch/cbm_estimator.py`, `harness/dispatch/product_loader.py`, `harness/dispatch/audit.py` 검토
  - `harness-validator` Agent 호출 — Karpathy 원칙·시크릿·파괴 작업 점검

- [ ] **Step 4: 사용자 검토 후 batch git commit (사용자 직접 수행)**
  Plan owner가 검토 후 commit. *본 plan은 commit 권한 없음.*

- [ ] **Step 5: Sub-Spec 3 handoff 노트**
  Sub-Spec 3 진입 시 필요한 의존성 명시:
  - `harness.dispatch.cbm_estimator.estimate_shipment_cbm` 호출 가능
  - Shipment 3 신규 필드 사용 가능
  - Product 캐시 공유 (`harness.dispatch.product_loader.load`)
  - Polling 인프라 standalone → Sub-Spec 4에서 통합

**Verification command:**
```bash
cat .claude/feature_list.json | python -c "import json, sys; data = json.load(sys.stdin); s = [x for x in data if x.get('id') == 'SCM-LANE-SUBSPEC-2']; print(s)"
```

---

## Risks (Implementation 단계)

| # | 리스크 | 영향 | 완화 |
|---|-------|------|------|
| I1 | Golden 100-sample 사용자 답안 작성 시간 | 🟡 Med | Task 6.2 manual step — 1~2h 예상, 한 번만 하면 됨 |
| I2 | Backtest 1,640건 fetch 시 Airtable rate limit | 🟢 Low | pagination + `time.sleep(0.2)` (`cbm_calc.load_product_lookup` 패턴 동일) |
| I3 | `parse_product_lines_v2`가 기존 `_parse_v1`을 호출하므로 회귀 위험 | 🟢 Low | `tests/settlement/` 기존 회귀 통과 확인 (Task 4) |
| I4 | Polling 첫 회 snapshot 부재 → 모든 shipment를 `new` 취급 | 🟢 Low | `cbm_last_snapshot.json` 부재 시 `previous = {}` → 첫 회는 *현재 상태만 기록* |
| I5 | Shipment 3 신규 필드 추가가 기존 view·formula에 영향 | 🟡 Med | Task 0 백업 + Task 1 후 view 확인 |
| I6 | `harness/dispatch/__init__.py` 미존재 (Sub-Spec 1 미완료) | 🔴 High | **Sub-Spec 1 commit 0363050 실행 완료** *필수 전제*. 미완료 시 Task 2 진입 X |

---

## Out of Scope (이 plan 범위 외)

- LLM 기반 품목 추출 (design doc §7)
- Airtable webhook
- Product 마스터 자동 등록
- 분할 배송 단위 CBM (Sub-Spec 3 wave 단위)
- Sub-Spec 3 호출자 측 통합 (별도 plan)
- `harness/settlement/cbm_calc.py` 리네이밍·이동 (Karpathy Surgical Changes)

---

## 관련 문서

- Design doc (this spec): `_AutoResearch/SCM/outputs/2026-05-27-sub-spec-2-cbm-engine-design.md`
- Master Roadmap: `docs/superpowers/plans/2026-05-27-lane-strategy-master-roadmap-v3.md`
- Sub-Spec 1 plan: `docs/superpowers/plans/2026-05-27-sub-spec-1-resource-mapping-ssot.md`
- Backtest: `_AutoResearch/SCM/outputs/2026-05-27-lane-strategy-backtest-2026.md`
- 재사용 코드: `harness/settlement/cbm_calc.py`
- 기존 backfill 참고: `scripts/backfill/backfill_total_cbm_safe.py`

---

> **시작 trigger:** Sub-Spec 1 commit 0363050 실행 완료 + Plan owner 승인 → Task 0 진입.
> **예상 종료:** Task 0~10 순차 완료 후 *사용자 batch git commit*.
