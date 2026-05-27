# 신시어리 자체 기사 + 외주 3PL Lane 분담 · 통합 적재 전략

> 작성일: 2026-05-27 | 작성자: Claude (superpowers:brainstorming) | 청중: SCM실장·물류파트장·CFO
> 시드 문서: `groovy-brewing-sparrow.md` §11.7 / `SCM-FinanceStrategy-2026-05-21.md` (T-H2-01 + T-H2-02)
> 산출 mirror: `docs/superpowers/specs/2026-05-27-driver-lane-consolidation-strategy-design.md` (git committed)

---

## Context

본 전략은 **(1) Plan §11.7에서 사용자가 우선순위로 재조정한 *Lane + 통합 적재 전략 brainstorm*** 결과이며, **(2) 2026-05-21 재무 KPI 연계 전략 문서의 H2 후보(T-H2-01 carrier mix + T-H2-02 통합 적재)를 통합**하여 *자체 기사 3명 + 외주 3PL·carrier 5개사*의 운영 정책을 설계한다.

**Why now:**
- 자체 기사 *이장훈·조희선* 합산 고정비 **1.37억원/년** — 비수기(3월~10월) 활용도 차이가 그대로 손실
- 성수기(4Q+1Q) 자체 기사 capacity 초과 → 고고엑스 퀵 spillover 비용 증가
- 현재 베스트 프랙티스(*조희선 콘솔 6건*, *박종성 다영기획 임가공 90%*)가 *공식 룰로 시스템화 안 됨* → 속인적 운영
- 5개 외주사 중 *우리 자율 영역*과 *고객/거리 lock-in*이 구분되어 있지 않아 전략 여지 불명확

**Intended outcome:**
- 자체 기사 3명 + 외주 5개사의 *역할 매트릭스 SSOT* 확립
- *비수기 흡수 룰* + *통합 적재 wave 시스템* + *자율 carrier RFQ* 3축 정책 도입
- 6개월 운영 후 *연 0.3~0.7억 절감* (Option B 추천 채택)
- 데이터 누적 시 Option C(구조 재설계)로 진화 가능 진입

---

## 1. 자원 매핑 (Resource Map)

### 1.1 자체 기사 3명 (Owned Fleet — 2026-05-27 확정)

| 기사 ID | 이름 | 차량 | 차량 CBM | 거주지 | 운영 시간 | 일 capacity | 고정비/일 | 계약 형태 |
|---------|------|------|---------|--------|----------|-----------|---------|---------|
| CA-0002 | 이장훈 | 현대 스타리아 (운전석 외 화물칸) | **~4~5m³** ⚠️ | 서울 성북구 | **09:00~13:00 (오전만)** | 최대 3건, CBM 최소화 | 160,000원 | 계약직 (고정비) |
| CA-NEW-1 | **조희선** ⭐신규 | (확인 필요) | (확인 필요) | 서울 양천구 | 풀 시간 (오전 3 + 오후 3) | **6건 콘솔 적재** | 360,000원 | 계약직 (고정비) |
| CA-0003 | 박종성 | (확인 필요) | (확인 필요) | 서울 중랑구 | 풀 시간, 건수 제한 없음 | **7~8건 (전국)** | **0원 (변동비)** | 개인사업자 |

**핵심 시사점:**
- *이장훈·조희선 합계 = 11.4백만원/월 ≈ 1.37억원/년 고정비* — 활용도 ↓ = 직접 손실
- *박종성 = 변동비 (배차 시만 지급)* — 매우 유연, 성수기 spillover 시 우선 활용 대상
- **데이터 갭 (Open Decision 1):**
  - 이장훈 차량 *현대 스타리아 화물칸 정확 CBM* — 추정 4~5m³ (1톤보다 약간 큼), 등록증/현대 카탈로그로 확정 필요
  - 조희선·박종성 차량 spec 미확인
- **CA-0004 김민준 → CA-NEW-1 조희선 교체** — `dispatch_advisor.py` (line 50~54) 코드 갱신 필요

### 1.2 외주 3PL 파트너 · Carrier 5개사

