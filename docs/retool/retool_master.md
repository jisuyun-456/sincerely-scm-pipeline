# Retool SCM Master Guide

> **앱명:** SSOT-SAP  
> **리소스:** postgres (Supabase Transaction Pooler :6543)  
> **최종 검증:** 2026-03-30  
> **통합 출처:** retool_page_setup.md + retool_setup_guide.md + retool_ui_layout.md  
> **스키마 매핑:** [retool_supabase_mapping.md](retool_supabase_mapping.md) — 10페이지 ↔ 6스키마 51테이블 매핑

---

## 1. 연결 설정

### Step 1: PostgreSQL Resource 생성

Retool → Settings → Resources → **+ New Resource** → **PostgreSQL**

| 항목 | 값 |
|------|-----|
| **Name** | `postgres` |
| **Host** | `aws-1-ap-south-1.pooler.supabase.com` |
| **Port** | `6543` (Transaction Pooler) |
| **Database** | `postgres` |
| **Username** | `postgres.aigykrijhgjxqludjqed` |
| **Password** | Supabase 대시보드 확인 |
| **SSL** | Required |

> ⚠️ Direct Connection(`5432`) 아닌 **Transaction Pooler(`6543`)** 사용

### Step 2: 연결 테스트

```sql
SELECT schemaname, COUNT(*) AS table_count
FROM pg_tables
WHERE schemaname IN ('shared','mm','wms','tms','pp','finance')
GROUP BY schemaname ORDER BY schemaname;
```
예상 결과: 6개 스키마, 총 51개 테이블

---

## 2. 앱 아키텍처 개요

### 10페이지 구조

| # | 페이지명 | 역할 | 쿼리 수 |
|---|---------|------|---------|
| 1 | dashboard | 프로젝트 대시보드 | 3 |
| 2 | project_detail | 프로젝트 상세 (탭) | 6 |
| 3 | purchase_orders | 구매/발주 | 2 |
| 4 | goods_receipt | 입고/검수 | 3 |
| 5 | inventory | 창고/재고 | 3 |
| 6 | production | 생산/조립 | 2 |
| 7 | delivery | 배송/물류 | 2 |
| 8 | finance | 회계/전표 | 2 |
| 9 | master_data | 마스터 데이터 | 5 |
| 10 | workflow | 워크플로우 추적기 | 2 |

---

## 3. 페이지별 상세

---

### Page 1: Dashboard

#### 와이어프레임
```
┌─────────────────────────────────────────────────────────┐
│  [Stat] 총 프로젝트   [Stat] 진행중   [Stat] 완료   [Stat] 이번달 배송  │
│    25                  20              5              1                │
├─────────────────────────────────────────────────────────┤
│  ┌─ tbl_projects ──────────────────────────────────────────────┐     │
│  │ 프로젝트코드 │ 프로젝트명 │ 고객사 │ 상태 │ 담당 │ 첫출고일 │ 리드타임 │     │
│  │ PRJ-025     │ 프리비알.. │ 프리비알│active│ 우예림│ Apr 1   │ 7      │     │
│  └──────────────────────────────────────── Showing 1-20 of 25 ┘     │
│  ┌─ status_select ─┐  ┌─ 상태 변경 ─┐                                │
│  │ planning ▼      │  │   [Button]  │                                │
│  └─────────────────┘  └────────────┘                                │
└─────────────────────────────────────────────────────────┘
```

#### 컴포넌트
- `statistic1`~`statistic4`: KPI 카드 (총/진행중/완료/이번달 배송)
- `tbl_projects`: 프로젝트 목록 (Data: `q_projects_list`)
  - 행 클릭 → Navigate to `project_detail`, URL param: `project_id={{ tbl_projects.selectedRow.data.id }}`
- `select1` (status_select): Manual (planning/active/completed/on_hold)
- `button1`: 상태 변경 → `q_project_update_status`

#### SQL 쿼리

**q_kpi**
```sql
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE project_status = 'active') AS active,
  COUNT(*) FILTER (WHERE project_status = 'completed') AS completed
FROM shared.projects;
```

**q_shipping_this_month**
```sql
SELECT COUNT(*) AS cnt
FROM tms.transportation_requirements
WHERE requested_shipment_date >= date_trunc('month', CURRENT_DATE)
  AND requested_shipment_date < date_trunc('month', CURRENT_DATE) + INTERVAL '1 month';
```

**q_projects_list**
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

---

### Page 2: Project Detail

