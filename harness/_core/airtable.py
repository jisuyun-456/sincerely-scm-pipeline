from __future__ import annotations
import hashlib
import json
import pathlib
import threading
import time
from collections import deque
from typing import ClassVar

from harness._core.config import ConfigError
from harness._core.http_session import AuthError, HttpSession
from harness._core.logger import StructuredLogger

_BASE_URL = "https://api.airtable.com/v0"
_META_URL = "https://api.airtable.com/v0/meta"
_SCHEMA_PIN = pathlib.Path(__file__).parent / "schema_pin.json"

_log = StructuredLogger("airtable")


class SchemaError(Exception):
    pass


class AuditTableMissingError(Exception):
    pass


class _RateLimiter:
    """In-process 3 req/s sliding-window limiter (thread-safe).

    Cross-process file-based limiting (binary circular buffer) is deferred
    to a future hardening pass; sufficient for current single-process usage.
    """

    def __init__(self, max_rps: float = 3.0) -> None:
        self._max_rps = max_rps
        self._window = 1.0 / max_rps
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            # Evict timestamps older than 1 second
            while self._timestamps and now - self._timestamps[0] >= 1.0:
                self._timestamps.popleft()
            if len(self._timestamps) >= int(self._max_rps):
                sleep_for = 1.0 - (now - self._timestamps[0])
                if sleep_for > 0:
                    time.sleep(sleep_for)
            self._timestamps.append(time.monotonic())


_global_limiter = _RateLimiter(max_rps=3.0)


class AirtableClient:
    _instances: ClassVar[dict[tuple[str, str], "AirtableClient"]] = {}
    _schema_checked: ClassVar[set[tuple[str, str]]] = set()

    def __init__(self, base_id: str, table_id: str, pat: str) -> None:
        self.base_id = base_id
        self.table_id = table_id
        self._pat = pat
        self._session = HttpSession(
            base_url=f"{_BASE_URL}/{base_id}/{table_id}"
        )
        self._session._session.headers.update(
            {"Authorization": f"Bearer {pat}", "Content-Type": "application/json"}
        )
        self._meta_session = HttpSession(base_url=_META_URL)
        self._meta_session._session.headers.update(
            {"Authorization": f"Bearer {pat}"}
        )

    @classmethod
    def get_or_create(
        cls, base_id: str, table_id: str, pat: str
    ) -> "AirtableClient":
        key = (base_id, table_id)
        if key not in cls._instances:
            cls._instances[key] = cls(base_id, table_id, pat)
        return cls._instances[key]

    def _check_response(self, data: dict) -> None:
        if "error" in data:
            err = data["error"]
            raise SchemaError(
                f"Airtable returned error in 200 OK: {err}"
            )

    def get_records(
        self,
        view_id: str | None = None,
        filter_formula: str | None = None,
        fields: list[str] | None = None,
        return_fields_by_field_id: bool = False,
    ) -> list[dict]:
        params: dict = {}
        if view_id:
            params["view"] = view_id
        if filter_formula:
            params["filterByFormula"] = filter_formula
        if fields:
            for f in fields:
                params.setdefault("fields[]", []).append(f)
        if return_fields_by_field_id:
            params["returnFieldsByFieldId"] = "true"

        records: list[dict] = []
        offset: str | None = None
        while True:
            if offset:
                params["offset"] = offset
            _global_limiter.acquire()
            resp = self._session.get("", params=params)
            data = resp.json()
            self._check_response(data)
            records.extend(data.get("records", []))
            offset = data.get("offset")
            if not offset:
                break
        return records

    def patch_record(
        self,
        record_id: str,
        fields: dict,
        idempotency_key: str | None = None,
    ) -> dict:
        if idempotency_key is None:
            raw = (
                self.base_id
                + self.table_id
                + record_id
                + json.dumps(sorted(fields.items()), ensure_ascii=False)
            )
            idempotency_key = hashlib.sha256(raw.encode()).hexdigest()

        headers = {"X-Airtable-Client-Request-Id": idempotency_key}
        payload = {"fields": fields}
        _global_limiter.acquire()
        resp = self._session.patch(
            f"/{record_id}", json=payload, headers=headers
        )
        data = resp.json()
        self._check_response(data)
        return data

    def assert_audit_table_exists(self, audit_table_id: str) -> None:
        try:
            _global_limiter.acquire()
            self._meta_session.get(f"/bases/{self.base_id}/tables/{audit_table_id}")
        except Exception as exc:
            raise AuditTableMissingError(
                f"harness_writes_audit table {audit_table_id!r} not found "
                f"in base {self.base_id!r}: {exc}"
            ) from exc

    def check_schema_drift(self) -> None:
        key = (self.base_id, self.table_id)
        if key in self._schema_checked:
            return
        if not _SCHEMA_PIN.exists():
            _log.warning("schema_pin.json missing — skipping drift check")
            self._schema_checked.add(key)
            return
        try:
            _global_limiter.acquire()
            resp = self._meta_session.get(
                f"/bases/{self.base_id}/tables"
            )
            live_tables = resp.json().get("tables", [])
            live_fields = {
                f["id"]: f["type"]
                for t in live_tables
                if t["id"] == self.table_id
                for f in t.get("fields", [])
            }
            with _SCHEMA_PIN.open(encoding="utf-8") as fh:
                pin = json.load(fh)
            pin_fields = {
                fid: meta["type"]
                for fid, meta in pin.get("tables", {})
                .get(self.table_id, {})
                .get("fields", {})
                .items()
            }
            drifted = {
                fid: (pin_fields[fid], live_fields[fid])
                for fid in pin_fields
                if fid in live_fields and pin_fields[fid] != live_fields[fid]
            }
            if drifted:
                raise SchemaError(
                    f"Schema drift detected in table {self.table_id}: {drifted}"
                )
            _log.info("schema drift check passed", table_id=self.table_id)
        except SchemaError:
            raise
        except Exception as exc:
            _log.warning("schema drift check failed (non-fatal)", error=str(exc))
        finally:
            self._schema_checked.add(key)
