# SIX-NETWORK CONFIGURATION CERTIFICATION MATRIX — 2026-10-03

- **Status:** **READ-ONLY CERTIFICATION COMPLETE** — no APPLY, no activation, no Mongo mutation, no restart/redeploy, no product/architecture code changes, no Docker→Mongo copy.
- **Captured (UTC):** `2026-10-03T09:14Z`–`09:17Z`
- **Cert workspace:** `/home/raghu/projects/arbicore-x-cert`
- **Production (read-only):** `/home/raghu/projects/arbicore-x-v2`
- **Live container:** `arbicore-x-backend-new` · image `arbicore-x-backend:ws-a-befb14e-20261002` · Up ~18h (healthy) · port `127.0.0.1:8001`
- **Implementation checkpoint (code only, not live):** commit `27dfab42ae6981b39628c04fd9d1b869c3f6c57b` — dynamic UI + generalised env_sync. **Not deployed** to this container (live `env_sync` still Base-only).
- **Audit baseline:** `docs/certification/SIX_NETWORK_DYNAMIC_CONFIG_AUDIT_20261003.md`
- **Canonical store:** Mongo `arbicore_config` · `kind=network` (via `NetworkConfigRepo`) — **no second Network Config architecture**.
- **Secrets policy:** Alchemy credentials never printed. Fingerprint = `sha256(<key>)[:8]` where `<key>` is the path segment after `/v2/`. URLs shown as host + `/v2/<REDACTED>` + `fp=…`.

---

## Executive verdict

| Question | Answer |
|---|---|
| Is Base durable Network Config correct (PAYG)? | **YES** — primary Alchemy fp **`cd505118`**, fallback **`mainnet.base.org`**, stale **`ce00e63d` ABSENT** from live Mongo/API |
| Are the other five chains durable in Network Config? | **NO** — `rpc_urls` key present only for `base`; eth/arb/op/poly/bnb have **no Mongo RPC lists** |
| Are the other five “configured” because Docker has Alchemy? | **NO** — Docker/`ARBICORE_RPC_URL_<CHAIN>` fp **`5e5d5bb1`** is **non-durable bootstrap**, not operator Network Config |
| Can a six-network APPLY be authorized now? | **NO** — see Exact Gaps |
| Anything mutated this turn? | **Only this certification document** under `docs/certification/` |

**STOP after this audit.** Six-network APPLY / activation remains blocked pending gap closure + explicit GO.

---

## Fingerprint legend

| fp8 | Meaning | Where observed this cert |
|---|---|---|
| `cd505118` | Base PAYG Alchemy key | Mongo/API Network Config primary only |
| `5e5d5bb1` | Docker bootstrap Alchemy key | Docker env for Base global + eth/arb/op/poly/bnb (non-durable) |
| `ce00e63d` | Retired / stale | **ABSENT** from live Mongo/API Network Config; present only in **history previous** of PAYG APPLY |

---

## 1. Live canonical Network Config identity

| Field | Live value |
|---|---|
| Source | `GET /api/arbicore/settings/network` **200** + Mongo `arbicore_config` `kind=network` (db `arbicore_x`) |
| `revision_id` | `rev-7c93bb93e65b4f5a9b7340bf513437c0` |
| `updated_at` | `2026-10-03T04:57:17.836236+00:00` |
| `updated_by` | `admin` |
| Draft | **none** |
| Last APPLY reason (history) | `"fetch"` (PAYG cutover) |
| Schema format check (local, no POST validate) | **PASS** — https schemes; known chains only; no format errors |
| POST `/network/validate` | **Not invoked** (auth write-path posture; avoided) |

### `chains_enabled` (Mongo/API)

| Chain | Enabled |
|---|---|
| ethereum | **false** |
| arbitrum | **false** |
| base | **true** |
| optimism | **false** |
| polygon | **false** |
| bnb | **false** |

### `rpc_urls` presence (Mongo/API)

| Chain | Mongo key present? | Entries |
|---|---|---|
| ethereum | **no** | — |
| arbitrum | **no** | — |
| base | **yes** | `[0]` Alchemy `base-mainnet.g.alchemy.com` fp **`cd505118`** · `[1]` `mainnet.base.org` |
| optimism | **no** | — |
| polygon | **no** | — |
| bnb | **no** | — |

---

## 2. Complete six-chain matrix

**Durability rule:** Mongo/API Network Config = durable/canonical. Docker env and ProviderRegistry bootstrap from Docker = **non-durable** unless/until written into Network Config and env_synced.

