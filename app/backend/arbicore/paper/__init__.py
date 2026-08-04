"""Phase 6 — Paper Opportunity Engine.

Consumes an opportunity payload (from a scanner or a Phase-5 live-data
feed once wired) and produces a full "would-have-executed" analysis
without ever broadcasting. Every output row is persisted to MID with
``execution_mode = "paper"`` so downstream tooling can distinguish it
from shadow-scanner emissions.

The engine deliberately uses Phase-5 provider abstractions for the
external inputs it needs (quotes, gas, flash-loan fee, liquidity).
When those providers are not registered, the engine falls back to the
values supplied in the opportunity payload — no live calls happen.

Phase 8 kill-switch is honoured: if the switch is engaged, the engine
skips the paper computation and returns a policy_blocked row.
"""
from .paper_engine import (
    PaperAnalysis, PaperEngine, PaperEngineStats,
)

__all__ = ["PaperAnalysis", "PaperEngine", "PaperEngineStats"]
