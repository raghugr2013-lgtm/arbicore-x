"""Opportunity Ledger v1 projection. No Mongo production writes, no scanner."""
from __future__ import annotations

import asyncio
import json

from arbicore.observability import observe_strategy_intelligence
from arbicore.opportunity_ledger import (
    DEFINED_MODES,
    OCTOBER_5_SHADOW_RUN_ID,
    OpportunityLedgerRepo,
    project_opportunity_ledger,
)
from arbicore.opportunity_ledger.identity import ledger_id_for, opportunity_id_for
from arbicore.scanners.flash_loan_arbitrage.filter import FlashLoanGate7AtomicProfit

RUN = OCTOBER_5_SHADOW_RUN_ID
WHEN = "2026-10-05T06:00:00+00:00"
GATE7 = "denied:gate_rejection:gate_7:atomic_profit $-59.31 < floor $25.00"


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class MemoryCollection:
    def __init__(self) -> None:
        self.docs = []
        self.indexes = []

    async def create_index(self, keys, **kwargs):
        self.indexes.append((keys, kwargs))

    async def update_one(self, filt, update, upsert=False):
        found = None
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in filt.items()):
                found = doc
                break
        if found is None:
            if not upsert:
                return
            found = {}
            self.docs.append(found)
            for key, value in (update.get("$setOnInsert") or {}).items():
                found[key] = value
        for key, value in (update.get("$set") or {}).items():
            found[key] = value

    async def find_one(self, filt, projection=None):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in filt.items()):
                return {key: value for key, value in doc.items() if key != "_id"}
        return None

    async def count_documents(self, filt):
        return sum(
            1 for doc in self.docs
            if all(doc.get(key) == value for key, value in filt.items())
        )


class MemoryDB:
    def __init__(self) -> None:
        self._cols = {}

    def __getitem__(self, name):
        self._cols.setdefault(name, MemoryCollection())
        return self._cols[name]


def _candidate(**over):
    doc = {
        "candidate_id": "cand-dex",
        "chain": "base",
        "hint_observed_at": 1791178100.0,
        "verified_at": 1791178200.0,
        "verified_outcome": GATE7,
        "hint_source": "flash_loan_route_search",
        "subject_id": "flash_loan:balancer_v2:base:USDC",
        "hint_metric": {
            "provider": "balancer_v2",
            "chain": "base",
            "cycle_token_path": ["USDC", "WETH", "USDC"],
            "hop_count": 2,
            "route_pools": ["pool-a", "pool-b"],
            "route_dex_protocols": ["uniswap_v3", "aerodrome_slipstream"],
            "rpc_url": "https://base-mainnet.g.alchemy.com/v2/supersecretvalue",
        },
    }
    doc.update(over)
    return doc


