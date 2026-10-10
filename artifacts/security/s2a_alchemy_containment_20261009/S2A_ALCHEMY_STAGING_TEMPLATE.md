# S2-A — Staging format reconciliation (secret-free)

**Status:** Prepare-only · no cutover · no mutations  
**Question:** Do six ArbiCore-x-2 chain endpoints map to `PRIMARY` + `FALLBACK_1..5`, or must the file be redesigned?

---

## Verdict

**Redesign the staging file.** Your six endpoints are **chain-specific primaries**, not five fallback credentials plus one primary.

| What you have | What the old contract expected |
|---|---|
| 6 URLs → Ethereum, Arbitrum, Base, Optimism, Polygon, BNB | 1 shared key (`PRIMARY`) + 5 shared fallback keys, each applied to **all** chain hosts |

---

## How production is laid out today (fps / hosts only)

Mongo `rpc_urls` for **every** chain has **6 slots** on the **same Alchemy host family**:

| Index | Role | Key fp8 (same on all 6 chains) | Host pattern |
|---:|---|---|---|
| 0 | primary | `24dab5d1` | `<chain>-mainnet.g.alchemy.com` (Base: `base-mainnet…`) |
| 1 | fallback_1 | `e315c86f` | same host as that chain |
| 2 | fallback_2 | `dc432a6b` | same |
| 3 | fallback_3 | `6e67e161` | same |
| 4 | fallback_4 | `cd505118` | same |
| 5 | fallback_5 | `124bc59c` | same |

ENV bootstrap (compose / `.env`), separate from Mongo primaries:

| Var | Host | fp8 |
|---|---|---|
| `ARBICORE_RPC_URL` / archive / eth/arb/op/poly/bnb | Alchemy per chain | `5e5d5bb1` |
| `ARBICORE_RPC_URL_BASE` | `mainnet.base.org` | (no key) |

So historically: **one credential identity per list index**, reused across chains; hosts differ by chain. Your Word doc is the opposite shape: **one endpoint per chain** (ArbiCore-x-2 networks).

g5.79 (`a7961b2b`) remains **out of scope**.

---

## Required staging template (use this)

Path: `/tmp/s2a_alchemy_replacements.env` · mode `0600`

```bash
# === Chain primaries (required) — full Alchemy URLs ===
PRIMARY_ETHEREUM=https://eth-mainnet.g.alchemy.com/v2/<PASTE>
PRIMARY_ARBITRUM=https://arb-mainnet.g.alchemy.com/v2/<PASTE>
PRIMARY_BASE=https://base-mainnet.g.alchemy.com/v2/<PASTE>
PRIMARY_OPTIMISM=https://opt-mainnet.g.alchemy.com/v2/<PASTE>
PRIMARY_POLYGON=https://polygon-mainnet.g.alchemy.com/v2/<PASTE>
PRIMARY_BNB=https://bnb-mainnet.g.alchemy.com/v2/<PASTE>

# === ENV bootstrap / archive (optional; default = PRIMARY_BASE) ===
BOOTSTRAP_BASE=https://base-mainnet.g.alchemy.com/v2/<PASTE>
ARCHIVE_BASE=https://base-mainnet.g.alchemy.com/v2/<PASTE>

# === Fallback registry policy for THIS cutover ===
# retain_existing = replace Mongo [0] only; keep [1..5] old fps until a later stage
FALLBACK_POLICY=retain_existing
```

### Host checklist (must match)

| Key | Expected host |
|---|---|
| `PRIMARY_ETHEREUM` | `eth-mainnet.g.alchemy.com` |
| `PRIMARY_ARBITRUM` | `arb-mainnet.g.alchemy.com` |
| `PRIMARY_BASE` | `base-mainnet.g.alchemy.com` |
| `PRIMARY_OPTIMISM` | `opt-mainnet.g.alchemy.com` |
| `PRIMARY_POLYGON` | `polygon-mainnet.g.alchemy.com` |
| `PRIMARY_BNB` | `bnb-mainnet.g.alchemy.com` |

If ArbiCore-x-2 is a **single Alchemy app key** attached to six networks, all six URLs will fingerprint to the **same** fp8 — that is normal and acceptable.

Do **not** use the obsolete `PRIMARY=` / `FALLBACK_1=` … `FALLBACK_5=` role names for these six chain URLs.

---

## What happens to FALLBACK_1–FALLBACK_5

Under default `FALLBACK_POLICY=retain_existing` (recommended with only six chain URLs):

| Slot | At cutover |
|---|---|
| Mongo `[0]` | → new ArbiCore-x-2 chain primary |
| Mongo `[1..5]` | **unchanged** (fps `e315c86f` … `124bc59c`) |
| Revoke after primary cutover | **Only** old primary `24dab5d1` and ENV `5e5d5bb1` become revoke-candidates after acceptance — **not** the fallback fps, and **not** g5.79 |

To replace fallbacks later, stage a **second** file (or extend this one) with either:

- shared `FALLBACK_1`…`FALLBACK_5` keys (old model: same key × all chain hosts), or  
- per-chain `FALLBACK1_<CHAIN>=` URLs  

That is a **separate** authorisation after primary cutover evidence.

---

## Cutover mapping (secret-free) — when later authorised

| Consumer | From | To |
|---|---|---|
| Mongo `rpc_urls.ethereum[0]` | fp `24dab5d1` @ eth host | `PRIMARY_ETHEREUM` |
| Mongo `rpc_urls.arbitrum[0]` | fp `24dab5d1` @ arb host | `PRIMARY_ARBITRUM` |
| Mongo `rpc_urls.base[0]` | fp `24dab5d1` @ base host | `PRIMARY_BASE` |
| Mongo `rpc_urls.optimism[0]` | fp `24dab5d1` @ opt host | `PRIMARY_OPTIMISM` |
| Mongo `rpc_urls.polygon[0]` | fp `24dab5d1` @ polygon host | `PRIMARY_POLYGON` |
| Mongo `rpc_urls.bnb[0]` | fp `24dab5d1` @ bnb host | `PRIMARY_BNB` |
| Mongo `rpc_urls.<chain>[1..5]` | old fallback fps | **retain** |
| `.env` `ARBICORE_RPC_URL` / `ARBICORE_ARCHIVE_RPC_URL` | fp `5e5d5bb1` | `BOOTSTRAP_BASE` / `ARCHIVE_BASE` (or PRIMARY_BASE) |
| `.env` `ARBICORE_RPC_URL_{ETHEREUM,…}` | fp `5e5d5bb1` | matching `PRIMARY_<CHAIN>` |
| `.env` `ARBICORE_RPC_URL_BASE` | `mainnet.base.org` | leave public **or** set to PRIMARY_BASE only if you explicitly want Base ENV=Alchemy |
| g5.79 | fp `a7961b2b` | **no change** |

---

## Prepare-only stop line

No production config, containers, or keys changed by this reconciliation.  
Stage using the **chain-primary** template above, then confirm with **staged** only.