#### 와이어프레임
```
┌─────────────────────────────────────────────────────────┐
│  ### PRJ-2026-025 · 프리비알 VIP 이벤트 150세트                       │
│  고객: 프리비알 | 상태: active | 담당: 우예림                          │
├─────────────────────────────────────────────────────────┤
│  ┌─ select_project ──────────────────┐                               │
│  │ PRJ-2026-025 · 프리비알 VIP... ▼  │                               │
│  └───────────────────────────────────┘                               │
├─────────────────────────────────────────────────────────┤
│  ┌─ tabbedContainer1 ──────────────────────────────────────────┐    │
│  │ [ 발주 ] [ 입고 ] [ 생산 ] [ 배송 ]                          │    │
│  │  table1(발주) / table2(입고) / table3(생산) / table4(배송)   │    │
│  └──────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

#### 컴포넌트
- `text1`: 프로젝트 헤더 (q_project_info 바인딩)
- `select_project`: Mapped, Data: `q_all_projects`, Value: `{{ item.id }}`, Label: `{{ item.project_name }}`
  - onChange → Trigger: q_project_info, q_project_pos, q_project_grs, q_project_production, q_project_delivery
- `tabbedContainer1` (4탭):
  - 발주: `table1` (Data: `q_project_pos`)
  - 입고: `table2` (Data: `q_project_grs`)
  - 생산: `table3` (Data: `q_project_production`)
  - 배송: `table4` (Data: `q_project_delivery`)

#### SQL 쿼리

> **WHERE 패턴:** `{{ urlparams.project_id || select_project.value }}`

**q_project_info**
```sql
SELECT
  p.project_code, p.project_name, p.project_status, p.main_usage,
  c.company_name, u.name AS cx_specialist,
  p.first_shipment_date, p.last_shipment_date,
  p.fulfillment_lead_time, p.ordered_items_summary
FROM shared.projects p
JOIN shared.clients c ON c.id = p.client_id
LEFT JOIN shared.users u ON u.id = p.cx_specialist_id
WHERE p.id = {{ urlparams.project_id || select_project.value }};
```

**q_project_pos** (발주 탭)
```sql
SELECT
  po.po_number, v.vendor_name, po.po_status, po.requested_date,
  poi.line_number, pt.parts_name, poi.order_qty, poi.unit_price,
  poi.total_amount, COALESCE(poi.received_qty, 0) AS received_qty
FROM mm.purchase_orders po
JOIN shared.vendors v ON v.id = po.vendor_id
LEFT JOIN mm.purchase_order_items poi ON poi.po_id = po.id
LEFT JOIN shared.parts_master pt ON pt.id = poi.parts_id
WHERE po.project_id = {{ urlparams.project_id || select_project.value }}
ORDER BY po.requested_date, poi.line_number;
```

**q_project_grs** (입고 탭)
```sql
SELECT
  gr.gr_number, pt.parts_name, gr.received_qty, gr.accepted_qty,
  gr.rejected_qty, gr.unit_cost, gr.total_cost,
  gr.actual_receipt_date, gr.inspection_result
FROM mm.goods_receipts gr
JOIN mm.purchase_orders po ON po.id = gr.po_id
JOIN shared.parts_master pt ON pt.id = gr.parts_id
WHERE po.project_id = {{ urlparams.project_id || select_project.value }}
ORDER BY gr.actual_receipt_date;
```

**q_project_production** (생산 탭)
```sql
SELECT
  pro.order_number, pro.status, pro.planned_start_date, pro.planned_end_date,
  pro.actual_start_date, pro.actual_end_date, pro.planned_qty, pro.actual_qty,
  pro.output_qty,
  CASE WHEN pro.planned_qty > 0
    THEN ROUND(COALESCE(pro.output_qty, 0)::numeric / pro.planned_qty * 100)
    ELSE 0
  END AS progress_pct
FROM pp.production_orders pro
WHERE pro.project_id = {{ urlparams.project_id || select_project.value }}
ORDER BY pro.planned_start_date;
```

**q_project_delivery** (배송 탭)
```sql
SELECT
  tr.tr_number, tr.delivery_type, tr.recipient_name, tr.recipient_address,
  tr.status AS tr_status, tr.requested_shipment_date,
  fo.fo_number, fo.shipping_status, cr.carrier_name,
  fo.actual_departure_datetime, fo.actual_arrival_datetime, fo.freight_cost