def _bundle():
    return {
        "schema_version": "m2.3",
        "source_component": "flash_loan_arb_verifier",
        "bundle_id": "flarb:cand-dex:1",
        "candidate_id": "cand-dex",
        "source_model_id": "cand-dex",
        "opportunity_id": None,
        "chain": "base",
        "flash_loan_provider": "balancer_v2",
        "created_at": "2026-10-05T05:30:00+00:00",
        "outcome_tag": GATE7,
        "verification_status": "DENIED",
        "broadcast": False,
        "route": {
            "cycle_token_path": ["USDC", "WETH", "USDC"],
            "hop_count": 2,
            "route_pools": ["pool-a", "pool-b"],
            "route_dex_protocols": ["uniswap_v3", "aerodrome_slipstream"],
            "route_pool_addresses": [None, None],
        },
        "quotes": {
            "hop_legs": [
                {
                    "dex_protocol": "uniswap_v3",
                    "token_in": "USDC",
                    "token_out": "WETH",
                    "amount_in_wei": 1000,
                    "amount_out_wei": 900,
                    "fee_bps": 5,
                    "venue_id": "uniswap_v3:base",
                    "source_id": "uniswap_v3_quoter_base",
                    "block_number": 10,
                    "price": None,
                    "status": "ok",
                },
                {
                    "dex_protocol": "aerodrome_slipstream",
                    "token_in": "WETH",
                    "token_out": "USDC",
                    "amount_in_wei": 900,
                    "amount_out_wei": 990,
                    "fee_bps": 0,
                    "venue_id": "aerodrome_slipstream:base",
                    "source_id": "aerodrome_quoter_base",
                    "block_number": 11,
                    "price": None,
                    "status": "ok",
                },
            ],
            "route_quote_status": "ok",
            "gross_profit_pct": -0.5,
            "quote_notional_usd": 10000.0,
        },
        "fees": {
            "flash_loan_fee_usd": 0.0,
            "flash_loan_fee_bps": 0,
            "total_swap_fee_pct": 0.05,
            "total_slippage_pct": 0.0,
        },
        "gas": {"gas_cost_usd": 0.15, "tx_gas_units": 250000},
        "economics": {
            "gross_spread_pct": -0.5,
            "atomic_profit_usd": -59.31,
            "expected_net_after_costs_usd": -59.31,
            "borrow_amount_usd": 10000.0,
        },
        "gates": {
            "gate_7": {
                "status": "FAIL",
                "reason": "atomic_profit $-59.31 < floor $25.00",
            },
            "gate_8": {"status": "NOT_EVALUATED", "reason": None},
            "gate_9": {"status": "NOT_EVALUATED", "reason": None},
        },
        "mev": {"label": "MEDIUM"},
        "block_context": {"verified_at_ts": 1791178200.0, "block_number": 11},
    }


def _project(**kwargs):
    args = dict(
        candidate=_candidate(),
        bundle=_bundle(),
        run_id=RUN,
        mode="SHADOW",
        git_sha="823a79b617ddb1f19397cf5073b9c516aae4e9fd",
        network_config_revision="rev-1068cb9715194f118c99e5f04f9e1bdb",
        projected_at=WHEN,
    )
    args.update(kwargs)
    return project_opportunity_ledger(**args)


def test_defined_modes_are_labels_only():
    assert DEFINED_MODES == frozenset({"SHADOW", "PAPER", "RECOMMENDATION"})


def test_deterministic_identity_and_same_source():
    first = _project()
    second = _project()
    assert first["ledger_id"] == second["ledger_id"]
    assert first["opportunity_id"] == second["opportunity_id"] == "cand-dex"
    assert first["opportunity_id"] == opportunity_id_for(
        candidate_id="cand-dex", bundle=_bundle())
    assert first["ledger_id"] == ledger_id_for(
        mode="SHADOW", run_id=RUN, candidate_id="cand-dex")
    assert first["evidence"] == second["evidence"]
    assert first["run_id"] == RUN


def test_bundle_opportunity_id_is_reused_when_present():
    bundle = _bundle()
    bundle["opportunity_id"] = "flash_loan_arb:subj:1791178200"
    record = _project(bundle=bundle)
    assert record["opportunity_id"] == "flash_loan_arb:subj:1791178200"
    assert record["ledger_id"] == ledger_id_for(
        mode="SHADOW", run_id=RUN, candidate_id="cand-dex")
    assert record["candidate_id"] == "cand-dex"
    assert record["verifier_bundle_id"] == "flarb:cand-dex:1"


def test_projection_upsert_is_idempotent_and_keeps_annotations():
    db = MemoryDB()
    repo = OpportunityLedgerRepo(db)
    record = _project()

    async def go():
        await repo.ensure_indexes()
        await repo.upsert(record)
        stored = await repo.get(record["ledger_id"])
        stored["annotations"]["review"] = "keep"
        await repo.upsert(record)
        return await repo.get(record["ledger_id"]), db["arbicore_opportunity_ledger"]

    got, col = _run(go())
    assert _run(col.count_documents({"ledger_id": record["ledger_id"]})) == 1
    assert len(col.docs) == 1
    assert got["annotations"]["review"] == "keep"
    assert got["evidence"]["strategy"]["classifier_version"] == (
        "phase0.strategy_intelligence.v1")
    assert col.indexes[0][1]["unique"] is True


