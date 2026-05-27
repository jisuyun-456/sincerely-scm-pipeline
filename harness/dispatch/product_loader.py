"""Product 캐시 — 24h TTL, stale-while-revalidate.

`cbm_calc.load_product_lookup`은 Airtable 호출 비용이 있으므로 process-level
캐시로 감싼다. fetch 실패 시 기존 캐시가 있으면 stale 사용.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from harness.settlement.cbm_calc import load_product_lookup

_DEFAULT_TTL_SEC = 86400  # 24h


@dataclass
class ProductCache:
    lookup: dict = field(default_factory=dict)
    loaded_at: float = 0.0
    ttl_sec: int = _DEFAULT_TTL_SEC

    def is_stale(self) -> bool:
        return time.time() - self.loaded_at > self.ttl_sec


_CACHE = ProductCache()


def load(headers: dict, force: bool = False) -> ProductCache:
    """Load Product cache. Stale-while-revalidate on fetch failure."""
    if not force and not _CACHE.is_stale() and _CACHE.lookup:
        return _CACHE
    try:
        _CACHE.lookup = load_product_lookup(headers)
        _CACHE.loaded_at = time.time()
    except Exception as e:
        if _CACHE.lookup:
            print(f"WARN: Product fetch failed, using stale cache: {e}")
        else:
            raise
    return _CACHE


def invalidate() -> None:
    _CACHE.loaded_at = 0.0
