# SIX-NETWORK THREE-TIER RPC DRAFT CERTIFICATION — 2026-10-03

- **Status:** **READ-ONLY PROBE OF THE PENDING DRAFT** — no APPLY, no draft edit, no chain activation, no executor change, no SHADOW start, no container restart.
- **Scope:** persisted draft in Mongo `arbicore_x.arbicore_config_drafts` `_id=network`, probed from inside `arbicore-x-backend-new`. The applied document was read for comparison and was not written.
- **Draft identity:** `updated_at=2026-10-03T14:37:36.940472+00:00`, `updated_by=operator`. Unchanged by this probe.
- **Container:** `arbicore-x-backend-new` · `arbicore-x-backend:27dfab4-20261003` · StartedAt `2026-10-03T12:42:03.446652725Z` · RestartCount `0` · healthy.
- **Related:** `docs/certification/SIX_NETWORK_DRAFT_CERTIFICATION_20261003.md` (persistence / applied-vs-draft). This note adds live JSON-RPC results.
- **Secrets:** Alchemy keys not printed. Fingerprint = `sha256(<key>)[:8]` of the path segment after `/v2/`.
- **Base executor warning:** expected. Draft `executor_addresses.base` is empty. Not modified.

**STOP.** This pass did not APPLY.

---

## Verdict

| Check | Result |
|---|---|
| Six chains in the pending draft | **PASS** |
| Tier 1 Alchemy primary fp **`cd505118`** on all six (Account A slot) | **PASS** — authenticated, chain id matches |
| Tier 2 Alchemy fallback fp **`124bc59c`** on all six (Account B slot) | **PASS** — distinct key, authenticated, chain id matches |
| Tier 3 independent public RPC on all six | **FAIL** — stored and healthy only on Optimism; BNB stored but `eth_getLogs` limited; Base, Ethereum, and Arbitrum HTTP **403**; Polygon **not stored** |
| `ce00e63d` absent from draft and applied | **PASS** |
| Applied config still Base-only `rev-7c93bb93e65b4f5a9b7340bf513437c0` | **PASS** |
| Generalized env_sync from `27dfab4` in the running backend | **PASS** |
| Rate limit on this sequential pass | **No HTTP 429.** One JSON-RPC limit: BNB public `eth_getLogs` code `-32005` |

Alchemy tier 1 and tier 2 are live on every chain. The three-tier last-resort design is not live on every chain.

---

## How the tiers were classified

Stored list order is the tier order. Nothing was reordered.

| Slot | Intended role | What is stored |
|---|---|---|
| RPC #1 | Alchemy Account A, primary | Alchemy host, fingerprint **`cd505118`** on every chain |
| RPC #2 | Alchemy Account B, fallback | Same chain host, fingerprint **`124bc59c`** on every chain |
| RPC #3 | Independent public last resort | Public host where a third URL exists |

`cd505118` and `124bc59c` are different keys. That is the evidence they are separate credentials. This probe does not measure Alchemy CU-pool dashboards.

`ce00e63d` is not in the draft fingerprint set `{cd505118, 124bc59c}` and not in the applied set `{cd505118}`.

---

## Six-chain × three-tier matrix

Chain ids are the product registry ids (`base` 8453, `ethereum` 1, `arbitrum` 42161, `optimism` 10, `polygon` 137, `bnb` 56). Probes are one sequential pass per URL: `eth_chainId`, `eth_blockNumber`, `eth_call`, `eth_getLogs`, `eth_estimateGas`.

`eth_call` target: **none in the draft**. Probed `eth_call` `to=0x000…0000`, `data=0x`, block `latest`. A result of `0x` means the method was accepted. It is not a contract read.

`eth_getLogs`: one block (the `eth_blockNumber` just read) filtered to `address=0x000…0000`. `log_count=0` means the method returned an empty list for that filter, not that the chain has no logs.

`eth_estimateGas`: `to=0x000…0000`, `value=0`, `data=0x`. Not signed and not broadcast.

