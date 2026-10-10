"""Flash-loan scanner runtime cache must mirror persisted enabled state.

Root cause: ``_refresh_caches_once`` copied ``enabled=false`` only when a
never-written ``_operator_set`` flag was present, and never copied
``enabled=true``. Resume updated Mongo; ``is_enabled()`` kept reading the
boot cache and every tick stayed a no-op.

These tests do not start SHADOW, do not enable the scanner at construction,
and do not weaken Gate 7/8/9.
"""
from __future__ import annotations

import inspect
import time
import uuid
from unittest.mock import MagicMock

from arbicore.models.discovery import (
    DiscoveryCandidate, VerifiedOutcome, make_candidate_id,
)
from arbicore.models.enums import OpportunityType
from arbicore.runtime import composition as comp
from arbicore.scanners.flash_loan_arbitrage.scanner import (
    FlashLoanArbitrageScanner,
)


def _boot_cache():
    return {
        "cfg": {
            "interval_s": 60.0,
            "chains": {
                "ethereum": {"enabled": False},
                "base": {"enabled": True},
                "bnb": {"enabled": False},
            },
            "route_search": {
                "max_hops": 4,
                "min_pool_tvl_usd": 100_000.0,
            },
            "providers": {},
        },
        "state": {"enabled": False},
    }


def test_factory_boots_disabled_and_mirrors_persisted_state():
    src = inspect.getsource(comp.get_flash_loan_arb_scanner)
    assert '"state": {"enabled": False}' in src
    assert "refresh_flash_loan_scanner_caches" in src
    assert 'rs.get("_operator_set")' not in src
    assert '"bnb": {"enabled": False}' in src


def test_persisted_enabled_true_is_reflected():
    cache = _boot_cache()
    row = {"enabled": True, "updated_by": "operator_resume"}
    comp.mirror_flash_loan_enabled_cache(cache, row)
    assert cache["state"]["enabled"] is True
    assert cache["state"]["updated_by"] == "operator_resume"
    # Config, chain posture, and TVL are not part of the state mirror.
    assert cache["cfg"]["chains"]["bnb"]["enabled"] is False
    assert cache["cfg"]["chains"]["base"]["enabled"] is True
    assert cache["cfg"]["route_search"]["min_pool_tvl_usd"] == 100_000.0


def test_persisted_enabled_false_stays_disabled():
    cache = _boot_cache()
    comp.mirror_flash_loan_enabled_cache(cache, {"enabled": True})
    comp.mirror_flash_loan_enabled_cache(
        cache, {"enabled": False, "updated_by": "operator_kill"})
    assert cache["state"]["enabled"] is False


def test_missing_or_non_bool_enabled_does_not_flip_cache():
    cache = _boot_cache()
    for persisted in (
        None,
        [],
        {},
        {"enabled": "true"},
        {"enabled": 1},
        {"enabled": None},
        {"_operator_set": True},
    ):
        comp.mirror_flash_loan_enabled_cache(cache, persisted)
        assert cache["state"]["enabled"] is False


def test_unreadable_state_leaves_cache_unchanged():
    cache = _boot_cache()
    comp.sync_flash_loan_runtime_cache(cache, None, None, cache["cfg"])
    assert cache["state"]["enabled"] is False
    cache["state"] = {"enabled": True}
    comp.sync_flash_loan_runtime_cache(cache, None, None, cache["cfg"])
    assert cache["state"]["enabled"] is True


def test_sync_mirrors_enabled_without_dropping_boot_config():
    boot = _boot_cache()["cfg"]
    cache = _boot_cache()
    comp.sync_flash_loan_runtime_cache(
        cache,
        {"route_search": {"max_hops": 4}},
        {"enabled": True},
        boot,
    )
    assert cache["state"]["enabled"] is True
    assert cache["cfg"]["chains"]["bnb"]["enabled"] is False
    assert cache["cfg"]["route_search"]["min_pool_tvl_usd"] == 100_000.0
    assert cache["cfg"]["route_search"]["max_hops"] == 4


def test_is_enabled_follows_mirrored_cache():
    cache = _boot_cache()
    scanner = _make_scanner(cache)
    assert scanner.is_enabled() is False
    comp.mirror_flash_loan_enabled_cache(cache, {"enabled": True})
    assert scanner.is_enabled() is True
    comp.mirror_flash_loan_enabled_cache(cache, {"enabled": False})
    assert scanner.is_enabled() is False


