from __future__ import annotations
import os
from typing import ClassVar


class ConfigError(Exception):
    pass


class ConfigBase:
    REQUIRED_ENV: ClassVar[list[str]] = []
    OPTIONAL_ENV: ClassVar[list[str]] = []

    def validate(self) -> None:
        missing = [k for k in self.REQUIRED_ENV if not os.environ.get(k)]
        if missing:
            raise ConfigError(
                f"Missing required environment variables: {missing}"
            )

    @classmethod
    def from_env(cls) -> "ConfigBase":
        instance = cls()
        instance.validate()
        return instance
