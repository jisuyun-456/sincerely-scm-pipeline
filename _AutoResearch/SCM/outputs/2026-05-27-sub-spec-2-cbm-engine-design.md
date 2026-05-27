# Sub-Spec 2 — CBM 추정 엔진 Design Doc

> 작성일: 2026-05-27 | 작성자: Claude (chain `lane-strategy-v3` P2 brainstorm+design)
> 모체: `docs/superpowers/plans/2026-05-27-lane-strategy-master-roadmap-v3.md` §2 Sub-Spec 2
> 의존: Sub-Spec 1 (`resource_loader.load_drivers()` — Plan v2 commit 0363050 완료 후 가용)
> Implementation plan: `docs/superpowers/plans/2026-05-27-sub-spec-2-cbm-engine.md`

---

## 1. Context

### 1.1 왜 CBM 추정 엔진인가

Backtest (2026-05-27, 26년 출하 1,640건 sample 100건)에서 `Total_CBM` NULL 비율 **44%** 확인 — Wave 추천 엔진(Sub-Spec 3)이 *차량 적재량 기반 그룹화*를 하려면 CBM이 필수이지만, **거의 절반의 shipment에 CBM 값이 없다**. 한편 동일 sample에서 `Product` 테이블(344 records, `tblBNh6oGDlTKGrdQ`)은 박스 사이즈·박스당 제품수·박스 당 CBM이 80%+ 완비되어 있어 *품목명 매칭으로 사전 추정 가능*.

또한 사용자 운영 모델 (2026-05-27 brainstorm)에서 *임가공 협력사*가 박스 패킹 후 *실측 CBM*을 `Total_CBM`에 입력하는 시점이 D-1~D-0이라, 그 *이전*에 wave 추천하려면 **사전 추정 → 실측 update 시 재계산** 2단계가 필요.

### 1.2 P0 backtest 결과 요약

| 지표 | 값 | 시사점 |
|------|---|------|
| Total_CBM NULL 비율 | 44% (44/100) | 사전 추정 *필수* |
| 출하 품목 텍스트 완비 | 100% | 매칭 입력으로 충분 |
| Product 테이블 records | 344 | 캐시 메모리 사용 가능 |
| 기존 `cbm_calc.py` 활용 가능 함수 | 4개 (`parse_product_lines`, `match_product`, `load_product_lookup`, `calc_from_products`) | *재구현 불필요* |
| 임가공 케이스 비율 (추정) | ~30~40% | 시점 분기 의미 있음 |

### 1.3 SAP 글로벌 표준 vs 신시어리

SAP TM에서 *Shipment* CBM 산출은 *Master Material Volume × Quantity*로 100% deterministic이며 NULL 없음. 신시어리는 *프로젝트형 굿즈 + 임가공*이라 SKU 자동 등록이 100% 안 되므로, Product 매칭률 ≥ 70% + 임가공 후 실측 보정의 hybrid 모델이 합리적 (Master Roadmap §3 자동화 한계 §1.2).

---

## 2. Schema Mapping

### 2.1 Product 테이블 필드 (tblBNh6oGDlTKGrdQ, TMS base)

| 필드 ID | 필드 이름 | 타입 | 사용 목적 |
|---------|---------|------|---------|
| `fldx01uKEnCd0J0nP` | Name (primary) | text | 매칭 키 (Jaccard) |
| `fldtpUf2UVooLcxwd` | 견적코드 | text | 보조 매칭 키 (exact) |
| `fldqGM1lw2TUpZdKW` | 박스명칭 | singleSelect | 박스 타입 (극소형~특대형) |
| `fldENIdfxbVn8YnPI` | 박스당 제품수 | number | `n_boxes = ceil(qty / qty_per_box)` |
| `fldSBWylTZwGf1aEh` | 박스 당 CBM | formula | 박스당 m³ — formula NULL 시 `BOX_TYPE_TO_CBM_M3` fallback |

### 2.2 Shipment 테이블 입력 필드 (tbllg1JoHclGYer7m, TMS base)