FROM tms.transportation_requirements tr
LEFT JOIN tms.freight_orders fo ON fo.tr_id = tr.id
LEFT JOIN tms.carriers cr ON cr.id = fo.carrier_id
WHERE tr.project_id = {{ urlparams.project_id || select_project.value }}
ORDER BY tr.requested_shipment_date;
```

---

### Page 3: Purchase Orders (구매/발주)

#### 와이어프레임
```
┌──────────────────────────┬──────────────────────────────┐
│  ┌─ tbl_po (좌 6:6) ─────┐│  ┌─ tbl_po_items (우 6:6) ─┐│
│  │ PO번호│프로젝트│공급업체 ││  │ 라인│품목코드│품목명       ││
│  │ 상태  │요청일  │총액    ││  │ 발주수량│입고수량│단가│총액 ││
│  │                       ││  │ 검사결과                  ││
│  └───────────────────────┘│  └──────────────────────────┘│
└──────────────────────────┴──────────────────────────────┘
```

#### 컴포넌트
- `tbl_po`: Data: `q_po_list`, Primary key: `id`
  - Select row → Trigger `q_po_items`
- `tbl_po_items`: Data: `q_po_items`

#### SQL 쿼리

**q_po_list**
```sql
SELECT
  po.id, po.po_number, p.project_code, p.project_name,
  v.vendor_name, po.po_status, po.requested_date,
  SUM(poi.total_amount) AS total_amount
FROM mm.purchase_orders po
JOIN shared.projects p ON p.id = po.project_id
JOIN shared.vendors v ON v.id = po.vendor_id
LEFT JOIN mm.purchase_order_items poi ON poi.po_id = po.id
GROUP BY po.id, p.project_code, p.project_name, v.vendor_name
ORDER BY po.requested_date DESC;
```

**q_po_items**
```sql
SELECT
  poi.line_number, pt.parts_code, pt.parts_name, poi.order_qty,
  COALESCE(poi.received_qty, 0) AS received_qty,
  poi.unit_price, poi.total_amount, poi.quality_check_result
FROM mm.purchase_order_items poi
JOIN shared.parts_master pt ON pt.id = poi.parts_id
WHERE poi.po_id = {{ tbl_po.selectedRow.data.id }}
ORDER BY poi.line_number;
```

---

### Page 4: Goods Receipt (입고/검수)

#### 와이어프레임
```
┌─────────────────────────────────────────────────────────┐
│  ┌─ tabbedContainer2 ──────────────────────────────────┐│
│  │ [ 입고내역 ] [ 입고대기 ] [ 반품 ]                    ││
│  │  tbl_gr_list / tbl_pending_receipt / tbl_returns     ││
│  └──────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────┤
│  ┌─ GR 등록 Form ──────────────────────────────────────┐│
│  │ [PO선택▼] [품목선택▼] [입고수량] [합격수량] [불량수량]  ││
│  │ [단가]    [입고일]    [세금계산서] [검수결과▼]          ││
│  │                              [ 입고 등록 Button ]    ││
│  └──────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

#### 컴포넌트
- `tabbedContainer2` (3탭):
  - Tab 1: `tbl_gr_list` (Data: `q_gr_list`)
  - Tab 2: `tbl_pending_receipt` (Data: `q_pending_receipt`)
  - Tab 3: `tbl_returns` (Data: `q_returns`)
- Form: `gr_po_select`, `gr_parts_id`, `gr_received_qty`, `gr_accepted_qty`, `gr_rejected_qty`, `gr_unit_cost`, `gr_receipt_date`, `gr_tax_invoice`, `gr_inspection_result`
- Button: 입고 등록 → `q_gr_insert`

#### SQL 쿼리

**q_gr_list**
```sql
SELECT
  gr.gr_number, po.po_number, pt.parts_name,
  gr.received_qty, gr.accepted_qty, gr.rejected_qty,
  gr.unit_cost, gr.total_cost, gr.actual_receipt_date, gr.inspection_result
FROM mm.goods_receipts gr
JOIN mm.purchase_orders po ON po.id = gr.po_id
JOIN shared.parts_master pt ON pt.id = gr.parts_id
ORDER BY gr.actual_receipt_date DESC;
```

**q_pending_receipt**
```sql
SELECT
  po.po_number, poi.line_number, pt.parts_code, pt.parts_name,
  poi.order_qty, COALESCE(poi.received_qty, 0) AS received_so_far,
  poi.order_qty - COALESCE(poi.received_qty, 0) AS remaining,
  po.requested_date, v.vendor_name
FROM mm.purchase_order_items poi
JOIN mm.purchase_orders po ON po.id = poi.po_id
JOIN shared.parts_master pt ON pt.id = poi.parts_id
JOIN shared.vendors v ON v.id = po.vendor_id
WHERE po.po_status NOT IN ('closed', 'cancelled')
  AND poi.order_qty > COALESCE(poi.received_qty, 0)
ORDER BY po.requested_date;
```