| Chain | chainId | Mongo Network Config present | enabled | Primary RPC (redacted) | Fallback RPC(s) | Provider | Credential fp | Validation status | Durable? | env_sync effective (live process) | RPC health / block |
|---|---:|---|---|---|---|---|---|---|---|---|---|
| **Ethereum** | 1 | **Partial** — `chains_enabled` key only; **`rpc_urls.ethereum` ABSENT** | false | *(none in Mongo)* | *(none in Mongo)* | n/a (Mongo) | n/a (Mongo) | Format OK for document overall; **no RPC list to validate** | **NO** — Docker-only | **Not synced** (live env_sync Base-only; Mongo empty) | **No Mongo endpoint to probe.** Docker non-durable note: `eth-mainnet.g.alchemy.com` fp `5e5d5bb1` → HTTP 200, chainId **1**, block≈26110857 (~130–205ms). ProviderRegistry `rpc_ethereum_0_…` HEALTHY (bootstrap) |
| **Arbitrum** | 42161 | Partial — enabled key only; **`rpc_urls.arbitrum` ABSENT** | false | *(none)* | *(none)* | n/a | n/a | No RPC list | **NO** — Docker-only | Not synced | **No Mongo probe.** Docker note: `arb-mainnet…` fp `5e5d5bb1` → 200, chainId **42161**, block≈511258951. Registry HEALTHY |
| **Base** | 8453 | **YES** — durable `rpc_urls.base[0..1]` | **true** | Alchemy `base-mainnet.g.alchemy.com/v2/<REDACTED>` | `mainnet.base.org` | Alchemy (primary) · public Base (fallback) | primary **`cd505118`** · fallback none | Format **PASS**; live `GET /rpc/check` READY | **YES** — Mongo authoritative | **YES** — last `env_sync` `2026-10-03T04:57:17Z` `exported 4 var(s) (chain=base)` | **Primary:** HTTP 200, chainId **8453**, block **52114829→52114832** (Δ+1 over ~3s), ~83–152ms. **`/rpc/check`:** READY, masked `base-mainnet.g.alchemy.com`, block 52114776. **Fallback:** HTTP **403** Forbidden (configured but probe-failing). Registry: alchemy prio 100 + `mainnet_base_org` prio 101 both marked HEALTHY |
| **Optimism** | 10 | Partial — enabled key only; **`rpc_urls.optimism` ABSENT** | false | *(none)* | *(none)* | n/a | n/a | No RPC list | **NO** — Docker-only | Not synced | **No Mongo probe.** Docker note: `opt-mainnet…` fp `5e5d5bb1` → 200, chainId **10**, block≈157710118. Registry HEALTHY |
| **Polygon** | 137 | Partial — enabled key only; **`rpc_urls.polygon` ABSENT** | false | *(none)* | *(none)* | n/a | n/a | No RPC list | **NO** — Docker-only | Not synced | **No Mongo probe.** Docker note: `polygon-mainnet…` fp `5e5d5bb1` → 200, chainId **137**, block≈94875916. Registry HEALTHY |
| **BNB Chain** | 56 | Partial — enabled key only; **`rpc_urls.bnb` ABSENT** | false | *(none)* | *(none)* | n/a | n/a | No RPC list | **NO** — Docker-only | Not synced | **No Mongo probe.** Docker note: `bnb-mainnet…` fp `5e5d5bb1` → 200, chainId **56**, block≈125458845. Registry HEALTHY |

### Matrix reading notes

1. **Do not treat ProviderRegistry HEALTHY on eth/arb/op/poly/bnb as Network Config certification.** Those providers are bootstrapped from Docker env (`fp=5e5d5bb1`), not from Mongo `rpc_urls`.
2. Docker probes above are **observational only** (already-present `ARBICORE_RPC_URL_<CHAIN>`). They are **not** durable Network Config and were **not** copied into Mongo.
3. No RPC endpoints were invented. Public defaults were not introduced as Mongo config.
4. Live container code still has `sync_env_from_network_config(..., chain: str = "base")` without `SUPPORTED_CHAINS` loop — **pre-`27dfab4` runtime**.

---

## 3. Base verification (mandatory)