| 필드 ID | 필드 이름 | 타입 | 사용 시점 |
|---------|---------|------|---------|
| `fldgSupj5XLjJXYQo` | 최종 출하 품목 | formula | **임가공 전** — 매칭 텍스트 입력 |
| `fldXXnGOXkm90snKn` | 최종 출고 품목 및 수량 | formula | **임가공 후** — 매칭 텍스트 입력 |
| `fldJ9DHjwoRyeUEqE` | Total_CBM | number | 임가공 후 실측 (정답 / confidence=1.0) |
| `fldQvmEwwzvQW95h9` | 출하확정일 | date | 7일 rolling 필터 |
| `fldBUwhBlhOMsJZdv` | SC_id | text | shipment 식별자 |

### 2.3 Shipment 신규 필드 3개 (Sub-Spec 2가 추가)

| 필드 이름 (제안) | 타입 | 설명 |
|---------------|------|------|
| `estimated_cbm` | number (precision 4) | 추정 CBM (m³). 임가공 후엔 Total_CBM과 일치. |
| `estimation_confidence` | number (precision 2, 0~1) | 매칭 라인 비율. 0.7 미만 = "needs review" flag. 실측 완료 = 1.0. |
| `estimation_updated_at` | lastModifiedTime + formula | 마지막 갱신 timestamp (감사용) |

(참고: 기존 `Total_CBM`은 *실측 입력 전용 — 자동 갱신 X*. 추정값은 별도 컬럼에 분리하여 immutable ledger 원칙 준수.)

---

## 3. Algorithm

### 3.1 Pseudocode

```python
def estimate_shipment_cbm(shipment, product_cache):
    """
    Returns (estimated_cbm: float, confidence: float, mode: str)
    mode ∈ {"실측", "임가공_후_추정", "임가공_전_추정", "no_match"}
    """
    # 1. 시점 분기
    total_cbm = shipment.get("Total_CBM")
    if total_cbm and float(total_cbm) > 0:
        return float(total_cbm), 1.0, "실측"

    if shipment.get("최종 출고 품목 및 수량"):
        text = shipment["최종 출고 품목 및 수량"]
        mode = "임가공_후_추정"
    else:
        text = shipment.get("최종 출하 품목", "")
        mode = "임가공_전_추정"

    # 2. 텍스트 파싱
    lines = parse_product_lines_v2(text)   # confidence 추정 위해 v2로 확장
    if not lines:
        return 0.0, 0.0, "no_match"

    # 3. 라인별 매칭 → CBM 합산
    total_cbm = 0.0
    matched_scores = []
    for name, qty in lines:
        key, entry, score = match_product(name, product_cache)
        if entry is None or qty == 0:
            matched_scores.append(0.0)
            continue
        n_boxes = math.ceil(qty / entry["qty_per_box"])
        total_cbm += n_boxes * entry["cbm_per_box"]
        matched_scores.append(score)

    # 4. confidence = sum(score≥0.4) / len(lines)
    matched_count = sum(1 for s in matched_scores if s >= 0.4)
    confidence = matched_count / len(lines)

    return round(total_cbm, 4), round(confidence, 2), mode
```

### 3.2 Branching Detail (임가공 전·후)

```
시작
  │
  ├── Total_CBM > 0 ? ──Yes─→ ("실측", confidence=1.0)
  │
  No
  │
  ├── 최종 출고 품목 및 수량 NOT NULL ? ──Yes─→ parse + match
  │                                              ("임가공_후_추정")
  │
  No
  │
  └── 최종 출하 품목 → parse + match ("임가공_전_추정")
```

### 3.3 Re-compute Trigger (임가공 완료 감지)

Polling cron (Sub-Spec 4와 공유, 3x/day 09·14·17시 KST)에서:
1. 직전 snapshot vs 현재 `Total_CBM` diff 감지
2. `Total_CBM`이 `NULL → number` 또는 `0 → > 0` 전이된 shipment 추출
3. `estimate_shipment_cbm()` 재실행 → `estimated_cbm` = `Total_CBM`, `confidence` = 1.0 update
4. Audit log에 기록: `shipment_id, previous_estimate, actual, diff, diff_ratio`

---

## 4. Decisions (Q1~Q7) — Defaults per chain handoff

