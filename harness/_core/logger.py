from __future__ import annotations
import json
import sys
from datetime import datetime, timezone


_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


class StructuredLogger:
    def __init__(self, name: str, level: str = "INFO") -> None:
        self.name = name
        self._level = _LEVELS.get(level.upper(), 20)

    def _emit(self, level: str, msg: str, **kwargs: object) -> None:
        if _LEVELS.get(level, 0) < self._level:
            return
        record: dict = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "logger": self.name,
            "msg": msg,
        }
        record.update(kwargs)
        line = json.dumps(record, ensure_ascii=False, default=str)
        print(line, flush=True)

    def debug(self, msg: str, **kwargs: object) -> None:
        self._emit("DEBUG", msg, **kwargs)

    def info(self, msg: str, **kwargs: object) -> None:
        self._emit("INFO", msg, **kwargs)

    def warning(self, msg: str, **kwargs: object) -> None:
        self._emit("WARNING", msg, **kwargs)

    def error(self, msg: str, **kwargs: object) -> None:
        self._emit("ERROR", msg, **kwargs)

    def critical(self, msg: str, **kwargs: object) -> None:
        self._emit("CRITICAL", msg, **kwargs)
