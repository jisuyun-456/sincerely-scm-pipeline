# NEST Production Specification API — 읽기 전용 PoC 프로브 리포트

**실행일**: 2026-07-10 22:39 KST · **실행**: `scripts/backbone/nest_probe.py` (읽기 전용 — NEST GET + Airtable GET만, 원격 쓰기 0건) · **호출**: 총 32콜 (샘플 30 + V5 재호출 2), 페이싱 ≤50/min, 429 발생 0건

---

## 결론: **가능 — BOM/CBM cascade 전개 가능 (신규 주문 forward 기준, 크로스워크 매개)**

최근 주문 PNA의 90%가 NEST에서 확정 견적으로 조회되고, 물리 굿즈 기준 NEST goodsCode의 **95.8%가 TMS Product CBM에 도달**(직접 87.5% + 기존 alias 8.3%p)하며, 견적수량과 주문수량의 **median 괴리 0.0%**, 명칭 일치 **100%**, NEST 굿즈→WMS_BOM(굿즈→PT) 연쇄 **90.8%**가 실측됐다. 즉 NEST 스냅샷 하나로 S0(수량)→S1(키)→S5(출하CBM 구조)→S2 진입(BOM 연쇄)이 끊기지 않고 이어진다. 단, NEST에는 CBM·PT 데이터가 없으므로 cascade의 **부피·자재 수치 자체는 여전히 TMS Product·WMS_BOM·ItemMaster가 공급**하고, NEST는 그 연결의 **키 품질·구조·수량 진실**을 제공하는 역할이다 (완결률 9%의 병목인 파츠CBM 미등록은 NEST로 해소 불가 — 치수입력 트랙 병행 필수). 구형 PNA는 `PRIMARY_QUOTE_NOT_FOUND`가 다수라 히스토리 백필용으로는 부적합하며 **forward-only 통합**이 맞다.

---

## 1. V-게이트 실측치

| ID | 질문 | 실측 | 판정 |
|---|---|---|---|
| **V2** 커버리지 | WMS 주문 PNA가 NEST에 존재? | 전체 **80.0%** (24/30) · **최근 20건 90%** · 엣지 10건 60%. 404 내역: `PRIMARY_QUOTE_NOT_FOUND` 5 (전부 PNA515xx 이하 구형) · `PROJECT_NOT_FOUND` 1 (PNA38461) | ✅ 게이트 통과 (경계). **forward-only 전제** |
| **V1** 키 연결 | NEST goodsCode ↔ TMS 견적코드 | 물리 distinct 48종: TMS 직접 등록 **87.5%** (42) · 기존 alias/사이즈 보정 포함 **95.8%** (46) · sync_item 수록 80.3% (전체 61종 기준) | ✅ **≥90% 결정론 밴드** — H1 사실상 참 (NEST→sync→WMS 동일 코드 체계) |
| **V1b** 사이즈옵션 | 사이즈 옵션 → TMS 사이즈 SKU | 사이즈성 옵션 보유 21건 중 **17건(81.0%)** 해소 (예: DRCG+M → SOLB) | ✅ ≥80% — 옵션지문 키 설계 유효 |
| **C-chk** CBM 도달 | NEST goods → TMS Product CBM | 물리 인스턴스 65건: direct 86.2% + alias/size 10.8% = **96.9%** (수량가중 93.4%). 미해소 실물 **2종뿐**: CMWG(Carry me 와인잔)·WSPB(화이트 쇼핑백) | ✅ S5 출하CBM 구조 계산 가능 |
| **B-chk** BOM 연쇄 | NEST 굿즈에 WMS_BOM(굿즈→PT) 존재? | 물리 65건 중 **59건(90.8%)** 모품목 행 존재 → NEST 키트→굿즈→PT 3단 연쇄 성립 | ✅ S2 MRP 진입 가능 |
| **V3** 수량 정합 | 견적수량 vs 주문수량 | 코드 매칭 61쌍 **median Δ 0.0%** · order-only 4코드 · **견적에만 있는 물리 굿즈 0건** (NEST-only 37코드는 전부 서비스 라인) | ✅ 수량 대사 신호로 강력 |
| **V4** 명칭 | goodsName vs WMS 굿즈명 | 물리 65건 **100%** (exact 59 + normalize 6). 서비스 포함 시 64.4% | ✅ sync 유래 확인 — 이름 조인도 가능하나 코드 조인 권장 |
| **V5** 안정성 | instanceId 재호출 안정성 | 2/2 PNA 완전 동일 | ✅ 단기 안정 (설계상은 스냅샷 내부 키 유지 권장) |

