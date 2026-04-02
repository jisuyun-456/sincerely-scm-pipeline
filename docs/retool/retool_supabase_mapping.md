# Retool ↔ Supabase 스키마 매핑

> **최종 업데이트:** 2026-04-01  
> **대상 앱:** SSOT-SAP (Retool 10페이지)  
> **대상 DB:** Supabase PostgreSQL — 6스키마 51테이블 7뷰  
> **관련 문서:** [retool_master.md](retool_master.md)

---

## 1. 전체 매핑 매트릭스

| # | Retool Page | shared (14) | mm (10) | wms (7) | tms (9) | pp (7) | finance (4) | 합계 |
|---|-------------|:-----------:|:-------:|:-------:|:-------:|:------:|:-----------:|:----:|
| 1 | Dashboard | ●3 | | | ●1 | | | 4 |
| 2 | Project Detail | ●4 | ●3 | | ●3 | ●1 | | 11 |
| 3 | Purchase Orders | ●3 | ●2 | | | | | 5 |
| 4 | Goods Receipt | ●2 | ●4 | | | | | 6 |
| 5 | Inventory | ●1 | ●1 | ●4 | | | | 6 |
| 6 | Production | ●1 | | ●1 | | ●4 | | 6 |
| 7 | Delivery | ●1 | | | ●3 | | | 4 |
| 8 | Finance | ●1 | | ●1 | | | ●2 | 4 |
| 9 | Master Data | ●6 | | ●2 | | ●2 | | 10 |
| 10 | Workflow | ●1 | ●2 | | ●2 | ●2 | ●1 | 8 |

> ●N = 해당 스키마에서 N개 테이블 사용. shared는 모든 페이지에서 참조됨.

---

## 2. 스키마별 테이블 인벤토리

### shared (14 tables) — 마스터 데이터

| 테이블 | SAP 매핑 | 핵심 컬럼 | 참조 페이지 |
|--------|----------|-----------|------------|
| `units_of_measure` | T006 | uom_code, dimension | 9 |
| `gl_accounts` | CoA | account_code, ifrs_category | 8, 9 |
| `material_types` | T134 | type_code, is_stockable | 9 |
| `material_groups` | T023 | group_code, parent_id | 9 |
| `organizations` | T001/T001W | org_code, org_type | 3 |
| `users` | SU01 | employee_number, team | 1, 2 |
| `clients` | BP-Customer | client_code, company_name | 1, 2, 9 |
| `vendors` | BP-Vendor | vendor_code, vendor_type | 2, 3, 4, 9 |
| `projects` | PS | project_code, project_status | 1, 2, 3, 4, 6, 7, 10 |
| `goods_master` | FERT | goods_code, default_bom_id | 6, 9 |
| `item_master` | HALB | item_code, production_type | 9 |
| `parts_master` | ROH/VERP | parts_code, vendor_id | 3, 4, 5, 6, 9 |
| `material_valuation` | MBEW | moving_avg_price, costing_method | — |
| `vendor_evaluations` | ME61 | quality_score, overall_score | — |

### mm (10 tables) — 자재관리/구매

| 테이블 | SAP 매핑 | 핵심 컬럼 | 참조 페이지 |
|--------|----------|-----------|------------|
| `purchase_requisitions` | EBAN | pr_number, source | — |
| `purchase_orders` | EKKO | po_number, po_status | 2, 3, 4, 10 |
| `purchase_order_items` | EKPO | order_qty, unit_price | 2, 3, 4 |
| `goods_receipts` | MKPF | gr_number, movement_type | 2, 4, 10 |
| `stock_movements` | MSEG | movement_type, actual_qty | 5 |
| `invoice_verifications` | MIRO | match_result, price_variance | — |
| `reservations` | RESB | requirement_qty, status | — |
| `return_orders` | Return | direction, disposition | 4 |
| `quality_inspections` | QALS | result, decision | — |
| `scrap_records` | Scrap | scrap_qty, reason_code | — |

