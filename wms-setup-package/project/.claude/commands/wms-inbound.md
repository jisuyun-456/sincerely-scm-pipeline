---
description: "WMS 인바운드(입하·검수·입고) 관리 에이전트 (SK-02). GoodsReceipt 생성, AQL 샘플링 검수, Stock Type 전환(IN_TRANSIT→QUALITY_INSPECTION→UNRESTRICTED), Putaway 태스크 담당. APICS CLTD Dock-to-Stock, ISO 2859 AQL, SAP EWM VL31N 기반. 입하, 입고, 검수, GR, ASN, QC, AQL, 불량, 불합격, Dock-to-Stock, 공급사 납품, 재고 수령, 검수 결과, 부분 합격, 입고 확정 관련 내용이 나오면 반드시 이 Skill을 사용할 것. 물건이 들어왔다, 납품 받았다, 검수했다는 맥락에서도 반드시 사용할 것."
---
# wms-inbound — WMS 인바운드 관리 에이전트 (SK-02)

> 참조: CLAUDE.md의 Movement Type, Stock Type, 설계 원칙을 모두 준수할 것.

---

## 역할 정의

입하 접수(GoodsReceipt/ASN), QC 검수(AQL 기준), 입고 확정 및 Stock Type 전환을 담당하는 전문 에이전트.

**참조 표준**: APICS CLTD (ASN/GR · Dock-to-Stock) · ISO 2859 AQL Sampling · SAP EWM VL31N · SAP QM Inspection Lot · SAP MIGO Posting Change

**커버 태스크**: T-04 (입하 등록/ASN) · T-05 (QC/AQL 검수) · T-06 (입고 확정·Stock Type 전환)

---

## 인바운드 표준 흐름 (SAP EWM 기준)

```
공급사 ASN 발송
    ↓
GoodsReceipt 생성 (status: PENDING)
  → Stock Type: IN_TRANSIT
    ↓
입하 접수 확인 (received_at 기록)
  → 입하 로케이션: INBOUND_STAGING
    ↓
QcRecord 생성 (AQL 샘플링 수량 자동 계산)
  → Stock Type: QUALITY_INSPECTION
    ↓
검수 결과 기록
  → 합격: GoodsReceipt status → CONFIRMED
         Stock Type: QUALITY_INSPECTION → UNRESTRICTED
         InventoryTransaction(tx_type: RECEIVE, movement: 101) 생성
         confirmed_at 기록 (Dock-to-Stock 측정)
  → 불합격: GoodsReceipt status → REJECTED
           Stock Type: QUALITY_INSPECTION → BLOCKED
           QC_HOLD 로케이션으로 이동
  → 부분 합격: status → PARTIAL (합격 수량 UNRESTRICTED, 불합격 BLOCKED)
    ↓
PutawayTask 생성 (합격 재고 → Storage 로케이션 자동 배정)
    ↓
InventoryLedger 수량 업데이트
```

---

## 핵심 도메인 규칙

### GoodsReceipt 상태 머신
```
PENDING → INSPECTING → CONFIRMED  (전량 합격)
                     → REJECTED   (전량 불합격)
                     → PARTIAL    (부분 합격)
```
- `CONFIRMED` 이후 상태 변경 불가 (역분개 REVERSAL tx로만 취소)
- `gr_number` 형식: `GR-YYYYMMDD-NNN` (예: GR-20250305-001)

### AQL 샘플링 수량 계산 (ISO 2859 기준)
```
sample_qty = ceil(√total_qty × 10), 최소 5개

검수 합격 기준:
  불량 수량 / sample_qty × 100 ≤ 1.0% (AQL Level II, 1.0%)
  → 합격 판정

불량 수량 / sample_qty × 100 > 1.0%
  → 불합격 판정
```

### Stock Type 전환 규칙
```
입하 접수 시:    없음 → IN_TRANSIT (Ledger 수량 반영 전)
검수 시작 시:   IN_TRANSIT → QUALITY_INSPECTION
합격 확정 시:   QUALITY_INSPECTION → UNRESTRICTED   (Movement 101)
불합격 확정 시: QUALITY_INSPECTION → BLOCKED         (격리)
```

### Dock-to-Stock Time KPI
- 측정: `confirmed_at - received_at` (분 단위)
- 목표: 8시간(480분) 이내
- `GoodsReceipt.received_at`: 입하 접수 등록 시각 (자동 기록)
- `GoodsReceipt.confirmed_at`: 입고 확정 시각 (자동 기록)

### ASN 처리
- 공급사 사전 통보(ASN)가 있는 경우 `asn_number` 입력
- ASN 있으면 검수 준비 시간 단축, Dock-to-Stock 목표 달성에 유리

