# Paperclip AI Team Design Spec
> Claude Code (실행 엔진) + Paperclip (관제탑) 이중 운영 모델

**Date**: 2026-04-06
**Status**: Draft
**Author**: Jisu + Claude

---

## 1. Context & Problem

현재 Claude Code에서 SCM_WORK(14 에이전트) + STOCK_WORK(5 에이전트)를 CLI 기반으로 운영 중.
이 에이전트들은 Airtable MCP 쓰기, 코드 수정, 매매 판단 등 **실행** 중심 역할을 수행한다.

**문제**: 실행은 잘 되지만, 운영 상태를 지속적으로 감시하고 이상을 자동 감지하는 "관제" 기능이 부족하다.

**해결**: Paperclip(localhost:3100)을 관제탑으로 도입하여, 읽기 전용 모니터링 + 판단 + 이슈 보고를 수행한다.

---

## 2. Architecture: 관제탑 모델 (Approach A)

```
┌───────────────────────────────────────────────────────────┐
│                      사용자 (지수)                          │
│            이슈 확인 · 판단 · Claude Code 지시               │
└──────────┬────────────────────────────────┬───────────────┘
           │ 지시·피드백                      │ 이슈 확인
           ▼                                ▼
┌──────────────────────┐      ┌─────────────────────────────┐
│   Claude Code        │      │   Paperclip (localhost:3100) │
│   (실행 엔진)         │      │   (관제탑 — 읽기 전용)        │
│                      │      │                             │
│  • 기획·설계          │      │  SCM_Company  (6 에이전트)   │
│  • Airtable MCP 쓰기  │      │  Stock_Company (6 에이전트)  │
│  • 코드 수정·배포     │      │                             │
│  • 매매 실행 판단     │      │  총 12 에이전트              │
└──────────────────────┘      └─────────────────────────────┘
       쓰기 권한                       읽기 전용
```

### 핵심 원칙
- Paperclip은 **절대 데이터를 수정하지 않음** (관찰 → 판단 → 보고만)
- 실행(쓰기)은 **항상 Claude Code**에서 수행
- 피드백 방식: **하이브리드** (수동 시작 → 안정 후 자동화 검토)
- 토큰 절약: On-demand only (Heartbeat 자동실행 없음, 태스크 할당 시에만)

---

## 3. 글로벌 표준 참조 체계

4대 참조 축 기반 설계 (글로벌 스탠다드 준수율 85/100):

| 표준 | 준수 | 적용 내용 |
|------|------|---------|
| **SAP** EWM/TM/MM | 85% | Movement Type 14종, Quant/Bin/Batch, Freight Order, VL01N |
| **APICS** CPIM/CLTD/CSCP | 90% | Safety Stock/ROP/EOQ 산식, Wave, FIFO/FEFO, AQL, Dock-to-Stock |
| **SCOR** v2.0 | 80% | Source/Deliver/Return 완전, Plan/Make 부분 구현 |
| **GS1** | 40% | SSCC(AI 00) Mod-10 구현, GTIN/EAN-13/GLN 필드 누락 (Critical Gap) |

### SAP Movement Type 매핑 (INSERT ONLY + Storno 역분개)

| 코드 | SAP Tx | 의미 | 재고 영향 |
|-----|--------|------|----------|
| 101 | MIGO | 구매입고 | +증가 |
| 102 | MIGO | 입고취소 | -감소 (역분개) |
| 122 | MIGO | 공급사반품 | -감소 |
| 161 | MIGO | 고객반품입고 | +증가 |
| 201 | MB1A | 원가센터출고 | -감소 |
| 261 | MB1A | 생산투입 | -감소 |
| 301 | MIGO | 재고이전 | ±이전 |
| 501 | MB1C | PO없는입고 | +증가 |
| 551 | MB1A | 폐기출고 | -감소 |
| 561 | MB1C | 초기재고 | +증가 |
| 601 | VL01N | 납품출고 | -감소 |
| 701 | MI07 | 재고조정(+) | +증가 |
| 702 | MI07 | 재고조정(-) | -감소 |

