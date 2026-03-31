# 신시어리 SCM 시스템 전환 발표 자료 — Claude AI 아티팩트 생성용

> 이 문서를 Claude AI에 붙여넣고 "이 내용으로 인터랙티브 HTML 발표 자료를 만들어줘"라고 요청하세요.
> 4개 섹션을 각각 별도 아티팩트 또는 탭으로 생성 권장.

---

## 발표 개요

- **발표자**: 물류파트 SCM 담당
- **회사**: 신시어리 — 임직원 선물 키트, 포장재 B2B 공급
- **목적**: Airtable 기반 운영 시스템을 Supabase + Retool + 더존 아마란스10 체계로 전환하는 계획 공유
- **청중**: 비개발 실무진 포함 (붕어빵 가게 비유로 이해도 확보)

---

## 섹션 1: As-Is / To-Be 워크플로우 비교

### 1-A. 실제 시스템 비교

#### AS-IS (현재 운영 중)

```
[운영자 수동 입력]
      │
      ▼
┌─────────────────────────────┐
│  Airtable (WMS+TMS 2 base)  │
│  30개 테이블 / 445개 필드     │
│  스프레드시트형 평면 구조      │
│  이모지 필드명, 중복 데이터    │
└──────────┬──────────────────┘
           │ webhook
           ▼
┌─────────────────────────────┐
│  NestJS (ngrok 임시 URL)     │
│  PM2 프로세스 매니저          │
└──────────┬──────────────────┘
           │ INSERT
           ▼
┌─────────────────────────────┐
│  Supabase sap 스키마         │
│  Shadow Ledger (4테이블)     │
│  mat_master, mat_document    │
│  stock_balance, period_close │
│  8,400+ 이동문서 적재 완료    │
└─────────────────────────────┘
```

**AS-IS 한계점:**
- Airtable은 스프레드시트 — 트랜잭션 보장 없음, 이력 추적 취약
- 이모지 포함 필드명 → 파이프라인 파싱 오류 발생
- 재고 rollup 필드 isValid:false 버그 → 수동 우회 중
- ngrok URL이 매 세션 변경 → webhook 수신 불안정
- 회계 연동 없음 — 더존에 수동 기표

#### TO-BE (전환 목표)

```
[운영자 입력]
      │
      ▼
┌─────────────────────────────┐
│  Retool (9페이지 운영 UI)    │
│  27개 조회 쿼리              │
│  15개 CRUD 뮤테이션 쿼리     │
│  프로젝트→발주→입고→생산      │
│  →출고→배송→회계 E2E 커버    │
└──────────┬──────────────────┘
           │ SQL (Supabase Pooler)
           ▼
┌─────────────────────────────────────────┐
│  Supabase PostgreSQL                     │
│  6 스키마 / 51 테이블                     │
│                                          │
│  shared (14) — 마스터 데이터              │
│  mm (10)     — 구매/입고/재고이동          │
│  wms (7)     — 창고/BIN/배치/재고수량      │
│  pp (6)      — BOM/생산오더/확인           │
│  tms (9)     — 운송요청/오더/배차          │
│  finance (4) — 전표/원가/더존연동/마감      │
│                                          │
│  자동 트리거 5개:                          │
│  입고→전표 / 출고→전표 / 운임→전표         │
│  재고이동→quants 갱신 / 실사→조정전표      │
└──────────┬──────────────────────────────┘
           │
     ┌─────┼─────────┐
     ▼     ▼         ▼
┌────────┐ ┌────────┐ ┌──────────────┐
│ NocoDB │ │Metabase│ │더존 아마란스10│
│테이블   │ │대시보드│ │실질 회계 원장 │
│탐색기   │ │차트    │ │K-IFRS 기표   │
└────────┘ └────────┘ └──────────────┘
```

**TO-BE 핵심 이점:**
- 정규화된 관계형 DB — 데이터 무결성 보장
- 불변 원장 원칙 — INSERT ONLY, 정정은 역분개(Storno)
- 자동 트리거 — 입고하면 회계 전표 자동 생성
- 더존 연계 — 전표 초안 자동 생성 → 회계팀 검토 → 더존 확정 기표
- 고정 URL (Railway) — webhook 안정성 확보

