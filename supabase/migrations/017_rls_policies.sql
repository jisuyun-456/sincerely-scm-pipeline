-- ============================================================================
-- Migration 017: Row Level Security (RLS) Policies
--
-- SCM 시스템 전체 테이블에 대한 RLS 정책 설정
-- 6개 schema, ~51개 테이블 중 주요 운영 테이블 대상
--
-- Strategy:
--   1. Enable RLS on main operational tables (NOT reference/config tables)
--   2. Authenticated users get SELECT on all data
--   3. Write policies are role-based (future: custom_access_token_hook)
--   4. Finance tables have restricted write (finance team only)
--
-- Excluded from RLS (reference/config — globally readable, admin-writable):
--   shared: organizations, users, gl_accounts, material_types,
--           material_groups, units_of_measure, locations
--   tms:    carriers, dispatch_schedules, packaging_materials, routes
--   wms:    warehouses, storage_types, storage_bins, batches
--   pp:     bom_headers, bom_items, work_centers, routings
--   finance: cost_settings
--
-- NOTE: Retool service account connects as authenticated user.
--       Service role (supabase admin) bypasses RLS entirely.
--
-- Dependencies:
--   001_create_schemas.sql
--   002–011 (all table-creation migrations)
-- ============================================================================


-- ============================================================================
-- SECTION 1: ENABLE ROW LEVEL SECURITY
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1a. shared schema
-- ---------------------------------------------------------------------------
ALTER TABLE shared.projects            ENABLE ROW LEVEL SECURITY;
ALTER TABLE shared.clients             ENABLE ROW LEVEL SECURITY;
ALTER TABLE shared.vendors             ENABLE ROW LEVEL SECURITY;
ALTER TABLE shared.goods_master        ENABLE ROW LEVEL SECURITY;
ALTER TABLE shared.item_master         ENABLE ROW LEVEL SECURITY;
ALTER TABLE shared.parts_master        ENABLE ROW LEVEL SECURITY;
ALTER TABLE shared.material_valuation  ENABLE ROW LEVEL SECURITY;
ALTER TABLE shared.vendor_evaluations  ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 1b. tms schema
-- ---------------------------------------------------------------------------
ALTER TABLE tms.transportation_requirements  ENABLE ROW LEVEL SECURITY;
ALTER TABLE tms.freight_orders               ENABLE ROW LEVEL SECURITY;
ALTER TABLE tms.logistics_releases           ENABLE ROW LEVEL SECURITY;
ALTER TABLE tms.logistics_release_items      ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 1c. wms schema
-- ---------------------------------------------------------------------------
ALTER TABLE wms.quants                ENABLE ROW LEVEL SECURITY;
ALTER TABLE wms.inventory_count_docs  ENABLE ROW LEVEL SECURITY;
ALTER TABLE wms.inventory_count_items ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 1d. mm schema
-- ---------------------------------------------------------------------------
ALTER TABLE mm.purchase_requisitions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE mm.purchase_orders        ENABLE ROW LEVEL SECURITY;
ALTER TABLE mm.purchase_order_items   ENABLE ROW LEVEL SECURITY;
ALTER TABLE mm.goods_receipts         ENABLE ROW LEVEL SECURITY;
ALTER TABLE mm.stock_movements        ENABLE ROW LEVEL SECURITY;
ALTER TABLE mm.invoice_verifications  ENABLE ROW LEVEL SECURITY;
ALTER TABLE mm.reservations           ENABLE ROW LEVEL SECURITY;
ALTER TABLE mm.return_orders          ENABLE ROW LEVEL SECURITY;
ALTER TABLE mm.quality_inspections    ENABLE ROW LEVEL SECURITY;
ALTER TABLE mm.scrap_records          ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 1e. pp schema
-- ---------------------------------------------------------------------------
ALTER TABLE pp.production_orders            ENABLE ROW LEVEL SECURITY;
ALTER TABLE pp.production_order_components  ENABLE ROW LEVEL SECURITY;
ALTER TABLE pp.production_confirmations     ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 1f. finance schema
-- ---------------------------------------------------------------------------
ALTER TABLE finance.accounting_entries  ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.douzone_sync_log   ENABLE ROW LEVEL SECURITY;
ALTER TABLE finance.period_closes      ENABLE ROW LEVEL SECURITY;