| 파트너 | 본질적 역할 | 위치 | 우리 자율 영역? | Lock-in 사유 |
|--------|----------|------|-------------|------------|
| **다영기획** | 프로젝트 임가공 협력사 | (확인 필요) | 🟡 일부 자율 (임가공 후 *퀵 발송*은 박종성 90% 흡수 가능) | *택배 발송*은 다영 자체 (고객 지정 케이스) |
| **베스트원** | 재고보관 창고 (3PL 보관) | **경기 광주시** | 🔴 거리 Lock-in | 기사 거주지 (서울)에서 광주시 들리는 거리 비효율 |
| **로지비** | 풀필먼트 보관·출하 협력사 | **경기 이천시** | 🔴 거리 Lock-in | 기사 거주지에서 이천시 거리 비효율 |
| **로젠택배** | 진짜 carrier (전국 택배망) | (전국) | 🟢 우리 자율 (단가 협상 가능) | — |
| **고고엑스** | 진짜 carrier (spillover 퀵) | (수도권 즉시) | 🟢 우리 자율 (단가 협상 가능) | — |

**핵심 시사점:**
- 5개사 중 **3개사(다영·베스트원·로지비)는 *3PL 파트너* — 단순 carrier가 아니라 *보관·임가공·풀필먼트* 가치를 제공**. *carrier 통합 RFQ* 표현 부정확 → *3PL 파트너 정기 리뷰* + *carrier(로젠·고고엑스) 단가 RFQ* 로 분리
- **거리 Lock-in (베스트원·로지비)** = 본 전략 *범위 외* — 변경 시 거점 자체 이동 필요 (대규모 자본 결정, H3 수준)
- *진짜 자율 영역*은 ① 자체 기사 vs 고고엑스(spillover 결정) ② 다영기획 임가공 후 퀵(박종성 흡수) ③ 로젠 vs 자체기사(지방 화물)

### 1.3 SLA SSOT (Service Level Agreement Single Source of Truth)

| 발송 방식 | 약속 납기 기준 | 고객 인지 |
|----------|------------|---------|
| 퀵 | TMS `Shipment.출하확정일` = *고객 수령 희망일* | 당일 도착 약속 |
| 택배 | TMS `Shipment.출하확정일` = *출고일* | 출고 후 1~4일 소요 인지 |

→ 모든 SLA 측정·D-2 알림(T-H1-03)의 기준 = `출하확정일`. 별도 SLA enum 불필요.

---

## 2. Lane 분류 (8 케이스, 매트릭스 v2)

| # | 케이스 (Lane) | 1순위 | 2순위/Fallback | 의사결정 | 비고 |
|---|-------------|------|--------------|--------|------|
| 1 | 신시어리 퀵 수도권 (오전, 소형) | 이장훈 (스타리아, ~3건) | 조희선 (콘솔), 고고엑스 | 🟢 자율 | 오전 슬롯 우선 채움 |
| 2 | 신시어리 퀵 수도권 (오후·풀일) | 조희선 (콘솔 6건) | 박종성, 고고엑스 | 🟢 자율 | 조희선 콘솔이 베스트 프랙티스 |
| 3 | 신시어리 지방·전국 | 박종성 (전국) | 로젠택배 | 🟢 자율 | CBM 큰 화물은 로젠 |
| 4 | 다영기획 임가공 → 퀵 발송 | **박종성 (90%)** | 다영 자체 배송 | 🟡 일부 자율 | 이미 정착된 베스트 프랙티스 |
| 5 | 다영기획 임가공 → 택배 발송 | 다영기획 택배 | — | 🔴 Lock-in | 다영 자체 택배 |
| 6 | 베스트원 재고 → 퀵/택배 (광주시) | 베스트원 자체 | 자체 기사 (거리 비효율) | 🔴 거리 Lock-in | 광주시 거리 |
| 7 | 로지비 풀필먼트 → 퀵/택배 (이천시) | 로지비 자체 | — | 🔴 거리 Lock-in | 이천시 거리 |
| 8 | **비수기 capacity 흡수** (3월~10월) | **자체 기사가 외주 임가공·재고이동 흡수** | (현재 의식적 시행) | 🟢 핵심 자율 영역 | 본 전략의 ₩ 임팩트 주력 |

---

## 3. 전략 (Option B — 중도, 3축 동시 진행)