def test_decision_only_candidate_keeps_null_economics():
    candidate = _candidate(
        candidate_id="cand-do",
        chain="bnb",
        verified_outcome=(
            "denied:gate_rejection:gate_7:atomic_profit $-146.87 < floor $25.00"
        ),
        hint_metric={
            "provider": "aave_v3",
            "chain": "bnb",
            "cycle_token_path": ["USDC", "WETH", "WBTC", "USDT", "USDC"],
            "hop_count": 4,
            "route_pools": ["p1", "p2", "p3", "p4"],
            "route_dex_protocols": ["uniswap_v3"] * 4,
        },
    )
    observed = observe_strategy_intelligence(None, candidate)
    record = project_opportunity_ledger(
        candidate=candidate, bundle=None, run_id=RUN, mode="SHADOW",
        projected_at=WHEN,
    )
    assert record["verifier_bundle_id"] is None
    assert record["opportunity_id"] == "cand-do"
    strategy = record["evidence"]["strategy"]
    assert strategy["primary_family"] == observed["strategy"]["primary_family"]
    assert strategy["classifier_version"] == "phase0.strategy_intelligence.v1"
    assert strategy["classification_completeness"] == (
        observed["strategy"]["strategy_completeness"])
    econ = record["evidence"]["economics"]
    assert econ["notional_usd"] is None
    assert econ["gross_profit_usd"] is None
    assert econ["true_net_usd"] is None
    assert econ["total_cost_usd"] is None
    gates = record["evidence"]["gates"]
    assert gates["gate_7"]["status"] is None
    assert gates["final_observed_status"].endswith("floor $25.00")
    assert gates["decision_net_usd"] == -146.87
    assert record["evidence"]["provenance"]["bundle_presence"] == "NO_BUNDLE"


def test_phase0_classification_and_leg_order_and_zeros():
    candidate = _candidate()
    bundle = _bundle()
    observed = observe_strategy_intelligence(bundle, candidate)
    record = _project()
    strategy = record["evidence"]["strategy"]
    assert strategy["primary_family"] == observed["strategy"]["primary_family"]
    assert strategy["primary_family"] == "DEX_TO_DEX"
    assert strategy["secondary_tags"] == observed["strategy"]["secondary_tags"]
    assert strategy["confidence"] == observed["strategy"]["confidence"]
    assert strategy["classification_completeness"] == "FULLY_CLASSIFIED"
    legs = record["evidence"]["legs"]
    assert [leg["leg_index"] for leg in legs] == [0, 1]
    assert [leg["token_in"] for leg in legs] == ["USDC", "WETH"]
    assert [leg["protocol"] for leg in legs] == ["uniswap_v3", "aerodrome_slipstream"]
    assert legs[1]["fee_bps"] == 0
    assert legs[0]["quote"] is None
    assert legs[0]["quote_timestamp"] is None
    assert legs[0]["input_amount"] == 1000
    assert legs[1]["output_amount"] == 990
    econ = record["evidence"]["economics"]
    assert econ["flash_loan_fee_usd"] == 0.0
    assert econ["slippage_pct"] == 0.0
    assert econ["gross_profit_usd"] is None
    assert econ["dex_fee_usd"] is None
    assert econ["true_net_pct"] is None
    assert econ["mev_penalty"] is None
    assert econ["total_cost_usd"] is None
    assert econ["true_net_usd"] == -59.31
    assert econ["notional_usd"] == 10000.0
    gates = record["evidence"]["gates"]
    assert gates["gate_7"]["status"] == "FAIL"
    assert gates["gate_7"]["reason"] == "atomic_profit $-59.31 < floor $25.00"
    assert gates["gate_8"]["status"] == "NOT_EVALUATED"
    assert gates["gate_9"]["status"] == "NOT_EVALUATED"
    assert gates["final_observed_status"] == GATE7
    assert gates["decision_net_usd"] == -59.31


