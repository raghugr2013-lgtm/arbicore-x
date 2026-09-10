# ArbiCore X — VPS Runtime Certification Procedure (chain-scoped, six-chain)

Local implementation is COMPLETE (see PRD/CHANGELOG). This is the exact, ordered
procedure to convert the reusable chain-scoped execution-readiness ladder from
IMPLEMENTED → RUNTIME-PROVEN on the VPS. It does NOT enable signing, broadcast,
auto-execution, Limited Live, Full Live, or deployment. It is read-only.

SAFETY PRECONDITIONS (verify before starting):
- Operator mode = SHADOW (control_state). Kill switch not required engaged.
- No signer key present is REQUIRED to run this (simulation is read-only).
- Protected files untouched: dex_arbitrage/scanner.py, docker-compose.yml,
  scripts/p0_3_flash_discovery_proof.py.

## 0. Inputs the operator must supply per chain (fail-closed without them)
Per chain C in {ETHEREUM, ARBITRUM, OPTIMISM, POLYGON, BNB, BASE}:
- Operator RPC:   ARBICORE_RPC_URL_<C>  (the SINGLE canonical cert.env input).
  It is auto-synced into PROVIDER_RPC_URL_<C> at init, so it satisfies BOTH the
  chain-scoped RPC/quote seam AND the economic all-in-cost gate — no separate
  PROVIDER_RPC_URL[S]_<C> is needed (if you set one explicitly, it WINS).
  Strict per-chain: non-Base chains NEVER inherit Base's endpoint.
- (Base only) ARBICORE_EXECUTOR_ADDRESS_BASE for the executor address; other
  chains resolve the executor ONLY from the read-only deploy registry.
- Native/ETH USD price source used by the chain gas model (per existing env).
No RPC ⇒ that chain stays BLOCKED at RPC (never a Base fallback), and its
economic gate stays fail-closed.

## 1. Per-chain ladder verification (read-only)
Run the reusable evaluator per chain (do NOT special-case Arbitrum/Base):

    from arbicore.control.chain_execution_readiness import (
        evaluate_chain_execution_readiness, make_registry_chain_id_reader)
    r = await evaluate_chain_execution_readiness(
        chain, chain_id_reader=make_registry_chain_id_reader(), candidate=CAND)

Expected genuine progression on a chain with operator RPC:
  RPC → PASS
  CHAIN_VERIFICATION → PASS   (live eth_chainId == expected id; mismatch BLOCKS)
  MARKET_COMPOSITION → PASS   (UniV3 executor-supported universe)
  LIQUIDITY_PROVIDER → PASS   (real Aave V3 aToken / Balancer vault balance)
  QUOTE → PASS                (exact-size live quote; probe-size REFUSED)
  ECONOMICS → PASS            (exact all-in cost via chain gas model; no defaults)
  ROUTE → PASS
  SIMULATION → PASS ONLY with a real candidate-bound atomic eth_call sim (H09);
               symbolic/paper/heuristic can NEVER certify.
  EXECUTION_CAPABILITY → BLOCKED until a deployed+verified receiver is recorded
               (see step 3). This is expected and correct.

CAND (candidate) must carry: chain, cycle_metadata (route_hops + closed
cycle_token_path), borrow_amount_usd, borrow_sizer (exact USD→wei), and — for
SIMULATION — evidence_bundle.execution_plan.executor_entry_calldata + rpc_url.

## 2. Opportunity Race (read-only, chain-agnostic)
Feed genuine candidates from ALL activated cells:

    from arbicore.control.opportunity_race import run_opportunity_race
    out = await run_opportunity_race(candidates, chain_id_reader=make_registry_chain_id_reader())

The FIRST candidate reaching ECONOMICS PASS that clears the UNCHANGED Gate-7
$25 floor wins. No chain is preferred. out.winner is None until a real edge
exists. Nothing is signed/broadcast/executed.

## 3. Execution-capability activation (NO deploy here)
EXECUTION_CAPABILITY turns green ONLY by recording, in the read-only deploy
registry (deploy/executor_deployments.json), a receiver that satisfies
`EXECUTION_CAPABILITY_EVIDENCE_CONTRACT` (see
control.chain_execution_readiness.execution_capability_requirements(chain)):
  - deploy_status == "success" with a valid 0x address,
  - supported_providers EXPLICITLY lists the runtime flash head(s),
  - receiver_version present (⇒ version_verified),
  - executor address resolvable for the chain.
Recording this evidence requires an already-deployed+verified receiver produced
OUT OF BAND under separate explicit approval. This procedure NEVER deploys.

## 4. Evidence capture
- Persist each chain's ladder verdict + the race result as an evidence bundle
  (db.evidence_bundles). No verdict may be fabricated; UNKNOWN/BLOCKED stays so.

## 5. STOP conditions (mandatory)
- Limited Live remains RED throughout (control.readiness hard-gates it).
- Do NOT enable signing/broadcast/auto-exec. Do NOT merge to main. Do NOT
  restart the production VPS stack. Report the per-chain matrix and STOP;
  await explicit operator approval before any Limited-Live step.

## Reusability note
The SAME code path advances all six chains. Supplying a chain's operator RPC is
the only per-chain action needed for RPC→ECONOMICS; SIMULATION additionally needs
a real candidate calldata; EXECUTION_CAPABILITY additionally needs a recorded,
verified receiver. No chain waits on another.
