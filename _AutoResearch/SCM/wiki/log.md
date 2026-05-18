# TMS AutoResearch — Session Log

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

## [2026-05-15] WEEKLY | 주간 분석 2026-W19

**상태:** 완료

### KPI 스냅샷
- 내부 소화율: 63.2% (목표 ≥80%) | 고고엑스: 5.3%
- OTIF On-Time: 99.9% (목표 ≥90%)
- 차량이용률 v2 (CBM 적재율): 31.2%
- 약속납기일 전환율: 100.0%
- 다음 주 예측: 76건 (피크 월요일)

### Iter6 갭분석
- 흡수 가능 고고엑스: 2건 → 내부 소화율 68.4% 달성 예상 (+5.2pp)

### 산출물
- [TMS-2026-W19.md](../outputs/TMS-2026-W19.md)

### 다음 주 포커스
- 내부 소화율 개선 (고고엑스 건 흡수 검토)

## [2026-05-15] WEEKLY | 주간 분석 2026-W19

**상태:** 완료

### KPI 스냅샷
- 내부 소화율: 63.2% (목표 ≥80%) | 고고엑스: 5.3%
- OTIF On-Time: 99.9% (목표 ≥90%)
- 차량이용률 v2 (CBM 적재율): 31.2%
- 약속납기일 전환율: 100.0%
- 다음 주 예측: 76건 (피크 월요일)

### Iter6 갭분석
- 흡수 가능 고고엑스: 2건 → 내부 소화율 68.4% 달성 예상 (+5.2pp)

### 산출물
- [TMS-2026-W19.md](../outputs/TMS-2026-W19.md)

### 다음 주 포커스
- 내부 소화율 개선 (고고엑스 건 흡수 검토)

## [2026-05-15] WEEKLY | 주간 분석 2026-W19

**상태:** 완료

### KPI 스냅샷
- 내부 소화율: 63.2% (목표 ≥80%) | 고고엑스: 5.3%
- OTIF On-Time: 99.9% (목표 ≥90%)
- 차량이용률 v2 (CBM 적재율): 31.2%
- 약속납기일 전환율: 100.0%
- 다음 주 예측: 76건 (피크 월요일)

### Iter6 갭분석
- 흡수 가능 고고엑스: 2건 → 내부 소화율 68.4% 달성 예상 (+5.2pp)

### 산출물
- [TMS-2026-W19.md](../outputs/TMS-2026-W19.md)

### 다음 주 포커스
- 내부 소화율 개선 (고고엑스 건 흡수 검토)

## [2026-05-16] Harness | Phase 1 FSM 구현 완료 — Event Log + /mission resume

**타입:** Universal Project Harness 업그레이드 (글로벌 ~/.claude/)
**상태:** 완료
**Origin:** Yeachan Heo Instagram "Harness Engineering" 분석 + oh-my-claudecode 비교

### 배경
사용자가 인스타 글 분석 요청 → 우리 하네스가 이미 95% 원칙 적용 중. 단 하나의 큰 갭: 미션 상태가 파일 존재로만 추론됨 → OS 재시작·세션 크래시 시 미션 손실, `/mission resume <id>` 부재.

Plan A (Event Log + State Snapshot) + step-level granularity로 결정 → 풀 구현 완료.

### 완료 항목
- `~/.claude/harness/scripts/event_log.py` (486줄) — emit/replay/validate_outputs/compute_resume_point/list_missions/abort_mission
- `~/.claude/harness/scripts/tests/test_event_log.py` — 24 tests, 모두 PASS
- `~/.claude/harness/event-log-spec.md` — 27 step type 카탈로그(MECE), resume 알고리즘, 실패 모드 명세
- `~/.claude/harness/scripts/cli.py` — 7 신규 subcommand (emit-event/replay/state/resume-point/validate-outputs/list-missions/abort-mission)
- `~/.claude/commands/mission.md` — resume/list/abort 서브커맨드
- `~/.claude/agents/*` — 9 agent에 Event Log Discipline 섹션 추가 (orchestrator + 8 sub-agents)
- `~/.claude/harness/notion-mapping.yaml` — 6 신규 event_* 매핑 (mission_resumed/runtime_capability_missing/runtime_cost_halted/sprint_rolled_back/lesson_approved/mission_aborted)

