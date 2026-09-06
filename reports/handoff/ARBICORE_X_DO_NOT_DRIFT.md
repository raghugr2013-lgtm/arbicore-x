# ArbiCore X v2 — DO NOT DRIFT (North Star + hard prohibitions)

## NORTH STAR (do not narrow)
MAXIMUM GENUINELY ACTIVATED OPPORTUNITY SURFACE across Base, Ethereum, Arbitrum,
Optimism, Polygon, BNB, and across all genuinely implemented DEX/venues,
strategies, route discovery, quoting, liquidity/TVL, economics, flash-liquidity
providers, execution, and intelligence.

Operating model:
BROAD PARALLEL ACTIVATION → MULTI-CHAIN OPPORTUNITY RACE → FIRST GENUINE
QUALIFYING EDGE → COMPLETE EXECUTION PROOF → CONTROLLED LIMITED LIVE →
PRODUCTION HARDENING → FULL LIVE.

ArbiCore X must NOT drift into a Base-only, UniV3-only, one-strategy, one-provider
demonstration.

## STRICT TRUTH DEFINITIONS
- Registry presence != activation.
- Adapter presence != executable capability.
- Quoteability != profitable opportunity.
- Profitability != execution readiness.
- Executor address != proof of live execution.
- Fork/simulation != real execution.
- NEVER fabricate opportunities, quotes, liquidity, profit, receipts, or execution.

## HARD PROHIBITIONS (no change without explicit admin approval)
- Do NOT weaken safety gates: signing OFF, broadcast OFF, full-live OFF,
  auto-exec OFF, runtime-autostart FALSE, scanner-autostart TRUE.
- Do NOT widen `SUPPORTED_DEXES={"uniswap_v3"}` ahead of a deployed Executor V2
  that can genuinely settle the added venue.
- Do NOT modify V1 `FlashLoanReceiver` into a generic arbitrary-call executor.
- Do NOT use an upgradeable proxy merely to solve the settlement boundary.
- Do NOT lower economic thresholds to manufacture a green opportunity (0 valid is
  a legitimate market result).
- Do NOT touch production: container, deployment, restart, executor, signing,
  broadcast, withdrawal controls, scanner/runtime/auto-exec safety.
- Do NOT deploy / broadcast / merge / push without explicit admin approval.

## PROTECTED FILES (do not modify)
- `app/backend/arbicore/scanners/dex_arbitrage/scanner.py`
- `deployment/compose/docker-compose.yml`
- `app/backend/scripts/p0_3_flash_discovery_proof.py`

## OPERATIONAL LANDMINES
- NEVER use `--remove-orphans`.
- Full-stack Compose has a known frontend `REACT_APP_BACKEND_URL` problem — do
  NOT invoke full-stack Compose as a certification shortcut.
- Real RPC URLs / secrets are injected VPS-locally only; never commit them
  (template: `deployment/cert/.env.example`; real `.env` is git-ignored).

## PROVENANCE (do not rebuild/redeploy production)
- Production commit `bd969ee507bcf9b37311814aeae25556c951e86d`, image
  `arbicore-x-backend:p0-3-bd969ee`.
- Cert image `arbicore-x-backend:cert-e5767d7ca85dc6812dc2bf6284307ada981fe965`.
