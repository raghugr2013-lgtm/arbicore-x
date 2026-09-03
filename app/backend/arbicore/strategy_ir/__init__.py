"""Native ArbiCore Strategy IR — DATA ONLY.

Strategy Factory (separate upstream system) emits a research strategy / hypothesis
as a Strategy IR. ArbiCore ingests it as a NON-EXECUTABLE candidate. A Strategy IR
is NOT an authorized transaction and carries NO execution authority: any field that
could influence execution/signing/broadcast/safety is REJECTED at validation.

An accepted candidate must still pass every existing ArbiCore downstream gate
(discovery → quote → economics → simulation → evidence) before it could ever become
an opportunity. Strategy IR never touches the kill switch, signer, allowlists, quote
freshness, repayment, calldata, profitability gates, execution mode, or readiness.
"""
from .schema import (
    StrategyIR, StrategyProvenance, SourceClass, ALLOWED_STRATEGY_TYPES,
    FORBIDDEN_KEYS, StrategyIRValidationError, compute_fingerprint,
    EXTERNAL_ORIGIN_CLASSES, RESTRICTED_CLASSES,
)

__all__ = [
    "StrategyIR", "StrategyProvenance", "SourceClass", "ALLOWED_STRATEGY_TYPES",
    "FORBIDDEN_KEYS", "StrategyIRValidationError", "compute_fingerprint",
    "EXTERNAL_ORIGIN_CLASSES", "RESTRICTED_CLASSES",
]