-- ============================================================================
-- SECTION 2: SELECT POLICIES — Authenticated read access on all RLS tables
-- ============================================================================
-- All authenticated users (including Retool service account) can read all data.
-- auth.role() returns 'authenticated' for any logged-in user in Supabase.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 2a. shared schema — SELECT
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_read_projects"
    ON shared.projects FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_clients"
    ON shared.clients FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_vendors"
    ON shared.vendors FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_goods_master"
    ON shared.goods_master FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_item_master"
    ON shared.item_master FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_parts_master"
    ON shared.parts_master FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_material_valuation"
    ON shared.material_valuation FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_vendor_evaluations"
    ON shared.vendor_evaluations FOR SELECT
    USING (auth.role() = 'authenticated');

-- ---------------------------------------------------------------------------
-- 2b. tms schema — SELECT
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_read_transportation_requirements"
    ON tms.transportation_requirements FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_freight_orders"
    ON tms.freight_orders FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_logistics_releases"
    ON tms.logistics_releases FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_logistics_release_items"
    ON tms.logistics_release_items FOR SELECT
    USING (auth.role() = 'authenticated');

-- ---------------------------------------------------------------------------
-- 2c. wms schema — SELECT
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_read_quants"
    ON wms.quants FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_inventory_count_docs"
    ON wms.inventory_count_docs FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_inventory_count_items"
    ON wms.inventory_count_items FOR SELECT
    USING (auth.role() = 'authenticated');

-- ---------------------------------------------------------------------------
-- 2d. mm schema — SELECT
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_read_purchase_requisitions"
    ON mm.purchase_requisitions FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_purchase_orders"
    ON mm.purchase_orders FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_purchase_order_items"
    ON mm.purchase_order_items FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_goods_receipts"
    ON mm.goods_receipts FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_stock_movements"
    ON mm.stock_movements FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_invoice_verifications"
    ON mm.invoice_verifications FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_reservations"
    ON mm.reservations FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_return_orders"
    ON mm.return_orders FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_quality_inspections"
    ON mm.quality_inspections FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_scrap_records"
    ON mm.scrap_records FOR SELECT
    USING (auth.role() = 'authenticated');

-- ---------------------------------------------------------------------------
-- 2e. pp schema — SELECT
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_read_production_orders"
    ON pp.production_orders FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_production_order_components"
    ON pp.production_order_components FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_production_confirmations"
    ON pp.production_confirmations FOR SELECT
    USING (auth.role() = 'authenticated');

-- ---------------------------------------------------------------------------
-- 2f. finance schema — SELECT
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_read_accounting_entries"
    ON finance.accounting_entries FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_douzone_sync_log"
    ON finance.douzone_sync_log FOR SELECT
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_read_period_closes"
    ON finance.period_closes FOR SELECT
    USING (auth.role() = 'authenticated');


-- ============================================================================
-- SECTION 3: WRITE POLICIES — Operational tables (non-finance)
-- ============================================================================
-- All authenticated users can INSERT/UPDATE/DELETE on operational tables.
-- Future: replace with role-based checks via custom_access_token_hook
--         e.g., (auth.jwt() ->> 'user_role') IN ('scm_admin', 'mm_manager')
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 3a. shared schema — INSERT / UPDATE / DELETE
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_insert_projects"
    ON shared.projects FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_projects"
    ON shared.projects FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_projects"
    ON shared.projects FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_clients"
    ON shared.clients FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_clients"
    ON shared.clients FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_clients"
    ON shared.clients FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_vendors"
    ON shared.vendors FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_vendors"
    ON shared.vendors FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_vendors"
    ON shared.vendors FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_goods_master"
    ON shared.goods_master FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_goods_master"
    ON shared.goods_master FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_goods_master"
    ON shared.goods_master FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_item_master"
    ON shared.item_master FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_item_master"
    ON shared.item_master FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_item_master"
    ON shared.item_master FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_parts_master"
    ON shared.parts_master FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_parts_master"
    ON shared.parts_master FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_parts_master"
    ON shared.parts_master FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_material_valuation"
    ON shared.material_valuation FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_material_valuation"
    ON shared.material_valuation FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_material_valuation"
    ON shared.material_valuation FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_vendor_evaluations"
    ON shared.vendor_evaluations FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_vendor_evaluations"
    ON shared.vendor_evaluations FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_vendor_evaluations"
    ON shared.vendor_evaluations FOR DELETE
    USING (auth.role() = 'authenticated');

