# Alchemy PAYG — Network Config Change Plan (PREPARE ONLY) — 2026-10-03

- **Status:** **PREPARE ONLY** — no APPLY, no VALIDATE-as-live-change, no restart/redeploy, no source/env mutation, no campaign reset
- **Fetched (UTC):** `2026-10-03T04:17:46Z` via `GET http://127.0.0.1:8001/api/arbicore/settings/network` (read-only)
- **Container (pre + post read):** `arbicore-x-backend-new` · Image `arbicore-x-backend:ws-a-befb14e-20261002`
  - **StartedAt:** `2026-10-02T15:08:52.884157323Z` (**unchanged**)
  - **RestartCount:** `0` (**unchanged**)
- **Canonical store:** Mongo Network Config (`kind=network`) → `rpc_urls.<chain>[]` (index **0 = PRIMARY**, rest = FALLBACK)
- **Live revision:** `rev-615fa528802d4bd8ab7074b03bfdf373` · `updated_at=2026-09-27T09:31:23.271601+00:00` · `updated_by=admin`
- **Live RPC probe:** `GET /api/arbicore/rpc/check` → `rpc_url_masked=mainnet.base.org`, `chain_id=8453`
- **Draft:** `null` (no pending draft)
- **Secrets policy:** Alchemy credentials never printed. Fingerprint = `sha256(<key>)[:8]` where `<key>` is the path segment after `/v2/` (matches prior cert fps `ce00e63d` / `5e5d5bb1`). URLs shown as `https://<host>/v2/<REDACTED>`.

**Prior evidence:** `ALCHEMY_PAYG_CONFIG_DISCOVERY_20261002.md`, `BASE_ALCHEMY_ROOT_CAUSE_AUDIT_20261002.md`.

---

## 1. Per-chain current Network Config `rpc_urls` (live)

| Chain | Enabled | Entries | Index | Role | Host | Path shape | Alchemy fp8 | `ce00e63d` | `5e5d5bb1` |
|---|---|---:|---:|---|---|---|---|---|---|
| **Base** | **ON** | 2 | 0 | **PRIMARY** | `mainnet.base.org` | `/` | n/a | no | no |
| **Base** | **ON** | 2 | 1 | **FALLBACK** | `base-mainnet.g.alchemy.com` | `/v2/<REDACTED>` | **`ce00e63d`** | **YES** | no |
| Ethereum | OFF | 0 | — | — | *(absent / empty list)* | — | — | no | no |
| Arbitrum | OFF | 0 | — | — | *(absent / empty list)* | — | — | no | no |
| Optimism | OFF | 0 | — | — | *(absent / empty list)* | — | — | no | no |
| Polygon | OFF | 0 | — | — | *(absent / empty list)* | — | — | no | no |
| BNB | OFF | 0 | — | — | *(absent / empty list in `rpc_urls`; key absent)* | — | — | no | no |

**Summary**

| Check | Result |
|---|---|
| `ce00e63d` in Network Config | **YES** — only at `rpc_urls.base[1]` |
| `5e5d5bb1` in Network Config | **NO** |
| Non-Base Network Config RPC lists | **empty / absent** (not authoritative for eth/arb/op/poly/bnb today) |

### Non-canonical note (Docker `.env` only — not applied)

Docker `deployment/upgrade/backend/.env` still carries Alchemy fp **`5e5d5bb1`** on `ARBICORE_RPC_URL`, archive, and eth/arb/op/poly/bnb singles; Base primary env is `mainnet.base.org`. For Base, `env_sync` overwrites process env from Network Config on start/APPLY — so Docker alone is **not durable**. This plan does **not** edit `.env`.

---

## 2. Exact Base entry that must be replaced

| Item | Value |
|---|---|
| **Field** | `rpc_urls.base[1]` |
| **Current role** | FALLBACK (stale) |
| **Current host/path** | `https://base-mainnet.g.alchemy.com/v2/<REDACTED>` |
| **Current fp8** | **`ce00e63d`** |
| **Action** | **Remove / replace** this credential entirely (retire `ce00e63d`) |

**Also required (reorder + promote):** after retiring `[1]`, the target list is **not** “keep public primary.” Target architecture flips roles:

| Index | Target role | Target value |
|---:|---|---|
| **0** | **PRIMARY** | `https://base-mainnet.g.alchemy.com/v2/<NEW_PAYG>` *(operator pastes real PAYG key; placeholder only here)* |
| **1** | **FALLBACK** | `https://mainnet.base.org` *(today’s `[0]` moves here)* |

So the live change is: **retire `rpc_urls.base[1]` (`ce00e63d`)**, **insert new PAYG Alchemy as `[0]`**, **keep public Base as sole fallback `[1]`**.

---

## 3. Target architecture (placeholders only)

| Chain | PRIMARY `[0]` | FALLBACK `[1+]` |
|---|---|---|
| Base | `https://base-mainnet.g.alchemy.com/v2/<NEW_PAYG>` | `https://mainnet.base.org` |
| Ethereum | `https://eth-mainnet.g.alchemy.com/v2/<NEW_PAYG>` | *(none in Network Config today; leave empty or add a validated secondary if operator has one)* |
| Arbitrum | `https://arb-mainnet.g.alchemy.com/v2/<NEW_PAYG>` | *(none in Network Config today)* |
| Optimism | `https://opt-mainnet.g.alchemy.com/v2/<NEW_PAYG>` | *(none in Network Config today)* |
| Polygon | `https://polygon-mainnet.g.alchemy.com/v2/<NEW_PAYG>` | *(none in Network Config today)* |
| BNB | `https://bnb-mainnet.g.alchemy.com/v2/<NEW_PAYG>` | *(none in Network Config today)* |