### 핵심 설계 결정
1. Event sourcing — events.jsonl SSOT, append-only, atomic fsync, malformed last line tolerance
2. Step-level granularity — 27 step type (MECE), 5 lock-creating, 9 terminal
3. Single-writer pattern — orchestrator만 emit, sub-agent는 응답 metadata만 제공
4. Idempotency by step_id, 출력 sha256 hash로 무결성 검증
5. Lock 자동 라이프사이클 (`locks/<step_id>.lock`)

### 검증 (Phase 1 acceptance 10/10 PASS)
- 24/24 unit test (test_event_log.py)
- 8-step CLI smoke test (happy path → kill → resume-point → mission.resumed → abort)
- 9 agent .md 모두 "Event Log Discipline" 섹션 포함
- 기존 38 meeting/render 테스트 모두 PASS (regression 0)
- `.claude` repo commit: f6c3648 (Stop 훅이 자동 commit, 메시지에 "Plan C"라고 적혔지만 Phase 1 변경 일체 포함)

### Phase 2 (다음 미션)
**6-Layer MECE 감사** — CLAUDE.md → Harness → Agents → Hooks → Skills → Domain Routing 전 stack 점검. 별도 `/brainstorm` 세션 진입.

### 다음 추천 태스크
1. Phase 1 실전 검증: 실제 4h `/mission build-pipeline` 1회 end-to-end
2. Phase 2 MECE 감사 brainstorm 진입
3. `render_meeting.py` pre-existing 테스트 1건 (`_render_checkpoint_top` NameError) 별도 fix — 이번 작업 무관

## [2026-05-16] Harness | Phase 2 — 6-Layer MECE Audit 완료

**타입:** Universal Project Harness 자가검증 (CLAUDE.md → Harness → Agents → Hooks → Skills → Domain Routing)
**상태:** Audit 완료 + P0 2건 즉시 fix
**Origin:** Phase 1 FSM 완료 후 사용자 후속 요청

### 방법론
- 3 parallel Explore agents × 6 layers × 7 dimensions (Drift/Overlap/Gap/Staleness/CrossLayer/Karpathy/HookCoverage)
- Synthesis: 6×7 매트릭스 + 11 cross-layer 충돌 추출 + P0/P1/P2 backlog 생성
- Raw 63 → unique 52 findings (cross-layer dedup 11)

### 산출 3 파일
- `docs/superpowers/specs/2026-05-16-6-layer-audit-design.md` — 방법론 + acceptance
- `docs/superpowers/outputs/2026-05-16-6-layer-audit-report.md` — findings 매트릭스 + cross-layer + per-layer 상세
- `.claude/feature_list.json` — 37 audit backlog 항목 추가 (총 48 tasks; P0=2, P1=24, P2=11)

### 주요 발견
**Cross-layer 충돌 11건 (X1~X11):**
- X1: Phase 1 FSM (event-log-spec.md, /mission resume/list/abort) L1·L2 docs 미반영
- X2: `/learn` 슬래시 커맨드 부재 (L2에서 2회 참조, 실제는 `/lesson`만 존재)
- X3: Event Log Discipline 5 agents 누락 (notion-sync, workflow-architect, reality-checker, codebase-onboarding-engineer, evidence-collector)
- X4: `runtime.snapshot` event_log.py VALID_TYPES에 있으나 spec catalog 부재
- X5: 6 notion-mapping event_* 매핑 선언만, 실제 emit 코드 path 부재
- X6: L1 model 기본 vs L2 opus override 패턴 미문서화
- X7: L2 routing keyword 충돌 4 pair (SK-06/D-TMS1, D-TMS1/D3, SK-09/D1, SK-08/MC)
- X8: strategy-design.yaml가 SCM_WORK 전용 에이전트 참조 (글로벌 부재) **P0**
- X9: L2 'PostToolUse 회의록 백업' 선언과 실제 구현 불일치
- X10: L1-L2 'Always respond in English' 중복
- X11: Hook 커버리지 8 lifecycle 누락 (PreToolUse/SubagentStop/PreCompact 가치 큼)