---

## 4. SCM_Company (6 에이전트)

### 4-1. 조직도

```
SCM_Company CEO
├── WMS-Analyst        입고·출고·재고·반품 통합 감시
├── TMS-Analyst        출하·배송·OTIF 감시
├── SAP-Accountant     분개·이동유형·기간마감 검증
├── PM-Controller      일정·리스크·KPI 종합
└── Ops-Alert          파이프라인 종합 건강점수 산출
```

### 4-1a. Airtable 테이블 → 에이전트 매핑

**TMS Base** (`app4x70a8mOrIKsMf`) — 10개 테이블:

| 테이블 | 건수 | 담당 에이전트 |
|--------|------|-------------|
| Shipment | 349건 | TMS-Analyst |
| 배송파트너 | - | TMS-Analyst |
| 배차일지 | 102건 | TMS-Analyst |
| OTIF | 348건 | TMS-Analyst |
| 배송이벤트 | 349건 | TMS-Analyst |
| 운임단가 | 15건 | SAP-Accountant |
| 배송SLA | 9건 | TMS-Analyst |
| 배송클레임 | 0건 | TMS-Analyst |
| 정산관리 | 2건 | SAP-Accountant |
| 택배추적로그 | 73건 | TMS-Analyst |

**WMS Base** (`appLui4ZR5HWcQRri`) — 10개 테이블:

| 테이블 | 상태 | 담당 에이전트 |
|--------|------|-------------|
| ⚡movement | 운영중 | WMS-Analyst |
| ⚡material (parts-stock) | 운영중 | WMS-Analyst |
| ⚡sync_parts | 운영중 | WMS-Analyst |
| ⚡sync_partner | 운영중 | WMS-Analyst |
| ⚡logistics_release | 운영중 | WMS-Analyst |
| ⚡purchasing | 운영중 | WMS-Analyst |
| ⚡real_stock | 미운영 | WMS-Analyst |
| ⚡실사문서 | 미운영 | WMS-Analyst |
| ⚡실사카운트 | 미운영 | WMS-Analyst |
| ⚡실사결과_클로징 | 미운영 | WMS-Analyst |

### 4-2. 에이전트 역할

| # | 에이전트 | Claude Code 대응 | 역할 |
|---|---------|-----------------|------|
| 1 | **CEO** | Orchestrator | 이슈 트리아지, 에이전트 위임, 보드 보고 |
| 2 | **WMS-Analyst** | SK-01~04, SK-07 | Wave·피킹·패킹·입고·검수·재고·반품 모니터링 |
| 3 | **TMS-Analyst** | SK-05~06 | Shipment·배송이벤트·OTIF·택배사별 분석 |
| 4 | **SAP-Accountant** | D2 세무회계 | 차대불일치·미분개·이동유형·기간마감·더존 동기화 |
| 5 | **PM-Controller** | D5 프로젝트매니저 | 스프린트 진행률·리스크 등급·전체 KPI 종합 |
| 6 | **Ops-Alert** | (신규) | 개별 리포트 → "오늘의 SCM 건강점수" 1장 종합 |

### 4-3. 이슈 생성 기준

#### WMS-Analyst