### Q1: 수량 표현 정규식 확장 범위

**Decision:** 다음 패턴 모두 수용 (case-insensitive, optional whitespace):
- `×40`, `x40`, `X40`, `*40` (기존)
- `40개`, `40 개`
- `40set`, `40 SET`
- `40박스`, `40 박스`
- `40 EA`, `40ea`, `40 EA.`
- 단순 trailing number `상품명 40` (fallback, 기존)

거부: `40여분` 단독 (Q2 분기로 처리), `여분 50` (단독)

**Rationale:** Sample shipment 텍스트(`최종 출하 품목`) 표기 다양성을 backtest에서 관찰. `×`가 표준이지만 `개`·`set`·`박스`·`EA`도 빈번. 정규식 1줄로 확장 가능. `여분`은 별도 의미(잉여분)라 Q2 분기.

### Q2: "여분 포함" 처리

**Decision:** 본수량 + 여분을 합산해 CBM 계산. `extra` 메타데이터에도 별도 보관.

수용 패턴:
- `상품명 100+여분 5` → `(quantity=105, extra=5)`
- `상품명 100+2` → `(quantity=102, extra=2)` (단, 두 번째 숫자 ≤ 첫 번째 ×0.2 일 때만 여분 해석. 아니면 무시)
- `상품명 100 (여분 5)` → `(quantity=105, extra=5)`
- `여분 포함 5 상품명 100` → `(quantity=105, extra=5)` — *prefix 여분*

`extra`는 `matched_list[i]["extra"]`에 기록. CBM은 합산값으로 계산.

**Rationale:** 사용자 운영 현실에서 여분은 *실제 출고 박스에 포함*되므로 CBM에 반영해야 함. 다만 메타 보관으로 디버깅 가능. 두 번째 숫자 20% 휴리스틱은 `2+2` 같은 모호 케이스 false positive 방지.

### Q3: 단품 vs 키트 감지

**Decision:** Product.Name 접미사 `(키트)` 존재 여부로 detect. 별도 신규 필드 X.

```python
def is_kit(product_name: str) -> bool:
    return product_name.strip().endswith("(키트)") or "(키트)" in product_name
```

키트는 *여러 sub-품목 묶음*이라 박스당 제품수가 *1 키트 단위*. 알고리즘 영향 없음 (`qty=수령자수`, `qty_per_box=1키트`로 자연스럽게 작동).

**Rationale:** 현재 Product 테이블 344 records에서 `(키트)` 접미사가 명시적 컨벤션. 신규 field 추가는 over-engineering — backtest sample에서 `(키트)` 접미사 누락 케이스 미발견. **Upgrade path:** 향후 키트 변형이 늘면 `Product.kit_type` singleSelect (단품/키트/리필키트) 추가.

### Q4: Confidence 임계값

**Decision:**
- 라인 매칭 임계: **Jaccard ≥ 0.4** ("matched"로 카운트). 기존 `cbm_calc.match_product()`와 동일.
- Overall confidence: `(매칭 라인 수) / (전체 라인 수)` (수량 0 라인 제외)
- **"needs review" threshold: overall < 0.7** → Slack 알림 + Shipment에 flag
- **"자동 wave 차단" threshold: overall < 0.5** → Sub-Spec 3에서 자동 wave 제외, 사용자 수동 처리

**Rationale:** 기존 `cbm_calc.py`가 이미 0.4 임계 사용 — 일관성 유지. Master Roadmap §2 C3 (매칭률 ≥ 70%)에 맞춰 0.7을 "정상" 라인. 0.5 미만은 매칭 실패가 절반 이상이라 추정 신뢰도 부족.

### Q5: 임가공 후 재계산 Trigger

**Decision:** Sub-Spec 4 polling (3x/day, 09·14·17시 KST)이 `Total_CBM` diff 감지 → 재계산. **Webhook X.**

알고리즘:
```
매 polling iteration:
  current = fetch_shipments(filter=auto_targets)
  previous = load_snapshot("cbm_last.json")
  for sh in current:
    if sh.Total_CBM != previous.get(sh.id, {}).get("Total_CBM"):
      # transition NULL→value 또는 value→다른 value
      estimate_shipment_cbm(sh, cache)
      audit_log.append(...)
  save_snapshot(current, "cbm_last.json")
```