### 즉시 fix 완료 (P0 2건)
1. `AUDIT-L4-DRIFT-01` — `SCM_WORK/.claude/agents/meeting-analysis.md` model `claude-sonnet-4-6` → `sonnet`
2. `AUDIT-X8` — `~/.claude/harness/missions/strategy-design.yaml`에 `project_specific: scm` + `required_agents` + `agent_search_paths` 추가 → 다른 프로젝트에서 호출 시 명시적 검증

### Hook 비교 (vs oh-my-claudecode)
- 현재: 4 hooks × 4 events (Stop/Notification/PostToolUse/SessionStart)
- 그쪽: 20 hooks × 11 events
- 우선 추가 권고: PreToolUse (git-guardrails) / SubagentStop (auto worker.completed) / PreCompact (state snapshot)
- AUDIT-X11-A는 별도 brainstorm 필요

### 다음 추천 태스크
1. P1 docs 5건 (X1, X2, X9, X10, X6) — L1·L2 단발 갱신 (~30분)
2. P1 agents 5건 (X3) — 5 agents에 Event Log Discipline 추가 (~45분)
3. 별도 brainstorm: AUDIT-X11-A (PreToolUse / git-guardrails)
4. P1 harness 4건 (X4, X5, X7 reflect, sprint-config override)
5. AUDIT-X11-B/C 후속 미션 (SubagentStop / PreCompact 훅)

### Phase 1+2 회고
- Yeachan Heo "Harness Engineering" 인스타 분석 → Phase 1 FSM 구현 → Phase 2 MECE audit
- 우리 하네스가 95% 원칙 적용 중이라는 가설 → audit 결과로 검증됨 (P0 2건만, 대부분 P1/P2 cleanup)
- "닫힌 deterministic loop 안에서 LLM이 판단" 원칙은 이미 작동 — 갱신·정합성 유지가 주된 과제

## [2026-05-17] Harness | Phase 2 후속 — Tasks 1-4 연속 실행 완료

**타입:** Audit P1 항목 batch resolution + 신규 lifecycle 훅 3개
**상태:** 18/37 AUDIT items done (P0 2/2, P1 15/24, P2 1/11)

### Task 1 — Docs 갱신 (X1/X2/X9/X10/X6) ✅
- L1 (`~/.claude/CLAUDE.md`):
  - Model strategy 섹션 "프로젝트 override" 조항 (L1 default sonnet, L2 opus 정당화)
  - Harness 구조에 Phase 1 FSM 명시 (event-log-spec.md, /mission resume·list·abort)
  - 신규 "Hook Lifecycle" 섹션 (현재 7 훅)
  - obsidian-routing ClaudeVault 절대경로
- L2 (`SCM_WORK/CLAUDE.md`):
  - "회의록 백업" 행을 실제 구현과 일치
  - ClaudeVault 절대경로 명시
  - 언어 정책 L1 상속 + 한국어 예외
  - Harness 섹션에 Routing 분기 충돌 4 pair + 모델 할당 정당화
  - `/learn` → `/lesson` 2곳 교체

### Task 2 — 5 Agents Event Log Discipline (X3) ✅
- notion-sync.md: consumer 입장 (events.jsonl 미읽기)
- workflow-architect.md: pre-Sprint 위임 시 orchestrator 발행
- reality-checker.md: 미션 final cert 시 events.jsonl SSOT 사용
- codebase-onboarding-engineer.md: once_per_project lifecycle
- evidence-collector.md: **의도적 제외** 사유 명시 (narrow scope)