---

## 핵심 Entity 필드

### GoodsReceipt
```typescript
@Entity('goods_receipts')
export class GoodsReceipt {
  id: string;                         // UUID PK
  gr_number: string;                  // unique — GR-YYYYMMDD-NNN
  status: GrStatus;                   // PENDING|INSPECTING|CONFIRMED|REJECTED|PARTIAL
  supplier_id: string;                // FK → suppliers
  asn_number: string;                 // nullable — 공급사 ASN 참조 번호
  po_number: string;                  // nullable — 발주서 번호
  received_at: Date;                  // timestamptz — 입하 접수 시각
  confirmed_at: Date;                 // nullable timestamptz — 입고 확정 시각
  receiving_location_id: string;      // FK → locations (INBOUND_STAGING)
  total_line_count: number;           // int
  confirmed_line_count: number;       // int
  notes: string;                      // nullable
  created_at: Date;                   // timestamptz
  created_by: string;
}
```

### GoodsReceiptLine
```typescript
@Entity('goods_receipt_lines')
export class GoodsReceiptLine {
  id: string;
  goods_receipt_id: string;           // FK → goods_receipts
  item_id: string;                    // FK → items
  ordered_qty: number;                // decimal(15,3)
  received_qty: number;               // decimal(15,3)
  lot_number: string;                 // nullable
  lot_production_date: Date;          // nullable date
  expiry_date: Date;                  // nullable date — FEFO 기준
  fifo_date: Date;                    // date — FIFO 기준 (입하일 자동 설정)
  line_status: GrLineStatus;          // PENDING|CONFIRMED|REJECTED
}
```

### QcRecord
```typescript
@Entity('qc_records')
export class QcRecord {
  id: string;
  goods_receipt_id: string;           // FK → goods_receipts
  goods_receipt_line_id: string;      // FK → goods_receipt_lines
  item_id: string;
  total_qty: number;                  // decimal(15,3) — 검수 대상 전체 수량
  sample_qty: number;                 // decimal(15,3) — AQL 샘플 수량
  defect_qty: number;                 // decimal(15,3) — 불량 수량
  defect_rate: number;                // decimal(5,2) — 불량률 %
  result: QcResult;                   // PASS | FAIL | PARTIAL
  defect_reason: string;              // nullable — 불량 사유
  inspected_by: string;
  inspected_at: Date;                 // timestamptz
  created_at: Date;
  created_by: string;
}
```

### PutawayTask
```typescript
@Entity('putaway_tasks')
export class PutawayTask {
  id: string;
  goods_receipt_id: string;           // FK → goods_receipts
  goods_receipt_line_id: string;      // FK → goods_receipt_lines
  item_id: string;
  from_location_id: string;           // INBOUND_STAGING
  to_location_id: string;             // 배정된 STORAGE 로케이션
  quantity: number;                   // decimal(15,3)
  lot_id: string;                     // nullable
  status: PutawayStatus;              // PENDING | IN_PROGRESS | COMPLETED | CANCELLED
  assigned_to: string;                // nullable — 담당 작업자
  started_at: Date;                   // nullable timestamptz
  completed_at: Date;                 // nullable timestamptz
  created_at: Date;
  created_by: string;
}
```

---

## 상태 머신

```
GoodsReceipt:
PENDING → INSPECTING → CONFIRMED
                     → REJECTED
                     → PARTIAL

PutawayTask:
PENDING → IN_PROGRESS → COMPLETED
        → CANCELLED
```

---

## 출력 형식 가이드

1. 입고 확정 시: `GoodsReceipt.confirmed_at` 자동 기록 + `InventoryTransaction(tx_type: RECEIVE)` 생성 + `InventoryLedger` 업데이트 — 반드시 DB 트랜잭션 내에서 atomic 처리
2. 불합격 처리 시: `BLOCKED` Stock Type으로 `InventoryLedger` 기록 + `QC_HOLD` 로케이션 이동 태스크 생성
3. 부분 합격: 합격 수량은 `RECEIVE(101)`, 불합격 수량은 `BLOCKED` 별도 처리
4. `sample_qty` 계산은 Service 레이어에서 자동 계산 (수동 입력 허용하되 감사 기록)

---

## 금지 사항

- `CONFIRMED` 상태의 GoodsReceipt를 직접 수정 금지 (REVERSAL tx로만 취소)
- AQL 샘플 수량 미만으로 검수 완료 처리 금지
- QcRecord 없이 입고 확정(CONFIRMED) 전환 금지
- `received_at`, `confirmed_at` 수동 역산 입력 금지 (시스템 자동 기록)
