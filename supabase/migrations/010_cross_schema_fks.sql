-- ============================================================
-- Migration 010: Cross-Schema Foreign Keys
-- Resolving circular dependencies between schemas
-- ============================================================
-- These FK constraints could not be created during initial
-- table creation because the referenced tables did not yet
-- exist (cross-schema dependency ordering).
-- ============================================================

-- pp → tms: logistics_releases.production_order_id
ALTER TABLE tms.logistics_releases
  ADD CONSTRAINT fk_lr_production_order
  FOREIGN KEY (production_order_id) REFERENCES pp.production_orders(id);

-- mm → pp: stock_movements.production_order_id
ALTER TABLE mm.stock_movements
  ADD CONSTRAINT fk_sm_production_order
  FOREIGN KEY (production_order_id) REFERENCES pp.production_orders(id);

-- mm → pp: reservations.production_order_id
ALTER TABLE mm.reservations
  ADD CONSTRAINT fk_res_production_order
  FOREIGN KEY (production_order_id) REFERENCES pp.production_orders(id);

-- mm → pp: scrap_records.production_order_id
-- (defined as plain UUID in migration 008; FK added here now
--  that pp.production_orders exists)
ALTER TABLE mm.scrap_records
  ADD CONSTRAINT fk_scrap_production_order
  FOREIGN KEY (production_order_id) REFERENCES pp.production_orders(id);

-- wms → mm: batches.gr_id
ALTER TABLE wms.batches
  ADD CONSTRAINT fk_batch_goods_receipt
  FOREIGN KEY (gr_id) REFERENCES mm.goods_receipts(id);

-- tms → wms: logistics_release_items.batch_id
ALTER TABLE tms.logistics_release_items
  ADD CONSTRAINT fk_lri_batch
  FOREIGN KEY (batch_id) REFERENCES wms.batches(id);

-- tms → wms: logistics_release_items.from_bin_id
ALTER TABLE tms.logistics_release_items
  ADD CONSTRAINT fk_lri_from_bin
  FOREIGN KEY (from_bin_id) REFERENCES wms.storage_bins(id);

-- shared → pp: goods_master.default_bom_id
ALTER TABLE shared.goods_master
  ADD CONSTRAINT fk_goods_default_bom
  FOREIGN KEY (default_bom_id) REFERENCES pp.bom_headers(id);
