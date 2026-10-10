# UniV4 Base Coverage Inventory (Research-Only)

**Recommendation:** **INSUFFICIENT EVIDENCE — DO NOT IMPLEMENT.**

**Decisive reason:** The frozen G1.5 export yields **327** full bytes32 V4 `PoolId`s covering all **2,012** cohort rows, but **zero hook contract addresses**. V4 executable identity is incomplete without hooks. Separately, **verified-owner** A/B kept-NET ≥$1 and ≥$25 are both **0**. A/B kept-NET bands are an external research signal only — not ArbiCore-capturable profit.

No RPC, SHADOW, PAPER, hot-path, code, or config work was performed.

---

## 1. Cohort

| Item | Value |
|---|---|
| Definition | Base winners whose `venue` atoms (split on `+`) include `UniswapV4` or start with `UniV4` — same as `BASE_G15_COVERAGE_PRIORITISATION.md` |
| N | **2,012** |
| Reconciliation | Matches frozen JSONL and `BASE_G15_ROUTE_COVERAGE.csv`; `validate_univ4_inventory.py` → **PASS** |
| Source IDs preserved | `tx_hash`, `jsonl_line_no`, `base_row_index` in `univ4_cohort_rows.csv` |

### Class distribution (G1.5 REPORT §4)
| Class | Meaning | Count |
|---|---|---:|
| A | CONFIRMED_SEARCHER_KEPT (trace-verified) | 556 |
| B | RECONSTRUCTABLE_SEARCHER_KEPT | 1,229 |
| C | GROSS_ONLY | 27 |
| D | UNKNOWN (`cyclic_v4_unresolved` / `cyclic_unknown_venue` among others) | 200 |

### Owner attribution (not upgraded)
| Basis | Count |
|---|---:|
| VERIFIED | 73 |
| INFERRED | 563 |
| MISSING | 1,376 |

Evidence source field: `owner_payout_basis` + `verified_vs_inferred.owner_payout_usd` from frozen JSONL. INFERRED/MISSING are **not** treated as verified.

---

## 2. Methodology (reproducible)

```bash
cd ~/projects/arbicore-x-cert/artifacts/g15/audit_offline_base_replay_20261009/univ4_inventory
python3 build_univ4_inventory.py
python3 validate_univ4_inventory.py   # must print PASS
```

### Observed vs inferred
| Field | Status in this export |
|---|---|
| `pool_id` (`v4:` + 64 hex = bytes32) from `pools[]` / `legs[].pool` | **OBSERVED** |
| Truncated `route` display prefixes (`v4:0x96d4b53…`) | **Ignored** (not full identity) |
| `UniV4[TOKEN/TOKEN fFEE]` label body | **OBSERVED** text; fee/symbols **PARSED_FROM_LABEL** |
| Leg `token_in` / `token_out` addresses | **OBSERVED** when `0x`+40 hex; `ETH`/`ETH*` sentinel is not an ERC-20 address |
| Hook **contract address** | **ABSENT** (never fabricated) |
| Venue atom `UniswapV4(hook)` / label word `hook` / `family_tags` `hook-pool` | **OBSERVED tag only** → `TAGGED_HOOK_NO_ADDRESS` |
| Tick spacing | **ABSENT** |

### Dedup keys
- **Pools:** lowercase full bytes32 `PoolId`
- **Tokens:** lowercase ERC-20 address from `tokens[].address`
- **Hooks with address:** none to dedupe

Each inventory row retains `source_row_refs` (`tx_hash|L{jsonl_line}|B{base_index}`) and `n_source_rows`.

---

## 3. Inventory results

### 3.1 Unique identities
| Kind | Unique count | Notes |
|---|---:|---|
| V4 pools (full PoolId) | **327** | Present on **100%** of 2,012 rows |
| Hooks with contract address | **0** | 14 rows tagged hook without address |
| Tokens with observed address | **171** | 12 also in ArbiCore `TOKENS`; 159 outside |

### 3.2 A/B kept-NET signal (not capture)
| Metric | Count |
|---|---:|
| A/B rows | 1,785 |
| A/B kept-NET ≥ $1 | **179** |
| A/B kept-NET ≥ $25 | **9** |
| VERIFIED-owner A/B kept-NET ≥ $1 | **0** |
| VERIFIED-owner A/B kept-NET ≥ $25 | **0** |

