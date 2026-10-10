# G1.6 — Offline false-arbitrage detection guard (methodology)

**Workspace:** `artifacts/g15/g16_false_arbitrage_guard_20261009/`  
**Inputs (read-only):** frozen `MEV_SCOUT_BASE_BSC_WINNERS_G1_5.jsonl` (Oct 8 export)  
**Non-goals:** collectors, Base tracker, live ledger, production runtime, strategy code

## Prior art inspected

- Frozen G1.5 winners schema (`classification`, `pipeline_class`, `pools`, `legs[]`, NET fields).
- Offline G1.5 route-coverage workspace `artifacts/g15/audit_offline_base_replay_20261009/` (coverage only; no mirror guard).
- G1.5 export `MANIFEST.md` references `code/gcpipe/families_lib.py` / `analyze.py`, but those reproducibility sources were **not present** in the core transfer tarball on this host (only winners/ledger/out). G1.6 therefore implements the accounting guard as a new offline module rather than patching missing collector code.

## Flags (additive investigation signals)

| Flag | Meaning |
|---|---|
| `POTENTIAL_CROSS_TX_MIRROR` | Another Base winner tx within ±3 blocks swaps the same pool in the reverse direction at comparable size |
| `REPEATED_POOL_ROUTE` | The same pool appears more than once in `pools` / `legs` of a single tx |
| `BOTH_FLAGS` | Both of the above |
| `NO_FLAG` | Neither |

**A flag is not proof of fraud, wash flow, or zero economic profit.** Original `classification` / `pipeline_class` remain authoritative and recoverable on every result row.

## Cross-tx mirror rule

Link legs `(A,B)` when all hold:

1. Same `pool` address (lowercased).
2. Reverse direction: `A.token_in == B.token_out` and `A.token_out == B.token_in`.
3. Comparable sizes: both `|A.amount_in − B.amount_out| / max` and `|A.amount_out − B.amount_in| / max` ≤ **5%**.
4. `|block_A − block_B| ≤ 3` (inclusive).

Recorded per link: blocks, tx indices, pool, directions, raw amounts, tx hashes, same-searcher / same-operator booleans, rationale string.

Transactions are **not** merged into a single economic row in the source. Results expose:

- `original_net_usd` — per-tx NET from the frozen export  
- `inferred_bundle_net_usd` — sum of member original NETs in the linked component (negatives retained; partial if any member NET missing)

## Dedup / double-counting policy

- Mirror storage key: undirected `(tx_lo, tx_hi, pool)` — one link row per pair+pool.
- Flag histogram: each `tx_hash` counted **once**.
- Overlapping candidates (A↔B and A↔C): multiple unique pairs allowed; bundle NET uses union-find over tx hashes so each tx’s NET is summed once per component.

## Reproducibility for the next 48-hour report

```bash
cd artifacts/g15/g16_false_arbitrage_guard_20261009
python3 -m pytest test_false_arbitrage_guard.py -q
python3 run_guard_on_frozen.py
```

Outputs under `out/` clearly separate:

- **Verified:** frozen row fields + `original_*` columns + source sha256  
- **Inferred:** `guard_flag`, `mirror_links`, `inferred_bundle_net_usd`

When a future 48h export arrives, point `FROZEN` at the new winners file **without** modifying collectors or the Oct 8 frozen export.