-- ---------------------------------------------------------------------------
-- 3b. tms schema — INSERT / UPDATE / DELETE
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_insert_transportation_requirements"
    ON tms.transportation_requirements FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_transportation_requirements"
    ON tms.transportation_requirements FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_transportation_requirements"
    ON tms.transportation_requirements FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_freight_orders"
    ON tms.freight_orders FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_freight_orders"
    ON tms.freight_orders FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_freight_orders"
    ON tms.freight_orders FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_logistics_releases"
    ON tms.logistics_releases FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_logistics_releases"
    ON tms.logistics_releases FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_logistics_releases"
    ON tms.logistics_releases FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_logistics_release_items"
    ON tms.logistics_release_items FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_logistics_release_items"
    ON tms.logistics_release_items FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_logistics_release_items"
    ON tms.logistics_release_items FOR DELETE
    USING (auth.role() = 'authenticated');

-- ---------------------------------------------------------------------------
-- 3c. wms schema — INSERT / UPDATE / DELETE
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_insert_quants"
    ON wms.quants FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_quants"
    ON wms.quants FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_quants"
    ON wms.quants FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_inventory_count_docs"
    ON wms.inventory_count_docs FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_inventory_count_docs"
    ON wms.inventory_count_docs FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_inventory_count_docs"
    ON wms.inventory_count_docs FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_inventory_count_items"
    ON wms.inventory_count_items FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_inventory_count_items"
    ON wms.inventory_count_items FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_inventory_count_items"
    ON wms.inventory_count_items FOR DELETE
    USING (auth.role() = 'authenticated');

-- ---------------------------------------------------------------------------
-- 3d. mm schema — INSERT / UPDATE / DELETE
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_insert_purchase_requisitions"
    ON mm.purchase_requisitions FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_purchase_requisitions"
    ON mm.purchase_requisitions FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_purchase_requisitions"
    ON mm.purchase_requisitions FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_purchase_orders"
    ON mm.purchase_orders FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_purchase_orders"
    ON mm.purchase_orders FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_purchase_orders"
    ON mm.purchase_orders FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_purchase_order_items"
    ON mm.purchase_order_items FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_purchase_order_items"
    ON mm.purchase_order_items FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_purchase_order_items"
    ON mm.purchase_order_items FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_goods_receipts"
    ON mm.goods_receipts FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_goods_receipts"
    ON mm.goods_receipts FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_goods_receipts"
    ON mm.goods_receipts FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_stock_movements"
    ON mm.stock_movements FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_stock_movements"
    ON mm.stock_movements FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_stock_movements"
    ON mm.stock_movements FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_invoice_verifications"
    ON mm.invoice_verifications FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_invoice_verifications"
    ON mm.invoice_verifications FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_invoice_verifications"
    ON mm.invoice_verifications FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_reservations"
    ON mm.reservations FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_reservations"
    ON mm.reservations FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_reservations"
    ON mm.reservations FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_return_orders"
    ON mm.return_orders FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_return_orders"
    ON mm.return_orders FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_return_orders"
    ON mm.return_orders FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_quality_inspections"
    ON mm.quality_inspections FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_quality_inspections"
    ON mm.quality_inspections FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_quality_inspections"
    ON mm.quality_inspections FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_scrap_records"
    ON mm.scrap_records FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_scrap_records"
    ON mm.scrap_records FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_scrap_records"
    ON mm.scrap_records FOR DELETE
    USING (auth.role() = 'authenticated');

-- ---------------------------------------------------------------------------
-- 3e. pp schema — INSERT / UPDATE / DELETE
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_insert_production_orders"
    ON pp.production_orders FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_production_orders"
    ON pp.production_orders FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_production_orders"
    ON pp.production_orders FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_production_order_components"
    ON pp.production_order_components FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_production_order_components"
    ON pp.production_order_components FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_production_order_components"
    ON pp.production_order_components FOR DELETE
    USING (auth.role() = 'authenticated');

CREATE POLICY "authenticated_insert_production_confirmations"
    ON pp.production_confirmations FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_production_confirmations"
    ON pp.production_confirmations FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_delete_production_confirmations"
    ON pp.production_confirmations FOR DELETE
    USING (auth.role() = 'authenticated');


