# TMS AutoResearch — Session Log

---

## [2026-05-18] RESEARCH-v1.1 | Hindsight vs OMEGA — 공동 1순위 + PoC 자동화 스크립트로 결정 (재구성)

**타입:** 리서치 / 의사결정 분석 (v1.1 재구성)
**상태:** 보고서 v1.1 + PoC 스크립트 완료, 사용자 랩탑 PoC 실행 대기

### v1.1 재구성 사유
v1.0 ("Hindsight 1순위 + OMEGA 이주 경로") 검토 중 사용자가 "이거 API 무료?" 질문 → 확인 결과 **Hindsight 셀프호스트 = 완전 무료** (MIT, 사용 제한 0, 텔레메트리 0). v1.0의 "이주 경로" 논리(향후 가격정책 리스크)가 약화 → 가격이 결정 요인에서 제거되어 두 후보가 거의 동률이 됨. 사용자 지시 "재구성"으로 결정 구조 변경.

### v1.0 → v1.1 변경 요약
- **결정 구조**: "Hindsight 1순위" → "공동 1순위 후보, PoC 결과로 최종 결정"
- **3개 사실 오류 정정**:
  1. pip 설치 변형 4종 명시 (`hindsight-all` 권장, `hindsight-api`는 서버 전용)
  2. Hindsight 셀프호스트 완전 무료 사실 §2.4 추가
  3. Python ≥ 3.11 요구사항 추가
- **Use-case 매트릭스 + Go/No-Go 매트릭스** 추가 — 주관 판단 대신 PoC 적중률로 결정

### PoC 실행 불가 → 자동화 스크립트로 대체
원격 임시 컨테이너에서 `pip install hindsight-all` 시도 → PyPI 차단 (`HTTP 403 host_not_allowed`). 컨테이너 환경에서는 PoC 실행 불가 확인.

대안: 사용자 랩탑용 PoC 자동화 스크립트 `scripts/poc_memory_systems.py` 작성.
- `_AutoResearch/SCM/outputs/TMS-2026-W18.md` 1개를 양쪽 시스템에 동일 retain
- 5개 한국어 SCM 쿼리 (에이원 OTIF / 수도권 직배송 / 내부 소화율 60% / PT2429 / 다영기획) recall × top-3
- 키워드 포함 채점 → side-by-side 적중률 표 + Go/No-Go 자동 판정
- 정책 준수: outputs/ 마크다운 1개만 사용 (Airtable 운영 데이터 indexing 금지 준수)

