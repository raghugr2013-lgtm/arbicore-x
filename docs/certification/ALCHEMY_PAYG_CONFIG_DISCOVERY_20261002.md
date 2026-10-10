# Alchemy PAYG Configuration Discovery (READ-ONLY) — 2026-10-02

- Status: **READ-ONLY discovery** — no config change, no restart, no campaign reset, no secrets printed
- Container: `arbicore-x-backend-new` · image `arbicore-x-backend:ws-a-befb14e-20261002`
- StartedAt: `2026-10-02T15:08:52Z` · RestartCount=`0`
- Compose: `/home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose/docker-compose.prod.yml`
- Env file: `/home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env` (mode `0600`)
- Override: `artifacts/deploy_staging/workstream-a-befb14e/POST_PATCH_OVERRIDE_ws-a-befb14e_20261002T150827Z.yml` (image/flags only; **no RPC secrets**)

All Alchemy credentials redacted to `sha256(path_segment)[:8]` fingerprints only.

---

## WHERE and HOW (canonical path first)

### Canonical source of truth
**Mongo Network Config** (`NetworkConfigRepo` / collection `arbicore_config`, kind=`network`) field:

`rpc_urls.<chain>[]` — ordered list; **index 0 = PRIMARY**, rest = failover.

Live Base (redacted):

| Index | Role today | Host | fp8 |
|---:|---|---|---|
| 0 | PRIMARY (wrong for PAYG goal) | `mainnet.base.org` | n/a |
| 1 | FALLBACK (**stale**) | `base-mainnet.g.alchemy.com` | **`ce00e63d`** |

Revision: `rev-615fa528…` · `updated_at=2026-09-27T09:31:23Z` · actor `admin` · reason G5.66 (public Base promoted primary; old Alchemy retained as fallback).

### How to provide a new PAYG credential (operator later — DO NOT execute now)

1. **Update Network Config first** (UI Settings › Network `/v2/settings/network` → VALIDATE → APPLY, or authenticated `POST /api/arbicore/settings/network/apply`).
2. Set `rpc_urls.base` (and other chains as needed) to:
   - `[0]` = Alchemy PAYG full URL `https://<alchemy-host>/v2/<NEW_KEY>`
   - `[1]` = validated secondary/public (e.g. `https://mainnet.base.org` for Base)
3. APPLY hot-loads via `env_sync` into process `os.environ` **without restart**.
4. **Mirror the same URLs into** `deployment/upgrade/backend/.env` so the next container recreate does not reintroduce drift (Docker alone is **not** authoritative while Network Config is non-empty).
5. Verify fingerprints only (see §10 / Q9). Never paste the key into chat, cert docs, or shell history.

**Do not** change only Docker/`backend/.env` and expect it to stick: on every startup, `env_sync` overwrites Base RPC env from Network Config when `rpc_urls.base` is non-empty.

---

## 1. Where credentials are currently stored

| Store | Path / location | What it holds (redacted) | Authoritative? |
|---|---|---|---|
| **Network Config (Mongo)** | `arbicore_config` kind=`network` → `rpc_urls.base[]` | `[mainnet.base.org, alchemy fp ce00e63d]` | **YES for Base after env_sync** |
| **Docker env_file** | `/home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env` | Full Alchemy URLs fp **`5e5d5bb1`** on `ARBICORE_RPC_URL`, archive, eth/arb/op/poly/bnb; Base primary=`mainnet.base.org`; `ALCHEMY_API_KEY` empty | Bootstrap / non-Base; **overridden for Base by env_sync** |
| **Compose** | `deployment/upgrade/compose/docker-compose.prod.yml` | `env_file: ../backend/.env` only | Wiring only |
| **POST_PATCH override** | `…/POST_PATCH_OVERRIDE_ws-a-befb14e_*.yml` | Image tag + SHADOW flags; **no RPC keys** | Image/mode only |
| **`ALCHEMY_API_KEY`** | env | **EMPTY** | Not used for RPC URL path |
| **VPS secret store / Docker secrets** | — | Not observed for Alchemy RPC | N/A |
| **ProviderRegistry** | in-process after bootstrap/sync | Base: `rpc_base_0_mainnet_base_org`, `rpc_base_1_…alchemy…` (from managed `PROVIDER_RPC_URLS_BASE`) | Derived |

---

## 2. Authoritative config at runtime (evidence)

Precedence for Base RPC **after startup**:

```
NetworkConfig.rpc_urls.base  --(env_sync)-->  os.environ
  ├─ ARBICORE_RPC_URL          = list[0]   (primary only)
  ├─ ARBICORE_RPC_URL_BASE     = list[0]
  ├─ BASE_RPC_URL              = list[0]   (legacy alias)
  └─ PROVIDER_RPC_URLS_BASE    = full CSV  (managed; G5.79)
         └─ ProviderRegistry + QuoterRegistry failover candidates
```

Code paths:

- `NetworkConfigRepo.ensure_seed_from_env` — seeds Mongo **once** if empty; **never overwrites** existing (`persistent.py`).
- `sync_env_from_network_config` — if persistent primary exists, **it wins** over Docker env (`env_sync.py` lines 12–15, 108–126).
- Invoked at: startup (`server.py` ~8663–8667) and `POST …/settings/network/{apply,rollback}` (~5996, ~6024).
- **Default `chain="base"` only** — env_sync does **not** currently push eth/arb/op/poly/bnb Network Config lists (those lists are empty live anyway).
- Quoter candidates: `QuoterRegistry._rpc_url_candidates` reads `ARBICORE_RPC_URL_<CHAIN>`, legacy `<CHAIN>_RPC_URL`, `PROVIDER_RPC_URLS_<CHAIN>`, then Base-only global `ARBICORE_RPC_URL` (`quoter.py`).
- Provider bootstrap: `PROVIDER_RPC_URLS_<CHAIN>` CSV first (`bootstrap.py` `_rpc_urls`).

Live evidence:

- Log `2026-10-02 15:09:08,734` — `env_sync: exported 5 var(s) … (chain=base)`
- `phase-10.10 env sync exported: ['ARBICORE_EXECUTOR_ADDRESS_BASE', 'ARBICORE_RPC_URL', 'ARBICORE_RPC_URL_BASE', 'BASE_RPC_URL', 'PROVIDER_RPC_URLS_BASE']`
- `GET /api/arbicore/rpc/check` → `rpc_url_masked: "mainnet.base.org"` (primary = public, not Docker Alchemy)

---

## 3. Exact mechanism: stale `ce00e63d` overrode Docker `5e5d5bb1`

1. Docker/`backend/.env` wired Alchemy fp **`5e5d5bb1`** into `ARBICORE_RPC_URL` (+ other chains).
2. Mongo Network Config still had Base fallback Alchemy fp **`ce00e63d`** (capacity-exhausted key cleared from Docker in M6, but **left in Network Config** since 2026-09-27 G5.66).
3. At container start `15:08:52Z`, startup ran `env_sync` at **`15:09:08Z`**.
4. env_sync set:
   - `ARBICORE_RPC_URL` / `ARBICORE_RPC_URL_BASE` / `BASE_RPC_URL` ← `rpc_urls.base[0]` = `mainnet.base.org` (**wiping Docker’s `5e5d5bb1` from the Base global alias**)
   - `PROVIDER_RPC_URLS_BASE` ← full list = `mainnet.base.org` + Alchemy **`ce00e63d`**
5. Quoter failover order became: public Base → stale Alchemy **`ce00e63d`** (via managed `PROVIDER_RPC_URLS_BASE`), **not** Docker `5e5d5bb1`.
6. ProviderRegistry registered `rpc_base_1_…alchemy…` from that managed CSV (observed TRIPPED / host_cooldown).

**Root cause class:** Network Config + env_sync managed multi-RPC export resurrected a stale credential that Docker had already replaced.

---

## 4. Exact variable names (new PAYG)

### Canonical (preferred)
| Chain | Network Config field |
|---|---|
| Base | `rpc_urls.base` |
| Ethereum | `rpc_urls.ethereum` |
| Arbitrum | `rpc_urls.arbitrum` |
| Optimism | `rpc_urls.optimism` |
| Polygon | `rpc_urls.polygon` |
| BNB | `rpc_urls.bnb` |