### 3.1 비수기 자체 기사 흡수 정책 (Axis 1)

**목표:** 비수기(3월~10월) 자체 기사 idle 시간 ↓ → 외주 임가공·재고이동을 자체 기사로 흡수

**룰:**
1. 매일 09:00 — 자체 기사 capacity 산출 (이장훈 3건 / 조희선 6건 / 박종성 7~8건)
2. 신시어리 정규 출하 후 *잔여 capacity*를 *외주 임가공·재고이동 후보*에 할당
3. 우선순위: 박종성 (변동비, 거리 무관) → 조희선 (콘솔 가능) → 이장훈 (오전·소형만)
4. *베스트원 재고이동(광주시)*은 거리상 어려움 — 단, *비수기 한정·박종성 한정*으로 시범 운영

**현재 시행 중인 패턴 (룰로 격상):**
- 조희선 콘솔 6건 = 베스트 프랙티스 (시스템화 대상)
- 박종성 다영기획 임가공 90% = 베스트 프랙티스 (시스템화 대상)

**시즌 모드 분기:**
- **성수기 (11월~2월)**: 자체 기사 full capacity → 초과분은 고고엑스 즉시 spillover (현재 운영 유지)
- **비수기 (3월~10월)**: 자체 기사 idle 측정 → 외주 임가공·재고이동 흡수 (신규 룰)

### 3.2 통합 적재 Wave 시스템화 (Axis 2) — *2026-05-27 사용자 확정 정책*

**Wave 개념 (도메인 용어 정의):**
- *Wave* = 여러 shipment를 *시간 단위로 묶어서* 한 차량으로 *한 번에 출발*시키는 batch.
- 분산 적재(주문 1건당 차량 1대) → 통합 적재(N건 → 차량 1대)로 *차량이용률 ↑ + 운반비 ↓*.

**Wave 정책 — 2 모드 동시 지원:**

| Wave | 기사 | Trigger 방식 | 빈도 | 건수 | 비고 |
|------|------|-----------|------|------|------|
| **W1** | 이장훈 | ⏰ 시간 고정 (**09:00** 확정) | 매일 1회 | ≤3건 소형 | 조희선 W2와 동시 09:00 wave |
| **W2-기본** | 조희선 | ⏰ 시간 고정 (09:00 이전 마감) | 매일 1회 (**99%**) | 콘솔 ≤6건 (오전 3 + 오후 3 통합) | 표준 패턴 |
| **W2-예외** | 조희선 | 🚨 예외 trigger — *CBM 초과 잔여* + *당일 임가공 오후 출고* | 오후 (1%) | 잔여 + 오후 임가공품 | 시스템 자동 trigger X — 수동 발동 |
| **W3** | **박종성** | 🔄 **Trigger 기반 (시간 자유)** — 새벽·낮·야간 모두 가능 | 매일 1+회 | 기본 5건 + 잔여 1~2건 lightweight wave | 가장 유연 |

**핵심 정정:** 이전 plan 초안에서는 *조희선이 매일 2 wave (09시+14시)* 로 가정했으나, 실제는 *99% 오전 1 wave, 1% 예외 오후 추가*. 박종성도 *고정 시간 wave가 아니라 trigger 기반 (자율 호출)*.

**Wave 그룹화 알고리즘 (2 모드):**

*A. 시간 고정 Wave 모드 (이장훈·조희선):*
1. 매일 08:30 시스템 자동 스캔
2. 출하확정일 = today + (퀵) 0 / (택배) 0~1 인 미발송 shipment 추출
3. 지역(`Shipment.수령인_주소`) + CBM 합산
4. 기사별 capacity 매칭 (이장훈 ≤3건 소형 / 조희선 콘솔 ≤6건)
5. 09:00 wave 자동 확정 → Slack 알림 (운영자 검토·승인)

*B. Trigger 기반 Wave 모드 (박종성):*
1. 시간 고정 X — 박종성이 *"출발 가능" 자발 호출* 또는
2. CBM 임계(예: ≥5m³) 모이면 시스템이 *제안 알림* (강제 X)
3. 잔여 1~2건도 lightweight wave 허용 (당일 추가 주문 대응)
4. 시스템은 *추천만*, 결정은 박종성 자율