**q_returns**
```sql
SELECT
  ro.return_number, ro.direction,
  CASE ro.direction
    WHEN 'vendor' THEN '공급업체 반품'
    WHEN 'customer' THEN '고객 반품'
  END AS dir_label,
  pt.parts_name, ro.return_qty, ro.reason_code, ro.disposition, ro.status
FROM mm.return_orders ro
JOIN shared.parts_master pt ON pt.id = ro.parts_id
ORDER BY ro.created_at DESC;
```

---

### Page 5: Inventory (창고/재고)

#### 와이어프레임
```
┌─────────────────────────────────────────────────────────┐
│  재고 정상 (또는 "음수 재고 N건 발견!")                   │
│  ┌─ tbl_inventory ─────────────────────────────────────┐│
│  │ 품목코드│품목명│창고│BIN│존│재고유형│실재고│예약│가용  ││
│  │ 배치   │단가 │재고금액│                              ││
│  └──────────────────────────────────────────────────────┘│
│  ┌─ tbl_stock_movements ───────────────────────────────┐│
│  │ 이동번호│유형코드│유형│품목명│수량│단가│전기일│상태│취소││
│  └──────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

#### 컴포넌트
- `negativeStockWarningText`: q_negative_stock 결과 바인딩
- `tbl_inventory`: Data: `q_inventory`
- `tbl_stock_movements`: Data: `q_stock_movements`

#### SQL 쿼리

**q_inventory**
```sql
SELECT
  pt.parts_code, pt.parts_name, w.warehouse_code, sb.bin_code, sb.zone,
  q.stock_type, q.physical_qty, q.reserved_qty, q.available_qty,
  b.batch_number, b.unit_cost,
  q.physical_qty * COALESCE(b.unit_cost, 0) AS stock_value
FROM wms.quants q
JOIN shared.parts_master pt ON pt.id = q.parts_id
JOIN wms.storage_bins sb ON sb.id = q.storage_bin_id
JOIN wms.warehouses w ON w.id = sb.warehouse_id
LEFT JOIN wms.batches b ON b.id = q.batch_id
ORDER BY pt.parts_code, sb.bin_code;
```

**q_negative_stock**
```sql
SELECT
  pt.parts_code, pt.parts_name, w.warehouse_code, q.physical_qty
FROM wms.quants q
JOIN shared.parts_master pt ON pt.id = q.parts_id
JOIN wms.storage_bins sb ON sb.id = q.storage_bin_id
JOIN wms.warehouses w ON w.id = sb.warehouse_id
WHERE q.physical_qty < 0;
```

**q_stock_movements**
```sql
SELECT
  sm.movement_number, sm.movement_type,
  CASE sm.movement_type
    WHEN '101' THEN '입고'    WHEN '102' THEN '입고취소'
    WHEN '161' THEN '고객반품' WHEN '201' THEN '출고'
    WHEN '261' THEN '생산출고' WHEN '262' THEN '생산반품'
    WHEN '301' THEN '창고이전' WHEN '551' THEN '폐기'
    WHEN '601' THEN '납품출고' WHEN '701' THEN '실사(+)'
    WHEN '702' THEN '실사(-)'
  END AS type_label,
  pt.parts_name, sm.actual_qty, sm.unit_cost_at_movement,
  sm.posting_date, sm.status, sm.is_reversal