### 1-B. 붕어빵 가게 비유 (비개발자용)

#### AS-IS: 종이 장부 붕어빵 가게

```
주문 접수: 사장님이 포스트잇에 메모 (Airtable 수동 입력)
    │
    ▼
재료 발주: 밀가루 10kg 주문 → 포스트잇에 "밀가루 10kg 주문함" 메모
    │ (다른 포스트잇에도 같은 내용 중복 기록)
    ▼
재료 입고: 밀가루 도착 → 포스트잇에 "밀가루 왔음" 메모
    │ (재고 수량은 머릿속으로 계산)
    ▼
붕어빵 제작: 밀가루 3kg 사용 → 기록 안 함 (나중에 "어? 밀가루 어디갔지?")
    │
    ▼
판매/배달: 붕어빵 100개 배달 → 포스트잇에 "100개 보냄"
    │
    ▼
정산: 월말에 포스트잇 모아서 계산 → 숫자 안 맞음 → 야근

문제점:
- 포스트잇(Airtable)이 여기저기 흩어져 있음
- 같은 정보를 여러 곳에 중복 기록
- 재고가 얼마나 남았는지 정확히 모름
- 회계 정산은 수동으로 따로 해야 함
```

#### TO-BE: 디지털 POS 붕어빵 가게

```
주문 접수: 태블릿 POS에서 터치 (Retool 화면에서 입력)
    │
    ▼
재료 발주: POS에서 "밀가루 10kg 발주" 버튼 클릭
    │ → 자동으로 발주서(PO) 생성, 공급업체에 알림
    ▼
재료 입고: 밀가루 도착 → POS에서 "입고 확인" 버튼
    │ → 재고 자동 +10kg (트리거)
    │ → 회계 전표 자동 생성: "밀가루 10kg / 50,000원 입고" (트리거)
    ▼
붕어빵 제작: POS에서 "생산 시작" → 밀가루 3kg 자동 차감 (트리거)
    │ → 회계 전표 자동: "원재료 3kg 생산투입" (트리거)
    ▼
판매/배달: POS에서 배달 등록 → 재고 자동 -100개
    │ → 운송장 자동 생성, 배달 추적 가능
    ▼
정산: 월말에 버튼 하나 → 자동 집계
    │ → 더존(회계 프로그램)에 숫자 그대로 전달
    │ → 야근 없음!

핵심 차이:
- 모든 데이터가 한 곳(Supabase)에 정리됨
- 입고하면 재고+회계가 자동으로 따라감
- 실시간으로 재고 정확히 파악
- 월말 정산이 버튼 하나로 끝남
```

---

## 섹션 2: 마이그레이션 맵 (Airtable → SAP+더존 SSOT)

### 전체 매핑 구조

