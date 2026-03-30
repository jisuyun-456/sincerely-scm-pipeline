---
name: accounting-period-close
description: K-IFRS 월말 기간마감 — 재고평가, 원가계산, 분개 검증, 기간잠금, 더존 아마란스10 동기화
---

# K-IFRS 월말 기간마감

> **대상 테이블:** finance.period_closes, finance.accounting_entries, finance.cost_settings, finance.douzone_sync_log
> **참조 테이블:** wms.quants, wms.batches, mm.stock_movements, shared.gl_accounts
> **원칙:** period_closes INSERT ONLY, is_closed=TRUE 후 해당 기간 수정 절대 불가

---

## 1. 월말 마감 5단계 체크리스트

```
Step 1: 미처리 확인     → 미전기 분개, 미완료 이동, 미동기화 전표
Step 2: 재고평가        → 가중평균/FIFO 원가 계산
Step 3: period_closes   → 기말 재고 스냅샷 INSERT
Step 4: 분개 검증       → 차변합=대변합, 계정 유효성
Step 5: 기간잠금        → is_closed=TRUE (되돌릴 수 없음)
```

---

## 2. Step 1 — 미처리 확인

### 미전기 분개 확인
```sql
SELECT entry_number, entry_type, amount, status
FROM finance.accounting_entries
WHERE fiscal_year = EXTRACT(YEAR FROM CURRENT_DATE)
  AND fiscal_period = EXTRACT(MONTH FROM CURRENT_DATE)
  AND status != 'posted';
-- 결과 0건이어야 마감 진행 가능
```

### 미완료 재고 이동 확인
```sql
SELECT movement_number, movement_type, status, posting_date
FROM mm.stock_movements
WHERE posting_date >= date_trunc('month', CURRENT_DATE)
  AND posting_date < date_trunc('month', CURRENT_DATE) + INTERVAL '1 month'
  AND status NOT IN ('completed', 'cancelled');
-- 결과 0건이어야 마감 진행 가능
```

### 더존 미동기화 전표 확인
```sql
SELECT ae.entry_number, dsl.sync_status, dsl.sync_notes
FROM finance.douzone_sync_log dsl
JOIN finance.accounting_entries ae ON ae.id = dsl.entry_id
WHERE ae.fiscal_year = EXTRACT(YEAR FROM CURRENT_DATE)
  AND ae.fiscal_period = EXTRACT(MONTH FROM CURRENT_DATE)
  AND dsl.sync_status != 'synced';
-- 결과 0건이어야 마감 진행 가능 (또는 강제 마감 시 경고)
```

---

## 3. Step 2 — 재고평가

### 원가 계산 방식 확인
```sql
SELECT parts_type, costing_method
FROM finance.cost_settings
WHERE effective_to IS NULL;  -- 현행 유효 정책
```

### 가중평균법 (weighted_avg)
```sql
-- 품목별 가중평균 단가 계산
SELECT
  q.parts_id,
  sb.warehouse_id,
  SUM(q.physical_qty) AS total_qty,
  CASE
    WHEN SUM(q.physical_qty) > 0
    THEN SUM(q.physical_qty * COALESCE(b.unit_cost, 0)) / SUM(q.physical_qty)
    ELSE 0
  END AS weighted_avg_cost,
  SUM(q.physical_qty * COALESCE(b.unit_cost, 0)) AS total_value
FROM wms.quants q
JOIN wms.storage_bins sb ON sb.id = q.storage_bin_id
LEFT JOIN wms.batches b ON b.id = q.batch_id
WHERE q.physical_qty > 0
GROUP BY q.parts_id, sb.warehouse_id;
```

### FIFO (선입선출법)
```sql
-- 배치별 입고 순서 기준 원가 적용
SELECT
  q.parts_id,
  sb.warehouse_id,
  b.batch_number,
  b.unit_cost,
  q.physical_qty,
  q.physical_qty * b.unit_cost AS batch_value,
  b.created_at AS fifo_order
FROM wms.quants q
JOIN wms.storage_bins sb ON sb.id = q.storage_bin_id
JOIN wms.batches b ON b.id = q.batch_id
WHERE q.physical_qty > 0
ORDER BY q.parts_id, sb.warehouse_id, b.created_at ASC;
```

---

## 4. Step 3 — period_closes INSERT

```sql
-- 기말 재고 스냅샷 생성
INSERT INTO finance.period_closes (
  id, period, parts_id, warehouse_id,
  closing_qty, closing_value, unit_cost,
  costing_method, is_closed, created_at
)
SELECT
  gen_random_uuid(),
  to_char(CURRENT_DATE, 'YYYY-MM'),
  q.parts_id,
  sb.warehouse_id,
  SUM(q.physical_qty),
  SUM(q.physical_qty * COALESCE(b.unit_cost, 0)),
  CASE
    WHEN SUM(q.physical_qty) > 0
    THEN ROUND(SUM(q.physical_qty * COALESCE(b.unit_cost, 0)) / SUM(q.physical_qty), 2)
    ELSE 0
  END,
  cs.costing_method,
  FALSE,  -- 아직 잠금 전
  NOW()
FROM wms.quants q
JOIN wms.storage_bins sb ON sb.id = q.storage_bin_id
LEFT JOIN wms.batches b ON b.id = q.batch_id
JOIN shared.parts_master pt ON pt.id = q.parts_id
LEFT JOIN finance.cost_settings cs
  ON cs.parts_type = pt.parts_type AND cs.effective_to IS NULL
WHERE q.physical_qty != 0
GROUP BY q.parts_id, sb.warehouse_id, cs.costing_method;
```

