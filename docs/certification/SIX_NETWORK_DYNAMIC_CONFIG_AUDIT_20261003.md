# SIX-NETWORK ACTIVATION + DYNAMIC NETWORK CONFIG — AUDIT (Part A + Part B)

- **Status:** **IMPLEMENTED (code only)** — see commit pointer below. No live Network Config APPLY, no Mongo mutation, no restart/redeploy, no AUTOEXEC/RUNTIME/live enablement, no six-network activation / SHADOW.
- **IMPLEMENTED pointer:** search `git log --oneline --grep='six-network dynamic Network Config'` for the implementation commit (FE allowlist + Add Network + generalised env_sync). Live APPLY / six-network activation / SHADOW remain blocked. **STOP — await activation GO.**
- **Date (UTC context):** 2026-10-03
- **Cert workspace:** `/home/raghu/projects/arbicore-x-cert`
- **Production (read-only):** `/home/raghu/projects/arbicore-x-v2`
- **Live container:** `arbicore-x-backend-new` · image `arbicore-x-backend:ws-a-befb14e-20261002`
- **Secrets policy:** Alchemy credentials never printed. Fingerprint = `sha256(<key>)[:8]` where `<key>` is the path segment after `/v2/`. URLs shown as host + `/v2/<REDACTED>` + `fp=…`.
- **Canonical store:** existing Mongo `NetworkConfigRepo` / `arbicore_config` kind=`network` — **no second network-configuration architecture**.

---

## Executive verdict

| Question | Answer |
|---|---|
| Why UI shows **five** panels? | Frontend hard-codes `CHAINS` / `chains` to five names and **omits `bnb`**. Backend schema already has six. |
| Is BNB / sixth network schema-ready? | **YES** — `SUPPORTED_CHAINS` includes `"bnb"`; Mongo `chains_enabled.bnb` exists; validation accepts `bnb`. |
| Is env_sync six-chain today? | **NO** — `sync_env_from_network_config(..., chain="base")` default; all callers omit `chain` → **Base-only**. |
| Partial six-support already? | **YES (backend / runtime / tests)**; **NO (Network Settings UI + env_sync breadth)**. |
| Base PAYG confirmation | Primary fp **`cd505118`**, fallback **`mainnet.base.org`**, stale **`ce00e63d` ABSENT**. |
| Anything modified this turn? | **Only this audit document** created. No APPLY, no code/config/Mongo/git changes. |

**STOP — wait for explicit GO before any coding (Parts D–K).**

---

## 1. Architecture findings (FE / BE / Mongo / env_sync / API)

### 1.1 Frontend (Network Settings)

- **File:** `app/frontend/src/v2/pages/SettingsPage.jsx`
- **Component:** `Network()` (Phase 10.1)
- **API client:** `app/frontend/src/v2/lib/api.js` → `networkGet` / `networkValidate` / `networkDraft` / `networkApply` / `networkRollback` / `networkHistory`
- **Rendering model:** fixed `const CHAINS = [...]` then `CHAINS.map(...)` → one panel per entry (toggle, RPC CSV, executor, MEV, gas, native price).
- **No "Add Network" control** exists in Settings UI (search: no matches).
- **Same five-list hard-code** also appears in:
  - `SettingsPage.jsx` Scanner section: `const chains = ["base", "ethereum", "arbitrum", "optimism", "polygon"]` (line ~773)
  - `FlashLoanOperatorPage.jsx`: `const CHAINS = ["base", "ethereum", "arbitrum", "optimism", "polygon"]`
- Cert and prod FE copies are **identical** on this hard-code.

### 1.2 Backend model / schema

- **File:** `app/backend/arbicore/config/persistent.py`
- **Allowlist:**

```text
SUPPORTED_CHAINS = ("base", "ethereum", "arbitrum", "optimism", "polygon", "bnb")
```

- **Default document shape** (`DEFAULT_NETWORK_CONFIG`):
  - `rpc_urls[chain]`: ordered list (index 0 = primary, rest = failover)
  - `chains_enabled[chain]`: bool (default only `base=true`)
  - `executor_addresses`, `gas_settings`, `native_price_usd`, `mev_relay_urls`
  - `seeded_from_env`
- **Validation:** rejects unknown chains; checks URL scheme `http(s)`; checks executor `0x` length; **does not** live-probe RPC / chainId (format-only).
- **Seed:** `ensure_seed_from_env` bootstraps **Base only** from env when Mongo empty; never overwrites existing.
- **Scanner config** (`scanner_config.py`) imports the **same** `SUPPORTED_CHAINS` (includes `bnb`) for `networks` defaults — FE Scanner UI still omits `bnb`.

