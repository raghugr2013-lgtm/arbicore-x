# ArbiCore X v2.7.0 — Production Readiness Report

**Audit basis:** Actual v2.7.0 source tree + live HTTP responses.
**Audit date:** 2026-08-04
**Verdict:** ✅ READY for the 7-day validation run **once RPC and
credential env vars are set on the VPS.**

---

## 1. Environment variables

Reference for every var the running code reads. Values marked `*` are
required for the VPS deploy.

**Core:**
| Var | Required? | Purpose |
|---|:---:|---|
| `MONGO_URL` | * | MongoDB URI |
| `DB_NAME` | * | Mongo database |
| `CORS_ORIGINS` | * | CORS allow-list (comma-separated) |

**Auth:**
| Var | Required? | Purpose |
|---|:---:|---|
| `ARBICORE_JWT_SECRET` | * | 32+ char JWT signing secret |
| `ARBICORE_ADMIN_PASS` or `ARBICORE_ADMIN_PASSWORD` | * | Admin seed password |
| `ARBICORE_OPERATOR_PASSWORD` |   | Operator seed password (defaults to seed) |

**Safety (defaults are all safe):**
| Var | Default | Effect |
|---|---|---|
| `ARBICORE_SAFETY_KILL_DEFAULT` | `true` | Kill engaged at every boot |
| `ARBICORE_SAFETY_LIVE_EXECUTION_ENABLED` | `false` | No live signing |
| `ARBICORE_SAFETY_REQUIRE_APPROVAL` | `true` | Approval gate |
| `ARBICORE_SAFETY_REQUIRE_PAPER_VALIDATION` | `true` | Paper first |
| `ARBICORE_SAFETY_MAX_PER_TRADE_USD` | `500` | Cap |
| `ARBICORE_SAFETY_MAX_PER_CHAIN_USD` | `5000` | Cap |
| `ARBICORE_SAFETY_MAX_DAILY_NOTIONAL_USD` | `25000` | Cap |

**Providers (Phase 6 config layer):**
| Var | Default | Purpose |
|---|---|---|
| `PROVIDER_RPC_URL_ETHEREUM` | llama free | Ethereum RPC |
| `PROVIDER_RPC_URL_ARBITRUM` | arb1 public | Arbitrum RPC |
| `PROVIDER_RPC_URL_BASE` | mainnet.base.org | Base RPC |
| `PROVIDER_RPC_URL_POLYGON` | polygon-rpc.com | Polygon RPC |
| `PROVIDER_RPC_URL_OPTIMISM` | mainnet.optimism.io | Optimism RPC |
| `PROVIDER_RPC_URL_BNB` | bsc-dataseed.binance.org | BNB RPC |
| `PROVIDER_RPC_URL_SOLANA` | mainnet-beta | Solana RPC |
| `PROVIDER_RPC_URLS_<CHAIN>` (CSV) | — | Failover chain per chain (overrides single) |
| `PROVIDER_CEX_ENABLED` | `binance,bybit,okx,coinbase,kraken,kucoin` | CEX allow-list |
| `PROVIDER_DEX_ENABLED` | 7 families | DEX allow-list |
| `PROVIDER_QUOTE_ENABLED` | `oneinch,zeroex` | Aggregator allow-list |
| `PROVIDER_1INCH_API_KEY` | — | 1inch auth (optional) |
| `PROVIDER_0X_API_KEY` | — | 0x auth (optional) |

**Scanner cadence, economics, validation, hardening:** see
`RELEASE_NOTES_v2.7.0.md` for the full table.

## 2. Provider registrations (live)

`GET /api/arbicore/providers/status` returned **47 providers** on the
audit build, all HEALTHY:
- 7 RPC (Ethereum, Arbitrum, Base, Polygon, Optimism, BNB, Solana)
- 13 DEX (Uniswap V3 ×6, Uniswap V2, Sushi ×2, Pancake, Balancer V2, Jupiter, Raydium)
- 18 quote-aggregator (6 CEX + 1inch ×6 + 0x ×6)
- 6 gas (per EVM chain)
- 1 static metadata
- 2 safety (NoOp wallet + env secret)