**예시 하루 시나리오 (2026-05-28 가상):**
```
03:00 박종성 "새벽 상차" → W3-1 wave 출발 (4건, 충청·강원)
08:30 시스템 자동 스캔 → W1·W2 추천
09:00 W1 출발 (이장훈 3건) + W2 출발 (조희선 6건)
12:00 추가 주문 5건 → 박종성 W3-2 trigger
15:00 잔여 2건 → 박종성 W3-3 lightweight wave
→ 합계 20건, 차량 3대 (자체 기사만)
```

**구현 위치:** `dispatch_advisor.py` 갱신 + Airtable `Shipment.wave_group` 필드 신규 (singleSelect: W1·W2-기본·W2-예외·W3) + 신규 `harness/dispatch/wave_planner.py` (시간 고정 wave) + 신규 `harness/dispatch/wave_trigger.py` (박종성 trigger 기반)

### 3.3 자율 Carrier 분기 RFQ + 3PL 파트너 정기 리뷰 (Axis 3)

**자율 Carrier (로젠·고고엑스):**
- 분기 1회 RFQ — 단가·SLA 비교 → 단가 협상
- Scorecard: Cost / OTIF / Capacity / Damage rate / Claim 처리 시간

**3PL 파트너 (다영·베스트원·로지비):**
- 분기 1회 운영 리뷰 — 단가가 아니라 *서비스 품질·정확도·소통* 중심
- Scorecard: 임가공 품질 / 보관 정확도 / 출고 정시율 / 클레임 / 비용
- 단가 협상은 *연 1회 계약 갱신 시점*에 집중

### 3.4 Carrier × 자체기사 통합 Scorecard 설계

5축 평가 (D-TMS2 tms-carrier 표준 + 신시어리 맞춤):

| 축 | 가중치 | 자체 기사 측정 | Carrier·3PL 측정 |
|----|------|------------|---------------|
| Cost | 25% | 고정비÷처리건수 (CBM당) | 운임÷CBM |
| Reliability (OTIF) | 30% | 약속납기 준수율 | 약속납기 준수율 |
| Capacity | 15% | 일 처리 건수·CBM | 월간 처리 가능 CBM |
| Damage / Quality | 15% | 파손·클레임 건수 | 파손·클레임 건수 |
| Flexibility | 15% | 시간창 유연성 | 임시 추가 capacity 응답성 |

**리뷰 주기:**
- 월 1회 Scorecard 자동 산출 (대시보드)
- 분기 1회 공식 리뷰 (SCM실 회의)
- 연 1회 계약 갱신 의사결정

---

## 4. KPI 셋 (5개)

| KPI | 이름 | 산식 | 목표 | Owner |
|-----|------|------|------|-------|
| K-LC-1 | 비수기 자체 기사 활용도 | (실 처리건수 ÷ 일 capacity) 월 평균 | 비수기 baseline (Sub-Spec 1 후 측정) 대비 +20%p ↑ | 물류파트장 |
| K-LC-2 | 통합 적재 Wave 비중 | (wave 처리 건수 ÷ 전체 자체기사 건수) | 70%+ (조희선·박종성) | 물류파트장 |
| K-LC-3 | 외주 spillover 비용 | (고고엑스 spillover 운임 합계) 월 | 성수기 baseline 대비 -20% | 물류파트장 |
| K-LC-4 | 자율 Carrier 단가 추세 | 로젠·고고엑스 CBM당 단가 (분기) | 분기 -3% 또는 유지 | 물류파트장 |
| K-LC-5 | Lane×Carrier Scorecard | 5축 가중 점수 (월) | 모든 carrier ≥ 70/100 | 물류파트장 |

**기존 16-Card KPI(K6 운반비/매출, K10 OTIF) 연계:**
- K-LC-3 + K-LC-4 → K6 (운반비/매출 ↓) 직접 기여
- K-LC-2 → 통합 적재로 K10 OTIF 보조

---

## 5. 구현 단계 (Sub-Spec 분해 — writing-plans 다음 단계 입력)

