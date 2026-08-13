"""Repo-wide pytest fixtures.

Why this file exists (deliberate exception to this repo's "no conftest.py"
convention): `harness/backbone/product_alias.resolve_product_entry` (stage
1.5) calls `harness.backbone.crosswalk_store.load_crosswalk()`, which by
default reads the real SSOT file `data/crosswalk/goods_crosswalk.csv` from
the repo root. That CSV is edited by humans as the governance mechanism for
promoting rows from '미검증' to '확정' — it is live, changing data, not a
fixture. If unit tests read it unguarded, they silently depend on whatever
rows happen to be confirmed on a given day and will keep breaking
unpredictably as the file evolves (this happened in commit ca87ef4, which
added ~1,394 rows and broke 5 previously-passing tests).

The autouse fixture below neutralizes the crosswalk for every test by
default, so tests get the pre-1.5-stage behavior unless they explicitly
opt in (as `tests/backbone/test_product_alias.py`'s crosswalk-stage tests
do via their own `monkeypatch.setattr(pa, "load_crosswalk", ...)`, which
overrides this fixture within that test).
"""
import pytest

import harness.backbone.crosswalk_store as crosswalk_store
import harness.backbone.product_alias as product_alias


@pytest.fixture(autouse=True)
def _no_live_crosswalk(monkeypatch):
    """Prevent tests from reading the real data/crosswalk/goods_crosswalk.csv.

    Patches the `load_crosswalk` name bound inside `product_alias` (that is
    the binding stage 1.5 actually calls, per its
    `from harness.backbone.crosswalk_store import load_crosswalk` import) to
    return {}, and clears crosswalk_store's parse cache before and after
    each test so no cached parse leaks across tests.
    """
    crosswalk_store.clear_cache()
    monkeypatch.setattr(product_alias, "load_crosswalk", lambda: {})
    yield
    crosswalk_store.clear_cache()
