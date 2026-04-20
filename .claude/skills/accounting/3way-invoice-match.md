---
name: accounting-invoice-match
description: PO↔GR↔Invoice 3-way match — 매입 인보이스 검증, 가격차이 처리, 더존 매입전표 연계
---

# PO↔GR↔Invoice 3-Way Match

> **핵심 원칙:** No PO, No Pay — 발주 없는 인보이스는 처리 불가
> **대상 테이블:** mm.invoice_verifications, mm.purchase_orders, mm.purchase_order_items, mm.goods_receipts
> **회계 테이블:** finance.accounting_entries, shared.gl_accounts
> **더존 연계:** finance.douzone_sync_log

---

## 1. 3-Way Match 원칙

```
PO (발주 금액)  ←→  GR (입고 금액)  ←→  Invoice (청구 금액)
   order_qty        received_qty         invoice_qty
   × unit_price     × unit_cost          × invoice_price
   = PO amount      = GR amount          = Invoice amount
```

**Match 판정 기준:**
| 조건 | 판정 | 처리 |
|------|------|------|
| PO = GR = Invoice | Perfect Match | 자동 승인 |
| 차이 ≤ 2% | Within Tolerance | 자동 승인 (차이 기록) |
| 차이 > 2% | Variance | 수동 승인 필요 |
| PO 없음 | No Match | 처리 불가 (No PO No Pay) |

---

## 2. 3-Way Match 매칭 쿼리

```sql
-- PO vs GR vs Invoice 비교
SELECT
  po.po_number,
  v.vendor_name,
  poi.line_number,
  pt.parts_name,
  -- PO 금액
  poi.order_qty AS po_qty,
  poi.unit_price AS po_price,
  poi.total_amount AS po_amount,
  -- GR 금액
  COALESCE(gr_sum.total_received, 0) AS gr_qty,
  COALESCE(gr_sum.avg_unit_cost, 0) AS gr_price,
  COALESCE(gr_sum.total_cost, 0) AS gr_amount,
  -- 차이 분석
  poi.total_amount - COALESCE(gr_sum.total_cost, 0) AS po_gr_diff,
  CASE
    WHEN poi.total_amount > 0
    THEN ROUND(ABS(poi.total_amount - COALESCE(gr_sum.total_cost, 0)) / poi.total_amount * 100, 2)
    ELSE 0
  END AS variance_pct,
  CASE
    WHEN ABS(poi.total_amount - COALESCE(gr_sum.total_cost, 0)) / NULLIF(poi.total_amount, 0) <= 0.02
    THEN 'matched'
    ELSE 'variance'
  END AS match_status
FROM mm.purchase_order_items poi
JOIN mm.purchase_orders po ON po.id = poi.po_id
JOIN shared.vendors v ON v.id = po.vendor_id
JOIN shared.parts_master pt ON pt.id = poi.parts_id
LEFT JOIN (
  SELECT
    po_item_id,
    SUM(received_qty) AS total_received,
    AVG(unit_cost) AS avg_unit_cost,
    SUM(total_cost) AS total_cost
  FROM mm.goods_receipts
  GROUP BY po_item_id
) gr_sum ON gr_sum.po_item_id = poi.id
WHERE po.po_status IN ('received', 'closed')
ORDER BY po.po_number, poi.line_number;
```

---

## 3. Invoice Verification 생성

```sql
-- 인보이스 검증 레코드 생성
INSERT INTO mm.invoice_verifications (
  id, iv_number, po_id, vendor_id,
  invoice_date, invoice_amount, gr_amount,
  price_variance, status, created_at
) VALUES (
  gen_random_uuid(),
  'IV-' || to_char(CURRENT_DATE, 'YYYYMMDD') || '-0001',
  '{{po_id}}',
  '{{vendor_id}}',
  CURRENT_DATE,
  {{invoice_amount}},
  {{gr_amount}},
  {{invoice_amount}} - {{gr_amount}},
  CASE
    WHEN ABS({{invoice_amount}} - {{gr_amount}}) / NULLIF({{gr_amount}}, 0) <= 0.02
    THEN 'matched'
    ELSE 'variance'
  END,
  NOW()
);
```

---

## 4. 가격차이 회계처리

### GL 계정 매핑
| 계정코드 | 계정명 | 용도 |
|----------|--------|------|
| 1140 | 원재료 | 입고 시 재고 자산 |
| 2110 | 외상매입금 | 공급업체 미지급 |
| 5110 | 매입원가 | 매입 비용 |
| 5220 | 매입가격차이 | PO vs Invoice 단가 차이 |

### 불리한 차이 (Invoice > GR)
```
Dr. 매입가격차이 (5220)    ₩50,000
  Cr. 외상매입금 (2110)              ₩50,000
```

### 유리한 차이 (Invoice < GR)
```
Dr. 외상매입금 (2110)      ₩30,000
  Cr. 매입가격차이 (5220)            ₩30,000
```