FROM mm.stock_movements sm
JOIN shared.parts_master pt ON pt.id = sm.parts_id
ORDER BY sm.posting_date DESC;
```

---

### Page 6: Production (생산/조립)

#### 와이어프레임
```
┌──────────────────────────┬──────────────────────────────┐
│  ┌─ tbl_production ─────┐│  ┌─ tbl_bom_components ────┐│
│  │ 오더번호│프로젝트코드  ││  │ 부품코드│부품명           ││
│  │ 상태   │프로젝트명    ││  │ 단위소요│총소요│불출│잔량  ││
│  │ 계획시작│계획종료     ││  │ 현재고 │                  ││
│  │ 실시작 │실종료       ││  │  ← 선택된 오더의 BOM     ││
│  │ 계획수량│실수량│진행률  ││  └──────────────────────────┘│
│  └──────────────────────┘│                              │
├──────────────────────────┴──────────────────────────────┤
│  ┌─ prod_status_select ─┐  ┌─ 상태 변경 ─┐              │
│  │ in_progress ▼        │  │   [Button]  │              │
│  └──────────────────────┘  └────────────┘              │
└─────────────────────────────────────────────────────────┘
```

#### 컴포넌트
- `tbl_production`: Data: `q_production_orders`, Row selection: Single
  - Select row → Trigger `q_bom_components`
- `tbl_bom_components`: Data: `q_bom_components`
  - 컬럼: 부품코드(`parts_code`), 부품명(`parts_name`), 단위소요(`qty_per_unit`), 총소요(`total_required`), 불출(`issued`), 잔량(`remaining`), 현재고(`current_stock`)
- `prod_status_select`: Manual (planned/in_progress/completed/cancelled)
- Button: 상태 변경 → `q_production_update_status`

#### SQL 쿼리

**q_production_orders**
```sql
SELECT
  pro.id, pro.order_number, pro.status,
  p.project_code, p.project_name,
  pro.planned_start_date, pro.planned_end_date,
  pro.actual_start_date, pro.actual_end_date,
  pro.planned_qty, pro.actual_qty, pro.output_qty,
  CASE WHEN pro.planned_qty > 0
    THEN ROUND(COALESCE(pro.output_qty, 0)::numeric / pro.planned_qty * 100)
    ELSE 0
  END AS progress_pct
FROM pp.production_orders pro
JOIN shared.projects p ON p.id = pro.project_id
ORDER BY
  CASE pro.status
    WHEN 'in_progress' THEN 1 WHEN 'released' THEN 2
    WHEN 'planned' THEN 3 WHEN 'completed' THEN 4 ELSE 5
  END;
```

**q_bom_components**
```sql
SELECT
  pt.parts_code, pt.parts_name,
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
WHERE pro.order_number = {{ tbl_production.selectedRow?.orderNumber }};
```

> **설정:** General → Run behavior: Manual  
> **참고:** Retool Table의 `selectedRow`에는 visible 컬럼만 포함됨. `id` 컬럼이 테이블에 없으면 `selectedRow.id`도 없으므로 `order_number`(= `orderNumber`)로 바인딩.

**q_production_update_status**
```sql
UPDATE pp.production_orders
SET status = {{ prod_status_select.value }},
    updated_at = NOW()
WHERE order_number = {{ tbl_production.selectedRow?.orderNumber }};
```

---

### Page 7: Delivery (배송/물류)

#### 와이어프레임
```
┌─────────────────────────────────────────────────────────┐
│  ┌─ tbl_transport_requests ──────────────────────────┐  │
│  │ TR번호│프로젝트코드│배송유형│수취인│주소│요청출고일│상태│  │
│  └────────────────────────────────────────────────────┘  │
│  ┌─ tbl_freight_orders ──────────────────────────────┐  │
│  │ FO번호│TR번호│운송사│계획출고│출발│도착│배송상태│운임  │  │
│  └────────────────────────────────────────────────────┘  │
│  [ 운임 청구 처리 Button ]                                │
└─────────────────────────────────────────────────────────┘
```

#### 컴포넌트
- `tbl_transport_requests`: Data: `q_transport_requests`
- `tbl_freight_orders`: Data: `q_freight_orders`
- Button: 운임 청구 처리 → `q_freight_mark_billed`

#### SQL 쿼리

**q_transport_requests**
```sql
SELECT
  tr.tr_number, p.project_code, p.project_name, tr.delivery_type,
  CASE tr.delivery_type
    WHEN 'direct' THEN '직납' WHEN 'courier' THEN '택배'
    WHEN 'relay'  THEN '릴레이' WHEN 'pickup' THEN '픽업'
    WHEN 'transfer' THEN '이전'
  END AS type_label,
  tr.recipient_name, tr.recipient_address,
  tr.requested_shipment_date, tr.status
FROM tms.transportation_requirements tr
JOIN shared.projects p ON p.id = tr.project_id
ORDER BY tr.requested_shipment_date DESC;
```

**q_freight_orders**
```sql
SELECT
  fo.fo_number, tr.tr_number, cr.carrier_name, cr.carrier_type,
  fo.planned_shipment_date, fo.confirmed_shipment_date,
  fo.actual_departure_datetime, fo.actual_arrival_datetime,
  fo.shipping_status, fo.total_cbm, fo.freight_cost, fo.tracking_number