| 카테고리 | 조건 | 심각도 | 이슈 제목 |
|---------|------|--------|----------|
| Wave | 미처리 Wave > 5건 | Medium | `[BACKLOG] 미처리 Wave {N}건 적체` |
| Wave | Wave 생성 후 24h 미착수 | High | `[DELAY] Wave {ID} 24시간 미착수` |
| 피킹 | 피킹 정확도 < 99% | High | `[QUALITY] 피킹 정확도 {N}%` |
| 피킹 | 피킹 평균소요시간 > 기준 2배 | Medium | `[SLOW] 피킹 평균 {N}분 — 기준 초과` |
| 패킹 | SSCC 누락 건 존재 | Critical | `[MISSING] SSCC 미부여 패킹 {N}건` |
| 패킹 | 패킹 완료 후 미출하 > 12h | High | `[STUCK] 패킹 완료 미출하 {N}건` |
| 입고 | Dock-to-Stock > 48h | High | `[SLOW] Dock-to-Stock {N}시간` |
| 입고 | ASN 대비 수량 불일치 | Critical | `[MISMATCH] GR {ID} ASN 수량 차이 {N}` |
| 검수 | AQL 불합격률 > 5% | High | `[DEFECT] 검수 불합격률 {N}%` |
| 마스터 | 바코드 미등록 품목 출고 시도 | Critical | `[MASTER] 바코드 미등록 품목 {code}` |
| 마스터 | ROP 미설정 활성 품목 | Medium | `[CONFIG] ROP 미설정 품목 {N}건` |
| 재고 | qty_on_hand < 0 발생 | Critical | `[NEGATIVE] {item_code} 음수재고 감지` |
| 재고 | Airtable <> Supabase 차이 | Critical | `[SYNC] 재고 불일치 {N}건 감지` |
| 재고 | 재고 정확도 < 99% | High | `[ACCURACY] 재고정확도 {N}%` |
| 재고 | A등급 품목 < 안전재고 | Critical | `[SAFETY] A등급 {item} 안전재고 미달` |
| 재고 | Zap webhook 실패 로그 | High | `[ZAP] 동기화 실패 {N}건` |
| 재고 | 사이클카운팅 예정일 미실시 > 3일 | Medium | `[OVERDUE] 사이클카운팅 {N}일 지연` |
| 재고 | 이동유형 미매칭 트랜잭션 | High | `[TYPE] 이동유형 미매칭 {N}건` |
| 반품 | 월간 반품율 > 3% | High | `[RETURN] 반품율 {N}% 기준 초과` |
| 반품 | 반품 접수 후 미처리 > 72h | High | `[PENDING] 반품 미처리 {N}건` |
| 반품 | DISPOSE 비율 > 20% | Medium | `[DISPOSE] 폐기 비율 {N}% — 원인 분석 필요` |
| 반품 | 특정 공급사 반품 > 5건/월 | High | `[SUPPLIER] {공급사} 반품 {N}건 집중` |
| 반품 | QC_HOLD 구역 체류 > 7일 | Medium | `[QC_HOLD] {N}건 7일 초과 체류` |
| 자재 | 가용재고 < 안전재고 (설정된 품목) | Critical | `[STOCK] {자재} 안전재고 미달 — 가용 {N}` |
| 자재 | 안전재고수량 미입력 활성 품목 | Medium | `[MASTER] 안전재고 미설정 {N}건` |
| 자재 | ABC등급 미입력 품목 | Medium | `[MASTER] ABC등급 미분류 {N}건` |
| 자재 | 자재상태 미입력 (활성/비활성 불명) | Medium | `[MASTER] 자재상태 미설정 {N}건` |
| 출고지시 | 출고지시 상태 "대기" > 24h | High | `[RELEASE] 출고지시 {N}건 24시간 미처리` |
| 출고지시 | 출고지시 대비 실출고 수량 불일치 | High | `[RELEASE] 출고 수량 불일치 {N}건` |
| 구매 | PO 발주 후 미입고 > 리드타임+3일 | High | `[PO] {PO번호} 입고 지연 — 리드타임 초과` |
| 구매 | 미입하 PO 누적 > 10건 | High | `[PO] 미입하 PO {N}건 적체` |
| 실사 | 실사 계획일 대비 미실시 > 7일 | High | `[COUNT] 실사 미실시 {N}일 지연` |
| 실사 | 실사 결과 차이율 > 3% | High | `[COUNT] 실사 차이율 {N}% — 기준 초과` |
| 실사 | 시정조치 미완료 > 14일 | Medium | `[COUNT] 시정조치 미완료 {N}건` |

