---
name: db-data-integrity
description: 프로덕션급 데이터 정합성 검증 — quants↔movements 크로스체크, 트리거 체인 디버깅, 음수 재고 탐지, 불변 원장 감사
---

# DB 데이터 정합성 검증 — Professional Grade

> **적용 대상:** PostgreSQL 기반 SCM 시스템
> **원칙:** stock_movements/goods_receipts/accounting_entries = INSERT ONLY 불변 원장. 정정은 반드시 Storno(역분개).

---

## 1. 검증 계층 구조 (Defense in Depth)

```
Layer 1: Schema Constraints     — PK/FK/UNIQUE/CHECK/NOT NULL
Layer 2: Trigger Invariants     — quants 자동갱신, 회계 자동전표
Layer 3: Application Assertions — Storno 역분개, 기간잠금
Layer 4: Periodic Audit Queries — 크로스체크, 드리프트 탐지
Layer 5: Anomaly Detection      — 음수재고, 고아 레코드, 합계 불일치
```

모든 검증은 Layer 순서대로 수행. 상위 레이어 위반은 하위 레이어 결함을 의미.

---

## 2. 핵심 불변식 (Invariants)

### INV-01: quants.physical_qty = SUM(stock_movements.actual_qty)
재고 수량은 모든 이동 트랜잭션의 합과 일치해야 함.

```sql
-- 불변식 검증: quants vs stock_movements 크로스체크
WITH movement_totals AS (
  SELECT
    parts_id,
    COALESCE(to_bin_id, from_bin_id) AS bin_id,
    batch_id,
    SUM(
      CASE
        WHEN movement_type IN ('101','161','262','501','561','701') THEN actual_qty   -- 입고성
        WHEN movement_type IN ('102','201','261','301','551','601','702') THEN -actual_qty  -- 출고성
        ELSE 0
      END
    ) AS calc_qty
  FROM mm.stock_movements
  WHERE status = 'completed'
  GROUP BY parts_id, COALESCE(to_bin_id, from_bin_id), batch_id
),
quant_totals AS (
  SELECT parts_id, storage_bin_id AS bin_id, batch_id, physical_qty
  FROM wms.quants
)
SELECT
  COALESCE(m.parts_id, q.parts_id) AS parts_id,
  COALESCE(m.bin_id, q.bin_id) AS bin_id,
  COALESCE(m.batch_id, q.batch_id) AS batch_id,
  COALESCE(q.physical_qty, 0) AS quant_qty,
  COALESCE(m.calc_qty, 0) AS movement_qty,
  COALESCE(q.physical_qty, 0) - COALESCE(m.calc_qty, 0) AS drift
FROM movement_totals m
FULL OUTER JOIN quant_totals q
  ON m.parts_id = q.parts_id
  AND m.bin_id = q.bin_id
  AND m.batch_id IS NOT DISTINCT FROM q.batch_id
WHERE COALESCE(q.physical_qty, 0) != COALESCE(m.calc_qty, 0);
```

**drift != 0 이면:** 트리거 누락 또는 직접 UPDATE 발생. 즉시 조사 필요.

### INV-02: quants.available_qty = physical_qty - reserved_qty - blocked_qty
GENERATED ALWAYS 컬럼이므로 DB 레벨에서 보장. 검증 불필요 (스키마가 강제).

### INV-03: 불변 원장 변조 없음
```sql
-- stock_movements에 UPDATE/DELETE 흔적 탐지
-- xmin이 insert 시점과 다르면 변조 의심
SELECT id, movement_number, xmin, created_at
FROM mm.stock_movements
WHERE updated_at > created_at + INTERVAL '1 second';

-- goods_receipts 변조 체크 (INSERT ONLY이므로 updated_at 없어야 함)
SELECT COUNT(*) AS tampered_count
FROM mm.goods_receipts
WHERE id IN (
  SELECT id FROM mm.goods_receipts
  EXCEPT
  SELECT id FROM mm.goods_receipts WHERE created_at IS NOT NULL
);
```

### INV-04: 역분개 무결성
```sql
-- 역분개가 원본을 정확히 상쇄하는지 검증
SELECT
  orig.movement_number AS original,
  rev.movement_number AS reversal,
  orig.actual_qty AS orig_qty,
  rev.actual_qty AS rev_qty,
  orig.parts_id = rev.parts_id AS parts_match,
  orig.actual_qty = rev.actual_qty AS qty_match
FROM mm.stock_movements rev
JOIN mm.stock_movements orig ON orig.id = rev.reversal_movement_id
WHERE rev.is_reversal = TRUE
  AND (orig.parts_id != rev.parts_id OR orig.actual_qty != rev.actual_qty);
-- 결과가 있으면: 역분개가 원본과 불일치 → 수동 조정 필요
```