FROM tms.freight_orders fo
JOIN tms.transportation_requirements tr ON tr.id = fo.tr_id
JOIN tms.carriers cr ON cr.id = fo.carrier_id
ORDER BY fo.planned_shipment_date DESC;
```

---

### Page 8: Finance (회계/전표)

#### 와이어프레임
```
┌─────────────────────────────────────────────────────────┐
│  ┌─ tbl_journal_entries ──────────────────────────────┐ │
│  │ 전표번호│전표일자│유형│차변│대변│금액│상태│역분개│더존번호│ │
│  └────────────────────────────────────────────────────┘ │
│  [ 더존 전표번호 입력 ] [ 검토완료 ] [ 더존확정 ] [ 검토취소 ] │
│  ┌─ tbl_period_closes ────────────────────────────────┐ │
│  │ 기간│품목코드│품목명│창고│마감수량│단가│마감금액│마감여부 │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

#### 컴포넌트
- `tbl_journal_entries`: Data: `q_journal_entries`
- `slip_no_input`: 더존 전표번호 TextInput
- Button: 검토완료(`q_entry_mark_reviewed`), 더존확정(`q_entry_post_douzone`), 검토취소(`q_entry_revert_draft`)
- `tbl_period_closes`: Data: `q_period_closes`

#### SQL 쿼리

**q_journal_entries**
```sql
SELECT
  ae.entry_number, ae.entry_date, ae.entry_type,
  CASE ae.entry_type
    WHEN 'goods_receipt' THEN '입고' WHEN 'goods_issue' THEN '출고'
    WHEN 'production' THEN '생산' WHEN 'assembly_issue' THEN '조립출고'
    WHEN 'assembly_receipt' THEN '조립입고' WHEN 'purchase_invoice' THEN '매입'
    WHEN 'freight' THEN '운임' WHEN 'inventory_adjustment' THEN '재고조정'
  END AS type_label,
  da.account_code || ' ' || da.account_name AS debit_account,
  ca.account_code || ' ' || ca.account_name AS credit_account,
  ae.amount, ae.status, ae.is_reversal, ae.douzone_slip_no
FROM finance.accounting_entries ae
JOIN shared.gl_accounts da ON da.id = ae.debit_account_id
JOIN shared.gl_accounts ca ON ca.id = ae.credit_account_id
ORDER BY ae.entry_date DESC, ae.entry_number DESC;
```

**q_period_closes**
```sql
SELECT
  pc.period, pt.parts_code, pt.parts_name, w.warehouse_code,
  pc.closing_qty, pc.closing_value, pc.unit_cost, pc.is_closed
FROM finance.period_closes pc
JOIN shared.parts_master pt ON pt.id = pc.parts_id
JOIN wms.warehouses w ON w.id = pc.warehouse_id
ORDER BY pc.period DESC, pt.parts_code;
```

---

### Page 9: Master Data (마스터 데이터)

#### 와이어프레임
```
┌─────────────────────────────────────────────────────────┐
│  ┌─ tabbedContainer3 (5탭) ──────────────────────────┐  │
│  │ [ 고객 ] [ 공급업체 ] [ 품목 ] [ BOM ] [ 창고 ]      │  │
│  │  tbl_clients / tbl_vendors / tbl_parts / tbl_bom  │  │
│  │  / tbl_warehouses                                 │  │
│  └────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

#### 컴포넌트
- `tabbedContainer3`: Tab1(`tbl_clients`), Tab2(`tbl_vendors`), Tab3(`tbl_parts`), Tab4(`tbl_bom`), Tab5(`tbl_warehouses`)

#### SQL 쿼리

**q_clients**
```sql
SELECT client_code, company_name, business_reg_number,
       contact_name, contact_email, contact_phone, status
FROM shared.clients ORDER BY client_code;
```

**q_vendors**
```sql
SELECT vendor_code, vendor_name, vendor_type, douzone_vendor_code,
       is_stock_vendor, contact_name, contact_phone, email, status
FROM shared.vendors ORDER BY vendor_code;
```

**q_parts**
```sql
SELECT
  pt.parts_code, pt.parts_name, mt.type_code AS material_type,
  mg.group_code AS material_group, v.vendor_name AS default_vendor,
  pt.base_uom, pt.reorder_point, pt.min_order_qty, pt.status
FROM shared.parts_master pt
LEFT JOIN shared.material_types mt ON mt.id = pt.material_type_id
LEFT JOIN shared.material_groups mg ON mg.id = pt.material_group_id
LEFT JOIN shared.vendors v ON v.id = pt.vendor_id
ORDER BY pt.parts_code;
```

**q_bom**
```sql
SELECT
  bh.bom_code, bh.bom_type,
  COALESCE(g.goods_name, i.item_name) AS product_name,
  bi.component_qty, pt.parts_code, pt.parts_name