**Rationale:** Airtable webhook은 Pro plan 이상 + 안정성 이슈. 3x/day로 임가공 후 ~5시간 내 반영 충분 (D-1 출고에는 D-1 09시 polling이 잡음). Master Roadmap §7 Out of Scope에 webhook 명시.

### Q6: 추정 vs 실측 이상값 탐지

**Decision:** 다음 조건 모두 충족 시 audit log + Slack 알림:
- `abs(estimated_cbm − actual_cbm) / actual_cbm > 0.5` (50% 이상 편차)
- `actual_cbm > 0.1` (m³) — 미미한 케이스 false positive 회피

기록 위치: `audit_log` 테이블 (신규 — Task 8에서 생성) 또는 `_AutoResearch/SCM/outputs/cbm-anomaly-{YYYYMM}.log`.

기록 필드: `timestamp, sc_id, estimated, actual, diff, diff_ratio, mode (전/후), 매칭 라인 dump`

**자동 보정 X — 사람 검토 후 알고리즘 개선 입력.**

**Rationale:** 50% 편차는 명백한 매칭 실패 (예: 키트 매칭 오류·신제품 누락). 자동 보정하면 *bias 누적 + 디버깅 불가*. 사람 검토로 알고리즘 개선 cycle 유지.

### Q7: Product 테이블 캐시 동기화 주기

**Decision:**
- 일 1회 06:00 KST refresh (cron — GitHub Actions 또는 Sub-Spec 4 polling 첫 회 piggyback)
- In-memory dict, TTL 24h
- Stale-while-revalidate: TTL 초과해도 fetch 실패 시 기존 캐시 사용 + 경고 로그
- 강제 refresh API: `product_loader.invalidate_cache()` (테스트/긴급용)

**Rationale:** Product 테이블 변경 빈도가 낮음 (월 ~5건 신제품 등록). 일 1회로 충분. polling startup 시 piggyback하면 별도 cron 불요. Stale-while-revalidate로 Airtable 장애 시도 운영 지속.

---

## 5. Validation Contract C1~C4 (정확 정의)

### C1: Product 캐시 적재 정확성

**Definition:** `product_loader.load()` 호출 시 Product 테이블 전체 records가 캐시에 적재되며, NULL 박스 사이즈는 `BOX_TYPE_TO_CBM_M3` fallback 적용.

**Pass criteria (quantitative):**
- `len(product_cache.entries) ≥ 327` AND `≤ 361` (344 ± 5% 허용 — 신규 등록·deprecated 대응)
- `cbm_per_box > 0` 라벨된 entry 비율 ≥ 95% (`BOX_TYPE_TO_CBM_M3` fallback 포함)
- name·code 양쪽 lookup 모두 작동: `lookup["굿이너프 비치타월".lower()]` 와 `lookup["견적코드"]` 동시 조회 가능

**Verification command:** `python tests/dispatch/test_product_loader.py::test_load_full_count` (Task 5)

**Failure mode:**
- < 327: Airtable 권한·rate limit 점검 → schema_pin 동기화
- cbm_per_box=0 비율 > 5%: 박스명칭 NULL records 식별 → 수동 입력 요청

### C2: parse_product_lines() 정확도

**Definition:** Golden 100-sample (실제 Shipment `최종 출하 품목` 문자열) 입력 시 추출된 `(품목명, 수량)` 튜플의 *수량 정확도* ≥ 95%.

**Pass criteria (quantitative):**
- Golden 100건 중 수량 추출 오류 < 5건 (5% 이하)
- 수량 추출 오류 = (추출 수량 ≠ 정답 수량) OR (라인 수 불일치)
- 품목명 *추출* 정확도는 별도 측정 X (Jaccard 매칭이 cover)

**Verification command:** `pytest tests/dispatch/test_cbm_estimator.py::test_parse_golden_100` (Task 6)

**Failure mode:**
- 오류 > 5건: 실패 케이스 분석 → 정규식 패턴 추가 → 재테스트
- Golden set 자체 오류: `_AutoResearch/SCM/outputs/cbm-golden-set-2026-05-27.yaml` 사용자 검토

