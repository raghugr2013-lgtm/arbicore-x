# ArbiCore X — MID Architecture (v2.0.1, Sprint 1A)

**Status:** shipped in `v2.0.1` (2026-08-02)
**Scope:** platform-wide persistent intelligence foundation
**Location:** `app/backend/arbicore/data/mid/`

---

## 1. What the MID is

The **Market Intelligence Database (MID)** is a single persistence façade covering **11 domains** under one Mongo namespace (`mid_*`). Every producer in the platform writes through the façade; no direct-to-Mongo writes bypass it (design invariant §6.5).

The MID is **strategy-agnostic**. v2.0.1 populates only flash-loan-family values, but the schema natively supports future strategy families (CEX-DEX, funding-rate, treasury, liquidation, institutional credit, cross-chain) without any migration.

---

## 2. Module layout

```
arbicore/data/mid/
├── __init__.py       # Public re-exports
├── enums.py          # Open-enum registry (strategy_type, opportunity_type,
│                     #   capital_source, chain, protocol, execution_mode,
│                     #   market_regime). Warning-not-fail on unknown values.
├── schemas.py        # Dataclasses per domain + MidMetadata + ReplayContext
├── writers.py        # MidWriter façade (11 write_* methods)
├── readers.py        # MidReader (query + status)
└── indexes.py        # ensure_indexes(db) — TTL + metadata + domain indexes
```

## 3. Strategy-agnostic metadata block

Every MID row carries a `meta` block:

```python
MidMetadata(
    strategy_type    = "flash_loan_arbitrage" | ... ,   # open enum
    opportunity_type = "dex_arbitrage" | "multi_hop" | "triangular" | "stablecoin_depeg" | ...,
    capital_source   = "flash_loan_aave_v3" | "flash_loan_balancer_v2" | ... | None,
    chain            = "base" | "arbitrum" | ... | "off_chain_cex" | "unknown",
    protocol         = "uniswap_v3" | "aave_v3" | "binance_spot" | ... | None,
    execution_mode   = "shadow" | "paper" | "limited_live" | "full_live",  # closed enum
    market_regime    = "UNKNOWN"  # regime engine (dormant until Sprint 1B) back-annotates
    tags             = [str]
)
```

## 4. Replay-readiness block

Every MID row carries a `replay_context` block sufficient to reconstruct the market moment:

```python
ReplayContext(
    block_number         = Optional[int]
    block_timestamp      = Optional[str]  # ISO-8601 UTC, chain-clock
    quote_snapshot_id    = Optional[str]
    liquidity_snapshot_id = Optional[str]
    gas_snapshot_id      = Optional[str]
    route_snapshot_id    = Optional[str]
    decision_snapshot_id = Optional[str]
    market_snapshot_id   = Optional[str]
)
```

## 5. Stable canonical identifiers

| ID | Semantics | Assigned |
|---|---|---|
| `mid_id` | Every row's UUID4 (unique index) | On write |
| `event_id` | `{opp_id}:{event_ordinal:04d}` for opportunity events | On write |
| `route_id` | `{chain}:{family}:{in_token}->{out_token}:{sha1(dex_path)[:12]}` | Computed deterministically; stable across weeks |
| `provider_id` | `{provider_family}:{chain}` (e.g. `aave_v3:base`, `binance_spot:off_chain_cex`) | Registered in `mid.enums` |
| `market_snapshot_id` | `ms:{chain}:{dex}:{pair}:{ts_bucket}` — shared by sibling rows describing the same moment | Assigned by first writer of the moment |

## 6. Domains & collections

| Domain | Collection | Retention | Notes |
|---|---|---|---|
| market_state | `mid_market_state` | 90 d | mid / depth / spread / imbalance |
| quotes | `mid_quotes` | 30 d | Every route quote (successful + rejected) |
| liquidity | `mid_liquidity` | 90 d | Pool depth + tick liquidity |
| gas | `mid_gas` | 180 d | gas_price / priority_fee / base_fee per chain |
| providers | `mid_providers` | 365 d | Per-capital-source availability / cost / revert-count |
| routes | `mid_routes` | **permanent** | UPSERT one doc per `route_id` |
| opportunities | `mid_opportunities` | **permanent** | Every state transition per opp |
| confidence | `mid_confidence` | 90 d | Every score + inputs |
| decisions | `mid_decisions` | **permanent** | Full audit surface |
| outcomes | `mid_outcomes` | **permanent** | Training data |
| replay | `mid_replay` | 30 d | Counter-factuals (recomputable) |

## 7. Public API (Python)

```python
from arbicore.data.mid import MidWriter, MidReader, make_meta, ensure_indexes

writer = MidWriter(db)

# every write returns the mid_id of the persisted row
mid_id = await writer.write_market_state(
    chain="base", dex="uniswap_v3", pair="WETH/USDC",
    mid_price=2500.0,
    meta=make_meta(chain="base", protocol="uniswap_v3"),
    replay_context=ReplayContext(block_number=12345, block_timestamp="…"),
)

mid_id = await writer.write_provider_snapshot(
    provider_id="aave_v3:base",
    meta=make_meta(chain="base", capital_source="flash_loan_aave_v3"),
    observed_cost_bps=5.0,
)

# reader with metadata filters
reader = MidReader(db)
rows = await reader.query(
    "outcomes",
    strategy_type="flash_loan_arbitrage",
    chain="base",
    execution_mode="shadow",
    ts_gte="2026-08-02T00:00:00Z",
    limit=50,
)
```

## 8. REST endpoints (v2.0.1)

- `GET /api/arbicore/mid/status` — per-domain counts + last-write timestamps + producer health
- `GET /api/arbicore/mid/query/{domain}?strategy_type=…&chain=…&execution_mode=…&ts_gte=…&limit=…` — 11 domains, same metadata filter set
- `GET /api/arbicore/mid/enums` — enum registry snapshot + closed-enum flags

## 9. Adding a new strategy family (future)

Zero schema migration. On process startup, the new strategy's writer:

```python
from arbicore.data.mid.enums import get_registry, STRATEGY_TYPE, CAPITAL_SOURCE

reg = get_registry()
reg.register(STRATEGY_TYPE, "cex_dex_arbitrage")
reg.register(CAPITAL_SOURCE, "cex_venue_binance")

# … then every write:
await writer.write_opportunity_event(
    opp_id=…, event_type="discovered",
    meta=make_meta(
        strategy_type="cex_dex_arbitrage",
        opportunity_type="cex_dex",
        capital_source="cex_venue_binance",
        chain="off_chain_cex",
        protocol="binance_spot",
        execution_mode="shadow",
    ),
)
```

No new collections. No index changes. No endpoint changes. Existing analytics that filter by `strategy_type` and `chain` immediately see the new data.

## 10. Regression coverage

`app/backend/tests/test_mid_sprint1a.py` — 27 tests covering:
- Schema round-trip (metadata defaults, replay-context defaults, route_id stability, market_snapshot_id stability)
- Enum registry (seed values, open/closed semantics, register, snapshot)
- `ensure_indexes()` idempotency
- All 11 writer methods (happy path + upsert semantics for routes)
- Enum warning audit path
- Reader query with metadata filters
- REST endpoints (`/mid/status`, `/mid/query/{domain}`, `/mid/enums`, unknown-domain 404, metadata-filter passthrough)

Full v2.0.1 regression: **1469 passed, 76 skipped, 0 failed**.