### INV-05: 회계 분개 차대변 균형
```sql
-- 차변 합계 = 대변 합계 (단일 행 차/대변 구조에서는 항상 성립)
-- 하지만 reversal 포함 시 순잔액 검증
SELECT
  fiscal_year, fiscal_period,
  SUM(amount) AS total_debit,
  SUM(amount) AS total_credit,
  SUM(CASE WHEN is_reversal THEN -amount ELSE amount END) AS net_amount
FROM finance.accounting_entries
WHERE status = 'posted'
GROUP BY fiscal_year, fiscal_period
ORDER BY fiscal_year, fiscal_period;
```

---

## 3. 음수 재고 탐지 및 대응

### 탐지
```sql
-- Level 1: 현재 음수 재고
SELECT
  pt.parts_code, pt.parts_name,
  w.warehouse_code, sb.bin_code,
  q.physical_qty, q.reserved_qty, q.available_qty,
  b.batch_number
FROM wms.quants q
JOIN shared.parts_master pt ON pt.id = q.parts_id
JOIN wms.storage_bins sb ON sb.id = q.storage_bin_id
JOIN wms.warehouses w ON w.id = sb.warehouse_id
LEFT JOIN wms.batches b ON b.id = q.batch_id
WHERE q.physical_qty < 0 OR q.available_qty < 0;

-- Level 2: 음수를 유발한 이동 추적
SELECT
  sm.movement_number, sm.movement_type, sm.actual_qty,
  sm.posting_date, sm.created_at,
  pt.parts_code,
  u.name AS created_by_name
FROM mm.stock_movements sm
JOIN shared.parts_master pt ON pt.id = sm.parts_id
LEFT JOIN shared.users u ON u.id = sm.created_by
WHERE sm.parts_id IN (
  SELECT parts_id FROM wms.quants WHERE physical_qty < 0
)
ORDER BY sm.posting_date DESC, sm.created_at DESC
LIMIT 50;
```

### 대응 절차
1. **원인 분류:** 이중 출고 / 입고 누락 / 타이밍 이슈 / 데이터 오류
2. **Storno 처리:** 잘못된 이동을 역분개 (is_reversal=TRUE, reversal_movement_id 설정)
3. **재고 조정:** 이동유형 701(잉여) / 702(부족) 으로 실사 조정
4. **절대 금지:** quants 직접 UPDATE (트리거 체인 무시됨)

---

## 4. 트리거 체인 디버깅

### 트리거 실행 순서
```
mm.stock_movements INSERT
  → [014] trg_update_quants: quants.physical_qty += actual_qty
  → [016] trg_create_accounting_entry: finance.accounting_entries INSERT

mm.reservations INSERT/UPDATE
  → [015] trg_update_reserved_qty: quants.reserved_qty 갱신

wms.inventory_count_items INSERT
  → trg_create_adjustment_movement: mm.stock_movements INSERT (701/702)
    → (위 체인 재귀 실행)
```

### 트리거 디버깅 쿼리
```sql
-- 트리거 존재 여부 확인
SELECT
  trigger_name, event_manipulation, event_object_schema, event_object_table,
  action_statement
FROM information_schema.triggers
WHERE event_object_schema IN ('mm', 'wms', 'finance')
ORDER BY event_object_schema, event_object_table;

-- 트리거 함수 소스 확인
SELECT
  n.nspname AS schema, p.proname AS function_name,
  pg_get_functiondef(p.oid) AS definition
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname IN ('mm', 'wms', 'finance')
  AND p.proname LIKE 'trg_%';

-- 트리거 실행 실패 탐지 (stock_movement 있는데 quant 미반영)
SELECT sm.id, sm.movement_number, sm.movement_type, sm.posting_date
FROM mm.stock_movements sm
WHERE sm.status = 'completed'
  AND NOT EXISTS (
    SELECT 1 FROM wms.quants q
    WHERE q.parts_id = sm.parts_id
      AND q.storage_bin_id = COALESCE(sm.to_bin_id, sm.from_bin_id)
  );
```

### 트리거 비활성화 (긴급 대량 작업 시에만)
```sql
-- ⚠️ 주의: 반드시 트랜잭션 안에서, 작업 후 즉시 재활성화
BEGIN;
ALTER TABLE mm.stock_movements DISABLE TRIGGER trg_update_quants;
-- 대량 INSERT 수행
ALTER TABLE mm.stock_movements ENABLE TRIGGER trg_update_quants;
-- 수동으로 quants 재계산 필요
COMMIT;
```

---

## 5. 고아 레코드 탐지

