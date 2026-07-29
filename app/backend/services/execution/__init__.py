"""Phase E2 — Execution Framework Scaffolding (SIMULATED / DISABLED BY DEFAULT).

This package contains the execution-layer scaffolding only: venue registry,
certification limits + kill switches, funding-asset math, route classification /
automation coverage, the manual opportunity engine, the portal-vs-exchange
opportunity computation, and the fund-tracking / recovery state machine.

*** NOTHING HERE MOVES FUNDS. ***
No exchange API calls, no wallet transactions, no purchases, no transfers, no
withdrawals. Every execution cycle is flagged simulated=True / dry_run=True.
Live / shadow execution is Phase E3+ and remains disabled until explicitly
enabled (execution_enabled / wallet_enabled flags, both OFF by default).
"""