**종합 게이트** (V2≥80% AND V1≥50%): **통과** — 상위 밴드(V1 95.8%)로 통과.

## 2. S0~S7 단계별 — NEST가 채우는 것 / 못 채우는 것

| 단계 | NEST가 채움 | NEST가 못 채움 (기존 유지) |
|---|---|---|
| S0 감지 | 수량 진실 교차검증 (견적↔주문 대사) | 주문 감지 자체 (order 미러 유지) |
| S1 키해석 | **goodsCode 결정론 제공** — 53% 텍스트조인 문제의 NEST↔TMS 레그 해소, `product_alias.py` 하드코딩 은퇴 경로 (13개 중 alias 8 + SIZE 4 대체 가능성, TWKF는 Product 등록 전까지 유지) | WMS↔NEST 레그는 sync가 이미 해결 (V4 100%) |
| S2 MRP | 키트 구성·kitQuantity (제작 세트수) | **소요량_개당·PT 전개 — WMS_BOM 그대로** (NEST에 PT 없음) |
| S3 입하CBM·M/H | — | **파츠CBM — ItemMaster/sync_parts 그대로** (완결률 병목 불변) |
| S4 창고투영 | — | 전부 기존 유지 |
| S5 배차/출하CBM | **키트 구성 서버검증 데이터** (8키트/32라인 실측, quantityPerKit 전부 1) + packageGoods 포장굿즈 식별 → kit fallback 보강 | CBM 값 자체는 TMS Product |
| S6 운임 | (부수 발견) 서비스 라인에 배송모드 코드 존재 — GBXS~GBLL(택배 4종)·QKXS~QKLL(퀵 4종) → **견적된 배송모드를 S6 예상운임과 대사 가능성** | 운임 rate 자체 |
| S7 Ledger | 대사 결과 필드 (`NEST_정합성`) 추가 여지 | Ledger 자체는 기존 유지 |

## 2.5 추가 발견 — NEST 마스터 DB에 박스 스펙(CBM 원천) 존재 (사용자 제보, 2026-07-10)

NEST 관리 화면(master-db) 확인 결과, **옵션 레벨**(예: Display 스트랩 박스 > 트레이 박스 > 색상 > 화이트)에 다음 필드가 존재:

- **박스 명칭** (특대형 등 — TMS Product 박스타입 5종과 동일 어휘) · **박스단위(개당)** (예: 0.0625 = 1/16, 개당 박스 점유율로 해석) — **단품/키트 각각 별도 값**
- 최소/최대 주문수량(MOQ)
- NEST가 이 데이터로 **견적 시점에 배차 차량 산정**을 수행 중

**의미**: 본 리포트 §2의 "NEST가 CBM을 못 채움"은 정확히는 **"API v1.0이 노출하지 않음"**이다. NEST 내부에는 굿즈 레벨 CBM 원천(박스타입×점유율)이 옵션 단위로 있고, 단품/키트 박스 스펙 분리는 TMS Product가 이름 접미로 임시 처리하는 것(예: LSPO 로고스트랩 파우치 대형/100 vs LSPH 同 (키트) 중대형/25)을 구조적으로 해결한 형태다. 따라서:

1. **§5 질의 1순위 승격**: quoteGoods/quoteItems에 박스명칭·박스단위(개당)·단품/키트 구분 노출 요청 (additive 변경이므로 /v1.x 가능). 노출되면 **L3(굿즈 CBM)의 소스가 NEST로 승격** 가능 — TMS Product 박스스펙과 대사 후 대체 경로.
2. NEST 견적의 차량 산정 로직 ↔ cascade S5 wave preview **교차검증** 대상 (동일 입력에 다른 결론이면 어느 쪽 마스터가 낡았는지 즉시 탐지).
3. "박스단위(개당)" 정확한 의미론(박스당 제품수의 역수 여부)은 NEST팀 확인 필요 — TMS에 동일 품목 미등록으로 교차 확인 불가였음.

## 3. 부수 발견 (프로브 부산물)