```sql
-- PO가 없는 GR (FK 위반이 아니라 논리적 고아)
SELECT gr.gr_number, gr.po_id
FROM mm.goods_receipts gr
LEFT JOIN mm.purchase_orders po ON po.id = gr.po_id
WHERE po.id IS NULL;

-- 프로젝트가 없는 PO
SELECT po.po_number, po.project_id
FROM mm.purchase_orders po
LEFT JOIN shared.projects p ON p.id = po.project_id
WHERE p.id IS NULL;

-- 배치가 없는 quant (batch_managed 품목인데 batch_id NULL)
SELECT q.id, pt.parts_code, pt.parts_name, q.physical_qty
FROM wms.quants q
JOIN shared.parts_master pt ON pt.id = q.parts_id
WHERE pt.is_batch_managed = TRUE AND q.batch_id IS NULL AND q.physical_qty > 0;

-- GL 계정이 삭제/비활성화된 분개
SELECT ae.entry_number, ae.debit_account_id, ae.credit_account_id
FROM finance.accounting_entries ae
LEFT JOIN shared.gl_accounts da ON da.id = ae.debit_account_id
LEFT JOIN shared.gl_accounts ca ON ca.id = ae.credit_account_id
WHERE da.id IS NULL OR ca.id IS NULL;
```

---

## 6. 기간 마감 정합성

```sql
-- period_closes 수량 vs 실제 quants 스냅샷 비교
WITH current_stock AS (
  SELECT
    q.parts_id,
    sb.warehouse_id,
    SUM(q.physical_qty) AS actual_qty,
    SUM(q.physical_qty * COALESCE(b.unit_cost, 0)) AS actual_value
  FROM wms.quants q
  JOIN wms.storage_bins sb ON sb.id = q.storage_bin_id
  LEFT JOIN wms.batches b ON b.id = q.batch_id
  GROUP BY q.parts_id, sb.warehouse_id
)
SELECT
  pc.period,
  pt.parts_code,
  w.warehouse_code,
  pc.closing_qty,
  cs.actual_qty,
  pc.closing_qty - COALESCE(cs.actual_qty, 0) AS qty_diff,
  pc.closing_value,
  cs.actual_value,
  pc.closing_value - COALESCE(cs.actual_value, 0) AS value_diff
FROM finance.period_closes pc
JOIN shared.parts_master pt ON pt.id = pc.parts_id
JOIN wms.warehouses w ON w.id = pc.warehouse_id
LEFT JOIN current_stock cs
  ON cs.parts_id = pc.parts_id AND cs.warehouse_id = pc.warehouse_id
WHERE pc.period = to_char(CURRENT_DATE, 'YYYY-MM')
  AND (pc.closing_qty != COALESCE(cs.actual_qty, 0)
    OR ABS(pc.closing_value - COALESCE(cs.actual_value, 0)) > 0.01);
```

---

## 7. 전체 정합성 감사 실행 순서

```
Step 1: INV-01 — quants ↔ stock_movements 드리프트 체크
Step 2: INV-03 — 불변 원장 변조 체크
Step 3: INV-04 — 역분개 무결성
Step 4: INV-05 — 회계 차대변 균형
Step 5: 음수 재고 탐지
Step 6: 고아 레코드 탐지
Step 7: 기간 마감 정합성 (마감 기간만)
```

**실행 빈도:**
- Step 1~5: 매일 (크론잡 또는 수동)
- Step 6: 주 1회
- Step 7: 월말 마감 직전

**결과 해석:**
- 모든 쿼리 결과가 0건 = 정합성 완벽
- 1건이라도 있으면 = 즉시 원인 분석 후 Storno/조정

---

## 8. 코드 리뷰 체크리스트 (DB 변경 시)

### INSERT 쿼리 리뷰
- [ ] 불변 원장 테이블에 UPDATE/DELETE 없는지 확인
- [ ] stock_movements INSERT 시 트리거가 quants를 정확히 갱신하는지
- [ ] batch_id 가 batch_managed 품목에서 필수로 들어가는지
- [ ] movement_type 이 유효한 SAP 코드인지 (101/102/161/201/261/262/301/501/551/561/601/701/702)
- [ ] unit_cost_at_movement 가 정확한 시점의 원가인지

### 트리거 변경 리뷰
- [ ] 기존 트리거 체인과 충돌 없는지
- [ ] BEFORE/AFTER 순서 확인
- [ ] 재귀 트리거 무한루프 방지
- [ ] EXCEPTION 핸들링으로 부분 실패 방지
- [ ] 대량 INSERT 성능 테스트 (1000건 이상)

### 마이그레이션 리뷰
- [ ] 기존 데이터 무결성 유지
- [ ] 롤백 스크립트 존재
- [ ] 인덱스 영향 분석
- [ ] RLS 정책 업데이트 필요 여부