### C3: 전체 매칭률

**Definition:** Backtest 1,640건 (또는 가용 sample 300+건) 입력 시 *라인 단위* Jaccard ≥ 0.4 비율.

**Pass criteria (quantitative):**
- 라인 단위 매칭률 ≥ **70%** (정답 라인이 Product table에 존재한다는 가정)
- Shipment 단위 confidence ≥ 0.7 비율 ≥ 60%
- Total_CBM 보유 케이스 비교: |estimated - actual| / actual 의 median < 30%

**Verification command:** `python harness/dispatch/cbm_estimator.py --backtest --since 2026-01-01`

**Failure mode:**
- 매칭률 < 70%: 미매칭 품목 dump → Product 테이블 등록 보완 또는 token 정규화 강화
- 50% 미만: **Kill criteria** 발동 → 자동 추정 비활성화, 사용자 수동 입력만 운영 (Master Roadmap §2 Kill Criteria 일치)

### C4: 임가공 trigger 재계산

**Definition:** `Total_CBM` 값이 NULL→number 또는 number→다른 number로 변경되면 다음 polling cycle(최대 5시간 후) 안에 `estimated_cbm`이 `Total_CBM`과 일치하고 `estimation_confidence = 1.0`.

**Pass criteria (quantitative):**
- 테스트: shipment 1건 `Total_CBM` 수동 변경 → 다음 polling 후 `estimated_cbm == Total_CBM` 검증
- Audit log에 transition 기록 1건 확인
- 시간 차: 변경 시점 ~ 반영 시점 ≤ 5h (다음 polling cycle 도달 시간)

**Verification command:** `python tests/dispatch/test_cbm_estimator.py::test_repolling_trigger` + 수동 E2E (Task 9 self-check)

**Failure mode:**
- 미반영: polling cron 로그 확인 → snapshot 파일 권한·경로 점검
- 시간 초과: polling 빈도 증가 또는 webhook 검토 (Out of Scope이지만 escalation)

---

## 6. Risks

| # | 리스크 | 영향도 | 완화 방안 |
|---|-------|------|---------|
| R1 | Product 매칭률 < 70% (Kill criteria) | 🔴 High | 미매칭 dump 분석 → Product 등록 보완. 못 보완 시 자동 추정 비활성화 + 사용자 수동 입력 운영 |
| R2 | 키트 변형 (`(키트)` 누락된 신제품) | 🟡 Med | Audit log monitor → 월 1회 사용자 검토 → 필요 시 Q3 upgrade path 발동 |
| R3 | Airtable rate limit (Product fetch 매번) | 🟢 Low | In-memory cache + 24h TTL (Q7). Stale-while-revalidate fallback |
| R4 | 캐시 staleness (신제품 등록 미반영) | 🟢 Low | 일 1회 refresh + 강제 invalidate API |
| R5 | `최종 출고 품목 및 수량` 필드가 일부 shipment에서 빈 채로 임가공 후도 그대로 | 🟡 Med | fallback 순서: 출고 → 출하 → 둘 다 NULL이면 confidence=0.0 |
| R6 | 임가공 후 `Total_CBM` 입력 누락 (운영팀 휴먼 에러) | 🟡 Med | Sub-Spec 4 polling alarm: D-0 출고 + Total_CBM NULL 케이스 Slack 알림 |
| R7 | Polling 실패 시 임가공 후 confidence가 영구히 낮은 채로 유지 | 🟢 Low | Polling 성공 로그 monitor + 24h 미실행 alarm |

---

## 7. Out of Scope (v3 범위 외)

- **LLM 기반 품목 추출** — 정규식 + Jaccard로 70%+ 달성 가능 시 LLM 도입 over-engineering. 50% 미만일 때 재검토.
- **Airtable webhook trigger** — Pro plan 필요. polling 3x/day로 충분 (Master Roadmap §7).
- **Product 마스터 자동 등록** — 미매칭 품목 자동 등록은 *데이터 품질 sanitize 없이 노이즈 누적*. 사용자 수동 등록 유지.
- **CBM 시계열 학습** — 매칭률·이상값을 ML로 보정하는 모델. 현재는 rule-based + audit log로 사람 검토 cycle.
- **분할 배송 그룹 단위 CBM 추정** — Sub-Spec 3 wave 단위. 본 spec은 *shipment 단위*만.