#### TMS-Analyst

| 카테고리 | 조건 | 심각도 | 이슈 제목 |
|---------|------|--------|----------|
| OTIF | OTIF 종합 < 93% | Critical | `[OTIF] 종합 {N}% — 목표 미달` |
| OTIF | On-Time Rate < 95% | High | `[OTIF] 정시율 {N}% 미달` |
| OTIF | In-Full Rate < 98% | High | `[OTIF] 완전납품율 {N}% 미달` |
| 출하 | 출하 대기 > 48h | High | `[DELAY] 출하대기 {N}건 48h 초과` |
| 출하 | 택배사별 지연 편중 > 30% | Medium | `[CARRIER] {택배사} 지연율 {N}%` |
| 배송 | 배송 이벤트 24h 미갱신 | Medium | `[TRACKING] SHP-{ID} 추적 끊김` |
| 배송 | POD 미처리 > 72h | High | `[POD] POD 미확인 {N}건` |
| 택배사 | 특정 택배사 클레임 > 3건/주 | High | `[CLAIM] {택배사} 주간 클레임 {N}건` |
| 파트너 | 특정 파트너 월간 OTIF달성률 < 90% | High | `[PARTNER] {파트너} OTIF {N}% — 성과 미달` |
| 파트너 | 파트너 파손건수 > 3건/월 | High | `[PARTNER] {파트너} 파손 {N}건 — 품질 문제` |
| 파트너 | 파트너 클레임건수 급증 (전월 대비 2배) | Critical | `[PARTNER] {파트너} 클레임 급증 {N}건` |
| 배차 | 차량이용률 < 50% | Medium | `[DISPATCH] 차량이용률 {N}% — 비효율` |
| 배차 | 차량이용률 > 100% (오버부킹) | Critical | `[DISPATCH] 오버부킹 감지 — 이용률 {N}%` |
| 배차 | 배정물량 0인 날 존재 | Medium | `[DISPATCH] {date} 미배차 — 운영 공백` |
| 배차 | 일일 배정물량 전주 평균 대비 150% 초과 | High | `[DISPATCH] 배정물량 급증 {N}건 — 용량 점검` |
| SLA | 구간별 실제 배송일수 > 목표배송일수 | High | `[SLA] {구간} 배송 {N}일 — 목표 {M}일 초과` |
| SLA | SLA 유효시작일 만료 후 미갱신 | Medium | `[SLA] {구간} SLA 기준 만료 — 갱신 필요` |
| SLA | 패널티조건 해당 건수 > 0 | High | `[SLA] 패널티 해당 {N}건 — 비용 발생 가능` |
| 클레임 | 미처리 클레임 > 7일 | High | `[CLAIM] 미처리 클레임 {N}건 7일 초과` |
| 클레임 | 클레임 유형별 편중 (파손 > 50%) | Medium | `[CLAIM] 파손 클레임 비율 {N}% — 포장 점검` |
| 클레임 | 보상금액 월 누계 > 기준금액 | Critical | `[CLAIM] 월 보상금액 W{N} — 예산 초과` |
| 클레임 | 동일 배송파트너 클레임 반복 > 3회 | High | `[CLAIM] {파트너} 반복 클레임 — 계약 검토` |
| 추적 | 추적상태 "미배달" > 48h | High | `[COURIER] {운송장} 미배달 48시간 초과` |
| 추적 | Shipment 연결 누락 (orphan 로그) | Medium | `[COURIER] 미연결 추적로그 {N}건` |
| 추적 | 택배사별 평균 배송시간 급증 | Medium | `[COURIER] {택배사} 평균배송 {N}시간 — 지연 추세` |

#### SAP-Accountant