FROM pp.bom_headers bh
LEFT JOIN shared.goods_master g ON g.id = bh.goods_id
LEFT JOIN shared.item_master i ON i.id = bh.item_id
JOIN pp.bom_items bi ON bi.bom_id = bh.id
JOIN shared.parts_master pt ON pt.id = bi.parts_id
ORDER BY bh.bom_code, bi.sort_order;
```

**q_warehouses**
```sql
SELECT
  w.warehouse_code, w.warehouse_name, w.address,
  w.max_cbm, w.status, COUNT(sb.id) AS bin_count
FROM wms.warehouses w
LEFT JOIN wms.storage_bins sb ON sb.warehouse_id = w.id
GROUP BY w.id ORDER BY w.warehouse_code;
```

---

### Page 10: Workflow (워크플로우 추적기)

#### 와이어프레임
```
┌─────────────────────────────────────────────────────────┐
│  ┌─ project_selector ───────────────────┐               │
│  │ PRJ-2026-025 — 프리비알 VIP... ▼     │               │
│  └──────────────────────────────────────┘               │
│  ┌─ tbl_workflow ──────────────────────────────────────┐ │
│  │ 프로젝트│상태│PO번호│PO상태│GR번호│생산오더│FO번호     │ │
│  │ 배송상태│운임│전표번호│전표유형│금액│전표상태          │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

#### 컴포넌트
- `project_selector`: Mapped, Data: `q_util_project_dropdown`
  - Event handler: Change → Trigger `q_workflow_tracker`
- `tbl_workflow`: Data: `q_workflow_tracker`

#### 쿼리

**q_util_project_dropdown**
```sql
SELECT
  id AS value,
  project_code || ' — ' || project_name AS label
FROM shared.projects
ORDER BY first_shipment_date DESC;
```

**q_workflow_tracker**
```sql
SELECT
  p.project_code, p.project_name, p.project_status,
  p.first_shipment_date,
  c.company_name AS client_name,
  po.po_number, po.po_status, po.requested_date,
  gr.gr_number, gr.actual_receipt_date,
  gr.received_qty, gr.rejected_qty, gr.unit_cost,
  prod.order_number AS prod_order_number,
  prod.status AS prod_status,
  prod.actual_start_date, prod.actual_end_date,
  fo.fo_number, fo.shipping_status, fo.freight_cost,
  fo.planned_shipment_date,
  ae.entry_number, ae.entry_type, ae.amount,
  ae.status AS entry_status, ae.entry_date
FROM shared.projects p
LEFT JOIN shared.clients c ON c.id = p.client_id
LEFT JOIN mm.purchase_orders po ON po.project_id = p.id
LEFT JOIN mm.goods_receipts gr ON gr.po_id = po.id
LEFT JOIN pp.production_orders prod ON prod.project_id = p.id
LEFT JOIN tms.transportation_requirements tr ON tr.project_id = p.id
LEFT JOIN tms.freight_orders fo ON fo.tr_id = tr.id
LEFT JOIN finance.accounting_entries ae ON ae.source_id = gr.id
  AND ae.source_table = 'mm.goods_receipts'
WHERE p.id = {{ project_selector.value }}
ORDER BY gr.actual_receipt_date NULLS LAST, ae.entry_date NULLS LAST;
```

> **설정:** Run behavior: Manual (페이지 로드 시 null 방지)

---

## 4. 권한/보안 설계

### 사용자 그룹

| 그룹 | 접근 페이지 | 권한 |
|------|-----------|------|
| 관리자 | 전체 | READ + WRITE |
| CX 담당 | 1, 2, 7 | READ + 배송 상태 UPDATE |
| 구매 담당 | 1, 3, 4, 9 | READ + PO/GR INSERT |
| 창고 담당 | 5, 6 | READ + 재고이동/생산확인 INSERT |
| 경리/회계 | 8 | READ ONLY |
| 경영진 | 1 | READ ONLY |

### RLS 전략
- **Option A (권장):** `service_role` 키 → Retool 그룹 권한으로 제어
- **Option B (엄격):** `anon` 키 + Supabase RLS (마이그레이션 017)

---

## 5. 쓰기 작업 원칙

### INSERT 가능

