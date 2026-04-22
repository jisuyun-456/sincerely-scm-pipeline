# SCM AutoResearch 운영 구조 개요

> 작성일: 2026-04-22 | 대상: TMS / WMS 자동화 파이프라인

---

## 1. 백필(Backfill) 구조

### TMS 백필

| 구분 | 내용 |
|------|------|
| 방식 | `tms_weekly_runner.py` 내부 Step 1로 포함 (별도 스크립트 없음) |
| 실행 주기 | 매주 월요일 09:00 KST (GitHub Actions 자동) |
| 백필 대상 | 직전 7일 Shipment 레코드의 **약속납기일(promised_date)** 자동 계산·삽입 |
| 데이터 소스 | TBL_SHIPMENT (Airtable TMS 베이스 `app4x70a8mOrIKsMf`) |
| 특이사항 | 17개 TMS 테이블은 이전에 1회성으로 796건 백필 완료. 이후 러너가 live 데이터 직접 읽음 |

### WMS 백필

| 구분 | 내용 |
|------|------|
| 방식 | `wms_sap_weekly.py` (별도 스크립트, runner 실행 전 Step으로 구성) |
| 실행 주기 | 매주 월요일 11:00 KST (GitHub Actions 자동, TMS 완료 2시간 후) |
| 백필 대상 | 직전 월요일 이후 신규 데이터를 SAP EWM 테이블에 증분 추가 |
| 멱등성 | `order_ref` / `movement_ref` / `pkg_schedule_ref` 기준 중복 SKIP |

WMS 백필 세부 내용:

| 소스 테이블 | 대상 SAP 테이블 | 처리 내용 |
|------------|--------------|----------|
| `order` (입하확정일 ≥ 기준일) | `WMS_GoodsReceipt` | 신규 입고 문서 생성, Dock-to-Stock 계산 |
| `movement` (생성일자 ≥ 기준일) | `WMS_InventoryTransaction` | SAP 이동유형 코드 변환 후 삽입 (101/261/531/601/311/701/702/122) |
| `pkg_schedule` (계획일 ≥ 기준일) | `WMS_Wave` + `WMS_PickingTask` | Wave 및 피킹 태스크 신규 생성 |
| (전체 TXN 누적 합산) | `WMS_InventoryLedger` | 품목×로케이션×스탁타입별 현재고 전체 재집계 |

---

## 2. AutoResearch Iteration 구성

### TMS — 5개 Iteration

**실행**: `tms_weekly_runner.py` | 매주 월요일 09:00 KST | 리포트 위치: `_AutoResearch/SCM/outputs/`

| Iter | 분석 제목 | 내용 | 주요 지표 |
|------|----------|------|----------|
| **1** | 배송 볼륨 패턴 | 배송방식(퀵/화물/직납 등)별 주간 건수, WoW 증감 | 이번 주 총 건수, 전주 대비 증감 |
| **2** | 배송 효율 (내부 소화율) | 퀵 수도권 Shipment 중 내부 기사 처리 비율, 기사별 운행일 | 내부 소화율 %, 기사별 운행일 수 |
| **3** | 운송비 분포 | 배송방식별 분포 기반 운송비 추정 | 방식별 비중, 추정 총액 |
| **4** | OTIF 실측 + 클레임 분석 | On-Time In-Full 달성률, 배송클레임 건수·유형 | OTIF %, 클레임 건수 |
| **5** | 다음 주 볼륨 예측 | 요일 패턴 기반 다음 주 배송 건수 예측, 추가 배차 필요일 권고 | 예측 건수, 임계치 초과 요일 |

---

### WMS — 7개 Iteration

**실행**: `wms_weekly_runner.py` | 매주 월요일 11:00 KST (백필 완료 후) | 리포트 위치: `_AutoResearch/WMS/outputs/`

#### AS-IS (기존 운영 테이블 직접 분석)