```
Airtable (AS-IS)              Supabase (TO-BE)           SAP 대응        더존 연계
════════════════              ════════════════           ════════        ════════════

WMS Base
├─ Products 테이블     →→→    shared.goods_master        FERT(완제품)     —
├─ Items 테이블        →→→    shared.item_master          HALB(반제품)     —
├─ Parts 테이블        →→→    shared.parts_master         ROH/VERP        —
├─ Clients 테이블      →→→    shared.clients              BP-Customer     거래처코드
├─ Vendors 테이블      →→→    shared.vendors              BP-Vendor       douzone_vendor_code
├─ Projects 테이블     →→→    shared.projects             PS              —
├─ PO 테이블           →→→    mm.purchase_orders          EKKO            —
├─ PO Items 테이블     →→→    mm.purchase_order_items     EKPO            —
├─ GR 테이블           →→→    mm.goods_receipts           MKPF            세금계산서
├─ Stock Movement      →→→    mm.stock_movements          MSEG            이동유형별 전표
├─ Inventory 테이블    →→→    wms.quants                  /SCWM/AQUA      —
├─ Warehouse 테이블    →→→    wms.warehouses              T001W           —
├─ BIN 테이블          →→→    wms.storage_bins            LAGP            —
├─ Batch 테이블        →→→    wms.batches                 MCHA            —
├─ BOM 테이블          →→→    pp.bom_headers + bom_items  CS01            —
├─ Production 테이블   →→→    pp.production_orders        CO01            —
│
TMS Base
├─ TR 테이블           →→→    tms.transportation_requirements  SAP TR    —
├─ FO 테이블           →→→    tms.freight_orders               SAP FO    운임전표
├─ Carriers 테이블     →→→    tms.carriers                     BP-Carrier —
├─ Dispatch 테이블     →→→    tms.dispatch_schedules           —          —
│
(신규 — Airtable에 없음)
│                             finance.accounting_entries       BKPF/BSEG  douzone_slip_no
│                             finance.cost_settings            T030       원가설정
│                             finance.douzone_sync_log         —          동기화이력
│                             finance.period_closes            MARDH      기간마감
│                             shared.gl_accounts               SKA1       douzone_code
│                             shared.material_types             T134       —
│                             shared.material_groups             T023       —
│                             shared.organizations               T001       —
│                             shared.units_of_measure             T006       —
│                             shared.material_valuation           MBEW       원가평가
│                             shared.vendor_evaluations           ME61       —
│                             mm.purchase_requisitions             EBAN       —
│                             mm.invoice_verifications             MIRO       3-way match
│                             mm.reservations                      RESB       —
│                             mm.quality_inspections               QALS       —
│                             mm.scrap_records                     —          폐기전표
│                             wms.storage_types                    /SCWM/T_ST —
│                             wms.inventory_count_docs             IKPF       —
│                             wms.inventory_count_items             ISEG       조정전표
│                             tms.locations                        —          —
│                             tms.logistics_releases               VL01N      —
│                             tms.logistics_release_items           LIPS       —
│                             tms.packaging_materials               —          —
│                             tms.routes                            —          —
│                             pp.work_centers                       CRHD       —
│                             pp.routings                           PLKO       —
│                             pp.production_order_components         RESB       —
│                             pp.production_confirmations            AFRU       —
```

### DFD (Data Flow Diagram) — 핵심 흐름

```
                    ┌──────────┐
                    │  고객사   │
                    └────┬─────┘
                         │ 주문
                         ▼
┌─────────┐      ┌──────────────┐      ┌───────────┐
│ 공급업체 │◄────│   프로젝트     │────►│  CX 담당자 │
└────┬────┘      │ shared.projects│     └───────────┘
     │           └──────┬───────┘
     │ 발주서           │ 생산지시
     ▼                  ▼
┌──────────┐     ┌──────────────┐
│ 구매발주  │     │   생산오더    │
│ mm.PO    │     │ pp.prod_orders│
└────┬─────┘     └──────┬───────┘
     │ 입고              │ 자재투입(261)
     ▼                  ▼
┌──────────┐     ┌──────────────┐
│ 입고검수  │     │  BOM 소요     │
│ mm.GR    │────►│ pp.bom_items  │
└────┬─────┘     └──────┬───────┘
     │                  │ 완성품입고
     ▼                  ▼
┌──────────────────────────────┐
│        재고 원장              │
│   wms.quants (현재고)         │
│   mm.stock_movements (이력)   │
│   wms.batches (배치/FIFO)     │
└──────────┬───────────────────┘
           │ 출고(601)
           ▼
┌──────────────┐     ┌──────────────┐
│  운송요청     │────►│  운송오더     │
│ tms.TR       │     │ tms.FO       │
└──────────────┘     └──────┬───────┘
                            │ 배송완료
                            ▼
                     ┌──────────────┐
                     │  회계 전표    │
                     │ finance.     │
                     │ accounting_  │
                     │ entries      │
                     └──────┬───────┘
                            │ 동기화
                            ▼
                     ┌──────────────┐
                     │더존 아마란스10│
                     │ K-IFRS 기표  │
                     └──────────────┘
```

### ERD 핵심 관계 (6스키마 주요 FK)

```
shared.clients ──1:N──► shared.projects ──1:N──► mm.purchase_orders
                              │                        │
                              │                   1:N  │
                              │                        ▼
                              │               mm.purchase_order_items
                              │                        │
                              │                   1:N  │
                              │                        ▼
                              │               mm.goods_receipts ──trigger──► finance.accounting_entries
                              │                        │
                              │                   1:N  │
                              │                        ▼
                              │               mm.stock_movements ──trigger──► wms.quants (시스템재고 갱신)
                              │
                         1:N  │
                              ▼
                    pp.production_orders ──M:N(BOM)──► shared.parts_master
                              │
                         1:N  │
                              ▼
                    tms.transportation_requirements
                              │
                         1:N  │
                              ▼
                    tms.freight_orders ──trigger──► finance.accounting_entries (운임전표)

shared.parts_master ◄── shared.vendors (기본 공급사)
shared.gl_accounts  ◄── shared.material_types (자재유형별 기본 차변/대변 계정)
finance.accounting_entries ──► finance.douzone_sync_log (더존 동기화 추적)
```