A/B kept bands: below $0: 11 · $0–<$1: 1,595 · $1–<$25: 170 · ≥$25: 9 · null handled via class C/D separately.

Partial route matches from the prior coverage CSV are **not** treated as executable (`match_tier` is recorded only as context; almost all UniV4 rows are `UNMATCHED` / `PARTIAL_*`).

### 3.3 Identity completeness (rows)
| Criterion | Rows | Share of 2,012 |
|---|---:|---:|
| ≥1 full PoolId | 2,012 | 100% |
| PoolId + (parseable label or leg token addresses) | 1,956 | **97.22%** |
| Hook address present | 0 | 0% |
| Tick spacing present | 0 | 0% |

**Complete executable V4 identity** (PoolId + hook address + tokens/params) = **0 / 2,012**.

### 3.4 Segmentation highlights
- Adjacent venues only mapped (UniV3/Aerodrome*) or none: majority compositional pattern (see summary JSON `segments`).
- Rows with ≥1 non-ArbiCore-universe token: high (long-tail XDP/WHUF/DRV/…).
- Pools with PoolId + label/leg tokens: **292**; unresolved beyond bare PoolId: **35**.
- Pools with that identity **and** A/B kept ≥$1: **72**.
- Of those 72, pools whose *every* contributing row stays inside ArbiCore’s 12-token universe: **0** (multi-hop co-tokens pull majors pools into non-universe rows).

Top ≥$25 pools by source rows are long-tail labels (WHUF, DGUY, DRV, DIEM/kDIEM) — not a majors-only allowlist.

### 3.5 Unresolved identifiers
| Missing | Scope |
|---|---|
| Hook contract addresses | **All 327 pools** |
| Tick spacing | All pools |
| Fee as on-chain param | Only label-parsed when `UniV4[… fN]` present; not independently verified |
| `?` labels | Present on some pools; 35 pools lack label/leg token enrichment |
| Class D unresolved V4 economics | 200 class-D rows in cohort |

---

## 4. Can a finite allowlist be built from frozen evidence alone?

**Finite PoolId list:** yes — 327 observed IDs.  
**Finite complete V4 candidate allowlist (PoolId + hook + tokens/params, auditable for implementation):** **no**.

| Allowlist bar | Result |
|---|---|
| Explicit PoolId | 327 |
| + label or leg tokens | 292 |
| + A/B kept-NET ≥$1 signal | 72 |
| + no non-universe token on contributing rows | **0** |
| + hook address | **0** |
| + VERIFIED-owner ≥$1 | **0** |

The prioritisation note that **9** A/B winners have kept-NET ≥$25 after excluding XDP remains a **research signal only**. It does not clear verified attribution or complete identity bars.

---

## 5. Fallback (not started)

If V4 cannot be advanced from frozen evidence, prioritisation rank **#7 — curated-pair gap** (Aerodrome Slipstream pairs among tokens already in ArbiCore `TOKENS`) is more tractable: it does not require V4 hooks and uses already-mapped dex families.

**That investigation was not begun in this task.**

---

## 6. Deliverables

| File | Role |
|---|---|
| `UNIV4_BASE_INVENTORY.md` | This report |
| `univ4_pool_hook_inventory.csv` | One row per PoolId; hook address column empty + `ABSENT` |
| `univ4_token_inventory.csv` | One row per observed token address |
| `univ4_inventory_summary.json` | Machine-readable counts + decision |
| `univ4_cohort_rows.csv` | 2,012 source-row sidecar for reconciliation |
| `build_univ4_inventory.py` | Offline builder |
| `validate_univ4_inventory.py` | Count reconciliation (**PASS**) |

---

## 7. Required closing figures

1. **Uniquely identified:** pools **327** · hooks with address **0** · tokens **171**  
2. **A/B kept-NET ≥$1 / ≥$25:** **179** / **9**  
3. **Verified-owner A/B ≥$1 / ≥$25:** **0** / **0**  
4. **Share with PoolId+label/leg completeness:** **97.22%** (1,956/2,012); share with **complete executable identity including hook address:** **0%**  
5. **Recommendation:** **INSUFFICIENT EVIDENCE — DO NOT IMPLEMENT** — because hook addresses are absent for every pool and verified-owner kept-NET signal is zero; do not implement, RPC, SHADOW, or hot-path on this basis.