| 테이블 | 용도 | 이동유형 |
|--------|------|---------|
| mm.purchase_orders + items | 신규 발주 | — |
| mm.goods_receipts | 입고 처리 | 101 |
| mm.stock_movements | 재고 이동/조정 | 261/301/701 |
| mm.return_orders | 반품 처리 | 122/161 |
| pp.production_orders | 생산지시 | — |
| tms.transportation_requirements | 배송 요청 | — |
| tms.freight_orders | 배차 | — |
| finance.accounting_entries | 분개 (draft) | — |

### UPDATE 가능 (상태 변경만)

| 테이블 | 허용 필드 |
|--------|---------|
| mm.purchase_orders | po_status |
| pp.production_orders | status, output_qty |
| tms.freight_orders | shipping_status |
| finance.accounting_entries | status (draft→reviewed→posted) |

### 절대 금지

| 테이블 | 이유 |
|--------|------|
| mm.goods_receipts | 불변 원장 |
| mm.stock_movements | Storno(역분개)로만 정정 |
| finance.period_closes (is_closed=TRUE) | 기간 마감 불가역 |
| wms.quants | 트리거 전용 |

---

## 6. 미등록 쿼리 (향후 추가 대상)

> SQL 전문: `docs/retool/page-queries.md` 참조

| 페이지 | 쿼리명 | 용도 | 비고 |
|--------|--------|------|------|
| dashboard | `q_pending_entries` | 미처리 전표 Stat 카드 | SELECT |
| project_detail | `q_project_update_status` | 프로젝트 상태 변경 | UPDATE |
| goods_receipt | `q_gr_insert` | GR 등록 | INSERT, 트리거 1번 |
| inventory | `q_inventory_adjustment_approve` | 재고 실사 조정 승인 | UPDATE, 트리거 6번 |
| production | `q_production_update_status` | 생산 상태 변경 | UPDATE |
| delivery | `q_freight_mark_billed` | 운임 청구 처리 | UPDATE, 트리거 5번 |
| finance | `q_entry_mark_reviewed` | draft→reviewed | UPDATE |
| finance | `q_entry_post_douzone` | reviewed→posted | UPDATE |
| finance | `q_entry_revert_draft` | reviewed→draft | UPDATE |
| workflow | ~~`q_workflow_tracker`~~ | ~~전체 흐름 타임라인~~ | **등록 완료** |
| workflow | `q_workflow_project_entries` | 프로젝트 전표 전체 | SELECT |
| 유틸 | ~~`q_util_project_dropdown`~~ | ~~프로젝트 드롭다운~~ | **등록 완료** |
| 유틸 | `q_util_trigger_check` | 트리거 검증 | SELECT |
| 유틸 | `q_util_verify_gr_entries` | GR-전표 매핑 확인 | SELECT |
| 유틸 | `q_util_pending_review_count` | draft 카운트 배지 | SELECT |

---

## 7. 구현 체크리스트

### Phase 1: 연결 (30분)
- [ ] PostgreSQL Resource 생성 (pooler:6543)
- [ ] Test Connection 성공
- [ ] `SELECT COUNT(*) FROM shared.projects;` → 25건

### Phase 2: 핵심 페이지 (2시간)
- [ ] Page 1: dashboard (KPI + 프로젝트 목록)
- [ ] Page 2: project_detail (4탭 + 드롭다운)
- [ ] Page 9: master_data (데이터 확인)

### Phase 3: 운영 페이지 (3시간)
- [ ] Page 3~4: 구매/입고
- [ ] Page 5~6: 재고/생산
- [ ] Page 7~8: 배송/회계

### Phase 4: 권한/배포
- [ ] 사용자 그룹 설정
- [ ] 팀원 초대

---

## 8. 컴포넌트 전체 요약

| Page | 컴포넌트 수 | 쿼리 수 | 핵심 인터랙션 |
|------|-----------|---------|-------------|
| Dashboard | 7 | 3 | 행 클릭→project_detail |
| Project Detail | 7 | 6 | 탭 전환, 드롭다운 선택 |
| Purchase Orders | 3 | 2 | PO 클릭→품목 |
| Goods Receipt | 13 | 3+2미등록 | GR 등록 Form |
| Inventory | 4 | 3 | 음수 재고 경고 |
| Production | 5 | 2+1미등록 | 오더 클릭→BOM |
| Delivery | 4 | 2 | 운임 청구 버튼 |
| Finance | 7 | 2+3미등록 | 전표 검토/확정/취소 |
| Master Data | 7 | 5 | 5탭 전환 |
| Workflow | 3 | 2 | 프로젝트 선택→흐름 |
| **합계** | **~60** | **~34** | |