### 더존 아마란스10 전표 연동 맵

| SCM 이벤트 | 트리거 | 전표 유형 | 차변 계정 | 대변 계정 | 더존 처리 |
|---|---|---|---|---|---|
| 입고 (GR INSERT) | 트리거1 | goods_receipt | 146000 원재료 | 252000 외상매입금 | 매입 전표 |
| 생산투입 (261) | 트리거2 | assembly_issue | 451000 제조원가 | 146000 원재료 | 원가 대체 |
| 생산완료 | 트리거3 | assembly_receipt | 167000 반제품 | 451000 제조원가 | 생산 완료 |
| 출고 (601) | 트리거4 | goods_issue | 401000 매출원가 | 167000 반제품 | 매출원가 |
| 운임 청구 | 트리거5 | freight | 831000 운반비 | 253000 미지급금 | 운반비 |
| 재고 조정 | 트리거6 | inventory_adj | 484000 재고손실 | 146000 원재료 | 재고 조정 |

---

## 섹션 3: To-Be 스키마 탐색기

### 6스키마 51테이블 전체 구조

#### shared 스키마 (14개 테이블) — 공통 마스터

| 테이블 | SAP 대응 | 핵심 컬럼 | 용도 |
|---|---|---|---|
| units_of_measure | T006 | uom_code (EA/KG/M/SET/BOX/SHEET/ROLL/PCS) | 단위 기준 |
| gl_accounts | SKA1 | account_code, douzone_code, normal_balance (debit/credit) | 더존 계정 매핑 |
| material_types | T134 | type_code (ROH/HALB/FERT/VERP/HIBE/HAWA) | 자재유형+기본 GL 매핑 |
| material_groups | T023 | group_code, parent_id (계층구조) | 자재그룹 |
| organizations | T001/T001W | org_code, org_type (company/plant/warehouse) | 조직 구조 |
| users | SU01 | auth_user_id, employee_number, team, slack_id | 사용자 |
| clients | BP-Customer | client_code, company_name, business_reg_number | 고객사 |
| vendors | BP-Vendor | vendor_code, douzone_vendor_code, is_stock_vendor | 공급업체 |
| projects | PS | project_code, cx_specialist_id, first_shipment_date | 프로젝트 |
| goods_master | FERT | goods_code, default_bom_id | 완제품 (선물키트) |
| item_master | HALB | item_code, production_type, requires_assembly | 반제품 (조립품) |
| parts_master | ROH/VERP | parts_code, vendor_id, reorder_point, is_customer_goods | 원자재/포장재 |
| material_valuation | MBEW | costing_method (weighted_avg/fifo), moving_avg_price | 원가 평가 |
| vendor_evaluations | ME61 | quality/delivery/price/overall_score, period | 공급사 평가 |

#### mm 스키마 (10개 테이블) — 구매/입고/재고이동

| 테이블 | SAP 대응 | 핵심 컬럼 | 데이터 원칙 |
|---|---|---|---|
| purchase_requisitions | EBAN | source (manual/mrp/reorder) | CRUD 가능 |
| purchase_orders | EKKO | po_status (draft→sent→confirmed→received→closed) | 상태변경만 |
| purchase_order_items | EKPO | order_qty, unit_price, total_amount(자동계산) | CRUD 가능 |
| goods_receipts | MKPF | received_qty, accepted_qty, rejected_qty, inspection_result | INSERT ONLY (불변) |
| stock_movements | MSEG | movement_type(15종), is_reversal, actual_qty | INSERT ONLY (불변) |
| invoice_verifications | MIRO | match_result (exact/within_tolerance/over_tolerance) | 3-way match |
| reservations | RESB | movement_type (261/201/601) | 예약 |
| return_orders | — | direction (vendor/customer), disposition | 반품 |
| quality_inspections | QALS | inspection_type, defect_codes(배열) | 품질 |
| scrap_records | — | reason_code, movement_id(551) | 폐기 |

