# SCM SSOT Retool 쿼리 모음

> Supabase 연결 기준 — 모든 쿼리는 Retool의 Supabase Resource를 사용합니다.
> 변수 참조: `{{ component_name.value }}` 형식

---

## 목차

1. [대시보드](#page-1-대시보드)
2. [Projects CRUD](#page-2-projects-crud)
3. [Clients/Vendors](#page-3-clientsvendors)
4. [발주/입하 (MM)](#page-4-발주입하-mm)
5. [재고/창고 (WMS)](#page-5-재고창고-wms)
6. [임가공 (PP)](#page-6-임가공-pp)
7. [출하/물류 (TMS)](#page-7-출하물류-tms)
8. [전표/더존 (Finance)](#page-8-전표더존-finance)
9. [워크플로우 추적기](#page-9-워크플로우-추적기)
10. [유틸리티 쿼리](#appendix-유용한-유틸리티-쿼리)

---

## Page 1: 대시보드

### Query: `dashboard_project_kpi`

프로젝트 상태별 KPI 카드용 집계

```sql
SELECT
  project_status,
  COUNT(*) as cnt
FROM shared.projects
GROUP BY project_status
ORDER BY cnt DESC;
```

### Query: `dashboard_pending_entries`

미처리 전표 현황 (대시보드 알림 카드)

```sql
SELECT
  status,
  COUNT(*) as cnt,
  SUM(amount) as total_amount
FROM finance.accounting_entries
GROUP BY status
ORDER BY status;
```

### Query: `dashboard_march_calendar`

3월 출하 일정 캘린더 (날짜 범위를 파라미터로 변경 가능)

```sql
SELECT
  project_code,
  project_name,
  first_shipment_date,
  last_shipment_date,
  project_status,
  c.company_name AS client_name,
  u.name AS cx_specialist
FROM shared.projects p
LEFT JOIN shared.clients c ON c.id = p.client_id
LEFT JOIN shared.users u ON u.id = p.cx_specialist_id
WHERE first_shipment_date BETWEEN '2026-03-01' AND '2026-03-31'
ORDER BY first_shipment_date;
```

---

## Page 2: Projects CRUD

### Query: `projects_list`

프로젝트 목록 (메인 테이블)

```sql
SELECT
  p.id, p.project_code, p.project_name, p.project_status,
  p.first_shipment_date, p.last_shipment_date,
  c.company_name AS client_name,
  u.name AS cx_specialist,
  p.ordered_items_summary,
  p.created_at
FROM shared.projects p
LEFT JOIN shared.clients c ON c.id = p.client_id
LEFT JOIN shared.users u ON u.id = p.cx_specialist_id
ORDER BY p.first_shipment_date DESC;
```

### Query: `projects_update_status`

프로젝트 상태 변경 (버튼 클릭 → Run Query)

```sql
UPDATE shared.projects
SET project_status = {{ status_select.value }},
    updated_at = NOW()
WHERE id = {{ projects_table.selectedRow.id }};
```

> **Retool 설정:** `status_select` = Select 컴포넌트, 옵션: `planning`, `active`, `completed`, `on_hold`

---

## Page 3: Clients/Vendors

### Query: `clients_list`

거래처 목록

```sql
SELECT id, client_code, company_name, contact_name, contact_email, contact_phone, status
FROM shared.clients
ORDER BY company_name;
```

### Query: `vendors_list`

공급업체 목록

```sql
SELECT id, vendor_code, vendor_name, vendor_type, contact_name, contact_phone, status
FROM shared.vendors
ORDER BY vendor_type, vendor_name;
```

---

## Page 4: 발주/입하 (MM)

### Query: `po_list`

발주서 목록 (상단 테이블)

```sql
SELECT
  po.id, po.po_number, po.po_status,
  p.project_code, p.project_name,
  v.vendor_name,
  po.requested_date,
  COUNT(poi.id) AS line_count,
  SUM(poi.order_qty) AS total_order_qty,
  SUM(poi.total_amount) AS total_amount
FROM mm.purchase_orders po
JOIN shared.projects p ON p.id = po.project_id
JOIN shared.vendors v ON v.id = po.vendor_id
LEFT JOIN mm.purchase_order_items poi ON poi.po_id = po.id
GROUP BY po.id, po.po_number, po.po_status, p.project_code, p.project_name, v.vendor_name, po.requested_date
ORDER BY po.requested_date DESC;
```

### Query: `po_items_detail`

발주 행 선택 시 하단 상세 테이블 로드

```sql
SELECT
  poi.id, poi.line_number, poi.parts_id,
  pm.parts_name, pm.parts_code,
  poi.order_qty, poi.received_qty,
  poi.unit_price, poi.total_amount,
  poi.planned_delivery_date, poi.quality_check_result
FROM mm.purchase_order_items poi
JOIN shared.parts_master pm ON pm.id = poi.parts_id
WHERE poi.po_id = {{ po_table.selectedRow.id }}
ORDER BY poi.line_number;
```

> **Retool 설정:** `po_table.selectedRow.id` 에서 자동 트리거

### Query: `gr_insert`

입하(GR) 등록 폼 제출 — **트리거 1번 발동** (finance 전표 자동생성)

```sql
INSERT INTO mm.goods_receipts (
  gr_number, po_id, po_item_id, parts_id, storage_bin_id,
  received_qty, accepted_qty, rejected_qty,
  unit_cost, total_cost, tax_invoice_no, vat_amount,
  actual_receipt_date, inspection_result, received_by
) VALUES (
  'GR-' || TO_CHAR(NOW(), 'YYYYMMDD') || '-' || LPAD(FLOOR(RANDOM()*9000+1000)::TEXT, 4, '0'),
  {{ gr_po_select.value }},
  {{ gr_po_item_select.value }},
  {{ gr_parts_id.value }},
  {{ gr_bin_select.value }},
  {{ gr_received_qty.value }},
  {{ gr_accepted_qty.value }},
  {{ gr_rejected_qty.value }},
  {{ gr_unit_cost.value }},
  {{ gr_received_qty.value }}::NUMERIC * {{ gr_unit_cost.value }}::NUMERIC,
  {{ gr_tax_invoice.value }},
  {{ gr_received_qty.value }}::NUMERIC * {{ gr_unit_cost.value }}::NUMERIC * 0.1,
  {{ gr_receipt_date.value }},
  {{ gr_inspection_result.value }},
  {{ current_user_id.value }}
);
-- ↑ 이 INSERT 후 finance.accounting_entries draft 전표 자동생성 (트리거 1번 발동)
```

> **트리거 1:** `mm.goods_receipts` INSERT → `finance.accounting_entries` draft 생성
> DR: 146000 원재료 / CR: 252000 외상매입금

---

## Page 5: 재고/창고 (WMS)

### Query: `quants_current_stock`

현재 재고 현황 (Quants 테이블)

```sql
SELECT
  q.id,
  pm.parts_code, pm.parts_name, pm.parts_type,
  wb.bin_code,
  wh.warehouse_name,
  q.physical_qty, q.system_qty,
  q.stock_type, q.verification_status
FROM wms.quants q
JOIN shared.parts_master pm ON pm.id = q.parts_id
JOIN wms.storage_bins wb ON wb.id = q.storage_bin_id
JOIN wms.warehouses wh ON wh.id = wb.warehouse_id
ORDER BY pm.parts_name, wb.bin_code;
```

### Query: `inventory_adjustment_approve`

재고 실사 조정 승인 — **트리거 6번 발동** (재고조정 전표 자동생성)

```sql
UPDATE wms.inventory_count_items
SET
  adjustment_approved = TRUE,
  approved_by = {{ current_user_id.value }},
  processed_at = NOW()
WHERE id = {{ inventory_items_table.selectedRow.id }};
-- ↑ adjustment_approved=TRUE 시 finance 재고조정 전표 자동생성 (트리거 6번 발동)
```

> **트리거 6:** `adjustment_approved = TRUE` → `finance.accounting_entries` 생성
> DR: 484000 재고자산손실 / CR: 146000 원재료 (부족 시)

---

## Page 6: 임가공 (PP)

### Query: `production_orders_list`

생산 지시서 목록

```sql
SELECT
  po.id, po.order_number, po.status,
  p.project_code, p.project_name,
  po.planned_start_date, po.planned_end_date,
  po.actual_start_date, po.actual_end_date,
  po.planned_qty, po.actual_qty, po.output_qty,
  po.production_location,
  u.name AS cx_responsible
FROM pp.production_orders po
JOIN shared.projects p ON p.id = po.project_id
LEFT JOIN shared.users u ON u.id = po.cx_responsible_id
ORDER BY po.planned_start_date DESC;
```

### Query: `production_order_update_status`

생산 지시서 상태 변경

```sql
UPDATE pp.production_orders
SET status = {{ prod_status_select.value }},
    updated_at = NOW()
WHERE id = {{ prod_table.selectedRow.id }};
```

> **Retool 설정:** `prod_status_select` 옵션: `planned`, `in_progress`, `completed`, `cancelled`

---

## Page 7: 출하/물류 (TMS)

### Query: `freight_orders_list`

화물 주문 목록

```sql
SELECT
  fo.id, fo.fo_number, fo.shipping_status, fo.billing_status,
  tr.tr_number,
  p.project_code, p.project_name,
  c.company_name AS client_name,
  fo.planned_shipment_date, fo.confirmed_shipment_date,
  fo.total_cbm, fo.freight_cost,
  fo.tax_invoice_no,
  ca.carrier_name
FROM tms.freight_orders fo
JOIN tms.transportation_requirements tr ON tr.id = fo.tr_id
JOIN shared.projects p ON p.id = tr.project_id
JOIN shared.clients c ON c.id = p.client_id
LEFT JOIN tms.carriers ca ON ca.id = fo.carrier_id
ORDER BY fo.planned_shipment_date DESC;
```

### Query: `freight_order_mark_billed`

운임 청구 처리 — **트리거 5번 발동** (운반비 전표 자동생성)

```sql
UPDATE tms.freight_orders
SET billing_status = 'billed',
    updated_at = NOW()
WHERE id = {{ fo_table.selectedRow.id }};
-- ↑ billing_status='billed' 전환 시 운반비 전표 자동생성 (트리거 5번 발동)
-- DR: 831000 운반비 / CR: 253000 미지급금
```

> **트리거 5:** `billing_status = 'billed'` → `finance.accounting_entries` 생성
> DR: 831000 운반비 / CR: 253000 미지급금

---

## Page 8: 전표/더존 (Finance)

### Query: `accounting_entries_list`

전표 목록 (전체 조회)

```sql
SELECT
  ae.id, ae.entry_number, ae.entry_date, ae.entry_type,
  ae.amount, ae.status, ae.source_table,
  dr.account_name AS debit_account, dr.account_code AS debit_code,
  cr.account_name AS credit_account, cr.account_code AS credit_code,
  ae.tax_invoice_no, ae.vat_amount,
  ae.reviewed_at, ae.douzone_slip_no,
  ae.created_at
FROM finance.accounting_entries ae
JOIN shared.gl_accounts dr ON dr.id = ae.debit_account_id
JOIN shared.gl_accounts cr ON cr.id = ae.credit_account_id
ORDER BY ae.entry_date DESC, ae.created_at DESC;
```

### Query: `entry_mark_reviewed`

전표 검토 완료 처리 (draft → reviewed)

```sql
UPDATE finance.accounting_entries
SET
  status = 'reviewed',
  reviewed_by = {{ current_user_id.value }},
  reviewed_at = NOW()
WHERE id = {{ entries_table.selectedRow.id }}
  AND status = 'draft';
```

### Query: `entry_post_with_douzone`

더존 전표번호 입력 후 확정 처리 (reviewed → posted)

```sql
UPDATE finance.accounting_entries
SET
  status = 'posted',
  douzone_slip_no = {{ slip_no_input.value }}
WHERE id = {{ entries_table.selectedRow.id }}
  AND status = 'reviewed';
```

> **Retool 설정:** `slip_no_input` = Text Input 컴포넌트, 더존 전표번호 직접 입력

### Query: `entry_revert_to_draft`

검토 취소 (reviewed → draft, 수정 필요시)

```sql
UPDATE finance.accounting_entries
SET
  status = 'draft',
  reviewed_by = NULL,
  reviewed_at = NULL
WHERE id = {{ entries_table.selectedRow.id }}
  AND status = 'reviewed';
```

---

## Page 9: 워크플로우 추적기

### Query: `workflow_tracker`

프로젝트 선택 → 전체 흐름 타임라인 (단일 프로젝트)

```sql
SELECT
  -- 프로젝트
  p.project_code, p.project_name, p.project_status,
  p.first_shipment_date,
  c.company_name AS client_name,
  -- 발주
  po.po_number, po.po_status, po.requested_date,
  -- 입하
  gr.gr_number, gr.actual_receipt_date,
  gr.received_qty, gr.rejected_qty, gr.unit_cost,
  -- 재고이동
  sm.movement_type, sm.actual_qty, sm.actual_date,
  -- 임가공
  prod.order_number AS prod_order_number,
  prod.status AS prod_status,
  prod.actual_start_date, prod.actual_end_date,
  -- 출하
  fo.fo_number, fo.shipping_status, fo.freight_cost,
  fo.planned_shipment_date,
  -- 전표
  ae.entry_number, ae.entry_type, ae.amount,
  ae.status AS entry_status, ae.entry_date,
  dr.account_name AS debit_account,
  cr.account_name AS credit_account
FROM shared.projects p
LEFT JOIN shared.clients c ON c.id = p.client_id
LEFT JOIN mm.purchase_orders po ON po.project_id = p.id
LEFT JOIN mm.goods_receipts gr ON gr.po_id = po.id
LEFT JOIN mm.stock_movements sm ON sm.gr_id = gr.id
  AND sm.movement_type = 'goods_receipt'
LEFT JOIN pp.production_orders prod ON prod.project_id = p.id
LEFT JOIN tms.transportation_requirements tr ON tr.project_id = p.id
LEFT JOIN tms.freight_orders fo ON fo.tr_id = tr.id
LEFT JOIN finance.accounting_entries ae ON ae.source_id = gr.id
  AND ae.source_table = 'mm.goods_receipts'
LEFT JOIN shared.gl_accounts dr ON dr.id = ae.debit_account_id
LEFT JOIN shared.gl_accounts cr ON cr.id = ae.credit_account_id
WHERE p.id = {{ project_selector.value }}
ORDER BY gr.actual_receipt_date NULLS LAST, ae.entry_date NULLS LAST;
```

### Query: `workflow_all_entries_for_project`

선택 프로젝트의 전표 전체 조회 (모든 entry_type 포함)

```sql
SELECT
  ae.entry_number, ae.entry_date, ae.entry_type,
  ae.amount, ae.status,
  ae.source_table, ae.source_id,
  dr.account_name AS debit_account,
  cr.account_name AS credit_account,
  ae.tax_invoice_no
FROM finance.accounting_entries ae
JOIN shared.gl_accounts dr ON dr.id = ae.debit_account_id
JOIN shared.gl_accounts cr ON cr.id = ae.credit_account_id
WHERE ae.source_id IN (
  SELECT gr.id FROM mm.goods_receipts gr
  JOIN mm.purchase_orders po ON po.id = gr.po_id
  WHERE po.project_id = {{ project_selector.value }}
  UNION
  SELECT sm.id FROM mm.stock_movements sm
  JOIN mm.purchase_orders po ON po.id = sm.po_item_id
  WHERE po.project_id = {{ project_selector.value }}
  UNION
  SELECT fo.id FROM tms.freight_orders fo
  JOIN tms.transportation_requirements tr ON tr.id = fo.tr_id
  WHERE tr.project_id = {{ project_selector.value }}
)
ORDER BY ae.entry_date, ae.entry_type;
```

---

## Appendix: 유용한 유틸리티 쿼리

### Query: `util_project_dropdown`

워크플로우 추적기의 `project_selector` Select 컴포넌트 데이터 소스

```sql
SELECT
  id AS value,
  project_code || ' — ' || project_name AS label,
  project_status
FROM shared.projects
ORDER BY first_shipment_date DESC;
```

> **Retool 설정:** Select 컴포넌트 → Values: `id`, Labels: `project_code || ' — ' || project_name`

### Query: `util_trigger_check`

트리거 발동 결과 검증 — 전표 유형별 건수 확인

```sql
SELECT
  entry_type,
  status,
  COUNT(*) AS cnt,
  SUM(amount) AS total_amount,
  MAX(created_at) AS latest_created
FROM finance.accounting_entries
GROUP BY entry_type, status
ORDER BY entry_type, status;
```

### Query: `util_verify_gr_entries`

입하 전표 연결 검증 — GR과 전표 매핑 확인 (트리거 1번 결과 확인용)

```sql
SELECT
  gr.gr_number,
  gr.actual_receipt_date,
  gr.total_cost,
  ae.entry_number,
  ae.entry_type,
  ae.amount,
  ae.status,
  ae.created_at AS entry_created_at
FROM mm.goods_receipts gr
LEFT JOIN finance.accounting_entries ae
  ON ae.source_id = gr.id
  AND ae.source_table = 'mm.goods_receipts'
ORDER BY gr.actual_receipt_date DESC, gr.created_at DESC
LIMIT 50;
```

### Query: `util_pending_review_count`

검토 대기 중인 draft 전표 수 (대시보드 배지용)

```sql
SELECT COUNT(*) AS pending_count
FROM finance.accounting_entries
WHERE status = 'draft';
```

---

## 트리거 요약표

| 트리거 번호 | 발동 조건 | 생성 전표 유형 | 차변 계정 | 대변 계정 |
|:-----------:|-----------|---------------|-----------|-----------|
| 1 | `mm.goods_receipts` INSERT | `goods_receipt` | 146000 원재료 | 252000 외상매입금 |
| 2 | `mm.stock_movements` 출고 | `stock_issue` | 451000 제조원가 | 146000 원재료 |
| 3 | `pp.production_orders` 완료 | `production_output` | 167000 반제품 | 451000 제조원가 |
| 4 | 출고 확정 (출하) | `goods_issue` | 401000 매출원가 | 167000 반제품 |
| 5 | `tms.freight_orders` billed | `freight_cost` | 831000 운반비 | 253000 미지급금 |
| 6 | `adjustment_approved = TRUE` | `inventory_adjustment` | 484000 재고자산손실 | 146000 원재료 |

---

*최종 업데이트: 2026-03-27*
