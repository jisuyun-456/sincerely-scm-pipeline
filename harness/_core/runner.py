from __future__ import annotations
import json
import os
import pathlib
import shutil
import signal
import threading
import time
from typing import Literal

from harness._core import CORE_SCHEMA_VERSION
from harness._core.calendar import assert_week_in_window
from harness._core.logger import StructuredLogger
from harness._core.paths import state_dir
from harness._core.sanitize import scrub_pii_in_state

try:
    import fcntl
    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False

_log = StructuredLogger("runner")

_FREE_SPACE_MIN = 100 * 1024 * 1024  # 100 MiB
_WALL_CLOCK_DEADLINE_S = 25 * 60     # 25 minutes


class WallClockDeadline(RuntimeError):
    pass


class IdempotentRunner:
    def __init__(
        self,
        domain: str,
        week: str,
        mode: Literal["resume", "reconcile", "fresh"] = "resume",
    ) -> None:
        self.domain = domain
        self.week = week
        self.mode = mode
        self._state_dir = state_dir(domain)
        self._checkpoint_path = (
            self._state_dir / f"{domain}_{week}_{CORE_SCHEMA_VERSION}.json"
        )
        self._shutdown = threading.Event()
        self._deadline_exceeded = False
        self._deadline_timer: threading.Timer | None = None
        self._checkpoint: dict = {}

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def __enter__(self) -> "IdempotentRunner":
        self._check_free_space()
        self._install_sigterm()
        self._start_deadline_timer()
        if self.mode == "fresh":
            self._checkpoint = {}
        else:
            self._checkpoint = self._load_checkpoint()
        return self

    def __exit__(self, *_: object) -> None:
        if self._deadline_timer:
            self._deadline_timer.cancel()

    # ── Checkpoint ────────────────────────────────────────────────────────────

    def _load_checkpoint(self) -> dict:
        bak = self._checkpoint_path.with_suffix(".bak")
        for path in (self._checkpoint_path, bak):
            if path.exists():
                try:
                    with path.open(encoding="utf-8") as fh:
                        data = json.load(fh)
                    _log.info("checkpoint loaded", path=str(path))
                    return data
                except Exception as exc:
                    _log.warning(
                        "checkpoint corrupt, skipping", path=str(path), error=str(exc)
                    )
        return {}

    def save_checkpoint(self, data: dict) -> None:
        tmp = self._checkpoint_path.with_suffix(".tmp")
        bak = self._checkpoint_path.with_suffix(".bak")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        # Rotate: old checkpoint → .bak, .tmp → checkpoint (POSIX atomic)
        if self._checkpoint_path.exists():
            self._checkpoint_path.replace(bak)
        tmp.replace(self._checkpoint_path)
        self._checkpoint = data

    def is_done(self, record_id: str) -> bool:
        return record_id in self._checkpoint.get("done", [])

    def mark_done(self, record_id: str, payload: dict | None = None) -> None:
        done = self._checkpoint.setdefault("done", [])
        if record_id not in done:
            done.append(record_id)
        if payload:
            scrubbed = {
                k: scrub_pii_in_state(v) if isinstance(v, str) else v
                for k, v in payload.items()
            }
            self._checkpoint.setdefault("payloads", {})[record_id] = scrubbed
        self.save_checkpoint(self._checkpoint)

    # ── Guards ────────────────────────────────────────────────────────────────

    def check_shutdown(self) -> None:
        if self._shutdown.is_set():
            _log.warning("SIGTERM received — stopping gracefully")
            raise SystemExit(0)
        if self._deadline_exceeded:
            raise WallClockDeadline(
                f"25-minute wall-clock deadline exceeded for {self.domain}/{self.week}"
            )

    def _check_free_space(self) -> None:
        usage = shutil.disk_usage(self._state_dir)
        if usage.free < _FREE_SPACE_MIN:
            raise OSError(
                f"Insufficient disk space: {usage.free // 1024 // 1024} MiB free "
                f"(need ≥ {_FREE_SPACE_MIN // 1024 // 1024} MiB)"
            )

    def _install_sigterm(self) -> None:
        try:
            signal.signal(signal.SIGTERM, lambda *_: self._shutdown.set())
        except (OSError, ValueError):
            # SIGTERM not available or main thread restriction on Windows
            pass

    def _start_deadline_timer(self) -> None:
        def _expire() -> None:
            self._deadline_exceeded = True

        self._deadline_timer = threading.Timer(_WALL_CLOCK_DEADLINE_S, _expire)
        self._deadline_timer.daemon = True
        self._deadline_timer.start()


class BatchedRunner(IdempotentRunner):
    """Checkpoint at batch granularity using a hash of batch contents."""

    def is_batch_done(self, batch_hash: str) -> bool:
        return batch_hash in self._checkpoint.get("batches_done", [])

    def mark_batch_done(self, batch_hash: str) -> None:
        batches = self._checkpoint.setdefault("batches_done", [])
        if batch_hash not in batches:
            batches.append(batch_hash)
        self.save_checkpoint(self._checkpoint)


class OutboundLedger:
    """Two-phase INTENT/COMMIT ledger for idempotent outbound writes.

    INTENT records signal the start of an operation; COMMIT records confirm
    completion. On resume, uncommitted INTENTs are re-queued (not re-executed).
    """

    def __init__(self, path: pathlib.Path) -> None:
        self._path = path
        self._lock = threading.RLock()

    def claim(self, intent_id: str, payload: dict) -> None:
        entry = json.dumps(
            {"type": "INTENT", "id": intent_id, "payload": payload, "ts": time.time()},
            ensure_ascii=False,
        )
        self._append(entry)

    def commit(self, intent_id: str) -> None:
        entry = json.dumps(
            {"type": "COMMIT", "id": intent_id, "ts": time.time()},
            ensure_ascii=False,
        )
        self._append(entry)

    def is_committed(self, intent_id: str) -> bool:
        if not self._path.exists():
            return False
        with self._lock:
            with self._path.open(encoding="utf-8") as fh:
                for line in fh:
                    try:
                        rec = json.loads(line)
                        if rec.get("type") == "COMMIT" and rec.get("id") == intent_id:
                            return True
                    except json.JSONDecodeError:
                        continue
        return False

    def _append(self, line: str) -> None:
        with self._lock:
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
            fd = os.open(str(self._path), flags, 0o600)
            try:
                if _HAS_FCNTL:
                    fcntl.flock(fd, fcntl.LOCK_EX)
                os.write(fd, (line + "\n").encode("utf-8"))
            finally:
                if _HAS_FCNTL:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
