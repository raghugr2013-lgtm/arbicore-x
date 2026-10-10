# SIX-NETWORK DRAFT CERTIFICATION — 2026-10-03

- **Status:** **READ-ONLY DRAFT CERTIFICATION COMPLETE** — no APPLY, no draft edit, no chain activation, no executor change, no SHADOW start, no container restart/redeploy, no Mongo write.
- **Captured (UTC):** `2026-10-03T14:44:10Z` (API `generated_at`) through `14:45Z`
- **Container:** `arbicore-x-backend-new` · image `arbicore-x-backend:27dfab4-20261003` · digest `sha256:77f0bb536f7f02ca18d18dadb16985aac34e980de5f6de540aaf660a0e7ca2bb` · StartedAt `2026-10-03T12:42:03.446652725Z` · RestartCount `0` · healthy · `127.0.0.1:8001`
- **BUILD_INFO:** `git_sha=27dfab42ae6981b39628c04fd9d1b869c3f6c57b` · `git_tag=27dfab4-20261003` · `build_time=2026-10-03T12:23:06Z`
- **Canonical store:** Mongo `arbicore_x` · current `arbicore_config` `_id=network` · pending `arbicore_config_drafts` `_id=network` · audit `arbicore_config_audit`
- **API:** `GET /api/arbicore/settings/network` **200** and `GET /api/arbicore/settings/network/history?limit=5` **200**. API and Mongo agree.
- **Secrets policy:** Alchemy credentials never printed. Fingerprint = `sha256(<key>)[:8]` of the path segment after `/v2/`. URLs shown as host + `/v2/<REDACTED:fp=…>`.
- **UI warning:** “no executor address configured for chain 'base' — LIMITED_LIVE flow will BLOCK” is **expected**. Every executor address in both the applied document and the draft is empty. It was not modified and is **not** a failure.

**STOP.** This pass did not APPLY.

---

## Executive verdict

| # | Check | Verdict |
|---:|---|---|
| 1 | Six chains present: base, ethereum, arbitrum, optimism, polygon, bnb | **PASS** |
| 2 | `rpc_urls` persisted for all six | **PASS** (draft) |
| 3 | Primary/fallback ordering is the stored order | **PASS** |
| 4 | `chains_enabled` reported separately for draft vs applied | **PASS** |
| 5 | Base primary remains Alchemy PAYG fingerprint `cd505118` | **PASS** |
| 6 | `ce00e63d` remains absent from applied config and from the draft | **PASS** |
| 7 | Draft exists and is not the applied configuration | **PASS** |
| 8 | Applied revision remains the previous Base-only revision | **PASS** |
| 9 | Generalized env_sync from `27dfab4` is in the running backend | **PASS** |
| 10 | No unexpected configuration changes | **PASS** |

---

## Six-chain draft matrix

Ordering is index order as stored. Index 0 is primary. Later indexes are fallbacks. Nothing was invented. Polygon has two stored URLs; the other five have three.

| Chain | Draft primary | Draft fallback(s) | Fingerprint | Enabled in draft | Applied vs draft |
|---|---|---|---|---|---|
| **base** | `base-mainnet.g.alchemy.com` `/v2/<REDACTED>` | `[1]` same host fp `124bc59c` · `[2]` `https://mainnet.base.org` | primary **`cd505118`** · fallback Alchemy **`124bc59c`** | **true** | **Draft only.** Applied is still `[0]` `cd505118` · `[1]` `mainnet.base.org`, enabled **true** |
| **ethereum** | `eth-mainnet.g.alchemy.com` `/v2/<REDACTED>` | `[1]` same host fp `124bc59c` · `[2]` `https://ethereum-rpc.publicnode.com` | primary **`cd505118`** · fallback Alchemy **`124bc59c`** | **true** | **Draft only.** Applied has **no** `rpc_urls.ethereum` key, enabled **false** |
| **arbitrum** | `arb-mainnet.g.alchemy.com` `/v2/<REDACTED>` | `[1]` same host fp `124bc59c` · `[2]` `https://arb1.arbitrum.io/rpc` | primary **`cd505118`** · fallback Alchemy **`124bc59c`** | **true** | **Draft only.** Applied has **no** `rpc_urls.arbitrum` key, enabled **false** |
| **optimism** | `opt-mainnet.g.alchemy.com` `/v2/<REDACTED>` | `[1]` same host fp `124bc59c` · `[2]` `https://mainnet.optimism.io` | primary **`cd505118`** · fallback Alchemy **`124bc59c`** | **true** | **Draft only.** Applied has **no** `rpc_urls.optimism` key, enabled **false** |
| **polygon** | `polygon-mainnet.g.alchemy.com` `/v2/<REDACTED>` | `[1]` same host fp `124bc59c` · **no third URL stored** | primary **`cd505118`** · fallback Alchemy **`124bc59c`** | **true** | **Draft only.** Applied has **no** `rpc_urls.polygon` key, enabled **false** |
| **bnb** | `bnb-mainnet.g.alchemy.com` `/v2/<REDACTED>` | `[1]` same host fp `124bc59c` · `[2]` `https://bsc-dataseed.bnbchain.org` | primary **`cd505118`** · fallback Alchemy **`124bc59c`** | **true** | **Draft only.** Applied has **no** `rpc_urls.bnb` key, enabled **false** |

