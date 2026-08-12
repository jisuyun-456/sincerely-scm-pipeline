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
- 변경: 실패 시 `normalize_goods(name)`으로 **Jaccard만** 재시도. `crosswalk.py:17-19`와 동일 패턴.
- `method` 반환값에 `'jaccard_norm'` 추가 — 어떤 경로로 해소됐는지 정산 리포트에서 구분 가능해야 함.
- ⚠️ **2단(name2code)은 재시도 대상이 아니다** — `product_alias.py:157`이 이미
  `c = name2code.get(normalize_goods(name))`로 *정규화한 키*를 조회한다. 실측 확인:
  `resolve_product_entry("데일리짐색(단품)", None, {"데일리짐색":"DLYG"}, lookup)`은
  **현행 코드에서 이미** `('DLYG', 'name2code')`를 반환한다. 2단 재시도 블록을 추가하면
  동일 키·동일 가드의 도달 불가 死코드가 된다.

**C. 배차 `estimate_shipment_cbm` 리졸버 교체 — 본 설계에서 제외(후속 과제)**
배차 경로도 공유 리졸버로 바꾸면 +4.0pp(57.5%→61.5%)를 얻지만, 다음 이유로 **분리**한다:
- `wave_recommender.yml` cron(KST 09/14/17)이 `replay_outbound_cbm.py --write`를 돌리고,
  그 안에서 `estimate_shipment_cbm` 결과가 `fuzzy_write_decision` 게이트(0.7 PATCH / 0.8 자동배차)를
  거쳐 **`estimated_cbm`·`estimation_confidence`로 자동 PATCH**된다.
- 리졸버 교체는 기존에 미매칭이던 라인을 코드·alias 경로로 해소시켜 **confidence를 올린다** →
  자동배차 밴드 진입 여부가 바뀔 수 있다. `name2code=None` 기본값으로도 동작이 달라지므로
  "하위호환"이라 부를 수 없다.
- 즉 별도의 confidence-band delta 계측과 사용자 게이트가 필요하며, 이는 본 설계의
  정산 스코프와 검증 축이 다르다. → 별도 spec/plan으로 분리.

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

## 6. ⚠️ 리스크 — 기사님 운임이 자동으로 바뀐다 (Risk-First)

**이 변경은 운임 정산의 `unload_fee`를 바꾸고, 그 값은 cron이 자동으로 Airtable에 쓴다.**

추적된 경로:
```
calc_from_products(...)["unload_fee"]        harness/tms_settlement/calc.py:241-242
   → cbm_unload → unload = _parse_unload_fee(box_text) or cbm_unload      calc.py:265
   → SettlementItem.unload_calc → _build_patch_fields → client.patch_record()  write.py:130
   → .github/workflows/tms_settlement.yml  cron '0 9 * * *' = 매일 KST 18:00
```
즉 **기사님께 지급되는 상하차비**가 대상이다. 완화 요인은 `calc.py:265`의 `or` — `box_text`
파싱이 0을 낼 때만 `cbm_unload`가 쓰이는 **폴백 경로**라 전량이 아니다. 그래도 자동 지급 금액이다.

- 수량 0 → 실수량 복원은 `n_boxes = ceil(qty/qty_per_box)`를 1 → N으로 올린다.
  `unload_fee`는 박스 수 기반(`BOX_FEE_RULES`, 상한 50,000원)이므로 **상하차비가 증가하는 방향**.
- 따라서 **변경 전/후 비교 리포트를 산출하고 사용자가 표본을 확인한 뒤에만 main에 병합**한다.
  cron은 main에서 돌므로 **feature 브랜치가 안전 경계**다. 병합 = 배포임을 명심.
- 과거 정산분 소급 정정 여부는 **본 설계 범위 밖**(사용자 판단 사항).
- 정산 원장 INSERT-only 원칙과 무관 — 본 변경은 *계산 로직*이지 기존 기록의 수정이 아니다.
- 정산 원장 자체는 INSERT-only 원칙 유지 — 본 변경은 *계산 로직*이지 기존 기록의 수정이 아니다.
  과거 정산분 소급 정정 여부는 **본 설계 범위 밖**(사용자 판단 사항).

기타 리스크:
- **Jaccard ≥0.4 오매칭** — `normalize_goods`로 후보 공간이 넓어지면 오매칭 여지도 커진다
  (예: `Solid스탠다드G형박스(브랜디드타월2개입)` → `Solid 커스텀 G형박스(S사이즈)` score 0.40).
  → 검증에서 신규 매칭의 score 분포를 출력하고 0.4~0.5 구간을 표본 육안 확인.
  ⚠️ `method='jaccard'`는 **exact 히트(score 1.0)에도 붙는다**(`cbm_calc.py:153-157`의 정확·무공백
  alias 경로). `matched[]`에는 score가 없으므로, 위험 구간을 보려면 계측 스크립트가
  `match_product`로 score를 **재계산**해야 한다(굿즈명 단위 캐시 — 동일 이름이 수천 건 반복).
- **순환 import** — A의 지연 import로 회피. 스모크 테스트(`tests/test_import_smoke.py`)로 확인.
- **커버리지 분모 이동** — v1은 19,547 라인, v2는 19,709 라인을 만든다(파서가 분할을 더 잘함).
  따라서 %만 비교하면 안 되고 **CBM-able 절대 건수**(2,828 → 목표 ~12,126)를 주 지표로 삼되
  분모를 함께 표기한다.

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
