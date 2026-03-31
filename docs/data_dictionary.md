# Sincerely SCM 데이터 사전 (Data Dictionary)

> 6개 스키마, 51개 테이블에 대한 전체 컬럼 정의서
> 최종 갱신: 2026-03-30 | 기준: Supabase migrations 002~011

---

## 목차

1. [용어 사전 (General Glossary)](#1-용어-사전-general-glossary)
2. [SAP 이동유형 (Movement Types)](#2-sap-이동유형-movement-types)
3. [K-IFRS 계정과목 (GL Accounts)](#3-k-ifrs-계정과목-gl-accounts)
4. [주요 상태값 정리](#4-주요-상태값-정리)
5. [Schema별 테이블 상세](#5-schema별-테이블-상세)
   - [5.1 shared 스키마 (공통 마스터)](#51-shared-스키마-공통-마스터)
   - [5.2 mm 스키마 (자재관리/구매)](#52-mm-스키마-자재관리구매)
   - [5.3 wms 스키마 (창고관리)](#53-wms-스키마-창고관리)
   - [5.4 tms 스키마 (운송관리)](#54-tms-스키마-운송관리)
   - [5.5 pp 스키마 (생산계획)](#55-pp-스키마-생산계획)
   - [5.6 finance 스키마 (회계)](#56-finance-스키마-회계)

---

## 1. 용어 사전 (General Glossary)

### 핵심 약어

| 약어 | 영문 Full Name | 한글 설명 |
|------|---------------|-----------|
| **PO** | Purchase Order | 구매발주서. 공급사에게 자재를 주문하는 문서 |
| **PR** | Purchase Requisition | 구매요청서. PO를 만들기 전 내부 승인용 문서 |
| **GR** | Goods Receipt | 입고. 자재가 물리적으로 창고에 도착하여 수령하는 행위 |
| **GI** | Goods Issue | 출고. 자재가 창고에서 나가는 행위 (생산투입, 납품 등) |
| **TR** | Transportation Requirement | 운송요청. "이 물건을 여기서 저기로 보내달라"는 요청서 |
| **FO** | Freight Order | 운송오더. TR을 기반으로 실제 차량/택배를 배정한 실행 문서 |
| **LR** | Logistics Release | 물류출고지시. 생산완료품을 창고에서 꺼내 배송 준비하는 지시서 |
| **BOM** | Bill of Materials | 자재명세서. 완제품 1개를 만드는데 필요한 부품/수량 목록 |
| **WIP** | Work In Progress | 재공품. 생산 진행 중인 미완성 제품 |
| **FIFO** | First In, First Out | 선입선출법. 먼저 들어온 재고를 먼저 출고하는 원가계산 방법 |
| **FEFO** | First Expired, First Out | 선만료선출법. 유통기한이 가까운 것부터 먼저 출고 |
| **MOQ** | Minimum Order Quantity | 최소주문수량. 공급사가 요구하는 최소 주문 단위 |
| **ROP** | Reorder Point | 재주문점. 재고가 이 수준 이하로 떨어지면 재주문해야 하는 시점 |
| **UOM** | Unit of Measure | 측정단위 (EA=개, KG=킬로그램, M=미터 등) |
| **CBM** | Cubic Meter | 세제곱미터. 화물 부피를 나타내는 단위 |
| **QC** | Quality Control | 품질관리. 입고/생산 시 품질 검사 |
| **AQL** | Acceptable Quality Level | 합격 품질 수준. 샘플 검사의 합격 기준 |
| **SSCC** | Serial Shipping Container Code | GS1 표준 박스/팔레트 식별 바코드 |
| **OTIF** | On Time In Full | 정시완전납품률. 약속한 날짜에 약속한 수량을 정확히 납품한 비율 |
| **POD** | Proof of Delivery | 배송완료증명. 수령자 서명 등으로 배송 완료를 증명 |
| **RLS** | Row Level Security | Supabase 행 수준 보안정책 |
| **FK** | Foreign Key | 외래키. 다른 테이블의 행을 참조하는 컬럼 |
| **UUID** | Universally Unique Identifier | 범용 고유 식별자 (예: `550e8400-e29b-41d4-a716-446655440000`) |
| **GTIN** | Global Trade Item Number | GS1 국제상품번호 (바코드 번호) |
| **GLN** | Global Location Number | GS1 국제위치번호 (물류거점 식별) |

### SAP 자재유형 코드

| 코드 | SAP 영문명 | 한글 설명 | 예시 |
|------|-----------|-----------|------|
| **ROH** | Raw Material | 원자재. 가공 전 상태의 자재 | 크라프트지, 원단, 잉크 |
| **HALB** | Semi-Finished | 반제품. 중간 가공 단계의 자재 | 인쇄된 종이, 조립된 부품 |
| **FERT** | Finished Good | 완제품. 최종 판매 가능한 제품 | 포장박스 세트, 완성 키트 |
| **VERP** | Packaging Material | 포장재. 제품을 담는 용기/포장 | 골판지박스, 에어캡, 완충재 |
| **HIBE** | Operating Supplies | 소모품. 생산에 쓰이지만 제품에 포함되지 않는 자재 | 테이프, 라벨, 장갑 |
| **HAWA** | Trading Goods | 상품(리셀). 가공 없이 그대로 판매하는 자재 | 기성 쇼핑백 |

### SAP 조달유형 코드

| 코드 | 설명 |
|------|------|
| **E** | In-house (자체 생산) |
| **F** | External (외부 구매) |
| **X** | Both (자체생산 + 외부구매 병행) |

---

## 2. SAP 이동유형 (Movement Types)

이동유형은 재고가 "왜" 이동했는지를 나타내는 코드입니다. 모든 재고 변동은 반드시 이동유형을 가집니다.

| 이동유형 | SAP 트랜잭션 | 한글 명칭 | 상세 설명 | 재고 영향 |
|----------|-------------|-----------|-----------|-----------|
| **101** | MIGO | 구매입고 | PO(구매발주) 기반으로 자재가 창고에 입고됨 | +재고 증가 |
| **102** | MIGO | 입고취소 | 101 입고의 역분개(취소). 잘못 입고한 경우 사용 | -재고 감소 |
| **122** | MIGO | 공급사반품 | 불량/오배송 자재를 공급사에게 반품 | -재고 감소 |
| **161** | MIGO | 고객반품입고 | 고객이 반품한 물건을 다시 창고로 입고 | +재고 증가 |
| **201** | MB1A | 원가센터출고 | 특정 부서/비용센터로 자재 출고 (소모품 등) | -재고 감소 |
| **261** | MB1A | 생산투입출고 | 생산오더를 위해 원자재를 생산라인에 투입 | -재고 감소 |
| **262** | MB1A | 생산반납입고 | 261로 투입했던 자재를 생산라인에서 다시 창고로 반납 | +재고 증가 |
| **301** | MIGO | 재고이전 | 한 저장위치에서 다른 저장위치로 자재 이동 | 출발지(-) / 도착지(+) |
| **309** | MIGO | 예약 없는 이전 | 사전 예약 없이 긴급으로 재고 이전 | 출발지(-) / 도착지(+) |
| **501** | MB1C | PO 없는 입고 | 구매발주 없이 직접 입고 (샘플, 무상 지급 등) | +재고 증가 |
| **551** | MB1A | 폐기출고 | 유통기한 만료, 불량 등으로 자재 폐기 | -재고 감소 |
| **561** | MB1C | 초기재고 | 시스템 도입 시 기존 재고를 초기 등록 | +재고 증가 |
| **601** | VL01N | 납품출고 | 고객에게 완제품을 출하(배송)하기 위한 출고 | -재고 감소 |
| **701** | MI07 | 재고조정(+) | 실사에서 전산보다 실물이 많을 때 플러스 조정 | +재고 증가 |
| **702** | MI07 | 재고조정(-) | 실사에서 전산보다 실물이 적을 때 마이너스 조정 | -재고 감소 |

### Storno (역분개) 원칙

본 시스템은 **INSERT ONLY 불변 원장** 원칙을 따릅니다.
- 잘못된 입고(101)가 있으면 DELETE/UPDATE 하지 않고, 반대 이동유형(102)으로 새 레코드를 INSERT합니다.
- 이것을 **Storno(역분개)** 또는 **취소전표**라 합니다.
- 모든 이력이 보존되어 감사추적(Audit Trail)이 가능합니다.

---

## 3. K-IFRS 계정과목 (GL Accounts)

더존 아마란스10 계정코드 체계 기준. 계정코드 첫째 자리로 계정 성격을 구분합니다.

| 계정코드 범위 | 계정 성격 | 정상잔액 | 설명 | 예시 계정 |
|--------------|-----------|----------|------|-----------|
| **1xxx** | 자산 (Asset) | 차변(Debit) | 회사가 보유한 경제적 자원 | 146000 원재료, 147000 제품, 148000 상품 |
| **2xxx** | 부채 (Liability) | 대변(Credit) | 회사가 갚아야 할 의무 | 251000 매입채무, 255000 미지급금 |
| **3xxx** | 자본 (Equity) | 대변(Credit) | 주주의 지분 | 311000 자본금 |
| **4xxx** | 수익 (Revenue) | 대변(Credit) | 매출 등 수입 | 401000 제품매출, 404000 운송수익 |
| **5xxx** | 비용 (Expense) | 차변(Debit) | 매출원가, 운영비 등 지출 | 501000 매출원가, 520000 운반비 |

### 주요 분개 패턴 (회계 전표 발생 시나리오)

| 거래 유형 | 차변 (Debit) | 대변 (Credit) | 설명 |
|-----------|-------------|---------------|------|
| 원자재 입고 (101) | 146000 원재료 | 251000 매입채무 | 원자재를 매입하여 재고 자산이 늘고, 대금 지급 의무 발생 |
| 생산투입 (261) | 501000 매출원가(WIP) | 146000 원재료 | 원자재를 생산에 투입하여 원가로 전환 |
| 완제품 입고 | 147000 제품 | 501000 매출원가(WIP) | 생산 완료된 제품을 재고 자산으로 인식 |
| 납품출고 (601) | 501000 매출원가 | 147000 제품 | 고객에게 출하하여 재고 감소, 매출원가 인식 |
| 운송비 발생 | 520000 운반비 | 255000 미지급금 | 택배/차량 운송비 발생 |
| 폐기 (551) | 501000 매출원가(폐기손실) | 146000 원재료 | 불량/만료 자재 폐기 처리 |
| 재고 플러스 조정 (701) | 146000 원재료 | 기타수익 | 실사에서 실물이 더 많은 경우 |
| 재고 마이너스 조정 (702) | 기타비용 | 146000 원재료 | 실사에서 실물이 부족한 경우 |

---

## 4. 주요 상태값 정리

### 4.1 구매발주 상태 (mm.purchase_orders.po_status)

| 상태값 | 한글 | 설명 |
|--------|------|------|
| `draft` | 초안 | PO가 작성되었지만 아직 공급사에 발송 안 됨 |
| `sent` | 발송완료 | 공급사에게 PO가 전달됨 |
| `confirmed` | 확인됨 | 공급사가 PO를 확인/승인함 |
| `partial_received` | 부분입고 | 일부 품목만 입고된 상태 |
| `received` | 입고완료 | 모든 품목이 입고 완료 |
| `closed` | 마감 | PO 처리가 모두 끝나서 더 이상 변경 불가 |
| `cancelled` | 취소 | PO 자체가 취소됨 |

### 4.2 운송 상태 (tms.freight_orders.shipping_status)

| 상태값 | 한글 | 설명 |
|--------|------|------|
| `planned` | 계획됨 | 운송 계획이 수립됨 |
| `confirmed` | 확정됨 | 차량/택배사가 배정되어 확정 |
| `in_transit` | 운송중 | 물건이 출발하여 이동 중 |
| `delivered` | 배송완료 | 목적지에 도착하여 수령 완료 |
| `cancelled` | 취소됨 | 운송이 취소됨 |

### 4.3 물류출고지시 상태 (tms.logistics_releases.status)

| 상태값 | 한글 | 설명 |
|--------|------|------|
| `pending` | 대기 | 출고지시가 생성되었으나 작업 미착수 |
| `picking` | 피킹중 | 창고에서 물건을 꺼내는 중 |
| `packed` | 포장완료 | 피킹 후 포장까지 완료 |
| `released` | 출고완료 | 창고에서 물건이 나감 |
| `cancelled` | 취소 | 출고지시가 취소됨 |

### 4.4 재고이동 상태 (mm.stock_movements.status)

| 상태값 | 한글 | 설명 |
|--------|------|------|
| `planned` | 계획됨 | 이동이 예약/계획됨 |
| `in_progress` | 진행중 | 이동이 실행되고 있음 |
| `completed` | 완료 | 이동이 완료됨 |
| `cancelled` | 취소 | 이동이 취소됨 |

### 4.5 생산오더 상태 (pp.production_orders.status)

| 상태값 | 한글 | 설명 |
|--------|------|------|
| `planned` | 계획됨 | 생산 계획 수립 상태 |
| `released` | 릴리스 | 생산 실행 승인됨 (자재 출고 가능) |
| `in_progress` | 생산중 | 실제 생산 진행 중 |
| `completed` | 완료 | 생산 완료, 완제품 입고됨 |
| `cancelled` | 취소 | 생산오더 취소 |

### 4.6 회계전표 상태 (finance.accounting_entries.status)

| 상태값 | 한글 | 설명 |
|--------|------|------|
| `draft` | 초안 | SCM 시스템에서 자동 생성된 전표 초안 |
| `reviewed` | 검토완료 | 담당자가 검토 완료 |
| `posted` | 기표완료 | 더존 아마란스10에 최종 기표됨 |

### 4.7 송장검증 상태 (mm.invoice_verifications.status)

| 상태값 | 한글 | 설명 |
|--------|------|------|
| `pending` | 대기 | 검증 대기 중 |
| `matched` | 일치 | PO/GR/송장 3-way 매칭 완료 |
| `variance` | 차이발생 | 금액 또는 수량 차이 발견 |
| `posted` | 전기완료 | 회계 전표로 전기 완료 |

### 4.8 재고유형 (wms.quants.stock_type)

| 상태값 | 한글 | 설명 |
|--------|------|------|
| `unrestricted` | 자유재고 | 자유롭게 사용/출고 가능한 정상 재고 |
| `quality_inspection` | 품질검사중 | QC 검사가 끝나지 않아 사용 불가 |
| `blocked` | 차단됨 | 품질 문제 등으로 사용이 차단된 재고 |
| `returns` | 반품재고 | 고객 반품으로 돌아온 재고 (재검사 필요) |

---

## 5. Schema별 테이블 상세

---

### 5.1 shared 스키마 (공통 마스터)

공통 마스터 데이터. 모든 다른 스키마에서 참조하는 기준 정보 테이블입니다.
총 14개 테이블.

---

#### 5.1.1 shared.units_of_measure (측정단위 마스터)

> SAP T006 | 모든 수량 필드에서 참조하는 단위 기준표

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| uom_code | VARCHAR(10) | 측정단위 코드 (PK) | MSEHI | `EA`, `KG`, `M`, `SET`, `BOX`, `SHEET`, `ROLL`, `PCS` |
| uom_name | VARCHAR(50) | 단위 이름 | MSEHL | `개`, `킬로그램`, `미터` |
| dimension | VARCHAR(20) | 물리 차원 | — | `quantity`, `length`, `weight`, `volume`, `area` |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-01-15 09:00:00+09` |

---

#### 5.1.2 shared.gl_accounts (계정과목 마스터)

> SAP SKA1 / 더존 아마란스10 계정코드 매핑

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| account_code | VARCHAR(10) | 더존 계정코드 (UNIQUE) | SAKNR | `146000` |
| account_name | VARCHAR(100) | 계정과목명 | TXT50 | `원재료`, `매출원가` |
| account_type | VARCHAR(20) | 계정 유형 | KTOKS | `asset`, `liability`, `equity`, `revenue`, `expense` |
| ifrs_category | VARCHAR(30) | K-IFRS 분류 | — | `inventory`, `cogs`, `trade_payable`, `trade_receivable` |
| normal_balance | VARCHAR(6) | 정상 잔액 방향 | — | `debit` (자산/비용), `credit` (부채/자본/수익) |
| parent_id | UUID | 상위 계정 (FK: gl_accounts) | — | 계정과목 계층구조용 |
| douzone_code | VARCHAR(20) | 더존 아마란스10 내부코드 | — | 더존 ERP 연동 시 사용 |
| is_active | BOOLEAN | 활성 여부 | — | `true` |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-01-15 09:00:00+09` |

---

#### 5.1.3 shared.material_types (자재유형 마스터)

> SAP T134 | 자재유형별 GL 계정 자동결정의 핵심 참조 테이블

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| type_code | VARCHAR(10) | 자재유형 코드 (UNIQUE) | MTART | `ROH`, `HALB`, `FERT`, `VERP` |
| type_name | VARCHAR(100) | 자재유형명 | MTBEZ | `원자재`, `반제품`, `완제품` |
| is_stockable | BOOLEAN | 재고관리 대상 여부 | — | `true` |
| is_batch_managed | BOOLEAN | 배치(LOT) 관리 여부 | — | `false` |
| default_procurement | VARCHAR(1) | 기본 조달유형 | BESKZ | `E`(자체생산), `F`(외부구매), `X`(병행) |
| default_valuation_class | VARCHAR(10) | 기본 평가클래스 | BKLAS | `3000` |
| default_debit_gl_id | UUID | 입고 시 차변 계정 (FK: gl_accounts) | — | 원재료 계정 UUID |
| default_credit_gl_id | UUID | 입고 시 대변 계정 (FK: gl_accounts) | — | 매입채무 계정 UUID |
| issue_debit_gl_id | UUID | 출고 시 차변 계정 (FK: gl_accounts) | — | 매출원가 계정 UUID |
| issue_credit_gl_id | UUID | 출고 시 대변 계정 (FK: gl_accounts) | — | 원재료 계정 UUID |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-01-15 09:00:00+09` |

---

#### 5.1.4 shared.material_groups (자재그룹 마스터)

> SAP T023 | 구매분석, 지출분석용 분류

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| group_code | VARCHAR(20) | 그룹 코드 (UNIQUE) | MATKL | `PKG-BOX`, `RAW-PAPER` |
| group_name | VARCHAR(100) | 그룹명 | WGBEZ | `포장박스류`, `지류 원자재` |
| parent_id | UUID | 상위 그룹 (FK: material_groups) | — | 그룹 계층구조용 |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-01-15 09:00:00+09` |

---

#### 5.1.5 shared.organizations (조직 마스터)

> SAP T001 (회사코드) / T001W (플랜트/창고) | 회사-플랜트-창고 계층구조

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| org_code | VARCHAR(10) | 조직 코드 (UNIQUE) | BUKRS/WERKS | `SC01`, `PL01`, `WH01` |
| org_name | VARCHAR(100) | 조직명 | BUTXT/NAME1 | `신시어리 본사`, `김포 플랜트` |
| org_type | VARCHAR(20) | 조직 유형 | — | `company`, `plant`, `warehouse` |
| parent_id | UUID | 상위 조직 (FK: organizations) | — | plant → company, warehouse → plant |
| country_code | CHAR(2) | 국가 코드 | LAND1 | `KR` |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-01-15 09:00:00+09` |

---

#### 5.1.6 shared.users (사용자 마스터)

> SAP SU01 + Supabase Auth 연동 | 내부 직원 정보

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| auth_user_id | UUID | Supabase 인증 ID (UNIQUE, FK: auth.users) | — | Supabase Auth 연동용 |
| employee_number | VARCHAR(20) | 사번 (UNIQUE) | PERNR | `EMP001` |
| name | VARCHAR(100) | 이름 | SNAME | `김철수` |
| email | VARCHAR(255) | 이메일 (UNIQUE) | SMTP_ADDR | `cs.kim@sincerely.kr` |
| phone | VARCHAR(20) | 전화번호 | TEL_NUMBER | `010-1234-5678` |
| team | VARCHAR(20) | 소속 팀 | — | `cx`, `logistics`, `scm`, `production`, `procurement` |
| slack_id | VARCHAR(50) | Slack 사용자 ID | — | `U01ABC123` |
| slack_id_tag | TEXT | Slack 멘션 태그 | — | `<@U01ABC123>` |
| status | VARCHAR(10) | 상태 | — | `active`, `inactive` |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-01-15 09:00:00+09` |
| updated_at | TIMESTAMPTZ | 수정일시 | — | `2026-01-15 09:00:00+09` |

---

#### 5.1.7 shared.clients (고객 마스터)

> SAP BP-Customer | 고객사(납품처) 정보

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| client_code | VARCHAR(20) | 고객 코드 (UNIQUE) | KUNNR | `CL-001` |
| company_name | VARCHAR(200) | 회사명 | NAME1 | `ABC 마케팅` |
| business_reg_number | VARCHAR(20) | 사업자등록번호 | STCD1 | `123-45-67890` |
| contact_name | VARCHAR(100) | 담당자명 | NAMEV | `박영희` |
| contact_email | VARCHAR(255) | 담당자 이메일 | SMTP_ADDR | `yh.park@abc.co.kr` |
| contact_phone | VARCHAR(20) | 담당자 전화번호 | TEL_NUMBER | `02-1234-5678` |
| address | TEXT | 주소 | STRAS | `서울시 강남구 ...` |
| status | VARCHAR(10) | 상태 | — | `active`, `inactive` |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-01-15 09:00:00+09` |

---

#### 5.1.8 shared.vendors (공급사 마스터)

> SAP BP-Vendor + 더존 ERP 연계 | 자재 공급업체 정보

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| vendor_code | VARCHAR(20) | 공급사 코드 (UNIQUE) | LIFNR | `VD-001` |
| vendor_name | VARCHAR(200) | 공급사명 | NAME1 | `한국포장재` |
| vendor_type | VARCHAR(50) | 공급사 유형 | — | `manufacturer`(제조), `packaging`(포장), `logistics`(물류), `assembly`(조립) |
| business_reg_number | VARCHAR(20) | 사업자등록번호 | STCD1 | `987-65-43210` |
| contact_name | VARCHAR(100) | 담당자명 | NAMEV | `이민수` |
| contact_phone | VARCHAR(20) | 담당자 전화번호 | TEL_NUMBER | `031-555-1234` |
| email | VARCHAR(255) | 이메일 | SMTP_ADDR | `ms.lee@vendor.co.kr` |
| address | TEXT | 주소 | STRAS | `경기도 김포시 ...` |
| bank_account | VARCHAR(50) | 은행 계좌번호 | BANKN | `123-456-789012` |
| bank_holder | VARCHAR(100) | 예금주 | KOINH | `한국포장재(주)` |
| bank_name | VARCHAR(100) | 은행명 | BANKL | `국민은행` |
| is_stock_vendor | BOOLEAN | 재고관리 자재 공급 여부 | — | `true`=재고관리 자재를 공급하는 업체 |
| douzone_vendor_code | VARCHAR(20) | 더존 거래처코드 | — | 더존 아마란스10 거래처 연동용 |
| status | VARCHAR(10) | 상태 | — | `active`, `inactive` |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-01-15 09:00:00+09` |
| updated_at | TIMESTAMPTZ | 수정일시 | — | `2026-01-15 09:00:00+09` |

---

#### 5.1.9 shared.projects (프로젝트 마스터)

> SAP PS (Project System) | 고객 프로젝트 — 주문에서 출하까지 연결

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| project_code | VARCHAR(50) | 프로젝트 코드 (UNIQUE) | PSPNR | `PRJ-2026-001` |
| project_name | VARCHAR(200) | 프로젝트명 | POST1 | `ABC마케팅 2026 봄 시즌 키트` |
| client_id | UUID | 고객 (FK: clients) | — | 프로젝트 발주 고객 |
| main_usage | VARCHAR(50) | 주요 용도 | — | `promotional`, `subscription`, `corporate_gift` |
| project_status | VARCHAR(20) | 프로젝트 상태 | — | `active`, `completed`, `on_hold`, `cancelled` |
| first_shipment_date | DATE | 첫 출하 예정일 | — | `2026-04-01` |
| last_shipment_date | DATE | 마지막 출하 예정일 | — | `2026-04-15` |
| fulfillment_lead_time | INTEGER | 풀필먼트 리드타임 (일) | — | `7` (주문~출하까지 평균 일수) |
| cx_specialist_id | UUID | CX 담당자 (FK: users) | — | 고객 소통 전담 직원 |
| ordered_items_summary | TEXT | 주문 품목 요약 | — | `포장박스 200EA, 에코백 500EA` |
| dropbox_link | TEXT | Dropbox 공유 링크 | — | 디자인 파일 등 공유 폴더 |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-01-15 09:00:00+09` |
| updated_at | TIMESTAMPTZ | 수정일시 | — | `2026-01-15 09:00:00+09` |

---

#### 5.1.10 shared.goods_master (완제품 마스터)

> SAP Material Master - FERT 레벨 | 최종 판매 가능한 완제품

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| goods_code | VARCHAR(50) | 완제품 코드 (UNIQUE) | MATNR | `GDS-BOX-001` |
| goods_name | VARCHAR(200) | 완제품명 | MAKTX | `ABC마케팅 봄 기프트박스` |
| material_type_id | UUID | 자재유형 (FK: material_types) | MTART | 보통 FERT |
| material_group_id | UUID | 자재그룹 (FK: material_groups) | MATKL | 분류 그룹 |
| base_uom | VARCHAR(10) | 기본 단위 (FK: units_of_measure) | MEINS | `EA` |
| goods_category | VARCHAR(50) | 상품 카테고리 | — | `goods`(일반상품), `kit`(키트), `sample`(샘플) |
| product_type_l1 | VARCHAR(50) | 제품유형 L1 분류 | — | `gift_box`, `eco_bag`, `tote_bag` |
| product_status | VARCHAR(20) | 제품 상태 | — | `active`, `discontinued`, `development` |
| moq | INTEGER | 최소주문수량 | — | `100` |
| packaging_qty_per_box | INTEGER | 박스당 입수량 | — | `50` (1박스에 50개 들어감) |
| packing_standard_qty | INTEGER | 포장 기준 수량 | — | `10` |
| release_date | DATE | 출시일 | — | `2026-03-01` |
| planned_release_date | DATE | 출시 예정일 | — | `2026-04-01` |
| packaging_tip | TEXT | 포장 유의사항 | — | `모서리 보호 필수, 습기 방지` |
| memo_cx | TEXT | CX팀 메모 | — | 고객 소통 관련 참고사항 |
| memo_scm | TEXT | SCM팀 메모 | — | 물류/재고 관련 참고사항 |
| lead_time_bulk_days | INTEGER | 대량생산 리드타임 (일) | — | `14` |
| default_bom_id | UUID | 기본 BOM (FK: pp.bom_headers, 지연) | STLAN | BOM 연결 (나중에 ALTER로 추가) |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-01-15 09:00:00+09` |
| updated_at | TIMESTAMPTZ | 수정일시 | — | `2026-01-15 09:00:00+09` |

---

#### 5.1.11 shared.item_master (반제품 마스터)

> SAP Material Master - HALB 레벨 | 중간 가공 단계의 반제품
> 완제품(goods_master)과의 관계는 FK가 아닌 BOM으로 표현

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| item_code | VARCHAR(50) | 반제품 코드 (UNIQUE) | MATNR | `ITM-ASM-001` |
| item_name | VARCHAR(200) | 반제품명 | MAKTX | `인쇄완료 내지` |
| material_type_id | UUID | 자재유형 (FK: material_types) | MTART | 보통 HALB |
| material_group_id | UUID | 자재그룹 (FK: material_groups) | MATKL | 분류 그룹 |
| base_uom | VARCHAR(10) | 기본 단위 (FK: units_of_measure) | MEINS | `EA` |
| item_detail | TEXT | 상세 설명 | — | 가공 방법, 규격 등 |
| category | VARCHAR(50) | 분류 | — | `inner_box`, `printed_sheet` |
| production_type | VARCHAR(20) | 생산 유형 | — | `purchase`(외주), `production`(자체생산), `assembly`(조립) |
| requires_assembly | BOOLEAN | 조립 필요 여부 | — | `true`=추가 조립 공정 필요 |
| dimensions | VARCHAR(100) | 규격 치수 | — | `210x297mm` |
| template_size | VARCHAR(100) | 템플릿 사이즈 | — | `A4`, `B5` |
| stock_managed | BOOLEAN | 재고관리 여부 | — | `true` |
| pre_packaging_instruction | TEXT | 전처리/포장 지침 | — | `인쇄 전 습도 확인 필수` |
| purchaser_id | UUID | 구매 담당자 (FK: users) | — | 이 반제품의 구매 담당 직원 |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-01-15 09:00:00+09` |
| updated_at | TIMESTAMPTZ | 수정일시 | — | `2026-01-15 09:00:00+09` |

---

#### 5.1.12 shared.parts_master (원자재/포장재 마스터)

> SAP Material Master - ROH/VERP 레벨 | 원자재, 포장재, 부자재
> 시스템에서 가장 많이 참조되는 핵심 마스터 테이블

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| parts_code | VARCHAR(50) | 부품 코드 (UNIQUE) | MATNR | `PKG-BOX-001`, `RAW-KRAFT-A4` |
| parts_name | VARCHAR(200) | 부품명 | MAKTX | `크라프트 3겹 박스 (소)` |
| material_type_id | UUID | 자재유형 (FK: material_types) | MTART | ROH, VERP 등 |
| material_group_id | UUID | 자재그룹 (FK: material_groups) | MATKL | 분류 그룹 |
| base_uom | VARCHAR(10) | 기본 단위 (FK: units_of_measure) | MEINS | `EA` |
| vendor_id | UUID | 기본 공급사 (FK: vendors) | LIFNR | 이 부품의 주 공급업체 |
| parts_type | VARCHAR(50) | 부품 유형 (레거시) | — | `raw`(원자재), `semi_finished`(반제품), `packaging`(포장재), `merchandise`(상품) |
| stock_classification | VARCHAR(20) | 재고 분류 | — | `A`(고가치), `B`(중간), `C`(저가치) - ABC 분석용 |
| is_stock_managed | BOOLEAN | 재고관리 대상 여부 | XCHPF | `true` |
| is_batch_managed | BOOLEAN | 배치(LOT) 관리 여부 | XCHPF | `true`=입고 시 배치번호 부여 |
| procurement_type | VARCHAR(1) | 조달 유형 | BESKZ | `E`(자체생산), `F`(외부구매), `X`(병행) |
| reorder_point | INTEGER | 재주문점 (ROP) | MINBE | `500` (재고가 이 이하이면 재주문) |
| min_order_qty | INTEGER | 최소 주문 수량 | BSTMI | `100` |
| gross_weight_kg | NUMERIC(10,3) | 총중량 (kg) | BRGEW | `0.250` |
| net_weight_kg | NUMERIC(10,3) | 순중량 (kg) | NTGEW | `0.200` |
| volume_cbm | NUMERIC(10,6) | 부피 (CBM) | VOLUM | `0.001500` |
| dimensions | VARCHAR(100) | 규격 치수 | — | `300x200x50mm` |
| material_spec | TEXT | 자재 사양 | — | `3겹 E골 크라프트, 내압강도 15kgf` |
| base_processing | TEXT | 기본 가공방법 | — | `합지→톰슨→접착` |
| printing_options | TEXT | 인쇄 옵션 | — | `4도 옵셋 양면, UV 코팅` |
| print_area | VARCHAR(200) | 인쇄 영역 | — | `전면 200x150mm` |
| print_color | VARCHAR(100) | 인쇄 색상 | — | `CMYK + 별색 1도` |
| vendor_product_name | VARCHAR(200) | 공급사측 품명 | — | 공급사가 부르는 제품 이름 |
| order_options | TEXT | 주문 옵션 | — | 주문 시 선택 가능한 옵션 |
| template_size | VARCHAR(100) | 템플릿 사이즈 | — | `A4`, `B5` |
| template_link | TEXT | 템플릿 파일 링크 | — | Dropbox/Drive URL |
| packaging_tip | TEXT | 포장 유의사항 | — | `습기 방지, 평적 보관` |
| is_customer_goods | BOOLEAN | 고객 지급 자재 여부 | — | `true`=고객이 직접 제공한 자재 |
| status | VARCHAR(20) | 상태 | — | `active`, `inactive`, `discontinued` |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-01-15 09:00:00+09` |
| updated_at | TIMESTAMPTZ | 수정일시 | — | `2026-01-15 09:00:00+09` |

---

#### 5.1.13 shared.material_valuation (자재평가)

> SAP MBEW | 자재별 원가 평가 정보 (가중평균/FIFO)

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| parts_id | UUID | 부품 (FK: parts_master) | MATNR | 평가 대상 자재 |
| valuation_area_id | UUID | 평가영역 (FK: organizations) | BWKEY | 보통 플랜트 단위 |
| valuation_class | VARCHAR(10) | 평가클래스 | BKLAS | `3000` |
| costing_method | VARCHAR(15) | 원가산정 방법 | — | `weighted_avg`(가중평균), `fifo`(선입선출) |
| standard_price | NUMERIC(15,4) | 표준원가 (기본단위당) | STPRS | `1250.0000` |
| moving_avg_price | NUMERIC(15,4) | 이동평균원가 (기본단위당) | VERPR | `1180.5000` |
| total_stock_value | NUMERIC(15,2) | 총 재고 금액 | SALK3 | `590250.00` |
| last_updated_at | TIMESTAMPTZ | 최종 갱신일시 | — | `2026-03-30 15:00:00+09` |

> UNIQUE 제약: (parts_id, valuation_area_id) -- 자재+평가영역 조합으로 유일

---

#### 5.1.14 shared.vendor_evaluations (공급사 평가)

> SAP ME61 | 월별 공급사 성과 평가

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| vendor_id | UUID | 공급사 (FK: vendors) | LIFNR | 평가 대상 공급사 |
| period | VARCHAR(7) | 평가 기간 | — | `2026-03` (YYYY-MM 형식) |
| quality_score | NUMERIC(5,2) | 품질 점수 | — | `92.50` (100점 만점) |
| delivery_score | NUMERIC(5,2) | 납기 점수 | — | `88.00` |
| price_score | NUMERIC(5,2) | 가격 점수 | — | `85.00` |
| overall_score | NUMERIC(5,2) | 종합 점수 | — | `88.50` |
| evaluated_by | UUID | 평가자 (FK: users) | — | 평가 수행 담당자 |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-03-31 09:00:00+09` |

> UNIQUE 제약: (vendor_id, period) -- 공급사+기간 조합으로 유일

---

### 5.2 mm 스키마 (자재관리/구매)

Materials Management + Quality Management. 구매, 입고, 재고이동, 품질검사, 반품, 폐기 등.
총 10개 테이블.

---

#### 5.2.1 mm.purchase_requisitions (구매요청)

> SAP EBAN | 구매발주(PO) 생성 전 내부 승인용 요청서

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| pr_number | VARCHAR(50) | 구매요청 번호 (UNIQUE) | BANFN | `PR-20260330-001` |
| parts_id | UUID | 요청 자재 (FK: parts_master) | MATNR | 구매 대상 부품 |
| required_qty | INTEGER | 필요 수량 | MENGE | `500` |
| required_date | DATE | 필요 일자 | LFDAT | `2026-04-15` |
| project_id | UUID | 프로젝트 (FK: projects) | — | 어떤 프로젝트를 위한 구매인지 |
| source | VARCHAR(10) | 생성 출처 | — | `manual`(수동), `mrp`(MRP 자동), `reorder`(재주문점) |
| status | VARCHAR(20) | 상태 | FRGZU | `open`→`approved`→`converted`→`closed` |
| converted_po_item_id | UUID | 변환된 PO 라인 (FK: purchase_order_items) | — | PR이 PO로 전환되면 해당 PO 라인 연결 |
| requested_by | UUID | 요청자 (FK: users) | ERNAM | 구매 요청한 직원 |
| approved_by | UUID | 승인자 (FK: users) | FRGNA | 구매 요청을 승인한 직원 |
| approved_at | TIMESTAMPTZ | 승인 일시 | — | `2026-03-30 14:00:00+09` |
| unit_of_measure | VARCHAR(10) | 단위 (FK: units_of_measure) | MEINS | `EA` |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-03-30 10:00:00+09` |
| updated_at | TIMESTAMPTZ | 수정일시 | — | `2026-03-30 14:00:00+09` |

---

#### 5.2.2 mm.purchase_orders (구매발주 헤더)

> SAP EKKO | 공급사별 구매발주서 헤더 (품목 상세는 purchase_order_items)

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| po_number | VARCHAR(50) | 발주번호 (UNIQUE) | EBELN | `PO-20260330-001` |
| project_id | UUID | 프로젝트 (FK: projects) | — | 관련 프로젝트 |
| vendor_id | UUID | 공급사 (FK: vendors) | LIFNR | 발주 대상 업체 |
| purchasing_org_id | UUID | 구매조직 (FK: organizations) | EKORG | 구매를 수행하는 조직 |
| po_status | VARCHAR(30) | 발주 상태 | — | `draft`→`sent`→`confirmed`→`partial_received`→`received`→`closed` |
| order_stage | VARCHAR(30) | 내부 워크플로우 단계 | — | 사내 진행상황 추적용 |
| requested_date | DATE | 요청 납기일 | EINDT | `2026-04-10` |
| ordered_by | UUID | 발주자 (FK: users) | ERNAM | PO를 작성한 직원 |
| cx_manager_id | UUID | CX 담당자 (FK: users) | — | 이 주문의 CX 매니저 |
| is_archived | BOOLEAN | 보관처리 여부 | — | `false` (완료 후 `true`로 변경) |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-03-30 10:00:00+09` |
| updated_at | TIMESTAMPTZ | 수정일시 | — | `2026-03-30 10:00:00+09` |

---

#### 5.2.3 mm.purchase_order_items (구매발주 품목)

> SAP EKPO | PO 하위의 개별 품목 라인 (PO 1건에 여러 품목 가능)

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| po_id | UUID | PO 헤더 (FK: purchase_orders) | EBELN | 소속 PO |
| line_number | INTEGER | 라인번호 | EBELP | `10`, `20`, `30` |
| parts_id | UUID | 발주 자재 (FK: parts_master) | MATNR | 주문하는 부품 |
| order_qty | INTEGER | 주문 수량 | MENGE | `1000` |
| received_qty | INTEGER | 입고된 수량 | — | `800` (부분입고 가능) |
| unit_price | NUMERIC(15,2) | 단가 | NETPR | `1500.00` |
| total_amount | NUMERIC(15,2) | 총액 (자동계산: order_qty x unit_price) | NETWR | `1500000.00` |
| unit_of_measure | VARCHAR(10) | 단위 (FK: units_of_measure) | MEINS | `EA` |
| planned_delivery_date | DATE | 예정 납기일 | EINDT | `2026-04-10` |
| confirmed_delivery_date | DATE | 확정 납기일 | — | `2026-04-12` (공급사 확인 후) |
| actual_delivery_date | DATE | 실제 입고일 | — | `2026-04-11` |
| quality_check_result | VARCHAR(20) | 품질검사 결과 | — | `pass`, `fail`, `pending`, `sample_pass` |
| sample_check_result | VARCHAR(20) | 샘플 검사 결과 | — | `pass`, `fail` |
| visual_check_result | VARCHAR(20) | 외관 검사 결과 | — | `pass`, `fail` |
| is_urgent | BOOLEAN | 긴급 여부 | — | `true`=긴급 발주 |
| is_rework | BOOLEAN | 재작업 여부 | — | `true`=불량으로 인한 재발주 |
| is_bespoke | BOOLEAN | 맞춤제작 여부 | — | `true`=고객 맞춤 특수 제작 |
| production_type | VARCHAR(20) | 생산유형 | — | `purchase`(구매), `production`(생산), `assembly`(조립) |
| over_delivery_tolerance_pct | NUMERIC(5,2) | 초과납품 허용률 (%) | UEBTO | `5.00` (5%까지 초과 OK) |
| under_delivery_tolerance_pct | NUMERIC(5,2) | 미달납품 허용률 (%) | UNTTO | `3.00` |
| design_file_url | TEXT | 디자인 파일 URL | — | 인쇄 시안 등 |
| spec_notes | TEXT | 사양 메모 | — | 추가 사양 설명 |
| box_count | INTEGER | 박스 수량 | — | `20` (몇 박스로 납품되는지) |
| tax_code | VARCHAR(10) | 세금 코드 | MWSKZ | `V1` (부가세 포함) |

> UNIQUE 제약: (po_id, line_number) -- PO 내 라인번호 유일

---

#### 5.2.4 mm.goods_receipts (입고전표)

> SAP MKPF/MSEG | 자재가 창고에 물리적으로 도착하여 수령하는 기록

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| gr_number | VARCHAR(50) | 입고전표 번호 (UNIQUE) | MBLNR | `GR-20260330-001` |
| po_id | UUID | PO 헤더 (FK: purchase_orders) | EBELN | 어떤 PO 기반 입고인지 |
| po_item_id | UUID | PO 품목 (FK: purchase_order_items) | EBELP | 어떤 PO 라인의 입고인지 |
| parts_id | UUID | 입고 자재 (FK: parts_master) | MATNR | 입고된 부품 |
| storage_bin_id | UUID | 저장위치 (FK: wms.storage_bins) | LGPLA | 자재가 놓인 창고 위치 |
| batch_id | UUID | 배치 (FK: wms.batches) | CHARG | 입고 시 생성된 배치 |
| movement_type | VARCHAR(10) | 이동유형 | BWART | `101`(입고), `102`(입고취소) |
| received_qty | INTEGER | 수령 수량 | MENGE | `1000` |
| accepted_qty | INTEGER | 합격 수량 | — | `980` (검사 후 합격된 수량) |
| rejected_qty | INTEGER | 불합격 수량 | — | `20` |
| unit_of_measure | VARCHAR(10) | 단위 (FK: units_of_measure) | MEINS | `EA` |
| unit_cost | NUMERIC(15,4) | 단가 | DMBTR/MENGE | `1500.0000` |
| total_cost | NUMERIC(15,2) | 총 입고 금액 | DMBTR | `1500000.00` |
| tax_invoice_no | VARCHAR(30) | 세금계산서 번호 | — | `20260330-001` |
| vat_amount | NUMERIC(15,2) | 부가세 금액 | — | `150000.00` |
| planned_receipt_date | DATE | 예정 입고일 | — | `2026-04-10` |
| actual_receipt_date | DATE | 실제 입고일 | BUDAT | `2026-04-11` |
| posting_date | DATE | 전기일 (회계 반영일) | BUDAT | `2026-04-11` |
| inspection_result | VARCHAR(20) | 검사 결과 | — | `pass`(합격), `fail`(불합격), `conditional`(조건부합격) |
| inspection_notes | TEXT | 검사 비고 | — | `2건 인쇄 불량, 나머지 양호` |
| inspection_photos_url | TEXT | 검사 사진 URL | — | 검수 사진 링크 |
| received_by | UUID | 수령자 (FK: users) | — | 물건을 받은 직원 |
| inspected_by | UUID | 검수자 (FK: users) | — | 품질 검사한 직원 |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-04-11 09:00:00+09` |

---

#### 5.2.5 mm.stock_movements (재고이동전표)

> SAP MSEG | 모든 물리적 재고 이동 기록 (시스템의 핵심 트랜잭션 테이블)

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| movement_number | VARCHAR(50) | 이동전표 번호 (UNIQUE) | — | `SM-20260330-001` |
| material_document_number | VARCHAR(50) | 자재문서 번호 | MBLNR | 관련 이동들을 묶는 문서번호 |
| movement_type | VARCHAR(30) | 이동유형 (SAP 코드) | BWART | `101`, `201`, `261`, `301`, `601` 등 |
| sap_movement_code | VARCHAR(10) | SAP 이동유형 코드 | BWART | movement_type과 동일값 |
| parts_id | UUID | 이동 자재 (FK: parts_master) | MATNR | 이동하는 부품 |
| from_bin_id | UUID | 출발 저장위치 (FK: wms.storage_bins) | LGPLA | 자재가 나가는 위치 (출고 시) |
| to_bin_id | UUID | 도착 저장위치 (FK: wms.storage_bins) | LGPLA | 자재가 들어가는 위치 (입고 시) |
| batch_id | UUID | 배치 (FK: wms.batches) | CHARG | 이동하는 배치 |
| planned_qty | INTEGER | 계획 수량 | — | `500` |
| actual_qty | INTEGER | 실제 수량 | MENGE | `480` |
| unit_of_measure | VARCHAR(10) | 단위 (FK: units_of_measure) | MEINS | `EA` |
| movement_purpose | VARCHAR(50) | 이동 목적 | — | `production_issue`, `customer_shipment` |
| planned_date | DATE | 계획일 | — | `2026-04-10` |
| actual_date | DATE | 실제 이동일 | — | `2026-04-10` |
| posting_date | DATE | 전기일 (회계 반영일) | BUDAT | `2026-04-10` |
| fiscal_year | VARCHAR(4) | 회계연도 | GJAHR | `2026` |
| fiscal_period | VARCHAR(2) | 회계기간 | MONAT | `04` |
| status | VARCHAR(20) | 이동 상태 | — | `planned`→`in_progress`→`completed`→`cancelled` |
| unit_cost_at_movement | NUMERIC(15,4) | 이동 시점 단가 | DMBTR/MENGE | `1500.0000` |
| total_cost | NUMERIC(15,2) | 이동 총 금액 | DMBTR | `720000.00` |
| gl_account_id | UUID | GL 계정 (FK: gl_accounts) | SAKTO | 이 이동에 적용되는 계정과목 |
| is_reversal | BOOLEAN | 역분개 여부 | XSTOB | `true`=다른 이동을 취소하는 역분개 전표 |
| reversal_movement_id | UUID | 역분개 원본 (FK: stock_movements) | SMBLN | 취소 대상 원래 이동 ID |
| gr_id | UUID | 입고전표 (FK: goods_receipts) | — | 관련 입고전표 |
| po_item_id | UUID | PO 품목 (FK: purchase_order_items) | — | 관련 PO 라인 |
| production_order_id | UUID | 생산오더 (FK: pp.production_orders, 지연) | AUFNR | 관련 생산오더 |
| logistics_release_id | UUID | 물류출고지시 (FK: tms.logistics_releases) | — | 관련 출고지시 |
| tr_id | UUID | 운송요청 (FK: tms.transportation_requirements) | — | 관련 운송요청 |
| reference_doc_type | VARCHAR(30) | 참조문서 유형 | — | `gr`, `po`, `production_order`, `logistics_release`, `tr`, `adjustment` |
| created_by | UUID | 생성자 (FK: users) | USNAM | 전표 생성한 직원 |
| last_modified_by | UUID | 최종 수정자 (FK: users) | — | 마지막 수정한 직원 |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-04-10 09:00:00+09` |
| updated_at | TIMESTAMPTZ | 수정일시 | — | `2026-04-10 09:00:00+09` |

---

#### 5.2.6 mm.invoice_verifications (송장검증)

> SAP MIRO | PO vs GR vs 세금계산서 3-way 매칭 (금액 대사)

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| iv_number | VARCHAR(50) | 검증 번호 (UNIQUE) | BELNR | `IV-20260330-001` |
| po_id | UUID | PO 헤더 (FK: purchase_orders) | EBELN | 매칭 대상 PO |
| vendor_id | UUID | 공급사 (FK: vendors) | LIFNR | 세금계산서 발행 업체 |
| invoice_date | DATE | 세금계산서 일자 | BLDAT | `2026-04-15` |
| posting_date | DATE | 전기일 | BUDAT | `2026-04-15` |
| invoice_amount | NUMERIC(15,2) | 세금계산서 금액 | WRBTR | `1650000.00` |
| gr_amount | NUMERIC(15,2) | GR(입고) 금액 | — | `1500000.00` |
| po_amount | NUMERIC(15,2) | PO 발주 금액 | — | `1500000.00` |
| price_variance | NUMERIC(15,2) | 가격 차이 (송장-PO) | — | `150000.00` (양수=초과 청구) |
| qty_variance | INTEGER | 수량 차이 (송장수량-GR수량) | — | `0` |
| tax_invoice_no | VARCHAR(30) | 세금계산서 번호 | — | `20260415-001` |
| vat_amount | NUMERIC(15,2) | 부가세 금액 | — | `150000.00` |
| status | VARCHAR(20) | 검증 상태 | — | `pending`→`matched`/`variance`→`posted` |
| match_result | VARCHAR(20) | 매칭 결과 | — | `exact`(정확일치), `within_tolerance`(허용범위내), `over_tolerance`(허용범위초과) |
| verified_by | UUID | 검증자 (FK: users) | — | 대사 검증한 직원 |
| verified_at | TIMESTAMPTZ | 검증 일시 | — | `2026-04-16 10:00:00+09` |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-04-15 09:00:00+09` |

---

#### 5.2.7 mm.reservations (자재예약)

> SAP RESB | 생산/출하 등을 위해 자재를 사전 예약(출고 보류)

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| reservation_number | VARCHAR(50) | 예약번호 (UNIQUE) | RSNUM | `RSV-20260330-001` |
| parts_id | UUID | 예약 자재 (FK: parts_master) | MATNR | 예약 대상 부품 |
| storage_bin_id | UUID | 저장위치 (FK: wms.storage_bins) | LGPLA | 어느 위치의 재고를 예약 |
| requirement_qty | INTEGER | 필요 수량 | BDMNG | `300` |
| withdrawn_qty | INTEGER | 출고된 수량 | ENMNG | `200` (부분 출고 가능) |
| movement_type | VARCHAR(10) | 이동유형 | BWART | `261`(생산투입), `201`(비용센터), `601`(납품) |
| unit_of_measure | VARCHAR(10) | 단위 (FK: units_of_measure) | MEINS | `EA` |
| project_id | UUID | 프로젝트 (FK: projects) | — | 프로젝트를 위한 예약 |
| production_order_id | UUID | 생산오더 (FK: pp.production_orders, 지연) | AUFNR | 생산오더를 위한 예약 |
| tr_id | UUID | 운송요청 (FK: transportation_requirements) | — | 출하를 위한 예약 |
| source_doc_type | VARCHAR(30) | 원본문서 유형 | — | `project`, `production_order`, `tr` |
| status | VARCHAR(20) | 예약 상태 | — | `open`→`partially_withdrawn`→`closed` / `cancelled` |
| requirement_date | DATE | 필요일 | BDTER | `2026-04-10` |
| created_by | UUID | 생성자 (FK: users) | — | 예약을 생성한 직원 |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-03-30 10:00:00+09` |
| updated_at | TIMESTAMPTZ | 수정일시 | — | `2026-03-30 10:00:00+09` |

---

#### 5.2.8 mm.return_orders (반품오더)

> 공급사 반품(122) 및 고객 반품(161) 관리

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| return_number | VARCHAR(50) | 반품번호 (UNIQUE) | — | `RTN-20260330-001` |
| direction | VARCHAR(10) | 반품 방향 | — | `vendor`(공급사에 돌려보냄), `customer`(고객이 돌려보냄) |
| original_doc_type | VARCHAR(30) | 원본 문서 유형 | — | `po`(구매발주), `gr`(입고), `freight_order`(운송) |
| original_doc_id | UUID | 원본 문서 ID | — | 반품 사유가 된 원본 문서 |
| parts_id | UUID | 반품 자재 (FK: parts_master) | MATNR | 반품하는 부품 |
| return_qty | INTEGER | 반품 수량 | — | `50` |
| unit_of_measure | VARCHAR(10) | 단위 (FK: units_of_measure) | — | `EA` |
| reason_code | VARCHAR(20) | 반품 사유 | — | `quality_fail`(품질불량), `wrong_item`(오배송), `damaged`(파손), `excess`(초과), `customer_return`(고객반품) |
| disposition | VARCHAR(20) | 처리 방법 | — | `restock`(재입고), `scrap`(폐기), `rework`(재작업), `replace`(교환) |
| status | VARCHAR(20) | 반품 상태 | — | `open`→`shipped`→`received`→`closed` |
| requested_date | DATE | 요청일 | — | `2026-04-01` |
| completed_date | DATE | 완료일 | — | `2026-04-05` |
| created_by | UUID | 생성자 (FK: users) | — | 반품 요청한 직원 |
| approved_by | UUID | 승인자 (FK: users) | — | 반품을 승인한 직원 |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-04-01 09:00:00+09` |

---

#### 5.2.9 mm.quality_inspections (품질검사)

> SAP QALS | 입고, 공정중, 최종 품질검사 기록

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| inspection_number | VARCHAR(50) | 검사 번호 (UNIQUE) | PRUEFLOS | `QI-20260330-001` |
| gr_id | UUID | 입고전표 (FK: goods_receipts) | — | 검사 대상 입고 문서 |
| parts_id | UUID | 검사 자재 (FK: parts_master) | MATNR | 검사하는 부품 |
| inspection_type | VARCHAR(20) | 검사 유형 | — | `incoming`(입고검사), `in_process`(공정검사), `final`(최종검사) |
| sample_size | INTEGER | 샘플 크기 | — | `50` (AQL 기준 표본 수) |
| accepted_qty | INTEGER | 합격 수량 | — | `48` |
| rejected_qty | INTEGER | 불합격 수량 | — | `2` |
| defect_codes | TEXT[] | 불량 코드 배열 | — | `{PRINT_DEFECT, COLOR_MISMATCH}` |
| result | VARCHAR(20) | 검사 결과 | — | `pass`(합격), `fail`(불합격), `conditional`(조건부) |
| decision | VARCHAR(20) | 사용 결정 | — | `accept`(수용), `reject`(반려), `rework`(재작업), `scrap`(폐기) |
| decision_date | DATE | 결정일 | — | `2026-04-11` |
| inspector_id | UUID | 검사자 (FK: users) | — | 검사 수행 직원 |
| photos_url | TEXT | 검사 사진 URL | — | 검사 증빙 사진 |
| notes | TEXT | 검사 비고 | — | `인쇄 색상 미세 차이, 조건부 합격` |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-04-11 10:00:00+09` |

---

#### 5.2.10 mm.scrap_records (폐기 기록)

> 이동유형 551 | 불량/만료 등으로 자재를 폐기하는 기록

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| scrap_number | VARCHAR(50) | 폐기번호 (UNIQUE) | — | `SCR-20260330-001` |
| parts_id | UUID | 폐기 자재 (FK: parts_master) | MATNR | 폐기하는 부품 |
| scrap_qty | INTEGER | 폐기 수량 | — | `100` |
| unit_of_measure | VARCHAR(10) | 단위 (FK: units_of_measure) | — | `EA` |
| reason_code | VARCHAR(20) | 폐기 사유 | — | `production_defect`(생산불량), `handling_damage`(취급파손), `expiry`(유통기한만료), `obsolete`(진부화) |
| cost_value | NUMERIC(15,2) | 폐기 손실 금액 | — | `150000.00` |
| production_order_id | UUID | 생산오더 (FK: pp.production_orders, 지연) | AUFNR | 생산 중 발생한 불량인 경우 |
| storage_bin_id | UUID | 저장위치 (FK: wms.storage_bins) | — | 폐기 자재가 있던 위치 |
| movement_id | UUID | 재고이동 (FK: stock_movements) | — | 폐기 처리한 이동유형 551 전표 |
| approved_by | UUID | 승인자 (FK: users) | — | 폐기를 승인한 직원 |
| scrap_date | DATE | 폐기일 | — | `2026-04-15` |
| notes | TEXT | 비고 | — | `인쇄 불량으로 재사용 불가` |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-04-15 09:00:00+09` |

---

### 5.3 wms 스키마 (창고관리)

Warehouse Management System. 물리적 창고 구조, 배치(LOT) 관리, 재고 수량(Quant), 실사.
총 7개 테이블.

---

#### 5.3.1 wms.warehouses (창고 마스터)

> SAP /SCWM/T_WH | 물리적 창고 단위

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| warehouse_code | VARCHAR(10) | 창고 코드 (UNIQUE) | LGNUM | `WH01`, `WH02` |
| warehouse_name | VARCHAR(200) | 창고명 | LNUMT | `김포 제1창고` |
| plant_id | UUID | 소속 플랜트 (FK: organizations) | WERKS | 이 창고가 속한 플랜트 |
| address | TEXT | 주소 | — | `경기도 김포시 ...` |
| max_cbm | NUMERIC(10,3) | 최대 수용량 (CBM) | — | `500.000` |
| manager_id | UUID | 창고 관리자 (FK: users) | — | 창고 책임자 |
| status | VARCHAR(10) | 상태 | — | `active`, `inactive` |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-01-15 09:00:00+09` |

---

#### 5.3.2 wms.storage_types (저장유형)

> SAP /SCWM/T_ST | 창고 내 저장 방식 분류

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| warehouse_id | UUID | 소속 창고 (FK: warehouses) | LGNUM | 이 저장유형이 있는 창고 |
| type_code | VARCHAR(10) | 유형 코드 | LGTYP | `HR`(고층랙), `FL`(바닥), `CL`(냉장) |
| type_name | VARCHAR(100) | 유형명 | — | `고층랙`, `바닥적재`, `냉장보관` |

> UNIQUE 제약: (warehouse_id, type_code) -- 창고별 유형코드 유일

---

#### 5.3.3 wms.storage_bins (저장위치/빈)

> SAP /SCWM/LAGP | 창고 내 실제 물건이 놓이는 물리적 위치 (좌표)

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| bin_code | VARCHAR(20) | 빈 코드 (UNIQUE) | LGPLA | `A-01-01` (통로-랙-단) |
| warehouse_id | UUID | 소속 창고 (FK: warehouses) | LGNUM | 이 빈이 있는 창고 |
| storage_type_id | UUID | 저장유형 (FK: storage_types) | LGTYP | 고층랙/바닥 등 |
| zone | VARCHAR(20) | 존 (출고Zone) | — | `ZONE-A`, `ZONE-B` (피킹 구역) |
| aisle | VARCHAR(10) | 통로 | — | `A`, `B`, `C` |
| rack | VARCHAR(10) | 랙 번호 | — | `01`, `02` |
| level | VARCHAR(10) | 단 (높이) | — | `01`(1단), `02`(2단) |
| bin_type | VARCHAR(20) | 빈 유형 | — | `standard`(일반), `bulk`(벌크), `picking`(피킹), `receiving`(입고), `shipping`(출하) |
| max_weight_kg | NUMERIC(8,2) | 최대 적재 중량 (kg) | — | `500.00` |
| max_cbm | NUMERIC(8,3) | 최대 적재 부피 (CBM) | — | `2.000` |
| status | VARCHAR(20) | 상태 | — | `active`, `inactive`, `maintenance` |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-01-15 09:00:00+09` |

---

#### 5.3.4 wms.batches (배치/LOT 마스터)

> SAP MCHA | 동일 자재를 입고 시점별로 구분하는 배치 (FIFO 원가 추적의 핵심)

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| parts_id | UUID | 자재 (FK: parts_master) | MATNR | 이 배치의 자재 |
| batch_number | VARCHAR(50) | 배치 번호 | CHARG | `BAT-20260411-001` |
| gr_id | UUID | 입고전표 (FK: mm.goods_receipts, 지연) | — | 이 배치를 생성한 입고 문서 |
| remaining_qty | INTEGER | 잔여 수량 | — | `800` (입고 후 출고 차감) |
| unit_cost | NUMERIC(15,4) | 배치 단가 (FIFO) | — | `1500.0000` (입고 시점 단가) |
| production_date | DATE | 생산일 | HSDAT | `2026-04-01` |
| expiry_date | DATE | 유통기한 | VFDAT | `2027-04-01` |
| vendor_batch_ref | VARCHAR(100) | 공급사 배치 참조번호 | LICHA | 공급사의 자체 LOT 번호 |
| status | VARCHAR(20) | 상태 | — | `active`, `exhausted`(소진), `expired`(만료) |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-04-11 09:00:00+09` |

> UNIQUE 제약: (parts_id, batch_number) -- 자재+배치번호 조합으로 유일

---

#### 5.3.5 wms.quants (재고 수량 단위)

> SAP /SCWM/AQUA | 재고의 최소 관리 단위. 자재+빈+배치+재고유형 조합당 1건
> 시스템에서 "현재 재고가 얼마인지"를 알려주는 핵심 테이블

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| parts_id | UUID | 자재 (FK: parts_master) | MATNR | 어떤 부품의 재고인지 |
| storage_bin_id | UUID | 저장위치 (FK: storage_bins) | LGPLA | 어느 빈에 있는 재고인지 |
| batch_id | UUID | 배치 (FK: batches) | CHARG | 어떤 배치의 재고인지 (NULL 가능) |
| stock_type | VARCHAR(20) | 재고 유형 | SOBKZ | `unrestricted`(자유), `quality_inspection`(QC중), `blocked`(차단), `returns`(반품) |
| physical_qty | INTEGER | 실물 수량 (최종 실사치) | — | `480` |
| system_qty | INTEGER | 전산 수량 | — | `500` |
| reserved_qty | INTEGER | 예약 수량 | — | `100` (출고예약으로 잡힌 수량) |
| blocked_qty | INTEGER | 차단 수량 | — | `0` |
| available_qty | INTEGER | 가용 수량 (자동계산) | — | `400` (= system_qty - reserved - blocked) |
| unit_of_measure | VARCHAR(10) | 단위 (FK: units_of_measure) | MEINS | `EA` |
| last_movement_date | DATE | 최종 이동일 | — | `2026-04-10` |
| last_verified_at | TIMESTAMPTZ | 최종 검증일시 | — | `2026-03-31 14:00:00+09` |
| verification_status | VARCHAR(20) | 검증 상태 | — | `pending`(미확인), `verified`(확인됨), `discrepancy`(불일치) |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-01-15 09:00:00+09` |
| updated_at | TIMESTAMPTZ | 수정일시 | — | `2026-04-10 09:00:00+09` |

> `available_qty`는 GENERATED STORED 컬럼: `system_qty - reserved_qty - blocked_qty`

---

#### 5.3.6 wms.inventory_count_docs (재고실사 문서 헤더)

> SAP IKPF | 재고실사(재고조사) 문서 헤더

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| doc_number | VARCHAR(50) | 실사문서 번호 (UNIQUE) | IBLNR | `IC-20260331-001` |
| count_name | VARCHAR(200) | 실사명 | — | `2026년 1분기 정기 재고실사` |
| count_type | VARCHAR(20) | 실사 유형 | — | `annual`(연간), `cycle`(사이클), `spot`(스팟/긴급) |
| warehouse_id | UUID | 대상 창고 (FK: warehouses) | LGNUM | 실사 대상 창고 |
| planned_date | DATE | 계획일 | — | `2026-03-31` |
| completed_date | DATE | 완료일 | — | `2026-03-31` |
| status | VARCHAR(20) | 문서 상태 | — | `created`→`in_progress`→`completed` / `cancelled` |
| scope | TEXT | 실사 범위 | — | `A존 전체 + B존 고가품목` |
| created_by | UUID | 생성자 (FK: users) | — | 실사를 계획한 직원 |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-03-25 09:00:00+09` |

---

#### 5.3.7 wms.inventory_count_items (재고실사 품목)

> SAP ISEG | 재고실사 문서의 개별 품목 라인 (부품별 실사 결과)

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| doc_id | UUID | 실사문서 (FK: inventory_count_docs) | IBLNR | 소속 실사 문서 |
| parts_id | UUID | 실사 자재 (FK: parts_master) | MATNR | 실사하는 부품 |
| storage_bin_id | UUID | 저장위치 (FK: storage_bins) | LGPLA | 실사하는 빈 |
| book_qty | INTEGER | 장부(전산) 수량 | MENGE_SOL | `500` |
| count_qty_1st | INTEGER | 1차 실사 수량 | — | `480` |
| count_qty_2nd | INTEGER | 2차 재실사 수량 | — | `482` (차이 발생 시 재실사) |
| final_count_qty | INTEGER | 최종 확정 수량 | MENGE_IST | `482` |
| difference | INTEGER | 차이 (최종-장부) | MENGE_DIF | `-18` |
| difference_type | VARCHAR(50) | 차이 유형 | — | `shortage`(부족), `surplus`(초과) |
| sap_movement_type | VARCHAR(10) | 조정 이동유형 | BWART | `701`(+조정), `702`(-조정) |
| adjustment_approved | BOOLEAN | 조정 승인 여부 | — | `true` |
| approved_by | UUID | 승인자 (FK: users) | — | 차이 조정을 승인한 직원 |
| counted_by | UUID | 실사자 (FK: users) | — | 실사를 수행한 직원 |
| counted_at | TIMESTAMPTZ | 실사 일시 | — | `2026-03-31 14:30:00+09` |
| processed_at | TIMESTAMPTZ | 처리(조정) 일시 | — | `2026-03-31 16:00:00+09` |

---

### 5.4 tms 스키마 (운송관리)

Transportation Management System. 위치, 운송사, 배차, 운송요청, 운송실행, 출고지시.
총 9개 테이블.

---

#### 5.4.1 tms.locations (위치 마스터)

> SAP TM Location Master | 물리적 위치 — 창고, 고객사, 허브 등

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| location_code | VARCHAR(20) | 위치 코드 (UNIQUE) | — | `LOC-WH01`, `LOC-CL001` |
| location_type | VARCHAR(20) | 위치 유형 | — | `warehouse`(창고), `customer`(고객사), `vendor`(공급사), `hub`(허브), `fulfillment`(풀필먼트센터) |
| location_name | VARCHAR(200) | 위치명 | — | `김포 제1창고`, `ABC마케팅 본사` |
| address | TEXT | 주소 | — | `경기도 김포시 ...` |
| postal_code | VARCHAR(10) | 우편번호 | — | `10034` |
| city | VARCHAR(100) | 도시 | — | `김포시` |
| country_code | CHAR(2) | 국가 코드 | — | `KR` |
| contact_name | VARCHAR(100) | 담당자명 | — | `박영희` |
| contact_phone | VARCHAR(20) | 담당자 전화번호 | — | `031-555-1234` |
| contact_email | VARCHAR(255) | 담당자 이메일 | — | `yh.park@abc.co.kr` |
| inbound_address | TEXT | 입고 전용 주소 | — | 물류 입고 시 사용하는 별도 주소 |
| max_cbm | NUMERIC(10,3) | 최대 수용량 (CBM) | — | `1000.000` |
| is_origin | BOOLEAN | 출발지 가능 여부 | — | `true`=출발지로 사용 가능 |
| is_destination | BOOLEAN | 도착지 가능 여부 | — | `true`=도착지로 사용 가능 |
| status | VARCHAR(10) | 상태 | — | `active`, `inactive` |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-01-15 09:00:00+09` |

---

#### 5.4.2 tms.carriers (운송사 마스터)

> SAP BP-Carrier | 택배사, 차량업체 등 운송 파트너

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| carrier_code | VARCHAR(20) | 운송사 코드 (UNIQUE) | — | `CRR-CJ`, `CRR-HANJIN` |
| carrier_name | VARCHAR(200) | 운송사명 | — | `CJ대한통운`, `한진택배` |
| carrier_type | VARCHAR(20) | 운송 유형 | — | `truck`(화물차), `courier`(택배), `air`(항공), `sea`(해운), `mixed`(복합) |
| max_cbm_per_trip | NUMERIC(10,3) | 1회 운송 최대 CBM | — | `50.000` |
| assigned_dispatcher | UUID | 담당 배차자 (FK: users) | — | 이 운송사를 관리하는 내부 직원 |
| contact_name | VARCHAR(100) | 담당자명 | — | `김배송` |
| contact_phone | VARCHAR(20) | 담당자 전화번호 | — | `02-1588-1234` |
| notes | TEXT | 비고 | — | `금요일 오후 집하 불가` |
| status | VARCHAR(10) | 상태 | — | `active`, `inactive` |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-01-15 09:00:00+09` |

---

#### 5.4.3 tms.dispatch_schedules (배차 스케줄)

> SAP Vehicle Scheduling | 일별 운송사 배차 용량 관리

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| schedule_date | DATE | 배차일 | — | `2026-04-10` |
| carrier_id | UUID | 운송사 (FK: carriers) | — | 해당일 배정된 운송사 |
| total_cbm_assigned | NUMERIC(10,3) | 배정된 총 CBM | — | `35.500` |
| max_cbm | NUMERIC(10,3) | 최대 가용 CBM | — | `50.000` |
| is_overbooked | BOOLEAN | 초과 예약 여부 | — | `true`=배정 CBM이 최대를 초과 |
| notes | TEXT | 비고 | — | `오전 집하 2건, 오후 1건` |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-04-05 09:00:00+09` |

---

#### 5.4.4 tms.transportation_requirements (운송요청)

> SAP TR | "이 물건을 여기서 저기로 보내주세요" 요청 문서

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| tr_number | VARCHAR(50) | 운송요청 번호 (UNIQUE) | — | `TR-20260330-001` |
| project_id | UUID | 프로젝트 (FK: projects) | — | 관련 프로젝트 |
| origin_location_id | UUID | 출발지 (FK: locations) | — | 출발 위치 |
| destination_location_id | UUID | 도착지 (FK: locations) | — | 도착 위치 |
| requested_shipment_date | DATE | 희망 출하일 | — | `2026-04-10` |
| delivery_type | VARCHAR(20) | 배송 유형 | — | `direct`(직납), `courier`(택배), `relay`(중계), `pickup`(직접수령), `transfer`(이전) |
| packaging_type | VARCHAR(50) | 포장 유형 | — | `box`, `pallet`, `wrapped` |
| payment_method | VARCHAR(20) | 결제 방법 | — | `prepaid`(선불), `collect`(착불) |
| delivery_method | VARCHAR(20) | 배송 방법 | — | `door_to_door`, `terminal` |
| delivery_type_detail | VARCHAR(50) | 배송 유형 상세 | — | 세부 분류 |
| outbound_method | VARCHAR(50) | 출하 방법 | — | `bulk`, `individual` |
| unloading_service | VARCHAR(20) | 하차 서비스 | — | `driver`, `self`, `forklift` |
| recipient_name | VARCHAR(200) | 수령인 이름 | — | `박영희` |
| recipient_phone | VARCHAR(20) | 수령인 전화번호 | — | `010-1234-5678` |
| recipient_alt_phone | VARCHAR(20) | 수령인 보조 전화번호 | — | `02-1234-5678` |
| recipient_address | TEXT | 수령인 주소 | — | `서울시 강남구 ...` |
| recipient_preferred_time | VARCHAR(50) | 수령 희망 시간대 | — | `오전 10~12시` |
| delivery_time_slot | VARCHAR(20) | 배송 시간대 | — | `AM`, `PM`, `ALL_DAY` |
| reception_time_slot | VARCHAR(20) | 수령 가능 시간대 | — | `AM`, `PM` |
| sender_name | VARCHAR(200) | 발송인 이름 | — | `신시어리 물류팀` |
| sender_phone | VARCHAR(20) | 발송인 전화번호 | — | `031-555-0000` |
| sender_address | TEXT | 발송인 주소 | — | `경기도 김포시 ...` |
| outer_box_count | INTEGER | 외박스 수량 | — | `5` |
| cbm_manual | NUMERIC(10,3) | 수동 입력 CBM | — | `3.500` |
| outbound_zone | TEXT[] | 출고 존 배열 | — | `{ZONE-A, ZONE-B}` |
| items_description | TEXT | 품목 설명 | — | `포장박스 200EA, 에코백 100EA` |
| special_instructions | TEXT | 특별 지시사항 | — | `깨지기 쉬움 - 취급 주의` |
| partner_instructions | TEXT | 파트너 안내사항 | — | 운송사/택배 기사에게 전달할 내용 |
| status | VARCHAR(20) | 운송요청 상태 | — | `draft`→`confirmed`→`in_progress`→`completed`→`cancelled` |
| dispatch_status | VARCHAR(20) | 배차 상태 | — | `unassigned`→`assigned`→`dispatched` |
| sync_source | VARCHAR(20) | 연동 출처 | — | `serpa`, `fulfillment`, `movement` (외부 시스템에서 들어온 경우) |
| external_record_id | VARCHAR(100) | 외부 레코드 ID | — | Airtable 등 외부 시스템의 원본 ID |
| is_pre_shipment | BOOLEAN | 사전 출하 여부 | — | `true`=정식 출하 전 사전 배송 |
| outbound_confirmation_url | TEXT | 출고 확인 URL | — | 출고 증빙 사진/문서 링크 |
| created_by | UUID | 생성자 (FK: users) | — | 요청을 생성한 직원 |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-03-30 10:00:00+09` |
| updated_at | TIMESTAMPTZ | 수정일시 | — | `2026-03-30 10:00:00+09` |

---

#### 5.4.5 tms.freight_orders (운송오더)

> SAP Freight Order | 실제 운송 실행 문서 (차량/택배 배정, 비용 정산)

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| fo_number | VARCHAR(50) | 운송오더 번호 (UNIQUE) | — | `FO-20260330-001` |
| tr_id | UUID | 운송요청 (FK: transportation_requirements) | — | 원본 TR |
| carrier_id | UUID | 운송사 (FK: carriers) | — | 배정된 운송사 |
| dispatch_schedule_id | UUID | 배차 스케줄 (FK: dispatch_schedules) | — | 해당일 배차 |
| origin_location_id | UUID | 출발지 (FK: locations) | — | 출발 위치 |
| destination_location_id | UUID | 도착지 (FK: locations) | — | 도착 위치 |
| planned_shipment_date | DATE | 예정 출하일 | — | `2026-04-10` |
| confirmed_shipment_date | DATE | 확정 출하일 | — | `2026-04-10` |
| actual_departure_datetime | TIMESTAMPTZ | 실제 출발 일시 | — | `2026-04-10 14:00:00+09` |
| actual_arrival_datetime | TIMESTAMPTZ | 실제 도착 일시 | — | `2026-04-11 10:00:00+09` |
| shipping_status | VARCHAR(20) | 배송 상태 | — | `planned`→`confirmed`→`in_transit`→`delivered`→`cancelled` |
| delivery_slot | VARCHAR(20) | 배송 시간대 | — | `AM`, `PM`, `ALL_DAY` |
| vehicle_type | VARCHAR(50) | 차량 유형 | — | `1t`, `2.5t`, `5t`, `wing_body` |
| total_cbm | NUMERIC(10,3) | 총 CBM | — | `3.500` |
| freight_revenue | NUMERIC(15,2) | 운송 매출 (고객 청구 금액) | — | `150000.00` |
| freight_cost | NUMERIC(15,2) | 운송 비용 (운송사 지급 금액) | — | `120000.00` |
| loading_cost | NUMERIC(15,2) | 상하차 비용 | — | `30000.00` |
| revenue_account_id | UUID | 매출 계정 (FK: gl_accounts) | — | 운송 수익 GL 계정 |
| cost_account_id | UUID | 비용 계정 (FK: gl_accounts) | — | 운송 비용 GL 계정 |
| tax_invoice_no | VARCHAR(30) | 세금계산서 번호 | — | `20260410-001` |
| tracking_number | VARCHAR(100) | 운송장 번호 | — | `123456789012` |
| packing_list_url | TEXT | 패킹리스트 URL | — | 박스별 내용물 목록 문서 |
| delivery_confirmation_url | TEXT | 배송완료 확인 URL | — | POD(배송증명) 문서/사진 |
| customer_signature_url | TEXT | 수령 서명 URL | — | 고객 서명 이미지 |
| qr_code_url | TEXT | QR 코드 URL | — | 배송 추적용 QR |
| slack_ts | VARCHAR(100) | Slack 스레드 ID | — | 배송 알림 Slack 메시지 타임스탬프 |
| alimtalk_sent | BOOLEAN | 알림톡 발송 여부 | — | `true`=카카오 알림톡 발송 완료 |
| pre_shipment_date | DATE | 사전 출하일 | — | 정식 출하 전 사전 배송일 |
| customer_accepted | BOOLEAN | 고객 수령 확인 | — | `true`=고객이 수령 확인함 |
| customer_accepted_name | VARCHAR(100) | 수령 확인자명 | — | `박영희` |
| customer_accepted_at | TIMESTAMPTZ | 수령 확인 일시 | — | `2026-04-11 10:30:00+09` |
| billing_status | VARCHAR(20) | 청구 상태 | — | `pending`(미청구), `invoiced`(청구완료), `paid`(수금완료) |
| expense_status | VARCHAR(20) | 비용 정산 상태 | — | `pending`(미정산), `invoiced`(청구받음), `paid`(지급완료) |
| portfolio_sent | BOOLEAN | 포트폴리오 발송 여부 | — | `true`=포트폴리오 동봉 |
| portfolio_tracking_number | VARCHAR(100) | 포트폴리오 운송장 | — | 포트폴리오용 별도 운송장 |
| created_by | UUID | 생성자 (FK: users) | — | FO 생성한 직원 |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-03-30 10:00:00+09` |
| updated_at | TIMESTAMPTZ | 수정일시 | — | `2026-04-11 10:30:00+09` |

---

#### 5.4.6 tms.logistics_releases (물류출고지시)

> SAP VL01N Outbound Delivery | 생산 완료품을 창고에서 출고하는 지시서

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| release_number | VARCHAR(50) | 출고지시 번호 (UNIQUE) | VBELN | `LR-20260330-001` |
| production_order_id | UUID | 생산오더 (FK: pp.production_orders, 지연) | AUFNR | 관련 생산오더 |
| project_id | UUID | 프로젝트 (FK: projects) | — | 관련 프로젝트 |
| tr_id | UUID | 운송요청 (FK: transportation_requirements) | — | 연결된 운송요청 |
| status | VARCHAR(20) | 출고지시 상태 | — | `pending`→`picking`→`packed`→`released`→`cancelled` |
| shipment_status | VARCHAR(20) | 출하 상태 | — | 배송 연동 상태 |
| requested_release_date | DATE | 요청 출고일 | — | `2026-04-10` |
| actual_release_date | DATE | 실제 출고일 | — | `2026-04-10` |
| items_summary | TEXT | 품목 요약 | — | `포장박스 200EA` |
| outer_box_count | INTEGER | 외박스 수 | — | `5` |
| outer_box_detail | TEXT | 외박스 상세 | — | `대형 3, 소형 2` |
| remaining_packing | TEXT | 잔여 포장 내역 | — | 아직 포장 안 된 내역 |
| release_confirmation_url | TEXT | 출고확인 URL | — | 출고 증빙 |
| delivery_confirmation_url | TEXT | 배송확인 URL | — | 배송 증빙 |
| customer_signature_url | TEXT | 수령서명 URL | — | 고객 서명 |
| courier_waybill_url | TEXT | 택배 운송장 URL | — | 운송장 이미지 |
| tracking_number | TEXT | 운송장 번호 | — | `123456789012` |
| created_by | UUID | 생성자 (FK: users) | — | 출고지시 생성 직원 |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-03-30 10:00:00+09` |
| updated_at | TIMESTAMPTZ | 수정일시 | — | `2026-04-10 14:00:00+09` |

---

#### 5.4.7 tms.logistics_release_items (물류출고지시 품목)

> SAP LIPS | 출고지시서의 개별 품목 라인

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| release_id | UUID | 출고지시 (FK: logistics_releases) | VBELN | 소속 출고지시서 |
| line_number | INTEGER | 라인번호 | POSNR | `10`, `20` |
| parts_id | UUID | 출고 자재 (FK: parts_master) | MATNR | 출고하는 부품 |
| released_qty | INTEGER | 출고 수량 | LFIMG | `200` |
| batch_id | UUID | 배치 (FK: wms.batches, 지연) | CHARG | 어떤 배치에서 출고 |
| from_bin_id | UUID | 출고 위치 (FK: wms.storage_bins, 지연) | LGPLA | 어느 빈에서 출고 |
| unit_of_measure | VARCHAR(10) | 단위 (FK: units_of_measure) | MEINS | `EA` |

> UNIQUE 제약: (release_id, line_number) -- 출고지시 내 라인번호 유일

---

#### 5.4.8 tms.packaging_materials (포장재 규격)

> SAP Packaging Material Master | 배송용 외박스 규격/부피

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| box_code | VARCHAR(20) | 박스 코드 (UNIQUE) | — | `BOX-S`, `BOX-M`, `BOX-L` |
| box_name | VARCHAR(100) | 박스명 | — | `소형 박스`, `중형 박스` |
| width_cm | NUMERIC(8,2) | 가로 (cm) | — | `30.00` |
| depth_cm | NUMERIC(8,2) | 세로 (cm) | — | `25.00` |
| height_cm | NUMERIC(8,2) | 높이 (cm) | — | `20.00` |
| cbm | NUMERIC(10,6) | 부피 (CBM) | — | `0.015000` |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-01-15 09:00:00+09` |

---

#### 5.4.9 tms.routes (운송 루트)

> SAP TM Route | 사전 정의된 운송 경로

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| route_code | VARCHAR(20) | 루트 코드 (UNIQUE) | — | `RT-WH01-SEL` |
| origin_location_id | UUID | 출발지 (FK: locations) | — | 출발 위치 |
| destination_location_id | UUID | 도착지 (FK: locations) | — | 도착 위치 |
| carrier_id | UUID | 운송사 (FK: carriers) | — | 이 루트의 기본 운송사 |
| standard_transit_days | INTEGER | 표준 운송일수 | — | `1` (1일 소요) |
| cost_rate | NUMERIC(10,2) | 운임 단가 | — | `50000.00` |
| status | VARCHAR(10) | 상태 | — | `active`, `inactive` |

---

### 5.5 pp 스키마 (생산계획)

Production Planning. BOM(자재명세서), 작업장, 공정경로, 생산오더, 생산실적.
총 7개 테이블.

---

#### 5.5.1 pp.bom_headers (BOM 헤더)

> SAP MAST | 자재명세서 헤더 — 완제품 1개를 만드는데 필요한 부품 목록의 상위

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| bom_code | VARCHAR(50) | BOM 코드 (UNIQUE) | STLNR | `BOM-GDS001-V1` |
| goods_id | UUID | 완제품 (FK: goods_master) | MATNR | BOM 대상 완제품 (또는 NULL) |
| item_id | UUID | 반제품 (FK: item_master) | MATNR | BOM 대상 반제품 (또는 NULL) |
| bom_type | VARCHAR(20) | BOM 유형 | STLAN | `kit`(키트), `assembly`(조립), `packaging`(포장) |
| valid_from | DATE | 유효 시작일 | DATEFR | `2026-01-01` |
| valid_to | DATE | 유효 종료일 | DATETO | `2026-12-31` |
| notes | TEXT | 비고 | — | `2026년 봄 시즌 BOM` |
| created_by | UUID | 생성자 (FK: users) | — | BOM 등록 직원 |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-01-15 09:00:00+09` |

> CHECK 제약: goods_id와 item_id 중 정확히 1개만 값이 있어야 함 (완제품 OR 반제품)

---

#### 5.5.2 pp.bom_items (BOM 품목)

> SAP STPO | BOM 구성 부품 목록 — 상위 BOM에 필요한 원자재/포장재

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| bom_id | UUID | BOM 헤더 (FK: bom_headers) | STLNR | 소속 BOM |
| parts_id | UUID | 구성 부품 (FK: parts_master) | IDNRK | 필요한 부품 |
| component_qty | NUMERIC(10,3) | 소요 수량 | MENGE | `2.000` (상위 1개당 2개 필요) |
| unit_of_measure | VARCHAR(10) | 단위 (FK: units_of_measure) | MEINS | `EA` |
| item_category | VARCHAR(20) | 품목 카테고리 | POSTP | `stock`(재고관리), `non_stock`(비재고) |
| scrap_pct | NUMERIC(5,2) | 예상 불량률 (%) | AUSCH | `2.00` (2% 스크랩 예상) |
| sort_order | INTEGER | 정렬 순서 | POSNR | `10`, `20`, `30` |
| notes | TEXT | 비고 | — | `고객 지정 규격` |

---

#### 5.5.3 pp.work_centers (작업장)

> SAP CRHD | 생산이 이루어지는 작업장/임가공 업체

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| wc_code | VARCHAR(20) | 작업장 코드 (UNIQUE) | ARBPL | `WC-INT-01`, `WC-EXT-VD01` |
| wc_name | VARCHAR(200) | 작업장명 | KTEXT | `본사 조립실`, `한국임가공 작업장` |
| wc_type | VARCHAR(20) | 작업장 유형 | — | `internal`(자체), `external_vendor`(외주/임가공) |
| vendor_id | UUID | 임가공 업체 (FK: vendors) | — | 외주인 경우 공급사 연결 |
| capacity_daily | INTEGER | 일일 생산능력 | — | `500` (하루 500개 가능) |
| cost_rate_hourly | NUMERIC(10,2) | 시간당 비용 | — | `15000.00` |
| location | TEXT | 위치 | — | `김포 공장 2층` |
| contact_name | VARCHAR(100) | 담당자명 | — | `박생산` |
| contact_phone | VARCHAR(20) | 담당자 전화번호 | — | `031-555-5678` |
| status | VARCHAR(10) | 상태 | — | `active`, `inactive` |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-01-15 09:00:00+09` |

---

#### 5.5.4 pp.routings (공정경로/라우팅)

> SAP PLKO/PLPO | 생산 공정 순서 — 어떤 작업을 어떤 순서로 수행하는지

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| routing_code | VARCHAR(50) | 공정경로 코드 (UNIQUE) | PLNNR | `RTG-GDS001-V1` |
| bom_id | UUID | BOM (FK: bom_headers) | — | 관련 BOM |
| goods_id | UUID | 완제품 (FK: goods_master) | MATNR | 생산 대상 완제품 |
| operation_number | INTEGER | 공정 번호 | VORNR | `10`, `20`, `30` (10단위 증가) |
| operation_name | VARCHAR(100) | 공정명 | LTXA1 | `인쇄`, `접착`, `조립`, `검사` |
| work_center_id | UUID | 작업장 (FK: work_centers) | ARBPL | 이 공정이 수행되는 작업장 |
| operation_type | VARCHAR(50) | 공정 유형 | — | `assembly`(조립), `packing`(포장), `qc_check`(검사), `printing`(인쇄), `cutting`(재단) |
| standard_time_min | NUMERIC(8,2) | 표준 작업시간 (분) | VGW01 | `5.00` (1개당 5분) |
| setup_time_min | NUMERIC(8,2) | 셋업 시간 (분) | RUEST | `30.00` (공정 전 준비 30분) |
| sort_order | INTEGER | 정렬 순서 | — | `10`, `20`, `30` |
| notes | TEXT | 비고 | — | `고객 샘플 기준 색상 맞춤` |

> UNIQUE 제약: (routing_code, operation_number) -- 공정경로 내 공정번호 유일

---

#### 5.5.5 pp.production_orders (생산오더)

> SAP Production Order | 실제 생산 실행 지시서 (임가공 포함)

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| order_number | VARCHAR(50) | 생산오더 번호 (UNIQUE) | AUFNR | `PRD-20260330-001` |
| project_id | UUID | 프로젝트 (FK: projects) | — | 관련 프로젝트 |
| goods_id | UUID | 생산 완제품 (FK: goods_master) | MATNR | 만들려는 완제품 |
| bom_id | UUID | BOM (FK: bom_headers) | STLNR | 사용할 BOM |
| work_center_id | UUID | 작업장 (FK: work_centers) | ARBPL | 생산할 작업장 |
| vendor_id | UUID | 임가공 업체 (FK: vendors) | LIFNR | 외주 생산인 경우 업체 |
| status | VARCHAR(20) | 생산 상태 | — | `planned`→`released`→`in_progress`→`completed`→`cancelled` |
| planned_start_date | DATE | 계획 시작일 | GSTRP | `2026-04-01` |
| planned_end_date | DATE | 계획 종료일 | GLTRP | `2026-04-05` |
| actual_start_date | DATE | 실제 시작일 | GSTRI | `2026-04-01` |
| actual_end_date | DATE | 실제 종료일 | GLTRI | `2026-04-06` |
| planned_qty | INTEGER | 계획 수량 | GAMNG | `1000` |
| actual_qty | INTEGER | 실제 생산 수량 | — | `980` |
| output_qty | INTEGER | 양품 수량 | — | `960` (합격 수량) |
| scrap_qty | INTEGER | 불량 수량 | — | `20` |
| zone | VARCHAR(20) | 출고 존 | — | `ZONE-A` (생산에 필요한 자재 출고 구역) |
| man_hours_planned | NUMERIC(8,2) | 계획 공수 (시간) | — | `80.00` |
| man_hours_calc | NUMERIC(8,2) | 계산 공수 (시간) | — | 표준시간 기반 자동 계산 |
| man_hours_actual | NUMERIC(8,2) | 실제 공수 (시간) | — | `85.50` |
| unit_cost_actual | NUMERIC(15,4) | 실제 단가 | — | `2500.0000` |
| picking_status | VARCHAR(20) | 피킹 상태 | — | `pending`→`in_progress`→`completed` |
| material_input_status | VARCHAR(20) | 자재 투입 상태 | — | `pending`→`partial`→`completed` |
| assembly_instructions | TEXT | 조립 지시사항 | — | 작업자에게 전달할 조립 순서/방법 |
| design_file_url | TEXT | 디자인 파일 URL | — | 인쇄 시안, 조립 도면 등 |
| special_notes | TEXT | 특별 지시사항 | — | `고객 샘플 기준 정확히 맞출 것` |
| is_bespoke | BOOLEAN | 맞춤제작 여부 | — | `true`=고객 맞춤 제작 |
| cx_responsible_id | UUID | CX 담당자 (FK: users) | — | 이 생산의 CX 책임자 |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-03-30 10:00:00+09` |
| updated_at | TIMESTAMPTZ | 수정일시 | — | `2026-04-06 17:00:00+09` |

---

#### 5.5.6 pp.production_order_components (생산오더 구성품)

> SAP RESB | 생산오더에 필요한 자재 목록 (BOM 전개 결과)

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| production_order_id | UUID | 생산오더 (FK: production_orders) | AUFNR | 소속 생산오더 |
| parts_id | UUID | 소요 자재 (FK: parts_master) | MATNR | 투입해야 하는 부품 |
| required_qty | INTEGER | 소요 수량 | BDMNG | `2000` (완제품 1000개 x BOM 소요량 2) |
| issued_qty | INTEGER | 투입(출고) 수량 | ENMNG | `1800` |
| returned_qty | INTEGER | 반납 수량 | — | `50` (미사용분 창고 반납) |
| storage_bin_id | UUID | 출고 위치 (FK: wms.storage_bins) | — | 자재를 꺼내올 창고 위치 |
| status | VARCHAR(20) | 상태 | — | `pending`→`partial`→`completed` |
| sort_order | INTEGER | 정렬 순서 | — | `10`, `20` |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-04-01 09:00:00+09` |

---

#### 5.5.7 pp.production_confirmations (생산실적확인)

> SAP AFRU | 생산 공정별 작업 완료 실적 보고

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| production_order_id | UUID | 생산오더 (FK: production_orders) | AUFNR | 실적 대상 생산오더 |
| confirmation_date | TIMESTAMPTZ | 확인 일시 | BUDAT | `2026-04-03 16:00:00+09` |
| operation_type | VARCHAR(50) | 공정 유형 | — | `assembly`(조립), `packing`(포장), `qc_check`(검사) |
| completed_qty | INTEGER | 완료 수량 | LMNGA | `300` |
| man_hours_actual | NUMERIC(8,2) | 실제 투입 공수 (시간) | ISM01 | `8.50` |
| worker_id | UUID | 작업자 (FK: users) | — | 작업을 수행한 직원 |
| notes | TEXT | 비고 | — | `오전 인쇄불량 5건 재작업` |
| photos_url | TEXT | 작업 사진 URL | — | 작업 증빙 사진 |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-04-03 16:30:00+09` |

---

### 5.6 finance 스키마 (회계)

K-IFRS 기준 회계 전표 + 더존 아마란스10 연계. SCM 트랜잭션의 회계 영향을 추적.
총 4개 테이블.

> **핵심 원칙**: 더존 아마란스10이 실질 원장(Real Ledger). 본 시스템은 SCM 트랜잭션에서 회계 전표 초안을 생성하고, 더존과의 동기화 상태를 추적합니다.

---

#### 5.6.1 finance.accounting_entries (회계 전표)

> SAP BKPF/BSEG | SCM 분개 전표 — 단일행 차변/대변 패턴

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| entry_number | VARCHAR(50) | 전표번호 (UNIQUE, 자동생성) | BELNR | `AE-20260411-0001` |
| entry_date | DATE | 전표일자 | BLDAT | `2026-04-11` |
| entry_type | VARCHAR(30) | 전표 유형 | — | `purchase_invoice`(매입), `goods_receipt`(입고), `goods_issue`(출고), `production`(생산), `assembly_issue`(조립투입), `assembly_receipt`(조립입고), `freight`(운송), `inventory_adjustment`(재고조정) |
| source_table | VARCHAR(50) | 원본 테이블명 | — | `mm.goods_receipts`, `mm.stock_movements` 등 |
| source_id | UUID | 원본 레코드 ID | — | 전표를 발생시킨 SCM 트랜잭션 ID |
| debit_account_id | UUID | 차변 계정 (FK: gl_accounts) | HKONT | 차변(왼쪽)에 기록되는 계정 |
| credit_account_id | UUID | 대변 계정 (FK: gl_accounts) | HKONT | 대변(오른쪽)에 기록되는 계정 |
| amount | NUMERIC(15,2) | 금액 (양수만) | DMBTR | `1500000.00` |
| quantity | INTEGER | 수량 | MENGE | `1000` |
| unit_cost | NUMERIC(15,4) | 단가 | — | `1500.0000` |
| costing_method | VARCHAR(15) | 원가산정 방법 | — | `weighted_avg`(가중평균), `fifo`(선입선출) |
| tax_invoice_no | VARCHAR(30) | 세금계산서 번호 | — | `20260411-001` |
| vat_amount | NUMERIC(15,2) | 부가세 금액 | — | `150000.00` |
| fiscal_year | VARCHAR(4) | 회계연도 | GJAHR | `2026` |
| fiscal_period | VARCHAR(2) | 회계기간 | MONAT | `04` (4월) |
| currency_code | CHAR(3) | 통화 코드 | WAERS | `KRW` |
| status | VARCHAR(15) | 전표 상태 | — | `draft`→`reviewed`→`posted` |
| reviewed_by | UUID | 검토자 (FK: users) | — | 전표를 검토한 직원 |
| reviewed_at | TIMESTAMPTZ | 검토 일시 | — | `2026-04-12 09:00:00+09` |
| posted_by | UUID | 기표자 (FK: users) | — | 최종 기표한 직원 |
| posted_at | TIMESTAMPTZ | 기표 일시 | — | `2026-04-12 10:00:00+09` |
| is_reversal | BOOLEAN | 역분개 여부 | STBLG | `true`=다른 전표를 취소하는 역분개 |
| reversal_entry_id | UUID | 역분개 원본 (FK: accounting_entries) | STBLG | 취소 대상 원래 전표 ID |
| douzone_slip_no | VARCHAR(30) | 더존 전표번호 | — | 회계팀이 더존에서 확정 후 기재하는 번호 |
| description | TEXT | 전표 설명 | SGTXT | `PO-20260330-001 입고 / 크라프트 박스 1000EA` |
| created_by | UUID | 생성자 (FK: users) | USNAM | 전표 생성 직원 |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-04-11 09:00:00+09` |
| updated_at | TIMESTAMPTZ | 수정일시 | — | `2026-04-12 10:00:00+09` |

---

#### 5.6.2 finance.cost_settings (원가 설정)

> SAP OBYA/T030 | 자재유형별 원가산정 방법 설정

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| parts_type | VARCHAR(50) | 자재유형 | — | `raw`(원자재), `packaging`(포장재), `merchandise`(상품), `semi_finished`(반제품) |
| costing_method | VARCHAR(15) | 원가산정 방법 | — | `weighted_avg`(가중평균법), `fifo`(선입선출법) |
| effective_from | DATE | 적용 시작일 | — | `2026-01-01` |
| effective_to | DATE | 적용 종료일 (NULL=현행) | — | `NULL` (현재 적용 중) |
| set_by | UUID | 설정자 (FK: users) | — | 원가 정책을 설정한 직원 |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-01-01 09:00:00+09` |

> UNIQUE 제약: (parts_type, effective_from) -- 자재유형+시작일 조합으로 유일

---

#### 5.6.3 finance.douzone_sync_log (더존 연동 이력)

> 커스텀 | SCM 전표 -> 더존 아마란스10 동기화 상태 추적

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| entry_id | UUID | 회계전표 (FK: accounting_entries) | — | 동기화 대상 전표 |
| douzone_slip_no | VARCHAR(30) | 더존 전표번호 | — | 더존에서 생성된 전표번호 |
| sync_status | VARCHAR(20) | 동기화 상태 | — | `pending`(대기), `synced`(완료), `error`(오류) |
| sync_notes | TEXT | 동기화 비고 | — | 오류 메시지, 비고 등 |
| synced_by | UUID | 동기화 담당자 (FK: users) | — | 동기화를 수행/확인한 직원 |
| synced_at | TIMESTAMPTZ | 동기화 일시 | — | `2026-04-12 11:00:00+09` |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-04-12 10:00:00+09` |

---

#### 5.6.4 finance.period_closes (월말마감 스냅샷)

> SAP MARDH/MBEWH | 월말 마감 시 자재별/창고별 재고 평가 스냅샷

| 컬럼명 | 데이터타입 | 한글 설명 | SAP 대응 | 예시 |
|--------|-----------|-----------|----------|------|
| id | UUID | 고유 식별자 (PK) | — | `550e8400-...` |
| period | VARCHAR(7) | 마감 기간 (YYYY-MM) | LFGJA/LFMON | `2026-03` |
| parts_id | UUID | 자재 (FK: parts_master) | MATNR | 마감 대상 부품 |
| warehouse_id | UUID | 창고 (FK: wms.warehouses) | LGNUM | 마감 대상 창고 |
| closing_qty | INTEGER | 마감 재고 수량 | — | `500` |
| closing_value | NUMERIC(15,2) | 마감 재고 금액 | — | `750000.00` (500 x 1500) |
| unit_cost | NUMERIC(15,4) | 기간 단위원가 | — | `1500.0000` |
| costing_method | VARCHAR(15) | 원가산정 방법 | — | `weighted_avg`, `fifo` |
| is_closed | BOOLEAN | 마감 확정 여부 | — | `true`=확정 (이후 변경 불가) |
| closed_by | UUID | 마감자 (FK: users) | — | 마감을 확정한 직원 |
| closed_at | TIMESTAMPTZ | 마감 확정 일시 | — | `2026-04-05 18:00:00+09` |
| created_at | TIMESTAMPTZ | 생성일시 | — | `2026-04-01 09:00:00+09` |

> UNIQUE 제약: (period, parts_id, warehouse_id) -- 기간+자재+창고 조합으로 유일

---

## 부록: 테이블 수 집계

| 스키마 | 테이블 수 | 테이블 목록 |
|--------|----------|------------|
| **shared** | 14 | units_of_measure, gl_accounts, material_types, material_groups, organizations, users, clients, vendors, projects, goods_master, item_master, parts_master, material_valuation, vendor_evaluations |
| **mm** | 10 | purchase_requisitions, purchase_orders, purchase_order_items, goods_receipts, stock_movements, invoice_verifications, reservations, return_orders, quality_inspections, scrap_records |
| **wms** | 7 | warehouses, storage_types, storage_bins, batches, quants, inventory_count_docs, inventory_count_items |
| **tms** | 9 | locations, carriers, dispatch_schedules, transportation_requirements, freight_orders, logistics_releases, logistics_release_items, packaging_materials, routes |
| **pp** | 7 | bom_headers, bom_items, work_centers, routings, production_orders, production_order_components, production_confirmations |
| **finance** | 4 | accounting_entries, cost_settings, douzone_sync_log, period_closes |
| **합계** | **51** | |

---

## 부록: 주요 테이블 간 관계도 (텍스트)

```
shared.projects ──────┬──── mm.purchase_orders ──── mm.purchase_order_items
  │                    │         │                           │
  │                    │         └── mm.goods_receipts ──────┤
  │                    │                    │                 │
  │                    │                    └── wms.batches   │
  │                    │                                      │
  │                    ├──── pp.production_orders ─── pp.production_order_components
  │                    │         │
  │                    │         └── pp.bom_headers ──── pp.bom_items
  │                    │
  │                    └──── tms.transportation_requirements
  │                              │
  │                              └── tms.freight_orders
  │                              └── tms.logistics_releases ──── tms.logistics_release_items
  │
shared.parts_master ──── (거의 모든 트랜잭션 테이블에서 참조)
  │
shared.vendors ──── mm.purchase_orders
  │
shared.gl_accounts ──── finance.accounting_entries
                         │
                         └── finance.douzone_sync_log
                         └── finance.period_closes
```

---

> 이 문서는 Supabase 마이그레이션 파일(002~011)을 기준으로 자동 생성되었습니다.
> 실제 운영 DB(sap 스키마)와 TO-BE(6스키마)가 병존하고 있으며, 이 문서는 TO-BE 구조를 다룹니다.