| Chain | RPC #1 primary | RPC #2 fallback | RPC #3 last resort | Ordering |
|---|---|---|---|---|
| **Base** | Alchemy `base-mainnet.g.alchemy.com` fp **`cd505118`** · chain **8453** · block **52124947** · HTTP **200** · auth **ok** · call `0x` · logs **0** · gas **21000** · 83–238 ms · no 429 | Alchemy same host fp **`124bc59c`** · chain **8453** · block **52124948** · HTTP **200** · auth **ok** · call `0x` · logs **0** · gas **21000** · 133–704 ms · no 429 | `mainnet.base.org` · **HTTP 403** on all five methods · chain id **unreadable** · 89–775 ms · no 429 | **PASS** as stored: A, B, public |
| **Ethereum** | Alchemy `eth-mainnet.g.alchemy.com` fp **`cd505118`** · chain **1** · block **26112537** · HTTP **200** · auth **ok** · call `0x` · logs **0** · gas **21000** · 57–163 ms · no 429 | Alchemy same host fp **`124bc59c`** · chain **1** · block **26112537** · HTTP **200** · auth **ok** · call `0x` · logs **0** · gas **21000** · 111–700 ms · no 429 | `ethereum-rpc.publicnode.com` · **HTTP 403** on all five · chain id **unreadable** · 163–579 ms · no 429 | **PASS** as stored: A, B, public |
| **Arbitrum** | Alchemy `arb-mainnet.g.alchemy.com` fp **`cd505118`** · chain **42161** · block **511332704** · HTTP **200** · auth **ok** · call `0x` · logs **0** · gas **21422** · 61–203 ms · no 429 | Alchemy same host fp **`124bc59c`** · chain **42161** · block **511332709** · HTTP **200** · auth **ok** · call `0x` · logs **0** · gas **21422** · 201–404 ms · no 429 | `arb1.arbitrum.io/rpc` · **HTTP 403** on all five · chain id **unreadable** · 200–773 ms · no 429 | **PASS** as stored: A, B, public |
| **Optimism** | Alchemy `opt-mainnet.g.alchemy.com` fp **`cd505118`** · chain **10** · block **157720240** · HTTP **200** · auth **ok** · call `0x` · logs **0** · gas **21000** · 96–368 ms · no 429 | Alchemy same host fp **`124bc59c`** · chain **10** · block **157720240** · HTTP **200** · auth **ok** · call `0x` · logs **0** · gas **21000** · 126–253 ms · no 429 | `mainnet.optimism.io` · chain **10** · block **157720241** · HTTP **200** · call `0x` · logs **0** · gas **21000** · 161–448 ms · no 429 | **PASS** as stored: A, B, public. Public tier **PASS** |
| **Polygon** | Alchemy `polygon-mainnet.g.alchemy.com` fp **`cd505118`** · chain **137** · block **94889415** · HTTP **200** · auth **ok** · call `0x` · logs **0** · gas **21000** · 116–776 ms · no 429 | Alchemy same host fp **`124bc59c`** · chain **137** · block **94889416** · HTTP **200** · auth **ok** · call `0x` · logs **0** · gas **21000** · 71–711 ms · no 429 | **Not stored.** Draft `rpc_urls.polygon` length **2** | Alchemy order **PASS**. Three-tier shape **FAIL** (no public URL) |
| **BNB** | Alchemy `bnb-mainnet.g.alchemy.com` fp **`cd505118`** · chain **56** · block **125503828** · HTTP **200** · auth **ok** · call `0x` · logs **0** · gas **21000** · 83–383 ms · no 429 | Alchemy same host fp **`124bc59c`** · chain **56** · block **125503832** · HTTP **200** · auth **ok** · call `0x` · logs **0** · gas **21000** · 112–422 ms · no 429 | `bsc-dataseed.bnbchain.org` · chain **56** · block **125503836** · HTTP **200** on all five · call `0x` · gas **21000** · 146–426 ms · **`eth_getLogs` JSON-RPC `-32005` `limit exceeded`** · no HTTP 429 · no `Retry-After` | **PASS** as stored: A, B, public. Public tier **PARTIAL** |