| 카테고리 | 조건 | 심각도 | 이슈 제목 |
|---------|------|--------|----------|
| 분개 | 차변합 != 대변합 | Critical | `[BALANCE] 차대불일치 {N}원` |
| 분개 | 재고 이동 후 미분개 > 24h | High | `[UNPOSTED] 미분개 거래 {N}건` |
| 이동유형 | SAP 이동유형 매핑 오류 | Critical | `[MOVTYPE] {type} 매핑 불일치` |
| 기간마감 | 마감 예정일 D-3 미완료 항목 | High | `[CLOSING] 기간마감 미완료 {N}건` |
| 동기화 | 더존 아마란스10 전송 실패 | High | `[DOUZONE] 동기화 실패 {N}건` |
| 운임 | 운임단가 유효시작일 만료 후 미갱신 > 30일 | High | `[FREIGHT] {구간} 운임단가 만료 — 갱신 필요` |
| 운임 | 동일 구간 복수 단가 존재 (중복) | Medium | `[FREIGHT] {구간} 단가 중복 {N}건` |
| 운임 | CBM당 운임 전분기 대비 +20% 이상 인상 | High | `[FREIGHT] {구간} 운임 급등 +{N}%` |
| 정산 | 물류손익 음수 (물류매출 < 총물류비) | Critical | `[SETTLE] {프로젝트} 물류 적자 W{N}` |
| 정산 | 정산상태 "미정산" > 월말+15일 | High | `[SETTLE] {정산월} 미정산 — 지연 {N}일` |
| 정산 | 세금계산서번호 미발행 건 | High | `[SETTLE] 세금계산서 미발행 {N}건` |
| 정산 | 운송비 전월 대비 +30% 이상 급증 | Medium | `[SETTLE] 운송비 급증 +{N}%` |

#### Ops-Alert (SCM 건강점수 종합)

| 카테고리 | 조건 | 심각도 | 이슈 제목 |
|---------|------|--------|----------|
| KPI | QC 불량률 > 10% (현재 20.6%) | Critical | `[HEALTH] QC 불량률 {N}% — Q2 목표 5% 대비 심각` |
| KPI | 음수재고 건수 > 0건 (현재 331건) | Critical | `[HEALTH] 음수재고 {N}건 — Q2 목표 0건` |
| KPI | 미입하 건수 > 30건 (현재 107건) | High | `[HEALTH] 미입하 {N}건 — Q2 목표 10건` |
| KPI | 차량이용률 < 50% (현재 27~57%) | Medium | `[HEALTH] 차량이용률 {N}% — Q2 목표 70%` |

### 4-4. 데이터 접근

Airtable REST API (읽기 전용 PAT):
```
GET https://api.airtable.com/v0/{baseId}/{tableName}
Headers: Authorization: Bearer {READ_ONLY_PAT}
```

---

## 5. Stock_Company (6 에이전트)

### 5-1. 조직도

```
Stock_Company CEO (Tax 룰 검증 내장)
├── Fundamental-Analyst   기업가치·매크로·어닝
├── Quant-Strategist      기술분석·VaR·상관관계
├── Market-Scanner        공시·수급·내부자·레버리지
├── Portfolio-Monitor     P&L·비중·MDD·데이터품질
└── Risk-Sentinel         전 포지션 통합 리스크 스코어
```

### 5-2. 에이전트 역할

| # | 에이전트 | Claude Code 대응 | 역할 |
|---|---------|-----------------|------|
| 1 | **CEO** | Chief Strategist | 투자 트리아지, Tax 룰 검증 내장, 종합 판단 |
| 2 | **Fundamental-Analyst** | Fundamental Analyst | PER·PBR·ROE·DCF·매크로·금리·GDP·CPI 모니터링 |
| 3 | **Quant-Strategist** | Quant Strategist | RSI·MACD·볼린저·이동평균·VaR·Kelly·상관행렬 |
| 4 | **Market-Scanner** | Market Scanner | 어닝발표·13F·공시·수급 변동·레버리지ETF 변동성끌림 |
| 5 | **Portfolio-Monitor** | (신규) | $20K P&L·포지션비중·MDD·데이터품질 실시간 추적 |
| 6 | **Risk-Sentinel** | (신규) | 전 리스크 종합 → 포트폴리오 위험도 1~10점 산출 |