-- ============================================================================
-- SECTION 4: FINANCE WRITE POLICIES — Restricted access
-- ============================================================================
-- Finance tables have tighter write controls:
--   - accounting_entries: INSERT allowed, UPDATE restricted to status transitions
--     (draft -> reviewed -> posted), DELETE not allowed
--   - douzone_sync_log: INSERT/UPDATE allowed (sync operations), DELETE not allowed
--   - period_closes: INSERT/UPDATE allowed (closing workflow), DELETE not allowed
--
-- Future: replace auth.role() checks with JWT role claims:
--   (auth.jwt() ->> 'user_role') IN ('finance_manager', 'finance_admin')
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 4a. finance.accounting_entries — INSERT (draft entries only)
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_insert_accounting_entries"
    ON finance.accounting_entries FOR INSERT
    WITH CHECK (
        auth.role() = 'authenticated'
        AND status = 'draft'                      -- new entries must start as draft
    );

-- ---------------------------------------------------------------------------
-- 4b. finance.accounting_entries — UPDATE
--     NOTE: PostgreSQL RLS WITH CHECK cannot reference OLD.
--     Status transition enforcement (draft→reviewed→posted) is handled by
--     a BEFORE UPDATE trigger instead. RLS only checks authentication.
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_update_accounting_entries"
    ON finance.accounting_entries FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

-- Status transition enforcement via trigger (replaces invalid OLD in RLS)
CREATE OR REPLACE FUNCTION finance.fn_enforce_entry_status_transition()
RETURNS TRIGGER AS $$
BEGIN
  -- Allowed transitions: draft→reviewed, reviewed→posted, posted→posted (douzone_slip_no backfill)
  IF NOT (
    (OLD.status = 'draft' AND NEW.status = 'reviewed')
    OR (OLD.status = 'reviewed' AND NEW.status = 'posted')
    OR (OLD.status = 'posted' AND NEW.status = 'posted')
  ) THEN
    RAISE EXCEPTION 'Invalid status transition: % → %', OLD.status, NEW.status;
  END IF;

  -- Protect immutable fields on posted entries (only douzone_slip_no can change)
  IF OLD.status = 'posted' THEN
    IF NEW.amount <> OLD.amount
       OR NEW.debit_account_id <> OLD.debit_account_id
       OR NEW.credit_account_id <> OLD.credit_account_id
       OR NEW.entry_type <> OLD.entry_type THEN
      RAISE EXCEPTION 'Cannot modify immutable fields on posted accounting entries';
    END IF;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_enforce_entry_status ON finance.accounting_entries;
CREATE TRIGGER trg_enforce_entry_status
  BEFORE UPDATE ON finance.accounting_entries
  FOR EACH ROW
  EXECUTE FUNCTION finance.fn_enforce_entry_status_transition();

-- NOTE: No DELETE policy on accounting_entries — posted entries must never be deleted.
-- Use reversal entries (is_reversal = TRUE) instead.

-- ---------------------------------------------------------------------------
-- 4c. finance.douzone_sync_log — INSERT / UPDATE (sync operations)
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_insert_douzone_sync_log"
    ON finance.douzone_sync_log FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "authenticated_update_douzone_sync_log"
    ON finance.douzone_sync_log FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

-- NOTE: No DELETE policy on douzone_sync_log — audit trail must be preserved.

-- ---------------------------------------------------------------------------
-- 4d. finance.period_closes — INSERT / UPDATE (closing workflow)
-- ---------------------------------------------------------------------------
CREATE POLICY "authenticated_insert_period_closes"
    ON finance.period_closes FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

-- UPDATE only allowed when period is NOT yet closed
-- Once is_closed = TRUE, the record becomes immutable
CREATE POLICY "authenticated_update_period_closes"
    ON finance.period_closes FOR UPDATE
    USING (
        auth.role() = 'authenticated'
        AND is_closed = FALSE                     -- cannot modify closed periods
    )
    WITH CHECK (auth.role() = 'authenticated');

-- NOTE: No DELETE policy on period_closes — closing snapshots must be preserved.


-- ============================================================================
-- SECTION 5: FORCE RLS FOR TABLE OWNERS
-- ============================================================================
-- By default, table owners bypass RLS. FORCE ROW LEVEL SECURITY ensures
-- that even the table owner (postgres role) is subject to policies.
-- This is a safety net — Retool and application code should never use
-- the postgres role directly, but this prevents accidental bypass.
--
-- NOTE: Supabase service_role key still bypasses RLS regardless of this
-- setting, which is the intended behavior for admin/migration operations.
-- ============================================================================

