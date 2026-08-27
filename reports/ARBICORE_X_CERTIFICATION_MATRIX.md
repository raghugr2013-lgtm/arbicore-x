# ARBICORE_X_CERTIFICATION_MATRIX.md
Audit 2026-08-27 (READ-ONLY). Classes: CERTIFIED · PARTIALLY CERTIFIED · IMPLEMENTED-NOT-CERTIFIED ·
PRESENT-UNVERIFIED · NOT-IMPLEMENTED · DENIED/FAIL-CLOSED.
Certified = genuine evidence (live/on-chain or authoritative test), not "implemented" and not "no failure seen".

| COMPONENT | IMPLEMENTED | TESTED | CERTIFIED | EVIDENCE | LIMITATION |
|---|---|---|---|---|---|
| Discovery (Base pool universe) | ✅ | unit+read-only | PARTIALLY CERTIFIED | Base dry-run enumerated real pools | Base only; aero partial |
| Route construction / RouteSearch | ✅ | unit | IMPLEMENTED-NOT-CERTIFIED | offline tests | no multi-chain live |
| Pool graph | ✅ | unit | PARTIALLY CERTIFIED | Base dry-run | Base only |
| Live quote (UniV3 QuoterV2) | ✅ | unit+live | PARTIALLY CERTIFIED | real quotes on Base, post-fee | Base only; 5 chains RPC-blocked |
| Live quote (Aerodrome classic / Slipstream) | ✅ | unit | IMPLEMENTED-NOT-CERTIFIED | code path real; not live-proven | aero reads throttled on public RPC |
| Route economics (FlashLoan verifier) | ✅ | unit | IMPLEMENTED-NOT-CERTIFIED (⚠ double-count) | aggregate_economics test | **swap-fee double-count confirmed** |
| Route economics (triangular multichain) | ✅ | unit | IMPLEMENTED-NOT-CERTIFIED | compute_true_net_profit tests | separate/parallel model |
| Flash-loan provider selection/optimizer | ✅ | unit (8/8) | PARTIALLY CERTIFIED (offline) | optimizer test suite | no live multi-provider liquidity proof |
| Gas + L1/security fee | ✅ (6 chains) | unit+live(Base) | PARTIALLY CERTIFIED | Base dry-run | 5 chains RPC-blocked |
| Slippage | ✅ | unit+live(Base) | PARTIALLY CERTIFIED | Base dry-run | Base only |
| MEV (Gate 9) | ✅ | unit+live(Base) | PARTIALLY CERTIFIED | eth_feeHistory genuine | Base only |
| Gate 7 (atomic ≥ $25) | ✅ | unit+live(Base) | PARTIALLY CERTIFIED (input suspect) | DENY on negative gross | fed by double-counted econ |
| Gate 8 (real TVL) | ✅ | unit+live(Base UniV3) | PARTIALLY CERTIFIED | UniV3 $8.48M onchain_reserves | aero TVL RPC-blocked |
| Gate 9 (MEV) | ✅ | unit+live(Base) | PARTIALLY CERTIFIED | genuine congestion | Base only |
| Provenance/evidence | ✅ | unit+live(Base) | PARTIALLY CERTIFIED | bundle fields present | populated-feed not proven |
| Candidate verification/approval | ✅ | unit+live(Base) | PARTIALLY CERTIFIED | all DENY, fail-closed | no GREEN candidate yet |
| M3 final authority | ✅ | unit+live(Base) | PARTIALLY CERTIFIED | broadcast_sent=false, safe=true | Base only |
| EmissionBus → Opportunities UI | ✅ | unit | PRESENT-UNVERIFIED (populated) | wiring proven; source=canonical empty | needs live scanner run |
| Fail-closed (no RPC/price/TVL/quote/break-even) | ✅ | unit+live | CERTIFIED | rejects None/break_even; empty feed | — |
| Cross-chain (atomic scope) | ✅ discovery | unit | NOT-IMPLEMENTED (atomic) / OUT-OF-SCOPE | bridge, non-atomic | RED for atomic Limited-Live |
| Signing/broadcast | n/a | n/a | DENIED/FAIL-CLOSED (by design) | no signer, no broadcast | intentionally disabled |