### 배경
사용자가 `vectorize-io/hindsight` (13.6k★) GitHub 레포 발견 → 현재 메모리 체계(log.md + outputs/*.md + SessionStart 훅) 대비 우월성 평가 요청. 후속 요구: 랩탑-only (Docker / Railway / Fly 금지), 3-way 비교 (현재 / Hindsight / OMEGA).

### 핵심 결론
- **1순위 = Hindsight** (`pip install hindsight-api`)
  - 13.6k★ + VentureBeat 보도, BEAM·LongMemEval 동시 1위, 토큰 효율 (~7,000/retrieval + budget 컨트롤)
  - 4-병렬 retrieval (semantic + BM25 + graph + temporal) + cross-encoder rerank
  - MCP + SDK 3종 (Python/TS/Go), embedded pg0 (별도 DB 불필요)
- **이주 경로 = OMEGA** (`pip install omega-memory[server]`)
  - Apache-2.0 + 네덜란드 재단 거버넌스 + Core 영구 OSS 약속 — 가격정책 리스크 0
  - LongMemEval 95.4% (ICLR 2025), 25 memory tools, **공식 Obsidian 플러그인 보유** (Hindsight에는 없음)
  - 발동 조건: Vectorize.io가 핵심 기능 Pro tier 게이팅 시
- **MIT 오해 정정** — Hindsight는 MIT 대학교 작품 아님. "MIT License"라는 라이센스 양식을 채택한 Vectorize.io (Series A 스타트업) 작품.

### 정책 검토 (CLAUDE.md 충돌 없음)
- Hindsight·OMEGA 둘 다 *마크다운 문서만 indexing* 시 안전
- Airtable 운영 데이터 (WMS movement / mat_document / TMS shipments) indexing 금지 — Airtable 단일 진실원천 정책 위반
- 메모리 DB는 *세컨더리 검색 인덱스*로만 작동

### 다음 단계 (사용자 GO 시 별도 task)
1. **한국어 30분 PoC**: outputs/TMS-W18.md 1개 retain → 5개 쿼리 recall → 4/5 적중 → 정식 도입 GO
2. PoC 실패 시 임베더 옵션 검토 (Anthropic / Gemini / bge-m3)
3. 도입 결정 후: CLAUDE.md 기술 스택 표 갱신, MCP 등록, `scripts/hindsight_index_vault.py` 작성

### 산출물
- [Memory-Systems-Comparison-20260518.md](../outputs/Memory-Systems-Comparison-20260518.md) v1.1 (~500+줄)
- [outputs/index.md](../outputs/index.md) (신규 생성 — CLAUDE.md 종료 규칙)
- `scripts/poc_memory_systems.py` (랩탑용 PoC 자동화, py_compile 통과)

---

## [2026-05-13] WMS | 에이원 휴면 재고 검토 + WMS 교차검증

**타입:** WMS 재고 분석
**상태:** 완료

### 완료 항목
- material(에이원) 229종 → order 링크 없는 36종 휴면 후보 추출
- WMS movement 교차검증 (2025-11-01~2026-04-30, PT별 API 36회 조회)
- 진짜 완전 휴면: **6종 4,003개** (PT2429, PT0526, PT5318, PT0510, PT1705, PT2089)
- 나머지 30종은 WMS에 실제 움직임 있어 "휴면" 판정 부적절

### 핵심 발견
- Excel `order` 컬럼 link 누락 ≠ 실제 미사용 (30종이 이에 해당)
- 실물=전산 완전 일치 (차이 0) → 재고 정합성 이상 없음
- 4월 말 대량 입고된 신규 자재들이 휴면 목록에 잘못 포함 (PT5314/5315/5316 세트 등)

### 다음 포커스
- 6종 4,003개 폐기/반납/재활용 결정 요청 (업체 협의 필요)
- A2HZx 좌표 7개 현장 확인
- order link 재연결 로직 개선 검토

### 산출물
- [WMS-DormantStock-20260513.md](../outputs/WMS-DormantStock-20260513.md)
- `scripts/dormant_candidates.csv` (36종)

---

## [2026-04-15] SETUP | project.md 초기화 + 백필 스크립트 작성

**타입:** Setup  
**상태:** 완료

### 완료 항목
- `project.md` 작성 (4 Iteration 계획, Agent 구조, 성공 지표)
- `_AutoResearch/SCM/` 디렉토리 구조 생성
- `scripts/backfill_promised_delivery.py` 작성

### SLA 리드타임 마스터 확인
배송SLA 테이블 9건 조회 완료:
- 수도권 직배송: 1일, OTIF 95%
- 수도권 택배: 3일, OTIF 90%
- 지방(광역시) 직배송: 2일, OTIF 90%
- 지방(기타) 택배: 7일, OTIF 80%
- 도서산간 택배: 10일, OTIF 70%

### 다음 단계
1. `backfill_promised_delivery.py --mode all` 실행 → 기존 Shipment 전체 약속납기일 업데이트
2. Iteration 1 (볼륨 baseline) 분석 시작
3. 주 1회 월요일마다 `--mode weekly` 실행

## [2026-04-15] WEEKLY | 주간 분석 20260415

**상태:** 완료

### KPI 스냅샷
- 차량이용률: 19.4% (목표 ≥70%)
- OTIF On-Time: 100.0% (목표 ≥90%)
- 약속납기일 전환율: 100.0%

### 산출물
- [week_20260415.md](../outputs/week_20260415.md)

### 다음 주 포커스
- 차량이용률 개선

## [2026-04-15] WEEKLY | 주간 분석 20260415

**상태:** 완료

### KPI 스냅샷
- 차량이용률: 34.9% (목표 ≥70%)
- OTIF On-Time: 100.0% (목표 ≥90%)
- 약속납기일 전환율: 100.0%

### 산출물
- [week_20260415.md](../outputs/week_20260415.md)

### 다음 주 포커스
- 차량이용률 개선

## [2026-04-15] WEEKLY | 주간 분석 20260415

**상태:** 완료

### KPI 스냅샷
- 차량이용률: 34.9% (목표 ≥70%)
- OTIF On-Time: 100.0% (목표 ≥90%)
- 약속납기일 전환율: 100.0%

### 산출물
- [week_20260415.md](../outputs/week_20260415.md)

### 다음 주 포커스
- 차량이용률 개선

## [2026-04-15] WEEKLY | 주간 분석 20260415

**상태:** 완료

### KPI 스냅샷
- 내부 소화율: 60.0% (목표 ≥80%) | 고고엑스: 6.7%
- OTIF On-Time: 100.0% (목표 ≥90%)
- 약속납기일 전환율: 100.0%

### 산출물
- [week_20260415.md](../outputs/week_20260415.md)

### 다음 주 포커스
- 내부 소화율 개선 (고고엑스 건 흡수 검토)

## [2026-04-15] WEEKLY | 주간 분석 20260415

**상태:** 완료

### KPI 스냅샷
- 내부 소화율: 60.0% (목표 ≥80%) | 고고엑스: 6.7%
- OTIF On-Time: 100.0% (목표 ≥90%)
- 약속납기일 전환율: 100.0%
- 다음 주 예측: 2건 (피크 월요일)

### 산출물
- [week_20260415.md](../outputs/week_20260415.md)

### 다음 주 포커스
- 내부 소화율 개선 (고고엑스 건 흡수 검토)

## [2026-04-15] WEEKLY | 주간 분석 20260415

**상태:** 완료

### KPI 스냅샷
- 내부 소화율: 60.0% (목표 ≥80%) | 고고엑스: 6.7%
- OTIF On-Time: 100.0% (목표 ≥90%)
- 약속납기일 전환율: 100.0%
- 다음 주 예측: 71건 (피크 월요일)

### 산출물
- [week_20260415.md](../outputs/week_20260415.md)

### 다음 주 포커스
- 내부 소화율 개선 (고고엑스 건 흡수 검토)

## [2026-04-20] WEEKLY | 주간 분석 20260420

**상태:** 완료

### KPI 스냅샷
- 내부 소화율: 56.2% (목표 ≥80%) | 고고엑스: 6.2%
- OTIF On-Time: 100.0% (목표 ≥90%)
- 약속납기일 전환율: 100.0%
- 다음 주 예측: 69건 (피크 월요일)

### 산출물
- [week_20260420.md](../outputs/week_20260420.md)

### 다음 주 포커스
- 내부 소화율 개선 (고고엑스 건 흡수 검토)

## [2026-04-20] WEEKLY | 주간 분석 20260420

**상태:** 완료

### KPI 스냅샷
- 내부 소화율: 56.2% (목표 ≥80%) | 고고엑스: 6.2%
- OTIF On-Time: 100.0% (목표 ≥90%)
- 약속납기일 전환율: 100.0%
- 다음 주 예측: 68건 (피크 월요일)

### 산출물
- [week_20260420.md](../outputs/week_20260420.md)

### 다음 주 포커스
- 내부 소화율 개선 (고고엑스 건 흡수 검토)

## [2026-04-20] WEEKLY | 주간 분석 2026-W16

**상태:** 완료

### KPI 스냅샷
- 내부 소화율: 56.2% (목표 ≥80%) | 고고엑스: 6.2%
- OTIF On-Time: 100.0% (목표 ≥90%)
- 약속납기일 전환율: 100.0%
- 다음 주 예측: 68건 (피크 월요일)

### 산출물
- [TMS-2026-W16.md](../outputs/TMS-2026-W16.md)

### 다음 주 포커스
- 내부 소화율 개선 (고고엑스 건 흡수 검토)

## [2026-04-20] WEEKLY | 주간 분석 2026-W16

**상태:** 완료

### KPI 스냅샷
- 내부 소화율: 56.2% (목표 ≥80%) | 고고엑스: 6.2%
- OTIF On-Time: 100.0% (목표 ≥90%)
- 약속납기일 전환율: 100.0%
- 다음 주 예측: 69건 (피크 월요일)

### 산출물
- [TMS-2026-W16.md](../outputs/TMS-2026-W16.md)

### 다음 주 포커스
- 내부 소화율 개선 (고고엑스 건 흡수 검토)

## [2026-04-27] WEEKLY | 주간 분석 2026-W17

**상태:** 완료

### KPI 스냅샷
- 내부 소화율: 61.8% (목표 ≥80%) | 고고엑스: 5.9%
- OTIF On-Time: 99.9% (목표 ≥90%)
- 약속납기일 전환율: 100.0%
- 다음 주 예측: 72건 (피크 월요일)

### 산출물
- [TMS-2026-W17.md](../outputs/TMS-2026-W17.md)

### 다음 주 포커스
- 내부 소화율 개선 (고고엑스 건 흡수 검토)

## [2026-04-27] WEEKLY | 주간 분석 2026-W17

**상태:** 완료

### KPI 스냅샷
- 내부 소화율: 61.8% (목표 ≥80%) | 고고엑스: 5.9%
- OTIF On-Time: 99.9% (목표 ≥90%)
- 약속납기일 전환율: 100.0%
- 다음 주 예측: 73건 (피크 월요일)

### 산출물
- [TMS-2026-W17.md](../outputs/TMS-2026-W17.md)

### 다음 주 포커스
- 내부 소화율 개선 (고고엑스 건 흡수 검토)

## [2026-05-04] WEEKLY | 주간 분석 2026-W18

**상태:** 완료

### KPI 스냅샷
- 내부 소화율: 60.0% (목표 ≥80%) | 고고엑스: 5.7%
- OTIF On-Time: 99.9% (목표 ≥90%)
- 약속납기일 전환율: 100.0%
- 다음 주 예측: 65건 (피크 월요일)

### 산출물
- [TMS-2026-W18.md](../outputs/TMS-2026-W18.md)

### 다음 주 포커스
- 내부 소화율 개선 (고고엑스 건 흡수 검토)

# WMS AutoResearch — Session Log

---

## [2026-04-21] SETUP | program.md 초기화 + 주간 러너 구성

**타입:** Setup  
**상태:** 완료

### 완료 항목
- `program.md` 작성 (3 KPI, 4 Iteration 계획)
- `_AutoResearch/WMS/` 디렉토리 구조 생성
- `scripts/wms_weekly_runner.py` 작성
- `.github/workflows/wms-weekly-autoresearch.yml` 등록

### 분석 대상 확정
- **QC 불량 proxy**: `order.표본 검수 결과` (singleSelect) 불합격 카운트 + `movement.검수 status` 텍스트 파싱
- **입출고 볼륨 트렌드**: `movement.이동목적` × `movement.생성일자` 주간 집계
- **공급사 납기 proxy**: `order.입고예정일` vs `order.실제 입고일` diff (공급사별 그룹핑)

### 다음 단계
1. GitHub Actions 수동 trigger → 첫 번째 WMS weekly 리포트 생성 확인
2. Iter 1 baseline 분석 시작

## [2026-04-21] WEEKLY | 주간 분석 2026-W16

**상태:** 완료

### KPI 스냅샷
- QC 불량 proxy: 0.0% (텍스트 파싱)
- 입출고 볼륨: 13건 (WoW -68건)
- 공급사 평균 납기 편차: 측정 불가

### 산출물
- [WMS-2026-W16.md](../outputs/WMS-2026-W16.md)

### 다음 주 포커스
- 납기 지연 공급사 지속 모니터링

## [2026-04-21] WEEKLY | 주간 분석 2026-W16

**상태:** 완료

### KPI 스냅샷
- QC 불량 proxy: 0.0% (텍스트 파싱)
- 입출고 볼륨: 13건 (WoW -68건)
- 공급사 평균 납기 편차: 측정 불가

### 산출물
- [WMS-2026-W16.md](../outputs/WMS-2026-W16.md)

### 다음 주 포커스
- 납기 지연 공급사 지속 모니터링

## [2026-04-21] WEEKLY | 주간 분석 2026-W16

**상태:** 완료

### KPI 스냅샷
- QC 이슈 proxy: 4.8% (176/3656건) (생산산출+재고생산 중 이슈카테고리 발생률)
- 입출고 볼륨: 18건 (WoW -63건)
- 미입하 발생이력: 87건

### 산출물
- [WMS-2026-W16.md](../outputs/WMS-2026-W16.md)

### 다음 주 포커스
- 납기 지연 공급사 지속 모니터링

## [2026-04-27] WEEKLY | 주간 분석 2026-W17

**상태:** 완료

### KPI 스냅샷
- QC 이슈 proxy: 4.8% (182/3814건) (생산산출+재고생산 중 이슈카테고리 발생률)
- 입출고 볼륨: 1건 (WoW -45건)
- 미입하 발생이력: 93건

### 산출물
- [WMS-2026-W17.md](../outputs/WMS-2026-W17.md)

### 다음 주 포커스
- 납기 지연 공급사 지속 모니터링
## [2026-05-08] WMS | Slack 이슈 교차검증 완료

**상태:** 완료

### 교차검증 요약
- WMS Movement 조회: 21,510건
- 카테고리 Slack 근접 ✅: 2/6개
- Slack 보고 총계: 71건

### 산출물
- [WMS-SlackXVal-20260508.md](../outputs/WMS-SlackXVal-20260508.md)

### 다음 포커스
- NOT_FOUND 케이스 Airtable UI 직접 확인
- TO번호 TMS Shipment 별도 검증

## [2026-05-08] SCM | WMS Slack MM 직접 조회 보고서

**상태:** 완료

### 산출물
- [WMS-SlackMM-20260508.md](../outputs/WMS-SlackMM-20260508.md)

### 요약
- 전체 6개 카테고리 / Slack 71건 기준 MM번호 직접 조회
- C1: 33건 (Slack 21건 / 실제 MM수), C2: 9건, C3: 6건, C4: 2건, C5: 1건, C6: 3건


## [2026-05-11] WEEKLY | 주간 분석 2026-W19

**상태:** 완료

### KPI 스냅샷
- 내부 소화율: 60.5% (목표 ≥80%) | 고고엑스: 5.3%
- OTIF On-Time: 99.9% (목표 ≥90%)
- 약속납기일 전환율: 100.0%
- 다음 주 예측: 55건 (피크 월요일)

### 산출물
- [TMS-2026-W19.md](../outputs/TMS-2026-W19.md)

### 다음 주 포커스
- 내부 소화율 개선 (고고엑스 건 흡수 검토)

## [2026-05-11] WEEKLY | 주간 분석 2026-W19

**상태:** 완료

### KPI 스냅샷
- 내부 소화율: 60.5% (목표 ≥80%) | 고고엑스: 5.3%
- OTIF On-Time: 99.9% (목표 ≥90%)
- 약속납기일 전환율: 100.0%
- 다음 주 예측: 55건 (피크 월요일)

### 산출물
- [TMS-2026-W19.md](../outputs/TMS-2026-W19.md)

### 다음 주 포커스
- 내부 소화율 개선 (고고엑스 건 흡수 검토)

## [2026-05-12] CBM | 박종성 다영기획 CBM 시뮬레이션 완료 — 2026-05-13 하네스 가동

**타입:** Settlement / CBM Master Data
**상태:** 시뮬레이션 완료, 5/13부터 하네스 실운영

### 배경
- 박종성 기사 다영기획 출발 71건(2026-01~05) 박스 데이터 전무 → 하차비 0원 누적
- F_BOX_TEXT(외박스 수량 rollup) 없는 레코드는 기존 `parse_unload_fee` 적용 불가
- 영업팀 CBM 마스터 PDF(7페이지, ~334 품목) 보유 확인 → CBM 기반 fallback 도입

### 완료 항목
1. **`harness/settlement/cbm_calc.py`** — 공용 모듈 신규
   - `load_product_lookup` (Product 테이블 전체 조회 → name/code 룩업)
   - `match_product` (exact → Jaccard ≥ 0.4)
   - `parse_product_lines` (품목+수량 텍스트 파싱)
   - `calc_from_products` (하차비 + Total_CBM 계산)
   - **버그 픽스:** 한글/영문 경계 토큰 분리 (`Tailored스트랩박스` → `Tailored 스트랩박스`)로 Jaccard 0.00 → 0.40~1.00 회복
   - **Fallback:** `BOX_TYPE_TO_CBM_M3` (formula 0 반환 시 표준 박스 부피)

2. **`harness/settlement/product_cbm_data.py`** — 데이터 신규 (14건 입력)
   - 시드 4건 + PDF 페이지 7 신규 10건 (NFCA, AWTW, SOLE, SORB, FANB, FANC, USLB, HHTW, HHTK, ATSS)

3. **`harness/settlement/import_product_cbm.py`** — UPSERT 스크립트 신규
   - 견적코드 기준 UPSERT, dry-run 지원
   - FLD_BOX_SIZE (`fld1ECU2hhnEurOef`) 추가 → Airtable formula '박스 당 CBM' 작동

4. **`scripts/backfill/backfill_상하차비용.py`** — 소급 백필 신규
   - 박종성 전체 Shipment 조회 → F_BOX_TEXT 우선, 없으면 CBM 룩업
   - 기존 F_UNLOAD > 0 은 `--force` 없이 skip

5. **`harness/settlement/settlement_calc.py`** — calc_park() Priority 3 fallback 추가
   - F_BOX_TEXT → PNA 박스 폴백 → CBM 기반 계산 순

6. **`scripts/tms_weekly_backfill.py`** — MODES에 `unload_fee` 추가

커밋: `9d02008` (이후 box_size 필드/토크나이저 버그 픽스 미커밋)

### 검증 결과
- Jaccard 매칭 8개 케이스 중 7개 성공 (score ≥ 0.4)
  - 미스: `더블업트래블파우치(Small) 키트` vs `더블업트래블파우치(S)` — Product 측 약식 표기 원인
- 모든 .py 파일 `py -m py_compile` 통과

### Product 테이블 현황
- Airtable Product 약 334번 행까지 기존 입력 존재 (사용자 스크린샷 확인)
- PDF 7페이지 품목 대부분 이미 Airtable에 존재 가능성 → UPSERT 시 충돌 없이 PATCH

### CBM 시뮬레이션 결과 (2026-05-12 세션)
- 대상: 박종성 다영기획 출발 박스 없는 건 **197건** (2024-01-01 ~ 2026-05-12)
- 완전 매칭 33.5% / 부분 매칭 60.9% / 전부 미매칭 0% ✅ / 품목텍스트 없음 5.6%
- 하차비 계산 가능 (sim > 0): **60건 (30.5%)**
- 시뮬 합계 **1,255,000원** vs 실제 지급 475,000원 → 2.6배 (캡 50,000원 정상 적용)
- 소량 건 0원은 정상 동작 (박스 임계치 미달)
- 스크립트: `harness/settlement/simulate_park_dayoung_cbm.py`

### 미매칭 Top 품목 (Product 마스터 보강 필요)
페이퍼샤쉐(6), 브랜디드타월(6), Tailored스트랩박스키트(4), 에디트캘린더/리유저블캘린더/페이퍼링캘린더(3), Simple슬라이드지퍼백(M)키트(3+2), 데일리짐색(3+2), 보냉키트백(3)

### 다음 단계
1. **5/13~:** 하네스 실운영 → 박종성 다영기획 건 상하차비용 자동 계산 시작
2. **이후:** 실운영 데이터 보면서 운임비 로직 개선 의논
3. **선택:** 미매칭 Top 품목 Product 마스터 추가 → 매칭률 90%+ 목표