### 1.3 Mongo storage

| Item | Value |
|---|---|
| Collection (current) | `arbicore_config` · `_id` / `kind` = `network` |
| Drafts | `arbicore_config_drafts` |
| Audit | `arbicore_config_audit` |
| Live revision | `rev-7c93bb93e65b4f5a9b7340bf513437c0` |
| Updated | `2026-10-03T04:57:17Z` by `admin` (reason `"fetch"` — PAYG APPLY) |
| Draft | none |

**No second network config store.** Other kinds in `arbicore_config` (account / execution / operational / telegram / scanner*) are separate domains, not alternate RPC architecture.

### 1.4 env_sync behavior

- **File:** `app/backend/arbicore/config/env_sync.py`
- **Signature:** `sync_env_from_network_config(network_repo, *, chain: str = "base")`
- **Per call, for that single chain only:**
  - `ARBICORE_RPC_URL` ← primary (also written for non-base if called with other chain — currently unused)
  - `ARBICORE_RPC_URL_<CHAIN>` ← primary
  - `<CHAIN>_RPC_URL` ← primary (legacy)
  - `PROVIDER_RPC_URLS_<CHAIN>` ← full CSV with managed provenance marker (G5.79)
  - `ARBICORE_EXECUTOR_ADDRESS_<CHAIN>` if set
- **Call sites** (`server.py`): startup + `POST …/network/apply` + `POST …/network/rollback` — **all call with default → Base only**.
- **Implication:** even if Mongo later stores eth/arb/op/poly/bnb RPC lists, **APPLY will not env_sync them** until env_sync is generalized.

### 1.5 Validation / apply endpoints

| Method | Path | Auth | Behavior |
|---|---|---|---|
| GET | `/api/arbicore/settings/network` | open (observed) | returns full current config + draft |
| POST | `/api/arbicore/settings/network/validate` | operator | `NetworkConfigRepo.validate` (schema only) |
| POST | `/api/arbicore/settings/network/draft` | operator | save draft after validate |
| POST | `/api/arbicore/settings/network/apply` | operator | apply → **env_sync(base)** → `sync_rpc_providers_from_env` |
| POST | `/api/arbicore/settings/network/rollback` | operator | rollback → same sync path |
| GET | `/api/arbicore/settings/network/history` | open | audit history |

**Read-only validation status today:** schema validation is available via POST validate (auth) or by inspecting GET config; **no RPC health is part of validate**. Live health is separately queryable via `GET /api/arbicore/rpc/check` (Base-focused) and `GET /api/arbicore/providers/status`.

### 1.6 Related runtime path (not a second Network Config)

- Docker / compose `backend/.env` supplies bootstrap `ARBICORE_RPC_URL_<CHAIN>` for all six (fp `5e5d5bb1` on Alchemy singles).
- `providers/bootstrap._rpc_urls` precedence: `PROVIDER_RPC_URLS_<CHAIN>` → `PROVIDER_RPC_URL_<CHAIN>` → `ARBICORE_RPC_URL_<CHAIN>` / global → optional public `DEFAULT_RPC_URLS` augmentation.
- Quoter candidates (`quoter._rpc_url_candidates`) read per-chain env + `PROVIDER_RPC_URLS_<CHAIN>`.
- These are **consumers** of env/Network Config — not a parallel operator config UI.

---

## 2. Why five UI panels (exact hard-codes)

| Location | Exact constant | Count | Omits |
|---|---|---:|---|
| `SettingsPage.jsx:541` | `const CHAINS = ["base", "ethereum", "arbitrum", "optimism", "polygon"];` | 5 | **`bnb`** |
| `SettingsPage.jsx:773` (Scanner) | `const chains = ["base", "ethereum", "arbitrum", "optimism", "polygon"];` | 5 | **`bnb`** |
| `FlashLoanOperatorPage.jsx:17` | `const CHAINS = ["base", "ethereum", "arbitrum", "optimism", "polygon"];` | 5 | **`bnb`** |

**Root cause:** the Network Settings panel list is a **frontend hard-coded five-tuple**, not driven by `SUPPORTED_CHAINS`, Mongo keys, or an API catalog. Backend already accepts/stores six; UI simply never renders the sixth.

Introduced with Phase 10.1 UI in canonical merge `6327c07` (same five-list); backend later gained/kept six-chain seam (`d9345da`, G5.79 `48f3840`) without updating the FE constant.

---

## 3. Schema capabilities vs gaps (dynamic + Add Network + BNB)