### wms (7 tables) — 창고관리

| 테이블 | SAP 매핑 | 핵심 컬럼 | 행수 | 참조 페이지 |
|--------|----------|-----------|------|------------|
| `warehouses` | /SCWM/T_WH | warehouse_code, max_cbm | 6 | 5, 8, 9 |
| `storage_types` | /SCWM/T_ST | type_code, type_name | 6 | 5 |
| `storage_bins` | /SCWM/LAGP | bin_code, zone/aisle/rack | 60 | 5, 6 |
| `batches` | MCHA | batch_number, unit_cost | 0 | 5 |
| `quants` | /SCWM/AQUA | physical_qty, available_qty | 26 | 5, 6 |
| `inventory_count_docs` | IKPF | doc_number, count_type | 1 | 5 |
| `inventory_count_items` | ISEG | book_qty, final_count_qty | 2 | 5 |

> wms 행수는 2026-04-01 Supabase Table Editor 기준 실측값

### tms (9 tables) — 운송관리

| 테이블 | SAP 매핑 | 핵심 컬럼 | 참조 페이지 |
|--------|----------|-----------|------------|
| `locations` | TM Location | location_code, location_type | 7 |
| `carriers` | BP-Carrier | carrier_code, carrier_type | 2, 7 |
| `dispatch_schedules` | Scheduling | schedule_date, total_cbm | — |
| `transportation_requirements` | TR | tr_number, delivery_type | 1, 2, 7, 10 |
| `freight_orders` | FO/Shipment | fo_number, shipping_status | 2, 7, 10 |
| `logistics_releases` | VL01N | release_number, status | — |
| `logistics_release_items` | LIPS | released_qty, batch_id | — |
| `packaging_materials` | Packaging | box_code, cbm | — |
| `routes` | TM Route | route_code, standard_transit_days | — |

### pp (7 tables) — 생산계획

| 테이블 | SAP 매핑 | 핵심 컬럼 | 참조 페이지 |
|--------|----------|-----------|------------|
| `bom_headers` | MAST | bom_code, bom_type | 6, 9 |
| `bom_items` | STPO | component_qty, scrap_pct | 6, 9 |
| `work_centers` | CRHD | wc_code, wc_type | — |
| `routings` | PLKO/PLPO | operation_type, standard_time | — |
| `production_orders` | Prod Order | order_number, status | 2, 6, 10 |
| `production_order_components` | RESB | required_qty, issued_qty | 6 |
| `production_confirmations` | AFRU | completed_qty, operation_type | — |

### finance (4 tables) — 재무/회계

| 테이블 | SAP 매핑 | 핵심 컬럼 | 참조 페이지 |
|--------|----------|-----------|------------|
| `accounting_entries` | BKPF/BSEG | entry_number, status | 8, 10 |
| `cost_settings` | OBYA/T030 | costing_method, parts_type | — |
| `douzone_sync_log` | 더존 연동 | sync_status, douzone_slip_no | — |
| `period_closes` | MARDH/MBEWH | closing_qty, closing_value | 8 |

---

## 3. 페이지별 상세 매핑

### Page 1: Dashboard

| 스키마 | 테이블 | 역할 |
|--------|--------|------|
| shared | projects, clients, users | KPI 집계, 프로젝트 목록 |
| tms | transportation_requirements | 이번 달 출하 건수 |

| 쿼리 | FROM/JOIN 테이블 |
|-------|-----------------|
| `q_kpi` | shared.projects |
| `q_shipping_this_month` | tms.transportation_requirements |
| `q_projects_list` | shared.projects → clients → users |
| `q_project_update_status` *(미등록)* | shared.projects |

---

### Page 2: Project Detail