### Sub-Spec 1: 자원 매핑 데이터 SSOT (1~2주)
- Airtable `tms_drivers` 신규 테이블 (3명 + 차량 spec + 고정비 + 계약 + 거주지)
- Airtable `tms_3pl_partners` 신규 테이블 (5개사 + 위치 + 역할 + 자율여부)
- `dispatch_advisor.py` 갱신 (CA-0004 김민준 → 조희선, 정확 spec 반영)

### Sub-Spec 2: 비수기 흡수 룰 + 시즌 모드 (2~3주)
- `harness/dispatch/seasonal_mode.py` — 성수기/비수기 자동 전환 (11월~2월 vs 3월~10월)
- `harness/dispatch/idle_capacity_calc.py` — 일 자체 기사 잔여 capacity 산출
- 외주 임가공·재고이동 후보 자동 매칭 룰

### Sub-Spec 3: 통합 적재 Wave 알고리즘 (3~4주) — 2 모드 동시 지원
- `harness/dispatch/wave_planner.py` — *시간 고정 모드* (이장훈·조희선): 매일 08:30 자동 스캔, 09:00 wave 확정
- `harness/dispatch/wave_trigger.py` — *Trigger 기반 모드* (박종성): CBM 임계 또는 자발 호출 시 wave 추천
- Airtable `Shipment.wave_group` 필드 신규 (singleSelect: W1 / W2-기본 / W2-예외 / W3)
- 자체 기사 wave 우선 채움 + 잔여 외주 (로젠·고고엑스)
- *조희선 W2 = 99% 1회 / 1% 예외 오후 — 예외는 수동 발동만 (시스템 자동 trigger X)*

### Sub-Spec 4: Carrier × 자체기사 Scorecard 대시보드 (2~3주)
- `harness/scorecard/calc.py` — 5축 월별 점수
- `pages/dashboard.html`에 위젯 추가 또는 `sincerely-scm-dashboard/` 페이지 신규
- 자율 Carrier(로젠·고고엑스) 분기 RFQ 양식 (Markdown 템플릿)

### Sub-Spec 5: KPI 측정 + 6개월 ROI 리뷰 (지속)
- K-LC-1~5 자동 산출 + 월간 리포트
- 6개월 후 *실측 ₩ 임팩트 vs 가설 0.3~0.7억* 비교
- 결과 기반 Option C 진입 여부 결정

**예상 총 기간:** 4~6주 (Sub-Spec 1~4 병렬·순차 혼합)

---

## 6. 주요 수정 대상 파일

| Sub-Spec | 수정/생성 대상 |
|---------|--------------|
| 1 | Airtable 신규: `tms_drivers`, `tms_3pl_partners` / `harness/virtual_sap/agents/dispatch_advisor.py` 갱신 (line 50~54) |
| 2 | 신규: `harness/dispatch/seasonal_mode.py`, `harness/dispatch/idle_capacity_calc.py` |
| 3 | 신규: `harness/dispatch/wave_planner.py` / Airtable Shipment 필드: `wave_group` (singleSelect) |
| 4 | 신규: `harness/scorecard/calc.py` / `pages/dashboard.html` 위젯 추가 또는 `sincerely-scm-dashboard/` 페이지 |
| 5 | 신규: `harness/kpi/lane_consolidation_kpi.py` / 월간 리포트 자동 발송 |

---

## 7. Open Decisions (사용자 확정 필요)

1. **이장훈 차량 정확 CBM** — 스타리아 화물칸 추정 4~5m³ → 등록증/현대 카탈로그로 확정
2. **조희선·박종성 차량 spec** — CBM, 차종 확인
3. **베스트원 재고이동 자체 흡수 협의** — 베스트원과 *비수기 한정 일부 자체 흡수* 가능 여부 협의 필요
4. **다영기획 퀵 90% → 100%** — 다영기획과 협의해 완전 박종성 흡수 가능 여부
5. **Wave 시각 (2026-05-27 사용자 모두 확정):** 이장훈 W1 = 09:00 / 조희선 W2 = 09:00 이전 마감 99% (1% 예외 오후) / 박종성 W3 = 유연 trigger (시간 자유) — *추가 Open Decision 없음*
6. **Sub-Spec 5개 진행 순서·병렬화 결정** — 1·2·3 순차 vs 1+2 병렬 vs 전체 병렬

