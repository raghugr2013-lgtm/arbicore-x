"""ArbiCore X — universal searcher core (chain-agnostic).

Local, RPC-free hot-path kernels that any ChainAdapter/DEXAdapter can feed:
  * amm_math      — local constant-product / concentrated-liquidity / stableswap math
  * pool_cache    — log-synced pool-state cache with block-staleness protection
  * route         — token graph, closed-cycle enumeration, cheap spot fast-filter
  * simulation    — universal SimulationBackend interface + local-math backend
                    (+ honest REVM/fork stub that refuses to fabricate results)

Pure/deterministic; no I/O. Base-specific data stays in adapters.
"""