| Iter | 분석 제목 | 내용 | 데이터 소스 |
|------|----------|------|-----------|
| **1** | QC 불량 proxy | 생산산출·재고생산 이동 중 이슈카테고리 발생 비율, 품질·수량·운영 이슈 구분 | `movement.이슈카테고리` |
| **2** | 입출고 볼륨 트렌드 | 이동목적별 주간 건수 집계, 최근 4주 트렌드, WoW 증감 | `movement.이동목적 × 생성일자` |
| **3** | 공급사 납기 proxy | 미입하 발생이력 체크 건수, 입하예상일 vs 실제입하일 평균 지연일, 지연 공급사 Top 3 | `movement.미입하 발생이력` |

#### SAP EWM (신규 SAP 테이블 기반 정밀 분석)

| Iter | 분석 제목 | 내용 | 데이터 소스 | 목표 |
|------|----------|------|-----------|------|
| **4** | Dock-to-Stock KPI | 입하 접수(received_at) → 입고 확정(confirmed_at) 평균 소요 시간, 목표 달성률 | `WMS_GoodsReceipt` | ≤480분, 달성률 ≥90% |
| **5** | 피킹 정확도 | is_accurate 비율, SHORT(수량 부족) 발생 건수·비율 | `WMS_Wave` + `WMS_PickingTask` | 정확도 ≥99% |
| **6** | QC 불량코드 Pareto | PASS/FAIL/PARTIAL 비율, 불량코드(QC-001~009) Top 5 Pareto | `WMS_GoodsReceipt.defect_code` | 불량률 <5% |
| **7** | 공급사 정시납품률 | promised_date vs received_at 비교, 공급사별 On-Time %, Top 5 랭킹 | `WMS_GoodsReceipt` | 전체 ≥95% |

---

## 3. WMS 신규 생성 SAP EWM 테이블 (7개)

> Airtable WMS 베이스(`appLui4ZR5HWcQRri`) 내 신규 추가. 기존 17개 운영 테이블은 변경 없음.

### WMS_Location — SAP Storage Bin
창고 내 실제 물리 공간을 빈(Bin) 단위로 관리. 재고 원장과 피킹 태스크의 위치 기준점.

| 필드 | 설명 |
|------|------|
| `location_id` | `BW01-ST-A03-R01-L1-B01` 형태 고유 ID |
| `zone_type` | INBOUND_STAGING → QC_HOLD → STORAGE → OUTBOUND_STAGING |
| `warehouse` | 베스트원(27개) / 에이원센터(3개) |
| `capacity` | 최대 수용 수량 |

**현재 데이터**: 30건 (베스트원 27 + 에이원센터 3)

---

### WMS_SupplierSLA — SAP Vendor SLA
공급사별 납기 표준을 등급으로 정의. Iter 7 공급사 정시납품률의 기준값.

| 필드 | 설명 |
|------|------|
| `sla_grade` | A(3일) / B(7일) / C(14일) / D(21일) |
| `standard_days` | 표준 납기 일수 |
| `urgent_days` | 긴급 납기 일수 |
| `on_time_rate_pct` | 최근 실측 납기 준수율 % |

**현재 데이터**: 20건 (에벤에셀기업, 신명인쇄 등 실제 협력사)

---

### WMS_GoodsReceipt — SAP Inbound Delivery
입고 문서. 1건 = 납품 1회. Dock-to-Stock·QC·공급사 납기 분석의 핵심 소스.

| 필드 | 설명 |
|------|------|
| `gr_number` | `GR-20260115-001` 형태 |
| `status` | PENDING / RECEIVED / CONFIRMED / QC_FAIL |
| `received_at` | 입하 접수 시각 ← Dock-to-Stock **시작** |
| `confirmed_at` | 입고 확정 시각 ← Dock-to-Stock **종료** |
| `dock_to_stock_min` | 두 시각의 차이(분) |
| `qc_result` | PASS / FAIL / PARTIAL |
| `defect_code` | QC-001 외관불량 / QC-002 수량미달 / QC-004 파손 등 |