#### wms 스키마 (7개 테이블) — 창고/재고

| 테이블 | SAP 대응 | 핵심 컬럼 | 비고 |
|---|---|---|---|
| warehouses | T001W | warehouse_code, max_cbm | 창고 |
| storage_types | /SCWM/T_ST | type_code (HR/FL) | 저장 유형 |
| storage_bins | LAGP | bin_code (A-01-01 좌표형), zone | BIN 위치 |
| batches | MCHA | batch_number, unit_cost (FIFO 원가) | 배치 |
| quants | /SCWM/AQUA | physical_qty, system_qty, available_qty(자동계산) | 현재고 |
| inventory_count_docs | IKPF | count_type (annual/cycle/spot) | 실사 문서 |
| inventory_count_items | ISEG | book_qty, count_qty, difference | 실사 항목 |

#### tms 스키마 (9개 테이블) — 운송/배송

| 테이블 | SAP 대응 | 핵심 컬럼 | 비고 |
|---|---|---|---|
| locations | TM Location | location_type (warehouse/customer/vendor/hub) | 위치 |
| carriers | BP-Carrier | carrier_type, max_cbm_per_trip | 운송사 |
| dispatch_schedules | — | total_cbm_assigned, is_overbooked | 배차 |
| transportation_requirements | SAP TR | delivery_type (direct/courier/relay/pickup/transfer) | 운송요청 |
| freight_orders | SAP FO | shipping_status, billing_status, tracking_number | 운송오더 |
| logistics_releases | VL01N | status (pending→picking→packed→released) | 출고지시 |
| logistics_release_items | LIPS | released_qty, batch_id, from_bin_id | 출고품목 |
| packaging_materials | — | box_code, width/depth/height_cm, cbm | 포장재 |
| routes | — | origin→destination, standard_transit_days | 경로 |

#### pp 스키마 (6개 테이블) — 생산/조립

| 테이블 | SAP 대응 | 핵심 컬럼 | 비고 |
|---|---|---|---|
| bom_headers | CS01 | bom_type (kit/assembly/packaging) | BOM 헤더 |
| bom_items | STPO | component_qty, scrap_pct | BOM 품목 |
| work_centers | CRHD | wc_type (internal/external_vendor) | 작업장 |
| routings | PLKO | operation_type (assembly/packing/qc/printing/cutting) | 공정 |
| production_orders | CO01 | planned/actual/output_qty, status | 생산오더 |
| production_order_components | RESB | required_qty, issued_qty, returned_qty | 소요자재 |
| production_confirmations | AFRU | completed_qty, man_hours_actual | 생산실적 |

#### finance 스키마 (4개 테이블) — 회계/더존

| 테이블 | SAP 대응 | 핵심 컬럼 | 비고 |
|---|---|---|---|
| accounting_entries | BKPF/BSEG | entry_type, debit/credit_account_id, amount, status, douzone_slip_no | 분개전표 |
| cost_settings | T030 | parts_type별 costing_method, effective_from/to | 원가설정 |
| douzone_sync_log | — | sync_status (pending/synced/error) | 더존동기화 |
| period_closes | MARDH | period, closing_qty/value, is_closed | 기간마감 |

### 자재 3단계 체계

```
┌─────────────────────────────────────┐
│  Goods (FERT 완제품)                 │
│  예: "프리비알 VIP 이벤트 150세트"    │
│  goods_master.goods_code             │
└───────────┬─────────────────────────┘
            │ BOM (pp.bom_headers/items)
            ▼
┌─────────────────────────────────────┐
│  Item (HALB 반제품/조립품)            │
│  예: "VIP 박스 조립세트"              │
│  item_master.item_code               │
└───────────┬─────────────────────────┘
            │ BOM (pp.bom_headers/items)
            ▼
┌─────────────────────────────────────┐
│  Parts (ROH 원자재 / VERP 포장재)    │
│  예: "크라프트 박스 300x200x150"      │
│  예: "리본 테이프 빨강 25mm"          │
│  parts_master.parts_code             │
└─────────────────────────────────────┘

핵심: Goods↔Item↔Parts 간 직접 FK 없음.
     관계는 오직 BOM(Bill of Materials)으로만 표현.
```

