-- ============================================================================
-- Migration 015: Triggers — Reservations -> Quants Reserved Qty
--
-- BUSINESS LOGIC:
--   When a reservation (mm.reservations) is created, updated, or deleted,
--   automatically adjust wms.quants.reserved_qty for the relevant quant.
--
--   reserved_qty tracks how much stock is "spoken for" by open reservations.
--   available_qty = system_qty - reserved_qty - blocked_qty (GENERATED column).
--
--   Only reservations with status IN ('open', 'partially_withdrawn') contribute
--   to reserved_qty. The open quantity for a reservation is:
--     open_qty = requirement_qty - COALESCE(withdrawn_qty, 0)
--
-- Dependencies:
--   007_wms_schema.sql   (wms.quants)
--   008_mm_schema.sql    (mm.reservations)
-- ============================================================================


-- ---------------------------------------------------------------------------
-- 1. Trigger function: wms.fn_update_reserved_qty
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION wms.fn_update_reserved_qty()
RETURNS TRIGGER AS $$
DECLARE
  v_old_open_qty  INTEGER := 0;
  v_new_open_qty  INTEGER := 0;
  v_delta         INTEGER;
  v_parts_id      UUID;
  v_bin_id        UUID;
BEGIN
  -- -----------------------------------------------------------------------
  -- Calculate the OLD open (unreleased) quantity
  -- Only count reservations that are actively reserving stock
  -- -----------------------------------------------------------------------
  IF TG_OP = 'UPDATE' OR TG_OP = 'DELETE' THEN
    IF OLD.status IN ('open', 'partially_withdrawn') THEN
      v_old_open_qty := GREATEST(OLD.requirement_qty - COALESCE(OLD.withdrawn_qty, 0), 0);
    END IF;
  END IF;

  -- -----------------------------------------------------------------------
  -- Calculate the NEW open (unreleased) quantity
  -- -----------------------------------------------------------------------
  IF TG_OP = 'INSERT' OR TG_OP = 'UPDATE' THEN
    IF NEW.status IN ('open', 'partially_withdrawn') THEN
      v_new_open_qty := GREATEST(NEW.requirement_qty - COALESCE(NEW.withdrawn_qty, 0), 0);
    END IF;
  END IF;

  -- -----------------------------------------------------------------------
  -- Compute delta and apply
  -- -----------------------------------------------------------------------
  v_delta := v_new_open_qty - v_old_open_qty;

  IF v_delta = 0 THEN
    -- No change to reserved qty
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
  END IF;

  -- -----------------------------------------------------------------------
  -- Determine which quant to update
  -- On UPDATE, the bin may have changed; handle both old and new bin
  -- -----------------------------------------------------------------------
  IF TG_OP = 'UPDATE'
     AND OLD.storage_bin_id IS DISTINCT FROM NEW.storage_bin_id
  THEN
    -- Bin changed: release old reservation, apply new reservation
    -- Release from old bin
    IF OLD.storage_bin_id IS NOT NULL AND v_old_open_qty > 0 THEN
      UPDATE wms.quants
      SET reserved_qty = GREATEST(reserved_qty - v_old_open_qty, 0),
          updated_at   = NOW()
      WHERE parts_id       = OLD.parts_id
        AND storage_bin_id = OLD.storage_bin_id
        AND stock_type     = 'unrestricted';
    END IF;
    -- Reserve at new bin
    IF NEW.storage_bin_id IS NOT NULL AND v_new_open_qty > 0 THEN
      UPDATE wms.quants
      SET reserved_qty = GREATEST(reserved_qty + v_new_open_qty, 0),
          updated_at   = NOW()
      WHERE parts_id       = NEW.parts_id
        AND storage_bin_id = NEW.storage_bin_id
        AND stock_type     = 'unrestricted';
    END IF;
  ELSE
    -- Same bin (or only one operation side has a bin)
    IF TG_OP IN ('INSERT', 'UPDATE') AND NEW.storage_bin_id IS NOT NULL THEN
      v_parts_id := NEW.parts_id;
      v_bin_id   := NEW.storage_bin_id;
    ELSIF TG_OP = 'DELETE' AND OLD.storage_bin_id IS NOT NULL THEN
      v_parts_id := OLD.parts_id;
      v_bin_id   := OLD.storage_bin_id;
    ELSE
      -- No bin specified; cannot update quants
      IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END IF;

    UPDATE wms.quants
    SET reserved_qty = GREATEST(reserved_qty + v_delta, 0),
        updated_at   = NOW()
    WHERE parts_id       = v_parts_id
      AND storage_bin_id = v_bin_id
      AND stock_type     = 'unrestricted';
  END IF;

  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION wms.fn_update_reserved_qty IS 'Trigger fn: sync wms.quants.reserved_qty with mm.reservations open quantity changes';


-- ---------------------------------------------------------------------------
-- 2. Create the trigger on mm.reservations
-- ---------------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_reservation_update_reserved ON mm.reservations;

CREATE TRIGGER trg_reservation_update_reserved
  AFTER INSERT OR UPDATE OR DELETE ON mm.reservations
  FOR EACH ROW
  EXECUTE FUNCTION wms.fn_update_reserved_qty();

COMMENT ON TRIGGER trg_reservation_update_reserved ON mm.reservations
  IS 'Auto-sync wms.quants.reserved_qty when reservations are created, modified, or deleted';
