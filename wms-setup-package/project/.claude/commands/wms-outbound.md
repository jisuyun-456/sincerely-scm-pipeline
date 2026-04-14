---
description: "WMS 아웃바운드(출고·피킹·패킹) 관리 에이전트 (SK-04). Wave 생성, PickingTask 관리, PackingRecord, SSCC GS1 라벨 생성 담당. APICS CLTD Wave Management, SAP EWM Warehouse Order/Task, GS1 SSCC(AI 00) 기반. 출고, 피킹, 패킹, Wave, 피킹 태스크, SSCC, 박스 라벨, 출고 지시, FIFO, FEFO, 피킹 정확도, 재고 예약, Goods Issue 관련 내용이 나오면 반드시 이 Skill을 사용할 것. 주문 출고 처리, 피킹 작업 생성, 패킹 완료 처리 맥락에서도 반드시 사용할 것."
---
# wms-outbound — WMS 아웃바운드 관리 에이전트 (SK-04)

> 참조: CLAUDE.md의 Movement Type, Stock Type, 설계 원칙을 모두 준수할 것.

---

## 역할 정의

Wave 생성, 피킹 태스크 관리, 패킹 기록, SSCC GS1 라벨 생성을 담당하는 전문 에이전트.

**참조 표준**: APICS CLTD (Pick/Pack · Wave Management) · SAP EWM Wave / Warehouse Order / WT · GS1 SSCC (Application Identifier 00)

**커버 태스크**: T-10 (Wave 생성·출고 지시) · T-11 (피킹 태스크 생성·관리) · T-12 (패킹 기록·SSCC 라벨)

---

## 아웃바운드 표준 흐름 (SAP EWM 기준)

```
출고 지시 수신 (OutboundOrder)
    ↓
Wave 생성 (복수 주문 묶음, Wave.status: PLANNED)
    ↓
PickingTask 생성 per 출고 라인
  → FIFO/FEFO LOT 자동 선택
  → InventoryLedger.quantity_reserved += 피킹 수량
  → Stock Type 변경: UNRESTRICTED 중 예약분 RESERVED 표시
    ↓
피킹 실행 (작업자 스캔 확인)
  → PickingTask.status: IN_PROGRESS → COMPLETED
    ↓
PackingRecord 생성 (박스 규격 선택)
  → SSCC 번호 자동 생성 (GS1 Mod-10)
    ↓
Goods Issue 처리
  → InventoryTransaction(tx_type: SHIP, movement: 601) INSERT
  → InventoryLedger.quantity_on_hand -= 출고 수량
  → InventoryLedger.quantity_reserved -= 예약 수량
    ↓
TMS Shipment 연동 (shipment_id 생성)
```

---

## 핵심 도메인 규칙

### Wave 관리
- Wave는 당일 출고 예정 주문들을 묶는 배치 단위
- `wave_number` 형식: `WAVE-YYYYMMDD-NNN`
- 단건 직접 피킹 **금지** — 반드시 Wave → PickingTask 경로
- Wave 취소 시: 모든 PickingTask → CANCELLED, `quantity_reserved` 환원

### FIFO / FEFO LOT 자동 선택
```
is_fefo = false: lot.fifo_date ASC (오름차순) 자동 선택
is_fefo = true:  lot.expiry_date ASC → fifo_date ASC (동일 만료일 시)

수동 LOT 오버라이드 시:
  → PickingTask.manual_lot_override = true
  → reason 필드에 오버라이드 사유 기록 필수
```

### 재고 예약 처리
- PickingTask 생성 즉시: `InventoryLedger.quantity_reserved += quantity`
- PickingTask COMPLETED: 예약 차감 + `quantity_on_hand` 감소 (Goods Issue 시)
- PickingTask CANCELLED: `quantity_reserved -= quantity` 환원

### SSCC 생성 (GS1 Mod-10)
```
형식: (00) + 18자리 숫자
= Extension Digit(1) + Company Prefix(8) + Serial Reference(9) + Check Digit(1)

Check Digit 계산:
  1. 오른쪽에서 홀수 위치 숫자 × 3 합산
  2. 오른쪽에서 짝수 위치 숫자 합산
  3. (1 + 2) 합계 올림하여 10의 배수 → Check Digit
```

---

## 핵심 Entity 필드

### Wave
```typescript
@Entity('waves')
export class Wave {
  id: string;
  wave_number: string;                // unique — WAVE-YYYYMMDD-NNN
  status: WaveStatus;                 // PLANNED|IN_PROGRESS|COMPLETED|CANCELLED
  planned_date: Date;                 // date — 출고 예정일
  total_order_count: number;          // int
  total_task_count: number;           // int
  completed_task_count: number;       // int
  started_at: Date;                   // nullable timestamptz
  completed_at: Date;                 // nullable timestamptz
  created_at: Date;
  created_by: string;
}
```

### PickingTask
```typescript
@Entity('picking_tasks')
export class PickingTask {
  id: string;
  wave_id: string;                    // FK → waves
  outbound_order_id: string;          // FK → outbound_orders
  item_id: string;
  lot_id: string;                     // nullable — FIFO/FEFO 선택 LOT
  from_location_id: string;           // STORAGE 로케이션
  to_location_id: string;             // OUTBOUND_STAGING
  quantity: number;                   // decimal(15,3)
  picked_qty: number;                 // decimal(15,3) default 0
  status: PickingStatus;              // PENDING|IN_PROGRESS|COMPLETED|SHORT|CANCELLED
  assigned_to: string;                // nullable — 담당 작업자
  manual_lot_override: boolean;       // default false
  reason: string;                     // nullable — 오버라이드 사유
  started_at: Date;                   // nullable
  completed_at: Date;                 // nullable
  created_at: Date;
  created_by: string;
}
```

### PackingRecord
```typescript
@Entity('packing_records')
export class PackingRecord {
  id: string;
  wave_id: string;                    // FK → waves
  picking_task_ids: string[];         // 포함된 PickingTask ID 목록 (jsonb array)
  box_type: string;                   // 박스 규격 코드
  sscc: string;                       // GS1 SSCC 18자리
  total_weight_kg: number;            // decimal(10,2)
  status: PackingStatus;              // PENDING|COMPLETED
  packed_by: string;
  packed_at: Date;                    // timestamptz
  created_at: Date;
  created_by: string;
}
```

---

## 상태 머신

```
Wave:
PLANNED → IN_PROGRESS → COMPLETED
        → CANCELLED

PickingTask:
PENDING → IN_PROGRESS → COMPLETED
                      → SHORT      (부족 피킹)
        → CANCELLED
```

---

## 출력 형식 가이드

1. Wave 생성 API: `POST /wms/outbound/wave` — outbound_order_ids[] 입력 → Wave + PickingTask[] 자동 생성
2. 피킹 완료 API: `PATCH /wms/outbound/picking/:id/complete` → Goods Issue tx 자동 생성
3. SSCC 생성: `PackingService.generateSscc()` 메서드로 GS1 Mod-10 알고리즘 구현
4. Goods Issue 처리는 반드시 DB 트랜잭션 내에서 atomic 처리

---

## 금지 사항

- Wave 없이 직접 PickingTask 생성 금지
- FIFO/FEFO 순서 무시하고 임의 LOT 선택 금지 (manual_lot_override + reason 기록 시 예외)
- `quantity_reserved` 미설정 상태에서 피킹 시작 금지
- SSCC GS1 Mod-10 Check Digit 검증 없이 SSCC 발행 금지
