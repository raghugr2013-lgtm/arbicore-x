"""D-5.1 — ChainLivenessRegistry tests."""
from __future__ import annotations

import asyncio
from typing import Any, Dict

import pytest

from arbicore.scanners.cross_chain_arbitrage.chain_liveness import (
    ChainLivenessRegistry, ChainLivenessSnapshot,
)


@pytest.fixture
def chain_cfg() -> Dict[str, Any]:
    return {
        "chains": {
            "ethereum": {"enabled": False, "gas_token": "ETH"},
            "arbitrum": {"enabled": False, "gas_token": "ETH"},
            "base":     {"enabled": False, "gas_token": "ETH"},
            "optimism": {"enabled": False, "gas_token": "ETH"},
            "polygon":  {"enabled": False, "gas_token": "MATIC"},
            "solana":   {"enabled": False, "gas_token": "SOL"},
        }
    }


def test_default_snapshot_is_calm(chain_cfg):
    reg = ChainLivenessRegistry(config_loader=lambda: chain_cfg)
    snap = reg.get("ethereum")
    assert snap.chain == "ethereum"
    assert snap.congestion_score < 50.0
    assert snap.ok is True
    assert snap.gas_token == "ETH"


def test_default_finality_is_chain_specific(chain_cfg):
    reg = ChainLivenessRegistry(config_loader=lambda: chain_cfg)
    eth = reg.get("ethereum")
    arb = reg.get("arbitrum")
    sol = reg.get("solana")
    assert eth.finality_s > arb.finality_s
    assert sol.finality_s < eth.finality_s


def test_all_snapshots_covers_in_scope_chains(chain_cfg):
    reg = ChainLivenessRegistry(config_loader=lambda: chain_cfg)
    snaps = reg.all_snapshots()
    assert set(snaps.keys()) == {
        "ethereum", "arbitrum", "base", "optimism", "polygon", "solana"}


def test_default_loader_is_noop(chain_cfg):
    reg = ChainLivenessRegistry(config_loader=lambda: chain_cfg)
    out = asyncio.run(reg.refresh())
    assert out == {} or all(
        isinstance(v, ChainLivenessSnapshot) for v in out.values())


def test_custom_loader_populates_snapshots(chain_cfg):
    async def loader():
        return {
            "ethereum": {"finality_s": 12.0, "congestion_score": 65.0,
                          "gas_token": "ETH", "ok": True},
            "polygon":  {"finality_s": 256.0, "congestion_score": 40.0,
                          "gas_token": "MATIC", "ok": True},
        }
    reg = ChainLivenessRegistry(config_loader=lambda: chain_cfg,
                                 liveness_loader=loader)
    asyncio.run(reg.refresh())
    eth = reg.get("ethereum")
    assert eth.congestion_score == 65.0
    assert eth.finality_s == 12.0


def test_loader_exception_does_not_raise(chain_cfg):
    async def bad_loader():
        raise RuntimeError("rpc dead")
    reg = ChainLivenessRegistry(config_loader=lambda: chain_cfg,
                                 liveness_loader=bad_loader)
    asyncio.run(reg.refresh())
    assert reg.last_error is not None
    assert "RuntimeError" in reg.last_error


def test_set_loader_at_runtime(chain_cfg):
    reg = ChainLivenessRegistry(config_loader=lambda: chain_cfg)

    async def loader():
        return {"ethereum": {"finality_s": 5.0, "congestion_score": 10.0,
                              "gas_token": "ETH"}}
    reg.set_loader(loader)
    assert reg._loader is loader  # noqa: SLF001


def test_inv2_chain_liveness_does_not_import_emission_bus():
    import arbicore.scanners.cross_chain_arbitrage.chain_liveness as mod
    text = open(mod.__file__).read()
    assert "from ...emission_bus" not in text
    assert "from ...runtime.event_bus" not in text
