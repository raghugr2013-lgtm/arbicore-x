# ArbiCore X v2 — VPS Software Certification Report

- Generated: 2026-09-09T09:33:06.861959+00:00
- Commit: `878f78597234993a01076534a5f15adefb198085`
- Receiver target chain (non-production): `84532`
- Status counts: `{'NOT_CONFIGURED': 19, 'BLOCKED': 3}`

Statuses: PASS | FAIL | BLOCKED | UNKNOWN | NOT_CONFIGURED. VPS-unavailable evidence is never upgraded to PASS.

## 1. Six-chain RPC verification
  - **rpc:base** → `NOT_CONFIGURED` — no operator RPC configured for this chain
  - **rpc:ethereum** → `NOT_CONFIGURED` — no operator RPC configured for this chain
  - **rpc:arbitrum** → `NOT_CONFIGURED` — no operator RPC configured for this chain
  - **rpc:optimism** → `NOT_CONFIGURED` — no operator RPC configured for this chain
  - **rpc:polygon** → `NOT_CONFIGURED` — no operator RPC configured for this chain
  - **rpc:bnb** → `NOT_CONFIGURED` — no operator RPC configured for this chain

## 2. Chain-ID results
  - **rpc:base** → `NOT_CONFIGURED` — 
  - **rpc:ethereum** → `NOT_CONFIGURED` — 
  - **rpc:arbitrum** → `NOT_CONFIGURED` — 
  - **rpc:optimism** → `NOT_CONFIGURED` — 
  - **rpc:polygon** → `NOT_CONFIGURED` — 
  - **rpc:bnb** → `NOT_CONFIGURED` — 

## 3. H05 exact-size result
  - **h05:exact_size_sizer** → `NOT_CONFIGURED` — operator price feed / borrow_sizer not enabled ⇒ quotes remain PROBE-sized and economics fail closed (DENIED_SIZE_NOT_QUOTED). This is the required fail-closed state without a sizer.

## 4. H07 runtime result
  - **h07:base** → `NOT_CONFIGURED` — no RPC ⇒ composition fails closed
  - **h07:ethereum** → `NOT_CONFIGURED` — no RPC ⇒ composition fails closed
  - **h07:arbitrum** → `NOT_CONFIGURED` — no RPC ⇒ composition fails closed
  - **h07:optimism** → `NOT_CONFIGURED` — no RPC ⇒ composition fails closed
  - **h07:polygon** → `NOT_CONFIGURED` — no RPC ⇒ composition fails closed
  - **h07:bnb** → `NOT_CONFIGURED` — no RPC ⇒ composition fails closed

## 5. H08 receiver identity/capability result
  - **h08:receiver** → `BLOCKED` — receiver deployed but declares NO supported_providers ⇒ every venue rejected (H08 stays FALSE until explicitly declared AND on-chain verified)

## 6. H09 simulation result
  - **h09:simulation_prereq** → `BLOCKED` — no exact candidate-bound simulator configured (ARBICORE_SIM_METHOD=''); infra availability is NOT a PASS. Certifying methods: atomic_exact/atomic_state_override/fork_exact/exact_call.

## 7. Executor/receiver bytecode & immutable verification
  - **b:bytecode_immutables** → `BLOCKED` — no operator RPC to inspect bytecode/immutables

## 8. Liquidity/provider evidence (chain-scoped TVL/pricing)
  - **isolation:base** → `NOT_CONFIGURED` — no RPC ⇒ no chain-scoped TVL/pricing possible (fail closed)
  - **isolation:ethereum** → `NOT_CONFIGURED` — no RPC ⇒ no chain-scoped TVL/pricing possible (fail closed)
  - **isolation:arbitrum** → `NOT_CONFIGURED` — no RPC ⇒ no chain-scoped TVL/pricing possible (fail closed)
  - **isolation:optimism** → `NOT_CONFIGURED` — no RPC ⇒ no chain-scoped TVL/pricing possible (fail closed)
  - **isolation:polygon** → `NOT_CONFIGURED` — no RPC ⇒ no chain-scoped TVL/pricing possible (fail closed)
  - **isolation:bnb** → `NOT_CONFIGURED` — no RPC ⇒ no chain-scoped TVL/pricing possible (fail closed)

