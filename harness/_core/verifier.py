from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar


@dataclass(kw_only=True)
class Issue:
    sc_id: str
    dim: str
    severity: str  # "ERROR" | "WARNING" | "INFO"
    msg: str


@dataclass(kw_only=True)
class FormativeResult:
    sc_id: str
    passed: bool
    issues: list[Issue] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.passed

    def summary(self) -> str:
        if self.passed:
            return f"[PASS] {self.sc_id}"
        errs = [i for i in self.issues if i.severity == "ERROR"]
        return f"[FAIL] {self.sc_id}: {len(errs)} error(s)"


@dataclass(kw_only=True)
class DimScore:
    name: str
    passed: bool
    rate: float
    detail: str


@dataclass(kw_only=True)
class BatchResult:
    week: str
    total: int
    passed: bool
    dims: dict[str, DimScore] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    blocked_count: int = 0

    def report(self, max_issues: int = 20) -> str:
        lines = [
            f"Week {self.week}: {'PASS' if self.passed else 'FAIL'} "
            f"({self.total} records, {self.blocked_count} blocked)"
        ]
        for dim, score in self.dims.items():
            status = "✓" if score.passed else "✗"
            lines.append(f"  {status} {dim}: {score.detail}")
        for issue in self.issues[:max_issues]:
            lines.append(f"  [{issue.severity}] {issue.sc_id}/{issue.dim}: {issue.msg}")
        if len(self.issues) > max_issues:
            lines.append(f"  ... and {len(self.issues) - max_issues} more")
        return "\n".join(lines)


class VerifierBase(ABC):
    _DIMS: ClassVar[tuple[str, ...]] = ()

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        # Import-time guard: all declared dims must have a _check_<dim>() method
        for dim in cls._DIMS:
            method_name = f"_check_{dim.lower()}"
            if not any(method_name in c.__dict__ for c in cls.__mro__):
                raise TypeError(
                    f"{cls.__name__} declares dim {dim!r} but is missing "
                    f"method {method_name}()"
                )

    @abstractmethod
    def verify_record(self, item: dict, **kwargs: object) -> FormativeResult:
        ...

    @abstractmethod
    def verify_batch(self, items: list[dict], week: str = "") -> BatchResult:
        ...
