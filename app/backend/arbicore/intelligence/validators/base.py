"""ArbiCore X — Shared validation result contract."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    reason: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"passed": self.passed, "reason": self.reason, "details": self.details}