### Capabilities (reuse)

| Capability | Status |
|---|---|
| Six named EVM chains including **`bnb`** | Present in `SUPPORTED_CHAINS` |
| Ordered multi-RPC primary/failover lists | Present (`rpc_urls[chain][]`) |
| Per-chain enable flags | Present (`chains_enabled`) |
| Draft / Validate / Apply / Rollback / Audit | Present |
| Scanner global networks keyed by `SUPPORTED_CHAINS` | Present (BE) |
| ProviderRegistry six-chain registration | Present (`_EVM_CHAINS` includes `bnb`) |
| Tests covering six-chain RPC seam / H05–H06 / G5.79 | Present |

### Gaps

| Gap | Detail |
|---|---|
| FE not schema-aligned | Hard-coded 5; no BNB panel; no Add Network |
| env_sync Base-only | APPLY/startup do not push non-Base Mongo RPC lists into env/Provider managed CSV |
| Not fully “dynamic” | Allowlist is a **fixed tuple**, not open-ended chain IDs; unknown chains rejected by validate |
| Seed Base-centric | First-boot seed only fills Base from env |
| Validate ≠ health | No chainId/block probe in validate endpoint |
| GET leaks secrets | `GET /settings/network` returns **full RPC URLs including Alchemy keys** (observed) — operator/API consumers see plaintext; cert docs must keep fingerprints only |
| Docker drift | Non-Base + Base bootstrap `.env` still fp `5e5d5bb1` / `mainnet.base.org`; Mongo Base is PAYG `cd505118` |
| bootstrap global fallthrough | `_rpc_urls` may fall back to global `ARBICORE_RPC_URL` (vs `resolve_rpc_url_from_env` which is Base-only-alias) — latent cross-chain leak if per-chain env missing |

**BNB sixth network:** **schema-ready**. Enabling it for operators is primarily FE exposure + writing `rpc_urls.bnb` + expanding env_sync — **not** a new schema.

**True dynamic Add Network (arbitrary L2):** **not schema-ready** without extending the allowlist (and adapters/readiness/quoter). Recommended refinement: drive UI from backend-exported `SUPPORTED_CHAINS` (single source of truth) + optional “Add from allowlist” — **still one architecture**.

---

## 4. Six-network current-state matrix (redacted)

**Fingerprint legend**

| fp8 | Meaning |
|---|---|
| `cd505118` | Base PAYG Alchemy key (Mongo Network Config primary) |
| `5e5d5bb1` | Docker bootstrap Alchemy key (non-Base env + legacy Base global) |
| `ce00e63d` | Retired / stale — **ABSENT** from Mongo Network Config |

### Matrix

| Chain | chainId | Mongo durable RPCs | chains_enabled | env_sync loads? | Docker/bootstrap env (non-authoritative when Mongo nonempty for Base) | ProviderRegistry (live) | Probe (read-only, configured URLs only) |
|---|---:|---|---|---|---|---|---|
| **Ethereum** | 1 | *(none — key absent in `rpc_urls`)* | false | **No** (env_sync Base-only; Mongo empty) | Alchemy `eth-mainnet…` fp **`5e5d5bb1`** | `rpc_ethereum_0_…alchemy…` prio 100 HEALTHY | HTTP 200, chainId **1**, block≈26110514, ~293ms |
| **Arbitrum** | 42161 | none | false | No | Alchemy `arb-mainnet…` fp **`5e5d5bb1`** | `rpc_arbitrum_0_…` prio 100 HEALTHY | HTTP 200, chainId **42161**, block≈511244168, ~124ms |
| **Base** | 8453 | **[0]** Alchemy `base-mainnet…` fp **`cd505118`** · **[1]** `mainnet.base.org` | **true** | **Yes** (only chain synced) | Proc1 bootstrap: `ARBICORE_RPC_URL` fp `5e5d5bb1`; `ARBICORE_RPC_URL_BASE=mainnet.base.org` (overridden in-process by env_sync for live path) | **[0]** alchemy prio 100 · **[1]** `mainnet_base_org` prio 101 — both HEALTHY | Primary: HTTP 200, chainId **8453**, block≈52112778, ~121ms. Fallback `mainnet.base.org`: **HTTP 403** on this audit’s probe (see note). `rpc/check`: READY, masked host `base-mainnet.g.alchemy.com` |
| **Optimism** | 10 | none | false | No | Alchemy `opt-mainnet…` fp **`5e5d5bb1`** | `rpc_optimism_0_…` prio 100 HEALTHY | HTTP 200, chainId **10**, block≈157708063, ~136ms |
| **Polygon** | 137 | none | false | No | Alchemy `polygon-mainnet…` fp **`5e5d5bb1`** | `rpc_polygon_0_…` prio 100 HEALTHY | HTTP 200, chainId **137**, block≈94873176, ~163ms |
| **BNB Chain** | 56 | none | false | No | Alchemy `bnb-mainnet…` fp **`5e5d5bb1`** | `rpc_bnb_0_…` prio 100 HEALTHY | HTTP 200, chainId **56**, block≈125449713, ~157ms |

