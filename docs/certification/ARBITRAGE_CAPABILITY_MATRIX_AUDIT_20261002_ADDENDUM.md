# Capability Matrix Addendum — Taxonomy Map (2026-10-02)

- **Status:** ADDENDUM ONLY — does **not** supersede `ARBITRAGE_CAPABILITY_MATRIX_AUDIT_20261002.md`
- **Parent:** `docs/certification/ARBITRAGE_CAPABILITY_MATRIX_AUDIT_20261002.md` (**READY**; tip `9b196cde…`)
- **Companion:** `docs/certification/24H_PARALLEL_READINESS_AUDIT_20261002.md`
- **Changelog:** 2026-10-02 — map parallel-workstream taxonomy ↔ existing A–F classes; **no cell reclassification** (no new SHADOW/economic proof since parent audit)

---

## Why addendum (not full rewrite)

Parent audit already proved six-chain × route × flash surfaces from source + M5/M6/paper evidence. Parallel 24h readiness asked for labels:

`IMPLEMENTED | WIRED | TESTED | SHADOW-PROVEN | ECONOMICALLY-PROVEN | DETECTION-ONLY | NOT-IMPLEMENTED | INFRA-BLOCKED`

Those are **finer-grained axes**, not a reason to rebuild the matrix. No new live campaign produced A>0, Morpho/UniV3-flash settle, STABLECOIN/LST engines, or CROSS_CHAIN executable since the parent audit.

---

## Taxonomy ↔ parent class map

| Parallel label | Meaning | Closest parent class |
|---|---|---|
| **IMPLEMENTED** | Code/adapters exist | Y in IMP column (A/B/C) |
| **WIRED** | Feeds canonical verifier / EmissionBus or V1 settle path | INT=Y (A/B); Partial = C |
| **TESTED** | Unit/integration/harness tests | Parent “tests” evidence rows |
| **SHADOW-PROVEN** | Live SHADOW / M6 (or equivalent) exercised that combo | SHADOW=Y with real chain evidence → typically **B** (or **C** if partial) |
| **ECONOMICALLY-PROVEN** | Cleared Gate7 with real positive net (**A_real_profitable > 0**) | **None today** — M6 A=0; parent never claimed A |
| **DETECTION-ONLY** | Classify/emit/hint; no settle claim | Parent **D** |
| **NOT-IMPLEMENTED** | No real path | Parent **E** |
| **INFRA-BLOCKED** | External RPC/tier/config blocks | Parent **F** (or N/A protocol) |

Parent **A** would require IMP+INT+QUOTE+ECON+EXEC+SHADOW+sufficient validation. Parallel workstream would map parent **A** ≈ IMPLEMENTED+WIRED+TESTED+SHADOW-PROVEN (+ ECONOMICALLY-PROVEN only if Gate7 A>0). **No parent A cells exist** for live profitability.

---

## Binding heatmaps (unchanged from parent)

### Route family × chain

| Family | eth | arb | base | op | poly | bnb | Parallel gloss |
|---|---|---|---|---|---|---|---|
| GENERIC_DEX | B | B | C | B | C | C | IMPLEMENTED+WIRED+TESTED+SHADOW-PROVEN (econ); **not** ECONOMICALLY-PROVEN |
| TRIANGULAR | C | C | C | C | C | C | IMPLEMENTED+WIRED+TESTED; SHADOW partial (0 candidates) |
| STABLECOIN | D | D | D | D | D | D | **DETECTION-ONLY** |
| MULTI_HOP | C | C | C | C | C | C | Partial IMPLEMENTED+WIRED (hop budget); not SHADOW-family-proven |
| LST_LRT | D | D | D | D | D | D | **DETECTION-ONLY** |
| CROSS_CHAIN | D* | D* | D* | D* | D* | D* | Detection **DETECTION-ONLY**; executable **NOT-IMPLEMENTED** |

### Flash provider × chain

| Provider | eth | arb | base | op | poly | bnb | Parallel gloss |
|---|---|---|---|---|---|---|---|
| Aave V3 | B | B | B | B | B | C | SHADOW-PROVEN fee/econ with GENERIC_DEX (bnb adapter gap → incomplete) |
| Balancer V2 | B | C | C | C | C | N/A | P0 eth SHADOW-PROVEN; P1b long-window **INFRA-BLOCKED** (Alchemy Free getLogs) |
| UniV3 flash | C | C | C | C | C | N/A | IMPLEMENTED+partial WIRED; **not** V1 EXEC / not SHADOW-PROVEN as flash head |
| Morpho Blue | C | N/A | C | N/A | N/A | N/A | IMPLEMENTED+weak WIRED; **not** V1 EXEC |

### Provider infra callouts (from M6 post-alchemy)

| Item | Label |
|---|---|
| Alchemy key fp `5e5d5bb1` (429 cleared) | Fix **complete** → enables SHADOW-PROVEN RPC/quote path |
| Alchemy Free `eth_getLogs` ≤10 blocks | **INFRA-BLOCKED** for long P1b |
| Balancer subgraph URL unset | Incomplete ops config (not code absence) |
| Six-chain H06 seam | WIRED + SHADOW-PROVEN (infra), not trading-certified |

---

## Delta vs parent (explicit)

| Change type | Content |
|---|---|
| Reclassified cells | **None** |
| New ECONOMICALLY-PROVEN cells | **None** (A=0 held) |
| New SHADOW-PROVEN families | **None** beyond parent GENERIC_DEX×Aave |
| Docs-only | This taxonomy map + reference from 24h parallel readiness audit |

---

## STOP

No source changes. No matrix rebuild. No SHADOW campaign alteration. Parent FINAL STATUS **READY** for Gate 9–10 SHADOW continuity remains in force.