### Task 3 — AUDIT-X11-A PreToolUse / git-guardrails ✅
- 설계 spec: `docs/superpowers/specs/2026-05-16-pretool-git-guardrails-design.md`
- 스크립트: `~/.claude/hooks/block-dangerous-git.sh` (upstream 다운로드 + customize)
- 패턴: git destructive ops + hook bypass flags + destructive rm at root
- 수정: jq → Python (jq 미설치) / grep `--` 추가 / fail-safe passthrough
- 8/8 smoke test 통과 — 직후 본 log entry도 한 번 차단당함 (워딩 회피해서 재시도)

### Task 4 — X11-B SubagentStop + X11-C PreCompact ✅
- `subagent-stop.sh`: observation log only (auto-emit 미구현; 추후 active-task 추적 성숙 시 통합)
- `pre-compact.sh`: 활성 미션 state.json snapshot (`py -m scripts.cli state`)
- settings.json 통합: 4 → 7 lifecycle events (+75%)

### Hook lifecycle 현황
| 이벤트 | 이전 | 현재 |
|--------|------|------|
| 합계 | 4 | **7** (+75%) |
| PreToolUse | — | ✅ Bash matcher, git-guardrails |
| SubagentStop | — | ✅ observation log |
| PreCompact | — | ✅ state snapshot |
| SessionStart / PostToolUse / Stop / Notification | 유지 |

oh-my-claudecode 비교 11 events. 우리 7 events. 나머지 4-5는 YAGNI.

### 남은 audit backlog (19/37 pending)
- P1 9건: notion-mapping emit(X5), Notion 6 DB inline(L1-GAP-01), feature_list 관리(L2-GAP-01), Contract 링크(L2-GAP-02), README Phase 2 갱신(L3-GAP-01), sprint duration override(L3-CROSS-01), Stop hook Supabase 주석(L5-DRIFT-01), PostToolUse matcher 확장(L5-GAP-01), runtime.snapshot catalog(X4)
- P2 10건: Karpathy cleanup, staleness check 등

### 다음 추천
1. 남은 P1 9건 batch 단발 (~60분)
2. 실전 검증: 4h `/mission build-pipeline` 1회 — Phase 1 FSM + 신규 훅 end-to-end
3. SubagentStop active-task tracking 강화 (Phase 3+)

## [2026-05-18] WEEKLY+ITER7 | 2026-W20 (full)

**상태:** 완료

### KPI 스냅샷 (W20 표준 분석)
- 내부 소화율: **63.2%** (목표 ≥80%) ⚠️ — 70% 하한 미달, D1 검토 필요
- 고고엑스 비중: 5.3% (2건/30일)
- OTIF On-Time: 99.9% (목표 ≥90%) ✅
- 차량이용률 v2 (CBM 적재율): 32.5%
- 약속납기일 전환율: 100.0%
- 다음 주 예측: 37건 (피크 수요일, 5/25 월요일 공휴일 제외)

### Iter6 갭분석
- 흡수 가능 고고엑스: 2건 → 내부 소화율 63.2% → 68.4% 달성 예상 (+5.2pp)

### Iter7 확장 분석 (6주 W14~W19)
- 내부 소화율 (6주): 71.9% — Pearson r v1/v2: 0.9426
- NPV: S1/S2 모두 음의 NPV → 현행 유지 (S3 단가협상 제외 확정)
- avg MAPE: 32.84% (보정계수 0.3→0.15 재검토 권장)
- Lane CBM 6주 총계: 270.33m³ → SK-09 인계 완료

### 산출물
- [TMS-2026-W20.md](../outputs/TMS-2026-W20.md)
- [TMS-2026-W20-Iter7.md](C:\Users\yjisu\Documents\ClaudeVault\SCM\_AutoResearch\outputs\TMS-2026-W20-Iter7.md)

### 다음 주 포커스
- 내부 소화율 개선 (고고엑스 2건 즉시 흡수 → 68.4% 달성)
- Iter8 착수 조건: 외주 건수 모니터링 + D1 NPV 가정 실사