1. **기존 버그 후보 — `is_service()` "퀵" 오분류**: 실물 "퀵차지 도킹형 보조배터리(QUIC)"가 "퀵" 키워드에 걸려 서비스로 분류됨 → 현행 cascade에서도 CBM/BOM 대상에서 오제외 중일 가능성. `harness/backbone/keys.py` `_SERVICE_KW` 정밀화 필요 (keys.py 주석의 "실물과 겹치지 않는 토큰만" 원칙 위반 사례).
2. **NEST 서비스 코드 체계**: 배송·퀵·디자인 등 비물리 라인에도 코드 부여 (GBLL/GBML/GBXL/GBXS 택배, QKLL/QKML/QKMM/QKXS 퀵, DSNF 디자인, SSSV 긴급제작, PKGP 키트포장). 물리/서비스 구분 필터를 NEST 소비층에 반드시 포함해야 하며, 역으로 **견적된 배송모드 정보**로 활용 가치 있음.
3. **PNA51684 (보령 레퍼런스)**: 굿즈 6종 + 키트 1건 정상 조회. `unassignedQuantity` 의미론 실측 확인 — BFSB 쇼핑백 100(전량 단품), DRCG 등 키트 구성분은 0.
4. 구형 PNA 404는 대부분 `PRIMARY_QUOTE_NOT_FOUND` (프로젝트는 존재, 확정 견적 없음) — NEST 견적 확정 플로우 도입 이전 세대로 추정. "NEST 전환 후 아이템 누락"(260421 회의록) 검증은 이 API로 상시 모니터링 가능.

> **후속 설계 (2026-07-14)**: 3문항 설계 브리프 — CBM 의존 체인·NEST 요구사항 등급표·자재팀 위치 액션(S2.5) → [`briefs/2026-07-14-nest-cbm-bom-cascade-design.md`](briefs/2026-07-14-nest-cbm-bom-cascade-design.md) (문서형 HTML 동반)

## 4. 다음 단계 권고 (후속 세션)

1. **P1 대사 전용 라이브**: `nest_sync.py` (cron 선행 스텝, T1 신규/T2 변경/T3 소비직전 호출 정책) + 스냅샷 참조 테이블(WMS 베이스, INSERT-only) + 주문↔견적 3-way 대사 digest — cascade 동작 무변경.
2. **P2 Shadow**: cascade가 WMS_KeyCrosswalk 확정행 + NEST 키트를 log-only 소비 (S1.5/S5), 전파상태 불변 검증.
3. **P3 단계 cutover**: `NEST_정합성` 원장 필드 → S5 kit fallback(conf≤0.8) → S1.5 → alias 항목별 은퇴.
4. 즉시 조치 후보: `_SERVICE_KW` "퀵" 오분류 수정 (QUIC), CMWG·WSPB 2종 Product 등록/크로스워크 큐레이션.
5. 설계 상세는 3-lens 합성 설계문서 참조 (세션 journal — memory `project_nest_integration` 소스 경로).

## 5. NEST팀 질의 목록 (V6 — 서면 확인 필요)

0. **(1순위) 마스터 DB 박스 스펙 API 노출**: 옵션 레벨 박스명칭·박스단위(개당)·단품/키트 구분·MOQ를 production-specification 응답에 추가 가능한지 (additive → /v1.x). "박스단위(개당)"의 정확한 의미론(박스당 제품수 역수?) 및 견적 차량 산정 로직의 입력 공유. — §2.5 참조
1. 견적 수정 시 `quote.publicId` 변경 여부 / 버전·updatedAt 신호 제공 계획 (변경 감지용).
2. `Cache-Control: no-store` 정책과 "운영 이력 스냅샷 영속화(감사 목적)"의 양립 — 서면 확인.
3. 벌크 굿즈 카탈로그 endpoint 로드맵 (/v2 위시리스트) — 현재는 프로젝트 단위 조회만 가능.
4. 구형 프로젝트 `PRIMARY_QUOTE_NOT_FOUND`의 정확한 조건 (확정 견적 지정 이력 범위).
5. 물류팀 키 스코프·로테이션 주기 확정, `X-Request-Id` prefix `scm-` 사용 통보.

---

**실행 메타**: 상태 분포 `200:OK` 26 · `404:PRIMARY_QUOTE_NOT_FOUND` 5 · `404:PROJECT_NOT_FOUND` 1 / raw 응답·집계는 로컬 scratchpad 보관 (repo 미포함) / API Key는 `.env`(`NEST_PRODUCTION_SPECIFICATION_API_KEY`) 로컬 전용.
