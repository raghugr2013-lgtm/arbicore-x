# BNB / Add Network UI Gap — Read-Only Diagnosis — 2026-10-03

- Status: **READ-ONLY diagnosis**. No product change, no APPLY, no BNB activation, no Mongo write, no RPC change, no image rebuild, no container restart.
- Timestamp: 2026-10-03T10:40Z (GET history `generated_at` 2026-10-03T10:39:57Z).
- Secrets: none printed. Alchemy `/v2/<key>` fingerprints are `sha256(key)[:8]`. URLs are host + fingerprint only.
- Classification: **A (not deployed) and B (stale frontend)** — same cause. Not C, not D, not E as the reason the controls are missing.

---

## Verdict

The operator-accepted UI (`27dfab4`) is in git and is not what Caddy serves. The live SPA is `arbicore-x-frontend:0.1.0`, built **2026-09-01**, bundle **`/static/js/main.dc5f82a3.js`**. That bundle hardcodes `["base","ethereum","arbitrum","optimism","polygon"]` and contains no Add Network control and no `bnb` string.

The five validated network configurations are **not staged**. `GET /api/arbicore/settings/network` returns `draft: null`. The applied document is still the 2026-10-03T04:57:17Z Base PAYG revision. VALIDATE does not persist. The sslip access log has **zero** `POST /settings/network/draft` calls and **no APPLY after 04:57Z**.

No live configuration was changed by this diagnosis.

---

## A. Git implementation status

| Item | Value |
|---|---|
| Repo | `/home/raghu/projects/arbicore-x-cert` (git worktree of `arbicore-x-v2`) |
| Branch | `phase-b/h06-six-chain-runtime` @ `17a656e` (docs stamp). `27dfab4` is an ancestor. |
| Commit | `27dfab42ae6981b39628c04fd9d1b869c3f6c57b` |
| Author / date | 2026-10-03 10:27:04 +0200 |
| Subject | `feat(network): six-network dynamic Network Config UI + generalised env_sync` |
| v2 checkout | `/home/raghu/projects/arbicore-x-v2` HEAD `5bd9525` does **not** contain `supportedChains.js`. The implementation is on the cert worktree, not on that checkout. |

`27dfab4` file set (product):

| Path | Role |
|---|---|
| `app/frontend/src/v2/lib/supportedChains.js` | **added.** `FALLBACK_SUPPORTED_CHAINS` = base, ethereum, arbitrum, optimism, polygon, **bnb**. `resolveSupportedChains`, `unusedAllowlistChains`, `enableAllowlistedChain`. |
| `app/frontend/src/v2/lib/supportedChains.test.js` | **added.** |
| `app/frontend/src/v2/pages/SettingsPage.jsx` | Network list from `resolveSupportedChains`. Add Network select + ENABLE (draft only, does not APPLY). Scanner list = `FALLBACK_SUPPORTED_CHAINS`. |
| `app/frontend/src/v2/pages/FlashLoanOperatorPage.jsx` | `CHAINS = FALLBACK_SUPPORTED_CHAINS`. |
| `app/backend/server.py` | `GET /arbicore/settings/network` adds `supported_chains` from `NetworkConfigRepo.SUPPORTED_CHAINS`. |
| `app/backend/arbicore/config/env_sync.py` | Syncs every `SUPPORTED_CHAINS` entry. `ARBICORE_RPC_URL` remains **Base-only**. |
| `app/backend/arbicore/config/persistent.py` | Not modified by this commit. `SUPPORTED_CHAINS` already includes `bnb` (content-identical to the live image). |

Working tree of those product files matches `27dfab4` (`git diff 27dfab4 HEAD` on them is empty). Wallet-registry `SUPPORTED_CHAINS` is a **different** tuple and stays five chains (no `bnb`) in both `27dfab4` and the live image. That tuple feeds `GET /arbicore/execution/wallets`, not the Settings Network page.

Backend allowlist in `persistent.py` (git and live, identical sha256 `41c0865cd5b9a408…`):

```text
SUPPORTED_CHAINS = ("base", "ethereum", "arbitrum", "optimism", "polygon", "bnb")
```