def test_shape_without_protocols_is_not_assigned_a_family():
    candidate = _candidate(
        candidate_id="cand-shape",
        hint_metric={
            "provider": "aave_v3",
            "chain": "base",
            "cycle_token_path": ["USDC", "WETH", "ARB", "USDC"],
            "hop_count": 3,
            "route_pools": ["a", "b", "c"],
        },
    )
    record = project_opportunity_ledger(
        candidate=candidate, bundle=None, run_id=RUN, mode="RECOMMENDATION",
        projected_at=WHEN,
    )
    assert record["mode"] == "RECOMMENDATION"
    assert record["evidence"]["strategy"]["primary_family"] == "UNCLASSIFIED"
    assert record["evidence"]["strategy"]["classification_state"] == "INCOMPLETE"


def test_provenance_drops_secrets_and_keeps_safe_fingerprint():
    candidate = _candidate(
        chain="https://eth-mainnet.g.alchemy.com/v2/supersecretvalue",
        verified_outcome="mongodb://user:supersecretvalue@mongo:27017/db",
    )
    record = project_opportunity_ledger(
        candidate=candidate,
        bundle=_bundle(),
        run_id=RUN,
        mode="PAPER",
        git_sha="https://user:supersecretvalue@github.com/org/repo",
        network_config_revision="rev-not-a-fingerprint",
        projected_at=WHEN,
    )
    blob = json.dumps(record)
    assert "supersecretvalue" not in blob
    assert "mongodb://" not in blob
    assert "alchemy.com" not in blob
    assert record["evidence"]["provenance"]["secrets_withheld"] is True
    assert record["evidence"]["provenance"]["git_sha"] is None
    assert record["evidence"]["provenance"]["network_config_revision"] is None
    assert record["evidence"]["provenance"]["rpc_identity"] is None
    clean = _project()
    assert clean["evidence"]["provenance"]["secrets_withheld"] is False
    assert clean["evidence"]["provenance"]["git_sha"] == (
        "823a79b617ddb1f19397cf5073b9c516aae4e9fd")
    assert clean["evidence"]["provenance"]["network_config_revision"] == (
        "rev-1068cb9715194f118c99e5f04f9e1bdb")
    assert clean["mode"] == "SHADOW"


def test_gate7_dynamic_floor_and_reporting_25():
    from arbicore.scanners.flash_loan_arbitrage.filter import (
        REPORTING_ATOMIC_PROFIT_FLOOR_USD)
    gate = FlashLoanGate7AtomicProfit(thresholds={})
    below_reporting = gate.evaluate(
        atomic_profit_usd=24.99, borrow_amount_usd=10000.0)
    at_reporting = gate.evaluate(
        atomic_profit_usd=25.0, borrow_amount_usd=10000.0)
    neg = gate.evaluate(atomic_profit_usd=-1.0, borrow_amount_usd=10000.0)
    assert below_reporting.passed is True  # $25 is not a hard reject
    assert at_reporting.passed is True
    assert at_reporting.reason == "atomic-profit gate passed"
    assert neg.passed is False
    assert REPORTING_ATOMIC_PROFIT_FLOOR_USD == 25.0
    # Operator-raised floor still works
    raised = FlashLoanGate7AtomicProfit(
        thresholds={"min_atomic_profit_usd": 25.0})
    r = raised.evaluate(atomic_profit_usd=24.99, borrow_amount_usd=10000.0)
    assert r.passed is False
    assert r.reason == "atomic_profit $24.99 < floor $25.00"