| 스키마 | 테이블 | 역할 |
|--------|--------|------|
| shared | projects, clients, users, vendors, parts_master | 프로젝트 기본정보 + 마스터 |
| mm | purchase_orders, purchase_order_items, goods_receipts | 발주/입고 탭 |
| pp | production_orders | 생산 탭 |
| tms | transportation_requirements, freight_orders, carriers | 배송 탭 |

| 쿼리 | FROM/JOIN 테이블 |
|-------|-----------------|
| `q_project_info` | shared.projects → clients → users |
| `q_all_projects` | shared.projects |
| `q_project_pos` | mm.purchase_orders → purchase_order_items → shared.vendors, parts_master |
| `q_project_grs` | mm.goods_receipts → purchase_orders → shared.parts_master |
| `q_project_production` | pp.production_orders |
| `q_project_delivery` | tms.transportation_requirements → freight_orders → carriers |

---

### Page 3: Purchase Orders

| 스키마 | 테이블 | 역할 |
|--------|--------|------|
| shared | projects, vendors, parts_master | 마스터 조인 |
| mm | purchase_orders, purchase_order_items | PO 헤더/라인 |

| 쿼리 | FROM/JOIN 테이블 |
|-------|-----------------|
| `q_po_list` | mm.purchase_orders → purchase_order_items → shared.projects, vendors |
| `q_po_items` | mm.purchase_order_items → shared.parts_master |

---

### Page 4: Goods Receipt

| 스키마 | 테이블 | 역할 |
|--------|--------|------|
| shared | parts_master, vendors | 마스터 조인 |
| mm | goods_receipts, purchase_orders, purchase_order_items, return_orders | GR/미입고/반품 |

| 쿼리 | FROM/JOIN 테이블 |
|-------|-----------------|
| `q_gr_list` | mm.goods_receipts → purchase_orders → shared.parts_master |
| `q_pending_receipt` | mm.purchase_order_items → purchase_orders → shared.parts_master, vendors |
| `q_returns` | mm.return_orders → shared.parts_master |
| `q_gr_insert` *(미등록)* | mm.goods_receipts (→ trigger: mm.stock_movements) |

---

### Page 5: Inventory

| 스키마 | 테이블 | 역할 |
|--------|--------|------|
| shared | parts_master | 품목명 조인 |
| wms | quants, storage_bins, warehouses, batches | 현재고 + 위치 |
| mm | stock_movements | 재고이동 이력 |

| 쿼리 | FROM/JOIN 테이블 |
|-------|-----------------|
| `q_inventory` | wms.quants → parts_master → storage_bins → warehouses → batches |
| `q_negative_stock` | wms.quants → shared.parts_master → storage_bins → warehouses |
| `q_stock_movements` | mm.stock_movements → shared.parts_master |

---

### Page 6: Production

| 스키마 | 테이블 | 역할 |
|--------|--------|------|
| shared | projects, parts_master | 마스터 조인 |
| pp | production_orders, bom_headers, bom_items, production_order_components | 생산지시 + BOM |
| wms | quants | 현재고 확인 |

| 쿼리 | FROM/JOIN 테이블 |
|-------|-----------------|
| `q_production_orders` | pp.production_orders → shared.projects |
| `q_bom_components` | pp.bom_items → shared.parts_master, pp.production_orders → production_order_components, wms.quants |
| `q_production_update_status` | pp.production_orders |

---

### Page 7: Delivery

| 스키마 | 테이블 | 역할 |
|--------|--------|------|
| shared | projects | 프로젝트명 조인 |
| tms | transportation_requirements, freight_orders, carriers | TR + FO |

| 쿼리 | FROM/JOIN 테이블 |
|-------|-----------------|
| `q_transport_requests` | tms.transportation_requirements → shared.projects |
| `q_freight_orders` | tms.freight_orders → transportation_requirements → carriers |
| `q_freight_mark_billed` *(미등록)* | tms.freight_orders |

---

### Page 8: Finance