`27dfab4` `env_sync` content sha256 `fdb8a6f8d5b57e49…`. Live image `env_sync` content sha256 `1b8844471ebd4fd6…` (different; see section 6).

---

## B. Live deployed frontend version

Caddy (`vqb-network`) sends `arbicorex.in`, `www.arbicorex.in`, and `144-91-78-175.sslip.io` non-API traffic to `arbicore-x-frontend:80`. That alias is container `81bc9a41f21f_arbicore-x-frontend` (`3f527d5c293a`). No volume mounts. Static files are the image.

| Item | Value |
|---|---|
| Image | `arbicore-x-frontend:0.1.0` |
| Image ID | `sha256:69e799f5fc9825c2f572ffa63991845dde3cd9fb4e27daaf7d0b3a22abccdd88` |
| Image created | 2026-09-01 21:05:01 +0200 |
| Container created / started | 2026-09-01T19:05:06Z / 2026-09-03T07:30:43Z |
| Runtime env | nginx only (`NGINX_VERSION=1.25.5`). No `REACT_APP_*` at runtime (CRA bakes env into the bundle). |
| Entrypoint | `/static/js/main.dc5f82a3.js` (823512 bytes, file mtime 2026-09-01 21:04 +0200) |
| Bundle sha256 | `34bd5f8f4cc5470b245ca1141d541445aa7602c3db707eac8153fc1337c6ee66` |
| CSS | `/static/css/main.8abf2014.css` |
| Other local frontend images | `arbicore-x-frontend:validator-5dd1cd86804d` (2026-08-25) only. **No image built from `27dfab4`.** |

Today’s sslip access log (operator Settings loads) fetched that same bundle:

- 2026-10-03T09:13:00Z `GET /static/js/main.dc5f82a3.js` 200
- 2026-10-03T10:28:11Z `GET /static/js/main.dc5f82a3.js` 200

`arbicore-x-nginx` is not on this path (unhealthy, separate compose). It does not serve this SPA.

---

## C. Whether `27dfab4` is deployed

**No.**

| Surface | Includes `27dfab4`? |
|---|---|
| Live frontend image / bundle | **No.** Image predates the commit by a month. Bundle string counts: `Add Network` 0, `addNetwork` 0, `supportedChains` 0, `supported_chains` 0, `enableAllowlistedChain` 0, `27dfab4` 0, `bnb` 0. |
| Live backend image | **Partial, by ancestry of older code, not by this commit.** Image `arbicore-x-backend:ws-a-befb14e-20261002` (`sha256:12759b11a783…`), container `arbicore-x-backend-new`, created 2026-10-02T15:08:40Z (started 15:08:52Z). That is **before** `27dfab4` (2026-10-03 08:27Z). `persistent.py` bytes match `27dfab4` (bnb already on the allowlist). `env_sync.py` and the network GET handler do **not** match `27dfab4`. |

Live bundle source map (`sourcesContent` for `v2/pages/SettingsPage.jsx`) still has:

```text
const CHAINS = ["base", "ethereum", "arbitrum", "optimism", "polygon"];
```

The same five-chain literal is in the Settings Scanner section and in `v2/pages/FlashLoanOperatorPage.jsx`. Recovered Settings source has `VALIDATE` / `SAVE DRAFT` / `APPLY` / `ROLLBACK` and **zero** occurrences of `Add Network` or `ENABLE`.

---

## D. Why BNB is missing from the UI

The live Settings Network page renders `CHAINS.map`, and `CHAINS` is the five-name constant above. BNB is not filtered out of a six-chain list. It was never compiled into this bundle.

`27dfab4` would show BNB even against the **current** backend: `resolveSupportedChains` uses `FALLBACK_SUPPORTED_CHAINS` (includes `bnb`) when the payload has no `supported_chains` field. The live GET omits that field (section E). The fallback still returns all six. Shipping the `27dfab4` frontend is sufficient for the BNB row and the Add Network control to appear. The backend image does not have to change for that display.

---

## E. Why Add Network is missing

