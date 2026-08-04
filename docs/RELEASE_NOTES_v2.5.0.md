# ArbiCore X v2.5.0 — Live Market Intelligence

**Release date:** 2026-08-04
**Stage:** 2 (Live Market Intelligence)
**Mode:** OBSERVE / PAPER. Kill switch ENGAGED by default. Live execution DISABLED.

---

## Summary

Replaces the Shadow/Demo market layer with a real read-only **Live Market
Intelligence** layer. Every price, spread, and opportunity displayed by
ArbiCore X after v2.5.0 comes from a live external provider consulted
through the Phase-5 Provider Registry.

Zero signing. Zero swaps. Zero flash loans. Zero wallet interaction. Zero
capital movement. Every existing safety guarantee is preserved.

## Provider inventory (registered on boot)

| Kind | Concrete providers | Count |
|------|--------------------|------:|
| RPC (EVM) | `EthJsonRpcProvider` on `ethereum`, `arbitrum`, `base`, `polygon`, `optimism`, `bnb` | 6 |
| RPC (Solana) | `SolanaRpcProvider` | 1 |
| DEX | Uniswap V3 (6 chains), Uniswap V2 (mainnet), SushiSwap (mainnet + arbitrum), PancakeSwap (bnb), Balancer V2 (mainnet), Jupiter (solana), Raydium (solana, health-only) | 13 |
| CEX | Binance, Bybit, OKX, Coinbase, Kraken, KuCoin | 6 |
| Quote Aggregator | 1inch (6 EVM chains), 0x (6 EVM chains) | 12 |
| Gas | RPC-derived on all 6 EVM chains | 6 |
| Token metadata | Static curated registry (WETH/WBTC/USDC/USDT/DAI/WBNB/SOL/…) | 1 |
| Wallet custody | `NoOpWalletProvider` (refuses to sign) | 1 |
| Secret | `EnvSecretProvider` | 1 |
| **TOTAL** |  | **47** |

Boot-time evidence: `GET /api/arbicore/providers/status` returns
`bootstrap.totals = { rpc: 7, dex: 13, cex: 6, quote: 12, gas: 6,
metadata: 1, errors: 0 }`.

## New scanner: `LiveMarketScanner`

Replaces `ShadowScannerAdapter` as the opportunity producer.

Every tick:
1. Polls enabled CEX providers for the configured symbols (default `BTC/USDT`, `ETH/USDT`).
2. Computes cross-venue best-bid / best-ask.
3. If spread ≥ `LIVE_MIN_SPREAD_BPS`, emits a `cex_spot_arbitrage` opportunity into MID via the existing `ScannerEvidenceBridge`.
4. Forwards the same opportunity to the Paper Engine.

Autostart on boot (`LIVE_MARKET_AUTOSTART=1`). Operator control via
`POST /api/arbicore/live/{start,stop}`.

## Live verification (this build)

```
GET /api/arbicore/live/status
  → running=true, iterations>0, quotes_collected>0, cex_venues_polled=6

GET /api/arbicore/live/prices
  BTC/USDT: OKX $63,561 · Coinbase $63,492 · Kraken $63,561 · KuCoin $63,566
    cross: buy@Coinbase / sell@KuCoin = 11.58 bps
  ETH/USDT: OKX $1,856 · Coinbase $1,854 · Kraken $1,856 · KuCoin $1,856
    cross: buy@Coinbase / sell@OKX = 11.27 bps

GET /api/arbicore/live/opportunities
  → 2 fresh live opportunities in MID, real prices, real spreads

GET /api/arbicore/paper/stats
  → policy_blocked=2 (kill switch correctly engaged; paper analysis
    refuses to compute because ARBICORE_SAFETY_KILL_DEFAULT=true)
```

Binance and Bybit return HTTP 451/403 from datacentre IPs (their public
policy); the scanner correctly falls over to the 4 remaining venues.
Cross-venue spread detection is unaffected.

## MID integration

Uses the existing `ScannerEvidenceBridge` — no new collections, no
duplicate storage. Every live opportunity produces:

- one `mid_opportunities` row (`event_type = "scanner.live_market.emit"`)
- one `mid_routes` row with a `cex:<buy>-><sell>:<symbol>` fingerprint
- one Wave-2 lifetime aggregate update
- one `paper.engine.analysed` event + `paper_engine` decision from the
  Paper Engine

## Safety posture (unchanged)

