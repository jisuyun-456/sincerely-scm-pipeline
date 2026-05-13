"""Virtual SAP verifier — shared dataclasses and enums."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    ERROR = "ERROR"
    WARN = "WARN"
    INFO = "INFO"


@dataclass
class Issue:
    dim: str           # D1-D5
    severity: Severity
    entity_type: str
    entity_id: str
    msg: str

    def __str__(self) -> str:
        return f"[{self.severity}][{self.dim}] {self.entity_type}/{self.entity_id}: {self.msg}"


@dataclass
class DimScore:
    dim: str
    passed: bool
    issue_count: int = 0


@dataclass
class VerifierResult:
    passed: bool
    dim_scores: list[DimScore] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "dim_scores": [
                {"dim": d.dim, "passed": d.passed, "issue_count": d.issue_count}
                for d in self.dim_scores
            ],
            "issues": [
                {
                    "dim": i.dim,
                    "severity": i.severity,
                    "entity_type": i.entity_type,
                    "entity_id": i.entity_id,
                    "msg": i.msg,
                }
                for i in self.issues
            ],
        }