### SAP 이동유형 체계 (stock_movements.movement_type)

| 코드 | 한글명 | 방향 | 회계 전표 |
|---|---|---|---|
| 101 | 입고 | + | DR 원재료 / CR 매입채무 |
| 102 | 입고취소 | - | 역분개 |
| 122 | 공급사반품 | - | DR 매입채무 / CR 원재료 |
| 161 | 고객반품 | + | DR 반제품 / CR 매출원가 |
| 201 | 원가센터출고 | - | — |
| 261 | 생산투입 | - | DR 제조원가 / CR 원재료 |
| 262 | 생산반납 | + | 역분개 |
| 301 | 재고이전 | ± | — |
| 551 | 폐기 | - | DR 폐기손실 / CR 원재료 |
| 561 | 초기재고 | + | — |
| 601 | 납품출고 | - | DR 매출원가 / CR 반제품 |
| 701 | 실사조정(+) | + | DR 원재료 / CR 잡이익 |
| 702 | 실사조정(-) | - | DR 잡손실 / CR 원재료 |

---

## 섹션 4: E2E 워크플로우 (프로젝트 1개 예시)

### 프로젝트: PRJ-2026-025 "프리비알 VIP 이벤트 150세트"

```
STEP 1: 프로젝트 등록
━━━━━━━━━━━━━━━━━━━
Retool [dashboard] → 프로젝트 생성
  shared.projects INSERT
  ├─ project_code: PRJ-2026-025
  ├─ project_name: 프리비알 VIP 이벤트 150세트 (긴급)
  ├─ client: 프리비알
  ├─ cx_specialist: 우예림
  ├─ first_shipment_date: 2026-04-15
  └─ status: planning → active

STEP 2: BOM 확인
━━━━━━━━━━━━━━━
Retool [master_data] → BOM 조회
  pp.bom_headers + pp.bom_items
  ├─ BOM: "프리비알 VIP 키트"
  │   ├─ 크라프트 박스 300x200x150    × 1ea
  │   ├─ 리본 테이프 빨강 25mm        × 2m
  │   ├─ 완충재 PE폼                  × 1ea
  │   ├─ 프리비알 로고 스티커          × 2ea  ← is_customer_goods=true (고객 지급)
  │   └─ 프리비알 카탈로그             × 1ea  ← is_customer_goods=true
  └─ 총 소요 = 150세트 × 각 수량

STEP 3: 발주
━━━━━━━━━━━
Retool [purchase_orders] → PO 생성
  mm.purchase_orders INSERT
  ├─ po_number: PO-2026-0401-001
  ├─ vendor: 한솔제지 (크라프트 박스)
  ├─ status: draft → sent
  └─ requested_date: 2026-04-03

  mm.purchase_order_items INSERT (3라인)
  ├─ Line 1: 크라프트 박스 150ea × @2,500원 = 375,000원
  ├─ Line 2: 리본 테이프 300m × @800원 = 240,000원
  └─ Line 3: 완충재 150ea × @500원 = 75,000원

STEP 4: 입고/검수
━━━━━━━━━━━━━━━
Retool [goods_receipt] → GR 등록
  mm.goods_receipts INSERT (불변)
  ├─ gr_number: GR-20260405-3847
  ├─ received_qty: 150
  ├─ accepted_qty: 148 (2개 불량)
  ├─ rejected_qty: 2
  ├─ inspection_result: conditional_pass
  └─ unit_cost: 2,500원

  ◆ 트리거 자동 발동:
  │
  ├─► mm.stock_movements INSERT (이동유형 101)
  │   actual_qty: 148, status: completed
  │
  ├─► wms.quants UPSERT (트리거: trg_stock_movement_update_quants)
  │   크라프트 박스 system_qty: +148
  │
  └─► finance.accounting_entries INSERT (트리거: trg_goods_receipt_accounting)
      entry_type: goods_receipt
      DR: 146000 원재료    370,000원
      CR: 252000 외상매입금 370,000원
      status: draft (회계팀 검토 대기)

STEP 5: 생산/조립
━━━━━━━━━━━━━━━
Retool [production] → 생산오더 생성
  pp.production_orders INSERT
  ├─ order_number: PRD-2026-0407-001
  ├─ project_id: PRJ-2026-025
  ├─ planned_qty: 150
  ├─ status: planned → in_progress
  └─ vendor_id: (주)굿박스 (임가공 업체)

  자재 불출 (생산투입):
  mm.stock_movements INSERT (이동유형 261)
  ├─ 크라프트 박스 148ea 불출
  ├─ 리본 테이프 300m 불출
  └─ 완충재 148ea 불출

  ◆ 트리거 자동 발동:
  ├─► wms.quants: 각 자재 system_qty 차감
  └─► finance.accounting_entries:
      DR: 451000 제조원가
      CR: 146000 원재료

  생산 완료:
  pp.production_orders.status → completed
  pp.production_confirmations INSERT
  ├─ completed_qty: 148 (2세트 불량으로 148세트 완성)
  └─ man_hours_actual: 24h

STEP 6: 출고/배송
━━━━━━━━━━━━━━━
Retool [delivery] → 운송요청 생성
  tms.transportation_requirements INSERT
  ├─ tr_number: TR-2026-0412-001
  ├─ delivery_type: direct (직납)
  ├─ recipient: 프리비알 본사
  └─ requested_shipment_date: 2026-04-14

  tms.freight_orders INSERT
  ├─ fo_number: FO-2026-0413-001
  ├─ carrier: CJ대한통운
  ├─ planned_shipment_date: 2026-04-13
  ├─ freight_cost: 85,000원
  └─ shipping_status: planned → in_transit → delivered

  출고 처리:
  mm.stock_movements INSERT (이동유형 601)
  ├─ 프리비알 VIP 키트 148세트 출고
  └─ ◆ 트리거: wms.quants 차감 + 매출원가 전표

STEP 7: 회계 정산
━━━━━━━━━━━━━━━
Retool [finance] → 전표 검토
  finance.accounting_entries 전체 조회
  ├─ GR 전표: 370,000원 (입고) ← status: draft → reviewed
  ├─ 생산투입 전표: 685,000원 ← status: draft → reviewed
  ├─ 출고 전표: ... ← status: draft → reviewed
  └─ 운임 전표: 85,000원 ← status: draft → reviewed

  회계팀 더존 기표:
  ├─ 더존 아마란스10에서 각 전표 확정
  ├─ douzone_slip_no 기재 (예: "2026-04-001")
  └─ status: reviewed → posted

  기간 마감:
  finance.period_closes INSERT
  ├─ period: 2026-04
  ├─ 품목별 closing_qty, closing_value 집계
  └─ is_closed: true (이후 해당 기간 수정 불가)
```