| 스키마 | 테이블 | 역할 |
|--------|--------|------|
| shared | gl_accounts | 계정과목명 조인 |
| finance | accounting_entries, period_closes | 전표/기간마감 |
| wms | warehouses | 마감 창고별 |

| 쿼리 | FROM/JOIN 테이블 |
|-------|-----------------|
| `q_journal_entries` | finance.accounting_entries → shared.gl_accounts |
| `q_period_closes` | finance.period_closes → shared.parts_master → wms.warehouses |
| `q_entry_mark_reviewed` *(미등록)* | finance.accounting_entries |
| `q_entry_post_douzone` *(미등록)* | finance.accounting_entries |
| `q_entry_revert_draft` *(미등록)* | finance.accounting_entries |

---

### Page 9: Master Data

| 스키마 | 테이블 | 역할 |
|--------|--------|------|
| shared | clients, vendors, parts_master, goods_master, item_master, material_types, material_groups | 5탭 마스터 뷰어 |
| pp | bom_headers, bom_items | BOM 탭 |
| wms | warehouses, storage_bins | 창고 탭 |

| 쿼리 | FROM/JOIN 테이블 |
|-------|-----------------|
| `q_clients` | shared.clients |
| `q_vendors` | shared.vendors |
| `q_parts` | shared.parts_master → material_types → material_groups → vendors |
| `q_bom` | pp.bom_headers → bom_items → shared.goods_master, item_master, parts_master |
| `q_warehouses` | wms.warehouses → storage_bins |

---

### Page 10: Workflow

| 스키마 | 테이블 | 역할 |
|--------|--------|------|
| shared | projects | 프로젝트 드롭다운 |
| mm | purchase_orders, goods_receipts | PO→GR 단계 |
| pp | production_orders, bom_headers | 생산 단계 |
| tms | freight_orders, transportation_requirements | 배송 단계 |
| finance | accounting_entries | 회계 단계 |

| 쿼리 | FROM/JOIN 테이블 |
|-------|-----------------|
| `q_util_project_dropdown` *(미등록)* | shared.projects |
| `q_workflow_tracker` *(미등록)* | 전 스키마 크로스 조인 |

---

## 4. 테이블별 역참조

### shared (14)

| 테이블 | 사용 페이지 |
|--------|-----------|
| units_of_measure | 9 |
| gl_accounts | 8 |
| material_types | 9 |
| material_groups | 9 |
| organizations | 3 |
| users | 1, 2 |
| clients | 1, 2, 9 |
| vendors | 2, 3, 4, 9 |
| projects | 1, 2, 3, 4, 6, 7, 10 |
| goods_master | 6, 9 |
| item_master | 9 |
| parts_master | 3, 4, 5, 6, 9 |
| material_valuation | — (향후 원가 페이지) |
| vendor_evaluations | — (향후 공급사 평가) |

### mm (10)

| 테이블 | 사용 페이지 |
|--------|-----------|
| purchase_requisitions | — (향후 PR 페이지) |
| purchase_orders | 2, 3, 4, 10 |
| purchase_order_items | 2, 3, 4 |
| goods_receipts | 2, 4, 10 |
| stock_movements | 5 |
| invoice_verifications | — (향후 3-way match) |
| reservations | — (향후 예약) |
| return_orders | 4 |
| quality_inspections | — (향후 QC) |
| scrap_records | — (향후 스크랩) |

### wms (7)

| 테이블 | 사용 페이지 |
|--------|-----------|
| warehouses | 5, 8, 9 |
| storage_types | 5 |
| storage_bins | 5, 6, 9 |
| batches | 5 |
| quants | 5, 6 |
| inventory_count_docs | 5 |
| inventory_count_items | 5 |

### tms (9)

| 테이블 | 사용 페이지 |
|--------|-----------|
| locations | 7 |
| carriers | 2, 7 |
| dispatch_schedules | — (향후 배차) |
| transportation_requirements | 1, 2, 7, 10 |
| freight_orders | 2, 7, 10 |
| logistics_releases | — (향후 출고 릴리스) |
| logistics_release_items | — (향후 출고 릴리스) |
| packaging_materials | — (향후 패킹) |
| routes | — (향후 노선) |

