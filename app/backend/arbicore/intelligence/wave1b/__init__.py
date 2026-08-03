"""Sprint 1B-α — Intelligence Activation.

Wires the six previously-dormant intelligence engines into the FastAPI
runtime and gives each of them a single, validated write path into the
Market Intelligence Database (MID) via :class:`MidEvidenceBridge`.

Design invariants (per Sprint 1B-α charter):
  * Engines consume only what already lives in MID; no live network I/O.
  * Every engine output that is worth learning from goes through
    ``MidEvidenceBridge`` — no producer bypasses MID.
  * Scanners are NOT activated in this wave; that is Wave 1B-β.
  * Activation is idempotent, non-destructive, and fully reversible: if
    any single engine fails to construct, the others still activate and
    the failure is surfaced in ``/api/arbicore/intelligence/status``.
"""
from .bridge import MidEvidenceBridge
from .registry import EngineStatus, IntelligenceRegistry
from .activation import IntelligenceActivation, activate_all

__all__ = [
    "MidEvidenceBridge",
    "EngineStatus",
    "IntelligenceRegistry",
    "IntelligenceActivation",
    "activate_all",
]