---

## 8. Risks

| # | 리스크 | 영향도 | 완화 방안 |
|---|-------|------|---------|
| 1 | 베스트원 재고이동 자체 흡수 협의 거부 — 거리 Lock-in 유지 | 🟡 Med | Plan §3.1 *시범 운영* 1개월 → 데이터로 협의 |
| 2 | 통합 적재 wave가 출고지시 발행 일정 변경 동반 → CX팀 업무 변경 | 🟡 Med | wave 시간창 협의 + 1개월 grace period |
| 3 | 비수기 idle 측정 데이터 부재 — baseline 산출 어려움 | 🟢 Low | Sub-Spec 1 완료 후 1개월 데이터 축적 후 추정 |
| 4 | 자체 기사들이 *룰 명문화*를 부담스러워함 (속인적 운영 익숙) | 🟡 Med | 기사들과 사전 협의 + 기존 패턴(콘솔·임가공 90%)을 *공식 인정*하는 측면 강조 |
| 5 | 자율 Carrier RFQ에 로젠·고고엑스가 단가 안 내려줌 — 시장 협상력 약함 | 🟢 Low | 신규 carrier 발굴 옵션 보류 (현재 5개 충분) |

---

## 9. Verification

각 Sub-Spec 공통:
1. **Pre-deploy**: harness-validator + feature-dev:code-reviewer 병행
2. **Post-deploy +1주**: KPI K-LC-1~5 중 해당 측정 가능 확인
3. **Post-deploy +1개월**: 실측 ₩ 임팩트 vs 가설 비교 → Notion AgentOps + Obsidian log

**E2E 검증 시나리오 (Sub-Spec 1~4 완료 후):**
1. 비수기 자체 기사 활용도 50% → 70%+ 달성 (3개월 평균)
2. 통합 적재 Wave 비중 70%+ (조희선·박종성)
3. 외주 spillover 비용 baseline 대비 -10%+ (성수기 1Q 측정)
4. Lane×Carrier Scorecard 5개사 모두 ≥ 70/100
5. 6개월 누적 ₩ 임팩트 *0.3~0.7억* 실측 검증

---

## 10. Out of Scope (이번 전략 범위 외)

- **거리 Lock-in carrier 변경** (베스트원 광주 → 자체 흡수 / 로지비 이천 → 다른 풀필먼트) — H3 거점 재설계 필요
- **자체 기사 인사·계약 변경** (Option C — 이장훈 오후 활용, 조희선 변동비화 등) — 별도 brainstorm + HR·법무 협의 필요
- **신규 carrier 발굴** — 현재 5개사로 충분, 추가는 K-LC-3 spillover 증가 시 검토
- **고객 지정 외주 변경** (다영기획 택배·로지비 등) — 영업·CX팀 협의 필요, 본 brainstorm 범위 아님
- **로봇·자동화 CapEx** (W-H3-01) — H3 후보, 본 전략 후

---

## 11. 관련 문서

- *모체:* [`SCM-FinanceStrategy-2026-05-21.md`](./SCM-FinanceStrategy-2026-05-21.md) — 16개 후보 카탈로그 (T-H2-01 + T-H2-02 통합)
- *상세:* [`SCM-FinanceStrategy-16Cards-2026-05-22.md`](./SCM-FinanceStrategy-16Cards-2026-05-22.md) — 16-Card 8-필드 분해
- *Plan:* `groovy-brewing-sparrow.md` §11.7 — Sprint 우선순위 재조정
- *회의록:* `sincerely-meeting-notes/260522_전략회의_재무KPI연계전략_MH트래킹.md`
- *코드 참조:* `harness/virtual_sap/agents/dispatch_advisor.py` (line 50~54 갱신 대상)
- *Airtable 참조:* TMS base `app4x70a8mOrIKsMf` — `Shipment`(tbllg1JoHclGYer7m) + `배송파트너`(tblI4ZXrte7WyhXyd) + `운임단가`(tblQA1ev9fjbowUoP)

---

> **다음 단계:** `superpowers:writing-plans` 스킬로 Sub-Spec 1 (자원 매핑 SSOT)의 implementation plan 작성 → Validation Contract 포함.

