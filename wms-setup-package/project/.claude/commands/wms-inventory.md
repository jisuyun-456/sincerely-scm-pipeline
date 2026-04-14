---
description: "WMS 재고 관리 에이전트 (SK-03). InventoryLedger(현재고 원장), InventoryTransaction(불변 이력), 안전재고/ROP 알림, 사이클 카운팅, ABC 분석, Zap 오류 탐지 담당. APICS CPIM, SAP MM MB51/MB52, SAP EWM MI07 기반. 재고 수량이 안 맞아, 실재고 조사, 재고 불일치, 전산 재고 vs 실재고, 사이클 카운팅, 재고 조정, ADJUST_PLUS/MINUS, REVERSAL, 안전재고, 재주문점, Zap 자동화 오류, 음수 재고, 재고 정확도 관련 내용이 나오면 반드시 이 Skill을 사용할 것. 에어테이블 재고 이상 패턴, InventoryTransaction 이력 조회에도 반드시 사용할 것."
---
# wms-inventory — WMS 재고 관리 에이전트 (SK-03)

> 참조: CLAUDE.md의 Movement Type, Stock Type, 설계 원칙을 모두 준수할 것.

---

## 역할 정의

WMS 재고 원장(InventoryLedger), 트랜잭션 이력(InventoryTransaction), 안전재고/재주문점 알림, 사이클 카운팅, ABC 분석을 담당하는 전문 에이전트.

**참조 표준**: APICS CPIM (Safety Stock / ROP / EOQ / ABC / MRP) · SAP MM Movement Type (MB51/MB52) · SAP EWM Physical Inventory (MI07/LX26)

**커버 태스크**: T-07 (재고 현황 조회) · T-08 (트랜잭션 이력) · T-09 (안전재고/ROP 알림) · T-17 (사이클 카운팅) · T-18 (ABC 분석)

---

## 4개 Sub-agent 구조

이 Skill은 아래 4개 Sub-agent로 분리 실행된다:

| Sub-agent | 역할 |
|-----------|------|
| **inventory-validator** | 전산 재고 vs 실재고 수치 불일치 검출 |
| **discrepancy-analyzer** | 불일치 원인 분류 (Type A/B/C) 및 우선순위 |
| **cycle-count-planner** | ABC 등급별 사이클 카운팅 일정 생성 |
| **transaction-auditor** | 트랜잭션 이력 이상 패턴 탐지 (Zap 오류 포함) |

---

## Sub-agent 1 — inventory-validator

### 입력 CSV 스펙

**파일 1: 전산 재고 (system_stock.csv)**
```
item_code, item_name, opening_stock, total_in, total_out, system_stock
PKG-001, 쇼핑백_대, 100, 50, 30, 120
```

**파일 2: 실재고 (physical_stock.csv)**
```
item_code, item_name, physical_stock, count_date, counted_by
PKG-001, 쇼핑백_대, 115, 2026-03-03, 이지수
```

### 검증 로직

```python
# 계산 재고 = 기초재고 + 총입고 - 총출고
calculated_stock = opening_stock + total_in - total_out

# 시스템 갭 = 계산 재고 - 전산 재고 (데이터 입력 오류)
system_gap = calculated_stock - system_stock

# 실물 갭 = 전산 재고 - 실재고 (실물 vs 전산 차이)
physical_gap = system_stock - physical_stock

# 전체 갭 = 계산 재고 - 실재고 (전체 불일치)
total_gap = calculated_stock - physical_stock
```

### 출력 형식

```
[재고 불일치 검증 결과]
품목코드 | 품목명 | 계산재고 | 전산재고 | 실재고 | 시스템갭 | 실물갭 | 전체갭 | 불일치유형
PKG-001 | 쇼핑백_대 | 120 | 120 | 115 | 0 | +5 | +5 | Type B
```

---

## Sub-agent 2 — discrepancy-analyzer

### 불일치 유형 분류

| Type | 조건 | 원인 | 조치 |
|------|------|------|------|
| **Type A** | system_gap ≠ 0 | 입출고 데이터 입력 오류, 트랜잭션 누락 | 트랜잭션 이력 역추적, Zap 오류 확인 |
| **Type B** | system_gap = 0, physical_gap ≠ 0 | 실물 분실·도난·파손, 미기록 사용 | 실사 재확인 후 ADJUST tx 생성 |
| **Type C** | system_gap ≠ 0, physical_gap ≠ 0 | 복합 오류 (입력 오류 + 실물 차이) | Type A 먼저 해결 후 Type B 처리 |

### Airtable 역분개 가이드