**Base PAYG confirmation (mandatory):**

| Check | Result |
|---|---|
| PAYG primary fp `cd505118` | **YES** — Mongo `rpc_urls.base[0]` |
| Fallback `mainnet.base.org` | **YES** — Mongo `rpc_urls.base[1]` |
| Stale `ce00e63d` | **ABSENT** from Mongo Network Config Alchemy fps |

**Notes**

1. Non-Base chains are **runtime-reachable via Docker env → ProviderRegistry**, but **not durable in Network Config** and **not env_synced from Mongo**.
2. `mainnet.base.org` returned **403** from inside the container during this audit; earlier same-day post-APPLY verify (05:00Z) recorded 200. Registry still marks fallback HEALTHY (score-based / prior). Treat fallback as **configured but currently probe-flaky**.
3. No endpoints were invented; probes used Mongo URLs (Base) or already-present Docker `ARBICORE_RPC_URL_<CHAIN>` only.
4. Schema validation status without APPLY: live document is structurally valid (six `chains_enabled` keys; Base RPCs https). POST validate not executed (would require operator auth write-path posture); format rules are as coded.

### Failover behavior notes

- **Authoritative ordering:** Mongo `rpc_urls[chain][]` index 0 primary.
- **Base failover path:** env_sync → managed `PROVIDER_RPC_URLS_BASE` CSV → ProviderRegistry priorities 100, 101… → quoter/registry consumers.
- **Non-Base today:** single Alchemy URL from Docker env; bootstrap may also append public `DEFAULT_RPC_URLS` as secondary when using canonical env (publicnode/bsc defaults) — **not** operator Network Config failover lists.
- **chains_enabled:** UI/scanner intent flags; env_sync does **not** currently gate export on `chains_enabled`.

---

## 5. Partial six-support already present?

| Layer | Six-support? | Evidence |
|---|---|---|
| BE `SUPPORTED_CHAINS` | **Yes** | includes `bnb` |
| Mongo live `chains_enabled` | **Yes (keys)** | all six present; only Base enabled; only Base has RPCs |
| FE Network Settings | **No** | hard-coded five |
| FE Scanner chain toggles | **No** | hard-coded five |
| env_sync | **No** | Base-only |
| ProviderRegistry / bootstrap | **Yes** | eth/arb/base/op/poly/bnb registered |
| Quoter / six-chain seam tests | **Yes** | `test_six_chain_rpc_seam.py`, H05/H06, Phase2, etc. |
| G5.79 multi-RPC sync | **Partial** | mechanism is chain-parameterized; production callers only sync Base |

**Conclusion:** six-network product capability is **partially present** in backend/runtime; **operator Network Config surface + env_sync breadth** are the primary activation blockers for durable six-network config (BNB panel included).

---

## 6. Proposed change plan (**proposal only — NOT implemented**)

Reuse existing `NetworkConfigRepo` + Settings Network tab. Do **not** invent a second config system.

### Reuse

- Schema / validate / draft / apply / rollback / audit
- G5.79 managed `PROVIDER_RPC_URLS_<CHAIN>` + `sync_rpc_providers_from_env`
- ProviderRegistry failover model
- Existing API paths under `/api/arbicore/settings/network/*`

### Likely files to touch (after GO)

| File | Change (proposal) |
|---|---|
| `app/frontend/src/v2/pages/SettingsPage.jsx` | Drive panels from backend-provided / shared six-list (`SUPPORTED_CHAINS` incl. `bnb`); optional Add Network = enable unused allowlist chain + empty RPC row; fix Scanner `chains` hard-code |
| `app/frontend/src/v2/pages/FlashLoanOperatorPage.jsx` | Align CHAINS with six-list |
| `app/frontend/src/v2/lib/api.js` | Optionally expose `supported_chains` from GET if BE adds it |
| `app/backend/arbicore/config/env_sync.py` | Loop `SUPPORTED_CHAINS` (or `chains_enabled`) instead of single `chain="base"`; keep Base global alias semantics explicit |
| `app/backend/server.py` | Call multi-chain env_sync on startup/apply/rollback |
| `app/backend/tests/test_phase10_10_env_sync.py` + G5.79 tests | Cover non-Base export + isolation + no Base leakage |
| Optional: GET redaction | Mask `/v2/<key>` in GET responses (fingerprints only) — safety hardening |
| Ops (separate, not code): | Mirror PAYG URLs into Docker `.env` for recreate durability |

