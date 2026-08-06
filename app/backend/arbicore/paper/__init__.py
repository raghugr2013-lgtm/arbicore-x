"""Phase 6 — Paper Opportunity Engine + v2.11.8 Paper Validation Framework.

Two coexisting surfaces:

**Legacy (Phase 6):** :mod:`paper_engine` computes "would-have-executed"
analyses for an opportunity payload using Phase-5 provider abstractions.

**v2.11.8 Paper Validation Framework:** produces an immutable
:class:`EvidenceBundle` per opportunity that transits the
OpportunityPipeline.  Every bundle carries a canonical
:class:`PaperOutcome` from the closed eight-value vocabulary, per-stage
:class:`StageMetric` timings, and a unique validation_id joining it to
the opportunity + journal + future Shadow Certification records.

The two surfaces are intentionally independent — the legacy engine
computes projected results; the Framework classifies actual pipeline
runs.
"""
from .paper_engine import (
    PaperAnalysis, PaperEngine, PaperEngineStats,
)
from .outcomes import PaperOutcome, TERMINAL_REASON_TO_OUTCOME
from .evidence import (
    StageMetric,
    EvidenceBundle,
    new_validation_id,
)
from .stage_recorder import StageRecorder
from .classifier import classify_outcome
from .repo import PaperEvidenceRepository, InMemoryPaperEvidenceRepository
from .liquidity import LiquidityCheckResult, check_liquidity
from .simulator import (
    EthCallSimulator,
    HeuristicSimulator,
    SimulationBackend,
    SimulationResult,
    SimulationRouter,
)
from .runner import PaperValidationRunner, RunnerMetrics, is_enabled_via_env

__all__ = [
    # Legacy Phase-6 surface
    "PaperAnalysis", "PaperEngine", "PaperEngineStats",
    # v2.11.8 Paper Validation Framework — Slice A
    "PaperOutcome", "TERMINAL_REASON_TO_OUTCOME",
    "StageMetric", "EvidenceBundle", "new_validation_id",
    "StageRecorder", "classify_outcome",
    "PaperEvidenceRepository", "InMemoryPaperEvidenceRepository",
    # v2.11.8 Paper Validation Framework — Slice B
    "LiquidityCheckResult", "check_liquidity",
    "EthCallSimulator", "HeuristicSimulator",
    "SimulationBackend", "SimulationResult", "SimulationRouter",
    # v2.11.8 Paper Validation Framework — Slice C
    "PaperValidationRunner", "RunnerMetrics", "is_enabled_via_env",
]