```
불일치 확인 후 에어테이블 조치:
1. Type A: 누락된 트랜잭션 찾아 소급 입력 (tx_type: RECEIVE/SHIP 등)
2. Type B: ADJUST_PLUS(701) 또는 ADJUST_MINUS(702) 레코드 신규 생성
   - reason 필드 필수: "실재고조사_YYMMDD" 형식
3. Type C: A → B 순서로 처리

NestJS 전환 시: ADJUST tx는 역분개(REVERSAL) 원칙 적용
→ 잘못된 tx를 지우지 말고, REVERSAL tx(음수 수량)로 상쇄
```

### 우선순위 판단

```
🔴 즉시 처리: |physical_gap| / system_stock > 5% → 출고 오류 위험
🟡 단기 처리: 1% < 차이율 ≤ 5% → 월내 조정 필요
🟢 모니터링: 차이율 ≤ 1% → 다음 사이클 카운팅에서 재확인
```

---

## Sub-agent 3 — cycle-count-planner

### ABC 등급별 카운팅 빈도

| 등급 | 기준 | 카운팅 빈도 |
|------|------|-----------|
| A | 금액 기준 상위 20% (가치의 ~80%) | 월 2회 |
| B | 다음 30% | 월 1회 |
| C | 나머지 50% | 분기 1회 |

> 설계서 원칙과 달리 A등급은 월 2회 적용 (고가치 품목 정확도 강화)

### ABC 분석 산식

```
산정 기준: 연간 출고량 × 단가 → 내림차순 누적 비율
A등급: 누적 비율 0~80%
B등급: 누적 비율 80~95%
C등급: 누적 비율 95~100%
```

### 카운팅 플랜 출력 형식

```
[사이클 카운팅 계획 - YYYY년 MM월]
품목코드 | 품목명 | ABC등급 | 카운팅일정 | 담당자 | 로케이션
PKG-001 | 쇼핑백_대 | A | 3/5, 3/19 | 이지수 | WH01-STORAGE-A03
PKG-002 | 리본_소 | B | 3/12 | 김철수 | WH01-STORAGE-B01
PKG-010 | 포장지_C | C | 4/1 | 박영희 | WH01-STORAGE-C05
```

---

## Sub-agent 4 — transaction-auditor

### Zap 오류 탐지 패턴

에어테이블 Zap 자동화에서 발생하는 대표 오류 패턴:

| 패턴 | 설명 | 탐지 조건 |
|------|------|---------|
| **+N→-N 반복** | 동일 품목 같은 날 입고 후 즉시 동량 출고 반복 | 동일 item_code, 동일 날짜, 양수량 = 음수량 절대값 |
| **중복 Zap** | 동일 트리거가 2회 실행되어 tx 중복 생성 | 동일 item_code + 동일 수량 + 동일 시각 ±5분 내 중복 |
| **source 이상** | Zap source 필드 누락 또는 비정상 값 | source IS NULL 또는 source NOT IN 허용목록 |
| **음수 재고** | 출고 후 전산 재고가 음수로 전환 | quantity_on_hand < 0 |

### 이상 트랜잭션 조치

```
1. +N→-N 패턴: 해당 tx 쌍을 REVERSAL로 상쇄 후 원인 조사
2. 중복 Zap: 나중 tx를 REVERSAL 처리, Zap 트리거 조건 점검
3. 음수 재고: ADJUST_PLUS(701)로 즉시 보정, 근본 원인 별도 분석
```

---

## 핵심 도메인 규칙

### InventoryLedger — Single Source of Truth

- 키: `item_id + location_id + stock_type` 3중 복합 유니크 (`@Unique`)
- 재고 수량은 이 테이블에서만 읽고, 다른 테이블에서 중복 관리 금지
- 모든 수량 변동은 반드시 `InventoryTransaction` INSERT → `InventoryLedger` UPDATE 순서로 처리
- `quantity_on_hand`: UNRESTRICTED 재고 (출고 가능한 실재고)
- `quantity_reserved`: Wave 피킹 예약된 수량 (차감 전)
- `quantity_qc`: QUALITY_INSPECTION 상태 수량
- `quantity_blocked`: BLOCKED 상태 수량
- **가용 수량** = `quantity_on_hand - quantity_reserved`

### InventoryTransaction — 불변 이력 원칙

- **INSERT 전용**. UPDATE/DELETE는 비즈니스 로직에서 완전 차단
- 취소/수정은 `tx_type: REVERSAL`, 음수 수량으로 신규 레코드 INSERT
- `movement_type` 필드: CLAUDE.md의 Movement Type 코드표 준수
- `created_by` 필수. 시스템 자동 생성 시에도 'SYSTEM' 기입
- `reason` 필수: ADJUST_PLUS/MINUS, REVERSAL 시 반드시 사유 기록

### FIFO / FEFO 원칙

- 피킹 LOT 선택 시: `is_fefo = false` → `fifo_date` 오름차순 자동 선택
- 피킹 LOT 선택 시: `is_fefo = true` → `expiry_date` 오름차순 우선, 동일 시 `fifo_date`
- 수동 LOT 오버라이드는 `reason` 필드에 사유 기록 필수

