# 출하 CBM — 정산 파서 통일 + 매칭 정규화 재시도 (설계)

- **일자**: 2026-08-11
- **Chain**: bridge-cbm-ssot (P1, 재설정)
- **선행**: `2026-08-11-wms-itemmaster-upsert-refresh-design.md` (⛔ SUPERSEDED — 전제 반증)
- **선행 커밋**: 8409485·802f8cc (Product 백필·dedup·`match_product` 공백무시 매칭) @ `feat/weekly-report-archive`

## 1. 목표 (Goal)

**출하 CBM 산출 가능 라인 비율을 14.5% → 61.5%로 올린다** (실측 19,547 라인 기준 +9,298 라인).

수단은 신규 로직이 아니라 **이미 존재하고 테스트된 자산의 연결**이다:
1. 정산 경로가 구형 파서(v1)를 쓰고 있어 수량을 77% 유실 → 이미 있는 `parse_product_lines_v2`로 통일.
2. 공유 리졸버의 이름 폴백에 `normalize_goods` 재시도가 없음 → `crosswalk.py:19`에 이미 있는 패턴 이식.

## 2. 근거 — 실측 (TMS Shipment 전수 12,282건 / 19,547 품목 라인)

`파서 × 리졸버` 조합별 측정. **CBM-able** = 매칭 성공 ∧ 수량>0 ∧ 박스 CBM 보유 —
셋 다 있어야 실제로 CBM이 산출되므로, 이것이 움직여야 할 지표다.

| 조합 | 매칭률 | 수량 파싱 | **CBM-able** |
|---|---|---|---|
| v1 + `resolve_product_entry` — **현행 정산** | 30.8% | 22.9% | **14.5%** (2,828) |
| v1 + resolve + normalize | 34.8% | 22.9% | 16.8% |
| v2 + bare `match_product` — **현행 배차 추정** | 61.0% | 81.0% | 57.5% |
| v2 + `resolve_product_entry` | 61.3% | 81.0% | 57.8% |
| **v2 + resolve + normalize** — 목표 | **65.2%** | **81.0%** | **61.5%** (12,126) |

**지배적 레버는 파서다(+43.3pp).** v1 `parse_product_lines`의 수량 정규식
(`\s+(\d+)\s*$`)이 한국식 보너스 표기 `100+1`을 못 잡는다 — `1` 앞이 공백이 아니라 `+`이므로
매칭 실패 → 수량 0 ∧ 품목명에 ` 100+1`이 남아 매칭까지 동시 실패. 실측 5,583 라인.
수량 0은 `calc_from_products`에서 `n_boxes = 1`로 처리되어 **CBM을 대폭 과소계상**한다.

`normalize_goods` 재시도는 그 위에 +3.7pp를 더한다 (`데일리짐색(단품)`→`데일리 짐색`[DLYG] 류 784 라인).

**두 경로의 결함이 상보적**이라는 것이 핵심 발견:

| 경로 | 파서 | 리졸버 |
|---|---|---|
| 정산 `calc_from_products` | v1 ❌ | `resolve_product_entry` ✅ (코드→alias→name2code→jaccard) |
| 배차 `estimate_shipment_cbm` | v2 ✅ | bare `match_product` ❌ (alias·name2code 없음) |

어느 쪽도 둘 다 갖고 있지 않다. 양쪽을 최선 조합으로 수렴시킨다.

## 3. 비목표 (Non-Goals)

- **`WMS_ItemMaster` 재적재** — 소비처가 PT행만 읽으므로 굿즈행 갱신은 무효과. 폐기(선행 설계 참조).
- **`parse_product_lines_v2` 로직 개선** — 이미 테스트된 자산을 *연결*만 한다. 신규 파싱 규칙 추가 금지.
- **Product 마스터 정리**(FGPS·dup/junk) — chain P2.
- **잔여 hard-unmatched 해소** — `프리미엄스트링후드집업(F`(93건, `/` 분할로 괄호 절단),
  `잔여분(...)`, `펜1` 등은 Product 마스터 부재 또는 원천 텍스트 품질 문제. 별도 진단 과제.
- **v1 `parse_product_lines` 삭제** — 외부 호출자 존재 가능. 남겨두되 정산에서만 v2로 전환.

## 4. 아키텍처

신규 파일 없음. 기존 3개 함수만 수정한다.

**A. `harness/settlement/cbm_calc.py::calc_from_products`** — 파서 교체
- `parse_product_lines(text)` → `parse_product_lines_v2(text)` (2-tuple → 3-tuple 언패킹)
- `qty_hint` 폴백 조건(`all(q == 0 ...)`)은 v2 하에서 발동 빈도가 급감하나 **의미는 동일하게 보존**.
- 순환 import 주의: `cbm_calc`(settlement) ← `cbm_estimator`(dispatch)는 이미
  `cbm_estimator`가 `cbm_calc.match_product`를 import 중 → **함수 내부 지연 import**로 해소
  (`product_alias.resolve_product_entry`가 이미 쓰는 기존 패턴과 동일).