async def test_resume_and_pause_update_runtime_state(monkeypatch):
    import arbicore.routes.scanners as routes

    persisted = {"enabled": False}
    cache = _boot_cache()
    started = {"n": 0}

    class _Repo:
        async def set_enabled(self, scanner_id, enabled, actor="admin"):
            assert scanner_id == "flash_loan_arb"
            persisted["enabled"] = bool(enabled)
            persisted["updated_by"] = actor
            return dict(persisted)

    class _Scanner:
        def is_enabled(self):
            return bool(cache["state"].get("enabled", False))

        async def _refresh_caches_once(self):
            comp.mirror_flash_loan_enabled_cache(cache, persisted)

        async def start(self):
            started["n"] += 1

    scanner = _Scanner()

    async def _refresh_live():
        await scanner._refresh_caches_once()

    monkeypatch.setattr(routes, "get_scanner_state_repo", lambda: _Repo())
    monkeypatch.setattr(routes, "get_flash_loan_arb_scanner", lambda: scanner)
    monkeypatch.setattr(comp, "refresh_live_flash_loan_state_cache", _refresh_live)

    assert scanner.is_enabled() is False
    resumed = await routes.flash_loan_resume()
    assert resumed["enabled"] is True
    assert scanner.is_enabled() is True
    assert started["n"] == 1

    paused = await routes.flash_loan_kill()
    assert paused["enabled"] is False
    assert scanner.is_enabled() is False
    assert started["n"] == 1


async def test_refresh_live_does_not_construct_or_start(monkeypatch):
    monkeypatch.setattr(comp, "_flash_loan_arb_scanner", None)
    await comp.refresh_live_flash_loan_state_cache()
    assert comp._flash_loan_arb_scanner is None


async def test_refresh_live_updates_existing_scanner_only(monkeypatch):
    seen = {"n": 0}

    class _Live:
        async def _refresh_caches_once(self):
            seen["n"] += 1

        async def start(self):
            raise AssertionError("state refresh must not start the scanner")

    monkeypatch.setattr(comp, "_flash_loan_arb_scanner", _Live())
    await comp.refresh_live_flash_loan_state_cache()
    assert seen["n"] == 1


class _StateRepo:
    def __init__(self, doc):
        self.doc = doc
        self.fail = False

    async def get(self, scanner_id="flash_loan_arb"):
        assert scanner_id == "flash_loan_arb"
        if self.fail:
            raise RuntimeError("state read failed")
        return dict(self.doc)


class _CfgRepo:
    async def get(self, scanner_id="flash_loan_arb"):
        assert scanner_id == "flash_loan_arb"
        return {"interval_s": 60.0}


async def test_refresh_caches_once_reflects_persisted_enabled():
    cache = _boot_cache()
    boot = dict(cache["cfg"])
    state = _StateRepo({"enabled": True, "updated_by": "operator_resume"})
    state.fail = True
    scanner = _make_scanner(cache)
    await comp.refresh_flash_loan_scanner_caches(
        cache, _CfgRepo(), state, boot)
    assert scanner.is_enabled() is False

    state.fail = False
    await comp.refresh_flash_loan_scanner_caches(
        cache, _CfgRepo(), state, boot)
    assert scanner.is_enabled() is True

    state.doc = {"enabled": False, "updated_by": "operator_kill"}
    await comp.refresh_flash_loan_scanner_caches(
        cache, _CfgRepo(), state, boot)
    assert scanner.is_enabled() is False

    state.fail = True
    await comp.refresh_flash_loan_scanner_caches(
        cache, _CfgRepo(), state, boot)
    assert scanner.is_enabled() is False
    assert cache["cfg"]["chains"]["bnb"]["enabled"] is False
    assert cache["cfg"]["route_search"]["min_pool_tvl_usd"] == 100_000.0


def _spy_discover(scanner):
    calls = {"n": 0}
    for source in scanner._sources:
        real = source.discover

        async def _wrapped(_real=real):
            calls["n"] += 1
            return await _real()

        source.discover = _wrapped
    return calls


async def test_disabled_tick_is_noop_and_gate7_still_denies():
    cache = _boot_cache()
    queue = _Queue()
    bus = _SpyBus()
    scanner = _make_scanner(cache, queue=queue, bus=bus,
                             quote_provider=_unprofitable_quote)
    # Pin the route signature so the enabled tick does not rebuild sources
    # out from under the discover spy. Rebuild itself is unchanged.
    scanner._route_cfg_sig = scanner._route_sig(scanner._cfg() or {})
    discover_calls = _spy_discover(scanner)

    await scanner._tick()
    assert scanner.is_enabled() is False
    assert scanner.stats["iterations"] == 0
    assert discover_calls["n"] == 0
    assert queue.claims == 0
    assert bus.emits == []

    comp.mirror_flash_loan_enabled_cache(cache, {"enabled": True})
    queue.pending = _fresh_candidate()
    await scanner._tick()
    assert discover_calls["n"] == len(scanner._sources)
    assert scanner.stats["iterations"] == 1
    assert scanner.stats["rows_emitted"] == 0
    assert scanner.stats["verifier_confirmed"] == 0
    assert scanner.stats["gate_rejections"]["gate_7_atomic_profit"] >= 1
    assert scanner.stats["gate_rejections"]["gate_8_liquidity_depth"] == 0
    assert bus.emits == []
    assert queue.marked
    assert queue.marked[-1].startswith(VerifiedOutcome.DENIED_GATE_PREFIX + "gate_7")

    comp.mirror_flash_loan_enabled_cache(cache, {"enabled": False})
    queue.pending = _fresh_candidate()
    seen = discover_calls["n"]
    await scanner._tick()
    assert scanner.is_enabled() is False
    assert discover_calls["n"] == seen
    assert scanner.stats["iterations"] == 1
    # Hybrid E: one productive claim + one empty terminator claim_batch.
    assert queue.claims == 2
    assert bus.emits == []