Draft Alchemy fingerprints present: `cd505118`, `124bc59c`. `ce00e63d` is not among them. `124bc59c` exists only on the pending draft, not on the applied document.

Executor addresses: **empty** on all six chains in both draft and applied. Expected LIMITED_LIVE warning for Base. Not modified.

---

## Identity — draft vs applied

| Field | Applied (`arbicore_config`) | Draft (`arbicore_config_drafts`) |
|---|---|---|
| Present | yes | **yes** |
| `updated_at` | `2026-10-03T04:57:17.836236+00:00` | `2026-10-03T14:37:36.940472+00:00` |
| `updated_by` | `admin` | `operator` |
| Authoritative revision | `rev-7c93bb93e65b4f5a9b7340bf513437c0` | **not applied** — pending document only |
| `chains_enabled` | base **true**; ethereum, arbitrum, optimism, polygon, bnb **false** | all six **true** |
| `rpc_urls` | `base` only (`cd505118`, then `mainnet.base.org`) | all six chains, order in the matrix |
| API vs Mongo | match | match |
| Distinct from applied | — | **yes** (`rpc_urls`, `chains_enabled`, `updated_at`, `updated_by`) |

The draft document also carries a copied `revision_id` field equal to `rev-7c93bb93e65b4f5a9b7340bf513437c0`. That is the revision id the UI included in the saved patch. It is **not** a new apply. The current collection was not replaced, and `save_draft` does not write an audit row.

Latest network audit is still the PAYG apply:

| Field | Value |
|---|---|
| action | `apply` |
| at | `2026-10-03T04:57:17.836236+00:00` |
| actor | `admin` |
| reason | `fetch` |
| revision_id | `rev-7c93bb93e65b4f5a9b7340bf513437c0` |
| next Base order | `[0]` fp `cd505118` · `[1]` `mainnet.base.org` |
| previous Base order (history only) | `[0]` `mainnet.base.org` · `[1]` fp `ce00e63d` |

Network audits with `at` after that apply: **0**. Audits of any kind after that timestamp: **0**.

---

## Checks 1–10

