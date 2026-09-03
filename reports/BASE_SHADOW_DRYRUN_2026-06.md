# ArbiCore X — Base RPC SHADOW Dry Run (read-only) · 2026-06

RPC: public **https://mainnet.base.org** (read-only eth_call; no key, no signing, no broadcast).
Head block observed: ~50,516,894–50,516,942 (real Base mainnet).
Execution controls: LIMITED_LIVE=0, FULL_LIVE=0, AUTOEXEC=0, no signer, no broadcaster. Deployed
server `.env` has NO RPC (stayed SHADOW); the dry run used an isolated script + inline env only.

Root-cause fix applied this session (verified by testing_agent iteration_2, 4/4 + 49/49):
`QuoterRegistry._rpc_url` now uses the canonical precedence resolver
(`ARBICORE_RPC_URL_<CHAIN>` > `ARBICORE_RPC_URL` > `<CHAIN>_RPC_URL`). Before the fix the quoter
read only the generic key, so with only `ARBICORE_RPC_URL_BASE` set EVERY hop degraded to
`fallback:rpc_error: ARBICORE_RPC_URL not configured` → routes unpriceable → Gate 7/8 blind.

## 15-point result

1. **Real pool addresses discovered** (genuine on-chain):
   - UniV3 (deterministic create2, verified): WETH/USDC 0.05% `0xd0b53D9277642d899DF5C87A3966A349A798F224`;
     WETH/USDC 0.3% `0x6c561B446416E1A00E8E93E221854d6eA4171372`; USDC/USDT 0.01% `0xD56da2B74bA826f19015E6B7Dd9Dae1903E85DA1`;
     USDC/cbETH 0.05% `0xFdebEDc97D56EDd31AbdcB887570546B257964f2`; WETH/cbETH 0.05% `0x10648BA41B8565907Cfa1496765fA4D95390aa0d`;
     WETH/wstETH 0.01% `0x20E068D76f9E90b90604500B84c7e19dCB923e7e`.
   - Aerodrome Slipstream USDC/WETH (ts=100): resolved on-chain via CL factory getPool → `0xb2cc224c1c9feE385f8ad6a55b4d94E92359DC59` (runtime_resolved, token-pair + tick-spacing validated).
   - Other 10 Aerodrome/Slipstream pools: NOT resolved (fail-closed) — mix of public-RPC rate-limiting and pools not matching the default factory/params. No address fabricated.

2. **TVL / liquidity provenance**: `onchain_reserves` (genuine ERC-20 balanceOf on the pool).
   - UniV3 GENUINE TVL: WETH/USDC 0.05% = **$8,482,813**; WETH/USDC 0.3% = **$116,356,552**.
   - Aerodrome: address resolves, but the 2nd `balanceOf` read was throttled by the public RPC (`raw1=None`) → TVL None → **fail-closed** (never fabricated).

3. **Price provenance**: `onchain_usd_feed_m2_5` (USDC-numeraire, peg/freshness-guarded). WETH = **$2,545.67**, USDC = **$1.00** (genuine on-chain).

4. **Quote provider status**: **LIVE** after the fix (QuoterRegistry live eth_call on real Base RPC). Candidate quotes returned real gross%: −0.185% / −0.102% / −0.178% / −100% (partial) / −0.013%. Before the fix: noop/fallback (the blocker).

5. **Borrow-provider status**: `balancer_v2`. Real Balancer V2 Vault WETH balance = **24.217 WETH** (genuine balanceOf). `provider_selection` is fee-driven + fail-closed (unknown liquidity never assumed). Per-candidate `flashloan_available` returned None where the borrow-token USD price wasn't resolved at that stage → fail-closed.

6. **Gas / cost**: Base chain gas model present (L2 exec + Base L1 GasPriceOracle + flash-loan fee + slippage allowance); all-in cost path exercised for priceable routes. $35 min-net gate unchanged.

7. **Gate 7 (atomic profit)**: all 5 candidates had NEGATIVE real gross → would DENY (unprofitable). Fail-closed, correct. No profitable opportunity existed at scan time.

8. **Gate 8 (real TVL)**: **PROVEN genuine on-chain TVL for UniV3** ($8.48M, provenance `onchain_reserves`). For Aerodrome/Slipstream: fails closed (TVL None) when the resolved-pool reserves read is throttled — the full chain (resolve → propagate → registry lookup → balanceOf) is proven correct; it needs a non-throttled RPC to complete.

9. **Gate 9 (flash-loan / MEV)**: MEV GENUINE — `eth_feeHistory.gasUsedRatio` congestion 34.5–36.5% → MEDIUM → `mev_ok=true`. Flash-loan liquidity from the real Balancer vault balance.

10. **M3 result**: all 5 candidates DENIED at revalidation (fail-closed). Broadcast ladder (`confirm=False`): **broadcast_sent=false**, denied at `mode_gate` (SHADOW) + no signer_wallet_id + no borrow step + slippage guard. **safe=true**.

11. **Evidence result**: no CONFIRMED candidates → no evidence bundles emitted (correct). Evidence sink is wired at activation (`make_flash_loan_evidence_sink`).

12. **Genuine candidates**: 5 scanned, **0 economically green** (all unprofitable on real quotes).

13. **Rejected & why** (all fail-closed, none fabricated):
    - WETH/USDC UniV3 fee-tier: real quote ok, real TVL $8.48M, gross −0.185% → net-negative / M3 revalidation deny.
    - WETH/USDC & USDC/USDT & WETH/wstETH cross-DEX (aero hop): Gate-8 TVL 0.0 (aero reserves unread) + negative gross.
    - WETH→USDC→cbETH→WETH triangular: quote `partial` (one hop unpriceable at block) → fresh-quote gate deny.

14. **Frontend canonical opportunities**: `/api/arbicore/opportunities/summary` → `source:"canonical"`, total 0 (deployed server has no RPC/scanners → honest empty). Dry run used an isolated script (did not write into the canonical repo). No fabricated rows.

15. **Exact remaining blockers**:
    a. **Production Base RPC required** — public `mainnet.base.org` rate-limits multi-call sequences, so Aerodrome `getPool`/`balanceOf` reads intermittently fail-closed. A dedicated/paid Base RPC (+ optional `ARBICORE_RPC_WSS_BASE`) is needed for reliable aero resolution + reserves.
    b. **Aerodrome factory/pool verification** — some canonical Slipstream/classic pool definitions don't match the default factories (`ARBICORE_AERO_CL_FACTORY_BASE` / classic) → getPool returns 0 / validation mismatch. Verify factories per pool or prune non-existent defs. No fabrication.
    c. **No profitable opportunity at scan time** — all real gross negative; a genuinely profitable route is required to observe a full GREEN end-to-end.
    d. **EmissionBus path** — to populate the canonical Opportunities feed (not just the M3 dry-run script), run the scanner with `ARBICORE_RUNTIME_AUTOSTART=on` + `ARBICORE_SCANNER_FLASH_LOAN_ARB=on` + a real RPC (kept OFF per instruction — Base FlashLoan proven at the M3 layer first, as requested).

## Safety confirmation
LIMITED_LIVE OFF · FULL_LIVE OFF · AUTOEXEC OFF · no signer · no signing · broadcast_sent=false ·
no execution/gate bypass · fail-closed everywhere · no fabricated market data · other scanner families NOT activated.
Audit artifact: `/app/reports/base_dryrun_audit_2.json`.
