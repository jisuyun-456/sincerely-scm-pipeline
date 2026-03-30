---
description: "WMS 반품·역물류 관리 에이전트 (SK-07). 반품 접수(ReturnRequest), 역물류 처리, 재입고(RESTOCK)/폐기(DISPOSE)/재가공(REPROCESS) 분류, 공급사 반품(RETURN_TO_SUPPLIER), 반품율 KPI 담당. APICS CLTD Reverse Logistics, SAP EWM Returns Management, SCOR Return 기반. 반품, 교환, 역물류, 반송, 고객 반품, 오배송 처리, 불량 반품, 배송 중 파손, 변심 반품, 재입고, 폐기, 재가공, RESTOCK, DISPOSE, RTN 번호, 반품율 관련 내용이 나오면 반드시 이 Skill을 사용할 것. 공급사에 불량품 돌려보내는 경우에도 반드시 사용할 것."
---
# wms-return — WMS 반품·역물류 관리 에이전트 (SK-07)

> 참조: CLAUDE.md의 Movement Type, Stock Type, 설계 원칙을 준수할 것.

---

## 역할 정의

반품 접수, 역물류 처리, 재입고/폐기/재가공 분류를 담당하는 전문 에이전트.

**참조 표준**: APICS CLTD Reverse Logistics · SAP EWM Returns Management · SCOR Return 프로세스

**커버 태스크**: T-16 (반품 접수·역물류 처리)

---

## 반품 처리 흐름 (SAP EWM Returns Management 기준)

```
반품 요청 접수 (ReturnRequest 생성)
  → 연관 Shipment 확인 (tracking_number 기준)
  → return_reason 분류
    ↓
반품 수령 확인 (received_at 기록)
  → QC_HOLD 구역 입고 (Stock Type: BLOCKED)
  → InventoryLedger 반영 (quantity_blocked 증가)
    ↓
검수 (재입고 가능 여부 판단)
    ↓
처리 결정:
  RESTOCK (재입고 가능)
    → Stock Type: BLOCKED → UNRESTRICTED
    → InventoryTransaction(tx_type: ADJUST_PLUS, movement: 701) 생성
    → 정상 STORAGE 로케이션으로 이동

  DISPOSE (폐기)
    → InventoryTransaction(tx_type: ADJUST_MINUS, movement: 702) 생성
    → quantity_blocked 차감
    → 폐기 이력 기록

  REPROCESS (재가공)
    → ASSEMBLY 구역으로 이동 (재작업)
    → 재작업 완료 후 RESTOCK 처리
    ↓
반품율 KPI 갱신
  반품율 = 반품 건 ÷ 전체 출하 건 × 100 (목표: ≤ 0.5%)
```

---

## 핵심 도메인 규칙

### 반품 사유 (return_reason) 4종
| return_reason | 의미 |
|---|---|
| `CUSTOMER_CHANGE_MIND` | 단순 변심 |
| `DEFECTIVE_PRODUCT` | 제품 불량 |
| `WRONG_DELIVERY` | 오배송 |
| `DAMAGE_IN_TRANSIT` | 배송 중 파손 |

### 처리 결과 (resolution) 3종
| resolution | 처리 | InventoryTransaction |
|---|---|---|
| `RESTOCK` | 재입고 (UNRESTRICTED) | ADJUST_PLUS (701) |
| `DISPOSE` | 폐기 | ADJUST_MINUS (702) |
| `REPROCESS` | 재가공 후 재입고 | TRANSFER (311) → 추후 ADJUST_PLUS |

### Stock Type 전환
```
반품 수령 시:  없음 → BLOCKED (QC_HOLD 구역 입고)
RESTOCK 시:   BLOCKED → UNRESTRICTED
DISPOSE 시:   BLOCKED → (삭제) qty_blocked -= disposal_qty
REPROCESS 시: BLOCKED → BLOCKED (ASSEMBLY 구역 이동, tx_type: TRANSFER)
```

### 반품율 KPI
```
반품율 = 반품 접수 건 ÷ 전체 출하 건 × 100
목표: ≤ 0.5%

RETURN_TO_SUPPLIER(122) 케이스:
  → 공급사 불량품 반송 시 사용
  → Supplier.defect_rate 자동 갱신
```

### 공급사 반품 (RETURN_TO_SUPPLIER) 플로우

고객 반품(Customer Return)과 구분 필요. BLOCKED 재고 중 공급사 귀책이 확인된 경우:

```
BLOCKED 재고 (QC_HOLD 구역)
    ↓
공급사 반품 결정 (resolution = RETURN_TO_SUPPLIER_CONFIRMED)
    ↓
InventoryTransaction(tx_type: RETURN_TO_SUPPLIER, movement: 122) INSERT
  → quantity 음수 (출고 방향)
  → reason: "공급사반품_{supplier_code}_{gr_number}"
    ↓
InventoryLedger.quantity_blocked -= 반품 수량
    ↓
Supplier.defect_rate 자동 갱신 (Event Emitter → master 모듈)
```