| Guarantee | Status |
|-----------|--------|
| OBSERVE mode | ✅ scanner is read-only |
| PAPER mode | ✅ paper engine consumes live opps |
| Kill switch engaged at boot | ✅ `ARBICORE_SAFETY_KILL_DEFAULT=true` (default) |
| Live execution disabled | ✅ `ARBICORE_SAFETY_LIVE_EXECUTION_ENABLED=false` (default) |
| No signing | ✅ `NoOpWalletProvider.sign_transaction` raises |
| No swaps | ✅ every DEX provider is view-only (`eth_call`, `queryBatchSwap`, `quoteExactInputSingle`) |
| No flash loans | ✅ `FlashLoanProvider` remains protocol-only; no concrete impl |
| No wallet interaction | ✅ only `NoOpWalletProvider` registered |
| No capital movement | ✅ paper engine's `_capital.clip_capital` clips at $500/trade |

## Configuration (env vars added in v2.5.0)

| Var | Default | Purpose |
|-----|---------|---------|
| `PROVIDER_RPC_URL_ETHEREUM` | `https://eth.llamarpc.com` | RPC endpoint override |
| `PROVIDER_RPC_URL_ARBITRUM` | `https://arb1.arbitrum.io/rpc` | |
| `PROVIDER_RPC_URL_BASE` | `https://mainnet.base.org` | |
| `PROVIDER_RPC_URL_POLYGON` | `https://polygon-rpc.com` | |
| `PROVIDER_RPC_URL_OPTIMISM` | `https://mainnet.optimism.io` | |
| `PROVIDER_RPC_URL_BNB` | `https://bsc-dataseed.binance.org` | |
| `PROVIDER_RPC_URL_SOLANA` | `https://api.mainnet-beta.solana.com` | |
| `PROVIDER_CEX_ENABLED` | `binance,bybit,okx,coinbase,kraken,kucoin` | CEX venue allow-list |
| `PROVIDER_DEX_ENABLED` | `uniswap_v3,uniswap_v2,sushiswap,pancakeswap,jupiter,raydium,balancer_v2` | DEX family allow-list |
| `PROVIDER_QUOTE_ENABLED` | `oneinch,zeroex` | Aggregator allow-list |
| `PROVIDER_1INCH_API_KEY` | (unset) | Optional auth for 1inch v5.2 |
| `PROVIDER_0X_API_KEY` | (unset) | Optional auth for 0x |
| `LIVE_MARKET_AUTOSTART` | `1` | Scanner autostart on boot |
| `LIVE_SYMBOLS` | `BTC/USDT,ETH/USDT` | Symbols to scan |
| `LIVE_TICK_INTERVAL_SECONDS` | `15` | Poll interval |
| `LIVE_MIN_SPREAD_BPS` | `5` | Opportunity emission threshold |
| `LIVE_QUOTE_NOTIONAL_USD` | `10000` | Assumed notional for P&L calc |

All existing safety env vars (see v2.4.0 release notes) unchanged.

## API endpoints added

| Endpoint | Purpose |
|----------|---------|
| `GET /api/arbicore/live/status` | Scanner runtime state + counters |
| `GET /api/arbicore/live/prices` | Latest cross-venue price snapshot |
| `GET /api/arbicore/live/opportunities?limit=N` | Recent live opportunities from MID |
| `POST /api/arbicore/live/start` | Start scanner (admin/operator) |
| `POST /api/arbicore/live/stop` | Stop scanner (admin/operator) |
| `GET /api/arbicore/providers/status` | Extended with `bootstrap.totals` and per-provider breakdown |

## Files changed

New:
- `arbicore/providers/cex.py` (Binance/Bybit/OKX/Coinbase/Kraken/KuCoin)
- `arbicore/providers/rpc.py` (`EthJsonRpcProvider`, `SolanaRpcProvider`)
- `arbicore/providers/dex.py` (Uniswap V3/V2, Sushi, Pancake, Curve, Balancer V2, Jupiter, Raydium)
- `arbicore/providers/aux.py` (1inch, 0x, gas, token metadata)
- `arbicore/providers/bootstrap.py`
- `arbicore/scanners/live/scanner.py` + `__init__.py`

Modified:
- `arbicore/data/mid/enums.py` — added `cex_spot_arbitrage`, `cex_dex_arbitrage`, and the 6 EVM chains + `solana`, `cex` to the OPPORTUNITY_TYPE / CHAIN enums (they were open enums; this suppresses the boot-time warnings).
- `backend/server.py` — bootstrap call at Phase-5 init + Live scanner startup event + 5 new endpoints.