| # | Check | Verdict | Evidence |
|---:|---|---|---|
| **1** | Six chains present | **PASS** | Draft `rpc_urls` and `chains_enabled` both contain exactly `base`, `ethereum`, `arbitrum`, `optimism`, `polygon`, `bnb`. No extra keys. API `supported_chains` is the same six. |
| **2** | `rpc_urls` persisted for all six | **PASS** | Draft lists are non-empty for every chain (counts 3, 3, 3, 3, 2, 3). Applied store still has a `rpc_urls` key for **base only**. |
| **3** | Primary/fallback order | **PASS** | Reported as stored. API list order equals Mongo list order. Index 0 is Alchemy `cd505118` on every chain. |
| **4** | `chains_enabled` | **PASS** | **Draft:** all six `true`. **Applied:** only `base=true`; the other five `false`. These are different documents. |
| **5** | Base primary fp `cd505118` | **PASS** | Applied `rpc_urls.base[0]` and draft `rpc_urls.base[0]` are both `base-mainnet.g.alchemy.com` fp **`cd505118`**. |
| **6** | `ce00e63d` absent | **PASS** | Absent from applied API, applied Mongo, draft API, and draft Mongo. It remains only inside **historical** audit `previous` snapshots (the pre-PAYG Base fallback). |
| **7** | Draft exists and is not applied | **PASS** | Draft document `updated_at=2026-10-03T14:37:36Z` `updated_by=operator`. Applied `updated_at` is still `04:57:17Z`. Zero audits after the PAYG apply, so the draft was not promoted. |
| **8** | Applied revision still Base-only | **PASS** | Current revision is still `rev-7c93bb93e65b4f5a9b7340bf513437c0`, `updated_by=admin`, Base-only RPC list, only Base enabled. Matches `ALCHEMY_PAYG_POST_APPLY_VERIFICATION_20261003.md` and `DEPLOY_27DFAB4_VERIFICATION_20261003.md`. |
| **9** | Generalized env_sync from `27dfab4` | **PASS** | Running `/app/arbicore/config/env_sync.py` sha256 `fdb8a6f8d5b57e4913d8f66060238684c1523eaa200a4f8b6c1f59bbe6c58ab8` matches commit `27dfab4` blob. It imports `SUPPORTED_CHAINS`, defaults `target = list(SUPPORTED_CHAINS)`, and the signature is `chain: Optional[str] = None` (no `chain: str = "base"` default). Running `persistent.py` sha256 `41c0865cd5b9a40873f98eec2fd01162b801b6d5b96300c16a2ba47e7142ca4c` matches the same commit and defines `SUPPORTED_CHAINS = ("base", "ethereum", "arbitrum", "optimism", "polygon", "bnb")`. Startup, apply, and rollback call `sync_env_from_network_config(_NETWORK_CONFIG)` with no single-chain override. Image and BUILD_INFO are `27dfab4`. |
| **10** | No unexpected configuration changes | **PASS** | Applied network document is unchanged from the known PAYG revision (same revision, timestamp, Base primary/fallback, other five RPC keys absent, other five disabled, executors empty). Gas, MEV relay, and native-price fields are identical on the draft and the applied document. The only post-PAYG config write is the network **draft**. No other `arbicore_config` kind has `updated_at` after `2026-10-03T04:57:17Z`. No APPLY this pass. Container StartedAt / RestartCount unchanged from the `27dfab4` deploy record. |

---

## Known prior applied state — comparison

| Prior fact | Now |
|---|---|
| Base primary fp `cd505118` | **unchanged** on the applied document |
| Base fallback `mainnet.base.org` | **unchanged** as applied index `[1]` |
| Other five Mongo `rpc_urls` absent | **unchanged** on the applied document |
| Other five disabled | **unchanged** on the applied document |
| `ce00e63d` absent from live config | **still absent** from applied and from the draft |
| Applied revision `rev-7c93bb93e65b4f5a9b7340bf513437c0` | **unchanged** |

The new pending draft is the operator SAVE DRAFT at `14:37:36Z`. It is not live configuration.

---

## Safety posture

| Constraint | Confirmed |
|---|---|
| No APPLY clicked or called | **YES** |
| Draft not modified by this pass | **YES** |
| No chain activation | **YES** — applied enablement unchanged |
| Executor addresses not modified | **YES** — all empty; Base warning expected |
| SHADOW not started | **YES** |
| Containers not restarted or redeployed | **YES** — StartedAt `2026-10-03T12:42:03Z`, RestartCount `0` |
| Mongo read-only | **YES** |
| Secrets fingerprint-only | **YES** |

---

## Three-tier live probe

Persistence and ordering above are unchanged. Read-only JSON-RPC results for each stored URL are in `docs/certification/SIX_NETWORK_THREE_TIER_RPC_DRAFT_CERT_20261003.md`.

That probe did not APPLY and did not edit the draft. Polygon still has two stored URLs. Public last-resort endpoints on Base, Ethereum, and Arbitrum returned HTTP 403. Optimism’s public RPC and BNB’s public RPC answered; BNB `eth_getLogs` returned JSON-RPC `-32005` limit exceeded.

## STOP

**STOP.** Six-network draft certification is complete. The draft is pending and is not the applied configuration. Do not APPLY from this note.