### Recommended sequencing after GO

1. **Align FE to `SUPPORTED_CHAINS` (show BNB)** — smallest visible fix; still one architecture.
2. **Generalize env_sync to all configured chains** — required for Mongo durability → runtime for non-Base.
3. **Add Network UX** = pick from remaining allowlist / enable toggle (not free-form chain invent).
4. **Only if required later:** extend allowlist for true dynamic chains (adapters, readiness, quoter) — still extend `SUPPORTED_CHAINS`, do not fork schema.

### Explicitly out of scope until GO

- APPLY Network Config for eth/arb/op/poly/bnb
- Restart / redeploy / AUTOEXEC / RUNTIME / live
- Inventing RPC endpoints
- Second config architecture

---

## 7. Risks / safety constraints

1. **APPLY is live-mutating** — touches Mongo + process env + ProviderRegistry; do not APPLY during audit/cert without explicit GO.
2. **env_sync Base-only today** — filling UI for BNB without env_sync generalization would create **false operator confidence** (Mongo saved, runtime still Docker-only).
3. **GET `/settings/network` returns plaintext Alchemy URLs** — treat as credential exposure risk; never paste into cert docs/chat; prefer fingerprint redaction before wider UI work.
4. **Docker `.env` drift** — recreate can reintroduce `5e5d5bb1` / public Base unless mirrored after PAYG.
5. **bootstrap vs resolve_rpc_url_from_env alias semantics differ** — risk of Base URL leaking to empty non-Base if per-chain env removed.
6. **Public DEFAULT_RPC_URLS** may silently augment provider lists — distinguish operator evidence vs public fallback in certifications.
7. **Do not enable AUTOEXEC / RUNTIME / live** as part of network UI work.
8. **Preserve uncommitted cert material** — no git reset/clean.
9. **Fallback Base.org 403** observed this session — failover resilience may be weaker than registry HEALTHY implies; re-probe before relying on public fallback.
10. **chains_enabled=false** on five networks — enabling RPCs without enablement/scanner policy review could expand load/CU unexpectedly.

---

## 8. Explicit STOP

**STOP.** This deliverable is Part A (+ Part B read-only) only.

- No coding started for Parts D–K.
- No Network Config APPLY.
- No Mongo writes.
- No restart/redeploy.
- No AUTOEXEC/RUNTIME/live changes.
- **Await explicit GO** before implementation.

---

## Appendix A — Relevant tests (existing)

| Suite | Focus |
|---|---|
| `tests/test_phase10_config.py` | NetworkConfigRepo validate/seed/apply/rollback |
| `tests/test_phase10_10_env_sync.py` | Base env_sync export / idempotence |
| `tests/test_g5_79_multirpc_provider_sync.py` | Managed multi-RPC Base sync |
| `tests/test_six_chain_rpc_seam.py` | Six-chain env resolution, no Base leakage |
| `tests/test_cert_rpc_env_contract.py` | Provider sync across `SUPPORTED_CHAINS` |
| H05/H06 / Phase2 multichain suites | Runtime six-chain including `bnb` |

## Appendix B — Relevant git history (selected)

| Commit | Relevance |
|---|---|
| `6327c07` | Canonical v2 merge — FE five-chain Network Settings + BE `SUPPORTED_CHAINS` six-tuple origin |
| `d9345da` | Six-chain operator-RPC seam; Base-only global alias |
| `48f3840` | G5.79 managed multi-RPC provider sync (env_sync + registry) |
| `26d36ee` / `a7f9634` | One operator RPC per chain for economic + chain-scoped seam |
| H05/H06 / Phase2 commits | Six-chain discovery/runtime (product), not Network Settings UI |

## Appendix C — Audit actions performed (read-only)

- Inspected cert + prod source for FE/BE/env_sync/API/tests
- Read Mongo `arbicore_config` network doc + audit trail (redacted)
- Queried live `GET /api/arbicore/settings/network`, `/rpc/check`, `/providers/status`
- Probed already-configured RPC URLs only (Mongo Base + Docker per-chain)
- Created **only** this markdown report under `docs/certification/`
)