### 생성 결과 검증
```sql
SELECT
  COUNT(*) AS record_count,
  SUM(closing_qty) AS total_qty,
  SUM(closing_value) AS total_value
FROM finance.period_closes
WHERE period = to_char(CURRENT_DATE, 'YYYY-MM')
  AND is_closed = FALSE;
```

---

## 5. Step 4 — 분개 검증

### 차변합 = 대변합 검증
```sql
-- 단일 행 차/대변 구조이므로 항상 균형 (amount = debit = credit)
-- 순잔액 기준으로 검증
SELECT
  fiscal_year, fiscal_period,
  COUNT(*) AS entry_count,
  SUM(CASE WHEN is_reversal THEN -amount ELSE amount END) AS net_amount,
  COUNT(*) FILTER (WHERE status != 'posted') AS unposted_count
FROM finance.accounting_entries
WHERE fiscal_year = EXTRACT(YEAR FROM CURRENT_DATE)
  AND fiscal_period = EXTRACT(MONTH FROM CURRENT_DATE)
GROUP BY fiscal_year, fiscal_period;
```

### GL 계정 유효성 체크
```sql
SELECT ae.entry_number, ae.debit_account_id, ae.credit_account_id
FROM finance.accounting_entries ae
LEFT JOIN shared.gl_accounts da ON da.id = ae.debit_account_id
LEFT JOIN shared.gl_accounts ca ON ca.id = ae.credit_account_id
WHERE ae.fiscal_year = EXTRACT(YEAR FROM CURRENT_DATE)
  AND ae.fiscal_period = EXTRACT(MONTH FROM CURRENT_DATE)
  AND (da.id IS NULL OR ca.id IS NULL);
-- 결과 0건이어야 정상
```

---

## 6. Step 5 — 기간잠금

```sql
-- 기간 잠금 실행 (되돌릴 수 없음!)
UPDATE finance.period_closes
SET
  is_closed = TRUE,
  closed_by = '{{current_user_id}}',
  closed_at = NOW()
WHERE period = to_char(CURRENT_DATE, 'YYYY-MM')
  AND is_closed = FALSE;
```

**잠금 후 효과:**
- 해당 기간의 stock_movements INSERT → 트리거가 거부
- 해당 기간의 accounting_entries INSERT → 트리거가 거부
- 해당 기간의 period_closes 재생성 불가

---

## 7. 더존 아마란스10 동기화 검증

```sql
-- 동기화 현황 요약
SELECT
  sync_status,
  COUNT(*) AS count
FROM finance.douzone_sync_log dsl
JOIN finance.accounting_entries ae ON ae.id = dsl.entry_id
WHERE ae.fiscal_year = EXTRACT(YEAR FROM CURRENT_DATE)
  AND ae.fiscal_period = EXTRACT(MONTH FROM CURRENT_DATE)
GROUP BY sync_status;

-- 실패 건 상세
SELECT
  ae.entry_number, ae.entry_type, ae.amount,
  dsl.sync_status, dsl.sync_notes, dsl.created_at
FROM finance.douzone_sync_log dsl
JOIN finance.accounting_entries ae ON ae.id = dsl.entry_id
WHERE dsl.sync_status = 'error'
  AND ae.fiscal_year = EXTRACT(YEAR FROM CURRENT_DATE)
  AND ae.fiscal_period = EXTRACT(MONTH FROM CURRENT_DATE);
```

**동기화 기준:**
- 전체 `synced` → 마감 가능
- `error` 1건이라도 있으면 → 재시도 후 마감
- `pending` → 동기화 완료 대기

---

## 8. 마감 취소/재오픈 절차

> **원칙:** 기간 마감은 되돌리지 않음. 불가피한 경우에만 관리자 승인 후 실행.

```sql
-- ⚠️ 관리자 전용 — 마감 취소
-- 1. 해당 기간에 새로운 이동이 없는지 확인
-- 2. 승인자 기록
UPDATE finance.period_closes
SET
  is_closed = FALSE,
  closed_by = NULL,
  closed_at = NULL
WHERE period = '2026-03'
  AND is_closed = TRUE;

-- 재오픈 후 반드시:
-- 1. 수정 사유 기록 (별도 audit_log 또는 코멘트)
-- 2. 수정 분개 추가 (Storno + 재기표)
-- 3. 재마감 실행
```

---

## 전체 마감 실행 순서 요약

```
1. 미처리 확인 쿼리 3개 실행 → 모두 0건 확인
2. 재고평가 쿼리 실행 → 결과 검토
3. period_closes INSERT 실행
4. 분개 검증 쿼리 2개 실행 → 모두 정상 확인
5. 더존 동기화 확인 → 전체 synced
6. 기간잠금 UPDATE 실행 → is_closed=TRUE
7. 마감 완료 보고
```