### pp (7)

| 테이블 | 사용 페이지 |
|--------|-----------|
| bom_headers | 6, 9, 10 |
| bom_items | 6, 9 |
| work_centers | — (향후 작업장) |
| routings | — (향후 공정) |
| production_orders | 2, 6, 10 |
| production_order_components | 6 |
| production_confirmations | — (향후 실적확인) |

### finance (4)

| 테이블 | 사용 페이지 |
|--------|-----------|
| accounting_entries | 8, 10 |
| cost_settings | — (설정 전용) |
| douzone_sync_log | — (백엔드 전용) |
| period_closes | 8 |

---

## 5. 뷰 목록

| 뷰 | 스키마 | 설명 | Retool 페이지 |
|----|--------|------|--------------|
| `v_quant_summary` | wms | quant별 입고/출고/이전 집계 | 5 (Inventory) |
| `v_available_qty` | shared | 품목별 가용재고 (시스템-예약-차단) | 5, 6 |
| `v_cost_weighted_avg` | finance | 가중평균 단가 | 8 |
| `v_cost_fifo` | finance | FIFO 원가 레이어 | 8 |
| `v_inventory_valuation` | finance | K-IFRS IAS 2 재고평가 | 8 |
| `v_stock_ledger` | finance | 기간별 재고수불부 | 8 |
| `v_accounting_summary` | finance | 전표 유형/상태별 집계 | 8 |

---

## 6. 시드 데이터 현황

### wms 스키마 (2026-04-01 Supabase 실측)

| 테이블 | 컬럼 | 행수 | 크기 | 상태 |
|--------|------|------|------|------|
| batches | 11 | 0 | 48kB | 빈 테이블 |
| inventory_count_docs | 11 | 1 | 96kB | 시드 있음 |
| inventory_count_items | 16 | 2 | 72kB | 시드 있음 |
| quants | 16 | 26 | 144kB | 시드 있음 |
| storage_bins | 13 | 60 | 104kB | 시드 있음 |
| storage_types | 4 | 6 | 40kB | 시드 있음 |
| warehouses | 9 | 6 | 80kB | 시드 있음 |

### 미사용 테이블 (Retool 10페이지에서 미참조)

현재 Retool에서 직접 쿼리하지 않는 테이블 **20개**:

| 스키마 | 테이블 | 향후 용도 |
|--------|--------|----------|
| shared | units_of_measure | 단위 변환 드롭다운 |
| shared | material_valuation | 원가 관리 페이지 |
| shared | vendor_evaluations | 공급사 평가 대시보드 |
| mm | purchase_requisitions | 구매요청 페이지 |
| mm | invoice_verifications | 3-way match 페이지 |
| mm | reservations | 자재 예약 관리 |
| mm | quality_inspections | QC 검사 페이지 |
| mm | scrap_records | 스크랩 관리 |
| tms | dispatch_schedules | 배차 스케줄러 |
| tms | logistics_releases | 출고 릴리스 |
| tms | logistics_release_items | 출고 릴리스 아이템 |
| tms | packaging_materials | 패킹 자재 |
| tms | routes | 노선 관리 |
| pp | work_centers | 작업장 관리 |
| pp | routings | 공정 관리 |
| pp | production_confirmations | 생산 실적확인 |
| finance | cost_settings | 원가 설정 (백엔드) |
| finance | douzone_sync_log | 더존 연동 로그 (백엔드) |
| tms | locations | 물류 거점 (Page 7에서 간접 사용) |
| shared | organizations | 조직 마스터 (Page 3에서 간접 사용) |

> 51개 중 **31개가 Retool에서 활발히 사용**, 20개는 향후 확장 또는 백엔드 전용.