**B. `harness/backbone/product_alias.py::resolve_product_entry`** — 3단(이름 Jaccard 폴백)에 정규화 재시도 추가
- 현행 3단: `match_product(name, lookup)` 실패 시 종료.
- 변경: 실패 시 `normalize_goods(name)`으로 ① name2code 재조회 ② Jaccard 재시도.
  `crosswalk.py:17-19`의 검증된 패턴과 동일.
- `method` 반환값에 `'name2code_norm'` / `'jaccard_norm'` 추가 — 관측 가능성 유지(어떤 경로로
  해소됐는지 정산 리포트에서 구분 가능해야 함).

**C. `harness/dispatch/cbm_estimator.py::estimate_shipment_cbm`** — 리졸버 교체
- `match_product(name, lookup)` → `resolve_product_entry(name, None, name2code, lookup)`.
- `name2code`는 선택 인자로 주입(기본 `None` → 현행 동작 보존, 하위호환).
- `score` 기반 confidence 계산 유지: 리졸버는 score를 반환하지 않으므로
  `method`→score 매핑(`code`/`name2code`=1.0, `jaccard`계열은 `match_product` score)으로 보존.

## 5. 데이터 흐름 (정산 1건)

```
Shipment 텍스트 "프라임폴더블멀티충전기 50+1, 데일리짐색(단품) 120+2"
        │
        ├─ v1(현행): [("프라임폴더블멀티충전기 50+1", 0), ("데일리짐색(단품) 120+2", 0)]
        │             → 매칭 실패 ×2, 수량 0 → n_boxes=1 → CBM 과소
        │
        └─ v2(변경): [("프라임폴더블멀티충전기", 51, 1), ("데일리짐색(단품)", 122, 2)]
                      → ①번 매칭 성공 / ②번은 normalize 재시도로 "데일리 짐색"[DLYG] 해소
                      → 정확한 n_boxes → CBM·상하차비 정상 산출
```

## 6. ⚠️ 리스크 — 정산 금액이 바뀐다 (Risk-First)

**이 변경은 운임 정산의 `total_cbm`과 `unload_fee`를 바꾼다.** 방향은 "과소계상 → 정상"이지만
**금액에 영향을 주는 변경이므로 사후 검증 없이 배포하면 안 된다.**

- 수량 0 → 실수량 복원은 `n_boxes = ceil(qty/qty_per_box)`를 1 → N으로 올린다.
  `unload_fee`는 박스 수 기반(`BOX_FEE_RULES`, 상한 50,000원)이므로 **상하차비가 증가하는 방향**.
- 따라서 **dry-run 비교 리포트(변경 전/후 shipment별 CBM·unload_fee delta)를 산출하고,
  사용자가 표본을 확인한 뒤에만 실제 정산에 반영**한다. 자동 반영 금지.
- 정산 원장 자체는 INSERT-only 원칙 유지 — 본 변경은 *계산 로직*이지 기존 기록의 수정이 아니다.
  과거 정산분 소급 정정 여부는 **본 설계 범위 밖**(사용자 판단 사항).

기타 리스크:
- **Jaccard ≥0.4 오매칭** — `normalize_goods`로 후보 공간이 넓어지면 오매칭 여지도 커진다
  (예: `Solid스탠다드G형박스(브랜디드타월2개입)` → `Solid 커스텀 G형박스(S사이즈)` score 0.40).
  → 검증에서 신규 매칭의 score 분포를 출력하고 0.4~0.5 구간을 표본 육안 확인.
- **순환 import** — A의 지연 import로 회피. 스모크 테스트(`tests/test_import_smoke.py`)로 확인.

## 7. 검증 계획

1. **단위 테스트**(신규, TDD): v2 전환 후 `calc_from_products`가 `"티셔츠 100+2"`를 수량 102로
   집계하는지 / `resolve_product_entry`가 `데일리짐색(단품)`을 `normalize` 경로로 해소하는지.
2. **기존 테스트 무회귀**: `tests/settlement/`(3파일)·`tests/dispatch/`·`tests/backbone/` 전체 green.
   특히 `test_calc_from_products_resolver.py::test_without_name2code_preserves_current_jaccard_miss`는
   `normalize_goods("데스크테리어 매트")`가 불변이므로 계속 green이어야 한다.
3. **전수 재측정**: 본 설계 §2 표를 재생성해 CBM-able 14.5% → 61.5% 도달 확인.
4. **금액 delta 리포트**: shipment별 `total_cbm`·`unload_fee` 변경 전/후 비교표 산출 →
   상위 20건 + score 0.4~0.5 신규매칭 표본을 사용자 확인.

## 8. 롤백

3개 함수 수정 모두 순수 로직 변경이며 **Airtable 쓰기가 없다** → `git revert` 한 번으로 원복.
운영 데이터 변경분이 없으므로 데이터 롤백 절차 불필요.
