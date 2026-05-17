# TMS AutoResearch — Session Log

---

## [2026-05-17] FEAT | Hybrid Skill+Subagent 아키텍처 도입

**타입:** 아키텍처 설계 + 구현
**상태:** 완료

### 완료 항목
- **Phase 1:** Probe Skill `.claude/skills/_probe/SKILL.md` 생성 (visibility 검증용)
- **Phase 2 Track A:** 5개 Knowledge Skills 신규 생성
  - `sap-movement-accounts` (+ 2 reference files: SAP movement types + K-IFRS codes)
  - `aql-sampling` (+ ANSI/ASQ Z1.4 full table)
  - `abc-xyz-rop-eoq` (+ formulas reference)
  - `storno-immutable-ledger`
  - `scm-kpi-formulas`
- **Phase 2 Agents:** 9개 Agent에 `## Available Skills` 3-line trailing block 추가 (SK-01~07, SK-09, D2)
- **Phase 3 Track B:** 7개 Script Skills 신규 생성 (cron parity 준수)
  - `tms-settlement-daily` (disable-model-invocation: true)
  - `tms-weekly-backfill` (disable-model-invocation: true)
  - `tms-weekly-report`, `wms-weekly-report`, `pdf-from-template` (model-invocable)
  - `wms-sap-weekly-sync`, `virtual-sap-tick` (disable-model-invocation: true)
- **Phase 4:** CLAUDE.md Skills section + routing priority line + `.claude/settings.local.json` Bash allowlist
- **Phase 5:** `.claude/skills/README.md` + feature_list.json golden tests + this log entry

### 핵심 설계 원칙
- Subagents 14개 완전 유지 — Skills은 ADDITIVE (교체 아님)
- Track B Skills = 기존 Python 모듈 래퍼 (코드 수정 0, cron parity 100%)
- Immutable Ledger 유지: destructive Skills에 disable-model-invocation: true 적용
- CLAUDE.md +10줄 이내 유지 (Boris Cherny bloat threshold)

### 검증 필수 항목
- [ ] `git diff harness/ scripts/ pdf/ api/ .github/workflows/` → 0 modifications
- [ ] 4개 destructive Script Skills에 disable-model-invocation: true 확인
- [ ] 14개 Subagent 라우팅 키워드 golden queries 정상 동작

### 다음 포커스
- Phase 1 probe Skill visibility 실증 확인 후 `_probe/` 삭제
- Golden test queries 실행 (SKILL-GOLDEN-* tasks in feature_list.json)

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