### Env mirrors (written by env_sync for Base; set in `.env` for all chains)
| Chain | Primary env var | Legacy alias | Managed multi-RPC CSV |
|---|---|---|---|
| Base | `ARBICORE_RPC_URL_BASE` (+ Base-only `ARBICORE_RPC_URL`) | `BASE_RPC_URL` | `PROVIDER_RPC_URLS_BASE` |
| Ethereum | `ARBICORE_RPC_URL_ETHEREUM` | `ETHEREUM_RPC_URL` | `PROVIDER_RPC_URLS_ETHEREUM` |
| Arbitrum | `ARBICORE_RPC_URL_ARBITRUM` | `ARBITRUM_RPC_URL` | `PROVIDER_RPC_URLS_ARBITRUM` |
| Optimism | `ARBICORE_RPC_URL_OPTIMISM` | `OPTIMISM_RPC_URL` | `PROVIDER_RPC_URLS_OPTIMISM` |
| Polygon | `ARBICORE_RPC_URL_POLYGON` | `POLYGON_RPC_URL` | `PROVIDER_RPC_URLS_POLYGON` |
| BNB | `ARBICORE_RPC_URL_BNB` | `BNB_RPC_URL` | `PROVIDER_RPC_URLS_BNB` |

Optional archive (Base): `ARBICORE_ARCHIVE_RPC_URL` (currently Alchemy in `.env`; **not** driven by env_sync).

---

## 5. Full URL with key vs `ALCHEMY_API_KEY` + templates

**Use complete HTTPS URLs with the key in the path.**  
Live system embeds the key in `/v2/<key>`; `ALCHEMY_API_KEY` is **empty** and is **not** consulted by `resolve_rpc_url_from_env` / quoter RPC candidates (it only gates some dex-scanner stubs).

Templates (same key material typically shared across Alchemy app networks):

| Chain | URL template |
|---|---|
| Base | `https://base-mainnet.g.alchemy.com/v2/<KEY>` |
| Ethereum | `https://eth-mainnet.g.alchemy.com/v2/<KEY>` |
| Arbitrum | `https://arb-mainnet.g.alchemy.com/v2/<KEY>` |
| Optimism | `https://opt-mainnet.g.alchemy.com/v2/<KEY>` |
| Polygon | `https://polygon-mainnet.g.alchemy.com/v2/<KEY>` |
| BNB | `https://bnb-mainnet.g.alchemy.com/v2/<KEY>` |

For PAYG goal (Alchemy primary, public fallback), Base example shape:

`rpc_urls.base = ["https://base-mainnet.g.alchemy.com/v2/<KEY>", "https://mainnet.base.org"]`

---

## 6. Will env_sync overwrite if only Docker env is modified?

**Yes for Base**, whenever Network Config `rpc_urls.base` is non-empty:

- On **every process start**, env_sync overwrites `ARBICORE_RPC_URL`, `ARBICORE_RPC_URL_BASE`, `BASE_RPC_URL`, and managed `PROVIDER_RPC_URLS_BASE`.
- On **APPLY/ROLLBACK**, same hot overwrite without restart.
- Changing only `backend/.env` / compose env **does not** update a live process until recreate **and** will be overwritten again if Mongo still has the old list.
- Explicit operator `PROVIDER_RPC_URLS_BASE` (without managed marker) would be preserved by G5.79 provenance rules — but that is a foot-gun vs Network Config; **do not use** as the PAYG path.

Non-Base chains: env_sync currently only runs for `chain=base`; Docker `ARBICORE_RPC_URL_{ETHEREUM,…}` remain the live source unless separately applied/extended later.

---

## 7. Safest way to provide the secret (no chat / logs / git / history)

1. Create the PAYG key in Alchemy dashboard; keep it in a password manager.
2. On the VPS, as the deploy user, edit files with an editor (**not** `echo`/`printf` into shell history):
   - `chmod 600` on `deployment/upgrade/backend/.env`
   - Paste full URLs only into Network Config UI fields (authenticated browser session) **or** into `.env` via editor.
3. Prefer **UI APPLY** over `curl … -d '…/v2/SECRET…'` (argv/history exposure).
4. Do **not** commit `.env`, paste keys into chat, cert markdown, or report JSON.
5. Know that Mongo `arbicore_config` + `arbicore_config_audit` **store full RPC URLs** (secret-bearing). Protect DB backups accordingly.
6. env_sync logs **variable names only** (good); still avoid putting keys on command lines.

---

## 8. Exact operator steps (DO NOT EXECUTE during discovery)

### A. UI (preferred)

1. Open operator UI → **Settings › Network** (`/v2/settings/network`).
2. For **base** (and each enabled chain):
   - RPC URLs (comma-separated, primary first):  
     `https://base-mainnet.g.alchemy.com/v2/<NEW_PAYG_KEY>, https://mainnet.base.org`
   - Repeat with the matching Alchemy host for eth/arb/op/poly/bnb if those chains should use PAYG primary.
