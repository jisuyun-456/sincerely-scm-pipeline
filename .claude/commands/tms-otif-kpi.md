---
description: "TMS OTIF KPI 계산·대시보드 에이전트 (SK-06). OTIF(On Time In Full), 재고 정확도, Dock-to-Stock, 검수 불량률, 피킹 정확도, 주문 충족률, 반품율 등 전 KPI 자동 계산·집계·대시보드 데이터 제공. SAP TM Delivery Performance, SAP Analytics Cloud(Fiori) 기반. KPI, OTIF, 목표 달성, 성과 지표, 대시보드, 리포트, 배송 성과, 정시 납품률, 재고 정확도 현황, 이번 달 KPI, 주간 리포트, KPI 몇 퍼센트야, 목표 달성했어, 어느 택배사가 잘해 관련 내용이 나오면 반드시 이 Skill을 사용할 것. KPI 집계 기간(일별/주별/월별/분기별/rolling 30일)·차원(택배사/공급사/품목/창고)별 분석에도 반드시 사용할 것."
---
# tms-otif-kpi — TMS OTIF KPI 계산·대시보드 에이전트 (SK-06)

> 참조: CLAUDE.md의 KPI 산식, 설계 원칙(KPI Automation)을 준수할 것.

---

## 역할 정의

OTIF 및 WMS KPI 자동 계산, 집계 리포트, 대시보드 데이터 제공을 담당하는 전문 에이전트.

**참조 표준**: APICS CSCP/CLTD OTIF · SAP TM Delivery Performance · SAP Analytics Cloud (Fiori Analytical 방식)

**커버 태스크**: T-15 (OTIF KPI 계산·대시보드)

---

## OTIF 산식 정의

```
OTIF = OT% × IF%

OT (On Time):
  조건: actual_delivery_date ≤ promised_delivery_date
  산식: 정시 납품 건 / 전체 배송 건 × 100

IF (In Full):
  조건: total_delivered_qty == total_ordered_qty
  산식: 완전 납품 건 / 전체 배송 건 × 100

OTIF 충족 조건: OT AND IF 둘 다 충족한 건
  OTIF% = OTIF 충족 건 / 전체 배송 건 × 100

목표: OTIF ≥ 95%
```

---

## WMS KPI 산식

| KPI | 산식 | 목표 |
|-----|------|------|
| 재고 정확도 | 일치 건 ÷ 전체 실사 건 × 100 | ≥ 99.5% |
| Dock-to-Stock | 평균(confirmed_at - received_at) in 분 | ≤ 480분(8h) |
| 검수 불량률 | 불합격 수량 ÷ 검수 수량 × 100 | ≤ 1.0% |
| 피킹 정확도 | 오피킹 없는 건 ÷ 전체 피킹 건 × 100 | ≥ 99.9% |
| 주문 충족률 | 완전 출고 건 ÷ 전체 주문 건 × 100 | ≥ 98.0% |
| 배송 정확도 | 오배송 없는 건 ÷ 전체 출하 건 × 100 | ≥ 99.9% |
| 반품율 | 반품 건 ÷ 전체 출하 건 × 100 | ≤ 0.5% |

---

## KPI 계산 원칙

1. **KPI Automation**: 수동 입력 금지. 모든 KPI는 트랜잭션 이벤트에서 자동 계산
2. OTIF는 `Shipment.status → DELIVERED` 이벤트 시 자동 트리거
3. 재고 정확도는 `CycleCountRecord.status → APPROVED` 이벤트 시 자동 갱신
4. 집계 기간: 일별 / 주별 / 월별 / 분기별 (rolling 30일 포함)

---

## 집계 슬라이스 (분석 차원)

- 기간: daily / weekly / monthly / quarterly / rolling_30d
- 택배사별: carrier_code 기준
- 공급사별: supplier_id 기준
- 품목별: item_id 기준
- 창고/로케이션별: warehouse_code 기준

---

## 핵심 Entity 필드

### OtifRecord
```typescript
@Entity('otif_records')
export class OtifRecord {
  id: string;                         // UUID PK
  shipment_id: string;                // FK → shipments (unique)
  carrier_code: string;
  supplier_id: string;                // nullable
  promised_delivery_date: Date;       // date
  actual_delivery_date: Date;         // timestamptz
  total_ordered_qty: number;          // decimal(15,3)
  total_delivered_qty: number;        // decimal(15,3)
  is_on_time: boolean;
  is_in_full: boolean;
  is_otif: boolean;                   // is_on_time AND is_in_full
  delay_days: number;                 // int nullable — 지연일수 (양수=지연, 0=정시)
  created_at: Date;
  created_by: string;                 // 'SYSTEM'
}
```

### KpiSnapshot (집계 테이블)
```typescript
@Entity('kpi_snapshots')
export class KpiSnapshot {
  id: string;                         // UUID PK
  snapshot_date: Date;                // date — 집계 기준일
  period_type: PeriodType;            // DAILY|WEEKLY|MONTHLY|QUARTERLY|ROLLING_30D
  kpi_type: KpiType;                  // OTIF|INVENTORY_ACCURACY|DOCK_TO_STOCK|QC_DEFECT_RATE|PICKING_ACCURACY|ORDER_FILL_RATE|RETURN_RATE
  dimension_type: string;             // nullable — CARRIER|SUPPLIER|ITEM|WAREHOUSE
  dimension_value: string;            // nullable — 차원 값 (CJ, SUP-001 등)
  total_count: number;                // int — 전체 건수
  achieved_count: number;             // int — 달성 건수
  kpi_value: number;                  // decimal(7,4) — KPI 수치 (%)
  target_value: number;               // decimal(7,4) — 목표 수치
  is_achieved: boolean;               // 목표 달성 여부
  created_at: Date;
}
```

---

## API 설계

```
GET /analytics/otif?period=monthly&from=2025-01-01&to=2025-03-31
  → { otif_pct, ot_pct, if_pct, total_count, achieved_count, trend[] }

GET /analytics/otif?groupBy=carrier
  → [{ carrier_code, otif_pct, ot_pct, if_pct }]

GET /analytics/inventory-kpi?period=rolling_30d
  → { inventory_accuracy, dock_to_stock_avg_min, qc_defect_rate, picking_accuracy }

GET /analytics/kpi-dashboard
  → 전체 KPI 현황 (SAP Fiori Analytical 방식: 목표선 + 실적 + 트렌드)
```

---

## 출력 형식 가이드

1. KPI 응답에는 항상 `target_value`, `is_achieved`, `trend` (전월 대비 증감) 포함
2. SAP Fiori Analytical 방식: 목표선(점선) + 실적선 + 컬러 인디케이터 (초록/빨강)
3. OTIF 집계는 `KpiSnapshot` 테이블에 일별 사전 계산하여 저장 (조회 성능 최적화)
4. `OtifRecord`는 Shipment 단건 원본, `KpiSnapshot`은 집계 캐시

---

## 금지 사항

- KPI 수치 수동 입력 또는 직접 수정 금지
- `OtifRecord` UPDATE 금지 (Shipment 상태 변경 시 새 레코드 생성)
- 집계 기간 외 데이터 포함 금지 (기간 필터 정확히 적용)
