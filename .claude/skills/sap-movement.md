# SAP 이동유형 처리 방법론

## 이동유형 결정 로직

에어테이블 '이동목적' 필드 → SAP Movement Type 매핑 (movement-type.map.ts):

```
재고이동   → 311  (창고간 이동 출고)
재고조정   → 701  (실사 조정, 방향은 수량 부호)
재고생산   → 101  (발주 입고, GR)
생산투입   → 201  (원가센터 출고)
생산산출   → 101  (생산 완료 입고)
조립투입   → 261  (소비출고, GI for Assembly)
조립산출   → 101  (조립 완료 입고)
고객납품   → 601  (고객 출고)
고객물품   → 101  (고객물품 입고)
외주임가공 → 261  (외주 임가공 출고)
리턴       → 312  (반품 입고)
회수       → 312  (회수 입고)
```

미매핑 이동목적(예: '생산샘플')은 '999'로 처리 → skipped_unknown_type.

## 방향 결정 (direction)

```typescript
// 1순위: 입하수량 > 0 → direction = +1 (입고)
// 2순위: 출고수량 > 0 → direction = -1 (출고)
// 3순위: 이동유형 기반 판단
const outTypes = ['261', '201', '311', '601', '702'];
return outTypes.includes(movementType) ? -1 : 1;
```

## Storno(역분개) 처리

취소가 필요할 때 원본을 수정하지 않고, 역방향 전표를 새로 생성한다.

### 절차
1. 원본 전표 조회 (doc_number로 검색)
2. 이미 reversed 상태면 스킵
3. STORNO-{원본doc_number} 역방향 전표 INSERT
   - direction: 원본 * -1 (역방향)
   - at_purpose: "STORNO:{원본목적}"
   - source: "storno"
4. stock_balance 역산: 현재 잔고 - (원본수량 * 원본방향)

### 예시
```
원본: PT1234 @ 에이원, 101입고, qty=100, direction=+1
Storno: STORNO-MM00200001, qty=100, direction=-1
잔고: 원래 300개 → 300 - (100 * 1) = 200개
```

### 주의: INSERT ONLY 원칙과 status UPDATE
현재 inventory.service.ts:160-162에서 원본 전표의 status를 'reversed'로 UPDATE하고 있음.
이는 편의를 위한 것이나 INSERT ONLY 원칙과 충돌 가능성 있음.
향후 status 트래킹을 별도 테이블 또는 REVERSAL 전표의 ref_doc_number로 대체 검토 필요.

## 음수 재고 차단

```
projected_qty = current_qty + (quantity * direction)
if (!is_customer_goods && projected_qty < 0) → ConflictException
```

고객물품(is_customer_goods=true)은 음수 허용 — 고객 소유 재고이므로 자사 원장과 독립.

## 관리 위치 필터
MANAGED_LOCATIONS = ['에이원지식산업센터', '베스트원']
이외 위치는 스킵 (unmanaged_location).

## 기간(Period) 형식
posting_date → YYMM (예: 2026-03-15 → '2603')
period_close.is_closed가 true면 해당 기간 전표 차단.