---

## 8. 기존 `cbm_calc.py` 재사용 vs 마이그레이션

기존 코드 `harness/settlement/cbm_calc.py` (244 lines)에서 4개 핵심 함수가 이미 운영 검증됨:

| 함수 | Sub-Spec 2에서 처리 | 사유 |
|------|------------------|------|
| `load_product_lookup(headers)` | **import + thin wrapper** (`product_loader.load()`) | 이미 검증, fallback dict 포함. wrapper로 캐시·TTL 추가만. |
| `_tokenize(text)`, `_jaccard(a,b)` | **import as-is** (private이지만 안정) | 한국어-Latin 경계 처리 검증 완료 |
| `match_product(name, lookup)` | **import as-is** | exact + Jaccard ≥ 0.4 동일 정책 (Q4) |
| `parse_product_lines(text)` | **wrapper + 확장** (`parse_product_lines_v2`) | Q1 정규식 확장 + Q2 여분 처리 추가 필요. 기존 함수는 fallback chain의 첫 단계로 호출. |
| `calc_from_products(text, lookup, qty_hint)` | **참고만, 호출 X** | 상하차비용 계산 포함 — Sub-Spec 2는 CBM만 필요. 별도 함수 `estimate_shipment_cbm()`로 분리. |
| `load_product_lookup` 내 `BOX_TYPE_TO_CBM_M3` fallback | **import + 활용** | NULL 박스사이즈 → 박스명칭 → fallback m³ 동일 |

**Import 경로:** `from harness.settlement.cbm_calc import load_product_lookup, match_product, parse_product_lines, _tokenize, _jaccard`

**마이그레이션 X 사유:** 기존 `cbm_calc.py`는 `tms_settlement` 정산 파이프라인(`harness/tms_settlement/calc.py`, `scripts/backfill/backfill_total_cbm_safe.py` 등)에서도 사용 중. 이동/리네이밍은 *Sub-Spec 2 범위 외 refactor*이며 Karpathy "Surgical Changes" 원칙 위배. **재사용 import only.**

---

## 9. Dependencies on Sub-Spec 1

- `harness/dispatch/resource_loader.py` (Plan v2 commit 0363050)
  - `load_drivers()` — Sub-Spec 3 wave 추천에서 필요. Sub-Spec 2 자체는 driver 정보 미사용.
- `harness/dispatch/__init__.py` — Plan v2 Task에서 생성됨. Sub-Spec 2도 같은 패키지에 추가.

**Sub-Spec 2가 Sub-Spec 1 *완료 전*에 시작 가능한가?** 부분적으로 가능 (driver 매핑 미사용). 단, Master Roadmap §1에서 *순차 진행* 권고 — Sub-Spec 1 완료 후 진입.

---

## 10. 관련 문서

- Master Roadmap v3: `docs/superpowers/plans/2026-05-27-lane-strategy-master-roadmap-v3.md`
- Sub-Spec 1 plan v2: `docs/superpowers/plans/2026-05-27-sub-spec-1-resource-mapping-ssot.md`
- Backtest: `_AutoResearch/SCM/outputs/2026-05-27-lane-strategy-backtest-2026.md`
- Design doc 모체: `_AutoResearch/SCM/outputs/2026-05-27-driver-lane-consolidation-strategy.md`
- Implementation plan (this spec): `docs/superpowers/plans/2026-05-27-sub-spec-2-cbm-engine.md`
- 기존 CBM 코드: `harness/settlement/cbm_calc.py` (재사용 대상)
- 기존 backfill 참고: `scripts/backfill/backfill_total_cbm_safe.py` (Total_CBM 백필 패턴)

---

> **다음 단계:** 본 design을 사용자 검토 → `docs/superpowers/plans/2026-05-27-sub-spec-2-cbm-engine.md` 11 Task 실행 (Sub-Spec 1 완료 후).