### 5-3. 현재 포트폴리오 ($20K 시뮬레이션)

| Ticker | 배분 | Entry | Thesis |
|--------|------|-------|--------|
| PLTR | $7,000 (35%) | $148.46 | AI government/enterprise |
| RKLB | $5,000 (25%) | $67.73 | Space launch |
| HIMS | $4,000 (20%) | $19.14 | GLP-1 telehealth |
| APLD | $3,000 (15%) | $24.56 | AI datacenter |
| IONQ | $1,000 (5%) | $29.30 | Quantum computing |

### 5-4. 이슈 생성 기준

#### Portfolio-Monitor

| 카테고리 | 조건 | 심각도 | 이슈 제목 |
|---------|------|--------|----------|
| 손절 | 개별 종목 손실 > -8% | Critical | `[STOP-LOSS] {ticker} 손실 {N}%` |
| 손절 | 개별 종목 손실 > -10% | Critical | `[STOP-LOSS] {ticker} -10% 돌파 — 즉시 행동` |
| MDD | 포트폴리오 MDD > -15% | High | `[MDD] 포트폴리오 MDD {N}%` |
| MDD | 포트폴리오 MDD > -20% | Critical | `[MDD] MDD -20% 돌파 — 전면 리밸런싱` |
| 비중 | 단일종목 > 20% | High | `[WEIGHT] {ticker} 비중 {N}% — 20% 초과` |
| 비중 | 단일섹터 > 40% | High | `[SECTOR] {sector} 비중 {N}% — 40% 초과` |
| 수익 | 개별 종목 이익 > +30% | Medium | `[PROFIT] {ticker} +{N}% — 부분 익절 검토` |
| 현금 | 현금 < 5% | Medium | `[CASH] 현금 비중 {N}% — 유동성 부족` |

#### Fundamental-Analyst

| 카테고리 | 조건 | 심각도 | 이슈 제목 |
|---------|------|--------|----------|
| 밸류에이션 | 보유종목 PER > 업종평균 2배 | High | `[VALUATION] {ticker} PER {N}x — 과대평가` |
| 실적 | 어닝 miss > 10% | High | `[EARNINGS] {ticker} EPS miss {N}%` |
| 실적 | 어닝 beat > 15% | Medium | `[EARNINGS] {ticker} EPS beat +{N}%` |
| 매크로 | 금리 변동 (FOMC) | Medium | `[MACRO] FOMC 금리 {N}bp 변동` |
| 매크로 | CPI 예상 대비 +-0.3%p | Medium | `[MACRO] CPI {N}% — 예상 대비 편차` |
| 매출 | QoQ 매출 성장률 급락 > 15%p | High | `[REVENUE] {ticker} 매출성장 급락 {N}%p` |
| 마진 | 영업이익률 전분기 대비 -5%p | High | `[MARGIN] {ticker} 영업이익률 급락` |

#### Quant-Strategist

| 카테고리 | 조건 | 심각도 | 이슈 제목 |
|---------|------|--------|----------|
| RSI | RSI > 70 (과매수) | Medium | `[RSI] {ticker} RSI {N} — 과매수` |
| RSI | RSI < 30 (과매도) | Medium | `[RSI] {ticker} RSI {N} — 과매도` |
| MACD | 데드크로스 | Medium | `[MACD] {ticker} 데드크로스` |
| MACD | 골든크로스 | Medium | `[MACD] {ticker} 골든크로스` |
| 이동평균 | 200일선 하향 이탈 | High | `[MA200] {ticker} 200일선 이탈` |
| 변동성 | 일일 변동성 > 5% | High | `[VOLATILITY] {ticker} 일변동성 {N}%` |
| VaR | 포트폴리오 일일 VaR > 3% | High | `[VAR] 포트폴리오 VaR {N}% 초과` |
| 상관관계 | 포지션간 상관 > 0.8 | Medium | `[CORR] {A}<>{B} 상관 {N} — 분산효과 약화` |