Same bundle. `27dfab4` wires Add Network in `SettingsPage.jsx` (`data-testid="v2-settings-network-add"`): a select of allowlisted chains that are not yet `chains_enabled`, and ENABLE, which only mutates the in-memory form. The live source map has no `addNetwork` function and no “Add Network” label.

This is not an unwired control inside `27dfab4`. The control exists in that commit and is absent from the image Caddy serves.

---

## Not the cause (C / D / E)

| Class | Applies? | Why |
|---|---|---|
| C BNB filtered | **No** | No six-chain list in the bundle to filter. `resolveSupportedChains` is not in the bundle. |
| D Add Network not wired | **No** as a defect in `27dfab4` | Wired there. Missing on the live page because that file is not in the image. |
| E FE–BE contract | **Not why the controls are hidden** | Live `GET /api/arbicore/settings/network` returns only `config`, `draft`, `generated_at`. It does **not** return `supported_chains` (confirmed `has_supported_chains False` at 2026-10-03T10:37:35Z). `27dfab4` frontend falls back to six chains when that field is absent, so the omission does not hide BNB. |

E is a **separate backend gap** for a later APPLY, not for this UI symptom. Live `sync_env_from_network_config(..., chain: str = "base")` exports **one** chain and defaults to base, and it writes the global `ARBICORE_RPC_URL` for that chain. `27dfab4` syncs every `SUPPORTED_CHAINS` entry and keeps `ARBICORE_RPC_URL` Base-only. An APPLY of non-Base RPC on the **current** image would persist Mongo (allowlist already includes `bnb`) and would **not** export `ARBICORE_RPC_URL_<CHAIN>` for the other five chains.

---

## 5–6. Backend BNB persistence and env_sync

Live container `arbicore-x-backend-new` on `vqb-network` alias `arbicore-x-backend` (this is the Caddy upstream).

| Check | Live image `ws-a-befb14e-20261002` | Git `27dfab4` |
|---|---|---|
| `NetworkConfigRepo.SUPPORTED_CHAINS` | base, ethereum, arbitrum, optimism, polygon, **bnb** | identical file |
| `validate()` rejects unknown chains | yes, against that tuple, so `bnb` is legal | same |
| `GET /settings/network` `supported_chains` | **absent** | present |
| `env_sync` | single chain, default `"base"` | all six; `ARBICORE_RPC_URL` Base-only |
| Wallet-registry `SUPPORTED_CHAINS` | five chains, no bnb | unchanged by `27dfab4` |

BNB **persistence is already supported** by the live backend (draft/validate/apply accept `bnb`). BNB **env export on APPLY is not** supported until the `27dfab4` `env_sync` is what the process runs. Neither has been used to store the five new configs.

---

## F. Are the five validated configurations safely staged?

**No. They are not on the server.**

Read-only `GET http://127.0.0.1:8001/api/arbicore/settings/network` (200, 1159 bytes, 2026-10-03T10:37:35Z):

| Field | Value |
|---|---|
| `draft` | **`null`** |
| `config.revision_id` | `rev-7c93bb93e65b4f5a9b7340bf513437c0` |
| `config.updated_at` | 2026-10-03T04:57:17.836236Z |
| `config.updated_by` | `admin` |
| `chains_enabled` | base **true**; ethereum, arbitrum, optimism, polygon, bnb **false** |
| `rpc_urls` keys | **`base` only** (2 endpoints) |
| base `[0]` | host `base-mainnet.g.alchemy.com`, fingerprint **`cd505118`** |
| base `[1]` | host `mainnet.base.org` (no `/v2/` key) |
| `executor_addresses.base` | empty |

`bnb: false` is the schema default from `SUPPORTED_CHAINS`. It is not evidence that an operator entered a BNB RPC. `rpc_urls` has no `bnb` key and no other non-base key.

History (`GET /api/arbicore/settings/network/history`, 5 revisions). Latest is that same revision:

| at (UTC) | action | reason (truncated) | current RPC fingerprint |
|---|---|---|---|
| 2026-10-03T04:57:17Z | apply | `fetch` | **`cd505118`** + `mainnet.base.org` |
| 2026-09-27T09:31:23Z | apply | G5.66 Base.org primary | historical `ce00e63d` (not current) |
| 2026-09-07 (three earlier applies) | apply | executor replace / boot seed | historical `ce00e63d` |

**`ce00e63d` is not the current primary.** It remains only inside older history snapshots. Current primary matches the PAYG fingerprint `cd505118`.

sslip vhost `arbicorex.access.log` (arbicorex.in log has **no** `settings/network` hits):

| UTC | HTTP | Path | Notes |
|---|---|---|---|
| 2026-10-03T04:57:18Z | 200 | `POST …/network/apply` | last APPLY; matches revision above |
| 2026-10-03T10:01:18Z – 10:28:01Z | **401** | `POST …/network/validate` | four calls, 30-byte body; not stored |
| 2026-10-03T10:28:04Z | 200 | `GET /dashboard/settings/network` | then the stale JS bundle |
| 2026-10-03T10:30:17Z | 200 | `POST …/network/validate` | response size **169** |
| 2026-10-03T10:32:08Z | 200 | `POST …/network/validate` | response size **169** |

Counts on that log: validate 9, **draft 0**, apply 4 (the newest apply is 04:57Z).

`POST /settings/network/validate` only returns `{ok, errors, warnings}` plus `generated_at`. It does not write Mongo. `save_draft` is a different route and was never called on this log. The Settings form copies `data.config` into React state; a reload drops unsaved edits. A pending draft, if one existed, would only show a banner — and `draft` is null.

The two HTTP 200 validates are consistent with the operator’s PASS (169-byte responses, not error pages). This diagnosis did not replay them and did not read request bodies. The stale page has RPC inputs for five chains and **no BNB field**, so a normal session of this bundle cannot submit a BNB URL. Whatever was typed is only in that browser tab, if the tab is still open.

**Not safe to treat as staged.** A refresh returns the Base-only PAYG document. Re-entry plus **SAVE DRAFT** (not VALIDATE alone) is required if those values must be kept. Do not APPLY as part of closing this UI gap.

---

## G. Exact minimal remediation (not executed)

1. **Build a frontend image from `27dfab4`** (HEAD `17a656e` has the same product files) and point the live `arbicore-x-frontend` service at it. Caddy already targets that service name. Do not change Network Config, Mongo, or RPC while doing this.
2. **Confirm the new bundle** is what the browser loads: not `main.dc5f82a3.js`; strings include `Add Network` and `bnb`; Settings Network renders six chain rows. With the current backend (no `supported_chains` field), the `27dfab4` fallback still shows all six, including disabled ones, and Add Network lists the five that are `chains_enabled: false`.
3. **Before any non-Base APPLY**, deploy the backend half of `27dfab4` as well (`server.py` GET field + generalised `env_sync`). Persistence of `bnb` is already in the live image; env export of non-Base chains is not. Keep `ARBICORE_RPC_URL` Base-only (that is what `27dfab4` does).
4. **Re-enter the five configurations and SAVE DRAFT** after the new UI is up. VALIDATE alone will not retain them. Leave APPLY for an explicit later decision. Do not activate BNB in this step.
5. No code defect was found in `27dfab4` that explains the missing controls. Do not patch the live bundle in place.

---

## H. Confirmation that no live configuration was changed

This pass used only reads:

- `git show` / `git log` / `git diff` (no commit, no checkout)
- `docker ps` / `docker inspect` / `docker images` / `docker exec` reads (`grep`, `awk`, `python` import of `SUPPORTED_CHAINS`)
- `docker cp` of `persistent.py`, `env_sync.py`, and the static JS bundle to `/tmp` for comparison
- `GET /api/arbicore/settings/network` and `GET /api/arbicore/settings/network/history`
- Caddy access-log field extraction (timestamp, status, method, path, response size)

No POST, no APPLY, no draft write, no Mongo update, no env edit, no image build, no restart. Applied revision is still `rev-7c93bb93e65b4f5a9b7340bf513437c0` at 2026-10-03T04:57:17Z. Current Base primary fingerprint remains `cd505118`.
