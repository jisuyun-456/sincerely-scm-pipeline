from __future__ import annotations
from typing import TYPE_CHECKING

from harness._core.logger import StructuredLogger

if TYPE_CHECKING:
    from harness._core.airtable import AirtableClient

_log = StructuredLogger("views")


class ViewNotFoundError(Exception):
    pass


class SilentDropError(Exception):
    pass


class AirtableViewRegistry:
    def __init__(self, client: "AirtableClient") -> None:
        self._client = client
        self._registry: dict[str, str] = {}  # name → view_id

    def register(self, name: str, view_id: str) -> None:
        self._registry[name] = view_id

    def validate_all(self) -> None:
        """Verify all registered view IDs still exist in the Airtable metadata."""
        if not self._registry:
            return
        try:
            from harness._core.airtable import _global_limiter
            _global_limiter.acquire()
            resp = self._client._meta_session.get(
                f"/bases/{self._client.base_id}/tables"
            )
            tables_data = resp.json().get("tables", [])
            # Build set of all view IDs in this base
            live_view_ids: set[str] = {
                v["id"]
                for t in tables_data
                for v in t.get("views", [])
            }
            for name, view_id in self._registry.items():
                if view_id not in live_view_ids:
                    raise ViewNotFoundError(
                        f"View {name!r} (id={view_id!r}) not found in base "
                        f"{self._client.base_id!r}. "
                        "View may have been deleted or recreated."
                    )
            _log.info(
                "view validation passed",
                count=len(self._registry),
            )
        except ViewNotFoundError:
            raise
        except Exception as exc:
            _log.warning("view validation failed (non-fatal)", error=str(exc))

    def fetch_view(self, view_id: str) -> list[dict]:
        """Paginated fetch by view ID with silent-zero-record detection."""
        records = self._client.get_records(view_id=view_id)
        if len(records) == 0:
            # Cross-check: is the table actually empty, or is the view broken?
            from harness._core.airtable import _global_limiter
            _global_limiter.acquire()
            all_records = self._client.get_records()  # no view filter
            if len(all_records) > 0:
                raise SilentDropError(
                    f"View {view_id!r} returned 0 records but table has "
                    f"{len(all_records)} unfiltered records. "
                    "View filter or ID may be invalid."
                )
        return records