Latency ranges are the min–max of the five method timings on that URL.

---

## Per-check reading

| Check | Alchemy #1 and #2 (all six) | Public #3 |
|---|---|---|
| Provider / fingerprint | #1 **`cd505118`**, #2 **`124bc59c`**, host matches the chain | Base `mainnet.base.org`; Ethereum `ethereum-rpc.publicnode.com`; Arbitrum `arb1.arbitrum.io`; Optimism `mainnet.optimism.io`; BNB `bsc-dataseed.bnbchain.org`; Polygon absent |
| Ordering | Index 0 then 1 then 2, same in API and Mongo | Same |
| Chain ID | Matches the registry id | Optimism **10**, BNB **56**. Base, Ethereum, Arbitrum unreadable (403). Polygon not probed |
| Endpoint validity | HTTP 200 and a chain id | Optimism and BNB reachable. Base, Ethereum, Arbitrum rejected. Polygon missing |
| Authentication | Both Alchemy keys accepted (HTTP 200, no auth error) | Public endpoints have no Alchemy key. 403 is origin rejection, not a bad Alchemy key |
| `eth_blockNumber` | Integer block on every Alchemy URL | Optimism and BNB returned a block. The 403 URLs did not |
| `eth_call` | HTTP 200, result `0x` (empty call to the zero address) | Same on Optimism and BNB. 403 elsewhere. No draft contract was called |
| `eth_getLogs` | HTTP 200, `log_count=0` for the zero-address one-block filter | Optimism: 0 logs. BNB public: `-32005 limit exceeded`. 403 elsewhere |
| `eth_estimateGas` | HTTP 200. Gas **21000** except Arbitrum **21422** on both Alchemy URLs | Optimism **21000**, BNB **21000**. 403 elsewhere |
| HTTP status | **200** throughout | **200** Optimism and BNB; **403** Base, Ethereum, Arbitrum |
| Rate limit | None observed (no 429, no rate-limit JSON-RPC error) | BNB `eth_getLogs` only: `-32005 limit exceeded` with HTTP 200 |

---

## Applied configuration and env_sync

| Item | Observed |
|---|---|
| Applied revision | `rev-7c93bb93e65b4f5a9b7340bf513437c0` |
| Applied `updated_at` | `2026-10-03T04:57:17.836236+00:00` (`admin`) |
| Applied `rpc_urls` keys | `base` only (two URLs: `cd505118`, then `mainnet.base.org`) |
| Applied `chains_enabled` | base true; ethereum, arbitrum, optimism, polygon, bnb false |
| Audits after that apply | **0** |
| Draft still pending | **yes** — later `updated_at`, not promoted |
| `ce00e63d` | Absent from applied and draft |
| Running env_sync | `/app/arbicore/config/env_sync.py` sha256 `fdb8a6f8d5b57e4913d8f66060238684c1523eaa200a4f8b6c1f59bbe6c58ab8` contains `target = list(SUPPORTED_CHAINS)`. BUILD_INFO `git_sha=27dfab42ae6981b39628c04fd9d1b869c3f6c57b` |

Startup, apply, and rollback call `sync_env_from_network_config` with no single-chain override. The draft is not what env_sync reads; env_sync reads the applied document. These probes did not change that.

---

## Safety

| Constraint | Confirmed |
|---|---|
| No APPLY | **YES** |
| Draft bytes unchanged (`updated_at` still `14:37:36Z`) | **YES** |
| No activation, executor edit, SHADOW, or restart | **YES** — RestartCount `0`, StartedAt unchanged |
| Read-only JSON-RPC only | **YES** |
| Keys not printed | **YES** |

---

## STOP

**STOP.** The pending draft was probed and left in place. Do not APPLY from this note.