**현재 데이터**: 50건 (90일치, QC_FAIL 3건 포함)

---

### WMS_InventoryTransaction — SAP Material Document
재고 이동 불변 원장 (INSERT ONLY). 재고가 움직일 때마다 1행씩 기록. 삭제·수정 금지.

| SAP 이동유형 | 의미 | 수량 방향 |
|------------|------|---------|
| 101 | 구매 입고 | + (양수) |
| 531 | 생산 산출 입고 | + |
| 311 | 창고 간 이동 | + |
| 261 | 생산 투입 출고 | - (음수) |
| 601 | 고객 납품 | - |
| 701 | 재고 조정 | - |
| 702 | 폐기 | - |
| 122 | 반품 | + |

**현재 데이터**: 30건 (초기 MCP 삽입) → 매주 `wms_sap_weekly.py`로 증분 추가

---

### WMS_InventoryLedger — SAP IM Ledger
품목 × 로케이션 × 스탁타입별 현재고 스냅샷. Transaction 전체를 누적 합산해 매주 재계산.

| 필드 | 설명 |
|------|------|
| `stock_type` | UNRESTRICTED(출고 가능) / QUALITY_INSPECTION(검수 중) / BLOCKED(출고 불가) |
| `qty_on_hand` | 현재고 |
| `qty_reserved` | 예약 수량 |
| `qty_available` | 가용 재고 (on_hand - reserved) |

**현재 데이터**: 15건 → 매주 전체 재집계 (DELETE all + re-INSERT)

---

### WMS_Wave — SAP Warehouse Order
피킹 작업 묶음. 1 Wave = 여러 PickingTask의 집합. Iter 5 피킹 정확도의 집계 단위.

| 필드 | 설명 |
|------|------|
| `wave_id` | `WAVE-20260301-001` 형태 |
| `status` | PLANNED / RELEASED / IN_PROGRESS / COMPLETED |
| `total_lines` | 피킹 계획 라인 수 |
| `picked_lines` | 실제 완료 라인 수 |
| `picking_accuracy_pct` | 완료율 % |

**현재 데이터**: 10건 (COMPLETED 9건, PLANNED 1건)

---

### WMS_PickingTask — SAP Warehouse Task
Wave 내 개별 피킹 작업. 1건 = 품목 1개 × 수량. SHORT는 계획 수량 미달 케이스.

| 필드 | 설명 |
|------|------|
| `task_id` | `TASK-20260301-001-01` 형태 |
| `wave_id` | 상위 Wave 연결 |
| `planned_qty` | 계획 수량 |
| `picked_qty` | 실제 피킹 수량 |
| `status` | COMPLETED / SHORT / PENDING |
| `lot_selection` | FIFO / FEFO / MANUAL (피킹 전략) |
| `is_accurate` | planned_qty == picked_qty 여부 |

**현재 데이터**: 18건 (SHORT 3건, FIFO 피킹 위주)

---

## 4. 실행 타임라인 요약

```
매주 월요일

09:00 KST  ─── TMS 워크플로우 시작 ───────────────────────────
           Step 1: 약속납기일 백필 (지난 7일 Shipment)
           Step 2: tms_weekly_runner.py (Iter 1~5 분석)
           Step 3: _AutoResearch/SCM/outputs/ 저장 + git push

11:00 KST  ─── WMS 워크플로우 시작 ───────────────────────────
           Step 1: wms_sap_weekly.py (SAP 테이블 증분 백필)
                   └─ GoodsReceipt 신규 추가
                   └─ InventoryTransaction 신규 추가
                   └─ Wave / PickingTask 신규 추가
                   └─ InventoryLedger 전체 재집계
           Step 2: wms_weekly_runner.py (Iter 1~7 분석)
           Step 3: _AutoResearch/WMS/outputs/ 저장 + git push
```

---

*생성: Claude Sonnet 4.6 | SCM_WORK 프로젝트*