| Check | Result | Evidence |
|---|---|---|
| Primary = Alchemy PAYG fp `cd505118` | **PASS** | Mongo + API `rpc_urls.base[0]`; probe chainId 8453; `/rpc/check` masked Alchemy host |
| Fallback = `mainnet.base.org` | **PASS (configured)** | Mongo + API `rpc_urls.base[1]` |
| Fallback live probe | **FAIL / flaky** | In-container eth_chainId / eth_blockNumber → **HTTP 403** |
| Stale `ce00e63d` absent from live Network Config | **PASS** | Mongo fps = `{cd505118}` only; API GET same |
| `ce00e63d` in audit history | Historical only | Latest APPLY `previous.rpc_urls.base[1]=ce00e63d`; **`next` has no `ce00e63d`** |
| Block progression (primary) | **PASS** | 52114831 → 52114832 (Δ+1) |
| Docker Base bootstrap ≠ PAYG | Drift noted | Docker `ARBICORE_RPC_URL` fp **`5e5d5bb1`**; `ARBICORE_RPC_URL_BASE=mainnet.base.org`; **`cd505118` absent from Docker env** — overridden in-process by env_sync for effective Base path |

---

## 4. env_sync effective configuration (live)

| Item | Live observation |
|---|---|
| Last env_sync log | `2026-10-03T04:57:17Z` — `exported 4 var(s) … (chain=base)` after PAYG APPLY |
| Prior env_sync | Startup `2026-10-02T15:09:08Z` — `exported 5 var(s) (chain=base)` |
| Chains synced by live code | **Base only** |
| Cert-tree code (`27dfab4`) | Generalised env_sync over `SUPPORTED_CHAINS` **present in workspace**, **not loaded** in running image |
| Docker `/proc`/container env snapshot | Still shows bootstrap values (`5e5d5bb1` / public Base); `PROVIDER_RPC_URLS_*` **unset** in container environ — do **not** treat as post-`putenv` truth for Base |
| Effective Base authority | Network Config → env_sync (APPLY/startup) → `/rpc/check` + ProviderRegistry Base ordering |

### Docker env (non-durable inventory — redacted)

| Variable | Redacted value |
|---|---|
| `ARBICORE_RPC_URL` | `base-mainnet.g.alchemy.com` fp **`5e5d5bb1`** |
| `ARBICORE_RPC_URL_BASE` | `mainnet.base.org` |
| `PROVIDER_RPC_URLS_BASE` | unset (in container environ) |
| `ARBICORE_RPC_URL_ETHEREUM` | `eth-mainnet…` fp **`5e5d5bb1`** |
| `ARBICORE_RPC_URL_ARBITRUM` | `arb-mainnet…` fp **`5e5d5bb1`** |
| `ARBICORE_RPC_URL_OPTIMISM` | `opt-mainnet…` fp **`5e5d5bb1`** |
| `ARBICORE_RPC_URL_POLYGON` | `polygon-mainnet…` fp **`5e5d5bb1`** |
| `ARBICORE_RPC_URL_BNB` | `bnb-mainnet…` fp **`5e5d5bb1`** |
| `PROVIDER_RPC_URLS_{ETH,ARB,OP,POLY,BNB}` | unset |

`ce00e63d` **absent** from Docker env RPC keys scanned.

---

## 5. ProviderRegistry snapshot (runtime, not Mongo)

`GET /api/arbicore/providers/status` — `by_kind.rpc` (EVM six + solana):

| Chain | provider_id (abbrev) | priority | status | Origin class |
|---|---|---:|---|---|
| base | `rpc_base_0_base-mainnet_g_alchemy_c` | 100 | HEALTHY | Durable path (env_sync from Mongo PAYG) |
| base | `rpc_base_1_mainnet_base_org` | 101 | HEALTHY | Durable path (Mongo fallback); **probe 403** |
| ethereum | `rpc_ethereum_0_…alchemy…` | 100 | HEALTHY | Docker bootstrap only |
| arbitrum | `rpc_arbitrum_0_…` | 100 | HEALTHY | Docker bootstrap only |
| optimism | `rpc_optimism_0_…` | 100 | HEALTHY | Docker bootstrap only |
| polygon | `rpc_polygon_0_…` | 100 | HEALTHY | Docker bootstrap only |
| bnb | `rpc_bnb_0_…` | 100 | HEALTHY | Docker bootstrap only |

Bootstrap metadata still lists Base index 0 as `rpc_base_0_mainnet_base_org` (seed-time), while live registry order shows Alchemy then public — consistent with post-APPLY resync for Base.

---

## 6. Exact gaps — required before six-network APPLY can be authorized

These are **blocking** for authorizing a six-network Network Config APPLY / activation. Order is pragmatic, not a schedule.