---

## 12. Addendum v3 (2026-05-27 후반) — 자동 시스템 결정 + Backtest 통합 + 새 조건

본 design doc 작성 후 *추가 brainstorm + Backtest + 사용자 결정*으로 다음 사항 확정. 상세는 **Master Roadmap v3** (`docs/superpowers/plans/2026-05-27-lane-strategy-master-roadmap-v3.md`) 참조.

### 12.1 사용자 결정 사항 (2026-05-27)

| # | 결정 | 사유 |
|---|-----|------|
| 1 | **자동 시스템 (옵션 C) 진행** — DSS 하이브리드 모델 | 사용자 수동 강점 인정 + 시스템 보조 |
| 2 | **자동 대상 = project + 이동목적 ∈ {고객납품, 생산샘플}** | 재고이동·기타는 수동 (100% 자동 불가 인정) |
| 3 | **CBM 추정 시점 분기** — 임가공 전(`최종 출하 품목`) / 후(`최종 출고 품목 및 수량`) | 사용자 운영 현실 반영 |
| 4 | **Product 테이블(344 records) 매칭으로 예상 CBM** | 매칭률 80%+ 추정 — sample 검증 완료 |
| 5 | **가정 기반 OTIF** — 퀵·자체기사 = 출하완료=OTIF / 택배 = +3일 추정 | POD 입력 불가능, 운영 가정 코드화 |
| 6 | **에스에스아이팩 제거** (Status=inactive) | 운영 종료, 과거 record link 보존 |
| 7 | **Airtable polling 3회/일** (09·14·17시) + 7일 rolling | webhook은 over-engineering |
| 8 | **자동화 목표 70~80%** (100% 시도 X) | SAP 글로벌 표준도 프로젝트 기반은 60~80% |

### 12.2 Backtest 결과 (2026-05-27, 26년 1,640건 sample 100건)

- 자체 기사 50% 가동 = 베스트 프랙티스 정착
- 멀티 파트너 0건 = wave 충돌 거의 없음
- POD 100% NULL → 가정 모델로 우회 (사용자 결정 5)
- CBM 44% NULL → Product 매칭 엔진으로 우회 (Sub-Spec 2)
- 구간유형 97% 채워짐 = 양호
- 상세: `_AutoResearch/SCM/outputs/2026-05-27-lane-strategy-backtest-2026.md`

### 12.3 ROI 재추정 (이전 보수 → v3 개선)

- 이전 (Backtest 후): 회수 2~3년
- v3 (CBM 매칭 가능성 + 자동 대상 필터): **회수 0.5~1년** (연 0.25~0.49억 절감)

### 12.4 Sub-Spec 5개 구조 (v3 최종)

1. **Sub-Spec 1** (Plan v2 commit 0363050) — 자원 매핑 SSOT
2. **Sub-Spec 2** — CBM 추정 엔진 (Product 매칭) — *다음 즉시*
3. **Sub-Spec 3** — Wave 추천 엔진 (자동 대상 + 분할 배송 + 7일 rolling)
4. **Sub-Spec 4** — Change Detection + 가정 OTIF (polling 3회/일)
5. **Sub-Spec 5** — Scorecard + KPI + 6개월 ROI 리뷰

### 12.5 SAP 글로벌 표준 비교 (사용자 질문 답)

- SAP 100% 자동화 = *대량 표준 출하* (Amazon FBA·쿠팡 풀필먼트)에서만
- 프로젝트형 제조 (신시어리 같은 굿즈·임가공 협력) = SAP도 60~80%
- *Airtable 기반 70% = SAP 70%와 기능적 동등* + 도입 비용 0원 vs 수십억

→ **신시어리 규모에서는 Airtable 기반이 SAP보다 합리적**

---

> **v3 산출:**
> - Master Roadmap: `docs/superpowers/plans/2026-05-27-lane-strategy-master-roadmap-v3.md`
> - Sub-Spec 1 plan: `docs/superpowers/plans/2026-05-27-sub-spec-1-resource-mapping-ssot.md` (commit 0363050, 그대로 유지)
> - Sub-Spec 2~5 plan: 진입 시점에 별도 작성