Use the **same** `<NEW_PAYG>` app key across Alchemy networks unless the operator intentionally creates per-chain apps. **Never invent a real key.**

---

## 4. Exact Settings → Network UI change plan (field-by-field)

**Path:** Operator UI → **Settings › Network** (`/v2/settings/network`)  
**Panel:** “Per-chain RPC endpoints”  
**Buttons (do not press APPLY until GO):** `VALIDATE` → (`SAVE DRAFT` optional) → **`APPLY`** (STOP before this) → `ROLLBACK` (emergency only)

### 4.1 BASE card (`data-testid=v2-settings-network-chain-base`)

| UI field | Current (redacted) | Change to |
|---|---|---|
| Chain toggle (`v2-settings-network-toggle-base`) | **ON** | Leave **ON** |
| **RPC URLs (comma-separated; primary first)** (`v2-settings-network-rpc-base`) | `https://mainnet.base.org, https://base-mainnet.g.alchemy.com/v2/<REDACTED:ce00e63d>` | `https://base-mainnet.g.alchemy.com/v2/<NEW_PAYG>, https://mainnet.base.org` |
| Executor address | `0x0E3FDb0F0E615A517588BD44ac6C78Bb7615927f` | **Do not change** |
| MEV relay URL | *(empty/as-is)* | **Do not change** |
| Gas price (gwei) | *(as-is / null)* | **Do not change** |
| Native price (USD) | *(as-is / null)* | **Do not change** |

**APPLY reason (when authorized):**  
`PAYG Alchemy primary; public Base fallback; retire stale fp ce00e63d`

### 4.2 ETHEREUM / ARBITRUM / OPTIMISM / POLYGON cards

| UI field | Current | Change to (when enabling PAYG for that chain) |
|---|---|---|
| Chain toggle | **OFF** | Leave **OFF** unless multi-chain enable is separately authorized |
| **RPC URLs (comma-separated; primary first)** | *(empty)* | If populating for durability: `https://<alchemy-host>/v2/<NEW_PAYG>` only — **no Network Config secondary exists today**. Do **not** invent a public fallback. |
| Executor / MEV / gas / native | as-is | **Do not change** unless part of a separate enablement plan |

Recommended for this GO window: **change Base RPC URLs only**; leave other chain RPC fields empty and toggles OFF (matches current enablement). Optionally pre-stage PAYG URLs into disabled-chain fields for restart durability later — still **no APPLY** until GO.

### 4.3 BNB

- Backend `chains_enabled` / schema include `bnb`.
- Frontend `SettingsPage.jsx` `CHAINS` array is currently `base, ethereum, arbitrum, optimism, polygon` — **no BNB card in UI**.
- For BNB PAYG later: use authenticated `POST /api/arbicore/settings/network/apply` with `rpc_urls.bnb`, or extend UI first. **Out of scope for this Base-first GO** unless operator explicitly expands scope.

### 4.4 Post-APPLY verification (only after GO — do not run apply now)

1. Fingerprint Network Config Base `[0]` → new fp ≠ `ce00e63d` (and ≠ `5e5d5bb1` if key rotated to fresh PAYG).
2. Confirm Base `[1]` host = `mainnet.base.org`, fp `n/a`.
3. Confirm **no** `ce00e63d` remains in any `rpc_urls.*.[*]`.
4. `GET /api/arbicore/rpc/check` → `rpc_url_masked` ≈ `base-mainnet.g.alchemy.com`.
5. APPLY response should include `env_synced` containing `ARBICORE_RPC_URL`, `ARBICORE_RPC_URL_BASE`, `PROVIDER_RPC_URLS_BASE` (and typically `BASE_RPC_URL`).
6. Mirror same URLs into `deployment/upgrade/backend/.env` via editor (mode `0600`) for recreate durability — **separate step; no restart unless authorized**.

---

## 5. API payload shape (reference only — DO NOT POST)

```json
{
  "reason": "PAYG Alchemy primary; public Base fallback; retire stale fp ce00e63d",
  "patch": {
    "rpc_urls": {
      "base": [
        "https://base-mainnet.g.alchemy.com/v2/<NEW_PAYG>",
        "https://mainnet.base.org"
      ]
    }
  }
}
```

Prefer UI paste over `curl` (avoids shell history). If scripting later, read URLs from a `0600` file — never put the key on the command line.

---

## 6. Explicit STOP

| Action | This session |
|---|---|
| Network Config **APPLY** | **NOT executed** |
| VALIDATE / SAVE DRAFT / ROLLBACK | **NOT executed** |
| Restart / redeploy / compose up | **NOT executed** |
| Source / `.env` / Mongo writes | **NOT executed** |
| Secrets printed | **NONE** |
| Container RestartCount / StartedAt | **Unchanged** (`0` / `2026-10-02T15:08:52.884157323Z`) |

**Wait for operator GO before any APPLY.** Hot APPLY would immediately `env_sync` Base RPC primary/failover into the live process without restart.