### 가격차이 분개 생성 SQL
```sql
-- 가격차이가 있는 경우 자동 분개
INSERT INTO finance.accounting_entries (
  id, entry_number, entry_date, entry_type,
  source_table, source_id,
  debit_account_id, credit_account_id,
  amount, fiscal_year, fiscal_period,
  status, description, created_at
)
SELECT
  gen_random_uuid(),
  'AE-' || to_char(CURRENT_DATE, 'YYYYMMDD') || '-' || LPAD(nextval('finance.ae_seq')::text, 4, '0'),
  CURRENT_DATE,
  'purchase_invoice',
  'mm.invoice_verifications',
  iv.id,
  CASE
    WHEN iv.price_variance > 0
    THEN (SELECT id FROM shared.gl_accounts WHERE account_code = '5220')  -- 불리한: Dr.가격차이
    ELSE (SELECT id FROM shared.gl_accounts WHERE account_code = '2110')  -- 유리한: Dr.매입금
  END,
  CASE
    WHEN iv.price_variance > 0
    THEN (SELECT id FROM shared.gl_accounts WHERE account_code = '2110')  -- 불리한: Cr.매입금
    ELSE (SELECT id FROM shared.gl_accounts WHERE account_code = '5220')  -- 유리한: Cr.가격차이
  END,
  ABS(iv.price_variance),
  EXTRACT(YEAR FROM CURRENT_DATE),
  EXTRACT(MONTH FROM CURRENT_DATE),
  'draft',
  'Price variance: PO ' || po.po_number || ' / IV ' || iv.iv_number,
  NOW()
FROM mm.invoice_verifications iv
JOIN mm.purchase_orders po ON po.id = iv.po_id
WHERE iv.price_variance != 0
  AND iv.status IN ('matched', 'variance');
```

---

## 5. 더존 아마란스10 매입전표 연계

### 필드 매핑
| SCM 필드 | 더존 아마란스10 |
|----------|---------------|
| entry_number | 전표번호 |
| entry_date | 전표일자 |
| vendor → douzone_vendor_code | 거래처코드 |
| debit_account → douzone_code | 차변계정코드 |
| credit_account → douzone_code | 대변계정코드 |
| amount | 금액 |
| tax_invoice_no | 세금계산서번호 |

### 동기화 상태 추적
```sql
-- 매입전표 동기화 기록
INSERT INTO finance.douzone_sync_log (
  id, entry_id, douzone_slip_no,
  sync_status, sync_notes, created_at
) VALUES (
  gen_random_uuid(),
  '{{entry_id}}',
  '{{douzone_slip_no}}',
  'synced',  -- pending / synced / error
  NULL,
  NOW()
);
```

---

## 6. 지급 처리 Workflow

```
Invoice 등록 → 3-Way Match → 검증 완료
  → matched: 자동 지급 대상 등록
  → variance (≤2%): 자동 승인 → 지급 대상
  → variance (>2%): 수동 승인 대기 → 승인 후 지급 대상
  → posted: 더존 전표 생성 → 지급 실행
```

### 지급 대상 조회
```sql
SELECT
  iv.iv_number,
  v.vendor_name,
  v.douzone_vendor_code,
  iv.invoice_amount,
  iv.status,
  v.bank_name, v.bank_account, v.bank_holder
FROM mm.invoice_verifications iv
JOIN shared.vendors v ON v.id = iv.vendor_id
WHERE iv.status = 'posted'
ORDER BY iv.invoice_date;
```

---

## 7. 예외 케이스

### 부분입고 (Partial Receipt)
- PO 150개 발주 → GR 140개 입고 → Invoice 140개 기준으로 매칭
- 미입고 10개는 다음 GR 대기

### 초과입고 (Over Receipt)
- PO 100개 → GR 105개 → over_delivery_tolerance_pct 확인
- 허용 범위 내: 정상 처리 / 초과: 반품 처리

### 반품 후 재청구
```
원본 GR: 100개 입고 → Invoice ₩500,000
불량 반품: 5개 반품 (RET-001, Storno)
재청구: Invoice ₩475,000 (95개 기준)
```
- 원본 Invoice에 대해 Credit Memo 발행
- 수정 Invoice로 재매칭

### Credit/Debit Memo
- **Credit Memo:** 공급업체가 금액 차감 (반품, 할인)
- **Debit Memo:** 추가 청구 (운임, 가공비)
- 모두 invoice_verifications에 별도 레코드로 INSERT

---

## 주의사항

- **INSERT ONLY 원칙:** invoice_verifications는 status UPDATE만 허용 (matched→posted)
- **기간 마감 체크:** is_closed=TRUE인 기간에는 새 분개 INSERT 불가
- **동시성:** 같은 PO에 대한 동시 IV 생성 방지 (UNIQUE constraint)
- **부가세:** vat_amount은 별도 관리 (세금계산서 연동 시)