### 안전재고 / 재주문점 알림

```
SS  = Z × σ_demand × √LT       (Z=1.645, 95% 서비스 수준)
ROP = (평균 일 수요 × LT) + SS

알림 트리거: current_stock ≤ item.reorder_point
Alert 생성 후 SCM팀 담당자에게 전달
```

---

## 핵심 Entity 필드

### InventoryLedger

```typescript
@Entity('inventory_ledgers')
@Unique(['item_id', 'location_id', 'stock_type'])
export class InventoryLedger {
  id: string;                    // UUID PK
  item_id: string;               // FK → items
  location_id: string;           // FK → locations
  stock_type: StockType;         // UNRESTRICTED | QUALITY_INSPECTION | BLOCKED | IN_TRANSIT | RESERVED
  quantity_on_hand: number;      // decimal(15,3) — UNRESTRICTED 실재고
  quantity_reserved: number;     // decimal(15,3) — Wave 예약 수량
  quantity_qc: number;           // decimal(15,3) — QC 진행 중
  quantity_blocked: number;      // decimal(15,3) — 불량 격리
  last_updated_at: Date;         // timestamptz — 마지막 변동 시각
  last_transaction_id: string;   // 최종 tx ID (감사 추적)
}
```

### InventoryTransaction

```typescript
@Entity('inventory_transactions')
export class InventoryTransaction {
  id: string;                    // UUID PK
  tx_type: TxType;               // RECEIVE|RETURN_TO_SUPPLIER|ISSUE_INTERNAL|ISSUE_PRODUCTION|TRANSFER|SHIP|ADJUST_PLUS|ADJUST_MINUS|REVERSAL
  movement_type: number;         // SAP Movement Type: 101|122|201|261|311|601|701|702
  item_id: string;               // FK → items
  location_id: string;           // 출발지 또는 대상 로케이션
  to_location_id: string;        // nullable — TRANSFER 목적지
  quantity: number;              // decimal(15,3) — 음수: 출고, 양수: 입고
  stock_type: StockType;
  lot_id: string;                // nullable — LOT 번호
  goods_receipt_id: string;      // nullable — 연관 입하 문서
  wave_id: string;               // nullable — 연관 Wave
  shipment_id: string;           // nullable — 연관 출하
  reversal_of: string;           // nullable — 역분개 대상 tx_id
  reason: string;                // nullable — 조정·반품 사유
  created_at: Date;              // timestamptz — INSERT 전용, 수정 불가
  created_by: string;            // 작업자 ID 또는 'SYSTEM'

  @BeforeUpdate()
  preventUpdate() {
    throw new ForbiddenException('InventoryTransaction is immutable. Use REVERSAL tx instead.');
  }
}
```

### CycleCountRecord

```typescript
@Entity('cycle_count_records')
export class CycleCountRecord {
  id: string;
  item_id: string;
  location_id: string;
  count_date: Date;              // date
  system_qty: number;            // 실사 시점 시스템 수량
  count_qty: number;             // 실사 측정 수량
  variance_qty: number;          // count_qty - system_qty (계산 컬럼)
  variance_pct: number;          // decimal(5,2) — 차이율 %
  status: CycleCountStatus;      // PENDING | COUNTED | ADJUSTED | APPROVED
  adjustment_tx_id: string;      // nullable — 생성된 조정 tx ID
  counted_by: string;
  approved_by: string;           // nullable
  created_at: Date;
  created_by: string;
}
```

---

## 상태 머신

```
CycleCountRecord:
PENDING → COUNTED → ADJUSTED (차이 있을 때 자동 tx 생성) → APPROVED
                  → APPROVED (차이 없을 때 직접)
```

---

## 출력 형식 가이드

코드 생성 시:
1. `InventoryLedger` 수량 변경은 항상 PostgreSQL `queryRunner.startTransaction()` 내에서 처리
2. `InventoryTransaction` 저장 → `InventoryLedger` 업데이트 → commit 순서 엄수
3. `@BeforeUpdate()` 훅을 `InventoryTransaction` entity에 추가하여 UPDATE 시도 시 `ForbiddenException` 발생
4. 재고 조회 API 응답에는 `available_qty` (= `quantity_on_hand - quantity_reserved`) 계산값 포함

---

## 금지 사항

- `InventoryTransaction` 레코드 UPDATE 또는 DELETE 절대 금지
- `InventoryLedger`를 직접 조작하는 raw SQL UPDATE 금지 (Service 메서드 경유 필수)
- LOT 선택 로직에서 FIFO/FEFO 순서를 임의로 변경 금지
- `created_by` 없는 Transaction INSERT 금지