3. **VALIDATE** → expect OK.
4. **APPLY** → reason e.g. `PAYG Alchemy primary; public fallback; retire ce00e63d`.
5. Confirm response includes `env_synced` containing `ARBICORE_RPC_URL`, `ARBICORE_RPC_URL_BASE`, `PROVIDER_RPC_URLS_BASE` (and legacy `BASE_RPC_URL`).
6. Mirror the same URLs into `deployment/upgrade/backend/.env` with an editor (for restart durability). **Do not restart** unless campaign interruption is authorized.

### B. API (authenticated operator session only)

```bash
# DO NOT put the real key on the command line in shell history.
# Prefer UI. If scripting, read URL from a 0600 file:
#   PAYG_BASE_URL=$(sudo cat /path/to/payg_base_url.txt)  # file mode 0600, shred after

curl -sS -X POST 'http://127.0.0.1:8001/api/arbicore/settings/network/apply' \
  -H "Authorization: Bearer <OPERATOR_TOKEN>" \
  -H 'Content-Type: application/json' \
  --data-binary @/path/to/network_apply_payload.json
```

Payload shape (secrets only inside the chmod-600 JSON file):

```json
{
  "reason": "PAYG Alchemy primary; public fallback; retire stale fp ce00e63d",
  "patch": {
    "rpc_urls": {
      "base": [
        "https://base-mainnet.g.alchemy.com/v2/<NEW_KEY>",
        "https://mainnet.base.org"
      ]
    }
  }
}
```

### C. Retire stale credential

Ensure **no** remaining `ce00e63d` in Network Config `rpc_urls.*.[*]` or in `.env`. After APPLY, managed `PROVIDER_RPC_URLS_BASE` regenerates from the new list.

### D. Do not change retry/cooldown knobs

Leave unset (running defaults from image `befb14e`):  
`ARBICORE_RPC_FAILOVER_CANDIDATE_RETRIES=1`, `ARBICORE_RPC_HTTP_429_COOLDOWN_S=60`, `ARBICORE_RPC_MAX_RETRIES=4`.

---

## 9. Verify via fingerprint only

```bash
# Network Config fps (no key print)
python3 - <<'PY'
import json, hashlib, re, urllib.request
with urllib.request.urlopen("http://127.0.0.1:8001/api/arbicore/settings/network") as r:
    cfg = json.load(r)["config"]
for chain, urls in (cfg.get("rpc_urls") or {}).items():
    for i, u in enumerate(urls or []):
        host = u.split("//",1)[-1].split("/",1)[0]
        m = re.search(r"/v2/([^/?#]+)", u)
        fp = hashlib.sha256(m.group(1).encode()).hexdigest()[:8] if m else "n/a"
        print(f"{chain}[{i}] host={host} fp8={fp}")
PY

# Local key material → fp only (operator compares to dashboard / expected NEW fp)
# python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.stdin.read().strip().encode()).hexdigest()[:8])' </path/to/key_only.txt

# rpc/check should show Alchemy host once PAYG is primary:
# curl -sS http://127.0.0.1:8001/api/arbicore/rpc/check
# expect rpc_url_masked ~ base-mainnet.g.alchemy.com
```

Expect after correct APPLY: Base `[0]` Alchemy with **new** fp ≠ `ce00e63d` (and ≠ old `5e5d5bb1` if key rotated); `[1]` public host fp `n/a`.

---

## 10. Campaign impact (12h POST-FIX SHADOW)

| Method | Affects live campaign? | Restart required? |
|---|---|---|
| Network Config APPLY | **Yes — immediate** (env_sync hot-load + provider resync) | No |
| Edit `backend/.env` only | **No** until container recreate; then still overwritten by Mongo if unchanged | Recreate needed to load file |
| Container recreate / redeploy | **Yes — interrupts campaign** | Yes |

**Honest recommendation:** Do **not** apply PAYG / Network Config changes while the 12h POST-FIX SHADOW campaign is running unless explicitly authorized. Hot-reload exists and **will** change live RPC primary/failover mid-campaign. Default: wait for campaign end/authorization, then APPLY Network Config + mirror `.env`.

Bounded retries + cooldown from image `befb14e` remain; this discovery does not change them.

---

## STOP

No secrets printed. No config/source changes. No restart/redeploy. No campaign reset.