### 프로젝트 타임라인 요약

```
날짜         이벤트              상태          자동 처리
─────────── ─────────────────── ──────────── ────────────────
04/01       프로젝트 등록        active        —
04/01       BOM 확인/발주        PO sent       —
04/05       입고 (148/150)       GR 완료       재고+148, 전표 자동
04/07~10    임가공 생산           생산 중        자재 불출, 전표 자동
04/10       생산 완료 (148세트)   completed     완성품 입고
04/13       출고/배송 시작        in_transit    재고-148, 전표 자동
04/14       배송 완료            delivered     운임 전표 자동
04/15       첫출고일 (납기)       on_time       OTIF 100%
04/30       월말 마감            posted        더존 전표 확정
```

---

## 아티팩트 생성 요청

위 4개 섹션을 각각 인터랙티브 HTML로 만들어주세요:

1. **As-Is / To-Be 비교** — 좌우 분할 또는 탭 전환, 붕어빵 비유는 일러스트 스타일
2. **마이그레이션 맵** — 인터랙티브 Sankey/트리맵 또는 테이블+매핑 화살표
3. **스키마 탐색기** — 6스키마 아코디언/탭 + 테이블 클릭 시 컬럼 상세 펼침
4. **E2E 워크플로우** — 타임라인/스텝퍼 UI, 각 단계 클릭 시 SQL/트리거 상세 표시

디자인: 깔끔한 비즈니스 프레젠테이션 스타일, 한국어, 다크/라이트 모드 토글