## 9. Exact commit / image deployed
  - commit: `878f78597234993a01076534a5f15adefb198085`
  - image: set ARBICORE_CERT_IMAGE in the cert env to record it

## 10. Safety-state confirmations
  - signing_off: `True`
  - broadcast_off: `True`
  - auto_exec_off: `True`
  - full_live_off: `True`
  - limited_live_off: `True`

## 11. Failures / blockers requiring further work
  - **rpc:base** (`NOT_CONFIGURED`): no operator RPC configured for this chain
  - **rpc:ethereum** (`NOT_CONFIGURED`): no operator RPC configured for this chain
  - **rpc:arbitrum** (`NOT_CONFIGURED`): no operator RPC configured for this chain
  - **rpc:optimism** (`NOT_CONFIGURED`): no operator RPC configured for this chain
  - **rpc:polygon** (`NOT_CONFIGURED`): no operator RPC configured for this chain
  - **rpc:bnb** (`NOT_CONFIGURED`): no operator RPC configured for this chain
  - **isolation:base** (`NOT_CONFIGURED`): no RPC ⇒ no chain-scoped TVL/pricing possible (fail closed)
  - **isolation:ethereum** (`NOT_CONFIGURED`): no RPC ⇒ no chain-scoped TVL/pricing possible (fail closed)
  - **isolation:arbitrum** (`NOT_CONFIGURED`): no RPC ⇒ no chain-scoped TVL/pricing possible (fail closed)
  - **isolation:optimism** (`NOT_CONFIGURED`): no RPC ⇒ no chain-scoped TVL/pricing possible (fail closed)
  - **isolation:polygon** (`NOT_CONFIGURED`): no RPC ⇒ no chain-scoped TVL/pricing possible (fail closed)
  - **isolation:bnb** (`NOT_CONFIGURED`): no RPC ⇒ no chain-scoped TVL/pricing possible (fail closed)
  - **h05:exact_size_sizer** (`NOT_CONFIGURED`): operator price feed / borrow_sizer not enabled ⇒ quotes remain PROBE-sized and economics fail closed (DENIED_SIZE_NOT_QUOTED). This is the required fail-closed state without a sizer.
  - **h07:base** (`NOT_CONFIGURED`): no RPC ⇒ composition fails closed
  - **h07:ethereum** (`NOT_CONFIGURED`): no RPC ⇒ composition fails closed
  - **h07:arbitrum** (`NOT_CONFIGURED`): no RPC ⇒ composition fails closed
  - **h07:optimism** (`NOT_CONFIGURED`): no RPC ⇒ composition fails closed
  - **h07:polygon** (`NOT_CONFIGURED`): no RPC ⇒ composition fails closed
  - **h07:bnb** (`NOT_CONFIGURED`): no RPC ⇒ composition fails closed
  - **h08:receiver** (`BLOCKED`): receiver deployed but declares NO supported_providers ⇒ every venue rejected (H08 stays FALSE until explicitly declared AND on-chain verified)
  - **b:bytecode_immutables** (`BLOCKED`): no operator RPC to inspect bytecode/immutables
  - **h09:simulation_prereq** (`BLOCKED`): no exact candidate-bound simulator configured (ARBICORE_SIM_METHOD=''); infra availability is NOT a PASS. Certifying methods: atomic_exact/atomic_state_override/fork_exact/exact_call.

## 12. Exact evidence required before Opportunity Race
  - PASS on six-chain RPC + chain-id (operator RPCs, no mismatch, ≥2 endpoints for failover)
  - H05: price feed + borrow_sizer enabled AND a live exact-size quote binding quote_notional_usd
  - H07: live per-chain composition proven against operator RPC/TVL/pricing
  - H08: deployed receiver on-chain-verified AND explicitly declaring the venue provider(s)
  - H09: a COMPLETE candidate binding + an exact candidate-bound simulation PASS + chain match
  - B: executor bytecode/immutables/owner verified on-chain against the artifact
  - Signing/broadcast/auto-exec/Limited-Live remain OFF until explicitly approved
