"""Tests for harness.dispatch.product_loader."""
from __future__ import annotations
import time
from unittest.mock import patch

from harness.dispatch import product_loader
from harness.dispatch.product_loader import ProductCache, invalidate, load


@patch("harness.dispatch.product_loader.load_product_lookup")
def test_load_returns_cache_with_data(mock_load):
    """C1: load() returns cache populated with lookup data."""
    invalidate()
    mock_load.return_value = {
        "굿이너프 비치타월".lower(): {"rec_id": "recA", "cbm_per_box": 0.0493, "qty_per_box": 40},
        "WLMW".lower(): {"rec_id": "recA", "cbm_per_box": 0.0493, "qty_per_box": 40},
    }
    cache = load({"Authorization": "Bearer fake"})
    assert isinstance(cache, ProductCache)
    assert len(cache.lookup) == 2
    assert not cache.is_stale()
    invalidate()


@patch("harness.dispatch.product_loader.load_product_lookup")
def test_cache_hit_on_second_call(mock_load):
    """C1: 2nd call within TTL returns cached without re-fetch."""
    invalidate()
    mock_load.return_value = {"a": {"rec_id": "r1", "cbm_per_box": 0.1, "qty_per_box": 10}}
    load({"Authorization": "fake"})
    load({"Authorization": "fake"})
    assert mock_load.call_count == 1
    invalidate()


@patch("harness.dispatch.product_loader.load_product_lookup")
def test_force_reload_bypasses_cache(mock_load):
    """force=True bypasses TTL and re-fetches."""
    invalidate()
    mock_load.return_value = {"a": {"rec_id": "r1", "cbm_per_box": 0.1, "qty_per_box": 10}}
    load({"Authorization": "fake"})
    load({"Authorization": "fake"}, force=True)
    assert mock_load.call_count == 2
    invalidate()


@patch("harness.dispatch.product_loader.load_product_lookup")
def test_invalidate_marks_stale(mock_load):
    """invalidate() makes is_stale() return True."""
    invalidate()
    mock_load.return_value = {"a": {"rec_id": "r1", "cbm_per_box": 0.1, "qty_per_box": 10}}
    cache = load({"Authorization": "fake"})
    assert not cache.is_stale()
    invalidate()
    assert cache.is_stale()


@patch("harness.dispatch.product_loader.load_product_lookup")
def test_stale_while_revalidate_on_fetch_failure(mock_load):
    """If fetch fails AFTER initial success, stale cache is returned."""
    invalidate()
    mock_load.return_value = {"a": {"rec_id": "r1", "cbm_per_box": 0.1, "qty_per_box": 10}}
    load({"Authorization": "fake"})
    # Force stale by zeroing loaded_at
    product_loader._CACHE.loaded_at = 0.0
    mock_load.side_effect = RuntimeError("Airtable rate limit")
    cache = load({"Authorization": "fake"})
    assert cache.lookup  # stale data preserved
    assert mock_load.call_count == 2
    # Reset for other tests
    mock_load.side_effect = None
    invalidate()


@patch("harness.dispatch.product_loader.load_product_lookup")
def test_initial_fetch_failure_raises(mock_load):
    """If fetch fails with NO prior cache, exception propagates (no stale fallback)."""
    # Fully reset cache (invalidate() only resets loaded_at; for true cold start we
    # must also clear .lookup since the module is process-global)
    product_loader._CACHE.lookup = {}
    product_loader._CACHE.loaded_at = 0.0
    mock_load.side_effect = RuntimeError("Airtable down")
    try:
        load({"Authorization": "fake"})
        assert False, "expected RuntimeError"
    except RuntimeError:
        pass
    mock_load.side_effect = None
    invalidate()
