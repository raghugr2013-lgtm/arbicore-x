"""Canonical thresholds + status enums for Shadow Certification (v2.11.9).

All numeric thresholds are env-tunable via ``ARBICORE_SHADOW_CERT_*``
overrides so operators can tighten / loosen before Base Sepolia
promotion without shipping a code change.

Status vocabularies are closed:

* :class:`CycleStatus`   — per-cycle grade (PASS / WARNING / FAIL).
* :class:`CertificationStatus` — terminal run grade (RUNNING → one of
  PASS / WARNING / FAIL / ABORTED).

A run is:
* PASS   → all thresholds met, target_cycles reached, no infra failures.
* WARNING → target_cycles reached, PASS thresholds missed but no FAIL
            trigger fired (e.g. executable_rate between warn and pass).
* FAIL   → any FAIL trigger fired (infra failure rate over cap,
            stage p95 over cap, or cycle FAIL count over cap).
* ABORTED → operator called stop() before target_cycles reached.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict


class CycleStatus(str, Enum):
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"


class CertificationStatus(str, Enum):
    RUNNING = "RUNNING"
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    ABORTED = "ABORTED"


# Terminal set — a run in these states is immutable and no more
# cycles may be appended.
TERMINAL_STATUSES = frozenset({
    CertificationStatus.PASS,
    CertificationStatus.WARNING,
    CertificationStatus.FAIL,
    CertificationStatus.ABORTED,
})


@dataclass(frozen=True)
class CertificationThresholds:
    """Frozen threshold pack applied to a single certification run.

    A copy of the active thresholds is embedded in every
    :class:`ShadowCertificationRun` so a historical run can always be
    re-graded against the exact configuration used at the time.
    """

    #: Total certification cycles required for PASS.
    target_cycles: int = 20

    #: Minimum sustained executable_rate for PASS status.
    #: (Paper Validation "executable_rate" = EXECUTABLE / total).
    min_executable_rate_pass: float = 0.10

    #: Minimum sustained executable_rate for WARNING status
    #: (anything below is FAIL for that dimension).
    min_executable_rate_warn: float = 0.05

    #: Maximum stage-p95 duration in ms.  A single cycle exceeding this
    #: is a per-cycle WARNING; sustained breach is a run-level FAIL.
    max_stage_p95_ms: float = 5_000.0

    #: Cycle infra failure rate cap (exceptions/cycles).  Above this,
    #: cycle is FAIL for infra dimension.
    max_infra_exception_rate: float = 0.01

    #: How many cycles are allowed to individually FAIL before the run
    #: is graded FAIL overall.
    max_fail_cycles: int = 2

    #: How many cycles are allowed to individually WARN before the run
    #: is graded WARNING overall.
    max_warn_cycles: int = 5

    #: Minimum opportunities_seen per cycle for the cycle to count
    #: toward statistical significance.  Below this the cycle is
    #: recorded but tagged ``low_volume`` and does NOT contribute to
    #: the executable_rate PASS check.
    min_opps_per_cycle: int = 10

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_cycles": self.target_cycles,
            "min_executable_rate_pass": self.min_executable_rate_pass,
            "min_executable_rate_warn": self.min_executable_rate_warn,
            "max_stage_p95_ms": self.max_stage_p95_ms,
            "max_infra_exception_rate": self.max_infra_exception_rate,
            "max_fail_cycles": self.max_fail_cycles,
            "max_warn_cycles": self.max_warn_cycles,
            "min_opps_per_cycle": self.min_opps_per_cycle,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CertificationThresholds":
        return cls(
            target_cycles=int(d.get("target_cycles", 20)),
            min_executable_rate_pass=float(d.get("min_executable_rate_pass", 0.10)),
            min_executable_rate_warn=float(d.get("min_executable_rate_warn", 0.05)),
            max_stage_p95_ms=float(d.get("max_stage_p95_ms", 5000.0)),
            max_infra_exception_rate=float(d.get("max_infra_exception_rate", 0.01)),
            max_fail_cycles=int(d.get("max_fail_cycles", 2)),
            max_warn_cycles=int(d.get("max_warn_cycles", 5)),
            min_opps_per_cycle=int(d.get("min_opps_per_cycle", 10)),
        )


def _f(env: str, default: float) -> float:
    v = os.environ.get(env)
    if v is None or v.strip() == "":
        return default
    try:
        return float(v)
    except ValueError:
        return default


def _i(env: str, default: int) -> int:
    v = os.environ.get(env)
    if v is None or v.strip() == "":
        return default
    try:
        return int(v)
    except ValueError:
        return default


def load_thresholds_from_env() -> CertificationThresholds:
    """Read live threshold overrides from the process env.

    Env keys (all optional):
      * ``ARBICORE_SHADOW_CERT_TARGET_CYCLES``
      * ``ARBICORE_SHADOW_CERT_MIN_EXEC_RATE_PASS``
      * ``ARBICORE_SHADOW_CERT_MIN_EXEC_RATE_WARN``
      * ``ARBICORE_SHADOW_CERT_MAX_STAGE_P95_MS``
      * ``ARBICORE_SHADOW_CERT_MAX_INFRA_EXCEPTION_RATE``
      * ``ARBICORE_SHADOW_CERT_MAX_FAIL_CYCLES``
      * ``ARBICORE_SHADOW_CERT_MAX_WARN_CYCLES``
      * ``ARBICORE_SHADOW_CERT_MIN_OPPS_PER_CYCLE``
    """
    return CertificationThresholds(
        target_cycles=_i("ARBICORE_SHADOW_CERT_TARGET_CYCLES", 20),
        min_executable_rate_pass=_f("ARBICORE_SHADOW_CERT_MIN_EXEC_RATE_PASS", 0.10),
        min_executable_rate_warn=_f("ARBICORE_SHADOW_CERT_MIN_EXEC_RATE_WARN", 0.05),
        max_stage_p95_ms=_f("ARBICORE_SHADOW_CERT_MAX_STAGE_P95_MS", 5000.0),
        max_infra_exception_rate=_f(
            "ARBICORE_SHADOW_CERT_MAX_INFRA_EXCEPTION_RATE", 0.01
        ),
        max_fail_cycles=_i("ARBICORE_SHADOW_CERT_MAX_FAIL_CYCLES", 2),
        max_warn_cycles=_i("ARBICORE_SHADOW_CERT_MAX_WARN_CYCLES", 5),
        min_opps_per_cycle=_i("ARBICORE_SHADOW_CERT_MIN_OPPS_PER_CYCLE", 10),
    )