-- shared
ALTER TABLE shared.projects            FORCE ROW LEVEL SECURITY;
ALTER TABLE shared.clients             FORCE ROW LEVEL SECURITY;
ALTER TABLE shared.vendors             FORCE ROW LEVEL SECURITY;
ALTER TABLE shared.goods_master        FORCE ROW LEVEL SECURITY;
ALTER TABLE shared.item_master         FORCE ROW LEVEL SECURITY;
ALTER TABLE shared.parts_master        FORCE ROW LEVEL SECURITY;
ALTER TABLE shared.material_valuation  FORCE ROW LEVEL SECURITY;
ALTER TABLE shared.vendor_evaluations  FORCE ROW LEVEL SECURITY;

-- tms
ALTER TABLE tms.transportation_requirements  FORCE ROW LEVEL SECURITY;
ALTER TABLE tms.freight_orders               FORCE ROW LEVEL SECURITY;
ALTER TABLE tms.logistics_releases           FORCE ROW LEVEL SECURITY;
ALTER TABLE tms.logistics_release_items      FORCE ROW LEVEL SECURITY;

-- wms
ALTER TABLE wms.quants                FORCE ROW LEVEL SECURITY;
ALTER TABLE wms.inventory_count_docs  FORCE ROW LEVEL SECURITY;
ALTER TABLE wms.inventory_count_items FORCE ROW LEVEL SECURITY;

-- mm
ALTER TABLE mm.purchase_requisitions  FORCE ROW LEVEL SECURITY;
ALTER TABLE mm.purchase_orders        FORCE ROW LEVEL SECURITY;
ALTER TABLE mm.purchase_order_items   FORCE ROW LEVEL SECURITY;
ALTER TABLE mm.goods_receipts         FORCE ROW LEVEL SECURITY;
ALTER TABLE mm.stock_movements        FORCE ROW LEVEL SECURITY;
ALTER TABLE mm.invoice_verifications  FORCE ROW LEVEL SECURITY;
ALTER TABLE mm.reservations           FORCE ROW LEVEL SECURITY;
ALTER TABLE mm.return_orders          FORCE ROW LEVEL SECURITY;
ALTER TABLE mm.quality_inspections    FORCE ROW LEVEL SECURITY;
ALTER TABLE mm.scrap_records          FORCE ROW LEVEL SECURITY;

-- pp
ALTER TABLE pp.production_orders            FORCE ROW LEVEL SECURITY;
ALTER TABLE pp.production_order_components  FORCE ROW LEVEL SECURITY;
ALTER TABLE pp.production_confirmations     FORCE ROW LEVEL SECURITY;

-- finance
ALTER TABLE finance.accounting_entries  FORCE ROW LEVEL SECURITY;
ALTER TABLE finance.douzone_sync_log   FORCE ROW LEVEL SECURITY;
ALTER TABLE finance.period_closes      FORCE ROW LEVEL SECURITY;


-- ============================================================================
-- SUMMARY
-- ============================================================================
-- Tables with RLS enabled:              31
--   shared:   8 tables
--   tms:      4 tables
--   wms:      3 tables
--   mm:      10 tables
--   pp:       3 tables
--   finance:  3 tables
--
-- Policy counts:
--   SELECT policies:                    31 (one per table, authenticated read)
--   INSERT policies:                    31 (28 general + 3 finance-specific)
--   UPDATE policies:                    31 (28 general + 3 finance-specific)
--   DELETE policies:                    28 (non-finance tables only)
--   Total policies:                    121
--
-- Finance restrictions:
--   - accounting_entries: INSERT draft only, UPDATE status transitions only, no DELETE
--   - douzone_sync_log:  INSERT/UPDATE only, no DELETE (audit trail)
--   - period_closes:     INSERT/UPDATE only (UPDATE blocked when is_closed=TRUE), no DELETE
--
-- Tables WITHOUT RLS (reference/config — admin-managed):
--   shared: organizations, users, gl_accounts, material_types,
--           material_groups, units_of_measure, locations
--   tms:    carriers, dispatch_schedules, packaging_materials, routes
--   wms:    warehouses, storage_types, storage_bins, batches
--   pp:     bom_headers, bom_items, work_centers, routings
--   finance: cost_settings
--
-- Future enhancements:
--   1. Add custom_access_token_hook to embed user_role in JWT
--   2. Replace auth.role() = 'authenticated' with role-based checks:
--      (auth.jwt() ->> 'user_role') IN ('scm_admin', 'mm_manager', ...)
--   3. Add row-level filtering (e.g., users see only their organization's data)
-- ============================================================================