| 구분 | tx_type | Movement | 대상 |
|------|---------|----------|------|
| 고객 반품 재입고 | ADJUST_PLUS | 701 | 고객이 보낸 반품 → 재고 복구 |
| 고객 반품 폐기 | ADJUST_MINUS | 702 | 고객이 보낸 반품 → 폐기 처리 |
| 공급사 반품 | RETURN_TO_SUPPLIER | 122 | 불량 입고품 → 공급사 반송 |

---

## 핵심 Entity 필드

### ReturnRequest
```typescript
@Entity('return_requests')
export class ReturnRequest {
  id: string;                         // UUID PK
  return_number: string;              // unique — RTN-YYYYMMDD-NNN
  shipment_id: string;                // nullable FK → shipments
  tracking_number: string;            // nullable — 원 배송 운송장
  customer_name: string;              // nullable
  return_reason: ReturnReason;        // CUSTOMER_CHANGE_MIND|DEFECTIVE_PRODUCT|WRONG_DELIVERY|DAMAGE_IN_TRANSIT
  status: ReturnStatus;               // REQUESTED|RECEIVED|INSPECTING|RESTOCKED|DISPOSED|REPROCESSING|COMPLETED
  resolution: ReturnResolution;       // nullable — RESTOCK|DISPOSE|REPROCESS
  received_at: Date;                  // nullable timestamptz — 반품 수령 시각
  inspected_at: Date;                 // nullable timestamptz
  completed_at: Date;                 // nullable timestamptz
  receiving_location_id: string;      // nullable FK → locations (QC_HOLD)
  inspection_notes: string;           // nullable
  adjustment_tx_id: string;           // nullable — 처리 시 생성된 tx ID
  inspected_by: string;               // nullable
  created_at: Date;
  created_by: string;
}
```

### ReturnRequestLine
```typescript
@Entity('return_request_lines')
export class ReturnRequestLine {
  id: string;
  return_request_id: string;          // FK → return_requests
  item_id: string;
  lot_id: string;                     // nullable
  requested_qty: number;              // decimal(15,3)
  received_qty: number;               // decimal(15,3) default 0
  restock_qty: number;                // decimal(15,3) default 0
  dispose_qty: number;                // decimal(15,3) default 0
  reprocess_qty: number;              // decimal(15,3) default 0
  line_resolution: ReturnResolution;  // nullable
}
```

---

## 상태 머신

```
ReturnRequest:
REQUESTED → RECEIVED → INSPECTING → RESTOCKED   (전량 재입고)
                                  → DISPOSED    (전량 폐기)
                                  → REPROCESSING → COMPLETED
                                  → COMPLETED   (혼합 처리 완료)
```

---

## API 설계

```
POST /wms/return                          → ReturnRequest 생성 (REQUESTED)
PATCH /wms/return/:id/receive             → 반품 수령 확인 (RECEIVED, received_at 기록)
PATCH /wms/return/:id/inspect             → 검수 결과 입력 (INSPECTING)
PATCH /wms/return/:id/resolve             → 처리 결정 (RESTOCK|DISPOSE|REPROCESS)
GET  /wms/return?status=INSPECTING        → 검수 대기 반품 목록
GET  /wms/return/:id                      → 반품 상세 조회
```

## 에어테이블 즉시 적용 방안

```
현재 에어테이블에서 반품 처리:
1. 반품 사유(CUSTOMER_CHANGE_MIND|DEFECTIVE_PRODUCT|WRONG_DELIVERY|DAMAGE_IN_TRANSIT) 필드 추가
2. 처리 결과(RESTOCK|DISPOSE|REPROCESS) 필드 추가
3. RESTOCK 시: InventoryTransaction 테이블에 ADJUST_PLUS(701) 레코드 생성
                reason: "반품재입고_{RTN번호}_{날짜}"
4. DISPOSE 시: InventoryTransaction 테이블에 ADJUST_MINUS(702) 레코드 생성
                reason: "반품폐기_{RTN번호}_{return_reason}"
5. 공급사 반품 시: RETURN_TO_SUPPLIER(122) 레코드 생성 + 해당 공급사 불량률 갱신
```

## 출력 형식 가이드

1. 반품 수령 시: QC_HOLD 구역 `InventoryLedger.quantity_blocked` 즉시 반영
2. RESTOCK 처리: `ADJUST_PLUS(701)` tx 생성 + BLOCKED → UNRESTRICTED 전환 + Ledger 업데이트
3. DISPOSE 처리: `ADJUST_MINUS(702)` tx 생성 + `reason: "반품 폐기 - {return_reason}"` 필수
4. 처리 후: 반품율 KPI 자동 갱신 (Event Emitter → analytics 모듈)
5. 공급사 반품: `RETURN_TO_SUPPLIER(122)` tx 생성 + `Supplier.defect_rate` 갱신 이벤트 emit

---

## 금지 사항

- `return_reason` 없이 ReturnRequest 생성 금지
- 검수(`INSPECTING`) 없이 RESTOCK/DISPOSE 처리 금지
- BLOCKED 상태가 아닌 재고를 반품 재고로 처리 금지
- DISPOSE 처리 시 `reason` 없는 ADJUST_MINUS tx 생성 금지