| # | Gap | Why it blocks |
|---|---|---|
| G1 | **No durable Mongo `rpc_urls` for ethereum, arbitrum, optimism, polygon, bnb** | Cannot APPLY/enable six networks from canonical store; Docker Alchemy must not be mistaken for configured Network Config |
| G2 | **All non-Base `chains_enabled=false`** | Operator enablement not set; enabling without deliberate RPC+policy review expands CU/load |
| G3 | **Live runtime lacks deployed `27dfab4` generalised env_sync** | Even if Mongo were filled, live APPLY/startup would still env_sync **Base only** until image/code with multi-chain env_sync is running |
| G4 | **No operator-validated durable RPC+failover lists for the five** | Need authorized endpoints written to Network Config (not invented; not silent Docker copy without operator intent), then format validate + health probe |
| G5 | **Base fallback `mainnet.base.org` currently HTTP 403** from container | Failover resilience for the only durable chain is weak; should be re-probed / replaced before relying on multi-network cutover narratives |
| G6 | **Docker ↔ Mongo credential drift** | Base PAYG `cd505118` not in Docker `.env`; recreate risk reverts Base bootstrap to `5e5d5bb1` / public until env_sync runs — ops mirror still open |
| G7 | **POST validate / draft / APPLY not yet exercised for multi-chain payload** | This cert intentionally did not APPLY; a future GO must validate then APPLY under change control |
| G8 | **Non-Base ProviderRegistry HEALTHY ≠ durable cert** | Any readiness claim must separate Docker bootstrap reachability from Network Config durability |

### Explicitly out of scope / not done

- No Network Config APPLY / draft save / rollback
- No AUTOEXEC / RUNTIME / SHADOW / live trading enablement
- No copying Docker RPC URLs into Mongo
- No inventing RPC endpoints
- No product or architecture code changes
- No restart / redeploy / image cutover to `27dfab4`

---

## 7. Confirmation — safety posture

| Constraint | Confirmed |
|---|---|
| No APPLY / activation / live execution / signing / broadcast / risk changes | **YES** |
| No product or architecture code changes | **YES** |
| No Docker RPC configs copied into Mongo | **YES** |
| No invented RPC endpoints | **YES** — probed only Mongo Base URLs + already-present Docker env URLs (labeled non-durable) |
| Secrets fingerprint-only | **YES** — `cd505118` / `5e5d5bb1` / `ce00e63d` as fp8 only |
| Deliverable | This file only: `docs/certification/SIX_NETWORK_CONFIG_CERTIFICATION_MATRIX_20261003.md` |

---

## 8. STOP

**STOP.** Read-only six-network configuration certification is complete.

- Base PAYG durable config verified (`cd505118` + `mainnet.base.org`; `ce00e63d` absent live).
- Five other chains are **not** durable Network Config–configured; Docker Alchemy is non-authoritative.
- Six-network APPLY remains **unauthorized** until Exact Gaps (esp. G1–G4) are closed under an explicit GO.

---

## Appendix A — API / probe methods used (read-only)

| Method | Path / action | Purpose |
|---|---|---|
| GET | `/api/arbicore/settings/network` | Canonical API Network Config |
| GET | `/api/arbicore/settings/network/history` | Audit trail / previous vs next fps |
| GET | `/api/arbicore/rpc/check` | Effective Base RPC health |
| GET | `/api/arbicore/providers/status` | ProviderRegistry runtime view |
| Mongo find | `arbicore_config` `kind=network` | Durable store cross-check |
| eth_chainId / eth_blockNumber | Mongo `rpc_urls.base[]` only as durable probes | Base health + progression |
| eth_chainId / eth_blockNumber | Existing Docker `ARBICORE_RPC_URL_*` | Non-durable observation only |
| Local format validation | Against GET payload | Schema-ish check without POST validate |

## Appendix B — Related pointers

| Pointer | Role |
|---|---|
| `27dfab42ae6981b39628c04fd9d1b869c3f6c57b` | Accepted implementation checkpoint (FE allowlist + generalised env_sync) — **code**, not live image |
| `docs/certification/SIX_NETWORK_DYNAMIC_CONFIG_AUDIT_20261003.md` | Prior architecture/gap audit |
| `docs/certification/ALCHEMY_PAYG_POST_APPLY_VERIFICATION_20261003.md` | Base PAYG APPLY verification |
| Live image `ws-a-befb14e-20261002` | Still Base-only env_sync at runtime |
