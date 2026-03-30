-- ============================================================
-- Migration 013: Performance Indexes — Composite & Additional
-- NOTE: Most FK/single-column indexes are already created inline
-- in each migration file. This file adds composite indexes and
-- any missing ones using IF NOT EXISTS for safety.
-- ============================================================

-- ============================================================
-- SCHEMA: shared
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_parts_master_vendor_id ON shared.parts_master (vendor_id);
CREATE INDEX IF NOT EXISTS idx_parts_master_parts_type ON shared.parts_master (parts_type);
CREATE INDEX IF NOT EXISTS idx_parts_master_material_type_id ON shared.parts_master (material_type_id);
CREATE INDEX IF NOT EXISTS idx_parts_master_material_group_id ON shared.parts_master (material_group_id);
CREATE INDEX IF NOT EXISTS idx_parts_master_status ON shared.parts_master (status);
CREATE INDEX IF NOT EXISTS idx_projects_client_id ON shared.projects (client_id);
CREATE INDEX IF NOT EXISTS idx_projects_project_status ON shared.projects (project_status);
CREATE INDEX IF NOT EXISTS idx_item_master_material_type_id ON shared.item_master (material_type_id);
CREATE INDEX IF NOT EXISTS idx_goods_master_material_type_id ON shared.goods_master (material_type_id);

-- ============================================================
-- SCHEMA: tms
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_freight_orders_carrier_id ON tms.freight_orders (carrier_id);
CREATE INDEX IF NOT EXISTS idx_freight_orders_tr_id ON tms.freight_orders (tr_id);
CREATE INDEX IF NOT EXISTS idx_freight_orders_dispatch_schedule_id ON tms.freight_orders (dispatch_schedule_id);
CREATE INDEX IF NOT EXISTS idx_freight_orders_shipping_status ON tms.freight_orders (shipping_status);
CREATE INDEX IF NOT EXISTS idx_freight_orders_planned_date ON tms.freight_orders (planned_shipment_date);
CREATE INDEX IF NOT EXISTS idx_tr_project_id ON tms.transportation_requirements (project_id);
CREATE INDEX IF NOT EXISTS idx_tr_status ON tms.transportation_requirements (status);
CREATE INDEX IF NOT EXISTS idx_lr_tr_id ON tms.logistics_releases (tr_id);
CREATE INDEX IF NOT EXISTS idx_lr_production_order_id ON tms.logistics_releases (production_order_id);

-- ============================================================
-- SCHEMA: wms
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_quants_parts_id ON wms.quants (parts_id);
CREATE INDEX IF NOT EXISTS idx_quants_storage_bin_id ON wms.quants (storage_bin_id);
CREATE INDEX IF NOT EXISTS idx_quants_parts_bin ON wms.quants (parts_id, storage_bin_id);
CREATE INDEX IF NOT EXISTS idx_quants_stock_type ON wms.quants (stock_type);
CREATE INDEX IF NOT EXISTS idx_storage_bins_warehouse_id ON wms.storage_bins (warehouse_id);
CREATE INDEX IF NOT EXISTS idx_storage_bins_zone ON wms.storage_bins (zone);
CREATE INDEX IF NOT EXISTS idx_batches_parts_id ON wms.batches (parts_id);
CREATE INDEX IF NOT EXISTS idx_batches_gr_id ON wms.batches (gr_id);
CREATE INDEX IF NOT EXISTS idx_batches_status ON wms.batches (status);

-- ============================================================
-- SCHEMA: mm
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_po_project_id ON mm.purchase_orders (project_id);
CREATE INDEX IF NOT EXISTS idx_po_vendor_id ON mm.purchase_orders (vendor_id);
CREATE INDEX IF NOT EXISTS idx_po_po_status ON mm.purchase_orders (po_status);
CREATE INDEX IF NOT EXISTS idx_poi_po_id ON mm.purchase_order_items (po_id);
CREATE INDEX IF NOT EXISTS idx_poi_parts_id ON mm.purchase_order_items (parts_id);
CREATE INDEX IF NOT EXISTS idx_gr_po_item_id ON mm.goods_receipts (po_item_id);
CREATE INDEX IF NOT EXISTS idx_gr_parts_id ON mm.goods_receipts (parts_id);
CREATE INDEX IF NOT EXISTS idx_gr_actual_receipt_date ON mm.goods_receipts (actual_receipt_date);
CREATE INDEX IF NOT EXISTS idx_sm_parts_id ON mm.stock_movements (parts_id);
CREATE INDEX IF NOT EXISTS idx_sm_movement_type ON mm.stock_movements (movement_type);
CREATE INDEX IF NOT EXISTS idx_sm_actual_date ON mm.stock_movements (actual_date);
CREATE INDEX IF NOT EXISTS idx_sm_status ON mm.stock_movements (status);
CREATE INDEX IF NOT EXISTS idx_sm_from_bin_id ON mm.stock_movements (from_bin_id);
CREATE INDEX IF NOT EXISTS idx_sm_to_bin_id ON mm.stock_movements (to_bin_id);
CREATE INDEX IF NOT EXISTS idx_sm_gr_id ON mm.stock_movements (gr_id);
CREATE INDEX IF NOT EXISTS idx_sm_production_order_id ON mm.stock_movements (production_order_id);

-- Composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_sm_parts_status ON mm.stock_movements (parts_id, status);
CREATE INDEX IF NOT EXISTS idx_sm_parts_type_date ON mm.stock_movements (parts_id, movement_type, actual_date);
CREATE INDEX IF NOT EXISTS idx_sm_status_date ON mm.stock_movements (status, actual_date);

CREATE INDEX IF NOT EXISTS idx_res_parts_id ON mm.reservations (parts_id);
CREATE INDEX IF NOT EXISTS idx_res_status ON mm.reservations (status);
CREATE INDEX IF NOT EXISTS idx_res_project_id ON mm.reservations (project_id);
CREATE INDEX IF NOT EXISTS idx_pr_parts_id ON mm.purchase_requisitions (parts_id);
CREATE INDEX IF NOT EXISTS idx_pr_status ON mm.purchase_requisitions (status);

-- ============================================================
-- SCHEMA: pp
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_prod_project_id ON pp.production_orders (project_id);
CREATE INDEX IF NOT EXISTS idx_prod_status ON pp.production_orders (status);
CREATE INDEX IF NOT EXISTS idx_prod_goods_id ON pp.production_orders (goods_id);
CREATE INDEX IF NOT EXISTS idx_prod_work_center_id ON pp.production_orders (work_center_id);
CREATE INDEX IF NOT EXISTS idx_bom_goods_id ON pp.bom_headers (goods_id);
CREATE INDEX IF NOT EXISTS idx_bom_item_id ON pp.bom_headers (item_id);
CREATE INDEX IF NOT EXISTS idx_poc_production_order_id ON pp.production_order_components (production_order_id);
CREATE INDEX IF NOT EXISTS idx_poc_parts_id ON pp.production_order_components (parts_id);

-- ============================================================
-- SCHEMA: finance
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_ae_status ON finance.accounting_entries (status);
CREATE INDEX IF NOT EXISTS idx_ae_entry_date ON finance.accounting_entries (entry_date);
CREATE INDEX IF NOT EXISTS idx_ae_source ON finance.accounting_entries (source_table, source_id);
CREATE INDEX IF NOT EXISTS idx_ae_entry_type ON finance.accounting_entries (entry_type);
CREATE INDEX IF NOT EXISTS idx_ae_debit_account_id ON finance.accounting_entries (debit_account_id);
CREATE INDEX IF NOT EXISTS idx_ae_credit_account_id ON finance.accounting_entries (credit_account_id);
CREATE INDEX IF NOT EXISTS idx_ae_fiscal ON finance.accounting_entries (fiscal_year, fiscal_period);
CREATE INDEX IF NOT EXISTS idx_ae_status_date ON finance.accounting_entries (status, entry_date);
CREATE INDEX IF NOT EXISTS idx_dz_entry_id ON finance.douzone_sync_log (entry_id);
CREATE INDEX IF NOT EXISTS idx_dz_sync_status ON finance.douzone_sync_log (sync_status);
CREATE INDEX IF NOT EXISTS idx_pc_period ON finance.period_closes (period);
CREATE INDEX IF NOT EXISTS idx_pc_parts_id ON finance.period_closes (parts_id);
CREATE INDEX IF NOT EXISTS idx_pc_warehouse_id ON finance.period_closes (warehouse_id);
CREATE INDEX IF NOT EXISTS idx_pc_parts_period ON finance.period_closes (parts_id, period);
CREATE INDEX IF NOT EXISTS idx_pc_parts_period_closed ON finance.period_closes (parts_id, period, is_closed);