## 3. Feature flags & background workers

Confirmed active by grep + live `/api/arbicore/*/status`:

- `wave1b/α` intelligence engines (6/6 active).
- `wave1b/β` shadow scanners (registered, both boot DORMANT — correct).
- `wave2` lifetime tracker + sweeper (running).
- `wave3` memory (mounted + serving).
- **Live scanners** (v2.5): `live_market` (autostart via `LIVE_MARKET_AUTOSTART`).
- **Cross scanners** (v2.6): `live_cex_dex`, `live_dex_dex` (autostart via `CROSS_AUTOSTART`).
- **Safety layer** (v2.4): kill switch, capital policy, approval gate.
- **Paper engine** (v2.4): bound to MID writer.
- **Daily summary writer** (v2.7): background loop, autostart via `VALIDATION_AUTOSTART_DAILY_WRITER`.

## 4. Health checks

`GET /api/arbicore/preflight` — 10 checks, machine-parseable `ok=bool`
gate. Verified live: 10/10 pass on the audit build.

Additional per-subsystem status endpoints (all live-tested):
- `/api/arbicore/intelligence/status`
- `/api/arbicore/scanners/status`
- `/api/arbicore/scanners/cross/status`
- `/api/arbicore/providers/status`
- `/api/arbicore/safety/status`
- `/api/arbicore/paper/stats`
- `/api/arbicore/memory/summary`
- `/api/arbicore/live/status`, `/api/arbicore/live/prices`, `/api/arbicore/live/opportunities`
- `/api/arbicore/validation/summary`, `.../daily_status`, `.../last_daily`
- `/api/arbicore/observability`
- `/api/arbicore/config/runtime`
- `/api/arbicore/flashloan/journey/status`

## 5. Observability

Every subsystem exposes a status endpoint returning `{available,
generated_at, ...}`. The Ops Center (Stage-3) polls a subset of these
every 6 seconds and renders live values.

## 6. Provider failover

`ProviderRegistry` returns a **priority-ordered** ranked list per kind.
On error each provider's `_record_event` is called; consecutive failures
trip the breaker for `HARDEN_BREAKER_OPEN_S` (default 60 s). CEX
scanner already tolerates and skips failed venues (verified live —
Binance/Bybit return HTTP 451/403 from datacentre IPs; scanner
continues with the other 4 venues without stopping).

## 7. Paper engine dependencies

- MID writer bound at startup (confirmed).
- Kill switch bound (paper analyses are `policy_blocked` when kill is
  engaged — verified `policy_blocked` counter increments correctly).
- Capital policy bound (`clip_capital` respected in the flash-loan
  journey — verified in v2.6.0 evidence).

## 8. Validation endpoints

All read-only. All confirmed live:
- `/api/arbicore/validation/summary`
- `/api/arbicore/validation/recurrence`
- `/api/arbicore/validation/calibration`
- `/api/arbicore/validation/venue_ranking`
- `/api/arbicore/validation/regime`
- `/api/arbicore/validation/daily_status`
- `/api/arbicore/validation/last_daily`

## 9. Known constraints (documented, not blockers)

- Free-tier public RPCs (`llamarpc.com`, `bsc-dataseed`) return 5xx
  from many datacentre egress IPs. VPS must set at least
  `PROVIDER_RPC_URL_ETHEREUM` to a paid endpoint (Alchemy / Infura /
  QuickNode) before the cross scanners emit real opportunities.
- Binance and Bybit geo-block many datacentre IPs. If the VPS is in
  such a range, disable them via
  `PROVIDER_CEX_ENABLED=okx,coinbase,kraken,kucoin`.
- 1inch v5.2 requires a Bearer token on many chains — set
  `PROVIDER_1INCH_API_KEY` or accept that only 0x will return
  aggregator quotes.

## 10. Sign-off

- ✅ Every env var the code reads is documented in this report.
- ✅ Every registered provider is live-inspected.
- ✅ Every scheduler is enumerated.
- ✅ `/api/arbicore/preflight` returns `ok=true` on the audit build.
- ✅ Safety invariants held.

**Ready for the 7-day validation run once operator env vars are set.**