#### Market-Scanner

| 카테고리 | 조건 | 심각도 | 이슈 제목 |
|---------|------|--------|----------|
| 13F | 주요 기관 대량 매도 | High | `[13F] {institution} {ticker} 매도 {N}주` |
| 내부자 | Form 4 내부자 매도 > $1M | High | `[INSIDER] {ticker} 내부자 매도 ${N}M` |
| 내부자 | Form 4 내부자 매수 > $500K | Medium | `[INSIDER] {ticker} 내부자 매수 +${N}K` |
| 공매도 | Short Interest > 20% | High | `[SHORT] {ticker} 공매도 비율 {N}%` |
| 뉴스 | 소송·FDA거부·규제 등 악재 | High | `[NEWS] {ticker} 악재: {headline}` |
| 레버리지 | 변동성끌림 > 3%/월 | Medium | `[DECAY] {ticker} 변동성끌림 {N}%` |
| 거래량 | 거래량 급증 > 평균 3배 | Medium | `[VOLUME] {ticker} 거래량 {N}x 급증` |

#### CEO 내장 Tax 룰 검증

| 카테고리 | 조건 | 심각도 | 이슈 제목 |
|---------|------|--------|----------|
| 양도세 | 연간 양도차익 > W2M | Medium | `[TAX] 양도차익 W{N}M — 면세 한도 접근` |
| 양도세 | 연간 양도차익 > W2.5M | High | `[TAX] 면세 한도 초과 — 22% 과세` |
| 배당세 | 금융소득 > W15M | High | `[TAX] 금융소득 W{N}M — 종합과세 주의` |
| 룰 위반 | 정량분석 미선행 매매 | Critical | `[RULE] 정량분석 미선행 매매 차단` |
| 손익통산 | 손실 확정 시 통산 기회 | Medium | `[TAX-OPT] {ticker} 손실확정 — 통산 검토` |

### 5-5. Risk-Sentinel 종합 위험도 산출

```
Risk Score = w1*기술리스크 + w2*비중리스크 + w3*이벤트리스크 + w4*매크로리스크
  (가중치 합 = 1.0, 기본: 0.3 / 0.25 / 0.25 / 0.2)

1~3점: Green (정상)
4~6점: Yellow (주의)
7~8점: Orange → High 이슈 자동 생성
9~10점: Red → Critical 이슈 + 전면 리밸런싱 권고
```

### 5-6. 데이터 접근

Yahoo Finance REST (읽기 전용):
```
GET https://query1.finance.yahoo.com/v8/finance/chart/{ticker}
  ?interval=1d&range=3mo
Headers: User-Agent: Mozilla/5.0
```

---

## 6. 운영 사이클

```
Phase 1: Claude Code 기획
  └─ 운영 매뉴얼 + 에이전트 지시문 작성

Phase 2: Paperclip 모니터링
  └─ 태스크 할당 시 해당 에이전트만 실행
  └─ 이상 감지 시 이슈 자동 생성

Phase 3: 사용자 이슈 확인
  └─ Paperclip UI(localhost:3100)에서 이슈 리뷰
  └─ 필요하면 Claude Code에 전달

Phase 4: Claude Code 실행
  └─ Airtable 쓰기, 코드 수정, 매매 판단 등 수행

Phase 5: 반영 확인
  └─ Paperclip이 다음 모니터링에서 수정 결과 확인
```

---

## 7. 토큰 절약 원칙

| 원칙 | 적용 |
|------|------|
| On-demand only | Heartbeat 자동실행 없음, 태스크 할당 시에만 |
| CEO 게이트 | 필요한 에이전트에만 위임 |
| 간결한 응답 | SOUL.md에 "표+불릿 3줄 이내" 강제 |
| 읽기 전용 | Airtable read-only PAT, Yahoo Finance GET only |
| 종합 에이전트 | Ops-Alert / Risk-Sentinel이 개별 리포트 압축 |