def test_operations_action_refreshes_only_flash_loan_cache():
    """UI start/pause writes Mongo, then refreshes only the flash-loan cache.

    The handler must not construct or start the scanner.
    """
    from pathlib import Path
    text = Path(__file__).resolve().parents[1].joinpath("server.py").read_text(
        encoding="utf-8")
    start = text.index("async def v2_scanner_action")
    end = text.index("@api_router.get(", start)
    body = text[start:end]
    assert 'scanner_id == "flash_loan_arb"' in body
    assert "refresh_live_flash_loan_state_cache" in body
    assert ".start(" not in body


# --- fixtures ---------------------------------------------------------------

_GATES = {
    "min_atomic_profit_usd": 25.0,
    "min_pool_tvl_usd_in_route": 100_000.0,
    "max_flash_loan_mev_risk_class": "MEDIUM",
}


def _cfg():
    return {
        "interval_s": 60,
        "default_notional_usd": 10_000.0,
        "providers": {
            "aave_v3": {"enabled": False, "fee_bps": 5},
            "balancer_v2": {"enabled": False, "fee_bps": 0},
            "uniswap_v3": {"enabled": False, "fee_bps_default": 30},
        },
        "chains": {c: {"enabled": False, "gas_token": "ETH",
                       "tx_gas_units": 800_000}
                   for c in ("ethereum", "arbitrum", "base",
                             "optimism", "polygon", "bnb")},
        "route_search": {"max_hops": 4, "wall_clock_cap_s": 5.0,
                         "candidate_cap": 64, "min_pool_tvl_usd": 100_000},
        "gate_thresholds": {"default": dict(_GATES)},
        "roi_probability": {"min_sample_size": 2},
    }


class _SpyBus:
    def __init__(self):
        self.emits = []

    async def emit(self, opp, *, venue_ids=None, actor=None):
        self.emits.append(opp)


class _Queue:
    def __init__(self):
        self.pending = None
        self.claims = 0
        self.marked = []

    async def upsert_many(self, cands):
        return None

    async def claim_batch(self, worker_id, batch_size=32, claim_ttl_s=60.0):
        self.claims += 1
        item = self.pending
        self.pending = None
        return [item] if item is not None else []

    async def queue_status(self, fresh_window_s=120.0, include_breakdowns=True):
        return {
            "unclaimed_eligible": 0,
            "fresh_eligible": 0,
            "per_chain_backlog": {},
            "per_strategy_backlog": {},
        }

    async def mark_processed(self, candidate_id, outcome, opportunity_id=None,
                             observed_at=None):
        self.marked.append(outcome)


def _fresh_candidate() -> DiscoveryCandidate:
    observed = time.time()
    hm = {
        "chain": "base", "provider": "aave_v3",
        "borrow_token": "USDC", "hop_count": 2, "min_tvl_usd": 500_000.0,
        "estimated_total_fee_pct": 0.6,
        "route_pools": ["p1", "p2"],
        "route_dex_protocols": ["uniswap_v3", "sushiswap"],
        "cycle_token_path": ["USDC", "WETH", "USDC"],
    }
    subject = f"flash_loan:aave_v3:base:USDC:{uuid.uuid4().hex[:6]}"
    cid = make_candidate_id(
        hint_source="flash_loan_route_search",
        opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        subject_id=subject, asset="USDC",
        candidate_venues=["p1", "p2"], hint_observed_at=observed)
    return DiscoveryCandidate(
        candidate_id=cid,
        opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        hint_source="flash_loan_route_search", hint_observed_at=observed,
        subject_id=subject, asset="USDC", candidate_venues=["p1", "p2"],
        hint_metric=hm, reason="state-cache-regression")


async def _unprofitable_quote(hm, amt):
    return {
        "hop_legs": [{"venue_id": "p1", "fee_bps": 30, "slippage_pct": 5.0,
                      "source_id": "uniswap_v3_quoter_base"}],
        "gross_profit_pct": 0.0,
        "min_pool_tvl_usd_in_route": 500_000.0,
    }


def _make_scanner(cache, *, queue=None, bus=None, quote_provider=None):
    return FlashLoanArbitrageScanner(
        emission_bus=bus or _SpyBus(),
        discovery_queue=queue or _Queue(),
        venue_capability_repo=MagicMock(),
        config_loader=_cfg,
        state_loader=lambda: cache["state"],
        pool_loader=lambda chain: [],
        quote_provider=quote_provider,
    )
