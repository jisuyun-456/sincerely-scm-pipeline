# SCM SSOT Retool 쿼리 모음

> **앱명:** SSOT-SAP
> **리소스:** postgres (Supabase pooler:6543)
> **네이밍 규칙:** 모든 쿼리명은 `q_` prefix 사용
> **변수 참조:** `{{ component_name.value }}` 형식
> **최종 동기화:** 2026-03-31 — retool_page_setup.md 기준 통일

---

## 목차

1. [Page 1: dashboard](#page-1-dashboard)
2. [Page 2: project_detail](#page-2-project_detail)
3. [Page 3: purchase_orders](#page-3-purchase_orders)
4. [Page 4: goods_receipt](#page-4-goods_receipt)
5. [Page 5: inventory](#page-5-inventory)
6. [Page 6: production](#page-6-production)
7. [Page 7: delivery](#page-7-delivery)
8. [Page 8: finance](#page-8-finance)
9. [Page 9: master_data](#page-9-master_data)
10. [CRUD 뮤테이션 쿼리 (미등록)](#crud-뮤테이션-쿼리-미등록)
11. [워크플로우 추적기 (미등록)](#워크플로우-추적기-미등록)
12. [유틸리티 쿼리](#appendix-유틸리티-쿼리)
13. [트리거 요약표](#트리거-요약표)

---

## Page 1: dashboard

### `q_kpi`

프로젝트 KPI 카드 (총/진행중/완료)

```sql
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE project_status = 'active') AS active,
  COUNT(*) FILTER (WHERE project_status = 'completed') AS completed
FROM shared.projects;
```

### `q_shipping_this_month`

이번달 출하 건수

```sql
SELECT COUNT(*) AS cnt
FROM tms.transportation_requirements
WHERE requested_shipment_date >= date_trunc('month', CURRENT_DATE)
  AND requested_shipment_date < date_trunc('month', CURRENT_DATE) + INTERVAL '1 month';
```

### `q_projects_list`

프로젝트 목록 (메인 테이블)

```sql
SELECT
  p.id,
  p.project_code,
  p.project_name,
  c.company_name,
  p.project_status,
  u.name AS cx_specialist,
  p.first_shipment_date,
  p.fulfillment_lead_time
FROM shared.projects p
JOIN shared.clients c ON c.id = p.client_id
LEFT JOIN shared.users u ON u.id = p.cx_specialist_id
ORDER BY p.project_code DESC;
```

> 행 클릭 → Navigate to `project_detail`, URL param: `project_id={{ tbl_projects.selectedRow.data.id }}`

---

## Page 2: project_detail

### `q_project_info`

프로젝트 헤더 정보

```sql
SELECT
  p.project_code,
  p.project_name,
  p.project_status,
  p.main_usage,
  c.company_name,
  u.name AS cx_specialist,
  p.first_shipment_date,
  p.last_shipment_date,
  p.fulfillment_lead_time,
  p.ordered_items_summary
FROM shared.projects p
JOIN shared.clients c ON c.id = p.client_id
LEFT JOIN shared.users u ON u.id = p.cx_specialist_id
WHERE p.id = {{ urlparams.project_id }};
```

### `q_project_pos` (발주 탭)

```sql
SELECT
  po.po_number,
  v.vendor_name,
  po.po_status,
  po.requested_date,
  poi.line_number,
  pt.parts_name,
  poi.order_qty,
  poi.unit_price,
  poi.total_amount,
  COALESCE(poi.received_qty, 0) AS received_qty
FROM mm.purchase_orders po
JOIN shared.vendors v ON v.id = po.vendor_id
LEFT JOIN mm.purchase_order_items poi ON poi.po_id = po.id
LEFT JOIN shared.parts_master pt ON pt.id = poi.parts_id
WHERE po.project_id = {{ urlparams.project_id }}
ORDER BY po.requested_date, poi.line_number;
```

### `q_project_grs` (입고 탭)

```sql
SELECT
  gr.gr_number,
  pt.parts_name,
  gr.received_qty,
  gr.accepted_qty,
  gr.rejected_qty,
  gr.unit_cost,
  gr.total_cost,
  gr.actual_receipt_date,
  gr.inspection_result
FROM mm.goods_receipts gr
JOIN mm.purchase_orders po ON po.id = gr.po_id
JOIN shared.parts_master pt ON pt.id = gr.parts_id
WHERE po.project_id = {{ urlparams.project_id }}
ORDER BY gr.actual_receipt_date;
```

### `q_project_production` (생산 탭)

```sql
SELECT
  pro.order_number,
  pro.status,
  pro.planned_start_date,
  pro.planned_end_date,
  pro.actual_start_date,
  pro.actual_end_date,
  pro.planned_qty,
  pro.actual_qty,
  pro.output_qty,
  CASE WHEN pro.planned_qty > 0
    THEN ROUND(COALESCE(pro.output_qty, 0)::numeric / pro.planned_qty * 100)
    ELSE 0
  END AS progress_pct
FROM pp.production_orders pro
WHERE pro.project_id = {{ urlparams.project_id }}
ORDER BY pro.planned_start_date;
```

### `q_project_delivery` (배송 탭)

```sql
SELECT
  tr.tr_number,
  tr.delivery_type,
  tr.recipient_name,
  tr.recipient_address,
  tr.status AS tr_status,
  tr.requested_shipment_date,
  fo.fo_number,
  fo.shipping_status,
  cr.carrier_name,
  fo.actual_departure_datetime,
  fo.actual_arrival_datetime,
  fo.freight_cost
FROM tms.transportation_requirements tr
LEFT JOIN tms.freight_orders fo ON fo.tr_id = tr.id
LEFT JOIN tms.carriers cr ON cr.id = fo.carrier_id
WHERE tr.project_id = {{ urlparams.project_id }}
ORDER BY tr.requested_shipment_date;
```

---

## Page 3: purchase_orders

### `q_po_list`

```sql
SELECT
  po.id,
  po.po_number,
  p.project_code,
  p.project_name,
  v.vendor_name,
  po.po_status,
  po.requested_date,
  SUM(poi.total_amount) AS total_amount
FROM mm.purchase_orders po
JOIN shared.projects p ON p.id = po.project_id
JOIN shared.vendors v ON v.id = po.vendor_id
LEFT JOIN mm.purchase_order_items poi ON poi.po_id = po.id
GROUP BY po.id, p.project_code, p.project_name, v.vendor_name
ORDER BY po.requested_date DESC;
```

### `q_po_items` (PO 선택 시)

```sql
SELECT
  poi.line_number,
  pt.parts_code,
  pt.parts_name,
  poi.order_qty,
  COALESCE(poi.received_qty, 0) AS received_qty,
  poi.unit_price,
  poi.total_amount,
  poi.quality_check_result
FROM mm.purchase_order_items poi
JOIN shared.parts_master pt ON pt.id = poi.parts_id
WHERE poi.po_id = {{ tbl_po.selectedRow.data.id }}
ORDER BY poi.line_number;
```

---

## Page 4: goods_receipt

### `q_gr_list`

```sql
SELECT
  gr.gr_number,
  po.po_number,
  pt.parts_name,
  gr.received_qty,
  gr.accepted_qty,
  gr.rejected_qty,
  gr.unit_cost,
  gr.total_cost,
  gr.actual_receipt_date,
  gr.inspection_result
FROM mm.goods_receipts gr
JOIN mm.purchase_orders po ON po.id = gr.po_id
JOIN shared.parts_master pt ON pt.id = gr.parts_id
ORDER BY gr.actual_receipt_date DESC;
```

### `q_pending_receipt` (입고 대기)

```sql
SELECT
  po.po_number,
  poi.line_number,
  pt.parts_code,
  pt.parts_name,
  poi.order_qty,
  COALESCE(poi.received_qty, 0) AS received_so_far,
  poi.order_qty - COALESCE(poi.received_qty, 0) AS remaining,
  po.requested_date,
  v.vendor_name
FROM mm.purchase_order_items poi
JOIN mm.purchase_orders po ON po.id = poi.po_id
JOIN shared.parts_master pt ON pt.id = poi.parts_id
JOIN shared.vendors v ON v.id = po.vendor_id
WHERE po.po_status NOT IN ('closed', 'cancelled')
  AND poi.order_qty > COALESCE(poi.received_qty, 0)
ORDER BY po.requested_date;
```

### `q_returns` (반품)

```sql
SELECT
  ro.return_number,
  ro.direction,
  CASE ro.direction
    WHEN 'vendor' THEN '공급업체 반품'
    WHEN 'customer' THEN '고객 반품'
  END AS dir_label,
  pt.parts_name,
  ro.return_qty,
  ro.reason_code,
  ro.disposition,
  ro.status
FROM mm.return_orders ro
JOIN shared.parts_master pt ON pt.id = ro.parts_id
ORDER BY ro.created_at DESC;
```

---

## Page 5: inventory

### `q_inventory`

```sql
SELECT
  pt.parts_code,
  pt.parts_name,
  w.warehouse_code,
  sb.bin_code,
  sb.zone,
  q.stock_type,
  q.physical_qty,
  q.reserved_qty,
  q.available_qty,
  b.batch_number,
  b.unit_cost,
  q.physical_qty * COALESCE(b.unit_cost, 0) AS stock_value
FROM wms.quants q
JOIN shared.parts_master pt ON pt.id = q.parts_id
JOIN wms.storage_bins sb ON sb.id = q.storage_bin_id
JOIN wms.warehouses w ON w.id = sb.warehouse_id
LEFT JOIN wms.batches b ON b.id = q.batch_id
ORDER BY pt.parts_code, sb.bin_code;
```

### `q_negative_stock` (음수 재고 경고)

```sql
SELECT
  pt.parts_code,
  pt.parts_name,
  w.warehouse_code,
  q.physical_qty
FROM wms.quants q
JOIN shared.parts_master pt ON pt.id = q.parts_id
JOIN wms.storage_bins sb ON sb.id = q.storage_bin_id
JOIN wms.warehouses w ON w.id = sb.warehouse_id
WHERE q.physical_qty < 0;
```

### `q_stock_movements`

```sql
SELECT
  sm.movement_number,
  sm.movement_type,
  CASE sm.movement_type
    WHEN '101' THEN '입고'
    WHEN '102' THEN '입고취소'
    WHEN '161' THEN '고객반품'
    WHEN '201' THEN '출고'
    WHEN '261' THEN '생산출고'
    WHEN '262' THEN '생산반품'
    WHEN '301' THEN '창고이전'
    WHEN '551' THEN '폐기'
    WHEN '601' THEN '납품출고'
    WHEN '701' THEN '실사(+)'
    WHEN '702' THEN '실사(-)'
  END AS type_label,
  pt.parts_name,
  sm.actual_qty,
  sm.unit_cost_at_movement,
  sm.posting_date,
  sm.status,
  sm.is_reversal
FROM mm.stock_movements sm
JOIN shared.parts_master pt ON pt.id = sm.parts_id
ORDER BY sm.posting_date DESC;
```

---

## Page 6: production

### `q_production_orders`

```sql
SELECT
  pro.id,
  pro.order_number,
  pro.status,
  p.project_code,
  p.project_name,
  pro.planned_start_date,
  pro.planned_end_date,
  pro.actual_start_date,
  pro.actual_end_date,
  pro.planned_qty,
  pro.actual_qty,
  pro.output_qty,
  CASE WHEN pro.planned_qty > 0
    THEN ROUND(COALESCE(pro.output_qty, 0)::numeric / pro.planned_qty * 100)
    ELSE 0
  END AS progress_pct
FROM pp.production_orders pro
JOIN shared.projects p ON p.id = pro.project_id
ORDER BY
  CASE pro.status
    WHEN 'in_progress' THEN 1
    WHEN 'released' THEN 2
    WHEN 'planned' THEN 3
    WHEN 'completed' THEN 4
    ELSE 5
  END;
```

### `q_bom_components` (선택한 생산오더의 BOM)

```sql
SELECT
  pt.parts_code,
  pt.parts_name,
  bi.component_qty AS qty_per_unit,
  bi.component_qty * pro.planned_qty AS total_required,
  COALESCE(poc.issued_qty, 0) AS issued,
  bi.component_qty * pro.planned_qty - COALESCE(poc.issued_qty, 0) AS remaining,
  COALESCE(stock.available, 0) AS current_stock
FROM pp.bom_items bi
JOIN shared.parts_master pt ON pt.id = bi.parts_id
JOIN pp.production_orders pro ON pro.bom_id = bi.bom_id
LEFT JOIN pp.production_order_components poc
  ON poc.production_order_id = pro.id AND poc.parts_id = bi.parts_id
LEFT JOIN (
  SELECT parts_id, SUM(available_qty) AS available
  FROM wms.quants GROUP BY parts_id
) stock ON stock.parts_id = bi.parts_id
WHERE pro.id = {{ tbl_production.selectedRow.data.id }};
```

---

## Page 7: delivery

### `q_transport_requests`

```sql
SELECT
  tr.tr_number,
  p.project_code,
  p.project_name,
  tr.delivery_type,
  CASE tr.delivery_type
    WHEN 'direct' THEN '직납'
    WHEN 'courier' THEN '택배'
    WHEN 'relay'  THEN '릴레이'
    WHEN 'pickup' THEN '픽업'
    WHEN 'transfer' THEN '이전'
  END AS type_label,
  tr.recipient_name,
  tr.recipient_address,
  tr.requested_shipment_date,
  tr.status
FROM tms.transportation_requirements tr
JOIN shared.projects p ON p.id = tr.project_id
ORDER BY tr.requested_shipment_date DESC;
```

### `q_freight_orders`

```sql
SELECT
  fo.fo_number,
  tr.tr_number,
  cr.carrier_name,
  cr.carrier_type,
  fo.planned_shipment_date,
  fo.confirmed_shipment_date,
  fo.actual_departure_datetime,
  fo.actual_arrival_datetime,
  fo.shipping_status,
  fo.total_cbm,
  fo.freight_cost,
  fo.tracking_number
FROM tms.freight_orders fo
JOIN tms.transportation_requirements tr ON tr.id = fo.tr_id
JOIN tms.carriers cr ON cr.id = fo.carrier_id
ORDER BY fo.planned_shipment_date DESC;
```

---

## Page 8: finance

### `q_journal_entries`

```sql
SELECT
  ae.entry_number,
  ae.entry_date,
  ae.entry_type,
  CASE ae.entry_type
    WHEN 'goods_receipt'        THEN '입고'
    WHEN 'goods_issue'          THEN '출고'
    WHEN 'production'           THEN '생산'
    WHEN 'assembly_issue'       THEN '조립출고'
    WHEN 'assembly_receipt'     THEN '조립입고'
    WHEN 'purchase_invoice'     THEN '매입'
    WHEN 'freight'              THEN '운임'
    WHEN 'inventory_adjustment' THEN '재고조정'
  END AS type_label,
  da.account_code || ' ' || da.account_name AS debit_account,
  ca.account_code || ' ' || ca.account_name AS credit_account,
  ae.amount,
  ae.status,
  ae.is_reversal,
  ae.douzone_slip_no
FROM finance.accounting_entries ae
JOIN shared.gl_accounts da ON da.id = ae.debit_account_id
JOIN shared.gl_accounts ca ON ca.id = ae.credit_account_id
ORDER BY ae.entry_date DESC, ae.entry_number DESC;
```

### `q_period_closes`

```sql
SELECT
  pc.period,
  pt.parts_code,
  pt.parts_name,
  w.warehouse_code,
  pc.closing_qty,
  pc.closing_value,
  pc.unit_cost,
  pc.is_closed
FROM finance.period_closes pc
JOIN shared.parts_master pt ON pt.id = pc.parts_id
JOIN wms.warehouses w ON w.id = pc.warehouse_id
ORDER BY pc.period DESC, pt.parts_code;
```

---

## Page 9: master_data

### `q_clients`

```sql
SELECT
  client_code,
  company_name,
  business_reg_number,
  contact_name,
  contact_email,
  contact_phone,
  status
FROM shared.clients
ORDER BY client_code;
```

### `q_vendors`

```sql
SELECT
  vendor_code,
  vendor_name,
  vendor_type,
  douzone_vendor_code,
  is_stock_vendor,
  contact_name,
  contact_phone,
  email,
  status
FROM shared.vendors
ORDER BY vendor_code;
```

### `q_parts`

```sql
SELECT
  pt.parts_code,
  pt.parts_name,
  mt.type_code AS material_type,
  mg.group_code AS material_group,
  v.vendor_name AS default_vendor,
  pt.base_uom,
  pt.reorder_point,
  pt.min_order_qty,
  pt.status
FROM shared.parts_master pt
LEFT JOIN shared.material_types mt ON mt.id = pt.material_type_id
LEFT JOIN shared.material_groups mg ON mg.id = pt.material_group_id
LEFT JOIN shared.vendors v ON v.id = pt.vendor_id
ORDER BY pt.parts_code;
```

### `q_bom`

```sql
SELECT
  bh.bom_code,
  bh.bom_type,
  COALESCE(g.goods_name, i.item_name) AS product_name,
  bi.component_qty,
  pt.parts_code,
  pt.parts_name
FROM pp.bom_headers bh
LEFT JOIN shared.goods_master g ON g.id = bh.goods_id
LEFT JOIN shared.item_master i ON i.id = bh.item_id
JOIN pp.bom_items bi ON bi.bom_id = bh.id
JOIN shared.parts_master pt ON pt.id = bi.parts_id
ORDER BY bh.bom_code, bi.sort_order;
```

### `q_warehouses`

```sql
SELECT
  w.warehouse_code,
  w.warehouse_name,
  w.address,
  w.max_cbm,
  w.status,
  COUNT(sb.id) AS bin_count
FROM wms.warehouses w
LEFT JOIN wms.storage_bins sb ON sb.warehouse_id = w.id
GROUP BY w.id
ORDER BY w.warehouse_code;
```

---

## CRUD 뮤테이션 쿼리 (미등록)

> 아래 쿼리들은 Retool에 아직 등록되지 않음. 데이터 입력/수정 기능 추가 시 등록할 것.

### `q_pending_entries` — Dashboard 미처리 전표 현황 카드

```sql
SELECT
  status,
  COUNT(*) as cnt,
  SUM(amount) as total_amount
FROM finance.accounting_entries
GROUP BY status
ORDER BY status;
```

> Dashboard에 Stat 카드로 추가 권장

### `q_project_update_status` — 프로젝트 상태 변경

```sql
UPDATE shared.projects
SET project_status = {{ status_select.value }},
    updated_at = NOW()
WHERE id = {{ projects_table.selectedRow.id }};
```

> Retool 설정: `status_select` = Select 컴포넌트, 옵션: `planning`, `active`, `completed`, `on_hold`

### `q_gr_insert` — 입하(GR) 등록 (트리거 1번 발동)

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
```

> 트리거 1: `mm.goods_receipts` INSERT → `finance.accounting_entries` draft 생성
> DR: 146000 원재료 / CR: 252000 외상매입금

### `q_inventory_adjustment_approve` — 재고 실사 조정 승인 (트리거 6번 발동)

```sql
UPDATE wms.inventory_count_items
SET
  adjustment_approved = TRUE,
  approved_by = {{ current_user_id.value }},
  processed_at = NOW()
WHERE id = {{ inventory_items_table.selectedRow.id }};
```

> 트리거 6: `adjustment_approved = TRUE` → 재고조정 전표 자동생성
> DR: 484000 재고자산손실 / CR: 146000 원재료 (부족 시)

### `q_production_update_status` — 생산 상태 변경

```sql
UPDATE pp.production_orders
SET status = {{ prod_status_select.value }},
    updated_at = NOW()
WHERE id = {{ prod_table.selectedRow.id }};
```

> Retool 설정: `prod_status_select` 옵션: `planned`, `in_progress`, `completed`, `cancelled`

### `q_freight_mark_billed` — 운임 청구 처리 (트리거 5번 발동)

```sql
UPDATE tms.freight_orders
SET billing_status = 'billed',
    updated_at = NOW()
WHERE id = {{ fo_table.selectedRow.id }};
```

> 트리거 5: `billing_status = 'billed'` → 운반비 전표 자동생성
> DR: 831000 운반비 / CR: 253000 미지급금

### `q_entry_mark_reviewed` — 전표 검토 완료 (draft → reviewed)

```sql
UPDATE finance.accounting_entries
SET
  status = 'reviewed',
  reviewed_by = {{ current_user_id.value }},
  reviewed_at = NOW()
WHERE id = {{ entries_table.selectedRow.id }}
  AND status = 'draft';
```

### `q_entry_post_douzone` — 더존 전표번호 입력 확정 (reviewed → posted)

```sql
UPDATE finance.accounting_entries
SET
  status = 'posted',
  douzone_slip_no = {{ slip_no_input.value }}
WHERE id = {{ entries_table.selectedRow.id }}
  AND status = 'reviewed';
```

> Retool 설정: `slip_no_input` = Text Input, 더존 전표번호 직접 입력

### `q_entry_revert_draft` — 검토 취소 (reviewed → draft)

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

## 워크플로우 추적기 (미등록)

> 향후 별도 페이지 또는 project_detail 하위 탭으로 추가 예정

### `q_workflow_tracker` — 프로젝트별 전체 흐름 타임라인

```sql
SELECT
  p.project_code, p.project_name, p.project_status,
  p.first_shipment_date,
  c.company_name AS client_name,
  po.po_number, po.po_status, po.requested_date,
  gr.gr_number, gr.actual_receipt_date,
  gr.received_qty, gr.rejected_qty, gr.unit_cost,
  sm.movement_type, sm.actual_qty, sm.actual_date,
  prod.order_number AS prod_order_number,
  prod.status AS prod_status,
  prod.actual_start_date, prod.actual_end_date,
  fo.fo_number, fo.shipping_status, fo.freight_cost,
  fo.planned_shipment_date,
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

### `q_workflow_project_entries` — 프로젝트 전표 전체 조회

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

## Appendix: 유틸리티 쿼리

### `q_util_project_dropdown` — 프로젝트 셀렉트 드롭다운

```sql
SELECT
  id AS value,
  project_code || ' — ' || project_name AS label,
  project_status
FROM shared.projects
ORDER BY first_shipment_date DESC;
```

> Retool 설정: Select 컴포넌트 → Values: `id`, Labels: `project_code || ' — ' || project_name`

### `q_util_trigger_check` — 트리거 발동 결과 검증

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

### `q_util_verify_gr_entries` — GR-전표 매핑 확인

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

### `q_util_pending_review_count` — draft 전표 카운트 (대시보드 배지용)

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

*최종 업데이트: 2026-03-31 — retool_page_setup.md 기준 통일*