---

## 8. Phase 2 확장 계획 (안정 후)

필요 시 분리 독립 가능한 후보:
- WMS-Analyst → WMS-Analyst + Inventory-Auditor + Returns-Analyst
- CEO Tax 내장 → Tax-Compliance 독립 에이전트
- Data-Engineer 독립 (FMP API 쿼터 관리)

---

## 9. 이슈 기준 총 집계

| 에이전트 | 이슈 기준 수 | 데이터 소스 |
|---------|------------|-----------|
| **WMS-Analyst** | 33개 | WMS Base 10개 테이블 |
| **TMS-Analyst** | 26개 | TMS Base 8개 테이블 |
| **SAP-Accountant** | 13개 | 운임단가·정산관리·분개 |
| **Ops-Alert** | 4개 | 전체 KPI 종합 |
| **SCM 합계** | **76개** | |
| **Portfolio-Monitor** | 8개 | Yahoo Finance |
| **Fundamental-Analyst** | 7개 | Yahoo Finance |
| **Quant-Strategist** | 8개 | Yahoo Finance |
| **Market-Scanner** | 7개 | Yahoo Finance |
| **CEO Tax** | 5개 | 내부 계산 |
| **Stock 합계** | **35개** | |
| **총 합계** | **111개** | |

---

## 10. 검증 방법

### SCM 테스트
1. Paperclip에서 CEO에게 태스크: "이번 주 출고 상태 점검"
2. CEO → WMS-Analyst + TMS-Analyst 위임
3. 각 에이전트가 Airtable 조회 → 리포트 코멘트
4. Ops-Alert가 종합 건강점수 산출
5. 이상 있으면 이슈 자동 생성 → 사용자 확인

### Stock 테스트
1. CEO에게 태스크: "포트폴리오 일일 진단"
2. CEO → Portfolio-Monitor + Quant-Strategist 위임
3. 각 에이전트가 Yahoo Finance 조회 → P&L/기술분석 리포트
4. Risk-Sentinel이 위험도 점수 산출
5. 7점 이상이면 Critical 이슈 생성 → 사용자 확인

---

## 11. 파일 작업 목록

### Paperclip 파일 (에이전트별 3파일 x 12 = 36파일)

**SCM_Company** (UI에서 회사+6에이전트 생성 후):
- `{CEO}/instructions/AGENTS.md, SOUL.md, HEARTBEAT.md`
- `{WMS-Analyst}/instructions/AGENTS.md, SOUL.md, HEARTBEAT.md`
- `{TMS-Analyst}/instructions/AGENTS.md, SOUL.md, HEARTBEAT.md`
- `{SAP-Accountant}/instructions/AGENTS.md, SOUL.md, HEARTBEAT.md`
- `{PM-Controller}/instructions/AGENTS.md, SOUL.md, HEARTBEAT.md`
- `{Ops-Alert}/instructions/AGENTS.md, SOUL.md, HEARTBEAT.md`

**Stock_Company** (UI에서 회사+6에이전트 생성 후):
- `{CEO}/instructions/AGENTS.md, SOUL.md, HEARTBEAT.md`
- `{Fundamental-Analyst}/instructions/AGENTS.md, SOUL.md, HEARTBEAT.md`
- `{Quant-Strategist}/instructions/AGENTS.md, SOUL.md, HEARTBEAT.md`
- `{Market-Scanner}/instructions/AGENTS.md, SOUL.md, HEARTBEAT.md`
- `{Portfolio-Monitor}/instructions/AGENTS.md, SOUL.md, HEARTBEAT.md`
- `{Risk-Sentinel}/instructions/AGENTS.md, SOUL.md, HEARTBEAT.md`