## Data flow diagram

```
                      +------------------------+
                      | LiveMarketScanner (15s)|
                      +-----------+------------+
                                  |
                                  | 6× parallel HTTPS to
                                  | CEX public REST endpoints
                                  v
     +---------+  +---------+  +---------+  +---------+  +---------+  +---------+
     | Binance |  |  Bybit  |  |   OKX   |  | Coinbase|  |  Kraken |  |  KuCoin |
     +----+----+  +----+----+  +----+----+  +----+----+  +----+----+  +----+----+
          \             \           |           |             /             /
           +--------------+---------+-----------+------------+-------------+
                                  |
                    bid / ask / last / volume  (per symbol × venue)
                                  |
                                  v
                    +-------------+--------------+
                    | Cross-venue spread compute |
                    +-------------+--------------+
                                  |  spread ≥ LIVE_MIN_SPREAD_BPS
                                  v
                +-----------------+------------------+
                | opportunity payload +               |
                | route fingerprint                   |
                +-----------------+------------------+
                                  |
             +--------------------+--------------------+
             |                    |                     |
             v                    v                     v
  ScannerEvidenceBridge     Wave-2 tracker        PaperEngine.analyse()
             |                    |                     |
             |                    |                     |
             v                    v                     v
   mid_opportunities +        mid_opportunity_lifetime  mid_decisions +
   mid_routes  (MID)          (MID)                    paper.engine.analysed
                                                        (MID)
                                  |
                                  v
                        Wave-3 memory + Wave-2 sweeper
                        + observability endpoints
                                  |
                                  v
                        /api/arbicore/live/*  ← consumed by Dashboard
```

## Testing

- `providers/status` returns 47 providers, 0 errors.
- `live/status` shows scanner running with real iterations & quotes.
- `live/prices` returns real BTC/ETH prices from 4+ live venues.
- `live/opportunities` returns fresh live opportunities in MID.
- `paper/stats` shows `policy_blocked` incrementing, confirming safety wired.
- Provider registry health scores are correctly rising for responding venues; failing venues (Binance/Bybit from datacentre IPs) record failures via `_record_event` without tripping the breaker (< threshold).

## Deployment

Standard: pull the tag, restart backend supervisor. All defaults are safe.

```bash
# on VPS
git fetch --tags
git checkout v2.5.0
sudo supervisorctl restart backend
curl -s $URL/api/arbicore/live/status
curl -s $URL/api/arbicore/live/prices
```

If Binance/Bybit are geo-blocked at your egress, set:
```
PROVIDER_CEX_ENABLED=okx,coinbase,kraken,kucoin
```
to disable them cleanly and avoid the health penalty.

## What Stage 2 delivers

- Live prices flowing from real institutional venues into MID.
- Real opportunity events with real spreads (no synthetic data).
- Paper Engine consuming real inputs.
- Provider Registry with 47 concrete instances + full failover, health, and breaker.
- All Stage-1 (Phase 1-8) architecture reused; no parallel systems.

## What remains before Stage 3 (paper validation)

- **Frontend live-wiring** — OpsCenter.jsx needs to consume `/api/arbicore/live/prices` and `/api/arbicore/live/opportunities` (backend is ready).
- **DEX-side opportunity production** — the DEX providers are registered and health-probing but no scanner currently produces DEX-native opportunities. `cex_dex_arbitrage` is the next scanner class.
- **Historical backfill** — record 24h+ of live opportunity data so the Wave-3 memory engine has samples to learn from.
- **Fee-adjusted spreads** — current `expected_profit_usd` assumes zero withdrawal/network fees. Add per-venue fee schedules.
- **CEX order-book depth** — currently only top-of-book is used; deep-book impact modelling is a Stage-3 add.

## Roadmap after Stage 3

- **Stage 3:** Paper validation — accumulate 7-day live opportunity dataset, validate paper P&L vs realised (backtestable) outcomes, calibrate `execution_probability`.
- **Stage 4:** Limited-live executor (single chain, single venue, capped notional) — requires a real `WalletCustodyProvider` (Ledger/MPC/KMS) and manual approval gate.
- **Stage 5:** Multi-venue smart order routing with automatic approval within pre-approved limits.
- **Stage 6:** Flash-loan arbitrage — requires concrete `FlashLoanProvider` classes (Aave V3, Balancer V2, Uniswap V3 flash), full simulation harness, and independent auditor sign-off.
